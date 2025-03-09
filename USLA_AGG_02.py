import yfinance as yf
import pandas as pd
import time
import calendar

# 데이터 기간 설정
start = '2015-06-01'
end = '2025-02-28'

# AGG 데이터
AGG = yf.download('AGG', start=start, end=end, auto_adjust=True, interval='1mo', progress=True, 
                  multi_level_index=False)

AGG.drop(['Open','High','Low','Volume'], axis=1, inplace=True)

# Average
AGG.loc[:,'MA'] = AGG.loc[:,'Close'].rolling(window=4).mean()
AGG.loc[:,'Regime Signal'] = AGG.loc[:,'Close'] >= AGG.loc[:,'MA']

print(AGG)
