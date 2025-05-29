import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# MA 기간 설정
MA = 185

# 데이터 로드
AGG = yf.download('AGG', start='2010-02-09', auto_adjust=True, interval='1d', progress=True, multi_level_index=False)
AGG.drop(['Open','High','Low','Volume'], axis=1, inplace=True)

AGG.loc[:,'AGG_MA'] = AGG.loc[:,'Close'].rolling(window=85).mean()
AGG = AGG[['Close', 'AGG_MA']].rename(columns={'Close': 'AGG'})
AGG.loc[:,'Regime'] = AGG.loc[:,'AGG'] >= AGG.loc[:,'AGG_MA']

TQQQ = yf.download('TQQQ', start='2010-02-09', auto_adjust=True, interval='1d', progress=True, multi_level_index=False)
TQQQ.drop(['Open','High','Low','Volume'], axis=1, inplace=True)

TQQQ.loc[:,'TQQQ_MA'] = TQQQ.loc[:,'Close'].rolling(window=MA).mean()
TQQQ = TQQQ[['Close', 'TQQQ_MA']].rename(columns={'Close': 'TQQQ'})
TQQQ.loc[:,'Long'] = TQQQ.loc[:,'TQQQ'] >= TQQQ.loc[:,'TQQQ_MA']

# AGG 데이터와 TQQQ 데이터 병합
df = TQQQ.join(AGG, how='left')

# 데이터 정렬 및 인덱스 설정
df = df.sort_index()
df.index = pd.to_datetime(df.index)
df = df.dropna(subset=['TQQQ_MA', 'AGG_MA'])

# Position 생성(당일 종가기준 포지션 진입)
df['Position'] = np.where((df['Long'] == 1) & (df['Regime'] == 1), 1, 0)
df['MAPosition'] = np.where((df['Long'] == 1), 1, 0)

df['Position'] = df['Position'].shift(0).fillna(0)
df['MAPosition'] = df['MAPosition'].shift(0).fillna(0) # 당일 신호 당일 종가

# 수익률 계산
df['daily_return'] = df['TQQQ'].pct_change().fillna(0)
df['MA_return'] = df['daily_return'] * df['MAPosition']  # MA 전략 수익률
df['strategy_return'] = df['daily_return'] * df['Position']

# 수수료 적용
fee = 0.0009
df['MA_return'] -= df['MAPosition'].diff().abs().fillna(0) * fee
df['strategy_return'] -= df['Position'].diff().abs().fillna(0) * fee

# 누적 수익률
df['cum_return'] = (1 + df['strategy_return']).cumprod()
df['cum_MA_return'] = (1 + df['MA_return']).cumprod()
df['cum_market'] = (1 + df['daily_return']).cumprod()

# 거래 신호 생성
df['signal'] = 0
df.loc[df['Position'] == 1, 'signal'] = 1
df.loc[df['Position'] == 0, 'signal'] = -1
# 거래 횟수 계산
df['trade'] = df['signal'].diff().abs().fillna(0)
df['trade'] = df['trade'].replace(2, 1)  # 포지션 진입과 청산을 하나의 거래로 간주
df['trade'] = df['trade'].astype(int)

df.drop(['TQQQ_MA','AGG', 'AGG_MA', 'Regime'], axis=1, inplace=True)

# 연도 계산
start_date = df.index[0]
end_date = df.index[-1]
n_years = (end_date - start_date).days / 365.25

# 통계 지표 계산
Strategy_results = []

cagr = df['cum_return'].iloc[-1] ** (1 / n_years) - 1
mdd = (df['cum_return'] / df['cum_return'].cummax() - 1).min()
num_trades = df['trade'].sum()
mean_return = df['strategy_return'].mean()
std_return = df['strategy_return'].std()
neg_std = df.loc[df['strategy_return'] < 0, 'strategy_return'].std()
sharpe_ratio = (mean_return / std_return) * np.sqrt(252) if std_return != 0 else np.nan
sortino_ratio = (mean_return / neg_std) * np.sqrt(252) if neg_std != 0 else np.nan

buy_and_hold_return = df['cum_market'].iloc[-1] - 1
buy_and_hold_cagr = buy_and_hold_return ** (1 / n_years) - 1
buy_and_hold_mdd = (df['cum_market'] / df['cum_market'].cummax() - 1).min()
BH_mean_return = df['daily_return'].mean()
BH_std_return = df['daily_return'].std()
neg_BH_std = df.loc[df['daily_return'] < 0, 'daily_return'].std()
BH_sharpe_ratio = (BH_mean_return / BH_std_return) * np.sqrt(252) if BH_std_return != 0 else np.nan
BH_sortino_ratio = (BH_mean_return / neg_BH_std) * np.sqrt(252) if neg_BH_std != 0 else np.nan

MA_cagr = df['cum_MA_return'].iloc[-1] ** (1 / n_years) - 1
MA_mdd = (df['cum_MA_return'] / df['cum_MA_return'].cummax() - 1).min()
MA_mean_return = df['MA_return'].mean()
MA_std_return = df['MA_return'].std()
neg_MA_std = df.loc[df['MA_return'] < 0, 'MA_return'].std()
MA_sharpe_ratio = (MA_mean_return / MA_std_return) * np.sqrt(252) if MA_std_return != 0 else np.nan
MA_sortino_ratio = (MA_mean_return / neg_MA_std) * np.sqrt(252) if neg_MA_std != 0 else np.nan


Strategy_results.append({
    'Model': 'MA+AGG',
    'MA': MA,
    'CAGR': cagr,
    'MDD': mdd,
    'Sharpe': sharpe_ratio,
    'Sortino': sortino_ratio,
    'Trades': int(num_trades)
    })

MA_results = []
MA_results.append({
    'Model': 'TQQQ MA',
    'MA': MA,
    'CAGR': MA_cagr,
    'MDD': MA_mdd,
    'Sharpe': MA_sharpe_ratio,
    'Sortino': MA_sortino_ratio,
    })

BH_results = []
BH_results.append({
    'Model': 'TQQQ BH',
    'CAGR': buy_and_hold_cagr,
    'MDD': buy_and_hold_mdd,
    'Sharpe': BH_sharpe_ratio,
    'Sortino': BH_sortino_ratio,
    })



# 결과 정리 및 출력
Strategy_results = pd.DataFrame(Strategy_results)
Strategy_results = Strategy_results.sort_values(by='CAGR', ascending=False).reset_index(drop=True)
print(Strategy_results)

MA_results = pd.DataFrame(MA_results)
MA_results = MA_results.sort_values(by='CAGR', ascending=False).reset_index(drop=True)
print(MA_results)

BH_results = pd.DataFrame(BH_results)
BH_results = BH_results.sort_values(by='CAGR', ascending=False).reset_index(drop=True)
print(BH_results)

print(df.head(5))
print(df.tail(5))
