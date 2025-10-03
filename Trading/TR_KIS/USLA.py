import yfinance as yf
import pandas as pd
import numpy as np
import riskfolio as rp
from datetime import datetime, date
import calendar
import warnings
warnings.filterwarnings('ignore')

class USLAS:
    def __init__(self):
        self.etf_tickers = ['UPRO', 'TQQQ', 'EDC', 'TMF', 'TMV']
        self.all_tickers = self.etf_tickers + ['CASH']
        self.tax_rate = 0.0009
        
    def get_month_end_date(self, year, month):
        """월말일 반환"""
        last_day = calendar.monthrange(year, month)[1]
        return f'{year}-{month:02d}-{last_day}'
    
    def calculate_regime_signal(self, target_month, target_year):
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
            
            regime_signal = current_price - avg_price
            
            return regime_signal
            
        except Exception as e:
            print(f"Regime Signal 계산 오류: {e}")
            return 0
    
    def calculate_momentum_scores(self, target_month, target_year):
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
    
    def get_current_prices(self):
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
    
    def run_strategy(self, target_month=None, target_year=None):
        """전략 실행"""
        if target_month is None or target_year is None:
            today = date.today()
            target_month = today.month
            target_year = today.year
            
        print(f"\n=== {target_year}년 {target_month}월 USLA 모멘텀 시그널 ===")
        
        # 1. Regime Signal 계산
        regime_signal = self.calculate_regime_signal(target_month, target_year)
        
        # 2. 모멘텀 점수 계산
        momentum_df = self.calculate_momentum_scores(target_month, target_year)
        
        if momentum_df.empty:
            print("모멘텀 데이터를 계산할 수 없습니다.")
            return None
            
        print("\n모멘텀 순위:")
        print(momentum_df[['ticker', 'momentum', 'rank']].round(4))
        
        # 3. 투자 전략 결정
        if regime_signal < 0:
            print(f"\nRegime Signal: {regime_signal:.2f} < 0 → RISK 모드")
            print("투자 결정: 100% CASH")
            allocation = {ticker: 0.0 for ticker in self.etf_tickers}
            allocation['CASH'] = 1.0
        else:
            print(f"\nRegime Signal: {regime_signal:.2f} ≥ 0 → 투자 모드")
            
            # 상위 2개 ETF 선택
            top_2_tickers = momentum_df.head(2)['ticker'].tolist()
            
            # 포트폴리오 가중치 계산
            weights = self.calculate_portfolio_weights(top_2_tickers)
            
            allocation = {ticker: 0.0 for ticker in self.etf_tickers}
            allocation.update(weights)
            allocation['CASH'] = 0.01  # 1% 현금 보유
        
        # 4. 현재 가격 조회
        current_prices = self.get_current_prices()
        
        # 5. 결과 출력
        print("\n최종 배분:")
        for ticker in self.all_tickers:
            if allocation.get(ticker, 0) > 0:
                print(f"{ticker}: {allocation[ticker]:.1%} (현재가: ${current_prices[ticker]:.2f})")
        
        return {
            'regime_signal': regime_signal,
            'momentum_scores': momentum_df,
            'allocation': allocation,
            'current_prices': current_prices
        }

# 실행 예제
if __name__ == "__main__":
    strategy = USLAS()
    
    # 현재 월 기준 실행
    result = strategy.run_strategy()
    
    # 또는 특정 월 지정 실행
    # result = strategy.run_strategy(target_month=1, target_year=2025)
    # print(result)