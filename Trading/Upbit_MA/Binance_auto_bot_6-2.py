'''
하다가 잘 안되시면 계속 내용이 추가되고 있는 아래 FAQ를 꼭꼭 체크하시고

주식/코인 자동매매 FAQ
https://blog.naver.com/zacra/223203988739

그래도 모르겠다면 클래스 댓글, 블로그 댓글, 단톡방( https://blog.naver.com/zacra/223111402375 )에 질문주세요! ^^

'''
import ccxt
import time
import pandas as pd
import pprint


access = "Yzgeud8QXdfK5zoxQzoVdGRT0NVIyZamN9d6m3vFqn87P9zG5Iopdy91tP0d2bkZ"
secret = "bUvUeovdSKcceGBHuqksw7wdUC66tc5RCHbiF8WARN9rBWK4KR4DO2OLylZhmebG"         # 본인 값으로 변경

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

# Binance 서버 시간과 동기화  > 윈도우 우하단 일자 우클릭 후 날짜와 시간 설정창으로 들어가서 시간 지금 동기화
binance.load_markets()
server_time = binance.fetch_time()
local_time = int(time.time() * 1000)
time_diff = server_time - local_time
if abs(time_diff) > 1000:
    print(f"Adjusting for time difference: {time_diff} ms")
    time.sleep(abs(time_diff) / 1000)

#해당 코인의 정보를 가져옵니다
btc = binance.fetch_ticker(Target_Coin_Ticker)
#현재 종가 즉 현재가를 읽어옵니다.
btc_price = btc['close']

print(btc['close'])

# 시장가 taker 0.04, 지정가 maker 0.02
# 시장가 숏 포지션 잡기
# print(binance.create_market_sell_order(Target_Coin_Ticker, 0.001)
# 시장가 롱 포지션 잡기(숏 정리)
# print(binance.create_market_buy_order(Target_Coin_Ticker, 0.001)

# 잔고 데이타 가져오기
balance = binance.fetch_balance(params={"type": "future"})
# pprint.pprint(balance)

print(balance['USDT'])

amt = 0  # 수량 정보 0이면 매수전(포지션 잡기 전), 양수면 롱 포지션 상태, 음수면 숏 포지션 상태
entryPrice = 0  # 평균 매입 단가. 따라서 물을 타면 변경 된다.
leverage = 1  # 레버리지, 앱이나 웹에서 설정된 값을 가져온다.
unrealizedProfit = 0  # 블신 예상 손익..그냥 참고용

for posi in balance['info']['positions']:
    if posi['symbol'] == Target_Coin_Symbol:
        amt = float(posi['positionAmt'])
        entryPrice = float(posi['entryPrice'])
        unrealizedProfit = float(posi['unrealizedProfit'])
        leverage = float(posi['leverage'])

print("amt:", amt)
print("entryPrice:",entryPrice)
print("leverage:",leverage)
print("unrealizedProfit:",unrealizedProfit)

abs_amt = abs(amt)

short_entryPrice = entryPrice * 0.999 # 숏 정리 시 0.999 정도 넣어주면 수익 0.1% * 레버리지 100배 시 10% 수익 나옴
long_entryPrice = entryPrice * 0.999 # 숏 정리 시 0.999 정도 넣어주면 수익 0.1% * 레버리지 100배 시 10% 수익 나옴
# 지정가 숏 포지션 잡기
# print(binance.create_limit_sell_order(Target_Coin_Ticker, 0.001, btc_price)
# 지정가 롱 포지션 잡기
# print(binance.create_limit_buy_order(Target_Coin_Ticker, 0.001, btc_price)

# 지정가 롱 포지션 잡기(숏 정리, 잔량, 목표가격)
# print(binance.create_limit_buy_order(Target_Coin_Ticker, abs_amt, short_entryPrice)

# 지정가 숏 포지션 잡기(롱 정리, 잔량, 목표가격)
# print(binance.create_limit_sell_order(Target_Coin_Ticker, abs_amt, long_entryPrice)

# chapter 6-3