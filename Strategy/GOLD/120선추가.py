import pandas as pd
import pybithumb

def MA투자(df, period):
    df.loc[:, 'MA'] = df.loc[:, 'close'].rolling(window=period).mean()
    df.loc[:, 'MA120'] = df.loc[:, 'close'].rolling(window=120).mean()
    
    # 매수 신호 조건: 전일 종가 >= 전일 MA & 전일 종가 >= 전일 120일 이동평균
    bsignal = (df.loc[:, 'close'].shift(1) >= df.loc[:, 'MA'].shift(1)) & \
              (df.loc[:, 'close'].shift(1) >= df.loc[:, 'MA120'].shift(1))
    ssignal = df.loc[:, 'close'].shift(1) < df.loc[:, 'MA'].shift(1)
    differ = bsignal != bsignal.shift(1)
    
    df.loc[:, 'Buy'] = df.loc[bsignal, 'open']
    df.loc[:, 'Sell'] = df.loc[ssignal, 'open']
    
    df.loc[:, 'Buy'] = df.loc[differ, 'Buy']
    df.loc[:, 'Sell'] = df.loc[differ, 'Sell']
    
    df = df.drop(df[differ == False].index, axis=0)
    
    trade = pd.DataFrame(df.loc[:, 'Buy'].dropna(axis=0))
    sell = df.loc[:, 'Sell'].dropna(axis=0)
    
    if len(trade) > len(sell):
        trade = trade.iloc[:len(sell)]
    elif len(sell) > len(trade):
        sell = sell.iloc[:len(trade)]
    
    trade.loc[:, 'Sell'] = sell.values
    trade_count = len(trade)
    
    if trade_count == 0:
        return 1, 0  # 수익률 1 (즉, 변화 없음), 거래 횟수 0
    
    trade.insert(loc=2, column='return', 
                 value=((trade['Sell'] - (trade['Sell'] * tax)) / (trade['Buy'] + (trade['Buy'] * tax))))
    
    cacul = trade.loc[:, 'return'].cumprod().iloc[-1] if not trade.empty else 1
    
    return cacul, trade_count

def buy_and_hold(df):
    if df.empty:
        return 1
    buy = df.iloc[0, 0]
    sell = df.iloc[-1, 3]
    return (sell - (sell * tax)) / (buy + (buy * tax))

def 연수(df):
    begin = df.index[0]
    end = df.index[-1]
    cac = str(end - begin).split()
    cac = float(cac[0]) / 365
    return cac

def CAGR(ret, cac):
    return ret ** (1 / cac) - 1

def buy_and_hold_CAGR(df, cac):
    ret = buy_and_hold(df)
    return ret ** (1 / cac) - 1

def 연도별수익률(df, period):
    dfy = df.to_period("Y")
    year = sorted(set(str(y) for y in dfy.index))
    
    if "2013" in year:
        year.remove("2013")
    
    result = []
    for y in year:
        dfv = df.loc[y]
        if dfv.empty:
            continue
        bnh = buy_and_hold(dfv)
        MAr = MA투자(dfv, period)
        result.append([y, MAr[0], bnh, MAr[1]])
    
    return result

ticker = input("Ticker?: ")
df = pybithumb.get_ohlcv(ticker)

tax = 0.0005 + 0.0002  # 수수료 + 슬리피지
data = []
cac = 연수(df)

for period in range(5, 121, 5):
    ret, trade_count = MA투자(df, period)
    CAG = CAGR(ret, cac)
    data.append([period, ret, CAG, trade_count])

rdf = pd.DataFrame(data, columns=["period", "return", "CAGR", "trade_count"])
rdf = rdf.sort_values("return")

best_MA = rdf.iloc[-1, 0]
BNH = buy_and_hold(df)
BNH_CAGR = buy_and_hold_CAGR(df, cac)

yr = 연도별수익률(df, best_MA)
yret = pd.DataFrame(data=yr, columns=['year', 'return', 'buy & hold', 'trade_count'])
yret.set_index(keys='year', inplace=True)

yret['return'] -= 1
yret['buy & hold'] -= 1

print(f"MA : {best_MA}")
print(f"Return : {rdf.iloc[-1, 1] - 1:.2%}")
print(f"투자횟수 : {rdf.iloc[-1, 3]}, 수수료 : {0.0005:.2%}, 슬리피지 : {0.0002:.2%}")
print(f"단순 보유 후 홀딩 : {BNH - 1:.2%}")
print(f"차이 {rdf.iloc[-1, 1] - 1 - (BNH - 1):.2%}")
print(f"CAGR : {rdf.iloc[-1, 2]:.2%}")
print(f"Buy&Hold CAGR : {BNH_CAGR:.2%}")
print("연도별 수익")

for y, r, b, d, n in zip(yret.index, yret['return'], yret['buy & hold'], yret['return'] - yret['buy & hold'], yret['trade_count']):
    print(f"{y}: MA수익률 {r:.2%}, 단순보유수익률 {b:.2%}, 차이 {d:.2%}, 투자횟수 {n}")

print(rdf.tail(5))


