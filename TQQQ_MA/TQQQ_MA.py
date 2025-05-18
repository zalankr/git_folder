import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# 1. 데이터 로딩
df = yf.download('TQQQ', start='2010-01-01', progress=False, multi_level_index=False)
df = df[['Close']].rename(columns={'Close': 'price'})

# 2. 50일 이동평균선
df['ma20'] = df['price'].rolling(20).mean()

# 3. 매수/매도 시그널 생성
df['signal'] = 0
df['signal'][20:] = np.where(df['price'][20:] > df['ma20'][20:], 1, 0)

# 4. 포지션 계산 (전일 signal 유지)
df['position'] = df['signal'].shift(1).fillna(0)

# 5. 일간 수익률 및 전략 수익률
df['daily_return'] = df['price'].pct_change().fillna(0)
df['strategy_return'] = df['daily_return'] * df['position']

# 6. 수수료 적용
fee = 0.0009
df['trade'] = df['position'].diff().abs()
df['strategy_return'] -= df['trade'] * fee

# 7. 누적 수익률 계산
df['cum_return'] = (1 + df['strategy_return']).cumprod()
df['cum_market'] = (1 + df['daily_return']).cumprod()

# 8. CAGR / MDD 계산
start_date = df.index[0]
end_date = df.index[-1]
n_years = (end_date - start_date).days / 365.25

cagr = df['cum_return'].iloc[-1] ** (1 / n_years) - 1
mdd = (df['cum_return'] / df['cum_return'].cummax() - 1).min()

print(f"[검증된 전략 성과]")
print(f"CAGR: {cagr:.2%}")
print(f"MDD: {mdd:.2%}")

