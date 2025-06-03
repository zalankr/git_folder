import pandas as pd
import numpy as np
from datetime import datetime
import os
from openpyxl import load_workbook

# KODEX200 + KOSDAQ100 결합 + QT종목 시트에서 ETF별 금액 단리로 가져오기기
def xlsx_to_dataframe(sheet_Num): # XLSX 불러오기 함수
    result = pd.DataFrame()
    try:
        # file_path = f'C:/Users/GSR\Desktop/Python_project/git_folder/SECTOR_ETF/ETF_Result.xlsx'
        file_path = f'C:/Users/ilpus/PythonProjects/git_folder/SECTOR_ETF/ETF_Result.xlsx'
        df = pd.read_excel(file_path, sheet_name=sheet_Num)
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        return df
    except Exception as e:
        print(f"오류 발생: {e}")
        return None

# dataframe 조정
def df_adjust(df, sheet_Num):
    df.drop(columns=['balance', 'dd', 'volume'], inplace=True)
    df.rename(columns={'return': f'{sheet_Num}_return'}, inplace=True)
    return df

# dataframe 생성 클래스
class df_make:
    def __init__(self, sheet_Num):
        self.sheet_Num = sheet_Num
        self.df = xlsx_to_dataframe(sheet_Num)
        self.df = df_adjust(self.df, self.sheet_Num)
    def get_df(self):
        return self.df

# 엑셀 파일 불러오기+데이터프레임으로 변환
KODEX_200 = df_make(0)
KOSDAQ_100 = df_make(2)
KODEX_SC = df_make(4)
KODEX_BK = df_make(5)
KODEX_MO = df_make(6)

KODEX_200 = KODEX_200.get_df()
KOSDAQ_100 = KOSDAQ_100.get_df()
KODEX_SC = KODEX_SC.get_df()
KODEX_BK = KODEX_BK.get_df()
KODEX_MO = KODEX_MO.get_df()

# dataframe 병합
df = pd.merge(pd.merge(pd.merge(pd.merge(KODEX_200, KOSDAQ_100, on='date', how='inner'), KODEX_SC, on='date', how='inner'), 
                       KODEX_BK, on='date', how='inner'), KODEX_MO, on='date', how='inner')
df.dropna(inplace=True)
df['date'] = pd.to_datetime(df['date'], errors='coerce')

initial_200 = 50000000  # 5000만원
initial_100 = 25000000  # 2500만원
initial_OTHER = 25000000  # 2500만원
수수료 = 0.00015  # 수수료율

# 수익률 계산
df['0_profit'] = np.where(df['0_return'] == 1, df['0_return'], (df['0_return'] - 1) * initial_200 - (initial_200 * 수수료 * 2))
df['2_profit'] = np.where(df['2_return'] == 1, df['2_return'], (df['2_return'] - 1) * initial_100 - (initial_100 * 수수료 * 2))
df['4_profit'] = np.where(df['4_return'] == 1, df['4_return'], (df['4_return'] - 1) * initial_OTHER - (initial_OTHER * 수수료 * 2))
df['5_profit'] = np.where(df['5_return'] == 1, df['5_return'], (df['5_return'] - 1) * initial_OTHER - (initial_OTHER * 수수료 * 2))
df['6_profit'] = np.where(df['6_return'] == 1, df['6_return'], (df['6_return'] - 1) * initial_OTHER - (initial_OTHER * 수수료 * 2))

# 합산 수익
df['total_profit'] = df['0_profit'] + df['2_profit'] + df['4_profit'] + df['5_profit'] + df['6_profit']
df['cumulative_profit'] = df['total_profit'].cumsum() + (initial_200 + initial_100 + (initial_OTHER * 3))

# CAGR 계산
start_value = initial_200 + initial_100 + (initial_OTHER * 3)
end_value = df['cumulative_profit'].iloc[-1]
days = (df['date'].iloc[-1] - df['date'].iloc[0]).days
years = days / 365.0
CAGR = (end_value / start_value) ** (1 / years) - 1

# MDD 계산
cumulative = df['cumulative_profit']
rolling_max = cumulative.cummax()
drawdown = (cumulative - rolling_max) / rolling_max
MDD = drawdown.min()

# 결과 출력
print(f"CAGR: {CAGR:.4%}")
print(f"MDD: {MDD:.2%}")

print(df.head(5))
############################ GPT 영역 #############################