import pandas as pd
import numpy as np
from datetime import datetime

def xlsx_to_dataframe(file_name): # XLSX 불러오기 함수
    try:
        file_path = f'C:/Users/GSR/Desktop/Python_project/git_folder/{file_name}'
        # file_path = f'C:/Users/ilpus/PythonProjects/git_folder/{file_name}'
        df = pd.read_excel(file_path)
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        return df
    except Exception as e:
        print(f"오류 발생: {e}")
        return None
    
def Investment_Period(df): # 투자 기간 계산 함수
    start_date = df.iloc[0,0]
    end_date = df.iloc[-1,0]
    days = (end_date - start_date).days
    years = days / 365 if days > 0 else 0
    return years

def MDD(df): # MDD 함수
    df['balance'] = 100 * df['return'].cumprod()
    df['peak'] = df['balance'].cummax()
    df['dd'] = (df['balance'] - df['peak']) / df['peak']
    # mdd = df['dd'].min()
    return df

def Return_CAGR(df, years): # 누적 수익률과 CAGR 함수
    total_return = df['return'].cumprod().iloc[-1]
    if years == 0:
        cagr = 0
    else:
        cagr = (total_return) ** (1 / years) - 1
    return total_return, cagr

def Sharpe_SortinoRatio(df): # sharpe_ratio과 sortino_ratio 함수
    df['log_return'] = np.log(df['return']) # 로그 수익률 계산
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

    return df, sharpe_ratio, sortino_ratio

## 변수 모음
# KODEX200.xlsx #3500
# KODEX코스닥150.xlsx #2500
# 직전 1개월간 거래대급 상위 국내섹터별 ETF 4개 #1,2위 2000, 3,4위 1000
# kodex2차전지.xlsx 
# kodex반도체.xlsx 
# kodex은행.xlsx
# kodex자동차.xlsx 
# tiger200중공업.xlsx
# tiger리츠부동산.xlsx
# tiger헬스케어.xlsx
# tiger화장품.xlsx
# range_model = (df['high'] - df['low']) * k
# range_model = (df['high'] - df['open']) * k
# range_model = (df['open'] - df['low']) * k

# 변수들 #
file_name = 'KODEX200.xlsx'
df = xlsx_to_dataframe(file_name)
tax = 0.000015
슬리피지 = 0.0002 # ETF별 조정
k = 0.4 # 테스트

# range_model = (df['high'] - df['low']) * k # 테스트
# range_modelstr = "전일고가-전일저가"
range_model = (df['high'] - df['open']) * k
range_modelstr = "전일고가-전일시가"
# range_model = (df['open'] - df['low']) * k 
# range_modelstr = "전일시가-전일저가"

print(f"ETF: {file_name[:-5]}")
# print('*'*40)

## 변동성 돌파 전략 익일시가 청산 ##
class vol_breakout_open:
    def __init__(self, df, tax, 슬리피지, k, range_model, range_modelstr):
        self.df = df
        self.tax = tax
        self.슬리피지 = 슬리피지
        self.k = k
        self.range_model = range_model
        self.range_modelstr = range_modelstr
        self.model = '변동성돌파_익일시가청산'
        print('*'*40)
    
    def back_test(self):
        self.df['range'] = self.range_model
        self.df['target'] = self.df['open'] + self.df['range'].shift(1)
        self.df['cond'] = self.df['high'] >= self.df['target']
        cond = self.df['cond']

        self.df['buy'] = self.df.loc[cond, 'target']
        self.df['open-1'] = self.df['open'].shift(-1)
        self.df['sell'] = self.df.loc[cond, 'open-1']

        self.trading = self.df.loc[cond, 'close']
        self.trading_count = len(self.trading)

        self.df['return'] = (self.df['sell'] - (self.df['sell'] * (self.tax + self.슬리피지))) / (self.df['buy'] + (self.df['buy'] * self.tax))
        self.df['return'] = self.df['return'].fillna(1)

        # MDD 계산
        self.df = MDD(self.df)
        self.mdd = self.df['dd'].min()

        # 투자 기간 계산
        self.years = Investment_Period(self.df)

        # 누적 수익률과 CAGR 계산
        self.total_return, self.cagr = Return_CAGR(self.df, self.years)

        # Sharpe & Sortino Ratio 계산
        self.df, self.sharpe_ratio, self.sortino_ratio = Sharpe_SortinoRatio(self.df)

        # 출력
        print(f"Model: {self.model} - K: {self.k}")
        print(f"Range: {self.range_modelstr}")
        print(f"Total Return: {self.total_return:.2%}")
        print(f"CAGR: {self.cagr:.2%}")
        print(f"Max Drawdown: {self.mdd:.2%}")
        print(f"Sharpe Ratio: {self.sharpe_ratio:.4f}")
        print(f"Sortino Ratio: {self.sortino_ratio:.4f}")
        print(f"Trading Count: {self.trading_count}")
        print(f"Investment Period: {self.years:.2f} years")
        print('*' * 40)







t1 = vol_breakout_open(df, tax, 슬리피지, k, range_model, range_modelstr)
t1.back_test()





# model = '변동성돌파_익일시가청산'
# df1 = df

# df1['range'] = range_model
# df1['target'] = df1['open'] + df1['range'].shift(1)
# df1['cond'] = df1['high'] >= df1['target']
# cond = df1['cond']

# df1['buy'] = df1.loc[cond, 'target']
# df1['open-1'] = df1['open'].shift(-1)
# df1['sell'] = df1.loc[cond, 'open-1']


# trading = df1.loc[cond, 'close']
# trading_count = len(trading)

# df1['return'] = (df1['sell'] - (df1['sell'] * (tax+슬리피지))) / (df1['buy'] + (df1['buy'] * tax))
# df1['return'] = df1['return'].fillna(1)

# # MDD 계산
# df1 = MDD(df)
# mdd = df1['dd'].min()

# # 투자 기간 계산
# years = Investment_Period(df1)

# # 누적 수익률과 CAGR 계산
# total_return = Return_CAGR(df1)[0]
# cagr = Return_CAGR(df1)[1]

# # Sharpe & Sortino Ratio 계산
# df1 = Sharpe_SortinoRatio(df1)[0]
# sharpe_ratio = Sharpe_SortinoRatio(df1)[1]
# sortino_ratio = Sharpe_SortinoRatio(df1)[2]

# # 출력
# print(f"Model: {model} - K: {k}")
# print(f"Range: {range_modelstr}")
# print(f"Total Return: {total_return:.2%}")
# print(f"CAGR: {cagr:.2%}")
# print(f"Max Drawdown: {mdd:.2%}")
# print(f"Sharpe Ratio: {sharpe_ratio:.4f}")
# print(f"Sortino Ratio: {sortino_ratio:.4f}")
# print(f"Trading Count: {trading_count}")
# print(f"Investment Period: {years:.2f} years")

# print('*'*40)

# 결과값 데이터프레임 만들기
# 1) 요약
# data = 
# rdf = pd.DataFrame(data=data, 
#                    index=['Total Return','CAGR', 'Max Drawdown', 'Sharpe Ratio', 'Sortino Ratio',
#                           'Trading Count', 'Investment Period'], columns=['file_name'])

## 변동성 돌파 전략 당일종가 청산 ##
# 기본 트레잉딩 모델 당일청산
# 변수들 #
model = '변동성돌파_당일종가청산'
df2 = df

df2['range'] = range_model
df2['target'] = df2['open'] + df2['range'].shift(1)
df2['cond'] = df2['high'] >= df2['target']
cond = df2['cond']

df2['buy'] = df2.loc[cond, 'target']
df2['sell'] = df2.loc[cond, 'close']

trading = df2.loc[cond, 'close']
trading_count = len(trading)

df2['return'] = (df2['sell'] - (df2['sell'] * (tax+슬리피지))) / (df2['buy'] + (df2['buy'] * tax))
df2['return'] = df2['return'].fillna(1)

# MDD 계산
df2 = MDD(df2)
mdd = df2['dd'].min()

# 투자 기간 계산
years = Investment_Period(df2)

# 누적 수익률과 CAGR 계산
total_return = Return_CAGR(df2, years)[0]
cagr = Return_CAGR(df2, years)[1]

# Sharpe & Sortino Ratio 계산
df = Sharpe_SortinoRatio(df2)[0]
sharpe_ratio = Sharpe_SortinoRatio(df2)[1]
sortino_ratio = Sharpe_SortinoRatio(df2)[2]

# 결과값 데이터프레임 만들기
# 1) 요약
# data = 
# rdf = pd.DataFrame(data=data, 
#                    index=['Total Return','CAGR', 'Max Drawdown', 'Sharpe Ratio', 'Sortino Ratio',
#                           'Trading Count', 'Investment Period'], columns=['file_name'])

# 출력
# print(df2.head(5))
print(f"Model: {model} - K: {k}")
print(f"Range: {range_modelstr}")
print(f"Total Return: {total_return:.2%}")
print(f"CAGR: {cagr:.2%}")
print(f"Max Drawdown: {mdd:.2%}")
print(f"Sharpe Ratio: {sharpe_ratio:.4f}")
print(f"Sortino Ratio: {sortino_ratio:.4f}")
print(f"Trading Count: {trading_count}")
print(f"Investment Period: {years:.2f} years")

print('*'*40)


########### 리니어 buy_and_hold k###################
# 변수들
model = 'buy_and_hold'
df0 = df
tax = 0

df0['buy'] = df0['close'].shift(1)
df0['sell'] = df0['close']

df0['return'] = df0['sell']/df0['buy']
df0['return'] = df0['return'].fillna(1)

# MDD 계산
df0 = MDD(df0)
mdd = df0['dd'].min()

# 투자 기간 계산
years = Investment_Period(df0)

# 누적 수익률과 CAGR 계산
total_return = Return_CAGR(df0, years)[0]
cagr = Return_CAGR(df0, years)[1]

# Sharpe & Sortino Ratio 계산
df = Sharpe_SortinoRatio(df0)[0]
sharpe_ratio = Sharpe_SortinoRatio(df0)[1]
sortino_ratio = Sharpe_SortinoRatio(df0)[2]

# 출력
# print(df0.head(10))
print(f"Model: {model}")
print(f"Total Return: {total_return:.2%}")
print(f"CAGR: {cagr:.2%}")
print(f"Max Drawdown: {mdd:.2%}")
print(f"Sharpe Ratio: {sharpe_ratio:.4f}")
print(f"Sortino Ratio: {sortino_ratio:.4f}")
print(f"Investment Period: {years:.2f} years")

########################################################################################################


### 기간수익률
# df.set_index('date', inplace=True)

# yearly_returns = {}
# yearly_mdds = {}

# for year, group in df.groupby(df.index.year):
#     year_return = group['return'].cumprod().iloc[-1]
#     balance = 100 * group['return'].cumprod()
#     peak = balance.cummax()
#     dd = (balance - peak) / peak
#     mdd = dd.min()

#     yearly_returns[year] = year_return
#     yearly_mdds[year] = mdd

# # 연도별 수익률 출력
# print("\n📈 연도별 수익률:")
# for year, r in yearly_returns.items():
#     print(f"{year}: {r:.2%}")

# # 연도별 MDD 출력
# print("\n📉 연도별 최대 낙폭 (MDD):")
# for year, m in yearly_mdds.items():
#     print(f"{year}: {m:.2%}")

# print('*'*30)

# # 월별 수익률 및 MDD 계산
# monthly_returns = {}
# monthly_mdds = {}

# # 월 단위로 그룹화
# for (year, month), group in df.groupby([df.index.year, df.index.month]):
#     month_key = f"{year}-{month:02d}"
#     month_return = group['return'].cumprod().iloc[-1]
#     balance = 100 * group['return'].cumprod()
#     peak = balance.cummax()
#     dd = (balance - peak) / peak
#     mdd = dd.min()

#     monthly_returns[month_key] = month_return
#     monthly_mdds[month_key] = mdd

# # 월별 수익률 출력
# print("\n📅 월별 수익률:")
# for month, r in monthly_returns.items():
#     print(f"{month}: {r:.2%}")

# # 월별 MDD 출력
# print("\n📉 월별 최대 낙폭 (MDD):")
# for month, m in monthly_mdds.items():
#     print(f"{month}: {m:.2%}")

# print('*'*30)

# df.set_index('date', inplace=True)

# yearly_returns = {}
# yearly_mdds = {}

# for year, group in df.groupby(df.index.year):
#     year_return = group['return'].cumprod().iloc[-1]
#     balance = 100 * group['return'].cumprod()
#     peak = balance.cummax()
#     dd = (balance - peak) / peak
#     mdd = dd.min()

#     yearly_returns[year] = year_return
#     yearly_mdds[year] = mdd

# # 연도별 수익률 출력
# print("\n📈 연도별 수익률:")
# for year, r in yearly_returns.items():
#     print(f"{year}: {r:.2%}")

# # 연도별 MDD 출력
# print("\n📉 연도별 최대 낙폭 (MDD):")
# for year, m in yearly_mdds.items():
#     print(f"{year}: {m:.2%}")

# print('*'*30)

# # 월별 수익률 및 MDD 계산
# monthly_returns = {}
# monthly_mdds = {}

# # 월 단위로 그룹화
# for (year, month), group in df.groupby([df.index.year, df.index.month]):
#     month_key = f"{year}-{month:02d}"
#     month_return = group['return'].cumprod().iloc[-1]
#     balance = 100 * group['return'].cumprod()
#     peak = balance.cummax()
#     dd = (balance - peak) / peak
#     mdd = dd.min()

#     monthly_returns[month_key] = month_return
#     monthly_mdds[month_key] = mdd

# # 월별 수익률 출력
# print("\n📅 월별 수익률:")
# for month, r in monthly_returns.items():
#     print(f"{month}: {r:.2%}")

# # 월별 MDD 출력
# print("\n📉 월별 최대 낙폭 (MDD):")
# for month, m in monthly_mdds.items():
#     print(f"{month}: {m:.2%}")

# print('*'*30)


# ########### 리니어 buy_and_hold k와 tax는 변수로 ###################
# # 변수들
# file_name = 'kodex반도체.xlsx'
# df = xlsx_to_dataframe(file_name)

# tax = 0
# ####################################################################
# df['buy'] = df['close'].shift(1)
# df['sell'] = df['close']

# df['return'] = df['sell']/df['buy']
# df['return'] = df['return'].fillna(1)

# # MDD 계산
# df = MDD(df)
# mdd = df['dd'].min()

# # 투자 기간 계산
# years = Investment_Period(df)

# # 누적 수익률과 CAGR 계산
# total_return = Return_CAGR(df)[0]
# cagr = Return_CAGR(df)[1]

# # Sharpe & Sortino Ratio 계산
# df = Sharpe_SortinoRatio(df)[0]
# sharpe_ratio = Sharpe_SortinoRatio(df)[1]
# sortino_ratio = Sharpe_SortinoRatio(df)[2]

# # 출력
# print(df.head(10))
# print(f"Total Return: {total_return:.2%}")
# print(f"CAGR: {cagr:.2%}")
# print(f"Max Drawdown: {mdd:.2%}")
# print(f"Sharpe Ratio: {sharpe_ratio:.4f}")
# print(f"Sortino Ratio: {sortino_ratio:.4f}")
# print(f"Investment Period: {years:.2f} years")

# df.set_index('date', inplace=True)

# yearly_returns = {}
# yearly_mdds = {}

# for year, group in df.groupby(df.index.year):
#     year_return = group['return'].cumprod().iloc[-1]
#     balance = 100 * group['return'].cumprod()
#     peak = balance.cummax()
#     dd = (balance - peak) / peak
#     mdd = dd.min()

#     yearly_returns[year] = year_return
#     yearly_mdds[year] = mdd

# # 연도별 수익률 출력
# print("\n📈 연도별 수익률:")
# for year, r in yearly_returns.items():
#     print(f"{year}: {r:.2%}")

# # 연도별 MDD 출력
# print("\n📉 연도별 최대 낙폭 (MDD):")
# for year, m in yearly_mdds.items():
#     print(f"{year}: {m:.2%}")

# print('*'*30)

# # 월별 수익률 및 MDD 계산
# monthly_returns = {}
# monthly_mdds = {}

# # 월 단위로 그룹화
# for (year, month), group in df.groupby([df.index.year, df.index.month]):
#     month_key = f"{year}-{month:02d}"
#     month_return = group['return'].cumprod().iloc[-1]
#     balance = 100 * group['return'].cumprod()
#     peak = balance.cummax()
#     dd = (balance - peak) / peak
#     mdd = dd.min()

#     monthly_returns[month_key] = month_return
#     monthly_mdds[month_key] = mdd

# # 월별 수익률 출력
# print("\n📅 월별 수익률:")
# for month, r in monthly_returns.items():
#     print(f"{month}: {r:.2%}")

# # 월별 MDD 출력
# print("\n📉 월별 최대 낙폭 (MDD):")
# for month, m in monthly_mdds.items():
#     print(f"{month}: {m:.2%}")