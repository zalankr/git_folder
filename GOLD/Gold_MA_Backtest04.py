import pandas as pd
import numpy as np
from datetime import datetime

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
    buy_prices = trade['Buy'].dropna().astype(float).reset_index(drop=True)
    sell_prices = trade['Sell'].dropna().astype(float).reset_index(drop=True)

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
    buy = float(df['Close'].iloc[0])
    sell = float(df['Close'].iloc[-1])

    ROI = (sell * (1 - tax)) / (buy * (1 + tax))
    max_dd = BNH_MDD(df)

    return ROI, max_dd

# 투자기간 계산
def Years(df):
    return (df.index[-1] - df.index[0]).days / 365

# CAGR 계산
def CAGR(ret, years):
    return ret**(1 / years) - 1 if years > 0 else 0

# GLD 데이터 로드 # CSV 불러오기
def csv_to_dataframe(file_path, month):
    try:
        # CSV 파일을 읽어 DataFrame으로 변환
        df = pd.read_csv(file_path)
        
        df['Be'] = df['Close'].shift(month)
        df.dropna(inplace=True)
        df.iat[-1,2] = 100000

        # Date 형식 변환
        df['Date'] = pd.to_datetime(df['Date'], format='%m/%d/%Y')
        df.set_index('Date', inplace=True)

        return df
    except Exception as e:
        print(f"오류 발생: {e}")
        return None

file_path = 'C:/Users/ilpus/PythonProjects/git_folder/Gold Futures Historical Data.csv'

# GLD 투자 기간 및 세팅
start = '1975-12-01'
end = '2025-03-13'

# 수수료 및 슬리피지
tax = 0.0033 + 0.0002

# 실행
for month in range(18, 61):
    df = csv_to_dataframe(file_path, month)
    year = Years(df)

    Before_Model_return, Before_Model_trade_count, Before_Model_MDD = Before_Model(df, tax)
    Before_Model_CAGR = CAGR(Before_Model_return, year)

    print(f"\nGLD Monthly trend invest : {month}개월전 가격비교")
    print(f"Invest period : {start} ~ {end}, {round(year, 1)}년")
    print(f"Before months Return : {Before_Model_return:.2%}")
    print(f"Before months CAGR : {Before_Model_CAGR:.2%}")
    print(f"Before months trade_count : {Before_Model_trade_count}")
    print(f"Before months MDD : {Before_Model_MDD:.2%}")

df1 = csv_to_dataframe(file_path, 0)
year = Years(df1)

BH_return, BH_MDD = buy_and_hold_return(df1, tax)
BH_CAGR = CAGR(BH_return, year)

print("\nGLD Buy and Hold Investment")
print(f"Invest period : {start} ~ {end}, {round(year, 1)}년")
print(f"Buy and holding Return : {BH_return:.2%}")
print(f"Buy and holding CAGR : {BH_CAGR:.2%}")
print(f"Buy and holding MDD : {BH_MDD:.2%}")
