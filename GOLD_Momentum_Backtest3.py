import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# 데이터 로드 (예: CSV 파일)
file_path = "C:/Users/ilpus/Desktop/INVEST/R&D/KRX_gold/gold_1.xlsx"
df = pd.read_excel(file_path)

df.set_index(keys='date', inplace = True)

initial_cash = 10000000  # 초기 자본 (1천만 원)
fee = 0.0033  # 거래수수료 0.33%
slippage = 0.0002  # 슬리피지 0.02%

# 5일 및 140일 이동평균선 계산
df["SMA"] = df["close"].rolling(window=40).mean()
df["LMA"] = df["close"].rolling(window=160).mean()
df.dropna(inplace=True)

# 백테스트 초기 설정
cash = initial_cash
holdings = 0
portfolio = initial_cash
history = []

for today in range(1, len(df)):
    today_price = df.iloc[today]["close"]
    prev_sma5 = df.iloc[today - 1]["SMA"]
    prev_sma20 = df.iloc[today - 1]["LMA"]
    today_sma5 = df.iloc[today]["SMA"]
    today_sma20 = df.iloc[today]["LMA"]
    
    if holdings == 0 and prev_sma5 <= prev_sma20 and today_sma5 > today_sma20:  # 골드크로스 (매수)
        buy_price = today_price * (1 + fee + slippage)
        holdings = cash / buy_price
        cash = 0
    
    elif holdings > 0 and prev_sma5 >= prev_sma20 and today_sma5 < today_sma20:  # 데드크로스 (매도)
        sell_price = today_price * (1 - fee - slippage)
        cash = holdings * sell_price
        holdings = 0
    
    portfolio = cash + (holdings * today_price)
    history.append([df.index[today], portfolio])

# 결과 데이터프레임 변환
history_df = pd.DataFrame(history, columns=["date", "portfolio"])
history_df.set_index("date", inplace=True)

# 최종 성과 계산
final_value = portfolio
returns = (final_value / initial_cash) - 1
CAGR = (final_value / initial_cash) ** (1 / (len(df) / 252)) - 1  # 연환산 수익률

# 최대 낙폭 (MDD) 계산
cum_max = history_df["portfolio"].cummax()
MDD = ((cum_max - history_df["portfolio"]) / cum_max).max()

# 연도별 수익률 계산
# yearly_returns = history_df.resample("Y").last().pct_change().dropna()

# Buy & Hold 전략 비교
bh_final_value = (initial_cash / df.iloc[0]["close"]) * df.iloc[-1]["close"]
bh_returns = (bh_final_value / initial_cash) - 1
bh_CAGR = (bh_final_value / initial_cash) ** (1 / (len(df) / 252)) - 1
bh_MDD = ((df["close"].cummax() - df["close"]) / df["close"].cummax()).max()
bh_yearly_returns = df["close"].resample("Y").last().pct_change().dropna()

# 결과 출력
print(f"최종 자산: {final_value:,.0f} 원")
print(f"수익률: {returns * 100:.2f}%")
print(f"CAGR: {CAGR * 100:.2f}%")
print(f"MDD: {MDD * 100:.2f}%")
# print("연도별 수익률:")
# print(yearly_returns * 100)

print("\n[Buy & Hold 전략]")
print(f"최종 자산: {bh_final_value:,.0f} 원")
print(f"수익률: {bh_returns * 100:.2f}%")
print(f"CAGR: {bh_CAGR * 100:.2f}%")
print(f"MDD: {bh_MDD * 100:.2f}%")
# print("연도별 수익률:")
# print(bh_yearly_returns * 100)

# 그래프 시각화
plt.figure(figsize=(12, 6))
plt.plot(history_df.index, history_df["portfolio"], label="Backtest Strategy")
plt.plot(df.index, (initial_cash / df.iloc[0]["close"]) * df["close"], label="Buy & Hold", linestyle="dashed")
plt.legend()
plt.title("Backtest vs Buy & Hold")
plt.show()