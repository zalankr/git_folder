import pandas as pd
import numpy as np
from datetime import datetime

# XLSX 불러오기
def xlsx_to_dataframe(file_name):
    try:
        file_path = f'C:/Users/GSR/Desktop/Python_project/git_folder/{file_name}'
        df = pd.read_excel(file_path)
        return df
    except Exception as e:
        print(f"오류 발생: {e}")
        return None

# xlsx 파일명
file_name = 'kodex반도체.xlsx'
df = xlsx_to_dataframe(file_name)

# 변수들
k = 0.5
tax = 0.000015
range_model = (df['high'] - df['low']) * k
# range_model = (df['high'] - df['open']) * k
# range_model = (df['open'] - df['low']) * k

# ### 리니어 변동성 돌파 전략 당일 종가 ###
# df['range'] = range_model
# df['target'] = df['open'] + df['range'].shift(1)
# df['cond'] = df['high'] >= df['target']
# cond = df['cond']

# df['buy'] = df.loc[cond, 'target']
# df['sell'] = df.loc[cond, 'close']

# trading = df.loc[cond, 'close']
# trading_count = len(trading)

# df['return'] = (df['sell'] - (df['sell'] * tax)) / (df['buy'] + (df['buy'] * tax))
# df['return'] = df['return'].fillna(1)

# df['balance'] = 100 * df['return'].cumprod()
# df['peak'] = df['balance'].cummax()
# df['dd'] = (df['balance'] - df['peak']) / df['peak']
# max_mdd = df['dd'].min()

# # 투자 기간 계산
# start_date = df.iloc[0,0]
# end_date = df.iloc[-1,0]

# days = (end_date - start_date).days
# years = days / 365 if days > 0 else 0

# # 누적 수익률과 CAGR 계산 (예외처리 포함)
# total_return = df['return'].cumprod().iloc[-1]
# if years == 0:
#     cagr = 0
# else:
#     cagr = (total_return) ** (1 / years) - 1

# # 로그 수익률 계산
# df['log_return'] = np.log(df['return'])
# mean_return = df['log_return'].mean()
# std_return = df['log_return'].std()
# down_std = df[df['log_return'] < 0]['log_return'].std()

# # 무위험 수익률
# rf = 0.01

# # Sharpe & Sortino Ratio 계산 (예외처리 포함)
# if std_return == 0 or np.isnan(std_return):
#     sharpe_ratio = 0
# else:
#     sharpe_ratio = (mean_return - rf / 252) / std_return * np.sqrt(252)

# if down_std == 0 or np.isnan(down_std):
#     sortino_ratio = 0
# else:
#     sortino_ratio = (mean_return - rf / 252) / down_std * np.sqrt(252)

# # 출력
# print(df.head(10))
# print(f"Total Return: {total_return:.2%}")
# print(f"CAGR: {cagr:.2%}")
# print(f"Max Drawdown: {max_mdd:.2%}")
# print(f"Sharpe Ratio: {sharpe_ratio:.4f}")
# print(f"Sortino Ratio: {sortino_ratio:.4f}")
# print(f"Trading Count: {trading_count}")
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


print('*'*30)

### 리니어 변동성 돌파 전략 익일 시가 ###
df['range'] = range_model
df['target'] = df['open'] + df['range'].shift(1)
df['cond'] = df['high'] >= df['target']
cond = df['cond']

df['buy'] = df.loc[cond, 'target']
df['sell'] = df.loc[:,'open'].shift(-1)
df['sell'] = df.loc[cond, 'sell']

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



########### 리니어 buy_and_hold k와 tax는 변수로 ###################
tax = 0.000015
df['return'] = df['sell']/df['buy']
df['return'] = df['return'].fillna(1)

total_return = df['return'].cumprod().iloc[-1]

df['balance'] = 100 * df['return'].cumprod()
df['peak'] = df['balance'].cummax()
df['dd'] = (df['balance'] - df['peak']) / df['peak']
max_mdd = df['dd'].min()

print("*" * 20)
print("*" * 20)
print(f"Total Return: {total_return:.2%}")
print(f"Max Drawdown: {max_mdd:.2%}")





# def buy_and_hold_CAGR(df, cac):
#     buy = df.iloc[0,0]
#     sell = df.iloc[-1,3]
#     ret = (sell-(sell*tax))/(buy+(buy*tax))
#     BNH_CAGR = ret**(1/cac) - 1     
#     return BNH_CAGR


        
#     result=[]
    
#     for y in year:
#         dfv = df.loc[y]
#         dfv.loc[:,'MA'] = dfv.loc[:,'close'].rolling(window=period).mean()
        
#         signal = dfv['close'].shift(1) >= dfv['MA'].shift(1)
    
#         rangea = (dfv["high"] - dfv["low"]) * k
#         Target = dfv["open"] + rangea.shift(1)
    
#         cond = dfv['high'] >= Target
                
#         buy = Target[cond]
#         sell = dfv.loc[cond, 'close']
             
#         buy = buy[signal]
#         sell = sell[signal]
        
#         n = len(sell)
    
#         ret = ((sell-(sell*tax))/(buy+(buy*tax)))
#         a = ret.cumprod().iloc[-1]
#         b = buy_and_hold(dfv)
#         n = len(sell)
        
#         result.append([y, a, b, n])
        
#     return result

# ticker = input("Ticker?: ")

# tax = 0.000015

# data = []
# cac = 연수(df)

# for period in range(5,101,5):   
#     for k in range(1,11):
#         ret = 변동성돌파(df, k/10, period)[0]
#         trading = 변동성돌파(df, k/10, period)[1]
#         CAG = CAGR(ret, cac)
#         data.append([period, k/10, ret, CAG, trading])
   
# rdf = pd.DataFrame(data)
# rdf.columns = ["period", "k", "return", "CAGR", "trading"]

# rdf = rdf.sort_values("return")

# best_k = rdf.iloc[-1, 1]
# best_MA = rdf.iloc[-1, 0]

# BNH = buy_and_hold(df)
# BNH_CAGR = buy_and_hold_CAGR(df, cac)

# yr = 연도별수익률(df, best_k, best_MA)

# yret = pd.DataFrame(data=yr, columns=['year', 'return', 'buy & hold', 'trading'])
# yret = yret.set_index(keys='year')

# yret['return'] = yret['return']-1
# yret['buy & hold'] = yret['buy & hold']-1

# print("-"*20)
# print("MA : {}".format(rdf.iloc[-1, 0]))
# print("K : {}".format(rdf.iloc[-1, 1]))
# print("Return : {:.2%}".format(rdf.iloc[-1, 2]-1))
# print("투자횟수 :", rdf.iloc[-1, 4], "수수료 : {:.2%}".format(수수료), 
#       "슬리피지 : {:.2%}".format(슬리피지))
# print("단순 보유 후 홀딩 : {:.2%}".format(BNH-1))
# print("차이 {:.2%}".format((rdf.iloc[-1, 2]-1)-(BNH-1)))
# print("CAGR : {:.2%}".format(rdf.iloc[-1, 3]))
# print("Buy&Hold CAGR : {:.2%}".format(BNH_CAGR))
# print("-"*20)
# print("연도별 수익")

# for y, r, b, d, n in zip(yret.index, yret['return'], yret['buy & hold'], yret['return']-yret['buy & hold'], 
#                       yret['trading']):
#     print(f"{y}: 변동성돌파 수익률 {r:.2%}, 단순보유수익률 {b:.2%}, 차이 {d:.2%}, 투자횟수 {n}")




