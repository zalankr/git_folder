#-*-coding:utf-8 -*-
# Binance 서버 시간과 동기화  > 윈도우 우하단 일자 우클릭 후 날짜와 시간 설정창으로 들어가서 시간 지금 동기화

import time
import pandas as pd
import pprint
import myBinance #우리가 만든 함수들이 들어있는 모듈

# Binance 토큰 불러오기
with open("C:/Users/ilpus/Desktop/NKL_invest/bnnkr.txt") as f:
    access, secret = [line.strip() for line in f.readlines()]

# binance 객체 생성
"""
선물거래용 코드
binanceX = myBinance.ccxt.binance(config={
    'apiKey': access, 
    'secret': secret,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future'
    }
})
"""

# 현물거래용 코드
binanceX = myBinance.ccxt.binance(config={
    'apiKey': access, 
    'secret': secret,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'spot'  # 또는 생략 가능
    }
})

binanceX.load_markets()
server_time = binanceX.fetch_time()
local_time = int(time.time() * 1000)
time_diff = server_time - local_time
if abs(time_diff) > 1000:
    print(f"Adjusting for time difference: {time_diff} ms")
    time.sleep(abs(time_diff) / 1000)


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
df_15 = myBinance.GetOhlcv(binance, Target_Coin_Ticker, "15m")

# 최근 3개의 종가 데이터
print("Price:", df_15['close'][-3:], "->", df_15['close'][-2:], "->", df_15['close'][-1:])
# 최근 3개의 5일선 데이터
print("MA5:", myBinance.GetMA(df_15, 5, -3), "->", myBinance.GetMA(df_15, 5, -2), "->", myBinance.GetMA(df_15, 5, -1))
# 최근 3개의 RSI14 데이터
print("RSI14:", myBinance.GetRSI(df_15, 14, -3), "->", myBinance.GetRSI(df_15, 14, -2), "->", myBinance.GetRSI(df_15, 14, -1))

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
        print(binanceX.fapiprivate_post_margintype({'symbol': Target_Coin_Symbol, 'marginType': 'ISOLATED'}))
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
coin_price = myBinance.GetCoinNowPrice(binance, Target_Coin_Ticker)


# 레버리지에 따른 매수 가능 수량 구하기
Max_Amount = round(myBinance.GetAmount(10000, coin_price, 0.5), 3) * leverage
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
ma5_before3 = myBinance.GetMA(df_15, 5, -4)
ma5_before2 = myBinance.GetMA(df_15, 5, -3)
ma5 = myBinance.GetMA(df_15, 5, -2)

# 최근 20일선 데이터
ma20 = myBinance.GetMA(df_15, 20, -2)

# RSI14 데이터
rsi14 = myBinance.GetRSI(df_15, 14, -1)

# 음수를 제거한 절대값 수량 ex -0.1 > 0.1로 변경
abs_amt = abs(amt)

#타겟 레이트 0.001 
target_rate = 0.001
#타겟 수익율 0.1%
target_revenue_rate = target_rate * 100.0

# amt가 0이면 포지션 없음
if amt == 0:
    print("------No Position")
    # 5일선이 20일선 위에 있는데 5일선이 하락추세로 꺾일때 숏 포지션 잡기
    if ma5 > ma20 and ma5_before3 < ma5_before2 and ma5_before2 > ma5 and rsi14 >=35 :
        binance.cancel_all_orders(Target_Coin_Ticker)
        time.sleep(0.1)

        #해당 코인 가격을 가져온다.
        coin_price = myBinance.GetCoinNowPrice(binanceX, Target_Coin_Ticker)
        
        # 숏포지션 잡는 식
        print("sell short: binance.create_limit_sell_order(Target_Coin_Ticker, first_amount, coin_price)")
        # 스탑로스
        print("SetStopLoss(binance, Target_Coin_Ticker, 0.5)")

    # 5일선이 20일선 아래에 있는데 5일선이 상승추세로 꺾일때 롱 포지션 잡기
    if ma5 < ma20 and ma5_before3 > ma5_before2 and ma5_before2 < ma5 and rsi14 <=65 :
        binance.cancel_all_orders(Target_Coin_Ticker)
        time.sleep(0.1)

        #해당 코인 가격을 가져온다.
        coin_price = myBinance.GetCoinNowPrice(binanceX, Target_Coin_Ticker)

        #롯포지션 잡는 식
        print("buy long: binance.create_limit_buy_order(Target_Coin_Ticker, afirst_amount, coin_price)")
        # 스탑로스
        print("SetStopLoss(binance, Target_Coin_Ticker, 0.5)")



# 0이 아니라면 포지션 있는 상태
else:
    print("------------------------------------------------------")

    #현재까지 구매한 퍼센트! 현재 보유 수량을 1%의 수량으로 나누면 된다.
    buy_percent = abs_amt / one_percent_amount
    print("Buy Percent : ", buy_percent)

    # 수익율을 구한다!
    revenue_rate = (coin_price - entryPrice) / entryPrice * 100.0

    # 단 숏 포지션일 경우 수익이 나면 마이너스로 표시 되고 손실이 나면 플러스가 표시 되므로 -1을 곱하여 바꿔준다.
    if amt < 0:
        revenue_rate = revenue_rate * -1.0

    #레버리지를 곱한 실제 수익율
    leverage_revenu_rate = revenue_rate * leverage

    print("Revenue Rate : ", revenue_rate,", Real Revenue Rate : ", leverage_revenu_rate)  

    #손절 마이너스 수익율을 셋팅한다.
    danger_rate = -5.0
    #레버리지를 곱한 실제 손절 할 마이너스 수익율
    leverage_danger_rate = danger_rate * leverage

    print("Danger Rate : ", danger_rate,", Real Danger Rate : ", leverage_danger_rate)

    """
    5 + 5
    10 + 10
    20 + 20
    40 + 40
    80 + 20

    5+10
    15+10
    25+10
    35+10
    45+10
    55+10

    """
    #추격 매수 즉 물 탈 마이너스 수익율을 셋팅한다.
    water_rate = -1.0

    if buy_percent <= 5.0:
        water_rate = -0.5
    elif buy_percent <= 10.0:
        water_rate = -1.0
    elif buy_percent <= 20.0:
        water_rate = -2.0
    elif buy_percent <= 40.0:
        water_rate = -3.0
    elif buy_percent <= 80.0:
        water_rate = -5.0

    # 음수면 숏포지션
    if amt < 0:
        print("------Short Position")

        # 롱 포지션을 잡을 상황
        if ma5 < ma20 and ma5_before3 > ma5_before2 and ma5_before2 < ma5 :
            # 수익이 났다! 숏포지션을 청산하고 롱 포지션도 잡기
            if revenue_rate >= target_revenue_rate :
                print("buy/long")
                # 주문취소 후
                print("binance.cancel_all_orders(Target_Coin_Ticker)")
                time.sleep(0.1)

                # 해당 코인 가격을 가져오기
                coin_price = myBinance.GetCoinNowPrice(binanceX, Target_Coin_Ticker)

                # 롱 포지션 잡기
                print("buy long: binance.create_limit_buy_order(Target_Coin_Ticker, abs_amt + first_amount, coin_price)")

                # 스탑로스
                print("SetStopLoss(binance, Target_Coin_Ticker, 0.5)")


        #영상에서 빠져있는 중요한 부분!!! 숏인 상태에서는 숏을 잡을 만한 상황에서 물을 타야 겠죠?
        #즉 5일 선이 20일 선 위에 있고 하락추세로 꺾였을 때 물을 탑니다.
        #숏 포지션을 잡을만한 상황!!!!
        if ma5 > ma20 and ma5_before3 < ma5_before2 and ma5_before2 > ma5:
            #물탈 수량 
            water_amount = abs_amt

            if Max_Amount < abs_amt + water_amount:
                water_amount = Max_Amount - abs_amt

            #물탈 마이너스 수익율 보다 내 수익율이 작다면 물을 타자!!
            if revenue_rate <= water_rate and Max_Amount >= abs_amt + water_amount:

                #주문 취소후
                binanceX.cancel_all_orders(Target_Coin_Ticker)
                time.sleep(0.1)
                
                #해당 코인 가격을 가져온다.
                coin_price = myBinance.GetCoinNowPrice(binanceX, Target_Coin_Ticker)

                #숏 포지션을 잡는다
                #사실 여기는 시장가로 잡는게 맞습니다 나중에 챕터 7-4의 최종코드를 확인하세요!
                #print(binanceX.create_limit_sell_order(Target_Coin_Ticker, water_amount, coin_price))
                print("binanceX.create_order(Target_Coin_Ticker, 'limit', 'sell', water_amount, coin_price)")

                #스탑 로스 설정을 건다.
                print("SetStopLoss(binanceX,Target_Coin_Ticker,0.5)")
                
        
        if revenue_rate <= danger_rate and buy_percent >= 90.0 :
            print("buy/long")
            # 주문취소 후
            print("binance.cancel_all_orders(Target_Coin_Ticker)")
            time.sleep(0.1)

            # 해당 코인 가격을 가져오기
            coin_price = myBinance.GetCoinNowPrice(binanceX, Target_Coin_Ticker)

            # 롱 포지션 잡기
            print("buy long: binance.create_limit_buy_order(Target_Coin_Ticker, abs_amt / 2.0, coin_price)")

            # 스탑로스
            print("SetStopLoss(binance, Target_Coin_Ticker, 0.5)")

        




     #양수면 롱 포지션 상태
    else:
        print("-----Long Position")


        #숏 포지션을 잡을만한 상황!!!!
        if ma5 > ma20 and ma5_before3 < ma5_before2 and ma5_before2 > ma5:
            #수익이 났다!!! 롱 포지션 종료하고 숏 포지션도 잡아주자!
            if revenue_rate >= target_revenue_rate:

                #주문 취소후
                binanceX.cancel_all_orders(Target_Coin_Ticker)
                time.sleep(0.1)
                
                #해당 코인 가격을 가져온다.
                coin_price = myBinance.GetCoinNowPrice(binanceX, Target_Coin_Ticker)

                #숏 포지션을 잡는다
                #사실 여기는 시장가로 잡는게 맞습니다 나중에 챕터 7-4의 최종코드를 확인하세요!
               # print(binanceX.create_limit_sell_order(Target_Coin_Ticker, abs_amt + first_amount, coin_price))
                print("binanceX.create_order(Target_Coin_Ticker, 'limit', 'sell', abs_amt + first_amount, coin_price)")

                #스탑 로스 설정을 건다.
                print("SetStopLoss(binanceX,Target_Coin_Ticker,0.5)")
            


        #영상에서 빠져있는 중요한 부분!!! 롱인 상태에서는 롱을 잡을 만한 상황에서 물을 타야 겠죠?
        #즉 5일 선이 20일 선 아래에 있고 상승추세로 꺾였을 때 물을 탑니다.
        #롱 포지션을 잡을만한 상황!!!!
        if ma5 < ma20 and ma5_before3 > ma5_before2 and ma5_before2 < ma5:
            #물탈 수량 
            water_amount = abs_amt

            if Max_Amount < abs_amt + water_amount:
                water_amount = Max_Amount - abs_amt

            #물탈 마이너스 수익율 보다 내 수익율이 작다면 물을 타자!!
            if revenue_rate <= water_rate and Max_Amount >= abs_amt + water_amount:

                #주문 취소후
                binanceX.cancel_all_orders(Target_Coin_Ticker)
                time.sleep(0.1)
                
                #해당 코인 가격을 가져온다.
                coin_price = myBinance.GetCoinNowPrice(binanceX, Target_Coin_Ticker)

                #롱 포지션을 잡는다
                #사실 여기는 시장가로 잡는게 맞습니다 나중에 챕터 7-4의 최종코드를 확인하세요!
                #print(binanceX.create_limit_buy_order(Target_Coin_Ticker, water_amount, coin_price))
                print("binanceX.create_order(Target_Coin_Ticker, 'limit', 'buy', water_amount, coin_price)")

                #스탑 로스 설정을 건다.
                print("SetStopLoss(binanceX,Target_Coin_Ticker,0.5)")

           


        #내 보유 수량의 절반을 손절한다 단!! 매수 비중이 90% 이상이면서 내 수익율이 손절 마이너스 수익율보다 작을 때
        if revenue_rate <= danger_rate and buy_percent >= 90.0:

            #주문 취소후
            binanceX.cancel_all_orders(Target_Coin_Ticker)
            time.sleep(0.1)
                
            #해당 코인 가격을 가져온다.
            coin_price = myBinance.GetCoinNowPrice(binanceX, Target_Coin_Ticker)

            #숏 포지션을 잡는다
            #사실 여기는 시장가로 잡는게 맞습니다 나중에 챕터 7-4의 최종코드를 확인하세요!
            #print(binanceX.create_limit_sell_order(Target_Coin_Ticker, abs_amt / 2.0, coin_price))
            print("binanceX.create_order(Target_Coin_Ticker, 'limit', 'sell', abs_amt / 2.0, coin_price)")

            #스탑 로스 설정을 건다.
            print("SetStopLoss(binanceX,Target_Coin_Ticker,0.5)")



#지정가 주문만 있기 때문에 혹시나 스탑로스가 안걸릴 수 있어서 마지막에 한번 더 건다
#해당 봇이 서버에서 주기적으로 실행되기 때문에 실행 될때마다 체크해서 걸어 줄 수 있다.
#스탑 로스 설정을 건다.
print("SetStopLoss(binanceX,Target_Coin_Ticker,0.5)")
