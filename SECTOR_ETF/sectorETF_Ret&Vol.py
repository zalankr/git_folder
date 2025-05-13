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

def ETF_char(file_name): 
    # ETF별 특성
    ETF_char_dict = {
        'KODEX 200.xlsx': ['KODEX 200', 0.4, df['high']-df['low'], 0.000215],
        'KODEX 코스닥150.xlsx': ['KODEX 코스닥150', 0.4, df['high']-df['low'], 0.000215],
        'KOSDAQ 100.xlsx': ['KOSDAQ 100', 0.4, df['high']-df['low'], 0.000215],
        'KODEX 2차전지산업.xlsx': ['KODEX 2차전지산업', 0.6, df['high']-df['low'], 0.000515],
        'KODEX 반도체.xlsx': ['KODEX 반도체', 0.1, df['high']-df['low'], 0.000515],
        'KODEX 은행.xlsx': ['KODEX 은행', 0.1, df['high']-df['low'], 0.000515],
        'KODEX 자동차.xlsx': ['KODEX 자동차', 0.1, df['high']-df['low'], 0.000515],
        'PLUS K방산.xlsx': ['PLUS K방산', 0.5, df['high']-df['open'], 0.000515],
        'SOL 조선TOP3플러스.xlsx': ['SOL 조선TOP3플러스', 0.1, df['high']-df['low'], 0.000515],
        'TIGER 200 IT.xlsx': ['TIGER 200 IT', 0.3, df['high']-df['low'], 0.000515],
        'TIGER 200 중공업.xlsx': ['TIGER 200 중공업', 0.1, df['high']-df['low'], 0.000515],
        'TIGER 리츠부동산인프라.xlsx': ['TIGER 리츠부동산인프라', 0.4, df['high']-df['low'], 0.000515],
        'TIGER 헬스케어.xlsx': ['TIGER 헬스케어', 0.4, df['high']-df['low'], 0.000515],
        'TIGER 화장품.xlsx': ['TIGER 화장품', 0.3, df['high']-df['low'], 0.000515]
    }
    for ETF in ETF_char_dict:
        if file_name in ETF:
            etf_char = ETF_char_dict[ETF]
      
    return etf_char

class Back_test: # 백테스트 클래스
    def __init__(self, df, etf_K, range_model, slipage):
        self.df = df
        self.k = etf_K
        self.range_model = range_model
        self.slipage = slipage
        self.k = etf_K

    def back_test(self):
        self.df['range'] = self.range_model * self.k
        self.df['target'] = self.df['open'] + self.df['range'].shift(1)
        self.df['cond'] = self.df['high'] >= self.df['target']
        cond = self.df['cond']

        self.df['buy'] = self.df.loc[cond, 'target']
        self.df['open-1'] = self.df['open'].shift(-1)
        self.df['sell'] = self.df.loc[cond, 'open-1']

        # 수익률 계산
        self.df['return'] = (self.df['sell'] - (self.df['sell'] * 0.000015)) / (self.df['buy'] + (self.df['buy'] * self.slipage))
        self.df['return'] = self.df['return'].fillna(1)

        # MDD 계산
        self.df = MDD(self.df)
        self.mdd = self.df['dd'].min()

        self.df = self.df.drop(columns=['open', 'high', 'low', 'close', 'target', 'range', 'peak', 'cond', 'buy', 'sell', 'open-1'])

        result1 = self.df
        return result1

class Save_Result: # 결과 저장 클래스
    def __init__(self, file_name, result, Period):
        self.file_name = file_name
        self.df = result
        self.Period = Period

    def save_to_excel(self, result):
        save_file_name = 'ETF_Result.xlsx'
        sheet_name = f'{self.file_name} ({self.Period:.2f}년)'
        save_path = os.path.join(save_dir, save_file_name)

        # 파일이 이미 존재하면 시트를 추가, 아니면 새로 생성
        if os.path.exists(save_path):
            with pd.ExcelWriter(save_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                result.to_excel(writer, index=False, sheet_name=sheet_name)
        else:
            with pd.ExcelWriter(save_path, engine='openpyxl') as writer:
                result.to_excel(writer, index=False, sheet_name=sheet_name)

        print(f"엑셀 파일이 저장되었습니다: {save_path}")

file_name = 'KOSDAQ 100.xlsx' # 직전 1개월간 거래대급 상위 국내섹터별 ETF 4개 #1,2위 2000, 3,4위 1000
# KODEX 200.xlsx #4000 # KODEX 코스닥150.xlsx #2000 # KOSDAQ 100.xlsx
# KODEX 2차전지산업.xlsx # KODEX 반도체.xlsx # KODEX 은행.xlsx# KODEX 자동차.xlsx 
# PLUS K방산.xlsx # SOL 조선TOP3플러스.xlsx
# TIGER 200 IT.xlsx # TIGER 200 중공업.xlsx # TIGER 리츠부동산인프라.xlsx # TIGER 헬스케어.xlsx # TIGER 화장품.xlsx

df = xlsx_to_dataframe(file_name)
etf_char = ETF_char(file_name)
etf_name = etf_char[0]
etf_K = etf_char[1] # K값
etf_range = etf_char[2] # 변동성 모델
etf_slipage = etf_char[3] # 슬리피지
Period = Investment_Period(df)

t1 = Back_test(df, etf_K, etf_range, etf_slipage)
result = t1.back_test()
print(result.head(5))

save_dir = 'C:/Users/GSR/Desktop/Python_project/git_folder/SECTOR_ETF'
# save_dir = 'C:/Users/ilpus/PythonProjects/git_folder/SECTOR_ETF'
M_result = Save_Result(file_name, result, Period)
M_result.save_to_excel(result)
######################################################################################################################

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