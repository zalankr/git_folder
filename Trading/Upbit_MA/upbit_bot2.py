import pyupbit as pu
import time
import pandas as pd
# import kakao_alert

# 업비트 계좌 연결
access_key = 
secret_key =   # 본인 값으로 변경

upbit = pu.Upbit(access_key, secret_key)

# RSI 계산
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

# 이동평균선
def GetMA(ohlcv, period=20, st=-1):
    close = ohlcv['close'].astype(float)
    ma = close.rolling(window=period).mean()
    return float(ma.iloc[st])

# 현재가 조회
def GetCurrentPrice(ticker):
    price = pu.get_current_price(ticker)
    return price

# 거래대금 상위 코인 리스트 가져오기
def GetTopCoinlist(interval="day", top=10):
    print(f"Getting top {top} coins by trading volume in {interval} interval...")
    tickers = pu.get_tickers(fiat="KRW")
    dic_coin_money = {}

    for ticker in tickers:
        try:
            df = pu.get_ohlcv(ticker, interval=interval)
            if df is not None and 'value' in df:
                value = df['value'].iloc[-1] + df['value'].iloc[-2]
                dic_coin_money[ticker] = value
            time.sleep(0.05)
        except Exception as e:
            print(f"Error processing {ticker}: {e}")

    dic_sorted_coin_money = sorted(dic_coin_money.items(), key=lambda x: x[1], reverse=True)
    coin_list = [coin_data[0] for coin_data in dic_sorted_coin_money[:top]]

    print(f"Top {top} coins by trading volume in {interval} interval:")
    return coin_list

# 코인이 리스트에 있는지 확인
def CheckCoinList(coin_list, ticker):
    return ticker in coin_list

# 수익률 계산
def GetRevenueRate(balances, Ticker):
    revenue_rate = 0.0
    for value in balances:
        try:
            if not isinstance(value, dict):
                continue
            unit_currency = value.get('unit_currency')
            currency = value.get('currency')
            avg_buy_price = value.get('avg_buy_price')
            if unit_currency is None or currency is None or avg_buy_price in (None, ''):
                continue
            realTicker = unit_currency + "-" + currency
            if Ticker == realTicker:
                time.sleep(0.05)
                nowPrice = pu.get_current_price(realTicker)
                if nowPrice is None or float(avg_buy_price) == 0:
                    continue
                revenue_rate = (float(nowPrice) - float(avg_buy_price)) * 100.0 / float(avg_buy_price)
                break
        except Exception as e:
            print(f"GetRevenueRate error: {e}")
    return revenue_rate

# 해당 코인을 보유 중인지 확인
def IsHasCoin(balances, Ticker):
    HasCoin = False
    for value in balances:
        if not isinstance(value, dict):
            continue
        try:
            unit_currency = value.get('unit_currency')
            currency = value.get('currency')
            if unit_currency is None or currency is None:
                continue
            realTicker = unit_currency + "-" + currency
            if Ticker == realTicker:
                HasCoin = True
                break
        except Exception as e:
            print(f"IsHasCoin error: {e}")
    return HasCoin

# 실행 시작
balances = upbit.get_balances()
TopCoinlist = GetTopCoinlist(interval="week", top=10)
risky_coin_list = ['KRW-BORA', 'KRW-CHZ', 'KRW-DOGE', 'KRW-SNT', 'KRW-SAND']
Lovely_coin_list = ['KRW-BTC', 'KRW-ETH', 'KRW-XRP', 'KRW-ADA', 'KRW-SOL']
Tickers = pu.get_tickers(fiat="KRW")

for ticker in Tickers:
    try:
        if not CheckCoinList(TopCoinlist, ticker):
            continue
        if CheckCoinList(risky_coin_list, ticker):
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

        if IsHasCoin(balances, ticker):
            print(f"{ticker} is already owned.")
        else:
            print(f"{ticker} is not owned.")
        
        time.sleep(0.05)  # To avoid hitting the API rate limit

        # if rsi60_min <= 30:
        #     print(f"RSI60 is below 30 for {ticker}, potential buy signal.")
        #     kakao_alert.SendMessage(f"{ticker} RSI60 is below 30, potential buy signal.")

    except Exception as e:
        print(f"Error processing {ticker}: {e}")
