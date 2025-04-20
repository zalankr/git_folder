import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt

def calculate_cagr(start_value, end_value, periods):
    return ((end_value / start_value) ** (1 / periods) - 1) * 100

def calculate_mdd(returns):
    cum_returns = (1 + returns).cumprod()
    peak = cum_returns.cummax()
    drawdown = (cum_returns - peak) / peak
    mdd = drawdown.min() * 100
    return mdd

# 데이터 가져오기 (GLD: 금 ETF, ^IRX: 10년물 TIPS 금리 근사)
gold = yf.download('GLD', start='2007-01-01', end='2024-01-01', multi_level_index=False)['Close']
tips = yf.download('^IRX', start='2007-01-01', end='2024-01-01', multi_level_index=False)['Close']

# 데이터 병합 및 정리
data = pd.merge(gold, tips, left_index=True, right_index=True, suffixes=('_gold', '_tips'))
data.dropna(inplace=True)
data['TIPS_rate'] = data['Close_tips'] / 100

# 6개월(126 거래일) 전의 TIPS 금리 추가
data['TIPS_rate_lag6m'] = data['TIPS_rate'].shift(400)

def backtest(data):
    cash = 10000
    gold_held = 0
    portfolio = []

    for i in range(len(data)):
        if data['TIPS_rate_lag6m'].iloc[i] <= 0.01 and gold_held == 0:  # 매수 조건
            gold_held = cash / data['Close_gold'].iloc[i]
            cash = 0

        elif data['TIPS_rate_lag6m'].iloc[i] >= 0.005 and gold_held > 0:  # 매도 조건
            cash = gold_held * data['Close_gold'].iloc[i]
            gold_held = 0

        portfolio_value = cash + gold_held * data['Close_gold'].iloc[i]
        portfolio.append(portfolio_value)

    data['strategy_value'] = portfolio

    # 성과 지표 계산
    total_return = (portfolio[-1] / portfolio[0] - 1) * 100
    cagr = calculate_cagr(portfolio[0], portfolio[-1], (len(data) / 252))
    mdd = calculate_mdd(data['strategy_value'].pct_change().dropna())

    return total_return, cagr, mdd

# 전략 백테스트
strategy_return, strategy_cagr, strategy_mdd = backtest(data)

# Buy and Hold 전략
buy_and_hold_value = 10000 * (data['Close_gold'] / data['Close_gold'].iloc[0])
data['buy_and_hold_value'] = buy_and_hold_value
buy_and_hold_return = (buy_and_hold_value.iloc[-1] / buy_and_hold_value.iloc[0] - 1) * 100
buy_and_hold_cagr = calculate_cagr(buy_and_hold_value.iloc[0], buy_and_hold_value.iloc[-1], (len(data) / 252))
buy_and_hold_mdd = calculate_mdd(data['buy_and_hold_value'].pct_change().dropna())

# 결과 출력
print("[실질금리 기반 전략 (6개월 전 시그널)]")
print(f"최종 수익률: {strategy_return:.2f}%")
print(f"CAGR: {strategy_cagr:.2f}%")
print(f"MDD: {strategy_mdd:.2f}%")

print("\n[Buy and Hold 전략]")
print(f"최종 수익률: {buy_and_hold_return:.2f}%")
print(f"CAGR: {buy_and_hold_cagr:.2f}%")
print(f"MDD: {buy_and_hold_mdd:.2f}%")

# 포트폴리오 가치 및 TIPS 금리 시각화
plt.figure(figsize=(12, 6))
plt.plot(data.index, data['strategy_value'], label='실질금리 전략 (6개월 전 시그널)')
plt.plot(data.index, data['buy_and_hold_value'], label='Buy and Hold')
plt.twinx()
plt.plot(data.index, data['TIPS_rate'], color='purple', linestyle='--', label='TIPS 금리')
plt.legend()
plt.title('금 vs 실질금리 기반 투자 전략 (6개월 전 시그널) 및 TIPS 금리')
plt.ylabel('포트폴리오 가치($)')
plt.grid(True)
plt.show()

