import pandas as pd
import pybithumb

# BTC 오류는 하기연도별 함수에 리스트에 2013년 데이터 삭제로 해결

def 변동성돌파(df, k, period):             
    df.loc[:,'MA'] = df.loc[:,'close'].rolling(window=period).mean()
    
    signal = df.loc[:,'close'].shift(1) >= df['MA'].shift(1)   
    rangea = (df.loc[:,"high"] - df.loc[:,"low"]) * k
    Target = df.loc[:,"open"] + rangea.shift(1)    
    cond = df.loc[:,'high'] >= Target
        
    buy = Target[cond]
    sell = df.loc[cond, 'close']
     
    buy = buy[signal]
    sell = sell[signal]
    
    trading = len(sell)
    
    ret = ((sell-(sell*tax))/(buy+(buy*tax)))
    return ret.cumprod().iloc[-1], trading

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

def 연도별수익률(df, k, period):
    dfy = df.to_period("Y")
    year = []
    for y in dfy.index: 
        y = str(y)
        if y not in year: 
            year.append(y)
    
    # del year[0] # BTC만 적용
        
    result=[]
    
    for y in year:
        dfv = df.loc[y]
        dfv.loc[:,'MA'] = dfv.loc[:,'close'].rolling(window=period).mean()
        
        signal = dfv['close'].shift(1) >= dfv['MA'].shift(1)
    
        rangea = (dfv["high"] - dfv["low"]) * k
        Target = dfv["open"] + rangea.shift(1)
    
        cond = dfv['high'] >= Target
                
        buy = Target[cond]
        sell = dfv.loc[cond, 'close']
             
        buy = buy[signal]
        sell = sell[signal]
        
        n = len(sell)
    
        ret = ((sell-(sell*tax))/(buy+(buy*tax)))
        a = ret.cumprod().iloc[-1]
        b = buy_and_hold(dfv)
        n = len(sell)
        
        result.append([y, a, b, n])
        
    return result

ticker = input("Ticker?: ")

df = pybithumb.get_ohlcv(ticker)

수수료 = 0.0005
슬리피지 = 0.0002

tax = 수수료 + 슬리피지

data = []
cac = 연수(df)

for period in range(5,101,5):   
    for k in range(1,11):
        ret = 변동성돌파(df, k/10, period)[0]
        trading = 변동성돌파(df, k/10, period)[1]
        CAG = CAGR(ret, cac)
        data.append([period, k/10, ret, CAG, trading])
   
rdf = pd.DataFrame(data)
rdf.columns = ["period", "k", "return", "CAGR", "trading"]

rdf = rdf.sort_values("return")

best_k = rdf.iloc[-1, 1]
best_MA = rdf.iloc[-1, 0]

BNH = buy_and_hold(df)
BNH_CAGR = buy_and_hold_CAGR(df, cac)

yr = 연도별수익률(df, best_k, best_MA)

yret = pd.DataFrame(data=yr, columns=['year', 'return', 'buy & hold', 'trading'])
yret = yret.set_index(keys='year')

yret['return'] = yret['return']-1
yret['buy & hold'] = yret['buy & hold']-1

print("-"*20)
print("MA : {}".format(rdf.iloc[-1, 0]))
print("K : {}".format(rdf.iloc[-1, 1]))
print("Return : {:.2%}".format(rdf.iloc[-1, 2]-1))
print("투자횟수 :", rdf.iloc[-1, 4], "수수료 : {:.2%}".format(수수료), 
      "슬리피지 : {:.2%}".format(슬리피지))
print("단순 보유 후 홀딩 : {:.2%}".format(BNH-1))
print("차이 {:.2%}".format((rdf.iloc[-1, 2]-1)-(BNH-1)))
print("CAGR : {:.2%}".format(rdf.iloc[-1, 3]))
print("Buy&Hold CAGR : {:.2%}".format(BNH_CAGR))
print("-"*20)
print("연도별 수익")

for y, r, b, d, n in zip(yret.index, yret['return'], yret['buy & hold'], yret['return']-yret['buy & hold'], 
                      yret['trading']):
    print(f"{y}: 변동성돌파 수익률 {r:.2%}, 단순보유수익률 {b:.2%}, 차이 {d:.2%}, 투자횟수 {n}")




