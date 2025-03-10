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

# 결과 저장을 위한 데이터프레임
results = []

# 이동평균선 조합별 백테스트 실행
for short_window in range(5, 21):
    for long_window in range(5, 240, 5):
        if short_window >= long_window:
            continue
        
        df["SMA_short"] = df["close"].rolling(window=short_window).mean()
        df["SMA_long"] = df["close"].rolling(window=long_window).mean()
        df.dropna(inplace=True)
        
        if len(df) < 2:
            continue
        
        cash = initial_cash
        holdings = 0
        portfolio = initial_cash
        history = []
        
        for today in range(1, len(df)):
            today_price = df.iloc[today]["close"]
            prev_sma_short = df.iloc[today - 1]["SMA_short"]
            prev_sma_long = df.iloc[today - 1]["SMA_long"]
            today_sma_short = df.iloc[today]["SMA_short"]
            today_sma_long = df.iloc[today]["SMA_long"]
            
            if holdings == 0 and prev_sma_short <= prev_sma_long and today_sma_short > today_sma_long:
                buy_price = today_price * (1 + fee + slippage)
                holdings = cash / buy_price
                cash = 0
            elif holdings > 0 and prev_sma_short >= prev_sma_long and today_sma_short < today_sma_long:
                sell_price = today_price * (1 - fee - slippage)
                cash = holdings * sell_price
                holdings = 0
            
            portfolio = cash + (holdings * today_price)
            history.append(portfolio)

        # 마지막 날에 매도하여 현금화
        if holdings > 0:
            final_sell_price = df.iloc[-1]["close"] * (1 - fee - slippage)
            cash = holdings * final_sell_price
            holdings = 0
            portfolio = cash  # 최종 자산을 현금화한 값으로 설정
            history.append(portfolio)
            
        
        final_value = portfolio
        returns = (final_value / initial_cash) - 1
        years = len(df) / 252 if len(df) > 0 else 1
        CAGR = (final_value / initial_cash) ** (1 / years) - 1 if years > 0 else 0
        cum_max = pd.Series(history).cummax()
        MDD = ((cum_max - history) / cum_max).max() if len(cum_max) > 0 else 0
        
        results.append([short_window, long_window, final_value, returns, CAGR, MDD])

# 결과 데이터프레임 변환
result_df = pd.DataFrame(results, columns=["Short MA", "Long MA", "Final Asset", "Return", "CAGR", "MDD"])
result_df = result_df.sort_values(by="CAGR", ascending=False)

# 데이터 유효성 검사
# if not df.empty:
#     # Buy & Hold 전략
#     try:
#         bh_final_value = (initial_cash / df.iloc[0]["close"]) * df.iloc[-1]["close"]
#         bh_returns = (bh_final_value / initial_cash) - 1
#         bh_years = len(df) / 252 if len(df) > 0 else 1
#         bh_CAGR = (bh_final_value / initial_cash) ** (1 / bh_years) - 1 if bh_years > 0 else 0
#         bh_MDD = ((df["close"].cummax() - df["close"]) / df["close"].cummax()).max()
#     except IndexError:
#         bh_final_value, bh_returns, bh_CAGR, bh_MDD = initial_cash, 0, 0, 0
# else:
#     bh_final_value, bh_returns, bh_CAGR, bh_MDD = initial_cash, 0, 0, 0

# 결과 출력
print("[수익률 상위 3개 전략]")
print(result_df.head(3))
# print("\n[Buy & Hold 전략]")
# print(f"최종 자산: {bh_final_value:,.0f} 원")
# print(f"수익률: {bh_returns * 100:.2f}%")
# print(f"CAGR: {bh_CAGR * 100:.2f}%")
# print(f"MDD: {bh_MDD * 100:.2f}%")

# 수익률 1위 전략
if not result_df.empty:
    best_strategy = result_df.iloc[0]
    print("\n[수익률 1위 전략]")
    print(f"단기 이동평균선: {best_strategy['Short MA']}일, 장기 이동평균선: {best_strategy['Long MA']}일")
    print(f"최종 자산: {best_strategy['Final Asset']:,.0f} 원")
    print(f"수익률: {best_strategy['Return'] * 100:.2f}%")
    print(f"CAGR: {best_strategy['CAGR'] * 100:.2f}%")
    print(f"MDD: {best_strategy['MDD'] * 100:.2f}%")


