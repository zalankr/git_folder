import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# 1. 데이터 로딩
df = yf.download('QQQ', progress=False, multi_level_index=False)
df = df[['Close']].rename(columns={'Close': 'price'})

results = []

# 2. 이동평균 주기별 백테스트
for ma in range(10, 301, 5):
    temp_df = df.copy()

    # 이동평균선 계산
    temp_df[f'ma{ma}'] = temp_df['price'].rolling(ma).mean()

    # 시그널 생성 (정렬된 인덱스로 비교)
    temp_df['signal'] = (temp_df['price'] > temp_df[f'ma{ma}']).astype(int)
    temp_df.loc[:temp_df.index[ma], 'signal'] = 0  # MA 이전 구간은 신호 없음

    # 포지션 (전일 신호 유지)
    temp_df['position'] = temp_df['signal'].shift(1).fillna(0)

    # 수익률 계산
    temp_df['daily_return'] = temp_df['price'].pct_change().fillna(0)
    temp_df['strategy_return'] = temp_df['daily_return'] * temp_df['position']

    # 수수료 적용
    fee = 0.0009
    temp_df['trade'] = temp_df['position'].diff().abs().fillna(0)
    temp_df['strategy_return'] -= temp_df['trade'] * fee

    # 누적 수익률
    temp_df['cum_return'] = (1 + temp_df['strategy_return']).cumprod()
    temp_df['cum_market'] = (1 + temp_df['daily_return']).cumprod()

    # 연도 계산
    start_date = temp_df.index[0]
    end_date = temp_df.index[-1]
    n_years = (end_date - start_date).days / 365.25

    # 통계 지표
    cagr = temp_df['cum_return'].iloc[-1] ** (1 / n_years) - 1
    mdd = (temp_df['cum_return'] / temp_df['cum_return'].cummax() - 1).min()
    num_trades = temp_df['trade'].sum()

    # Sharpe & Sortino
    mean_return = temp_df['strategy_return'].mean()
    std_return = temp_df['strategy_return'].std()
    neg_std = temp_df.loc[temp_df['strategy_return'] < 0, 'strategy_return'].std()

    sharpe_ratio = (mean_return / std_return) * np.sqrt(252) if std_return != 0 else np.nan
    sortino_ratio = (mean_return / neg_std) * np.sqrt(252) if neg_std != 0 else np.nan

    results.append({
        'MA': ma,
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


