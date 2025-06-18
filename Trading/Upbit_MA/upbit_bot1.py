import pyupbit as pu
import time
import pandas as pd
# import kakao_alert

# Function to calculate the Relative Strength Index (RSI)
def GetRSI(ohlcv, period=14, st=-1):
    ohlcv['close'] = ohlcv['close'].astype(float)
    delta = ohlcv['close'].diff()
    up, down = delta.copy(), delta.copy()
    up[up < 0] = 0
    down[down > 0] = 0
    _gain = up.ewm(com=(period - 1), min_periods=period).mean()
    _loss = down.abs().ewm(com=(period - 1), min_periods=period).mean()
    rs = _gain / _loss
    return float(pd.Series(100 - (100 / (1 + rs)), name='RSI').iloc[st])

# Function to calculate the Moving Average (MA)
def GetMA(ohlcv, period=20, st=-1):
    close = ohlcv['close'].astype(float)
    ma = close.rolling(window=period).mean()
    return float(ma.iloc[st])

# Function to get the current price of a ticker
def GetCurrentPrice(ticker):
    price = pu.get_current_price(ticker)
    return price

# 거래대금 상위 코인 티커 산출
def GetTopCoinlist(interval="day", top=10):
    print(f"Getting top {top} coins by trading volume in {interval} interval...")

    # Get tickers for KRW market
    tickers = pu.get_tickers(fiat="KRW")
    dic_coin_money = {}

    for ticker in tickers:
        try:
            df = pu.get_ohlcv(ticker, interval=interval)
            value = df['value'].iloc[-1] + df['value'].iloc[-2]
            dic_coin_money[ticker] = value
            # print(f"Ticker: {ticker}, Value: {dic_coin_money[ticker]}")
            time.sleep(0.05)  # To avoid hitting the API rate limit            
        except Exception as e:
            print(f"Error processing {ticker}: {e}")

    dic_sorted_coin_money = sorted(dic_coin_money.items(), key=lambda x: x[1], reverse=True)

    coin_list = []
    cnt = 0
    for coin_data in dic_sorted_coin_money:
        cnt += 1

        if cnt <= top:
            coin_list.append(coin_data[0])
        else:
            break

    print(f"Top {top} coins by trading volume in {interval} interval:")

    return coin_list

# 해당코인이 리스트안에 있는지 여부를 리턴
def CheckCoinList(coin_list, ticker):
    InCoinOK = False
    for cointicker in coin_list:
        if cointicker == ticker:
            InCoinOK = True
            break  

    return InCoinOK

# 거래대금 상위 코인 리스트
TopCoinlist = GetTopCoinlist(interval="day", top=5)

# for top_ticker in TopCoinlist:
#     print(f"Ticker: {top_ticker}")

# 위험한 코인 리스트
risky_coin_list = ['KRW-BORA', 'KRW-CHZ', 'KRW-DOGE', 'KRW-SNT', 'KRW-SAND']

# 나의 코인
Lovely_coin_list = ['KRW-BTC', 'KRW-ETH', 'KRW-XRP', 'KRW-ADA', 'KRW-SOL']


Tickers = pu.get_tickers(fiat="KRW")

for ticker in Tickers:
    try:
        if CheckCoinList(TopCoinlist, ticker) == False:
            continue
        if CheckCoinList(risky_coin_list, ticker) == True:
            continue

        print(f"Processing ticker: {ticker}, is Target")
    except Exception as e:
        print(f"Error processing {ticker}: {e}")

# Chapter 5-2 Next

# kakao_alert.SendMessage(f"현재 20일 이동평균선(MA)은 {MAnow}입니다.")
# kakao_alert.SendMessage(f"현재 가격은 {current_price}입니다.")

# if current_price > MAnow:
#     kakao_alert.SendMessage("현재 가격이 20일 이동평균선(MA)보다 높습니다. 매수 신호입니다.")
# if current_price < MAnow:
#     kakao_alert.SendMessage("현재 가격이 20일 이동평균선(MA)보다 낮습니다. 매도 신호입니다.")