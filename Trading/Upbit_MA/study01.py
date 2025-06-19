import pyupbit as pu
import time

access_key = ""
secret_key = ""
upbit = pu.Upbit(access_key, secret_key)

tickers = pu.get_tickers(fiat="KRW")

for ticker in tickers:
    if ticker == "KRW-BTC":
        df = pu.get_ohlcv(ticker, interval="day")
        print(df['close'].tail(20))
        print("-" * 30)
        print(df.index[-1], ":", df['close'].iloc[-1])
        break




# balance = upbit.get_balances()
# print("Balance:", balance)

# for coin_balance in balance:
#     ticker = coin_balance['currency']
#     if ticker == "KRW" or ticker == "APENFT":
#         continue

#     print(f"Ticker: {ticker}, Balance: {coin_balance['balance']}")
#     print(f"Avg Buy Price: {coin_balance['avg_buy_price']}")
#     current_price = pu.get_current_price(f"KRW-{ticker}")
#     수익률 = (current_price - float(coin_balance['avg_buy_price'])) / float(coin_balance['avg_buy_price']) * 100
#     수익률 = round(수익률, 2)  # Round to 2 decimal places
#     print(f"Return: {수익률}%")
  

#     if 수익률 < -0.6:
#         upbit.sell_limit_order(f"KRW-{ticker}", pu.get_tick_size(current_price * 1.09), float(coin_balance['balance'])/20)
#         print(f"Sell order placed for {ticker} at {pu.get_tick_size(current_price * 1.09)} KRW")

#     print("-" * 30)




"""
Coins = pu.get_tickers(fiat="KRW")
for coin in Coins:
    print(coin, pu.get_current_price(coin))
    time.sleep(0.1)  # To avoid hitting the rate limit

    if coin == "KRW-BTC":
        upbit.buy_market_order(coin, 5000)  # Buy BTC with 5,000 KRW
        print("Buy done", coin)
"""

# btc_balance = upbit.get_balance("KRW-BTC")  # Check balance of KRW-BTC
# upbit.sell_market_order("KRW-BTC", btc_balance)

# btc_balance = upbit.get_balance("KRW-BTC")
# print("Sell done", btc_balance)

# Get current price of BTC
# btc_price = pu.get_current_price("KRW-BTC")
# buy_price = pu.get_tick_size(btc_price * 0.99)

# won = 10000

# upbit.buy_limit_order("KRW-BTC", buy_price, (won / buy_price))
# print("Buy limit order placed at", buy_price, "for", won, "KRW worth of BTC")
