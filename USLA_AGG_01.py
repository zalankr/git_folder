import yfinance as yf
import pandas as pd
import time
import calendar

# 날짜 인풋 받기
year = '2025' ##################
month = input('month?:')
mon = int(month)

if mon < 10 :
    monstr = f'0{mon}'    
else :
    monstr = str(mon)


# 전월 파일명 구현하기
B1month = mon - 1

if B1month < 1 :
    B1year = str(int(year)-1)
    B1month = '12'
    
elif B1month < 10 and B1month >= 1 :
    B1month = f'0{B1month}'
    B1year = year

else:
    B1year = year

# 티커
All_ticker = ['UPRO', 'TQQQ', 'EDC', 'TMF', 'TMV', 'CASH'] # 예수금 포함

# 호출 날짜
B4month = mon - 4

if B4month <= 0 :
    B4month = str(12+B4month)
    B4year = str(int(year)-1)
else :
    B4month = '0'+str(int(month)-4)
    B4year = year

endd = calendar.monthrange(int(B1year), int(B1month))
endday = str(endd[1])

end = f'{B1year}-{B1month}-{endday}'
start = f'{B4year}-{B4month}-01'

# AGG 데이터
AGG = yf.download('AGG', start=start, end=end, auto_adjust=True, interval='1mo', progress=True, 
                  multi_level_index=False)


AGG.drop(['Open','High','Low','Volume'], axis=1, inplace=True)
AGG.sort_index(axis=0, ascending=False, inplace=True)

# AGG 0열(라벨) 날짜형식 깨끗하게 정리
date1 = list()
date2 = AGG.index

for i in date2 :
    i = i.strftime('%Y-%m-%d')
    date1.append(i)
    
AGG = AGG.set_axis(labels=[date1[0], date1[1], date1[2], date1[3]], axis=0)

# Regime Signal 확인
Regime_Signal = round(AGG.iloc[0, 0] - AGG['Close'].mean(), 2)

AGG_add1 = pd.DataFrame(data=[AGG['Close'].mean()], index=['AGG_4mo_avg'], columns=['Close'])
AGG_add2 = pd.DataFrame(data=[Regime_Signal], index=['Regime_Signal'], columns=['Close'])

AGG = pd.concat([AGG, AGG_add1])
AGG = pd.concat([AGG, AGG_add2])

print(AGG)