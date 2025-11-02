import yfinance as yf
import pandas as pd
import riskfolio as rp
import kakao_alert as KA
import KIS_US
import json
from datetime import date
import calendar
import warnings
warnings.filterwarnings('ignore')

class USLA_Model(KIS_US.KIS_API): #상속
    def __init__(self, key_file_path, token_file_path, cano, acnt_prdt_cd):
        super().__init__(key_file_path, token_file_path, cano, acnt_prdt_cd)  # 부모 생성자 호출
        self.etf_tickers = ['UPRO', 'TQQQ', 'EDC', 'TMF', 'TMV']
        self.all_tickers = self.etf_tickers + ['CASH']
        self.USLA_data_path = "/var/autobot/TR_KIS/USLA_data.json"
        self.KIS_TR_path = "/var/autobot/TR_KIS/KIS_TR.json"
        self.fee = self.SELL_FEE_RATE  # 매도 수수료 0.09%

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
                KA.SendMessage("USAA 경고: AGG 데이터가 충분하지 않습니다.")
                return 0
                
            current_price = agg_data.iloc[-1]  # 최신 가격
            avg_price = agg_data.mean()  # 4개월 평균
            
            regime = current_price - avg_price
            
            return regime
            
        except Exception as e:
            KA.SendMessage(f"USAA Regime 계산 오류: {e}")
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
                KA.SendMessage("USAA 경고: LA모멘텀 계산을 위한 데이터가 충분하지 않습니다.")
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
                    KA.SendMessage(f"USAA LA {ticker} 모멘텀 계산 오류: {e}")
                    continue
            
            if not momentum_scores:
                return pd.DataFrame()
                
            momentum_df = pd.DataFrame(momentum_scores)
            momentum_df['rank'] = momentum_df['momentum'].rank(ascending=False)
            momentum_df = momentum_df.sort_values('rank').reset_index(drop=True)
            
            return momentum_df
            
        except Exception as e:
            KA.SendMessage(f"USAA LA모멘텀 점수 계산 오류: {e}")
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
        
        # 1. Regime Signal 계산
        regime = self.calculate_regime(target_month, target_year)
        
        # 2. 모멘텀 점수 계산
        momentum_df = self.calculate_momentum(target_month, target_year)
        
        if momentum_df.empty:
            KA.SendMessage("USAA 경고: LA모멘텀 데이터가 비어 계산할 수 없습니다.")
            return None
        
        momentum = momentum_df.head(5)
        lines = ["모멘텀 순위:"]
        for i in range(5):
            ticker = momentum.iloc[i]['ticker']
            score = momentum.iloc[i]['momentum']
            lines.append(f"{i+1}위: {ticker} ({score:.4f})")

        KA.SendMessage("\n".join(lines))
            
        
        # 3. 투자 전략 결정
        if regime < 0: # < 0으로 변경, 테스트 후엔
            KA.SendMessage(f"Regime: {regime:.2f} < 0 → 100% CASH")
            allocation = {ticker: 0.0 for ticker in self.etf_tickers}
            allocation['CASH'] = 1.0

        else:
            KA.SendMessage(f"Regime Signal: {regime:.2f} ≥ 0 → 투자 모드")
            
            # 상위 2개 ETF 선택
            top_2_tickers = momentum_df.head(2)['ticker'].tolist()
            
            # 포트폴리오 가중치 계산
            weights = self.calculate_portfolio_weights(top_2_tickers)
            
            allocation = {ticker: 0.0 for ticker in self.etf_tickers}
            allocation.update(weights)
            allocation['CASH'] = 0.01  # 1% 현금 보유
        
        # 4. 현재 가격 조회
        current_prices = self.get_USLA_current_prices()
        
        # 4. 결과 출력
        for ticker in self.all_tickers:
            if allocation.get(ticker, 0) > 0:
                print(f"{ticker}: {allocation[ticker]:.1%} (현재가: ${current_prices[ticker]:.2f})")
        
        return {
            'regime': regime,
            'momentum': momentum_df,
            'allocation': allocation,
            'current_prices': current_prices
        }
    
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
                value = price * qty * (1 - self.fee)
                hold_USD_value += value

        return hold_USD_value
    
    def target_ticker_weight(self): # make_trading_data함수에 종속되어 target 티커별 목표 비중 산출
        """USLA 모델 실행, target ticker와 weight 구하기"""
        invest = self.run_strategy()
        target = {
            ticker: weight 
            for ticker, weight in invest['allocation'].items() 
            if weight >= 0.01
        }
        regime_signal = invest['regime']
        return target, regime_signal

    def calculate_target_qty(self, target, target_usd_value): # make_trading_data함수에 종속되어 target 티커별 목표 quantity 산출
        # 보유 $기준 잔고를 바탕으로 목표 비중에 맞춰 ticker별 quantity 계산
        target_qty = {}
        target_stock_value = 0
        for ticker in target.keys():
            if ticker != "CASH":
                try:
                    price = self.get_US_current_price(ticker)
                    
                    # 타입 체크 추가
                    if isinstance(price, (int, float)) and price > 0:
                        target_qty[ticker] = int(target_usd_value[ticker] / price)  
                        target_stock_value += target_qty[ticker] * price
                        
                    else:
                        KA.SendMessage(f"{ticker}: 가격 정보 없음 (price={price})")
                        target_qty[ticker] = 0
                        
                except Exception as e:
                    KA.SendMessage(f"{ticker}: 수량 계산 오류 - {e}")
                    target_qty[ticker] = 0

        # 남은 현금 = 전체 USD - 주식 매수 예정 금액
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
            sell_splits = 5
            sell_price_adjust = [1.0025, 1.005, 1.0075, 1.01, 1.0125]
            buy_splits = 5
            buy_price_adjust = [0.9975, 0.995, 0.9925, 0.99, 0.9875]

            if round == 1:
                pass
            elif round == 2:
                sell_price_adjust[0] = 0.99
            elif round == 3:
                sell_splits = 4
                sell_price_adjust = sell_price_adjust[:sell_splits]
                buy_price_adjust[0] = 1.01
            elif round == 4:
                sell_splits = 4
                sell_price_adjust = sell_price_adjust[:sell_splits]
                buy_splits = 4
                buy_price_adjust = buy_price_adjust[:buy_splits]
            elif round == 5:
                sell_splits = 4
                sell_price_adjust = sell_price_adjust[:sell_splits]
                sell_price_adjust[0] = 0.99
                buy_splits = 4
                buy_price_adjust = buy_price_adjust[:buy_splits]
            elif round == 6:
                sell_splits = 3
                sell_price_adjust = sell_price_adjust[:sell_splits]
                buy_splits = 4
                buy_price_adjust = buy_price_adjust[:buy_splits]
                buy_price_adjust[0] = 1.01
            elif round == 7:
                sell_splits = 3
                sell_price_adjust = sell_price_adjust[:sell_splits]
                buy_splits = 3
                buy_price_adjust = buy_price_adjust[:buy_splits]
            elif round == 8:
                sell_splits = 3
                sell_price_adjust = sell_price_adjust[:sell_splits]
                sell_price_adjust[0] = 0.99
                buy_splits = 3
                buy_price_adjust = buy_price_adjust[:buy_splits]
            elif round == 9:
                sell_splits = 2
                sell_price_adjust = sell_price_adjust[:sell_splits]
                buy_splits = 3
                buy_price_adjust = buy_price_adjust[:buy_splits]
                buy_price_adjust[0] = 1.01
            elif round == 10:
                sell_splits = 2
                sell_price_adjust = sell_price_adjust[:sell_splits]
                buy_splits = 2
                buy_price_adjust = buy_price_adjust[:buy_splits]
            elif round == 11:
                sell_splits = 2
                sell_price_adjust = sell_price_adjust[:sell_splits]
                sell_price_adjust[0] = 0.99
                buy_splits = 2
                buy_price_adjust = buy_price_adjust[:buy_splits]
            elif round == 12:
                sell_splits = 1
                sell_price_adjust = sell_price_adjust[:sell_splits]
                sell_price_adjust[0] = 0.97
                buy_splits = 2
                buy_price_adjust = buy_price_adjust[:buy_splits]
                buy_price_adjust[0] = 1.01
            elif round == 13:
                sell_splits = 1
                sell_price_adjust[0] = 0.97
                buy_splits = 1
                buy_price_adjust = buy_price_adjust[:buy_splits]
                buy_price_adjust = [1.03]
            
        round_split = {
            "order_type": order_type,
            "sell_splits": sell_splits, 
            "sell_price_adjust": sell_price_adjust, 
            "buy_splits": buy_splits, 
            "buy_price_adjust": buy_price_adjust
        }

        return round_split

    def load_USLA_data(self): # make_trading_data함수에 종속되어 USLA data 불러오기
        """USLA data 불러오기"""   
        try:
            with open(self.USLA_data_path, 'r', encoding='utf-8') as f:
                USLA_data = json.load(f)
            return USLA_data

        except Exception as e:
            KA.SendMessage(f"JSON 파일 오류: {e}")
            exit()

    def load_KIS_TR(self): # Kis_TR data 불러오기
        """KIS_TR 불러오기"""   
        try:
            with open(self.KIS_TR_path, 'r', encoding='utf-8') as f:
                TR_data = json.load(f)
            return TR_data

        except Exception as e:
            print(f"JSON 파일 오류: {e}")
            exit()

    def save_USLA_data_json(self, USLA_data):
        """Kis_TR_data를 JSON 파일로 저장"""     
        try:
            with open(self.USLA_data_path, 'w', encoding='utf-8') as f:
                json.dump(USLA_data, f, ensure_ascii=False, indent=4)
            print(f"\n USLA_data.json 파일 저장 완료")
            return True
        except Exception as e:
            print(f"\n JSON 파일 저장 오류: {e}")
            return False

    def save_KIS_TR_json(self, TR_data):
        """Kis_TR_data를 JSON 파일로 저장"""     
        try:
            with open(self.KIS_TR_path, 'w', encoding='utf-8') as f:
                json.dump(TR_data, f, ensure_ascii=False, indent=4)
            print(f"\n Kis_TR.json 파일 저장 완료")
            return True
        except Exception as e:
            print(f"\n JSON 파일 저장 오류: {e}")
            return False
        
    def calculate_sell_summary(self, Sell_order):
        """매도 체결 내역 조회 및 집계 (종목별 집계 포함)"""
        
        Sell_result = []
        
        for order in Sell_order:
            execution = self.check_order_execution(
                order_number=order['order_number'],
                ticker=order['ticker'],
                order_type="01"
            )
            Sell_result.append(execution)
        
        # 체결된 주문만 필터링
        filled = [r for r in Sell_result if r and r.get('success')]
        
        if not filled:
            return {
                'success': False,
                'count': 0,
                'total_quantity': 0,
                'total_amount': 0.0,
                'total_fee': 0.0,  # 추가
                'net_amount': 0.0,  # 추가 (실제 입금액)
                'avg_price': 0.0,
                'by_ticker': {},
                'details': []
            }
        
        # 전체 집계
        total_quantity = sum(int(r.get('qty', 0)) for r in filled)
        total_amount = sum(float(r.get('amount', 0)) for r in filled)
        
        # 수수료 계산
        total_fee = total_amount * self.SELL_FEE_RATE
        
        # 실제 입금액 (체결금액 - 수수료)
        net_amount = total_amount - total_fee
        
        avg_price = total_amount / total_quantity if total_quantity > 0 else 0
        
        # 종목별 집계
        from collections import defaultdict
        ticker_summary = defaultdict(lambda: {'qty': 0, 'amount': 0, 'orders': []})
        
        for r in filled:
            ticker = r.get('name', '알 수 없음')
            qty = int(r.get('qty', 0))
            amount = float(r.get('amount', 0))
            price = float(r.get('price', 0))
            
            ticker_summary[ticker]['qty'] += qty
            ticker_summary[ticker]['amount'] += amount
            ticker_summary[ticker]['orders'].append({
                'qty': qty,
                'price': price,
                'amount': amount
            })
        
        # 종목별 평균가 계산
        by_ticker = {}
        for ticker, data in ticker_summary.items():
            qty = data['qty']
            amount = data['amount']
            avg = amount / qty if qty > 0 else 0
            
            # 종목별 수수료 및 실제 입금액 계산
            fee = amount * self.SELL_FEE_RATE
            net = amount - fee
            
            by_ticker[ticker] = {
                'quantity': qty,
                'amount': amount,  # 체결금액
                'fee': fee,  # 수수료
                'net_amount': net,  # 실제 입금액
                'avg_price': avg,
                'order_count': len(data['orders']),
                'orders': data['orders']
            }
        
        return {
            'success': True,
            'count': len(filled),
            'total_quantity': total_quantity,
            'total_amount': total_amount,  # 체결금액
            'total_fee': total_fee,  # 전체 수수료
            'net_amount': net_amount,  # 실제 입금액 ← 이것이 예수금!
            'avg_price': avg_price,
            'by_ticker': by_ticker,
            'details': filled
        }

    def calculate_buy_summary(self, Buy_order):
        """매수 체결 내역 조회 및 집계 (종목별 집계 포함)"""
        
        Buy_result = []
        
        for order in Buy_order:
            execution = self.check_order_execution(
                order_number=order['order_number'],
                ticker=order['ticker'],
                order_type="02"  # 매수는 "02"
            )
            Buy_result.append(execution)
        
        # 체결된 주문만 필터링
        filled = [r for r in Buy_result if r and r.get('success')]
        
        if not filled:
            return {
                'success': False,
                'count': 0,
                'total_quantity': 0,
                'total_amount': 0.0,
                'avg_price': 0.0,
                'by_ticker': {},
                'details': []
            }
        
        # 전체 집계
        total_quantity = sum(int(r.get('qty', 0)) for r in filled)
        total_amount = sum(float(r.get('amount', 0)) for r in filled)
        
        # 실제 사용 금액 (체결금액 + 수수료)
        avg_price = total_amount / total_quantity if total_quantity > 0 else 0
        
        # 종목별 집계
        from collections import defaultdict
        ticker_summary = defaultdict(lambda: {'qty': 0, 'amount': 0, 'orders': []})
        
        for r in filled:
            ticker = r.get('name', '알 수 없음')
            qty = int(r.get('qty', 0))
            amount = float(r.get('amount', 0))
            price = float(r.get('price', 0))
            
            ticker_summary[ticker]['qty'] += qty
            ticker_summary[ticker]['amount'] += amount
            ticker_summary[ticker]['orders'].append({
                'qty': qty,
                'price': price,
                'amount': amount
            })
        
        # 종목별 평균가 계산
        by_ticker = {}
        for ticker, data in ticker_summary.items():
            qty = data['qty']
            amount = data['amount']
            avg = amount / qty if qty > 0 else 0
            
            by_ticker[ticker] = {
                'quantity': qty,
                'amount': amount,  # 체결금액
                'avg_price': avg,
                'order_count': len(data['orders']),
                'orders': data['orders']
            }
        
        return {
            'success': True,
            'count': len(filled),
            'total_quantity': total_quantity,
            'total_amount': total_amount,
            'avg_price': avg_price,
            'by_ticker': by_ticker,
            'details': filled
        }
