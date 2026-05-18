import pandas as pd
import numpy as np
from datetime import datetime
import os
from openpyxl import load_workbook
이격도 = 110 # 이격도 기준값

def xlsx_to_dataframe(file_name):
    try:
        file_path = f'C:/Users/GSR/Desktop/Python_project/git_folder/SECTOR_ETF/{file_name}'
        df = pd.read_excel(file_path)
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        return df
    except Exception as e:
        print(f"오류발생: {e}")
        return None

def Slipage(file_name):
    IndexETF = ['KODEX 200.xlsx', 'KODEX 코스닥140.xlsx', 'KOSDAQ 100.xlsx']
    if file_name in IndexETF:
        return 0.0002
    else:
        return 0.0005

def Investment_Period(df):
    start_date = df.iloc[0, 0]
    end_date = df.iloc[-1, 0]
    days = (end_date - start_date).days
    years = days / 365 if days > 0 else 0
    return years

def MDD(df):
    df['balance'] = 100 * df['return'].cumprod()
    df['peak'] = df['balance'].cummax()
    df['dd'] = (df['balance'] - df['peak']) / df['peak']
    return df

def Return_CAGR(df, years):
    total_return = df['return'].cumprod().iloc[-1]
    cagr = (total_return) ** (1 / years) - 1 if years > 0 else 0
    return total_return, cagr

def Sharpe_SortinoRatio(df):
    df['log_return'] = np.log(df['return'])
    mean_return = df['log_return'].mean()
    std_return = df['log_return'].std()
    down_std = df[df['log_return'] < 0]['log_return'].std()
    rf = 0.01

    sharpe_ratio = (mean_return - rf / 252) / std_return * np.sqrt(252) if std_return != 0 and not np.isnan(std_return) else 0
    sortino_ratio = (mean_return - rf / 252) / down_std * np.sqrt(252) if down_std != 0 and not np.isnan(down_std) else 0
    return df, sharpe_ratio, sortino_ratio

def range_list(df):
    rm1 = [(df['high'] - df['low']), "고가-저가"]
    rm2 = [(df['high'] - df['open']), "고가-시가"]
    rm3 = [(df['open'] - df['low']), "시가-저가"]
    return [rm1, rm2, rm3]

class vol_breakout_open:
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
        self.df['disparity'] = (self.df['close'] / self.df['close'].rolling(window=20).mean()) * 100
        self.df['cond'] = (self.df['high'] >= self.df['target']) & (self.df['disparity'] <= 이격도)

        cond = self.df['cond']
        self.df['buy'] = self.df.loc[cond, 'target']
        self.df['open-1'] = self.df['open'].shift(-1)
        self.df['sell'] = self.df.loc[cond, 'open-1']

        self.trading = self.df.loc[cond, 'close']
        self.trading_count = len(self.trading)

        self.df['return'] = (self.df['sell'] - self.df['sell'] * (self.tax + self.슬리피지)) / (self.df['buy'] + self.df['buy'] * self.tax)
        self.df['return'] = self.df['return'].fillna(1)

        self.df = MDD(self.df)
        self.mdd = self.df['dd'].min()
        self.years = Investment_Period(self.df)
        self.total_return, self.cagr = Return_CAGR(self.df, self.years)
        self.df, self.sharpe_ratio, self.sortino_ratio = Sharpe_SortinoRatio(self.df)

        data = [self.model, self.range_modelstr, self.k, self.total_return, self.cagr, self.mdd,
                self.sharpe_ratio, self.sortino_ratio, self.trading_count, self.years]
        return pd.DataFrame(data=[data], columns=['Model', 'Range', 'k', 'Total Return', 'CAGR', 'MDD',
                                                  'Sharpe Ratio', 'Sortino Ratio', 'Trading Count', 'Investment Period'])

class vol_breakout_close:
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
        self.df['disparity'] = (self.df['close'] / self.df['close'].rolling(window=20).mean()) * 100
        self.df['cond'] = (self.df['high'] >= self.df['target']) & (self.df['disparity'] <= 이격도)

        cond = self.df['cond']
        self.df['buy'] = self.df.loc[cond, 'target']
        self.df['sell'] = self.df.loc[cond, 'close']

        self.trading = self.df.loc[cond, 'close']
        self.trading_count = len(self.trading)

        self.df['return'] = (self.df['sell'] - self.df['sell'] * (self.tax + self.슬리피지)) / (self.df['buy'] + self.df['buy'] * self.tax)
        self.df['return'] = self.df['return'].fillna(1)

        self.df = MDD(self.df)
        self.mdd = self.df['dd'].min()
        self.years = Investment_Period(self.df)
        self.total_return, self.cagr = Return_CAGR(self.df, self.years)
        self.df, self.sharpe_ratio, self.sortino_ratio = Sharpe_SortinoRatio(self.df)

        data = [self.model, self.range_modelstr, self.k, self.total_return, self.cagr, self.mdd,
                self.sharpe_ratio, self.sortino_ratio, self.trading_count, self.years]
        return pd.DataFrame(data=[data], columns=['Model', 'Range', 'k', 'Total Return', 'CAGR', 'MDD',
                                                  'Sharpe Ratio', 'Sortino Ratio', 'Trading Count', 'Investment Period'])

class buy_and_hold:
    def __init__(self, df):
        self.df = df
        self.tax = 0
        self.model = 'buy_and_hold'

    def back_test(self):
        self.df['buy'] = self.df['close'].shift(1)
        self.df['sell'] = self.df['close']
        self.df['return'] = self.df['sell'] / self.df['buy']
        self.df['return'] = self.df['return'].fillna(1)

        self.df = MDD(self.df)
        self.mdd = self.df['dd'].min()
        self.years = Investment_Period(self.df)
        self.total_return, self.cagr = Return_CAGR(self.df, self.years)
        self.df, self.sharpe_ratio, self.sortino_ratio = Sharpe_SortinoRatio(self.df)

        data = [self.model, 'NA', 'NA', self.total_return, self.cagr, self.mdd,
                self.sharpe_ratio, self.sortino_ratio, 'NA', self.years]
        return pd.DataFrame(data=[data], columns=['Model', 'Range', 'k', 'Total Return', 'CAGR', 'MDD',
                                                  'Sharpe Ratio', 'Sortino Ratio', 'Trading Count', 'Investment Period'])

class Save_Result:
    def __init__(self, file_name, df):
        self.file_name = file_name
        self.df = df

    def save_to_excel(self, result):
        save_file_name = '변동성돌파이격도Result.xlsx'
        sheet_name = f'{self.file_name}'
        save_path = os.path.join(save_dir, save_file_name)

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
        self.tax = 0.00015
        self.k = 0.1
        self.rm_list = range_list(self.df)

    def run(self):
        print('*' * 40)
        print(f"ETF: {self.file_name[:-5]}")
        print('*' * 40)

        result = buy_and_hold(self.df).back_test()

        for i in range(3):
            range_model = self.rm_list[i][0]
            range_modelstr = self.rm_list[i][1]
            for j in range(9):
                k = 0.1 + (j * 0.1)
                result = pd.concat([
                    result,
                    vol_breakout_open(self.df, self.tax, self.slipage, k, range_model, range_modelstr).back_test(),
                    vol_breakout_close(self.df, self.tax, self.slipage, k, range_model, range_modelstr).back_test()
                ])

        print(result.head(5))
        Save_Result(self.file_name, self.df).save_to_excel(result)
        return result

file_name = 'KODEX 반도체.xlsx'
save_dir = 'C:/Users/GSR/Desktop/Python_project/git_folder/SECTOR_ETF'
# KODEX 200.xlsx #4000 # KOSDAQ 100.xlsx #2000 # KODEX 코스닥150.xlsx
# KODEX 2차전지산업.xlsx # KODEX 반도체.xlsx # KODEX 은행.xlsx# KODEX 자동차.xlsx 
# PLUS K방산.xlsx# SOL 조선TOP3플러스.xlsx
# TIGER 200 IT.xlsx # TIGER 200 중공업.xlsx # TIGER 리츠부동산인프라.xlsx # TIGER 헬스케어.xlsx # TIGER 화장품.xlsx
# save_dir = 'C:/Users/ilpus/PythonProjects/git_folder/SECTOR_ETF'

finrun = run_back_test(file_name)
finrun.run()
