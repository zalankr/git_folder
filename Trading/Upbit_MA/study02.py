import pyupbit as pu
import time

access_key = ""
secret_key = ""
upbit = pu.Upbit(access_key, secret_key)

coin = "KRW-BTC"
upbit.buy_market_order(coin, 5000)  # Buy BTC with 5,000 KRW
print("Buy done", coin)
