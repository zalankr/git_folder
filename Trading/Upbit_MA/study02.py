import pyupbit as pu
import time

access_key = "Wl6CAHw8AtcYoFuxydCCzAVAv8AlgMNUe0EChW2x"
secret_key = "2cxa4xE5ocdpXUG3zN5K7slGGvGrW4X6lMIUz4lR"
upbit = pu.Upbit(access_key, secret_key)

coin = "KRW-BTC"
upbit.buy_market_order(coin, 5000)  # Buy BTC with 5,000 KRW
print("Buy done", coin)
