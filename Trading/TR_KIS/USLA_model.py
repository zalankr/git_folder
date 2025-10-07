import yfinance as yf
import pandas as pd
import numpy as np
import riskfolio as rp
import KIS_US
import json
from datetime import datetime, date
import calendar
import warnings
warnings.filterwarnings('ignore')


class USLA_Model(KIS_US.KIS_API): #상속
    def __init__(self, key_file_path, token_file_path, cano, acnt_prdt_cd):
        super().__init__(key_file_path, token_file_path, cano, acnt_prdt_cd)  # 부모 생성자 호출
        self.etf_tickers = ['UPRO', 'TQQQ', 'EDC', 'TMF', 'TMV']
        self.all_tickers = self.etf_tickers + ['USLA_CASH']
        self.tax_rate = 0.0009
        self.USLA_data_path = "C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/USLA_data.json"  

    def get_month_end_date(self, year, month):
        """월말일 반환"""
        last_day = calendar.monthrange(year, month)[1]
        return f'{year}-{month:02d}-{last_day}'
    
    def calculate_regime(self, target_month, target_year):
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
    
    def calculate_momentum(self, target_month, target_year):
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
    
    def calculate_portfolio_weights(self, top_tickers):
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
    
    def get_USLA_current_prices(self):
        """현재 가격 조회"""
        try:
            prices = {}
            for ticker in self.etf_tickers:
                data = yf.download(ticker, period='1d', interval='1d', progress=False, multi_level_index=False)['Close']
                prices[ticker] = float(data.iloc[-1])
            prices['USLA_CASH'] = 1.0
            return prices
        except Exception as e:
            print(f"가격 조회 오류: {e}")
            return {ticker: 100.0 for ticker in self.all_tickers}  # 기본값
    
    def run_strategy(self, target_month=None, target_year=None):
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
            print("투자 결정: 99% BIL, 1% USLA_CASH")
            allocation = {ticker: 0.0 for ticker in self.etf_tickers}
            allocation['USLA_CASH'] = 0.01
            allocation['BIL'] = 0.99

        else:
            print(f"\nRegime Signal: {regime:.2f} ≥ 0 → 투자 모드")
            
            # 상위 2개 ETF 선택
            top_2_tickers = momentum_df.head(2)['ticker'].tolist()
            
            # 포트폴리오 가중치 계산
            weights = self.calculate_portfolio_weights(top_2_tickers)
            
            allocation = {ticker: 0.0 for ticker in self.etf_tickers}
            allocation.update(weights)
            allocation['USLA_CASH'] = 0.01  # 1% 현금 보유
        
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
    
    def get_USLA_data(self):
        """USLA data 불러오기"""   
        try:
            with open(self.USLA_data_path, 'r', encoding='utf-8') as f:
                USLA_data = json.load(f)
            return USLA_data

        except Exception as e:
            print(f"JSON 파일 오류: {e}")
            exit()

    def calculate_USD_value(self, holding):
        """USD 환산 잔고 계산"""
        holding_USD_value = 0
        for t in holding.keys():
            if t == "USLA_CASH":
                # USLA_CASH도 float로 변환
                holding_USD_value += float(holding["USLA_CASH"])
            else:
                price = self.get_US_current_price(ticker=t)
                # holding[t]를 float로 변환
                quantity = float(holding[t])
                value = price * quantity * (1 - self.tax_rate)
                holding_USD_value += value

        return holding_USD_value
    
    def calculate_target_ticker_weight(self):
        """USLA 모델 실행, target ticker와 weight 구하기"""
        invest = self.run_strategy()
        target = {
            ticker: weight 
            for ticker, weight in invest['allocation'].items() 
            if weight > 0
        }

        return target    

    def calculate_target_quantity(self, USLA_data):
        """target비중에 맞춰 보유 $환산금액을 곱해서 현재가로 나누기 > ticker별 수량 반환+USD금액 반환"""
        target = self.calculate_target_ticker_weight()
        # USLA_data에서 holding을 추출할 때 float로 변환
        holding = {ticker: float(qty) for ticker, qty in zip(USLA_data['ticker'], USLA_data['quantity'])}
        holding_USD_value = self.calculate_USD_value(holding)

        # 보유 $기준 잔고를 바탕으로 목표 비중에 맞춰 ticker별 quantity 계산
        target_usd_value = {ticker: target[ticker] * holding_USD_value for ticker in target.keys()}

        target_quantity = {}
        target_stock_value = 0
        for ticker in target.keys():
            if ticker != "USLA_CASH":
                try:
                    price = self.get_US_current_price(ticker)
                    if price and price > 0:
                        target_quantity[ticker] = int(target_usd_value[ticker] / price)
                        target_stock_value += target_quantity[ticker] * price * (1 + self.tax_rate)
                    else:
                        print(f"{ticker}: 가격 정보 없음")
                        target_quantity[ticker] = 0
                except Exception as e:
                    print(f"{ticker}: 수량 계산 오류 - {e}")
                    target_quantity[ticker] = 0

        target_quantity["USLA_CASH"] = sum(target_usd_value.values()) - target_stock_value

        return target_quantity, target_stock_value

    def trading_ticker(self, holding, USLA_data):
        """trading 할 ticker별 매수매도량 구하기"""
        holding_ticker = list(holding.keys())
        # USLA_data가 아닌 holding을 전달
        holding_USD_value = self.calculate_USD_value(holding)
        target = self.calculate_target_ticker_weight()
        target_ticker = list(target.keys())
        target_usd_value = {ticker: target[ticker] * holding_USD_value for ticker in target.keys()}
        # calculate_target_quantity에 USLA_data 전달
        target_quantity, target_stock_value = self.calculate_target_quantity(USLA_data)
        
        sell_ticker = {}
        buy_ticker = {}
        keep_ticker = {}

        for hold in holding_ticker:
            if hold not in target_ticker:
                sell_ticker[hold] = holding[hold]
            else:
                edited_quantity = target_quantity[hold] - holding[hold]
                if edited_quantity > 0:
                    buy_ticker[hold] = edited_quantity
                elif edited_quantity < 0:
                    sell_ticker[hold] = abs(edited_quantity)  # 음수를 양수로
                elif edited_quantity == 0:
                    keep_ticker[hold] = holding[hold]

        for target in target_ticker:
            if target not in holding_ticker:
                buy_ticker[target] = target_quantity[target]

        return sell_ticker, buy_ticker, keep_ticker
    
    def create_kis_tr_data(self, holding, USLA_data, sell_ticker, buy_ticker):
        """
        거래 데이터를 JSON 형식으로 생성
        
        Parameters:
        holding: 현재 보유 수량
        USLA_data: USLA JSON 데이터
        sell_ticker: 매도할 티커와 수량
        buy_ticker: 매수할 티커와 수량
        """
        kis_tr_data = []
        # self를 제거
        target_quantity, target_stock_value = self.calculate_target_quantity(USLA_data)
        
        # 모든 관련 티커 수집 (CASH 제외)
        all_tickers = set(holding.keys()) | set(target_quantity.keys())
        all_tickers.discard("USLA_CASH")
        
        for ticker in sorted(all_tickers):
            # 포지션 결정
            if ticker in buy_ticker:
                position = "Buy"
            elif ticker in sell_ticker:
                position = "Sell"
            else:
                position = "Hold"
            
            # 수량 정보
            hold_amount = holding.get(ticker, 0)
            target_amount = target_quantity.get(ticker, 0)
            tr_quantity = target_amount - hold_amount
            
            ticker_data = {
                "ticker": ticker,
                "position": position,
                "target_amount": target_amount,
                "hold_amount": hold_amount,
                "TR_quantity": tr_quantity,
                "order_quantity": 0,
                "filled_quantity": 0,
                "unfilled_quantity": 0,
                "pending_order": 0
            }
            
            kis_tr_data.append(ticker_data)
        
        # CASH 정보 추가
        USLA_cash_data = {
            "ticker": "USLA_CASH",
            "position": "USLA_Cash",
            "target_amount": round(target_quantity.get("USLA_CASH", 0), 2),
            "hold_amount": round(holding.get("USLA_CASH", 0), 2),
            "TR_quantity": "",
            "order_quantity": "",
            "filled_quantity": "",
            "unfilled_quantity": "",
            "pending_order": ""
        }
        kis_tr_data.append(USLA_cash_data)
        
        return kis_tr_data

    def save_kis_tr_json(self, kis_tr_data):
        """Kis_TR_data를 JSON 파일로 저장"""
        file_path = "C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/Kis_TR_data.json"
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(kis_tr_data, f, ensure_ascii=False, indent=4)
            print(f"\n Kis_TR_data.json 파일 저장 완료: {file_path}")
            return True
        except Exception as e:
            print(f"\n JSON 파일 저장 오류: {e}")
            return False

    def print_tr_table(self, kis_tr_data):
        """거래 데이터를 표 형식으로 출력"""
        print("\n" + "="*120)
        print("Kis Trading Data Table")
        print("="*120)
        
        # 헤더
        header = f"{'ticker':<8} {'position':<10} {'target':<8} {'hold':<8} {'TR qty':<8} {'order':<8} {'filled':<8} {'unfilled':<8} {'pending':<8}"
        print(header)
        print("-"*120)
        
        # 데이터
        for data in kis_tr_data:
            row = (f"{data['ticker']:<8} "
                f"{data['position']:<10} "
                f"{str(data['target_amount']):<8} "
                f"{str(data['hold_amount']):<8} "
                f"{str(data['TR_quantity']):<8} "
                f"{str(data['order_quantity']):<8} "
                f"{str(data['filled_quantity']):<8} "
                f"{str(data['unfilled_quantity']):<8} "
                f"{str(data['pending_order']):<8}")
            print(row)
        
        print("="*120)

# 실행 예제
if __name__ == "__main__":
    # 또는 특정 월 지정 실행
    # result = strategy.run_strategy(target_month=1, target_year=2025)
    # print(result)

    key_file_path = "C:/Users/ilpus/Desktop/NKL_invest/kis63721147nkr.txt"
    token_file_path = "C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/kis63721147_token.json"
    cano = "63721147"  # 종합계좌번호 (8자리)
    acnt_prdt_cd = "01"  # 계좌상품코드 (2자리)

    USLA = USLA_Model(key_file_path, token_file_path, cano, acnt_prdt_cd)

    # 서머타임(DST) 확인
    is_dst = USLA.is_us_dst()
    print("="*60)
    print(is_dst)
    print(f"현재 UTC 시간: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"서머타임(DST): {True if is_dst else False}")

    # 최초 1회만 target비중 계산, Json데이터에서 holding ticker와 quantity 구하기
    USLA_data = USLA.get_USLA_data()
    # float로 변환하여 holding 생성
    holding = {ticker: float(qty) for ticker, qty in zip(USLA_data['ticker'], USLA_data['quantity'])}

    # target비중에 맞춰 USD환산금액을 곱하고 현재가로 나누기 > ticker별 수량 반환+USD금액 반환
    target_quantity, target_stock_value = USLA.calculate_target_quantity(USLA_data)
    sell_ticker, buy_ticker, keep_ticker = USLA.trading_ticker(holding, USLA_data)

    print("\n[매도 종목]")
    print(sell_ticker)
    print("\n[매수 종목]")
    print(buy_ticker)
    print("\n[유지 종목]")
    print(keep_ticker)

    # Kis_TR_data 생성
    print("\n" + "="*60)
    print("거래 데이터 생성 중...")
    print("="*60)

    # USLA_data 전달 (holding이 아님)
    kis_tr_data = USLA.create_kis_tr_data(holding, USLA_data, sell_ticker, buy_ticker)

    # 표 형식으로 출력
    USLA.print_tr_table(kis_tr_data)

    # JSON 파일로 저장
    USLA.save_kis_tr_json(kis_tr_data)
