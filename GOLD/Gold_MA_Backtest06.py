import yfinance as yf
import pandas as pd
import numpy as np

# GLD ETF 데이터 불러오기
gld = yf.Ticker("GLD")
data = gld.history(period="max")
data['Return'] = data['Close'].pct_change()

# 백테스트 설정
start_cash = 10000
commission = 0.0033
slippage = 0.0002

# 성과 저장 변수
cash = start_cash
position = 0
Nday = 200

def calculate_mdd(series):
    peak = series.cummax()
    drawdown = (series / peak) - 1
    return drawdown.min()

# N일 전 종가 열 추가
data['Close_lag'] = data['Close'].shift(Nday)

# 백테스트 실행
portfolio_value = []
for i in range(Nday, len(data)):
    price = data['Close'].iloc[i]
    price_lag = data['Close_lag'].iloc[i]

    # 매수 조건: 당일 종가가 N일 전 종가보다 위
    if position == 0 and price > price_lag:
        position = (cash * (1 - commission - slippage)) / price
        cash = 0

    # 매도 조건: 당일 종가가 N일 전 종가보다 아래
    elif position > 0 and price <= price_lag:
        cash = position * price * (1 - commission - slippage)
        position = 0

    # 현재 포트폴리오 가치 저장
    portfolio_value.append(cash + position * price)

# 최종 자산 평가
final_value = cash + (position * data['Close'].iloc[-1])

# 성과 지표 계산
total_return = (final_value - start_cash) / start_cash
years = (data.index[-1] - data.index[Nday]).days / 365.25
cagr = (final_value / start_cash) ** (1 / years) - 1
mdd = calculate_mdd(pd.Series(portfolio_value))
sharpe = data['Return'].mean() / data['Return'].std() * np.sqrt(252)

# Buy and Hold 성과 계산
buy_hold_return = (data['Close'].iloc[-1] - data['Close'].iloc[0]) / data['Close'].iloc[0]
years = (data.index[-1] - data.index[0]).days / 365.25
buy_hold_cagr = (data['Close'].iloc[-1] / data['Close'].iloc[0]) ** (1 / years) - 1
buy_hold_mdd = calculate_mdd(data['Close'])
buy_hold_sharpe = data['Return'].mean() / data['Return'].std() * np.sqrt(252)

# 결과 DataFrame 생성 및 출력
result_df = pd.DataFrame([
    ["N-Day Lag Crossover", total_return, cagr, mdd, sharpe],
    ["Buy and Hold", buy_hold_return, buy_hold_cagr, buy_hold_mdd, buy_hold_sharpe]
], columns=["Strategy", "Total_Return", "CAGR", "MDD", "Sharpe_Ratio"])

print(result_df)
