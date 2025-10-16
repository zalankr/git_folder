import pyupbit
from datetime import datetime
import time as time_module  # time 모듈을 별칭으로 import
import json
import math
import kakao_alert as KA

# 필요한 라이브러리 설치: pip install gspread google-auth

#이동평균선 수치, 첫번째: 분봉/일봉 정보, 두번째: 기간, 세번째: 기준 날짜
def getMA(ohlcv,period,st):
    close = ohlcv["close"]
    ma = close.rolling(period).mean()
    return float(ma.iloc[st])

# 어제 포지션을 오늘 포지션으로 변경 함수
def make_position(ETH, BTC, KRW): # Upbit모듈로 ETH, BTC, 원화 잔고 불러 삽입
    # 어제의 json값 불러오기
    Upbit_data_path = '/var/autobot/TR_Upbit/Upbit2_data.json'
    try:
        with open(Upbit_data_path, 'r', encoding='utf-8') as f:
            Upbit_data = json.load(f)

    except Exception as e:
        print("Exception File")

    # JSON에서 어제의 데이터 추출
    ETH = dict()
    ETH["Position"] = Upbit_data["ETH"]["Position"]
    ETH["ETH_weight"] = Upbit_data["ETH"]["ETH_weight"]
    ETH["ETH_target"] = Upbit_data["ETH"]["ETH_target"]
    ETH["KRW_weight"] = Upbit_data["ETH"]["KRW_weight"]
    ETH["ETH_model_balance"] = Upbit_data["ETH"]["ETH_model_balance"]
    ETH["ETH"] = Upbit_data["ETH"]["ETH"]
    ETH["KRW"] = Upbit_data["ETH"]["KRW"]

    BTC =dict()
    BTC["Position"] = Upbit_data["BTC"]["Position"]
    BTC["BTC_weight"] = Upbit_data["BTC"]["BTC_weight"]
    BTC["BTC_target"] = Upbit_data["BTC"]["BTC_target"]
    BTC["KRW_weight"] = Upbit_data["BTC"]["KRW_weight"]
    BTC["BTC_model_balance"] = Upbit_data["BTC"]["BTC_model_balance"]
    BTC["BTC"] = Upbit_data["BTC"]["BTC"]
    BTC["KRW"] = Upbit_data["BTC"]["KRW"]

    Account = dict()
    Account["Total_balance"] = Upbit_data["Account"]["Total_balance"]
    Account["Last_day_Total_balance"] = Upbit_data["Account"]["Total_balance"]
    Account["Last_month_Total_balance"] = Upbit_data["Account"]["Last_month_Total_balance"]
    Account["Last_year_Total_balance"] = Upbit_data["Account"]["Last_year_Total_balance"]
    Account["Daily_return"] = Upbit_data["Account"]["Daily_return"]
    Account["Monthly_return"] = Upbit_data["Account"]["Monthly_return"]
    Account["Yearly_return"] = Upbit_data["Account"]["Yearly_return"]

    # ETH 가격자료 불러오기
    ETH_data = pyupbit.get_ohlcv(ticker="KRW-ETH", interval="day")
    ETH_price = ETH_data["close"].iloc[-1]

    # BTC 가격자료 불러오기
    BTC_data = pyupbit.get_ohlcv(ticker="KRW-BTC", interval="day")
    BTC_price = BTC_data["close"].iloc[-1]   

    # 이동평균선 계산
    ETH_MA20 = getMA(ETH_data, 20, -1)
    ETH_MA40 = getMA(ETH_data, 40, -1)
    BTC_MA45 = getMA(BTC_data, 45, -1)
    BTC_MA120 = getMA(BTC_data, 120, -1)

    # 포지션 산출
    if ETH["ETH_weight"] == 1.0 :
        if ETH_data["close"].iloc[-1] >= ETH_MA20 and ETH_data["close"].iloc[-1] >= ETH_MA40:
            ETH["Position"] = "Hold_state"
            ETH["ETH_weight"] = 1.0
            ETH["ETH_target"] = ETH["ETH"]
            ETH["KRW_weight"] = 0.0
            ETH["ETH_sell_qty"] = 0.0
            ETH["KRW_buy_qty"] = 0.0
        elif ETH_data["close"].iloc[-1] < ETH_MA20 and ETH_data["close"].iloc[-1] < ETH_MA40:
            ETH["Position"] = "Sell_full"
            ETH["ETH_weight"] = 0.0
            ETH["ETH_target"] = 0.0
            ETH["KRW_weight"] = 1.0
            ETH["ETH_sell_qty"] = ETH["ETH"]
            ETH["KRW_buy_qty"] = 0.0
        else:
            ETH["Position"] = "Sell_half"
            ETH["ETH_weight"] = 0.5
            ETH["ETH_target"] = ETH["ETH"] * 0.5
            ETH["KRW_weight"] = 0.5
            ETH["ETH_sell_qty"] = ETH["ETH"] * 0.5
            ETH["KRW_buy_qty"] = 0.0
    elif ETH["ETH_weight"] == 0.5:
        if ETH_data["close"].iloc[-1] >= ETH_MA20 and ETH_data["close"].iloc[-1] >= ETH_MA40:
            ETH["Position"] = "Buy_full"
            ETH["ETH_weight"] = 1.0
            ETH["ETH_target"] = ETH["ETH"] + ((KRW*0.9995)/ETH_price)
            ETH["KRW_weight"] = 0.0
            ETH["ETH_sell_qty"] = 0.0
            ETH["KRW_buy_qty"] = KRW
        elif ETH_data["close"].iloc[-1] < ETH_MA20 and ETH_data["close"].iloc[-1] < ETH_MA40:
            ETH["Position"] = "Sell_full"
            ETH["ETH_weight"] = 0.0
            ETH["ETH_target"] = 0.0
            ETH["KRWEweight"] = 1.0
            ETH["ETH_sell_qty"] = ETH["ETH"]
            ETH["KRW_buy_qty"] = 0.0
        else:
            ETH["Position"] = "Hold_state"
            ETH["ETH_weight"] = 0.5
            ETH["ETH_target"] = ETH["ETH"]
            ETH["KRW_weight"] = 0.5
            ETH["ETH_sell_qty"] = 0.0
            ETH["KRW_buy_qty"] = 0.0
    elif ETH["ETH_weight"] == 0.0:
        if ETH_data["close"].iloc[-1] >= ETH_MA20 and ETH_data["close"].iloc[-1] >= ETH_MA40:
            ETH["Position"] = "Buy_full"
            ETH["ETH_weight"] = 1.0
            ETH["ETH_target"] = (KRW*0.9995)/ETH_price
            ETH["KRW_weight"] = 0.0
            ETH["ETH_sell_qty"] = 0.0
            ETH["KRW_buy_qty"] = KRW
        elif ETH_data["close"].iloc[-1] < ETH_MA20 and ETH_data["close"].iloc[-1] < ETH_MA40:
            ETH["Position"] = "Hold_state"
            ETH["ETH_weight"] = 0.0
            ETH["ETH_target"] = 0.0
            ETH["KRW_weight"] = 1.0
            ETH["ETH_sell_qty"] = 0.0
            ETH["KRW_buy_qty"] = 0.0
        else:
            ETH["Position"] = "Buy_half"
            ETH["ETH_weight"] = 0.5
            ETH["ETH_target"] = ((KRW*0.9995)/ETH_price) * 0.5
            ETH["KRW_weight"] = 0.5
            ETH["ETH_sell_qty"] = 0.0
            ETH["KRW_buy_qty"] = KRW * 0.5

    if BTC["BTC_weight"] == 1.0 :
        if BTC_data["close"].iloc[-1] >= BTC_MA45 and BTC_data["close"].iloc[-1] >= BTC_MA120:
            BTC["Position"] = "Hold_state"
            BTC["BTC_weight"] = 1.0
            BTC["BTC_target"] = BTC["BTC"]
            BTC["KRW_weight"] = 0.0
            BTC["BTC_sell_qty"] = 0.0
            BTC["KRW_buy_qty"] = 0.0
        elif BTC_data["close"].iloc[-1] < BTC_MA45 and BTC_data["close"].iloc[-1] < BTC_MA120:
            BTC["Position"] = "Sell_full"
            BTC["BTC_weight"] = 0.0
            BTC["BTC_target"] = 0.0
            BTC["KRW_weight"] = 1.0
            BTC["BTC_sell_qty"] = BTC["BTC"]
            BTC["KRW_buy_qty"] = 0.0
        else:
            BTC["Position"] = "Sell_half"
            BTC["BTC_weight"] = 0.5
            BTC["BTC_target"] = BTC["BTC"] * 0.5
            BTC["KRW_weight"] = 0.5
            BTC["BTC_sell_qty"] = BTC["BTC"] * 0.5
            BTC["KRW_buy_qty"] = 0.0
    elif BTC["BTC_weight"] == 0.5:
        if BTC_data["close"].iloc[-1] >= BTC_MA45 and BTC_data["close"].iloc[-1] >= BTC_MA120:
            BTC["Position"] = "Buy_full"
            BTC["BTC_weight"] = 1.0
            BTC["BTC_target"] = BTC["BTC"] + ((KRW*0.9995)/BTC_price)
            BTC["KRW_weight"] = 0.0
            BTC["BTC_sell_qty"] = 0.0
            BTC["KRW_buy_qty"] = KRW
        elif BTC_data["close"].iloc[-1] < BTC_MA45 and BTC_data["close"].iloc[-1] < BTC_MA120:
            BTC["Position"] = "Sell_full"
            BTC["BTC_weight"] = 0.0
            BTC["BTC_target"] = 0.0
            BTC["KRW_weight"] = 1.0
            BTC["BTC_sell_qty"] = BTC["BTC"]
            BTC["KRW_buy_qty"] = 0.0
        else:
            BTC["Position"] = "Hold_state"
            BTC["BTC_weight"] = 0.5
            BTC["BTC_target"] = BTC["BTC"]
            BTC["KRW_weight"] = 0.5
            BTC["BTC_sell_qty"] = 0.0
            BTC["KRW_buy_qty"] = 0.0
    elif BTC["BTC_weight"] == 0.0:
        if BTC_data["close"].iloc[-1] >= BTC_MA45 and BTC_data["close"].iloc[-1] >= BTC_MA120:
            BTC["Position"] = "Buy_full"
            BTC["BTC_weight"] = 1.0
            BTC["BTC_target"] = (KRW*0.9995)/BTC_price
            BTC["KRW_weight"] = 0.0
            BTC["BTC_sell_qty"] = 0.0
            BTC["KRW_buy_qty"] = KRW
        elif BTC_data["close"].iloc[-1] < BTC_MA45 and BTC_data["close"].iloc[-1] < BTC_MA120:
            BTC["Position"] = "Hold_state"
            BTC["BTC_weight"] = 0.0
            BTC["BTC_target"] = 0.0
            BTC["KRW_weight"] = 1.0
            BTC["BTC_sell_qty"] = 0.0
            BTC["KRW_buy_qty"] = 0.0
        else:
            BTC["Position"] = "Buy_half"
            BTC["BTC_weight"] = 0.5
            BTC["BTC_target"] = ((KRW*0.9995)/BTC_price) * 0.5
            BTC["KRW_weight"] = 0.5
            BTC["BTC_sell_qty"] = 0.0
            BTC["KRW_buy_qty"] = KRW * 0.5

    return ETH, BTC, Account

# 시간확인 조건문 함수: 8:55 > daily파일 불러와 Signal산출 후 매매 후 TR기록 json생성, 9:05/9:15/9:25> 트레이딩 후 TR기록 9:30 > 트레이딩 후 
def what_time():
    # 현재 시간 가져오기
    now = datetime.now()
    current_time = now.time()

    current_hour = current_time.hour
    current_minute = current_time.minute

    # 시간 비교 시 초 단위까지 정확히 매칭하기 어려우므로 시간 범위로 체크
    if current_hour == 23 and 57 < current_minute <= 59:  # 23:58
        TR_time = ["0858", 8] # 시간, 분할 횟수
    elif current_hour == 0 and 4 < current_minute <= 6:  # 00:05
        TR_time = ["0905", 7] # 시간, 분할 횟수
    elif current_hour == 0 and 11 < current_minute <= 13:  # 00:12
        TR_time = ["0912", 6] # 시간, 분할 횟수
    elif current_hour == 0 and 18 < current_minute <= 20:  # 00:19
        TR_time = ["0919", 5] # 시간, 분할 횟수
    elif current_hour == 0 and 25 < current_minute <= 30:  # 00:26
        TR_time = ["0926", 4]       
    elif current_hour == 0 and 32 < current_minute <= 34:  # 00:33
        TR_time = ["0933", 3] # 시간, 분할 횟수
    elif current_hour == 0 and 39 < current_minute <= 41:  # 00:40
        TR_time = ["0940", 2] # 시간, 분할 횟수
    elif current_hour == 0 and 46 < current_minute <= 50:  # 00:47
        TR_time = ["0947", 1]
    else:
        TR_time = [None, 0]
    
    return now, current_time, TR_time

# tick size 계산 함수
def get_tick_size(price, method="floor"):
    if method == "floor":
        func = math.floor
    elif method == "round":
        func = round 
    else:
        func = math.ceil 

    if price >= 2000000:
        tick_size = func(price / 1000) * 1000
    elif price >= 1000000:
        tick_size = func(price / 1000) * 1000
    elif price >= 500000:
        tick_size = func(price / 500) * 500
    elif price >= 100000:
        tick_size = func(price / 100) * 100
    elif price >= 50000:
        tick_size = func(price / 50) * 50
    elif price >= 10000:
        tick_size = func(price / 10) * 10
    elif price >= 5000:
        tick_size = func(price / 5) * 5
    elif price >= 1000:
        tick_size = func(price / 1) * 1
    elif price >= 100:
        tick_size = func(price / 1) * 1
    elif price >= 10:
        tick_size = func(price / 0.1) / 10
    elif price >= 1:
        tick_size = func(price / 0.01) / 100
    elif price >= 0.1:
        tick_size = func(price / 0.001) / 1000
    elif price >= 0.01:
        tick_size = func(price / 0.0001) / 10000
    elif price >= 0.001:
        tick_size = func(price / 0.00001) / 100000
    elif price >= 0.0001:
        tick_size = func(price / 0.000001) / 1000000
    elif price >= 0.00001:
        tick_size = func(price / 0.0000001) / 10000000
    else:
        tick_size = func(price / 0.00000001) / 100000000

    return tick_size

# 매수매도주문 모두 취소
def Cancel_Order(upbit):
    orders_ETH = upbit.get_order("KRW-ETH")
    orders_BTC = upbit.get_order("KRW-BTC")
    result = []
    if len(orders_ETH) > 0:
        for order in orders_ETH:
            time_module.sleep(0.1)
            result.append(upbit.cancel_order(order['uuid']))
    if len(orders_BTC) > 0:
        for order in orders_BTC:
            time_module.sleep(0.1)
            result.append(upbit.cancel_order(order['uuid']))
    return result

# 매도주문 ###### ticker 인수 넣기
def partial_selling(current_price, amount_per_times, TR_time, upbit):        
    prices = []
    for i in range(TR_time[1]):
        order_num = i + 1
        price = current_price * (1+(order_num*0.0005))
        prices.append(get_tick_size(price=price, method="floor"))

    if TR_time[1] < 5:
        prices[0] = get_tick_size(price=current_price * 0.99, method="floor")

    result = None
    for t in range(TR_time[1]):
        try:
            time_module.sleep(0.05)

            if isinstance(prices[t], list):
                price = prices[t][0]
            else:
                price = prices[t]
                
            # 마지막 주문 처리 개선 - 계속 오류가 생기니 일단 이부분 없애고
            # if t == TR_time[1] - 1:
            #     remaining_balance = upbit.get_balance_t("ETH")
            #     # 안전마진 제거 - 전량 매도
            #     volume = round(remaining_balance, 8)  # 소수점 8자리로 정확히
            # else:
            #     volume = round(amount_per_times, 8)
            volume = round(amount_per_times, 8)

            # 주문 금액 체크 - 실제 주문 금액으로 검증
            order_amount = volume * price
            if order_amount < 5500:  # 5500원으로 체크
                print(f"주문 {t+1}회차: 주문금액 부족 (금액: {order_amount:.0f}원, 필요: 5500원)")
                continue

            result = upbit.sell_limit_order("KRW-ETH", price, volume)
            print(f"{TR_time[0]}차 {t+1}/{TR_time[1]}분할 매도:", result)

            if result and 'price' in result:
                KA.SendMessage(f"Upbit {TR_time[0]}, {t+1}/{TR_time[1]}분할 매도가: {result['price']}원, 수량: {volume}")
            else:
                KA.SendMessage(f"Upbit {TR_time[0]}, {t+1}/{TR_time[1]} 주문 실패: {result}")

        except Exception as order_error:
            print(f"주문 {t+1}회차 오류: {order_error}")
            KA.SendMessage(f"Upbit {TR_time[0]}, {t+1}/{TR_time[1]}분할 매도 오류: {order_error}")

    return result
# 매수주문
def partial_buying(current_price, amount_per_times, TR_time, upbit):        
    prices = []
    for i in range(TR_time[1]):
        order_num = i + 1
        price = current_price * (1-(order_num*0.0005))
        prices.append(get_tick_size(price=price, method="floor"))

    if TR_time[1] < 5:
        prices[0] = get_tick_size(price=current_price*1.01, method="floor")

    result = None
    for t in range(TR_time[1]):
        try:
            time_module.sleep(0.05)
            
            if isinstance(prices[t], list):
                price = prices[t][0]
            else:
                price = prices[t]
            
            # 마지막 주문 처리 개선 - 계속 오류가 생기니 일단 이부분 없애고
            # if t == TR_time[1] - 1:
            #     KRW = upbit.get_balance_t("KRW")
            #     # 수수료 고려하여 안전하게 계산
            #     volume = round((KRW / price) * 0.9990, 8)  # 0.9995 -> 0.9990으로 더 안전하게
            # else:
            #     volume = round(amount_per_times / price, 8)
            volume = round(amount_per_times / price, 8)
            
            # 주문 금액 체크 - 실제 주문 금액으로 검증
            order_amount = volume * price
            if order_amount < 5500:  # 6000원보다 여유있게 5500원으로 체크
                print(f"주문 {t+1}회차: 주문금액 부족 (금액: {order_amount:.0f}원, 필요: 5500원)")
                continue
                
            result = upbit.buy_limit_order("KRW-ETH", price, volume)
            print(f"{TR_time[0]}차 {t+1}/{TR_time[1]}분할 매수", result)
            
            if result and 'price' in result:
                KA.SendMessage(f"Upbit {TR_time[0]}, {t+1}/{TR_time[1]}분할 매수가: {result['price']}원, 수량: {volume}")
            else:
                KA.SendMessage(f"Upbit {TR_time[0]}, {t+1}/{TR_time[1]}분할 매수 오류: {result}")
                
        except Exception as order_error:
            print(f"주문 {t+1}회차 오류: {order_error}")
            KA.SendMessage(f"Upbit {TR_time[0]}, {t+1}/{TR_time[1]}분할 매수 오류: {order_error}")

    return result

# 종합 잔고조회
def Total_balance(upbit):
    KRW = upbit.get_balance_t("KRW")
    ETH = upbit.get_balance_t("ETH")
    BTC = upbit.get_balance_t("BTC")
    Total_balance = KRW + (ETH * pyupbit.get_current_price("KRW-ETH")) + (BTC * pyupbit.get_current_price("KRW-BTC"))

    return KRW, ETH, BTC,Total_balance