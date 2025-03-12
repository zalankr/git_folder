import pandas as pd
import numpy as np
import yfinance as yf

# 18개월전 투자 MDD
def max_drawdown(trade):
    """
    거래 데이터에서 Max Drawdown 계산
    :param trade: 매수/매도 가격을 포함한 pandas DataFrame
    :return: Max Drawdown 값
    """
    trade['cum_max'] = trade['Sell'].cummax()
    trade['drawdown'] = trade['Sell'] / trade['cum_max'] - 1
    return trade['drawdown'].min()

# N개월전 가격 비교 투자
def Before_Model(df, tax):
    bsignal = df['Close'] >= df['Be']
    ssignal = df['Close'] < df['Be']

    differ = bsignal != bsignal.shift(1)

    df.loc[differ & bsignal, 'Buy'] = df['Close']
    df.loc[differ & ssignal, 'Sell'] = df['Close']

    # 매수 및 매도 시점 필터링
    trade = df.loc[df['Buy'].notna() | df['Sell'].notna(), ['Buy', 'Sell']].copy()

    # 매수와 매도 인덱스를 초기화하여 정렬 문제 해결
    buy_prices = trade['Buy'].dropna().reset_index(drop=True)
    sell_prices = trade['Sell'].dropna().reset_index(drop=True)

    # 매수-매도 쌍의 길이를 맞추기
    min_len = min(len(buy_prices), len(sell_prices))

    trade = pd.DataFrame({
        'Buy': buy_prices[:min_len],
        'Sell': sell_prices[:min_len]
    })

    # 수익률 계산
    trade['return'] = (trade['Sell'] * (1 - tax)) / (trade['Buy'] * (1 + tax))

    # 누적 수익률 계산
    cacul = trade['return'].cumprod().iloc[-1] if not trade.empty else 1

    # MDD 계산
    mdd = max_drawdown(trade) if not trade.empty else 0

    return cacul, len(trade), mdd

# Buy & hold에서 MDD 산출
def BNH_MDD(df):
    df = df.copy()
    df['cum_max'] = df['Close'].cummax()
    df['drawdown'] = df['Close'] / df['cum_max'] - 1
    return df['drawdown'].min()

# Buy and hold 수익률 계산
def buy_and_hold_return(df, tax):
    buy = df['Close'].iloc[0]
    sell = df['Close'].iloc[-1]

    ROI = (sell * (1 - tax)) / (buy * (1 + tax))
    max_dd = BNH_MDD(df)

    return ROI, max_dd

# 투자기간 계산
def Years(df):
    return (df.index[-1] - df.index[0]).days / 365

# CAGR 계산
def CAGR(ret, years):
    return ret**(1 / years) - 1 if years > 0 else 0

# GLD 데이터 로드
def Data_load(month, start, end):
    df = yf.download('GLD', start=start, end=end, auto_adjust=True, interval='1mo', progress=False, multi_level_index=False)
    df.drop(['Open', 'High', 'Low', 'Volume'], axis=1, inplace=True)

    df['Be'] = df['Close'].shift(month)
    df.dropna(inplace=True)

    return df

# GLD 투자 기간 및 세팅
start = '2004-12-01'
end = '2025-02-28'

# 수수료 및 슬리피지
tax = 0.0033 + 0.0002

# 실행
for month in range(1, 37):
    df = Data_load(month, start, end)
    year = Years(df)

    Before_Model_return, Before_Model_trade_count, Before_Model_MDD = Before_Model(df, tax)
    Before_Model_CAGR = CAGR(Before_Model_return, year)

    print(f"\nGLD Monthly trend invest : {month}개월전 가격비교")
    print(f"Invest period : {start} ~ {end}, {round(year, 1)}년")
    print(f"Before months Return : {Before_Model_return:.2%}")
    print(f"Before months CAGR : {Before_Model_CAGR:.2%}")
    print(f"Before months trade_count : {Before_Model_trade_count}")
    print(f"Before months MDD : {Before_Model_MDD:.2%}")

df = Data_load(1, start, end)
year = Years(df)

BH_return, BH_MDD = buy_and_hold_return(df, tax)
BH_CAGR = CAGR(BH_return, year)

print("\nGLD Buy and Hold Investment")
print(f"Invest period : {start} ~ {end}, {round(year, 1)}년")
print(f"Buy and holding Return : {BH_return:.2%}")
print(f"Buy and holding CAGR : {BH_CAGR:.2%}")
print(f"Buy and holding MDD : {BH_MDD:.2%}")
