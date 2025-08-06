import yfinance as yf
import pandas as pd
import openpyxl

# 데이터 기간 설정
start = '2005-01-01'
end = '2025-07-31'

def save_dataframe_to_excel(df, filename):
    try:
        df.to_excel(filename, index=True)  # 인덱스 제외하고 저장
        print(f"DataFrame이 성공적으로 '{filename}' 파일로 저장되었습니다.")
    except Exception as e:
        print(f"파일 저장 중 오류 발생: {e}")


# AGG 데이터
AGG = yf.download('AGG', start=start, end=end, auto_adjust=True, interval='1mo', progress=True, 
                  multi_level_index=False)

AGG.drop(['Open','High','Low','Volume'], axis=1, inplace=True)

# Average
AGG.loc[:,'MA'] = AGG.loc[:,'Close'].rolling(window=4).mean()
AGG.loc[:,'Regime Signal'] = AGG.loc[:,'Close'].shift(1) >= AGG.loc[:,'MA'].shift(1)

# Excel 파일로 저장
AGG.sort_index(axis=0, ascending=False, inplace=True)
save_dataframe_to_excel(AGG, 'AGG_ajM.xlsx')

