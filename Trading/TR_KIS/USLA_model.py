import yfinance as yf
import pandas as pd
import numpy as np
import riskfolio as rp
import KIS_US
import json
from datetime import datetime, date
import time as time_module  # time 모듈을 별칭으로 import
import calendar
import warnings
warnings.filterwarnings('ignore')

class USLA_Model(KIS_US.KIS_API): #상속
    def __init__(self, key_file_path, token_file_path, cano, acnt_prdt_cd):
        super().__init__(key_file_path, token_file_path, cano, acnt_prdt_cd)  # 부모 생성자 호출
        self.etf_tickers = ['UPRO', 'TQQQ', 'EDC', 'TMF', 'TMV']
        self.all_tickers = self.etf_tickers + ['CASH']
        self.tax_rate = 0.0009
        self.USLA_rebalancing_data_path = "C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/USLA_rebalancing_data.json"  

    def get_month_end_date(self, year, month): # run_strategy함수에 종속되어 월말일 계산
        """월말일 반환"""
        last_day = calendar.monthrange(year, month)[1]
        return f'{year}-{month:02d}-{last_day}'
    
    def calculate_regime(self, target_month, target_year): # run_strategy함수에 종속되어 Regime Signal 계산
        """AGG ETF 기반 Regime Signal 계산"""
        try:
            # 4개월 전 시작일 계산
            start_month = target_month - 4
            start_year = target_year
            
            if start_month <= 0:
                start_month = 12 + start_month
                start_year = target_year - 1
                
            # 전월 말일 계산    
            prev_month = target_month - 1 if target_month > 1 else 12
            prev_year = target_year if target_month > 1 else target_year - 1
            
            start_date = f'{start_year}-{start_month:02d}-01'
            end_date = self.get_month_end_date(prev_year, prev_month)
            
            # AGG 데이터 다운로드
            agg_data = yf.download('AGG', start=start_date, end=end_date, 
                                 interval='1mo', progress=False, multi_level_index=False)['Close']
            
            if len(agg_data) < 4:
                print("경고: AGG 데이터가 충분하지 않습니다.")
                return 0
                
            current_price = agg_data.iloc[-1]  # 최신 가격
            avg_price = agg_data.mean()  # 4개월 평균
            
            regime = current_price - avg_price
            
            return regime
            
        except Exception as e:
            print(f"Regime 계산 오류: {e}")
            return 0
    
    def calculate_momentum(self, target_month, target_year): # run_strategy함수에 종속되어 모멘텀점수 계산
        """모멘텀 점수 계산"""
        try:
            # 13개월 데이터 필요 (현재 + 12개월)
            start_year = target_year - 2
            prev_month = target_month - 1 if target_month > 1 else 12
            prev_year = target_year if target_month > 1 else target_year - 1
            
            start_date = f'{start_year}-{target_month:02d}-01'
            end_date = self.get_month_end_date(prev_year, prev_month)
            
            # 가격 데이터 다운로드
            price_data = yf.download(self.etf_tickers, start=start_date, end=end_date,
                                   interval='1mo', progress=False, multi_level_index=False)['Close']
            
            if len(price_data) < 13:
                print("경고: 모멘텀 계산을 위한 데이터가 충분하지 않습니다.")
                return pd.DataFrame()
                
            momentum_scores = []
            
            for ticker in self.etf_tickers:
                try:
                    prices = price_data[ticker].dropna()
                    if len(prices) < 13:
                        continue
                        
                    # 현재가 기준 수익률 계산
                    current = prices.iloc[-1]
                    returns = {
                        '1m': (current / prices.iloc[-2] - 1) if len(prices) >= 2 else 0,
                        '3m': (current / prices.iloc[-4] - 1) if len(prices) >= 4 else 0,
                        '6m': (current / prices.iloc[-7] - 1) if len(prices) >= 7 else 0,
                        '9m': (current / prices.iloc[-10] - 1) if len(prices) >= 10 else 0,
                        '12m': (current / prices.iloc[-13] - 1) if len(prices) >= 13 else 0
                    }
                    
                    # 모멘텀 점수 계산 (가중평균)
                    score = (returns['1m'] * 30 + returns['3m'] * 25 + 
                            returns['6m'] * 20 + returns['9m'] * 15 + 
                            returns['12m'] * 10)
                    
                    momentum_scores.append({
                        'ticker': ticker,
                        'momentum': score,
                        '1m_return': returns['1m'],
                        '3m_return': returns['3m'],
                        '12m_return': returns['12m']
                    })
                    
                except Exception as e:
                    print(f"{ticker} 모멘텀 계산 오류: {e}")
                    continue
            
            if not momentum_scores:
                return pd.DataFrame()
                
            momentum_df = pd.DataFrame(momentum_scores)
            momentum_df['rank'] = momentum_df['momentum'].rank(ascending=False)
            momentum_df = momentum_df.sort_values('rank').reset_index(drop=True)
            
            return momentum_df
            
        except Exception as e:
            print(f"모멘텀 점수 계산 오류: {e}")
            return pd.DataFrame()
    
    def calculate_portfolio_weights(self, top_tickers): # run_strategy함수에 종속되어 최소분산 포트폴리오 가중치 계산
            """최소분산 포트폴리오 가중치 계산"""
            try:
                # 최근 3개월 일일 수익률 데이터
                Hist = yf.download(tickers=top_tickers, period='3mo', auto_adjust=True, interval='1d', 
                                        progress=False)['Close']
                Hist.sort_index(axis=0, ascending=False, inplace=True)
                
                Hist = Hist.iloc[: 45]
                Ret = Hist.pct_change(-1).dropna()
                Ret = Ret.round(4)

                port = rp.Portfolio(returns=Ret)
                method_mu = 'hist'
                method_cov = 'hist'
                port.assets_stats(method_mu=method_mu, method_cov=method_cov)

                model = 'Classic'
                rm = 'MV'
                obj = 'MinRisk'
                hist = True
                rf = 0
                l = 0

                # 유니버스 데이터베이스
                ticker_class = []
                for i in top_tickers :
                    if i == 'UPRO' or i == 'TQQQ' or i == 'EDC' :
                        ticker_class.append('stock')
                    else : 
                        ticker_class.append('bond')

                asset_classes = {
                    'Asset' : [top_tickers[0], top_tickers[1]],
                    'Class' : [ticker_class[0], ticker_class[1]]}

                asset_classes = pd.DataFrame(asset_classes)

                # 제약조건 설정 데이터베이스
                constraints = {'Disabled' : [False, False],
                            'Type' : ['All Assets', 'All Assets'],
                            'Set' : ['', ''],
                            'Position' : ['', ''],
                            'Sign' : ['>=', '<='],
                            'Weight' : [0.2, 0.8],
                            'Type Relative' : ['', ''],
                            'Relative Set' : ['', ''],
                            'Relative' : ['', ''],
                            'Factor' : ['', '']}

                constraints = pd.DataFrame(constraints)


                # 제약조건 적용 MVP모델 Weight 해찾기
                A, B = rp.assets_constraints(constraints, asset_classes)

                port.ainequality = A
                port.binequality = B

                weights = port.optimization(model=model, rm=rm, obj=obj, rf=rf, l=l, hist=hist)
                
                if weights is None or weights.empty:
                    print("최적화 실패: 동일가중으로 설정")
                    return {ticker: 1.0/len(top_tickers) for ticker in top_tickers}
                
                weight_dict = {}
                for i, ticker in enumerate(top_tickers):
                    weight_dict[ticker] = float(weights.iloc[i, 0]) * 0.99
                    
                return weight_dict
                
            except Exception as e:
                print(f"포트폴리오 최적화 오류: {e}")
                # 동일가중으로 폴백
                equal_weight = 0.99 / len(top_tickers)
                return {ticker: equal_weight for ticker in top_tickers}
    
    def get_USLA_current_prices(self): # run_strategy함수에 종속되어 USLA model의 현재 가격 조회
        """현재 가격 조회"""
        try:
            prices = {}
            for ticker in self.etf_tickers:
                data = yf.download(ticker, period='1d', interval='1d', progress=False, multi_level_index=False)['Close']
                prices[ticker] = float(data.iloc[-1])
            prices['CASH'] = 1.0
            return prices
        except Exception as e:
            print(f"가격 조회 오류: {e}")
            return {ticker: 100.0 for ticker in self.all_tickers}  # 기본값
    
    def run_strategy(self, target_month=None, target_year=None): # USLA model의 Regime signal, momentum결과 투자 ticker 및 비중
        """전략 실행"""
        if target_month is None or target_year is None:
            today = date.today()
            target_month = today.month
            target_year = today.year
            
        print(f"\n=== {target_year}년 {target_month}월 USLA 모멘텀 시그널 ===") # Kakao
        
        # 1. Regime Signal 계산
        regime = self.calculate_regime(target_month, target_year)
        
        # 2. 모멘텀 점수 계산
        momentum_df = self.calculate_momentum(target_month, target_year)
        
        if momentum_df.empty:
            print("모멘텀 데이터를 계산할 수 없습니다.")
            return None
            
        print("\n모멘텀 순위:")
        print(momentum_df[['ticker', 'momentum', 'rank']].round(4))
        
        # 3. 투자 전략 결정
        if regime < 0: # < 0으로 변경, 테스트 후엔
            print(f"\nRegime Signal: {regime:.2f} < 0 → RISK 모드")
            print("투자 결정: 100% CASH")
            allocation = {ticker: 0.0 for ticker in self.etf_tickers}
            allocation['CASH'] = 1.0

        else:
            print(f"\nRegime Signal: {regime:.2f} ≥ 0 → 투자 모드")
            
            # 상위 2개 ETF 선택
            top_2_tickers = momentum_df.head(2)['ticker'].tolist()
            
            # 포트폴리오 가중치 계산
            weights = self.calculate_portfolio_weights(top_2_tickers)
            
            allocation = {ticker: 0.0 for ticker in self.etf_tickers}
            allocation.update(weights)
            allocation['CASH'] = 0.01  # 1% 현금 보유
        
        # 4. 현재 가격 조회
        current_prices = self.get_USLA_current_prices()
        
        # 5. 결과 출력
        print("\n최종 배분:")
        for ticker in self.all_tickers:
            if allocation.get(ticker, 0) > 0:
                print(f"{ticker}: {allocation[ticker]:.1%} (현재가: ${current_prices[ticker]:.2f})")
        
        return {
            'regime': regime,
            'momentum': momentum_df,
            'allocation': allocation,
            'current_prices': current_prices
        }
    
    def USLA_rebalancing_data(self): # make_trading_data함수에 종속되어 USLA data 불러오기
        """USLA data 불러오기"""   
        try:
            with open(self.USLA_rebalancing_data_path, 'r', encoding='utf-8') as f:
                USLA_data = json.load(f)
            return USLA_data

        except Exception as e:
            print(f"JSON 파일 오류: {e}")
            exit()

    def calculate_USD_value(self, hold): # make_trading_data함수에 종속되어 USD 환산 잔고 계산
        """USD 환산 잔고 계산"""
        hold_USD_value = 0
        for t in hold.keys():
            if t == "CASH":
                # USLA_CASH도 float로 변환
                hold_USD_value += float(hold["CASH"])
            else:
                price = self.get_US_current_price(ticker=t)
                # hold[t]를 float로 변환
                qty = float(hold[t])
                value = price * qty * (1 - self.tax_rate)
                hold_USD_value += value

        return hold_USD_value
    
    def target_ticker_weight(self): # make_trading_data함수에 종속되어 target 티커별 목표 비중 산출
        """USLA 모델 실행, target ticker와 weight 구하기"""
        invest = self.run_strategy()
        target = {
            ticker: weight 
            for ticker, weight in invest['allocation'].items() 
            if weight > 0
        }
        return target

    def calculate_target_qty(self, target, target_usd_value): # make_trading_data함수에 종속되어 target 티커별 목표 quantity 산출
        # 보유 $기준 잔고를 바탕으로 목표 비중에 맞춰 ticker별 quantity 계산
        target_qty = {}
        target_stock_value = 0
        for ticker in target.keys():
            if ticker != "CASH":
                try:
                    price = self.get_US_current_price(ticker)
                    if price and price > 0:
                        target_qty[ticker] = int(target_usd_value[ticker] / price)
                        target_stock_value += target_qty[ticker] * price * (1 + self.tax_rate)
                    else:
                        print(f"{ticker}: 가격 정보 없음")
                        target_qty[ticker] = 0
                except Exception as e:
                    print(f"{ticker}: 수량 계산 오류 - {e}")
                    target_qty[ticker] = 0

        target_qty["CASH"] = sum(target_usd_value.values()) - target_stock_value

        return target_qty
    
    def make_split_data(self, market, round): # make_trading_data함수에 종속되어 시장과 시간대별 티커별 분할횟수와 분할당 가격 산출
        if market == "Pre-market":
            order_type = "order_daytime_US"
            sell_splits = 4
            sell_price_adjust = [1.015, 1.03, 1.045, 1.06]
            buy_splits = 2
            buy_price_adjust = [0.995, 0.99]

        elif market == "Regular":
            order_type = "order_US"
            sell_splits = 6
            sell_price_adjust = [1.0025, 1.005, 1.0075, 1.01, 1.0125, 1.015]
            buy_splits = 6
            buy_price_adjust = [0.9975, 0.995, 0.9925, 0.99, 0.9875, 0.985]

            if round in range(1, 7):
                pass

            elif round in range(7, 13):
                sell_price_adjust[0] = 0.99

            elif round in range(13, 19):
                sell_splits = 5
                sell_price_adjust = sell_price_adjust[:sell_splits]
                buy_price_adjust[0] = 1.01

            elif round in range(19, 25):
                sell_splits = 5
                sell_price_adjust = sell_price_adjust[:sell_splits]
                buy_splits = 5
                buy_price_adjust = buy_price_adjust[:buy_splits]

            elif round in range(25, 31):
                sell_splits = 5
                sell_price_adjust = sell_price_adjust[:sell_splits]
                sell_price_adjust[0] = 0.99
                buy_splits = 5
                buy_price_adjust = buy_price_adjust[:buy_splits]

            elif round in range(31, 37):
                sell_splits = 4
                sell_price_adjust = sell_price_adjust[:sell_splits]
                buy_splits = 5
                buy_price_adjust = buy_price_adjust[:buy_splits]
                buy_price_adjust[0] = 1.01

            elif round in range(37, 43):
                sell_splits = 4
                sell_price_adjust = sell_price_adjust[:sell_splits]
                buy_splits = 4
                buy_price_adjust = buy_price_adjust[:buy_splits]

            elif round in range(43, 49):
                sell_splits = 4
                sell_price_adjust = sell_price_adjust[:sell_splits]
                sell_price_adjust[0] = 0.99
                buy_splits = 4
                buy_price_adjust = buy_price_adjust[:buy_splits]

            elif round in range(49, 55):
                sell_splits = 3
                sell_price_adjust = sell_price_adjust[:sell_splits]
                buy_splits = 4
                buy_price_adjust = buy_price_adjust[:buy_splits]
                buy_price_adjust[0] = 1.01

            elif round in range(55, 61):
                sell_splits = 3
                sell_price_adjust = sell_price_adjust[:sell_splits]
                buy_splits = 3
                buy_price_adjust = buy_price_adjust[:buy_splits]

            elif round in range(61, 67):
                sell_splits = 3
                sell_price_adjust = sell_price_adjust[:sell_splits]
                sell_price_adjust[0] = 0.99
                buy_splits = 3
                buy_price_adjust = buy_price_adjust[:buy_splits]

            elif round in range(67, 73):
                sell_splits = 2
                sell_price_adjust = sell_price_adjust[:sell_splits]
                buy_splits = 3
                buy_price_adjust = buy_price_adjust[:buy_splits]
                buy_price_adjust[0] = 1.01

            elif round in range(73, 76):
                sell_splits = 2
                sell_price_adjust = [0.99, 1.0025]
                buy_splits = 2
                buy_price_adjust = buy_price_adjust[:buy_splits]

            elif round == 77:
                sell_splits = 1
                sell_price_adjust = [0.97]
                buy_splits = 2
                buy_price_adjust = [1.01, 0.9975]

            elif round == 78:
                sell_splits = 1
                sell_price_adjust = [0.97]
                buy_splits = 1
                buy_price_adjust = [1.03]
            
        round_split = {
            "order_type": order_type,
            "sell_splits": sell_splits, 
            "sell_price_adjust": sell_price_adjust, 
            "buy_splits": buy_splits, 
            "buy_price_adjust": buy_price_adjust
        }

        return round_split

    def USLA_trading_data(self, order_time):
        """trading에 필요한 모든 데이터 구하기"""
        # oround_split 딕셔너리에 있는 key값을 value값으로 변환, 시장 시간대, 회차 구하기
        market = order_time['market']
        round = order_time['round']
        round_split = self.make_split_data(market, round)

        # order_type = round_split['order_type']
        sell_splits = round_split['sell_splits']
        sell_price_adjust = round_split['sell_price_adjust']
        buy_splits = round_split['buy_splits']
        buy_price_adjust = round_split['buy_price_adjust']

        # 지난 시즌 저장한 USLA_rebalancing_data.json 불러오기
        USLA_data = self.USLA_rebalancing_data()

        # 보유 티커 및 전체 잔고 및 달러화 가치, 목표 티커 및 전체 비중 수량 달러화 가치 구하기
        hold = {ticker: float(qty) for ticker, qty in zip(USLA_data['ticker'], USLA_data['qty'])} # Hold dict 생성, ticker별 qty를 float로 변환
        hold_ticker = list(hold.keys()) # hold tocker 리스트
        hold_USD_value = self.calculate_USD_value(hold) # Hold 보유 잔고를 바탕으로 USD 환산 잔고 계산
        target = self.target_ticker_weight() # target_ticker별 비중 dict
        target_ticker = list(target.keys()) # target_ticker 리스트
        target_usd_value = {ticker: target[ticker] * hold_USD_value for ticker in target.keys()} # target_ticker별 USD 배정 dict
        target_qty = self.calculate_target_qty(target, target_usd_value) # target_ticker별 목표 quantity 계산

        # data 정리
        meta_data = {
            'date': order_time['date'],
            'time': order_time['time'],
            'model': 'USLA',
            'season': order_time['season'],
            'market': order_time['market'],
            'order_type': round_split['order_type'], #####에러발생했던 부분#####
            'round': order_time['round'],
            'total_round': order_time['total_round']
        }

        buy_ticker = {} # buy 티커 dict 초기화
        sell_ticker = {} # sell 티커 dict 초기화
        keep_ticker = {} # keep 티커 dict 초기화
        CASH = {} # CASH dict 초기화

        # buy, sell, keep 티커 트레이딩 수량 구하기
        for ticker in hold_ticker:
            if ticker not in target_ticker:
                qty_per_split = int(hold[ticker] // buy_splits)
                sell_ticker[ticker] = {
                    'position': 'sell',
                    'hold_qty': hold[ticker],
                    'target_qty': 0,
                    'trading_qty': hold[ticker],
                    'splits': sell_splits,
                    'price_adjust': sell_price_adjust,
                    'qty_per_split': qty_per_split,
                    'order_status': 'ready',
                    'orders': [                      
                    ]
                }
                for price_adjust in sell_price_adjust: # sell > -self.tax_rate
                    sell_ticker[ticker]['orders'].append({
                        'order_num': 0,
                        'order_price': self.get_US_current_price(ticker) * price_adjust,
                        'qty': qty_per_split,
                        'splits_value': qty_per_split * self.get_US_current_price(ticker) * (price_adjust-self.tax_rate),
                        'status': 'ready',
                        'filled_qty': 0,
                        'filled_value': 0,
                        "unfilled_qty": 0,
                        "unfilled_value": 0
                    })
                    time_module.sleep(0.05)

            else:
                edited_qty = int(target_qty[ticker]) - int(hold[ticker])
                if edited_qty > 0:
                    qty_per_split = int(edited_qty // buy_splits)
                    buy_ticker[ticker] = {
                        'position': 'buy',
                        'hold_qty': hold[ticker],
                        'target_qty': target_qty[ticker],
                        'trading_qty': edited_qty,
                        'splits': buy_splits,
                        'price_adjust': buy_price_adjust,
                        'qty_per_split': qty_per_split,
                        'order_status': 'ready',
                        'orders': [                      
                        ]
                    }
                    for price_adjust in buy_price_adjust: # buy > +self.tax_rate
                        buy_ticker[ticker]['orders'].append({
                            'order_num': 0,
                            'order_price': self.get_US_current_price(ticker) * price_adjust,
                            'qty': qty_per_split,
                            'splits_value': qty_per_split * self.get_US_current_price(ticker) * (price_adjust+self.tax_rate),
                            'status': 'ready',
                            'filled_qty': 0,
                            'filled_value': 0,
                            "unfilled_qty": 0,
                            "unfilled_value": 0
                        })
                    time_module.sleep(0.05)

                elif edited_qty < 0:
                    qty_per_split = int(abs(edited_qty) // buy_splits)
                    sell_ticker[ticker] = {
                        'position': 'sell',
                        'hold_qty': hold[ticker],
                        'target_qty': target_qty[ticker],
                        'trading_qty': abs(edited_qty),
                        'splits': sell_splits,                       
                        'price_adjust': sell_price_adjust,
                        'qty_per_split': qty_per_split,
                        'order_status': 'ready',
                        'orders': [                      
                        ]
                    }
                    for price_adjust in sell_price_adjust: # sell > -self.tax_rate
                        sell_ticker[ticker]['orders'].append({
                            'order_num': 0,
                            'order_price': self.get_US_current_price(ticker) * price_adjust,
                            'qty': qty_per_split,
                            'splits_value': qty_per_split * self.get_US_current_price(ticker) * (price_adjust-self.tax_rate),
                            'status': 'ready',
                            'filled_qty': 0,
                            'filled_value': 0,
                            "unfilled_qty": 0,
                            "unfilled_value": 0
                        })
                        time_module.sleep(0.05)

                elif edited_qty == 0:
                    qty_per_split = 0
                    keep_ticker[ticker] = {
                        'position': 'keep',
                        'hold_qty': hold[ticker],
                        'target_qty': target_qty[ticker],
                        'trading_qty': edited_qty,
                        'splits': 0,
                        'price_adjust': 0,
                        'qty_per_split': 0,
                        'order_status': 'hold',
                        'orders': [                      
                        ]
                    }

        for target in target_ticker:
            if target not in hold_ticker:
                qty_per_split = int(target_qty[target] // buy_splits)
                buy_ticker[target] = {
                    'position': 'buy',
                    'hold_qty': 0,
                    'target_qty': target_qty[target],
                    'trading_qty': target_qty[target],
                    'splits': buy_splits,
                    'price_adjust': buy_price_adjust,
                    'qty_per_split': qty_per_split,
                    'order_status': 'ready',
                    'orders': [                      
                    ]
                }
                for price_adjust in buy_price_adjust: # buy > +self.tax_rate
                    buy_ticker[target]['orders'].append({
                        'order_num': 0,
                        'order_price': self.get_US_current_price(target) * price_adjust,
                        'qty': qty_per_split,
                        'splits_value': qty_per_split * self.get_US_current_price(target) * (price_adjust+self.tax_rate),
                        'status': 'ready',
                        'filled_qty': 0,
                        'filled_value': 0,
                        "unfilled_qty": 0,
                        "unfilled_value": 0
                    })
                time_module.sleep(0.1)

        hold_cash = hold['CASH']
        target_cash = target_qty['CASH']

        CASH = {
            'position': 'cash',
            'hold_qty': hold_cash,
            'target_qty': target_cash,
            'expected_change': target_cash - hold_cash
        }

        TR_data = {
            "metadata": meta_data,
            "sell_ticker": sell_ticker,
            "buy_ticker": buy_ticker,
            "keep_ticker": keep_ticker, 
            "CASH": CASH}

        return TR_data

    def save_kis_tr_json(self, TR_data):
        """Kis_TR_data를 JSON 파일로 저장"""
        file_path = "C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/Kis_TR_data.json"
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(TR_data, f, ensure_ascii=False, indent=4)
            print(f"\n Kis_TR_data.json 파일 저장 완료: {file_path}")
            return True
        except Exception as e:
            print(f"\n JSON 파일 저장 오류: {e}")
            return False

# 실행 예제
