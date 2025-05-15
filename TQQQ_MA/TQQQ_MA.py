import yfinance as yf
import pandas as pd
import numpy as np

# 1. 데이터 다운로드
df = yf.download('TQQQ', auto_adjust=True, progress=False, multi_level_index=False)
df = df[['Close']].copy()
df['Date'] = pd.to_datetime(df.index)

# 2. 50일 이동평균 계산
df['50MA'] = df['Close'].rolling(window=50).mean()
df.dropna(inplace=True)
df.reset_index(drop=True, inplace=True)

# 3. 매수/매도 시그널 계산
close = df['Close']
ma50 = df['50MA']

close_aligned, ma50_aligned = close.align(ma50, join='inner', axis=0)

close_shifted = close_aligned.shift(1)
ma50_shifted = ma50_aligned.shift(1)

# shift 후 align 필수
close_shifted, ma50_shifted = close_shifted.align(ma50_shifted, join='inner', axis=0)

buy_signal = (close_aligned > ma50_aligned) & (close_shifted <= ma50_shifted)
sell_signal = (close_aligned < ma50_aligned) & (close_shifted >= ma50_shifted)

df['Position'] = 0
df.loc[buy_signal.index[buy_signal], 'Position'] = 1
df.loc[sell_signal.index[sell_signal], 'Position'] = -1

# 4. 포지션 누적 유지
df['Position'] = df['Position'].replace(to_replace=0, method='ffill').fillna(0)

# 5. 일별 수익률 계산
df['Return'] = df['Close'].pct_change().fillna(0)

# 6. 거래 발생일 계산 (포지션 변동 시)
df['Trade'] = df['Position'].diff().fillna(0).abs()

# 7. 거래 수수료 적용 (매수/매도 각각 0.1%)
fee = 0.001

# 거래 발생일에 수수료 차감: 수익률에서 직접 차감 (복리 계산에 적합)
df['Strategy_Return'] = df['Return'] * df['Position'].shift(1)  # 전일 포지션 기준 수익률
df.loc[df['Trade'] != 0, 'Strategy_Return'] -= fee

# 8. 누적 수익률 계산
df['Cumulative_Strategy'] = (1 + df['Strategy_Return']).cumprod()
df['Cumulative_BuyHold'] = (1 + df['Return']).cumprod()

# 9. 연 단위 양도소득세 계산 (연간 실현이익 기준)
df['Year'] = df['Date'].dt.year
tax_rate = 0.22

# 연도별 누적 수익률 구하기
year_ends = df.groupby('Year').apply(lambda x: x.index[-1])

tax_adjusted_cumprod = df['Cumulative_Strategy'].copy()

prev_cum = 1.0
for idx in year_ends:
    year_return = tax_adjusted_cumprod.loc[idx] / prev_cum - 1
    if year_return > 0:
        tax = year_return * tax_rate
        tax_adjusted_cumprod.loc[idx:] *= (1 - tax)
    prev_cum = tax_adjusted_cumprod.loc[idx]

df['Tax_Adjusted'] = tax_adjusted_cumprod

# 10. 성과지표 계산
days = (df['Date'].iloc[-1] - df['Date'].iloc[0]).days
CAGR = df['Tax_Adjusted'].iloc[-1] ** (365 / days) - 1

rolling_max = df['Tax_Adjusted'].cummax()
drawdown = df['Tax_Adjusted'] / rolling_max - 1
MDD = drawdown.min()

sharpe = df['Strategy_Return'].mean() / df['Strategy_Return'].std() * np.sqrt(252)

downside_std = df.loc[df['Strategy_Return'] < 0, 'Strategy_Return'].std()
sortino = df['Strategy_Return'].mean() / downside_std * np.sqrt(252)

trades = int(df['Trade'].sum())

# 11. 결과 출력
print(f"CAGR (Tax Adjusted): {CAGR:.2%}")
print(f"MDD: {MDD:.2%}")
print(f"Sharpe Ratio: {sharpe:.2f}")
print(f"Sortino Ratio: {sortino:.2f}")
print(f"총 거래 횟수: {trades}")
print(f"연간 거래 횟수: {trades / (days / 252):.2f}")

