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
df1 = df_make(0)
df2 = df_make(-1)
df3 = df_make(3)
df4 = df_make(4)
df5 = df_make(5)

df1 = df1.get_df()
df2 = df2.get_df()
df3 = df3.get_df()
df4 = df4.get_df()
df5 = df5.get_df()

# dataframe 병합
df = pd.merge(pd.merge(pd.merge(pd.merge(df1, df2, on='date', how='inner'), df3, on='date', how='inner'), 
                       df4, on='date', how='inner'), df5, on='date', how='inner')
df.dropna(inplace=True)
df['date'] = pd.to_datetime(df['date'], errors='coerce')

initial_kodex = 40000000  # 4000만원
initial_kosdaq = 30000000  # 3000만원
initial_sector = 20000000  # 2000만원

df['0_profit'] = (df['0_return'] - 1) * initial_kodex
df['-1_profit'] = (df['-1_return'] - 1) * initial_kosdaq
df['3_profit'] = (df['3_return'] - 1) * initial_sector
df['4_profit'] = (df['4_return'] - 1) * initial_sector
df['5_profit'] = (df['5_return'] - 1) * initial_sector

# 합산 수익
df['total_profit'] = df['0_profit'] + df['-1_profit'] + df['3_profit'] + df['4_profit'] + df['5_profit']
df['cumulative_profit'] = df['total_profit'].cumsum() + (initial_kodex + initial_kosdaq + (initial_sector * 3))

# CAGR 계산
start_value = initial_kodex + initial_kosdaq + (initial_sector * 3)
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



print(df.head(10))
############################ GPT 영역 #############################