import pyupbit
import time
import pandas as pd
import kakao_alert
import datetime

access = "CvRZ8L3uWWx7SxeixwwX5mQVFXpJUaN7lxxT9gTe"          # 본인 값으로 변경
secret = "3iOZ7kGlSUP2v1yIUc7Y6zfOn50mXp2dMqHUqJR1"          # 본인 값으로 변경

upbit = pyupbit.Upbit(access, secret)

# 카카오톡 메세지 보내는 함수
def SendMessage(msg):
    kakao_alert.SendMessage(msg)
#아래 함수안의 내용은 참고로만 보세요! 제가 말씀드렸죠? 검증된 함수니 안의 내용 몰라도 그냥 가져다 쓰기만 하면 끝!
#RSI지표 수치를 구해준다. 첫번째: 분봉/일봉 정보, 두번째: 기간, 세번째: 기준 날짜
def GetRSI(ohlcv, period=14, st=-1):
    #이 안의 내용이 어려우시죠? 넘어가셔도 되요. 우리는 이 함수가 RSI지표를 정확히 구해준다는 것만 알면 됩니다.
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
def GetMA(ohlcv, period=20, st=-1):
    #이 역시 이동평균선을 제대로 구해줍니다.
    close = ohlcv["close"]
    ma = close.rolling(period).mean()
    return float(ma.iloc[st])

#거래대금이 많은 순으로 코인 리스트를 얻는다. 첫번째 : Interval기간(day,week,minute15 ....), 두번째 : 몇개까지 
def GetTopCoinList(interval="day", top=10):
    print("--------------GetTopCoinList Start-------------------")
    #원화 마켓의 코인 티커를 리스트로 담아요.
    Tickers = pyupbit.get_tickers("KRW")

    #딕셔너리를 하나 만듭니다.
    dic_coin_money = dict()

    #for문을 돌면서 모든 코인들을 순회합니다.
    for ticker in Tickers:
        try:
            #캔들 정보를 가져와서 
            df = pyupbit.get_ohlcv(ticker,interval)
            #최근 2개 캔들의 종가와 거래량을 곱하여 대략의 거래대금을 구합니다.
            volume_money = (df['close'].iloc[-1] * df['volume'].iloc[-1]) + (df['close'].iloc[-2] * df['volume'].iloc[-2])
            #volume_money = float(df['value'].iloc[-1]) + float(df['value'].iloc[-2]) #거래대금!
            #이걸 위에서 만든 딕셔너리에 넣어줍니다. Key는 코인의 티커, Value는 위에서 구한 거래대금 
            dic_coin_money[ticker] = volume_money
            #출력해 봅니다.
            print(ticker, dic_coin_money[ticker])
            #반드시 이렇게 쉬어줘야 합니다. 안그럼 에러가.. 시간조절을 해보시며 최적의 시간을 찾아보세요 전 일단 0.1로 수정했어요!
            time.sleep(0.1)

        except Exception as e:
            print("exception:",e)

    #딕셔너리를 값으로 정렬하되 숫자가 큰 순서대로 정렬합니다.
    dic_sorted_coin_money = sorted(dic_coin_money.items(), key = lambda x : x[1], reverse= True)

    #빈 리스트를 만듭니다.
    coin_list = list()

    #코인을 셀 변수를 만들어요.
    cnt = 0

    #티커와 거래대금 많은 순으로 정렬된 딕셔너리를 순회하면서 
    for coin_data in dic_sorted_coin_money:
        #코인 개수를 증가시켜주는데..
        cnt += 1

        #파라메타로 넘어온 top의 수보다 작으면 코인 리스트에 코인 티커를 넣어줍니다.
        #즉 top에 10이 들어갔다면 결과적으로 top 10에 해당하는 코인 티커가 coin_list에 들어갑니다.
        if cnt <= top:
            coin_list.append(coin_data[0])
        else:
            break

    print("--------------GetTopCoinList End-------------------")

    #코인 리스트를 리턴해 줍니다.
    return coin_list

#해당되는 리스트안에 해당 코인이 있는지 여부를 리턴하는 함수
def CheckCoinInList(CoinList, Ticker):
    InCoinOk = False

    #리스트안에 해당 코인이 있는지 체크합니다.
    for coinTicker in CoinList:
        #있으면 True로!!
        if coinTicker == Ticker:
            InCoinOk = True
            break

    return InCoinOk

#티커에 해당하는 코인의 수익율을 구해서 리턴하는 함수.
def GetRevenueRate(balances, Ticker):
    revenue_rate = 0.0
    for value in balances:
        try:
            if not isinstance(value, dict):
                continue
            realTicker = value['unit_currency'] + "-" + value['currency']
            if Ticker == realTicker:
                time.sleep(0.05)
                
                #현재 가격을 가져옵니다.
                nowPrice = pyupbit.get_current_price(realTicker)

                #수익율을 구해서 넣어줍니다
                revenue_rate = (float(nowPrice) - float(value['avg_buy_price'])) * 100.0 / float(value['avg_buy_price'])
                break

        except Exception as e:
            print("GetRevenueRate error:", e)

    return revenue_rate

#티커에 해당하는 코인의 총 매수금액을 리턴하는 함수
def GetCoinNowMoney(balances, Ticker):
    CoinMoney = 0.0
    for value in balances:
        try:
            if not isinstance(value, dict):
                continue
            if 'unit_currency' in value and 'currency' in value and 'avg_buy_price' in value and 'balance' in value and 'locked' in value:
                realTicker = value['unit_currency'] + "-" + value['currency']
                if Ticker == realTicker:
                    #해당 코인을 지정가 매도를 걸어놓으면 그 수량이 locked에 잡히게 됩니다. 
                    #만약 전체 수량을 지정가 매도를 걸었다면 balance에 있던 잔고가 모두 locked로 이동하는 거죠
                    #따라서 총 코인 매수 금액을 구하려면 balance + locked를 해줘야 합니다.
                    CoinMoney = float(value['avg_buy_price']) * (float(value['balance']) + float(value['locked']))
                    break
        except Exception as e:
            print("GetCoinNowMoney error:", e)
    return CoinMoney

#티커에 해당하는 코인이 매수된 상태면 참을 리턴하는함수
def IsHasCoin(balances, Ticker):
    HasCoin = False
    for value in balances:
        if not isinstance(value, dict):
            continue
        realTicker = value['unit_currency'] + "-" + value['currency']
        if Ticker == realTicker:
            HasCoin = True
    return HasCoin

#내가 매수한 (가지고 있는) 코인 개수를 리턴하는 함수
def GetHasCoinCnt(balances):
    CoinCnt = 0
    for value in balances:
        try:
            if not isinstance(value, dict):
                continue
            avg_buy_price = float(value['avg_buy_price'])
            if avg_buy_price != 0: #원화, 드랍받은 코인(평균매입단가가 0이다) 제외!
                CoinCnt += 1
        except Exception as e:
            continue
    return CoinCnt

#총 원금을 구한다!
def GetTotalMoney(balances):
    total = 0.0
    for balance in balances:
        try:
            # 키가 존재하는지 먼저 확인
            if 'currency' in balance and 'balance' in balance:
                #원화일 때는 실제값을 더한다.
                if balance['currency'] == "KRW":
                    total += float(balance['balance'])
                #코인일 때는 매수 금액을 더한다
                elif 'avg_buy_price' in balance:
                    total += float(balance['avg_buy_price']) * float(balance['balance'])
        except Exception as e:
            pass
    return total

#총 평가 금액을 구한다.
def GetTotalRealMoney(balances):
    total = 0.0
    for balance in balances:
        try:
            # 키가 존재하는지 먼저 확인
            if 'currency' in balance and 'balance' in balance:
                #원화일 때는 실제값을 더한다.
                if balance['currency'] == "KRW":
                    total += float(balance['balance'])
                #코인일 때는 현재가를 가져와서 더한다
                else:
                    ticker = "KRW-" + balance['currency']
                    data = pyupbit.get_current_price(ticker)
                    total += float(data) * float(balance['balance'])
        except Exception as e:
            pass
    return total

##########################################################################################3

#내가 매수할 총 코인 개수
MaxCoinCnt = 5.0
#처음 매수할 비중(퍼센트) 
FirstRate = 10.0
#추가 매수할 비중 (퍼센트)
WaterRate = 5.0

# 잔고 데이터
balances = upbit.get_balances()

TotalMoney = GetTotalMoney(balances)
TotalRealMoney = GetTotalRealMoney(balances)
# 내 총 수익률
TotalRevenue = (TotalRealMoney - TotalMoney) * 100.0 / TotalMoney

# 코인 당 매수 금액 리미트
CoinMaxMoney = TotalRealMoney / MaxCoinCnt

#처음 매수할 금액
FirstEnterMoney = CoinMaxMoney / 100.0 * FirstRate

#그 이후 매수할 금액 - 즉 물 탈 금액
WaterEnterMoeny = CoinMaxMoney / 100.0 * WaterRate

print("-"*30)
print("Total Money:", TotalMoney)
print("Total Real Money:", TotalRealMoney)
print("Total Revenue: {:.2f}%".format(TotalRevenue))
print("-"*30)
print ("Coin Max Money:", CoinMaxMoney)
print ("First Enter Money:", FirstEnterMoney)
print ("Water Enter Money:", WaterEnterMoeny)
print("-"*30)

# 거래대금이 많은 탑코인 10개의 리스트
TopCoinList = GetTopCoinList(interval="day", top=10)

# 위험한 코인 리스트
DangerCoinList = ['KRW-MARO','KRW-TSHP','KRW-PXL']

# 내가 선호하는 코인 리스트
LovelyCoinList = ['KRW-BTC','KRW-ETH','KRW-XRP','KRW-SOL']

Tickers = pyupbit.get_tickers(fiat="KRW")

Now = datetime.datetime.now()
print(f"현재 시각: {Now.strftime('%Y-%m-%d %H:%M:%S')}")
print("-"*30)

for ticker in Tickers:
    try:
        # 거래량 상위 TopCoinList에 포함되어 있지 않으면 스킵!
        if CheckCoinInList(TopCoinList, ticker) == False:
            continue
        # 위험한 코인 리스트에 포함되어 있으면 스킵!
        if CheckCoinInList(DangerCoinList, ticker) == True:
            continue
        time.sleep(0.05)
        df_60 = pyupbit.get_ohlcv(ticker=ticker, interval="minute60")# 600분봉
        rsi60_min_before = GetRSI(df_60, period=14, st=-2) 
        rsi60_min = GetRSI(df_60, period=14, st=-1)

        revenue_rate = GetRevenueRate(balances, ticker)
        print("ticker:", ticker, rsi60_min_before, "->", rsi60_min)
        print("revenue_rate:", revenue_rate)

        # 이미 매수된 코인
        if IsHasCoin(balances, ticker) == True:
            # 매수 코인의 총 매수 금액
            NowCoinTotalMoney = GetCoinNowMoney(balances, ticker)
            # 코인당 리미트 매수금액 
            Total_Rate = NowCoinTotalMoney / CoinMaxMoney *100.0

            if rsi60_min <= 30.0:
                if Total_Rate < 50.0:
                    time.sleep(0.05)
                    print(f"rsi60_min: {rsi60_min} & Total_Rate: {Total_Rate}, upbit.buy_market_order({ticker}, WaterEnterMoeny)")
                    SendMessage(f"rsi60_min: {rsi60_min} & Total_Rate: {Total_Rate}, upbit.buy_market_order({ticker}, WaterEnterMoeny)")
                else:
                    if revenue_rate <= -5.0 :
                        time.sleep(0.05)
                        print(f"rsi60_min: {rsi60_min} & revenue_rate: {Total_Rate}, upbit.buy_market_order({ticker}, WaterEnterMoeny)")
                        SendMessage(f"rsi60_min: {rsi60_min} & revenue_rate: {Total_Rate}, upbit.buy_market_order({ticker}, WaterEnterMoeny)")

        # 아직 매수하기 전인 코인
        else:
            #거래량 많은 탑코인 리스트안의 코인이 아니라면 스킵! 탑코인에 해당하는 코인만 이후 로직을 수행한다.
            if CheckCoinInList(TopCoinList,ticker) == False:
                continue

            #60분봉 기준 RSI지표 30 이하이면서 아직 매수한 코인이 MaxCoinCnt보다 작다면 매수 진행!
            if rsi60_min <= 30.0 and GetHasCoinCnt(balances) < MaxCoinCnt :
                time.sleep(0.05)
                print(f"rsi60_min: {rsi60_min} and {GetHasCoinCnt(balances)}, upbit.buy_market_order({ticker}, FirstEnterMoney)")
                SendMessage(f"rsi60_min: {rsi60_min} and {GetHasCoinCnt(balances)}, upbit.buy_market_order({ticker}, FirstEnterMoney)")

    except Exception as e:
        print("error:", e)






















