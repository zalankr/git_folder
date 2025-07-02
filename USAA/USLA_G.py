import yfinance as yf
import pandas as pd
import time
import gspread
import riskfolio as rp
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

# Google spread account 연결 및 오픈 ########################
gc = gspread.service_account("C:/Users/ilpus/PythonProjects/US_Asset_Allocation/service_account.json")
# gc = gspread.service_account("C:/Users/ilpus/PythonProjects/US_Asset_Allocation/service_account.json")
url = 'https://docs.google.com/spreadsheets/d/19KCxCqF32emisAEO1zT0XEDgD_Ye4n2-R3-0jzbZ-zs/edit?gid=1963431369#gid=1963431369'
# 기 작성 URL기입
# 기 작성된 연도별 USLA gspread URL 기입
sh = gc.open_by_url(url) # 스프레드시트 url주소로 연결
     
# 워크시트 가져오기
worksheet0 = sh.get_worksheet(mon-1)


# 티커
All_ticker = ['UPRO', 'TQQQ', 'EDC', 'TMF', 'TMV', 'CASH'] # 예수금 포함


col = ['전월수량', '전월주가', '전월평가금']
dic = worksheet0.get("Q2:S7")

TR = pd.DataFrame(data=dic, index=None, dtype=float, columns=col, copy=True)
TR.insert(loc=0, column='티커', value=All_ticker)


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
AGG = yf.download(tickers='AGG', start=start, end=end, auto_adjust=True, interval='1mo', progress=True, 
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

time.sleep(0.1)

# 포트폴리오 가격 불러오기
ticker = ['UPRO', 'TQQQ', 'EDC', 'TMF', 'TMV'] # 모멘텀 티커
 
B12year = str(int(B1year)-1)

end = f'{B1year}-{B1month}-{endday}'
start = f'{B12year}-{B1month}-01'

SignalPort = yf.download(tickers=ticker, start=start, end=end, auto_adjust=False, interval='1mo', progress=True, 
                         multi_level_index=False)['Close']
# 수정주가보단 일반주가가 포폴비쥬얼라이즈에 더 근사값['Adj Close'] 
time.sleep(0.1)

SignalPort.sort_index(axis=0, ascending=False, inplace=True)

date1 = list()
date2 = SignalPort.index

for i in date2 :
    i = i.strftime('%Y-%m-%d')
    date1.append(i)
    
SignalPort =SignalPort.set_axis(labels=[date1[0], date1[1], date1[2], date1[3], date1[4], 
                                        date1[5], date1[6], date1[7], date1[8], date1[9], 
                                        date1[10], date1[11], date1[12]], axis=0)


# 포트폴리오 모멘텀 점수
momentum =[]

for i in ticker :
    cur = SignalPort.loc[date1[0], i]
    mo1 = SignalPort.loc[date1[1], i]
    mo3 = SignalPort.loc[date1[3], i]
    mo6 = SignalPort.loc[date1[6], i]
    mo9 = SignalPort.loc[date1[9], i]
    mo12 = SignalPort.loc[date1[12], i]
    score = ((cur/mo1-1)*30)+((cur/mo3-1)*25)+((cur/mo6-1)*20)+((cur/mo9-1)*15)+((cur/mo12-1)*10)
    momentum.append([i, score.round(2)])

momentum = pd.DataFrame(momentum, columns=['ticker', 'momentum'])

momentum.loc[:, 'rank'] = momentum.loc[:, 'momentum'].rank(ascending=False, 
                                                       method='max', 
                                                       pct=False, 
                                                       na_option='bottom')

momentum = momentum.sort_values(by=['rank'], ascending=True, ignore_index=False, inplace=False)


# 타겟 티커 확정
Target_ticker = [momentum.iloc[0, 0], momentum.iloc[1, 0]]


#기본 MVP모델 Weight 해찾기 riskfolio Portfolio 설정
Hist = yf.download(tickers=Target_ticker, period='3mo', auto_adjust=True, interval='1d', 
                   progress=False)['Close']
Hist.sort_index(axis=0, ascending=False, inplace=True)

Hist = Hist.iloc[: 45]
Ret = Hist.pct_change(-1).dropna()
Ret = Ret.round(4)

port = rp.Portfolio(returns=Ret)
method_mu = 'hist'
method_cov = 'hist'
port.assets_stats(method_mu=method_mu, method_cov=method_cov)

model = 'Classic'
rm = 'MV'
obj = 'MinRisk'
hist = True
rf = 0
l = 0


# 유니버스 데이터베이스
ticker_class = []
for i in Target_ticker :
    if i == 'UPRO' or i == 'TQQQ' or i == 'EDC' :
        ticker_class.append('stock')
    else : 
        ticker_class.append('bond')


asset_classes = {
    'Asset' : [Target_ticker[0], Target_ticker[1]],
    'Class' : [ticker_class[0], ticker_class[1]]}

asset_classes = pd.DataFrame(asset_classes)


# 제약조건 설정 데이터베이스
constraints = {'Disabled' : [False, False],
               'Type' : ['All Assets', 'All Assets'],
               'Set' : ['', ''],
               'Position' : ['', ''],
               'Sign' : ['>=', '<='],
               'Weight' : [0.2, 0.8],
               'Type Relative' : ['', ''],
               'Relative Set' : ['', ''],
               'Relative' : ['', ''],
               'Factor' : ['', '']}

constraints = pd.DataFrame(constraints)


# 제약조건 적용 MVP모델 Weight 해찾기
A, B = rp.assets_constraints(constraints, asset_classes)

port.ainequality = A
port.binequality = B

w = port.optimization(model=model, rm=rm, obj=obj, rf=rf, l=l, hist=hist)


# 최종 당월 투자 종목 및 비중 프린트
print('----------------------------------------------------------------------')
print(momentum)
print('----------------------------------------------------------------------')

ax = rp.plot_bar(w=w, title='Portfolio', kind='h', ax=None)

I1 = w.index[0]
I2 = w.index[1]

if Regime_Signal < 0 :
    print('Regime Signal :', Regime_Signal,'> RISK')
    print('Asset :', 'CASH')   
else :
    print('Regime Signal :', Regime_Signal,'> Stable')
    print('Asset :', I1, '> Weight :', round(w.loc[I1, 'weights'], 4))
    print('Asset :', I2, '> Weight :', round(w.loc[I2, 'weights'], 4))
    
print('----------------------------------------------------------------------')
time.sleep(0.1)


# 현재가 및 현재평가금액 구하기 확인(궁극적으로는 현재가는 한투API 현재가 불러오기로 대체)
TR_ticker = ['UPRO', 'TQQQ', 'EDC', 'TMF', 'TMV'] # 트레이딩 티커
price = []
 
for i in TR_ticker :    
    j = yf.download(tickers=i, period='1d', interval='1d', progress=False, auto_adjust=False,
                    multi_level_index=False)['Close']
    price.append(round(j.iloc[0],4))
price.append(1)

TR['현재가'] = price

tax = 0.0009
TR.insert(loc=5, column='현재평가금', value=(TR.전월수량*TR.현재가)-(TR.전월수량*TR.현재가*tax))
TR.iat[5, 5] = TR.iat[5, 3]

# 월수익률 구하기
TR.insert(loc=6, column='월수익률', value=round(TR.현재평가금/TR.전월평가금-1, 4))
TR.iat[5, 6] = 0

################################

# 비중 열 삽입 하기
V1 = w.values[0]
V2 = w.values[1]

V1 = round(float(V1[0])*0.99, 4)
V2 = round(float(V2[0])*0.99, 4)

Weight = []

if Regime_Signal >= 0 :
    for i in ticker :
        if i != I1 and i != I2 :
            Weight.append(float(0))            
        elif i == I1 :
            Weight.append(V1)
        elif i == I2 :
            Weight.append(V2)
    Weight.append(float(0.01))
else :
    Weight = [float(0), float(0), float(0), float(0), float(0), float(1)]
        
TR['투입비중'] = Weight


# 투입금액 구하기
PreSum = TR['현재평가금'].sum(axis=0)
TR.insert(loc=8, column='투입금액', value=TR.투입비중*PreSum)


# 목표량 구하기
TR.insert(loc=9, column='목표량', value=TR.투입금액/TR.현재가)
TR.iat[5, 9] = TR.iat[5, 8]


# 매도항목 구하기
sell =[]
for k in range(6) :
    l = TR.iat[k, 1] - TR.iat[k, 9]
    if l > 0 :
        sell.append(l)
    else :
        sell.append(0)

TR['매도량'] = sell
TR['매도가'] = price
TR.insert(loc=12, column='매도금액', value=round((TR.매도량*TR.매도가)-(TR.매도량*TR.매도가*tax), 4))
TR.iat[5, 12] = TR.iat[5, 10]


# 매수항목 구하기
buy =[]
for m in range(6) :
    n = TR.iat[m, 9] - TR.iat[m, 1]
    if n > 0 :
        buy.append(n)
    else :
        buy.append(0)

TR['매수량'] = buy
TR['매수가'] = price
TR.insert(loc=15, column='매수금액', value=round((TR.매수량*TR.매수가)+(TR.매수량*TR.매수가*tax), 4))
TR.iat[5, 15] = TR.iat[5, 13]


# 최종항목 구하기
TR.insert(loc=16, column='최종수량', value=TR.전월수량+TR.매수량-TR.매도량)
TR['최종주가'] = price
TR.insert(loc=18, column='최종평가금', value=(TR.최종수량*TR.최종주가)-(TR.최종수량*TR.최종주가*tax))
TR.iat[5, 18] = TR.iat[5, 16]


# 하단 합계행 추가
d1 = TR['전월평가금'].sum(axis=0)
d2 = TR['현재평가금'].sum(axis=0)

d4 = TR['투입비중'].sum(axis=0)
d5 = TR['투입금액'].sum(axis=0)
d6 = TR['매도금액'].sum(axis=0)
d7 = TR['매수금액'].sum(axis=0)
d8 = TR['최종평가금'].sum(axis=0)
d9 = float(d2) / float(d1) - 1

PF = pd.DataFrame(data=[['Portfolio', d1, d2, d9, d4, d5, d6, d7, d8]], 
                  columns=['티커', '전월평가금', '현재평가금', '월수익률', '투입비중', '투입금액', 
                           '매도금액', '매수금액', '최종평가금'])
TR = pd.concat([TR, PF], axis=0, ignore_index=True)


## 하단 구글식행 추가
# 전월 파일 읽어오기
# ticker0 = ticker
# ticker0.append('CASH')

col = ['전월수량', '전월주가', '전월평가금']
dic = worksheet0.get("Q2:S7")
dic2 = float(worksheet0.acell('S8').value)

TR0 = pd.DataFrame(data=dic, index=None, dtype=float, columns=col, copy=True)
TR0.insert(loc=0, column='티커', value=All_ticker)

df1 = pd.DataFrame(data=[['Portfolio', dic2]], columns=['티커','전월평가금'])
TR0 = pd.concat([TR0, df1], axis=0, ignore_index=True)


price = []
balance = []
ret = []
investmoney = []
Weight2 = Weight
target = []
sell = []
sepr = []
semo = []
buy = []
bupr = []
bumo = []
laam = []
lapr = []
lamo = []

for i in range(9, 16) :
    price.append(f'=GOOGLEFINANCE($A{i})')
    balance.append(f'=(B{i}*E{i})-(B{i}*E{i}*0.09%)')
    ret.append(f'=iferror((F{i}/D{i})-1)')
    investmoney.append(f'=F15*H{i}')
    target.append(f'=I{i}/E{i}')
    sell.append(f'=IF(B{i}-J{i}>0, B{i}-J{i}, 0)')
    sepr.append(f'=E{i}')
    semo.append(f'=(K{i}*L{i})-(K{i}*L{i}*0.09%)')
    buy.append(f'=IF(B{i}-J{i}<=0, J{i}-B{i}, 0)')
    bupr.append(f'=E{i}')
    bumo.append(f'=(N{i}*O{i})+(N{i}*O{i}*0.09%)')   
    laam.append(f'=B{i}-K{i}+N{i}')
    lapr.append(f'=E{i}')
    lamo.append(f'=(Q{i}*R{i})-(Q{i}*R{i}*0.09%)')
    
price[5] = 1
price[6] = ''
balance[5] ='=D14'
balance[6] ='=SUM(F9:F14)'
Weight2.append('=SUM(H9:H14)')
investmoney[6] ='=SUM(I9:I14)'
target[5] = '=I14'
target[6] = ''
sell[6] = ''
sepr[6] = ''
semo[5] = '=K14'
semo[6] = '=SUM(M9:M14)'
buy[6] = ''
bupr[6] = ''
bumo[5] = '=N14'
bumo[6] = '=SUM(P9:P14)'
laam[6] = ''
lapr[6] = ''
lamo[5] = '=Q14'
lamo[6] = '=SUM(S9:S14)'

TR0['현재가'] = price
TR0['현재평가금'] = balance
TR0['월수익률'] = ret
TR0['투입비중'] = Weight2
TR0['투입금액'] = investmoney
TR0['목표량'] = target
TR0['매도량'] = sell
TR0['매도가'] = sepr
TR0['매도금액'] = semo
TR0['매수량'] = buy
TR0['매수가'] = bupr
TR0['매수금액'] = bumo
TR0['최종수량'] = laam
TR0['최종주가'] = lapr
TR0['최종평가금'] = lamo

TR = pd.concat([TR, TR0], axis=0, ignore_index=True)
TR = TR.fillna('')

## Google Spread sheet 저장
worksheet = sh.get_worksheet(mon) #시트순서로 월 선택

worksheet.clear()

worksheet.update([TR.columns.values.tolist()] + TR.values.tolist())
worksheet.update_cell(16, 1, f"Regime Signal : {Regime_Signal}")
worksheet.update_cell(17, 1, "* 수정 > 찾기 및 바꾸기 > 찾기: ' | 바꾸기 : 공란 > 체크+수식내검색 > 모두 바꾸기 & 말일신호 익일거래 & 실제 수량 및 금액 기입 시 ,표 없이")

# 스프레드시트 모양다듬기 - 정렬 & 보더 & 바탕구분색+볼드체강조 & 퍼센트

worksheet.format("A1:A15", {
    "horizontalAlignment": "CENTER",
    })
time.sleep(0.1)

worksheet.format("G2:G15", {
    "numberFormat": {
        "type": "PERCENT"
        },
    })
time.sleep(0.1)


worksheet.format("A1:S15", {
    "borders": {
        "top": {
            "style": "SOLID",
            "colorStyle": {
                "rgbColor": {
                    "red": 0.8,
                    "green": 0.8,
                    "blue": 0.8
                    }
                }
            },
        "bottom": {
            "style": "SOLID",
            "colorStyle": {
                "rgbColor": {
                    "red": 0.8,
                    "green": 0.8,
                    "blue": 0.8
                    }
                }
            },
        "left": {
            "style": "SOLID",
            "colorStyle": {
                "rgbColor": {
                    "red": 0.8,
                    "green": 0.8,
                    "blue": 0.8
                    }
                }
            },
        "right": {
            "style": "SOLID",
            "colorStyle": {
                "rgbColor": {
                    "red": 0.8,
                    "green": 0.8,
                    "blue": 0.8
                    }
                }
            }
        }
    })
time.sleep(0.1)   
      
worksheet.format("A1:S1", {
    "backgroundColor": {
      "red": 0.9,
      "green": 0.9,
      "blue": 0.9
    },
    "horizontalAlignment": "CENTER",
    "textFormat": {
      "bold": True
    }
})
time.sleep(0.1) 

worksheet.format("A8:S8", {
    "backgroundColor": {
      "red": 0.95,
      "green": 0.95,
      "blue": 0.95
    },
    "textFormat": {
      "bold": True
    }
})
time.sleep(0.1)

worksheet.format("A15:S15", {
    "backgroundColor": {
      "red": 0.95,
      "green": 0.95,
      "blue": 0.95
    },
    "textFormat": {
      "bold": True
    }
})
time.sleep(0.1)