import pandas as pd
import numpy as np
from datetime import datetime

def xlsx_to_dataframe(file_name): # XLSX 불러오기 함수
    try:
        file_path = f'C:/Users/GSR/Desktop/Python_project/git_folder/{file_name}'
        df = pd.read_excel(file_path)
        return df
    except Exception as e:
        print(f"오류 발생: {e}")
        return None

## 변수 모음
# xlsx 파일명
# kodex2차전지.xlsx
# kodex반도체.xlsx
# kodex은행.xlsx
# kodex자동차.xlsx
# tiger200중공업.xlsx
# tiger리츠부동산.xlsx
# tiger헬스케어.xlsx
# tiger화장품.xlsx

# 변수들
file_name = 'kodex반도체.xlsx'
df = xlsx_to_dataframe(file_name)
df['date'] = pd.to_datetime(df['date'], errors='coerce')
tax = 0.000015
k = 0.5

range_model = (df['high'] - df['low']) * k
# range_model = (df['high'] - df['open']) * k
# range_model = (df['open'] - df['low']) * k

## 리니어 변동성 돌파 전략 당일 종가 ###

df['range'] = range_model
df['target'] = df['open'] + df['range'].shift(1)
df['cond'] = df['high'] >= df['target']
cond = df['cond']

df['buy'] = df.loc[cond, 'target']
df['sell'] = df.loc[cond, 'close']

trading = df.loc[cond, 'close']
trading_count = len(trading)

df['return'] = (df['sell'] - (df['sell'] * tax)) / (df['buy'] + (df['buy'] * tax))
df['return'] = df['return'].fillna(1)

df['balance'] = 100 * df['return'].cumprod()
df['peak'] = df['balance'].cummax()
df['dd'] = (df['balance'] - df['peak']) / df['peak']
max_mdd = df['dd'].min()

# 투자 기간 계산
start_date = df.iloc[0,0]
end_date = df.iloc[-1,0]

days = (end_date - start_date).days
years = days / 365 if days > 0 else 0

# 누적 수익률과 CAGR 계산 (예외처리 포함)
total_return = df['return'].cumprod().iloc[-1]
if years == 0:
    cagr = 0
else:
    cagr = (total_return) ** (1 / years) - 1

# 로그 수익률 계산
df['log_return'] = np.log(df['return'])
mean_return = df['log_return'].mean()
std_return = df['log_return'].std()
down_std = df[df['log_return'] < 0]['log_return'].std()

# 무위험 수익률
rf = 0.01

# Sharpe & Sortino Ratio 계산 (예외처리 포함)
if std_return == 0 or np.isnan(std_return):
    sharpe_ratio = 0
else:
    sharpe_ratio = (mean_return - rf / 252) / std_return * np.sqrt(252)

if down_std == 0 or np.isnan(down_std):
    sortino_ratio = 0
else:
    sortino_ratio = (mean_return - rf / 252) / down_std * np.sqrt(252)

# 출력
print(df.head(10))
print(f"Total Return: {total_return:.2%}")
print(f"CAGR: {cagr:.2%}")
print(f"Max Drawdown: {max_mdd:.2%}")
print(f"Sharpe Ratio: {sharpe_ratio:.4f}")
print(f"Sortino Ratio: {sortino_ratio:.4f}")
print(f"Trading Count: {trading_count}")
print(f"Investment Period: {years:.2f} years")

df.set_index('date', inplace=True)

yearly_returns = {}
yearly_mdds = {}

for year, group in df.groupby(df.index.year):
    year_return = group['return'].cumprod().iloc[-1]
    balance = 100 * group['return'].cumprod()
    peak = balance.cummax()
    dd = (balance - peak) / peak
    mdd = dd.min()

    yearly_returns[year] = year_return
    yearly_mdds[year] = mdd

# 연도별 수익률 출력
print("\n📈 연도별 수익률:")
for year, r in yearly_returns.items():
    print(f"{year}: {r:.2%}")

# 연도별 MDD 출력
print("\n📉 연도별 최대 낙폭 (MDD):")
for year, m in yearly_mdds.items():
    print(f"{year}: {m:.2%}")

print('*'*30)

# 월별 수익률 및 MDD 계산
monthly_returns = {}
monthly_mdds = {}

# 월 단위로 그룹화
for (year, month), group in df.groupby([df.index.year, df.index.month]):
    month_key = f"{year}-{month:02d}"
    month_return = group['return'].cumprod().iloc[-1]
    balance = 100 * group['return'].cumprod()
    peak = balance.cummax()
    dd = (balance - peak) / peak
    mdd = dd.min()

    monthly_returns[month_key] = month_return
    monthly_mdds[month_key] = mdd

# 월별 수익률 출력
print("\n📅 월별 수익률:")
for month, r in monthly_returns.items():
    print(f"{month}: {r:.2%}")

# 월별 MDD 출력
print("\n📉 월별 최대 낙폭 (MDD):")
for month, m in monthly_mdds.items():
    print(f"{month}: {m:.2%}")

print('*'*30)
print('*'*30)

########### 리니어 buy_and_hold k와 tax는 변수로 ###################
# 변수들
file_name = 'kodex반도체.xlsx'
df = xlsx_to_dataframe(file_name)
df['date'] = pd.to_datetime(df['date'], errors='coerce')
tax = 0
####################################################################
df['buy'] = df['close'].shift(1)
df['sell'] = df['close']

df['return'] = df['sell']/df['buy']
df['return'] = df['return'].fillna(1)

df['balance'] = 100 * df['return'].cumprod()
df['peak'] = df['balance'].cummax()
df['dd'] = (df['balance'] - df['peak']) / df['peak']
max_mdd = df['dd'].min()

# 투자 기간 계산
start_date = df.iloc[0,0]
end_date = df.iloc[-1,0]

days = (end_date - start_date).days
years = days / 365 if days > 0 else 0

# 누적 수익률과 CAGR 계산 (예외처리 포함)
total_return = df['return'].cumprod().iloc[-1]
if years == 0:
    cagr = 0
else:
    cagr = (total_return) ** (1 / years) - 1

# 로그 수익률 계산
df['log_return'] = np.log(df['return'])
mean_return = df['log_return'].mean()
std_return = df['log_return'].std()
down_std = df[df['log_return'] < 0]['log_return'].std()

# 무위험 수익률
rf = 0.01

# Sharpe & Sortino Ratio 계산 (예외처리 포함)
if std_return == 0 or np.isnan(std_return):
    sharpe_ratio = 0
else:
    sharpe_ratio = (mean_return - rf / 252) / std_return * np.sqrt(252)

if down_std == 0 or np.isnan(down_std):
    sortino_ratio = 0
else:
    sortino_ratio = (mean_return - rf / 252) / down_std * np.sqrt(252)

# 출력
print(df.head(10))
print(f"Total Return: {total_return:.2%}")
print(f"CAGR: {cagr:.2%}")
print(f"Max Drawdown: {max_mdd:.2%}")
print(f"Sharpe Ratio: {sharpe_ratio:.4f}")
print(f"Sortino Ratio: {sortino_ratio:.4f}")
print(f"Investment Period: {years:.2f} years")

df.set_index('date', inplace=True)

yearly_returns = {}
yearly_mdds = {}

for year, group in df.groupby(df.index.year):
    year_return = group['return'].cumprod().iloc[-1]
    balance = 100 * group['return'].cumprod()
    peak = balance.cummax()
    dd = (balance - peak) / peak
    mdd = dd.min()

    yearly_returns[year] = year_return
    yearly_mdds[year] = mdd

# 연도별 수익률 출력
print("\n📈 연도별 수익률:")
for year, r in yearly_returns.items():
    print(f"{year}: {r:.2%}")

# 연도별 MDD 출력
print("\n📉 연도별 최대 낙폭 (MDD):")
for year, m in yearly_mdds.items():
    print(f"{year}: {m:.2%}")

print('*'*30)

# 월별 수익률 및 MDD 계산
monthly_returns = {}
monthly_mdds = {}

# 월 단위로 그룹화
for (year, month), group in df.groupby([df.index.year, df.index.month]):
    month_key = f"{year}-{month:02d}"
    month_return = group['return'].cumprod().iloc[-1]
    balance = 100 * group['return'].cumprod()
    peak = balance.cummax()
    dd = (balance - peak) / peak
    mdd = dd.min()

    monthly_returns[month_key] = month_return
    monthly_mdds[month_key] = mdd

# 월별 수익률 출력
print("\n📅 월별 수익률:")
for month, r in monthly_returns.items():
    print(f"{month}: {r:.2%}")

# 월별 MDD 출력
print("\n📉 월별 최대 낙폭 (MDD):")
for month, m in monthly_mdds.items():
    print(f"{month}: {m:.2%}")