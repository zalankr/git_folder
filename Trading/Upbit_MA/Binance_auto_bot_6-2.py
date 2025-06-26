import ccxt
import time
import pandas as pd
import pprint


access = "Yzgeud8QXdfK5zoxQzoVdGRT0NVIyZamN9d6m3vFqn87P9zG5Iopdy91tP0d2bkZ"
secret = "bUvUeovdSKcceGBHuqksw7wdUC66tc5RCHbiF8WARN9rBWK4KR4DO2OLylZhmebG"

# binance 객체 생성
binance = ccxt.binance(config={
    'apiKey': access, 
    'secret': secret,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future'
    }
})

#포지션 잡을 코인을 설정합니다.
Target_Coin_Ticker = "BTC/USDT"
Target_Coin_Symbol = "BTCUSDT"

#해당 코인의 정보를 가져옵니다
btc = binance.fetch_ticker(Target_Coin_Ticker)
#현재 종가 즉 현재가를 읽어옵니다.
btc_price = btc['close']

pprint.pprint(btc)
