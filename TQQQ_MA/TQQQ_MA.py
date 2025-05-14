import yfinance as yf
import pandas as pd
import time
import numpy as np
from datetime import datetime
import os
from openpyxl import load_workbook

class Save_Result: # 결과 저장 클래스
    def __init__(self):
        self.save_dir = 'C:/Users/GSR/Desktop/Python_project/git_folder/TQQQ_MA'
        # save_dir = 'C:/Users/ilpus/PythonProjects/git_folder/SECTOR_ETF'

    def save_to_excel(self, result):
        save_file_name = 'TEST.xlsx'
        save_path = os.path.join( self.save_dir, save_file_name)

        # 파일이 이미 존재하면 시트를 추가, 아니면 새로 생성
        if os.path.exists(save_path):
            with pd.ExcelWriter(save_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                result.to_excel(writer, index=False)
        else:
            with pd.ExcelWriter(save_path, engine='openpyxl') as writer:
                result.to_excel(writer, index=False)

        print(f"엑셀 파일이 저장되었습니다: {save_path}")

# TQQQ 데이터
df = yf.download(tickers='TQQQ', auto_adjust=True, interval='1d', progress=True, multi_level_index=False)
df.drop(['Open','High','Low','Volume'], axis=1, inplace=True)

df.loc[:,'Date'] = df.index
df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
df = df.reindex(columns=['Date', 'Close'])
df.loc[:,'50MA'] = df.loc[:,'Close'].rolling(window=50).mean()
df.loc[:,'220MA'] = df.loc[:,'Close'].rolling(window=220).mean()
df.dropna(axis=0, inplace=True)

df.loc[:,'Signal'] = df.loc[:,'Close'] >= df['220MA']   


print(df.head(10))
print(df.tail(10))

M_result = Save_Result()
M_result.save_to_excel(df)



# def MA투자(df, period):
#     df.loc[:,'MA'] = df.loc[:,'close'].rolling(window=period).mean()

#     bsignal = df.loc[:,'close'].shift(1) >= df.loc[:,'MA'].shift(1)
#     ssignal = df.loc[:,'close'].shift(1) < df.loc[:,'MA'].shift(1)
#     differ = bsignal != bsignal.shift(1)

#     df.loc[:,'Buy'] = df.loc[bsignal, 'open']
#     df.loc[:,'Sell'] = df.loc[ssignal, 'open']

#     df.loc[:,'Buy'] = df.loc[differ, 'Buy']
#     df.loc[:,'Sell'] = df.loc[differ, 'Sell']

#     df = df.drop(df[differ == False].index, axis=0)

#     trade = pd.DataFrame(df.loc[:,'Buy'].dropna(axis=0))
#     sell = df.loc[:,'Sell'].dropna(axis=0)

#     if len(trade) != len(sell):
#         trade =trade.iloc[:-1]
        
#     datas = []
#     for i in sell:
#         datas.append(i)

#     trade.loc[:,'Sell'] = datas
#     trade_count = len(trade)

#     trade.insert(loc=2, column='return', 
#                  value=((trade['Sell']-(trade['Sell']*tax))/(trade['Buy']+(trade['Buy']*tax))))
    
#     cacul = trade.loc[:,'return'].cumprod().iloc[-1]
    
#     return cacul, trade_count



# # Regime Signal 확인
# Regime_Signal = round(AGG.iloc[0, 0] - AGG['Close'].mean(), 2)

# AGG_add1 = pd.DataFrame(data=[AGG['Close'].mean()], index=['AGG_4mo_avg'], columns=['Close'])
# AGG_add2 = pd.DataFrame(data=[Regime_Signal], index=['Regime_Signal'], columns=['Close'])

# AGG = pd.concat([AGG, AGG_add1])
# AGG = pd.concat([AGG, AGG_add2])

# time.sleep(0.1)

# # 포트폴리오 가격 불러오기
# ticker = ['UPRO', 'TQQQ', 'EDC', 'TMF', 'TMV'] # 모멘텀 티커
 
# B12year = str(int(B1year)-1)

# end = f'{B1year}-{B1month}-{endday}'
# start = f'{B12year}-{B1month}-01'

# SignalPort = yf.download(tickers=ticker, start=start, end=end, auto_adjust=False, interval='1mo', progress=True, 
#                          multi_level_index=False)['Close']
# # 수정주가보단 일반주가가 포폴비쥬얼라이즈에 더 근사값['Adj Close'] 
# time.sleep(0.1)

# SignalPort.sort_index(axis=0, ascending=False, inplace=True)

# date1 = list()
# date2 = SignalPort.index

# for i in date2 :
#     i = i.strftime('%Y-%m-%d')
#     date1.append(i)
    
# SignalPort =SignalPort.set_axis(labels=[date1[0], date1[1], date1[2], date1[3], date1[4], 
#                                         date1[5], date1[6], date1[7], date1[8], date1[9], 
#                                         date1[10], date1[11], date1[12]], axis=0)


# # 포트폴리오 모멘텀 점수
# momentum =[]

# for i in ticker :
#     cur = SignalPort.loc[date1[0], i]
#     mo1 = SignalPort.loc[date1[1], i]
#     mo3 = SignalPort.loc[date1[3], i]
#     mo6 = SignalPort.loc[date1[6], i]
#     mo9 = SignalPort.loc[date1[9], i]
#     mo12 = SignalPort.loc[date1[12], i]
#     score = ((cur/mo1-1)*30)+((cur/mo3-1)*25)+((cur/mo6-1)*20)+((cur/mo9-1)*15)+((cur/mo12-1)*10)
#     momentum.append([i, score.round(2)])

# momentum = pd.DataFrame(momentum, columns=['ticker', 'momentum'])

# momentum.loc[:, 'rank'] = momentum.loc[:, 'momentum'].rank(ascending=False, 
#                                                        method='max', 
#                                                        pct=False, 
#                                                        na_option='bottom')

# momentum = momentum.sort_values(by=['rank'], ascending=True, ignore_index=False, inplace=False)


# # 타겟 티커 확정
# Target_ticker = [momentum.iloc[0, 0], momentum.iloc[1, 0]]


# #기본 MVP모델 Weight 해찾기 riskfolio Portfolio 설정
# Hist = yf.download(tickers=Target_ticker, period='3mo', auto_adjust=True, interval='1d', 
#                    progress=False)['Close']
# Hist.sort_index(axis=0, ascending=False, inplace=True)

# Hist = Hist.iloc[: 45]
# Ret = Hist.pct_change(-1).dropna()
# Ret = Ret.round(4)

# port = rp.Portfolio(returns=Ret)
# method_mu = 'hist'
# method_cov = 'hist'
# port.assets_stats(method_mu=method_mu, method_cov=method_cov)

# model = 'Classic'
# rm = 'MV'
# obj = 'MinRisk'
# hist = True
# rf = 0
# l = 0


# # 유니버스 데이터베이스
# ticker_class = []
# for i in Target_ticker :
#     if i == 'UPRO' or i == 'TQQQ' or i == 'EDC' :
#         ticker_class.append('stock')
#     else : 
#         ticker_class.append('bond')


# asset_classes = {
#     'Asset' : [Target_ticker[0], Target_ticker[1]],
#     'Class' : [ticker_class[0], ticker_class[1]]}

# asset_classes = pd.DataFrame(asset_classes)


# # 제약조건 설정 데이터베이스
# constraints = {'Disabled' : [False, False],
#                'Type' : ['All Assets', 'All Assets'],
#                'Set' : ['', ''],
#                'Position' : ['', ''],
#                'Sign' : ['>=', '<='],
#                'Weight' : [0.2, 0.8],
#                'Type Relative' : ['', ''],
#                'Relative Set' : ['', ''],
#                'Relative' : ['', ''],
#                'Factor' : ['', '']}

# constraints = pd.DataFrame(constraints)


# # 제약조건 적용 MVP모델 Weight 해찾기
# A, B = rp.assets_constraints(constraints, asset_classes)

# port.ainequality = A
# port.binequality = B

# w = port.optimization(model=model, rm=rm, obj=obj, rf=rf, l=l, hist=hist)


# # 최종 당월 투자 종목 및 비중 프린트
# print('----------------------------------------------------------------------')
# print(momentum)
# print('----------------------------------------------------------------------')

# ax = rp.plot_bar(w=w, title='Portfolio', kind='h', ax=None)

# I1 = w.index[0]
# I2 = w.index[1]

# if Regime_Signal < 0 :
#     print('Regime Signal :', Regime_Signal,'> RISK')
#     print('Asset :', 'CASH')   
# else :
#     print('Regime Signal :', Regime_Signal,'> Stable')
#     print('Asset :', I1, '> Weight :', round(w.loc[I1, 'weights'], 4))
#     print('Asset :', I2, '> Weight :', round(w.loc[I2, 'weights'], 4))
    
# print('----------------------------------------------------------------------')
# time.sleep(0.1)


# # 현재가 및 현재평가금액 구하기 확인(궁극적으로는 현재가는 한투API 현재가 불러오기로 대체)
# TR_ticker = ['UPRO', 'TQQQ', 'EDC', 'TMF', 'TMV'] # 트레이딩 티커
# price = []
 
# for i in TR_ticker :    
#     j = yf.download(tickers=i, period='1d', interval='1d', progress=False, 
#                     multi_level_index=False)['Close']
#     price.append(round(j.iloc[0],4))
# price.append(1)

# TR['현재가'] = price

# tax = 0.0009
# TR.insert(loc=5, column='현재평가금', value=(TR.전월수량*TR.현재가)-(TR.전월수량*TR.현재가*tax))
# TR.iat[5, 5] = TR.iat[5, 3]

# # 월수익률 구하기
# TR.insert(loc=6, column='월수익률', value=round(TR.현재평가금/TR.전월평가금-1, 4))
# TR.iat[5, 6] = 0

# ################################

# # 비중 열 삽입 하기
# V1 = w.values[0]
# V2 = w.values[1]

# V1 = round(float(V1[0])*0.99, 4)
# V2 = round(float(V2[0])*0.99, 4)

# Weight = []

# if Regime_Signal >= 0 :
#     for i in ticker :
#         if i != I1 and i != I2 :
#             Weight.append(float(0))            
#         elif i == I1 :
#             Weight.append(V1)
#         elif i == I2 :
#             Weight.append(V2)
#     Weight.append(float(0.01))
# else :
#     Weight = [float(0), float(0), float(0), float(0), float(0), float(1)]
        
# TR['투입비중'] = Weight


# # 투입금액 구하기
# PreSum = TR['현재평가금'].sum(axis=0)
# TR.insert(loc=8, column='투입금액', value=TR.투입비중*PreSum)


# # 목표량 구하기
# TR.insert(loc=9, column='목표량', value=TR.투입금액/TR.현재가)
# TR.iat[5, 9] = TR.iat[5, 8]


# # 매도항목 구하기
# sell =[]
# for k in range(6) :
#     l = TR.iat[k, 1] - TR.iat[k, 9]
#     if l > 0 :
#         sell.append(l)
#     else :
#         sell.append(0)

# TR['매도량'] = sell
# TR['매도가'] = price
# TR.insert(loc=12, column='매도금액', value=round((TR.매도량*TR.매도가)-(TR.매도량*TR.매도가*tax), 4))
# TR.iat[5, 12] = TR.iat[5, 10]


# # 매수항목 구하기
# buy =[]
# for m in range(6) :
#     n = TR.iat[m, 9] - TR.iat[m, 1]
#     if n > 0 :
#         buy.append(n)
#     else :
#         buy.append(0)

# TR['매수량'] = buy
# TR['매수가'] = price
# TR.insert(loc=15, column='매수금액', value=round((TR.매수량*TR.매수가)+(TR.매수량*TR.매수가*tax), 4))
# TR.iat[5, 15] = TR.iat[5, 13]


# # 최종항목 구하기
# TR.insert(loc=16, column='최종수량', value=TR.전월수량+TR.매수량-TR.매도량)
# TR['최종주가'] = price
# TR.insert(loc=18, column='최종평가금', value=(TR.최종수량*TR.최종주가)-(TR.최종수량*TR.최종주가*tax))
# TR.iat[5, 18] = TR.iat[5, 16]


# # 하단 합계행 추가
# d1 = TR['전월평가금'].sum(axis=0)
# d2 = TR['현재평가금'].sum(axis=0)

# d4 = TR['투입비중'].sum(axis=0)
# d5 = TR['투입금액'].sum(axis=0)
# d6 = TR['매도금액'].sum(axis=0)
# d7 = TR['매수금액'].sum(axis=0)
# d8 = TR['최종평가금'].sum(axis=0)
# d9 = float(d2) / float(d1) - 1

# PF = pd.DataFrame(data=[['Portfolio', d1, d2, d9, d4, d5, d6, d7, d8]], 
#                   columns=['티커', '전월평가금', '현재평가금', '월수익률', '투입비중', '투입금액', 
#                            '매도금액', '매수금액', '최종평가금'])
# TR = pd.concat([TR, PF], axis=0, ignore_index=True)


# TQQQ.sort_index(axis=0, ascending=False, inplace=True)