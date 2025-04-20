import pandas as pd
import numpy as np
import yfinance as yf

# 18개월전 가격 비교 투자
import pandas as pd

def max_drawdown(trade):
    """
    거래 데이터에서 Max Drawdown 계산
    :param trade: 매수/매도 가격을 포함한 pandas DataFrame
    :return: Max Drawdown 값
    """
    trade['cum_max'] = trade['Sell'].cummax()
    trade['drawdown'] = trade['Sell'] / trade['cum_max'] - 1
    return trade['drawdown'].min()

def Before_Model(df, tax):
    bsignal = df.loc[:, 'Close'] >= df.loc[:, 'Be']
    ssignal = df.loc[:, 'Close'] < df.loc[:, 'Be']

    differ = bsignal != bsignal.shift(1)

    df.loc[:, 'Buy'] = df.loc[bsignal, 'Close']
    df.loc[:, 'Sell'] = df.loc[ssignal, 'Close']

    df.loc[:, 'Buy'] = df.loc[differ, 'Buy']
    df.loc[:, 'Sell'] = df.loc[differ, 'Sell']

    df = df.drop(df[differ == False].index, axis=0)

    trade = pd.DataFrame(df.loc[:, 'Buy'].dropna(axis=0))
    sell = df.loc[:, 'Sell'].dropna(axis=0)

    if len(trade) != len(sell):
        trade = trade.iloc[:-1]

    datas = []
    for i in sell:
        datas.append(i)

    trade.loc[:, 'Sell'] = datas
    trade_count = len(trade)

    trade.insert(loc=2, column='return', 
                 value=((trade['Sell'] - (trade['Sell'] * tax)) / (trade['Buy'] + (trade['Buy'] * tax))))
    
    cacul = trade.loc[:, 'return'].cumprod().iloc[-1]

    # MDD 계산
    mdd = max_drawdown(trade)
    
    return cacul, trade_count, mdd

# Buy & hold에서 MDD 산출
def BNH_MDD(df):
    df = df.copy()
    df['cum_max'] = df['Close'].cummax()  # 최고점 갱신
    df['drawdown'] = df['Close'] / df['cum_max'] - 1  # 하락률 계산
    max_dd = df['drawdown'].min()  # 최대 낙폭
    return max_dd

# Buy and hold 수익률 계산
def buy_and_hold_return(df):
    buy = df.iloc[0,0]
    sell = df.iloc[-1,0]
    ROI = (sell-(sell*tax))/(buy+(buy*tax))
    max_dd = BNH_MDD(df)
    return ROI, max_dd

# 투자기간
def Years(df):
    begin = df.index[0]
    end = df.index[-1]
    year = str(end - begin).split()
    year = float(year[0]) / 365
    return year

def CAGR(ret, cac):
    """
    ret = 최종수익률
    cac = 연수
    """
    CAGR = ret**(1/cac) - 1     
    return CAGR

# Period
start = '2004-12-01'
end = '2025-02-28'

# Tax
수수료 = 0.0033
슬리피지 = 0.0002
tax = 수수료 + 슬리피지

# GLD data load
month = 18
df = yf.download('GLD', start=start, end=end, auto_adjust=True, interval='1mo', progress=True, 
                  multi_level_index=False)
df.drop(['Open','High','Low','Volume'], axis=1, inplace=True)
df.loc[:,'Be'] = df.loc[:,'Close'].shift(month)
df = df.dropna(axis=0)
df.iloc[-1,1] = 1000

start = df.index[0]
start = start.strftime('%Y-%m-%d')

# 실행
BH_return = buy_and_hold_return(df)[0]
year = Years(df)
BH_CAGR = CAGR(BH_return, year)
BH_MDD = buy_and_hold_return(df)[1]
Before_Model_return = Before_Model(df, tax)[0]
Before_Model_CAGR = CAGR(Before_Model_return, year)
Before_Model_trade_count = Before_Model(df, tax)[1]
Before_Model_MDD = Before_Model(df, tax)[2]


# 출력
print()
print(f'GLD Monthly trend invest : {month}개월전 가격비교')
print(f"Invest period : {start} ~ {end}, {round(year, 1)}년")
print()
print("Buy and holding Return : {:.2%}".format(BH_return))
print("Buy and holding CAGR : {:.2%}".format(BH_CAGR))
print("Buy and holding MDD : {:.2%}".format(BH_MDD))
print()
print("Before months Return : {:.2%}".format(Before_Model_return))
print("Before months CAGR : {:.2%}".format(Before_Model_CAGR))
print(f"Before months trade_count : {Before_Model_trade_count}")
print("Before months MDD : {:.2%}".format(Before_Model_MDD))