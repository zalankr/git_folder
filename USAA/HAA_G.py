import yfinance as yf
import pandas as pd
import time
import gspread
# import line_alert
import calendar

# 날짜 인풋 받기
year = '2025'   ###
month = input('month?:')
mon = int(month)

if mon < 10 :
    monstr = f'0{mon}'    
else :
    monstr = str(mon)

# 전월 파일명 구현하기
B1month  = mon-1
        
if B1month == 0 : ###
    B1year = str(int(year)-1)
    B1month = '12'
            
elif B1month < 10 and B1month >= 1 : ###
    B1month = f'0{B1month}'
    B1year = year
        
else:
    B1year = year

B12month = B1month
B12year = str(int(B1year)-1)


# Google spread account 연결 및 오픈 ###
gc = gspread.service_account("C:/Users/ilpus/PythonProjects/US_Asset_Allocation/service_account.json")
# gc = gspread.service_account("C:/Users/ilpus/PythonProjects/US_Asset_Allocation/service_account.json")
url = 'https://docs.google.com/spreadsheets/d/16IAqsD_1MEP7tGumz66y4c9hXZ_uAVJEmMQJKYZudck/edit?gid=1303568032#gid=1303568032'
# 기 작성 URL기입
# 기 작성된 연도별 USLA gspread URL 기입
sh = gc.open_by_url(url) # 스프레드시트 url주소로 연결


# 워크시트 가져오기
worksheet0 = sh.get_worksheet(mon-1)

ticker0 = ['SPY', 'IWM', 'VEA', 'VWO', 'PDBC', 'VNQ', 'TLT', 'IEF','BIL', 'CASH'] ###
# ticker0.append('CASH')

col = ['전월수량', '전월주가', '전월평가금']
dic = worksheet0.get("R2:T11")

TR = pd.DataFrame(data=dic, index=None, dtype=float, columns=col, copy=True)
TR.insert(loc=0, column='티커', value=ticker0)

    
# Momentum 주가 데이터
ticker = ['TIP', 'SPY', 'IWM', 'VEA', 'VWO', 'PDBC', 'VNQ', 'TLT', 'IEF','BIL']

endday = calendar.monthrange(int(B1year), int(B1month))
endday = str(endday[1])

end = f'{B1year}-{B1month}-{endday}'
start = f'{B12year}-{B1month}-01'

port = yf.download(tickers=ticker, start=start, end=end, auto_adjust=True, interval='1mo', 
                   progress=True, multi_level_index=False)['Close']
time.sleep(0.01)


port.sort_index(axis=0, ascending=False, inplace=True)
#######################################################################################################

end2 = f'{year}-{monstr}-01'  ####
start2 = f'{B1year}-{B1month}-01'

port2 = yf.download(tickers=ticker, start=start2, end=end2, auto_adjust=True, interval='1d', period='1d', 
                    progress=True, multi_level_index=False)['Close']
port2.sort_index(axis=0, ascending=False, inplace=True)

for pa in range(10) :
    port.iat[0, pa] = port2.iat[0, pa]

#######################################################################################################

date1 = list()
date2 = port.index
        
for i in date2 :
    i = i.strftime('%Y-%m-%d')
    date1.append(i)
            
port = port.set_axis(labels=[date1[0], date1[1], date1[2], date1[3], date1[4], date1[5], date1[6], 
                             date1[7], date1[8], date1[9], date1[10], date1[11], date1[12]], axis=0)
        
Momentum = []

for i in ticker :
    mo0 = port.at[date1[0], i]
    mo1 = port.at[date1[1], i]
    mo3 = port.at[date1[3], i]
    mo6 = port.at[date1[6], i]
    mo12 = port.at[date1[12], i]
    score = ((mo0/mo1-1)+(mo0/mo3-1)+(mo0/mo6-1)+(mo0/mo12-1))*100
    Momentum.append([i, score.round(2)]) 
      
mo0 = pd.DataFrame(Momentum, columns=['티커', 'Momentum'])

mo0.drop([0], axis=0, inplace=True)
mo1 = pd.DataFrame({'티커' : ["CASH"],'Momentum' : ['']})
mo0 = pd.concat([mo0, mo1], axis=0, ignore_index=True)

TR.insert(loc=4, column='Momentum', value=mo0.Momentum)

time.sleep(0.01)

# Regime Signal
Regime_Signal = Momentum[0][1]
        
        
# Momentum Score 산출
Agg_M = mo0.drop(index=[8, 9])    
Agg_M.loc[:, 'rank'] = Agg_M.loc[:, 'Momentum'].rank(ascending=False, 
                                                     method='max', 
                                                     pct=False, 
                                                     na_option='bottom')        
Agg_M = Agg_M.sort_values(by=['rank'], ascending=True, ignore_index=True, inplace=False)
        
Def_M = mo0.drop(index=[0,1,2,3,4,5,6,9])      
Def_M.loc[:, 'rank'] = Def_M.loc[:, 'Momentum'].rank(ascending=False, 
                                                               method='max', 
                                                               pct=False, 
                                                               na_option='bottom')        
Def_M = Def_M.sort_values(by=['rank'], ascending=True, ignore_index=True, inplace=False)


# 타겟 티커 및 비중 선정
Target = []
Weight = []
        
if Regime_Signal < 0 :
    if Def_M.iat[0,0] == 'BIL' :
        Target.append('CASH')
        Weight.append(1)
    else :
        Target.append('IEF')
        Weight.append(0.99)
        Target.append('CASH')
        Weight.append(0.01)        
        
else :
    for i in range(4) :
        k = Agg_M.iat[i,0]
        o = Agg_M.iat[i,1]
        if o >= 0 :
            Target.append(k)
            Weight.append(0.25*0.99)
                    
    if len(Target) < 4 :
        if Def_M.iat[0,0] == 'BIL' :
            Weight.append((4-len(Target))*0.25*0.99)
            Target.append('CASH')
            
        else :           
            if 'IEF' in Target :
                idx = Target.index('IEF')
                ridx = Weight[idx] + ((4-len(Target))*0.25*0.99)
                Weight[idx] = ridx
            else :
                Weight.append((4-len(Target))*0.25*0.99)
                Target.append('IEF')
                
    Target.append('CASH')
    Weight.append(0.01)    


TaWe = []
for i in range(len(Target)) :
    TaWe.append([Target[i], Weight[i]])
  
                    
# 당월 투자 종목 및 비중 프린트
print(f'--------------{year}-{month}--------------------------------------------')
if Regime_Signal < 0 :
    print('HAA Regime Signal :', Regime_Signal,'> RISK')
    print('Asset :', Target, Weight)   
else :
    try : 
        print('HAA Regime Signal :', Regime_Signal,'> Stable')
        print('Asset :', Target[0], '> Weight :', Weight[0])
        print('Asset :', Target[1], '> Weight :', Weight[1])
        print('Asset :', Target[2], '> Weight :', Weight[2])
        print('Asset :', Target[3], '> Weight :', Weight[3])
    except : 
        print('티커 4개 이하')
                                
print('----------------------------------------------------------------------')


# 현재가 및 현재평가금액 구하기 확인(궁극적으로는 현재가는 한투API 현재가 불러오기로 대체)
ticker = ['SPY', 'IWM', 'VEA', 'VWO', 'PDBC', 'VNQ', 'TLT', 'IEF','BIL']
price = []

for i in ticker :    
    j = yf.download(tickers=i, period='1d', auto_adjust=True, interval='1d', progress=False,
                    multi_level_index=False)['Close']
    price.append(round(j.iloc[0],4))
price.append(1)

TR['현재가'] = price

tax = 0.0009
TR.insert(loc=6, column='현재평가금', value=(TR.전월수량*TR.현재가)-(TR.전월수량*TR.현재가*tax))
TR.iat[9, 6] = TR.iat[9, 3]


# 월수익률 구하기
TR.insert(loc=7, column='월수익률', value=round(TR.현재평가금/TR.전월평가금-1, 4))
TR.iat[9, 7] = 0


# 비중 열 삽입 하기
zero = [0,0,0,0,0,0,0,0,0,0]
TR.insert(loc=8, column='투입비중', value=zero)
TR['투입비중'] = TR['투입비중'].astype(float)

for i in TaWe :
    for j in range(10) :
        if TR.iat[j, 0] == i[0] :
            TR.iat[j, 8] = i[1] ###         



# 투입금액 구하기
PreSum = TR['현재평가금'].sum(axis=0)
TR.insert(loc=9, column='투입금액', value=TR.투입비중*PreSum)


# 목표량 구하기
TR.insert(loc=10, column='목표량', value=(TR.투입금액/TR.현재가))
TR.iat[9, 10] = TR.iat[9, 9]


# 매도항목 구하기
sell =[]
for k in range(10) :
    l = TR.iat[k, 1] - TR.iat[k, 10]
    if l > 0 :
        sell.append(l)
    else :
        sell.append(0)

TR['매도량'] = sell
TR['매도가'] = price
TR.insert(loc=13, column='매도금액', value=(TR.매도량*TR.매도가)-(TR.매도량*TR.매도가*tax))
TR.iat[9, 13] = TR.iat[9, 11]


# 매수항목 구하기
buy =[]
for m in range(10) :
    n = TR.iat[m, 10] - TR.iat[m, 1]
    if n > 0 :
        buy.append(n)
    else :
        buy.append(0)

TR['매수량'] = buy
TR['매수가'] = price
TR.insert(loc=16, column='매수금액', value=round((TR.매수량*TR.매수가)+(TR.매수량*TR.매수가*tax), 4))
TR.iat[9, 16] = TR.iat[9, 14]


# 최종항목 구하기
TR.insert(loc=17, column='최종수량', value=TR.전월수량+TR.매수량-TR.매도량)
TR['최종주가'] = price
TR.insert(loc=19, column='최종평가금', value=(TR.최종수량*TR.최종주가)-(TR.최종수량*TR.최종주가*tax))
TR.iat[9, 19] = TR.iat[9, 17]


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


# 하단 구글식행 추가
col = ['전월수량', '전월주가', '전월평가금']
dic = worksheet0.get("R2:T11")
dic2 = float(worksheet0.acell('T12').value)

TR0 = pd.DataFrame(data=dic, index=None, dtype=float, columns=col, copy=True)
TR0.insert(loc=0, column='티커', value=ticker0)

df1 = pd.DataFrame(data=[['Portfolio', dic2]], columns=['티커','전월평가금'])
TR0 = pd.concat([TR0, df1], axis=0, ignore_index=True)
mog = mo0.Momentum

TR0 = pd.concat([TR0, mog], axis=1, ignore_index=False)


price = []
balance = []
ret = []
investmoney = []
weight3 = []
for j in TR.투입비중 :
    weight3.append(j)
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

for i in range(13, 24) :
    price.append(f'=GOOGLEFINANCE($A{i})')    
    balance.append(f'=(B{i}*F{i})-(B{i}*F{i}*0.09%)')
    ret.append(f'=iferror((G{i}/D{i})-1)')
    investmoney.append(f'=G23*I{i}')
    target.append(f'=J{i}/F{i}')
    sell.append(f'=IF(B{i}-K{i}>0, B{i}-K{i}, 0)')
    sepr.append(f'=F{i}')
    semo.append(f'=(M{i}*L{i})-(M{i}*L{i}*0.09%)')
    buy.append(f'=IF(B{i}-K{i}<=0, K{i}-B{i}, 0)')
    bupr.append(f'=F{i}')
    bumo.append(f'=(P{i}*O{i})+(P{i}*O{i}*0.09%)')
    laam.append(f'=B{i}-L{i}+O{i}')
    lapr.append(f'=F{i}')
    lamo.append(f'=(S{i}*R{i})-(S{i}*R{i}*0.09%)')
    
price[9] = 1
price[10] = ''
balance[9] ='=D22'
balance[10] ='=SUM(G13:G22)'
investmoney[10] ='=SUM(J13:J22)'
target[9] = '=J22'
target[10] = ''
sell[10] = ''
sepr[10] = ''
semo[9] = '=L22'
semo[10] = '=SUM(N13:N22)'
buy[10] = ''
bupr[10] = ''
bumo[9] = '=O22'
bumo[10] = '=SUM(Q13:Q22)'
laam[10] = ''
lapr[10] = ''
lamo[9] = '=R22'
lamo[10] = '=SUM(T13:T22)'

TR0['현재가'] = price
TR0['현재평가금'] = balance
TR0['월수익률'] = ret
TR0['투입비중'] = weight3
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
# worksheet.update([TR.columns.values.tolist()] + TR.values.tolist(), "A1:T23")
worksheet.update([TR.columns.values.tolist()] + TR.values.tolist())
worksheet.update_cell(24, 1, f"Regime Signal : {Regime_Signal}")
worksheet.update_cell(25, 1, "* 수정 > 찾기 및 바꾸기 > 찾기: ' | 바꾸기 : 공란 > 체크+수식내검색 > 모두 바꾸기 & 말일신호 익일거래 & 실제 수량 및 금액 기입 시 ,표 없이 | TIP는 현재가 수정주가로 조정 되었는 지 확인")


# 스프레드시트 모양다듬기 - 정렬 & 보더 & 바탕구분색+볼드체강조 & 퍼센트
worksheet.format("A1:A23", {
    "horizontalAlignment": "CENTER",
    })
time.sleep(0.1)

worksheet.format("H2:H23", {
    "numberFormat": {
        "type": "PERCENT"
        },
    })
time.sleep(0.1)


worksheet.format("A1:T23", {
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
      
worksheet.format("A1:T1", {
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

worksheet.format("A12:T12", {
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

worksheet.format("A23:T23", {
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


# 라인알러트 보내기
# line_alert.SendMessage(str(year) + '-' + str(month) +' HAA')

# if Regime_Signal < 0 :
#     line_alert.SendMessage('HAA Regime Signal :' + str(Regime_Signal) +'> RISK')
#     line_alert.SendMessage('Asset :' + Target[0] + '> Weight :' + str(Weight[0]))  
# else :
#     try : 
#         line_alert.SendMessage('HAA Regime Signal :' + str(Regime_Signal) +'> Stable')
#         line_alert.SendMessage('Asset :' + Target[0] + '> Weight :' + str(Weight[0]))
#         line_alert.SendMessage('Asset :' + Target[1] + '> Weight :' + str(Weight[1]))
#         line_alert.SendMessage('Asset :' + Target[2] + '> Weight :' + str(Weight[2]))
#         line_alert.SendMessage('Asset :' + Target[3] + '> Weight :' + str(Weight[3]))
#     except : 
#         line_alert.SendMessage('티커 4개 이하')