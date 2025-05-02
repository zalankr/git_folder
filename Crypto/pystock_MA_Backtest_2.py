import pandas as pd
import pybithumb

def MA투자(df, period):
    df.loc[:,'MA'] = df.loc[:,'close'].rolling(window=period).mean()

    bsignal = df.loc[:,'close'].shift(1) >= df.loc[:,'MA'].shift(1)
    ssignal = df.loc[:,'close'].shift(1) < df.loc[:,'MA'].shift(1)
    differ = bsignal != bsignal.shift(1)

    df.loc[:,'Buy'] = df.loc[bsignal, 'open']
    df.loc[:,'Sell'] = df.loc[ssignal, 'open']

    df.loc[:,'Buy'] = df.loc[differ, 'Buy']
    df.loc[:,'Sell'] = df.loc[differ, 'Sell']

    df = df.drop(df[differ == False].index, axis=0)

    trade = pd.DataFrame(df.loc[:,'Buy'].dropna(axis=0))
    sell = df.loc[:,'Sell'].dropna(axis=0)

    if len(trade) != len(sell):
        trade =trade.iloc[:-1]
        
    datas = []
    for i in sell:
        datas.append(i)

    trade.loc[:,'Sell'] = datas
    trade_count = len(trade)

    trade.insert(loc=2, column='return', 
                 value=((trade['Sell']-(trade['Sell']*tax))/(trade['Buy']+(trade['Buy']*tax))))
    
    cacul = trade.loc[:,'return'].cumprod().iloc[-1]
    
    return cacul, trade_count

def buy_and_hold(df):
    buy = df.iloc[0,0]
    sell = df.iloc[-1,3]
    return (sell-(sell*tax))/(buy+(buy*tax))

def 연수(df):
    begin = df.index[0]
    end = df.index[-1]
    cac = str(end - begin).split()
    cac = float(cac[0]) / 365
    return cac
    
def CAGR(ret, cac):
    """
    ret = 최종수익률
    cac = 연수
    """
    CAGR = ret**(1/cac) - 1     
    return CAGR

def buy_and_hold_CAGR(df, cac):
    buy = df.iloc[0,0]
    sell = df.iloc[-1,3]
    ret = (sell-(sell*tax))/(buy+(buy*tax))
    BNH_CAGR = ret**(1/cac) - 1     
    return BNH_CAGR

def 연도별수익률(df, period):
    dfy = df.to_period("Y")
    year = []
    for y in dfy.index: 
        y = str(y)
        if y not in year: 
            year.append(y)
    
    del year[0] # BTC만 적용
        
    result=[]
    
    for y in year:
        dfv = df.loc[y]
        bnh = buy_and_hold(dfv)
        MAr = MA투자(dfv, period)       
        result.append([y, MAr[0], bnh, MAr[1]])
        
    return result


ticker = input("Ticker?: ")

df = pybithumb.get_ohlcv(ticker)

수수료 = 0.0005
슬리피지 = 0.0002

tax = 수수료 + 슬리피지

data = []
cac = 연수(df)

for period in range(5,121,5):   
    ret = MA투자(df, period)[0]
    trade_count = MA투자(df, period)[1]
    CAG = CAGR(ret, cac)
    data.append([period, ret, CAG, trade_count])
   
rdf = pd.DataFrame(data)
rdf.columns = ["period", "return", "CAGR", "trade_count"]

rdf = rdf.sort_values("return")

best_MA = rdf.iloc[-1, 0]

BNH = buy_and_hold(df)
BNH_CAGR = buy_and_hold_CAGR(df, cac)

yr = 연도별수익률(df, best_MA)

yret = pd.DataFrame(data=yr, columns=['year', 'return', 'buy & hold', 'trade_count'])
yret = yret.set_index(keys='year')

yret['return'] = yret['return']-1
yret['buy & hold'] = yret['buy & hold']-1

print("MA : {}".format(rdf.iloc[-1, 0]))
print("Return : {:.2%}".format(rdf.iloc[-1, 1]-1))
print("투자횟수 :", rdf.iloc[-1, 3], "수수료 : {:.2%}".format(수수료), 
      "슬리피지 : {:.2%}".format(슬리피지))
print("단순 보유 후 홀딩 : {:.2%}".format(BNH-1))
print("차이 {:.2%}".format((rdf.iloc[-1, 1]-1)-(BNH-1)))
print("CAGR : {:.2%}".format(rdf.iloc[-1, 2]))
print("Buy&Hold CAGR : {:.2%}".format(BNH_CAGR))
print("연도별 수익")

for y, r, b, d, n in zip(yret.index, yret['return'], yret['buy & hold'], yret['return']-yret['buy & hold'], 
                      yret['trade_count']):
    print(f"{y}: MA수익률 {r:.2%}, 단순보유수익률 {b:.2%}, 차이 {d:.2%}, 투자횟수 {n}")
    
print(rdf.tail(5))




