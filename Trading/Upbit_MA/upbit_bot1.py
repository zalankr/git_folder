import pyupbit as pu
import time
import pandas as pd
# import kakao_alert

# 업비트 계좌 연결
access_key = ""
secret_key = ""         # 본인 값으로 변경

#업비트 객체를 만들어요 액세스 키와 시크릿 키를 넣어서요.
upbit = pu.Upbit(access_key, secret_key)

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

#티커에 해당하는 코인의 수익율을 구해서 리턴하는 함수.
def GetRevenueRate(balances, Ticker):
    revenue_rate = 0.0
    for value in balances:
        try:
            if not isinstance(value, dict):
                continue
            unit_currency = value.get('unit_currency')
            currency = value.get('currency')
            avg_buy_price = value.get('avg_buy_price')
            if unit_currency is None or currency is None or avg_buy_price is None or avg_buy_price == '':
                continue
            realTicker = unit_currency + "-" + currency
            if Ticker == realTicker:
                time.sleep(0.05)
                
                # 현재 가격을 가져옵니다.
                nowPrice = pu.get_current_price(realTicker)
                if nowPrice is None or float(avg_buy_price) == 0:
                    continue

                # 수익율을 구해서 넣어줍니다
                revenue_rate = (float(nowPrice) - float(avg_buy_price)) * 100.0 / float(avg_buy_price)
                break

        except Exception as e:
            print("GetRevenueRate error:", e)

    return revenue_rate

#티커에 해당하는 코인이 매수된 상태면 참을 리턴하는함수
def IsHasCoin(balances,Ticker):
    HasCoin = False
    for value in balances:
        realTicker = value['unit_currency'] + "-" + value['currency']
        if Ticker == realTicker:
            HasCoin = True
    return HasCoin

#내가 가진 잔고 데이터를 다 가져온다.
balances = upbit.get_balances()

# 거래대금 상위 코인 리스트
TopCoinlist = GetTopCoinlist(interval="week", top=10)

# 위험한 코인 리스트
risky_coin_list = ['KRW-BORA', 'KRW-CHZ', 'KRW-DOGE', 'KRW-SNT', 'KRW-SAND']

# 나의 코인
Lovely_coin_list = ['KRW-BTC', 'KRW-ETH', 'KRW-XRP', 'KRW-ADA', 'KRW-SOL']

Tickers = pu.get_tickers(fiat="KRW")

for ticker in Tickers:
    try:
        # 거래대금이 많은 코인인지 확인, 아니면 스킵        
        if CheckCoinList(TopCoinlist, ticker) == False:
            continue
        # 위험한 코인인지 확인, 맞으면 스킵
        if CheckCoinList(risky_coin_list, ticker) == True:
            continue

        df_60 = pu.get_ohlcv(ticker, interval="minute60")
        if df_60 is None:
            print(f"Error: OHLCV data is None for {ticker}, skipping...")
            continue
        rsi60_min_before = GetRSI(df_60, period=14, st=-2)
        rsi60_min = GetRSI(df_60, period=14, st=-1)

        revenue_rate = GetRevenueRate(balances, ticker)
        print(f"Ticker: {ticker}, RSI60 before: {rsi60_min_before} -> RSI60 now: {rsi60_min}")
        print("Revenue Rate: {:.2f}%".format(revenue_rate))

        if IsHasCoin(balances, ticker) == True:
            print(f"{ticker} is already owned.")
        else:
            print(f"{ticker} is not owned.")

        # if rsi60_min <= 30:
        #     # 분할매수를 진행한다
            

        #     print(f"RSI60 is below 30 for {ticker}, potential buy signal.")


            # kakao_alert.SendMessage(f"{ticker} RSI60 is below 30, potential buy signal.")

        # print(f"Processing ticker: {ticker}, is Target")
    except Exception as e:
        print(f"Error processing {ticker}: {e}")

# Chapter 5-2 Next

# kakao_alert.SendMessage(f"현재 20일 이동평균선(MA)은 {MAnow}입니다.")
# kakao_alert.SendMessage(f"현재 가격은 {current_price}입니다.")

# if current_price > MAnow:
#     kakao_alert.SendMessage("현재 가격이 20일 이동평균선(MA)보다 높습니다. 매수 신호입니다.")
# if current_price < MAnow:
#     kakao_alert.SendMessage("현재 가격이 20일 이동평균선(MA)보다 낮습니다. 매도 신호입니다.")