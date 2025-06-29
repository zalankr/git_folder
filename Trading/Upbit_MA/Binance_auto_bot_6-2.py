'''
하다가 잘 안되시면 계속 내용이 추가되고 있는 아래 FAQ를 꼭꼭 체크하시고
주식/코인 자동매매 FAQ
https://blog.naver.com/zacra/223203988739
그래도 모르겠다면 클래스 댓글, 블로그 댓글, 단톡방( https://blog.naver.com/zacra/223111402375 )에 질문주세요! ^^
'''
# Binance 서버 시간과 동기화  > 윈도우 우하단 일자 우클릭 후 날짜와 시간 설정창으로 들어가서 시간 지금 동기화

import ccxt
import time
import pandas as pd
import pprint

access = "Yzgeud8QXdfK5zoxQzoVdGRT0NVIyZamN9d6m3vFqn87P9zG5Iopdy91tP0d2bkZ"
secret = "bUvUeovdSKcceGBHuqksw7wdUC66tc5RCHbiF8WARN9rBWK4KR4DO2OLylZhmebG"         # 본인 값으로 변경

# binance 객체 생성
binanceX = ccxt.binance(config={
    'apiKey': access, 
    'secret': secret,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future'
    }
})

binanceX.load_markets()
server_time = binanceX.fetch_time()
local_time = int(time.time() * 1000)
time_diff = server_time - local_time
if abs(time_diff) > 1000:
    print(f"Adjusting for time difference: {time_diff} ms")
    time.sleep(abs(time_diff) / 1000)

#RSI지표 수치를 구해준다. 첫번째: 분봉/일봉 정보, 두번째: 기간, 세번째: 기준 날짜
def GetRSI(ohlcv,period,st):
    ohlcv["close"] = ohlcv["close"]
    delta = ohlcv["close"].diff()
    up, down = delta.copy(), delta.copy()
    up[up < 0] = 0
    down[down > 0] = 0
    _gain = up.ewm(com=(period - 1), min_periods=period).mean()
    _loss = down.abs().ewm(com=(period - 1), min_periods=period).mean()
    RS = _gain / _loss
    return float(pd.Series(100 - (100 / (1 + RS)), name="RSI").iloc[st])

#이동평균선 수치를 구해준다 첫번째: 분봉/일봉 정보, 두번째: 기간, 세번째: 기준 날짜
def GetMA(ohlcv,period,st):
    close = ohlcv["close"]
    ma = close.rolling(period).mean()
    return float(ma.iloc[st])

#분봉/일봉 캔들 정보를 가져온다 첫번째: 바이낸스 객체, 두번째: 코인 티커, 세번째: 기간 (1d,4h,1h,15m,10m,1m ...)
def GetOhlcv(binance, Ticker, period):
    btc_ohlcv = binance.fetch_ohlcv(Ticker, period)
    df = pd.DataFrame(btc_ohlcv, columns=['datetime', 'open', 'high', 'low', 'close', 'volume'])
    df['datetime'] = pd.to_datetime(df['datetime'], unit='ms')
    df.set_index('datetime', inplace=True)
    return df

#스탑로스를 걸어놓는다. 해당 가격에 해당되면 바로 손절한다. 첫번째: 바이낸스 객체, 두번째: 코인 티커, 세번째: 손절 수익율 (1.0:마이너스100% 청산, 0.9:마이너스 90%, 0.5: 마이너스 50%)
def SetStopLoss(binance, Ticker, cut_rate):
    time.sleep(0.1)
    #주문 정보를 읽어온다.
    orders = binance.fetch_orders(Ticker)

    StopLossOk = False
    for order in orders:

        if order['status'] == "open" and order['type'] == 'stop_market':
            #print(order)
            StopLossOk = True
            break

    #스탑로스 주문이 없다면 주문을 건다!
    if StopLossOk == False:

        time.sleep(10.0)

        #잔고 데이타를 가지고 온다.
        balance = binance.fetch_balance(params={"type": "future"})
        time.sleep(0.1)
                                
        amt = 0
        entryPrice = 0
        leverage = 0
        #평균 매입단가와 수량을 가지고 온다.
        for posi in balance['info']['positions']:
            if posi['symbol'] == Ticker.replace("/", ""):
                entryPrice = float(posi['entryPrice'])
                amt = float(posi['positionAmt'])
                leverage = float(posi['leverage'])


        #롱일땐 숏을 잡아야 되고
        side = "sell"
        #숏일땐 롱을 잡아야 한다.
        if amt < 0:
            side = "buy"

        danger_rate = ((100.0 / leverage) * cut_rate) * 1.0

        #롱일 경우의 손절 가격을 정한다.
        stopPrice = entryPrice * (1.0 - danger_rate*0.01)

        #숏일 경우의 손절 가격을 정한다.
        if amt < 0:
            stopPrice = entryPrice * (1.0 + danger_rate*0.01)

        params = {
            'stopPrice': stopPrice,
            'closePosition' : True
        }

        print("side:",side,"   stopPrice:",stopPrice, "   entryPrice:",entryPrice)
        #스탑 로스 주문을 걸어 놓는다.
        print(binance.create_order(Ticker,'STOP_MARKET',side,abs(amt),stopPrice,params))

        print("####STOPLOSS SETTING DONE ######################")

#구매할 수량을 구한다.  첫번째: 돈(USDT), 두번째:코인 가격, 세번째: 비율 1.0이면 100%, 0.5면 50%
def GetAmount(usd, coin_price, rate):

    target = usd * rate 

    amout = target/coin_price
    # 아래 조건 때문에 최소 구매 수량은 0.001
    if amout < 0.001:
        amout = 0.001

    #print("amout", amout)
    return amout

#거래할 코인의 현재가를 가져온다. 첫번째: 바이낸스 객체, 두번째: 코인 티커
def GetCoinNowPrice(binance,Ticker):
    coin_info = binance.fetch_ticker(Ticker)
    coin_price = coin_info['last'] # coin_info['close'] == coin_info['last'] 

    return coin_price

# 시장가 taker 0.04, 지정가 maker 0.02
# 시장가 숏 포지션 잡기
# print(binance.create_market_sell_order(Target_Coin_Ticker, 0.001)
# 시장가 롱 포지션 잡기(숏 정리)
# print(binance.create_market_buy_order(Target_Coin_Ticker, 0.001)

#포지션 잡을 코인을 설정합니다.
Target_Coin_Ticker = "BTC/USDT"
Target_Coin_Symbol = "BTCUSDT"
#binance 변수 만들기
binance = binanceX
# 캔들정보 가져오기
df_15 = GetOhlcv(binance, Target_Coin_Ticker, "15m")

# 최근 3개의 종가 데이터
print("Price:", df_15['close'][-3:], "->", df_15['close'][-2:], "->", df_15['close'][-1:])
# 최근 3개의 5일선 데이터
print("MA5:", GetMA(df_15, 5, -3), "->", GetMA(df_15, 5, -2), "->", GetMA(df_15, 5, -1))
# 최근 3개의 RSI14 데이터
print("RSI14:", GetRSI(df_15, 14, -3), "->", GetRSI(df_15, 14, -2), "->", GetRSI(df_15, 14, -1))

# 잔고 데이타 가져오기
balance = binanceX.fetch_balance(params={"type": "future"})
# pprint.pprint(balance)

print(balance['USDT'])
print("Total Money:", float(balance['USDT']['total']))
print("Remain Money:", float(balance['USDT']['free']))

amt = 0  # 수량 정보 0이면 매수전(포지션 잡기 전), 양수면 롱 포지션 상태, 음수면 숏 포지션 상태
entryPrice = 0  # 평균 매입 단가. 따라서 물을 타면 변경 된다.
leverage = 1  # 레버리지, 앱이나 웹에서 설정된 값을 가져온다.
unrealizedProfit = 0  # 미실현 예상 손익..그냥 참고용
isolated = True #격리모드인지 
short_entryPrice = entryPrice * 0.999 # 숏 정리 시 0.999 정도 넣어주면 수익 0.1% * 레버리지 100배 시 10% 수익 나옴
long_entryPrice = entryPrice * 0.999 # 숏 정리 시 0.999 정도 넣어주면 수익 0.1% * 레버리지 100배 시 10% 수익 나옴

for posi in balance['info']['positions']:
    if posi['symbol'] == Target_Coin_Symbol:
        amt = float(posi['positionAmt'])
        entryPrice = float(posi['entryPrice'])
        unrealizedProfit = float(posi['unrealizedProfit'])
        leverage = float(posi['leverage'])
        isolated = posi['isolated']
        break

#################################################################################################################
#영상엔 없지만 격리모드가 아니라면 격리모드로 처음 포지션 잡기 전에 셋팅해 줍니다,.
if isolated == False:
    try:
        print(binanceX.fapiPrivate_post_margintype({'symbol': Target_Coin_Symbol, 'marginType': 'ISOLATED'}))
    except Exception as e:
        try:
            print(binanceX.fapiprivate_post_margintype({'symbol': Target_Coin_Symbol, 'marginType': 'ISOLATED'}))
        except Exception as e:
            print("error:", e)
#################################################################################################################

print("amt:", amt)
print("entryPrice:",entryPrice)
print("leverage:",leverage)
print("unrealizedProfit:",unrealizedProfit)

# 해당 코인 가격을 가져온다.
coin_price = GetCoinNowPrice(binance, Target_Coin_Ticker)


# 레버리지에 따른 매수 가능 수량 구하기
Max_Amount = round(GetAmount(10000, coin_price, 0.5), 3) * leverage
# Max_Amount = round(GetAmount(float(balance['USDT']['total']), coin_price, 0.5), 3) * leverage
one_percent_amount  = Max_Amount / 100.0
first_amount = round(one_percent_amount * 5.0, 3)

if first_amount < 0.001:
    first_amount = 0.001
print("Max_Amount:", Max_Amount)
print("one_percent_amount:", one_percent_amount)
print("first_bamount:", first_amount)
"""
5  +5
10 +10
20 +20
40 +40
80
"""

# 최근 5일선 3개 데이터
ma5_before3 = GetMA(df_15, 5, -4)
ma5_before2 = GetMA(df_15, 5, -3)
ma5 = GetMA(df_15, 5, -2)

# 최근 20일선 데이터
ma20 = GetMA(df_15, 20, -2)

# RSI14 데이터
rsi14 = GetRSI(df_15, 14, -1)

# 음수를 제거한 절대값 수량 ex -0.1 > 0.1로 변경
abs_amt = abs(amt)

# amt가 0이면 포지션 없음
if amt == 0:
    print("------No Position")
    # 5일선이 20일선 위에 있는데 5일선이 하락추세로 꺾일때 숏 포지션 잡기
    if ma5 > ma20 and ma5_before3 < ma5_before2 and ma5_before2 > ma5 and rsi14 >=35 :
        binance.cancel_all_orders(Target_Coin_Ticker)
        time.sleep(0.1)
        print("sell short: binance.create_limit_sell_order(Target_Coin_Ticker, first_amount, coin_price)")
        # 스탑로스
        print("SetStopLoss(binance, Target_Coin_Ticker, 0.5)")

    # 5일선이 20일선 아래에 있는데 5일선이 상승추세로 꺾일때 롱 포지션 잡기
    if ma5 < ma20 and ma5_before3 > ma5_before2 and ma5_before2 < ma5 and rsi14 <=65 :
        binance.cancel_all_orders(Target_Coin_Ticker)
        time.sleep(0.1)
        print("buy long: binance.create_limit_buy_order(Target_Coin_Ticker, afirst_amount, coin_price)")
        # 스탑로스
        print("SetStopLoss(binance, Target_Coin_Ticker, 0.5)")



# 0이 아니라면 포지션 있는 상태
else:
    # 음수면 숏포지션
    if amt < 0:
        print("------Short Position")
    # 양수면 롱포지션
    else:
        print("------Long Position")

# 스탑로스
print("SetStopLoss(binance, Target_Coin_Ticker, 0.5)")


# 지정가 숏 포지션 잡기
# print(binance.create_limit_sell_order(Target_Coin_Ticker, 0.001, btc_price)
# 지정가 롱 포지션 잡기
# print(binance.create_limit_buy_order(Target_Coin_Ticker, 0.001, btc_price)
# 지정가 롱 포지션 잡기(숏 정리, 잔량, 목표가격)
# print(binance.create_limit_buy_order(Target_Coin_Ticker, abs_amt, short_entryPrice)
# 지정가 숏 포지션 잡기(롱 정리, 잔량, 목표가격)
# print(binance.create_limit_sell_order(Target_Coin_Ticker, abs_amt, long_entryPrice)

#해당 코인의 정보를 가져옵니다
btc = binanceX.fetch_ticker(Target_Coin_Ticker)
#현재 종가 즉 현재가를 읽어옵니다.
btc_price = btc['close']


# chapter 6-4