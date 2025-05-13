import pandas as pd
import numpy as np
from datetime import datetime
import os
from openpyxl import load_workbook

def xlsx_to_dataframe(file_name): # XLSX 불러오기 함수
    try:
        file_path = f'C:/Users/GSR\Desktop/Python_project/git_folder/SECTOR_ETF/{file_name}'
        # file_path = f'C:/Users/ilpus/PythonProjects/git_folder/SECTOR_ETF/{file_name}'
        df = pd.read_excel(file_path)
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        return df
    except Exception as e:
        print(f"오류 발생: {e}")
        return None

def Slipage(file_name): # 슬리피지 계산 함수
    IndexETF = ['KODEX 200.xlsx', 'KODEX 코스닥150.xlsx', 'KOSDAQ 100.xlsx']
    if file_name in IndexETF:
        슬리피지 = 0.0002 # ETF별 지수ETF = 0.02%
    else:
        슬리피지 = 0.0005 # ETF별 개별종목 = 0.05%
    return 슬리피지

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

def range_list(df):
    rm1 = [(df['high'] - df['low']), "고가-저가"]
    rm2 = [(df['high'] - df['open']), "고가-시가"]
    rm3 = [(df['open'] - df['low']), "시가-저가"]
    rm_list = [rm1, rm2, rm3]
    return rm_list

class vol_breakout_open: ## 변동성 돌파 전략 익일시가 청산 CLASS
    def __init__(self, df, tax, 슬리피지, k, range_model, range_modelstr):
        self.df = df
        self.tax = tax
        self.슬리피지 = 슬리피지
        self.k = k
        self.range_model = range_model * k
        self.range_modelstr = range_modelstr
        self.model = '익일시가'
    
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

        data = [self.model, self.range_modelstr, self.k, self.total_return, self.cagr, self.mdd, self.sharpe_ratio, self.sortino_ratio, self.trading_count, self.years]
        result1 = pd.DataFrame(data = [data], columns = ['Model', 'Range', 'k', 'Total Return', 'CAGR', 'MDD', 'Sharpe Ratio', 'Sortino Ratio', 'Trading Count', 'Investment Period'])
        return result1

class vol_breakout_close: ## 변동성 돌파 전략 당일종가 청산 CLASS
    def __init__(self, df, tax, 슬리피지, k, range_model, range_modelstr):
        self.df = df
        self.tax = tax
        self.슬리피지 = 슬리피지
        self.k = k
        self.range_model = range_model * k
        self.range_modelstr = range_modelstr
        self.model = '당일종가'
    
    def back_test(self):
        self.df['range'] = self.range_model
        self.df['target'] = self.df['open'] + self.df['range'].shift(1)
        self.df['cond'] = self.df['high'] >= self.df['target']
        cond = self.df['cond']
        
        self.df['buy'] = self.df.loc[cond, 'target']
        self.df['sell'] = self.df.loc[cond, 'close']

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

        data = [self.model, self.range_modelstr, self.k, self.total_return, self.cagr, self.mdd, self.sharpe_ratio, self.sortino_ratio, self.trading_count, self.years]
        result2 = pd.DataFrame(data = [data], columns = ['Model', 'Range', 'k', 'Total Return', 'CAGR', 'MDD', 'Sharpe Ratio', 'Sortino Ratio', 'Trading Count', 'Investment Period'])
        return result2

class buy_and_hold: ## buy_and_hold CLASS
    def __init__(self, df):
        self.df = df
        self.tax = 0
        self.model = 'buy_and_hold'
    
    def back_test(self):
        self.df['buy'] = self.df['close'].shift(1)
        self.df['sell'] = self.df['close']

        self.df['return'] = self.df['sell']/self.df['buy']
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
       
        data = [self.model, 'NA', 'NA', self.total_return, self.cagr, self.mdd, self.sharpe_ratio, self.sortino_ratio, 'NA', self.years]
        result = pd.DataFrame(data = [data], columns = ['Model', 'Range', 'k', 'Total Return', 'CAGR', 'MDD', 'Sharpe Ratio', 'Sortino Ratio', 'Trading Count', 'Investment Period'])
        return result

class Save_Result: # 결과 저장 클래스
    def __init__(self, file_name, df):
        self.file_name = file_name
        self.df = df

    def save_to_excel(self, result):
        save_file_name = '변동성돌파Result.xlsx'
        sheet_name = f'{self.file_name}'
        save_path = os.path.join(save_dir, save_file_name)

        # 파일이 이미 존재하면 시트를 추가, 아니면 새로 생성
        if os.path.exists(save_path):
            with pd.ExcelWriter(save_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                result.to_excel(writer, index=False, sheet_name=sheet_name)
        else:
            with pd.ExcelWriter(save_path, engine='openpyxl') as writer:
                result.to_excel(writer, index=False, sheet_name=sheet_name)

        print(f"엑셀 파일이 저장되었습니다: {save_path}")

class run_back_test:
    def __init__(self, file_name):
        self.file_name = file_name
        self.df = xlsx_to_dataframe(file_name)
        self.slipage = Slipage(file_name)
        self.tax = 0.000015 # 세금
        self.k = 0.1 # k값
        self.rm_list = range_list(self.df)

    def run(self):
        print('*'*40)
        print(f"ETF: {file_name[:-5]}")
        print('*'*40)

        t3 = buy_and_hold(self.df)
        result = t3.back_test()

        for i in range(3):
            range_model = self.rm_list[i][0]
            range_modelstr = self.rm_list[i][1]
            for j in range(9):
                k = 0.1 + (j * 0.1)
                
                t1 = vol_breakout_open(self.df, self.tax, self.slipage, k, range_model, range_modelstr)
                result = pd.concat([result, t1.back_test()])

                t2 = vol_breakout_close(self.df, self.tax, self.slipage, k, range_model, range_modelstr)
                result = pd.concat([result, t2.back_test()])

        print(result.head(5))
        M_result = Save_Result(file_name, self.df)
        M_result.save_to_excel(result)

        return result

# 변수설정 #
file_name = 'KOSDAQ 100.xlsx' # 직전 1개월간 거래대급 상위 국내섹터별 ETF 4개 #1,2위 2000, 3,4위 1000
save_dir = 'C:/Users/GSR/Desktop/Python_project/git_folder/SECTOR_ETF'
# KODEX 200.xlsx #4000 # KODEX 코스닥150.xlsx # KOSDAQ 100.xlsx #2000
# KODEX 2차전지산업.xlsx # KODEX 반도체.xlsx # KODEX 은행.xlsx# KODEX 자동차.xlsx 
# PLUS K방산.xlsx# SOL 조선TOP3플러스.xlsx
# TIGER 200 IT.xlsx # TIGER 200 중공업.xlsx # TIGER 리츠부동산인프라.xlsx # TIGER 헬스케어.xlsx # TIGER 화장품.xlsx
# save_dir = 'C:/Users/ilpus/PythonProjects/git_folder/SECTOR_ETF'

finrun = run_back_test(file_name)
finrun.run()

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