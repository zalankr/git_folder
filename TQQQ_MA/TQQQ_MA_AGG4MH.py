import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# 1. 데이터 로딩
df = yf.download('TQQQ', start='2010-01-01', progress=False, multi_level_index=False)
df = df[['Close']].rename(columns={'Close': 'price'})

results = []

# 이동평균선 계산
df['MA225'] = df['price'].rolling(225).mean()

# 시그널 생성 (정렬된 인덱스로 비교)
df['signal'] = (df['price'] > df['MA225']).astype(int)
df.loc[:df.index[225], 'signal'] = 0  # MA 이전 구간은 신호 없음

# 포지션 (전일 신호 유지)
df['position'] = df['signal'].shift(1).fillna(0)

# 수익률 계산
df['daily_return'] = df['price'].pct_change().fillna(0)

# 전략 수익률
df['strategy_return'] = df['daily_return'] * df['position']

# 수수료 적용
fee = 0.0009
df['trade'] = df['position'].diff().abs().fillna(0)
df['strategy_return'] -= df['trade'] * fee

# 누적 수익률

df['cum_return'] = (1 + df['strategy_return']).cumprod()
df['cum_market'] = (1 + df['daily_return']).cumprod()

# 연도 계산
start_date = df.index[0]
end_date = df.index[-1]
n_years = (end_date - start_date).days / 365.25

# 통계 지표
results = []

cagr = df['cum_return'].iloc[-1] ** (1 / n_years) - 1
mdd = (df['cum_return'] / df['cum_return'].cummax() - 1).min()

num_trades = df['trade'].sum()
mean_return = df['strategy_return'].mean()
std_return = df['strategy_return'].std()
neg_std = df.loc[df['strategy_return'] < 0, 'strategy_return'].std()

sharpe_ratio = (mean_return / std_return) * np.sqrt(252) if std_return != 0 else np.nan
sortino_ratio = (mean_return / neg_std) * np.sqrt(252) if neg_std != 0 else np.nan

results.append({
    'MA': 225,
    'CAGR': cagr,
    'MDD': mdd,
    'Sharpe': sharpe_ratio,
    'Sortino': sortino_ratio,
    'Trades': int(num_trades)
})

# 결과 정리 및 출력
result = pd.DataFrame(results)
result = result.sort_values(by='CAGR', ascending=False).reset_index(drop=True)
print(result)


