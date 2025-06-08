import pyupbit as pu
import time

access_key = "Wl6CAHw8AtcYoFuxydCCzAVAv8AlgMNUe0EChW2x"
secret_key = "2cxa4xE5ocdpXUG3zN5K7slGGvGrW4X6lMIUz4lR"
upbit = pu.Upbit(access_key, secret_key)

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

chapter 3-5