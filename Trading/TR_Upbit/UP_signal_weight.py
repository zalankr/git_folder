import pyupbit
from datetime import datetime
import time as time_module  # time 모듈을 별칭으로 import
import json
import math
# 필요한 라이브러리 설치: pip install gspread google-auth

#이동평균선 수치, 첫번째: 분봉/일봉 정보, 두번째: 기간, 세번째: 기준 날짜
def getMA(ohlcv,period,st):
    close = ohlcv["close"]
    ma = close.rolling(period).mean()
    return float(ma.iloc[st])

# 어제 포지션을 오늘 포지션으로 변경 함수
def make_position(ETH, KRW): # Upbit모듈로 이더리움과 원화 잔고 불러 삽입
<<<<<<< HEAD
    # 어제의 json값 불러오기
    Upbit_data_path = '/var/autobot/TR_Upbit/Upbit_data.json' # Home경로
=======
    # 어제의 json값 불러오기 AWS경로로
    Upbit_data_path = 'C:/Users/ilpus/Desktop/git_folder/Trading/TR_Upbit/Upbit_data.json' # Home경로
    # Upbit_data_path = 'C:/Users/GSR/Desktop/Python_project/git_folder/Trading/TR_Upbit/Upbit_data.json' # Company경로
>>>>>>> a6e42013e7e3c0ddd599b55b604bdb41e1c0dcd2
    try:
        with open(Upbit_data_path, 'r', encoding='utf-8') as f:
            Upbit_data = json.load(f)

    except Exception as e:
        print("Exception File")

    # JSON에서 어제의 데이터 추출
    ETH_weight = Upbit_data["ETH_weight"]
    Last_day_Total_balance = Upbit_data["Last_day_Total"]
    Last_month_Total_balance = Upbit_data["Last_month_Total"]
    Last_year_Total_balance = Upbit_data["Last_year_Total"]

    # ETH 가격자료 불러오기
    data = pyupbit.get_ohlcv(ticker="KRW-ETH", interval="day")
    price = data["close"].iloc[-1]


    # 이동평균선 계산
    MA20 = getMA(data, 20, -1)
    MA40 = getMA(data, 40, -1)
    # 포지션 산출
    if ETH_weight == 0.99 :
        if data["close"].iloc[-1] >= MA20 and data["close"].iloc[-1] >= MA40:
            position = {"position": "Hold state", "ETH_weight": 0.99, "ETH_target": ETH, "CASH_weight": 0.01, "Invest_Quantity": 0.0}
        elif data["close"].iloc[-1] < MA20 and data["close"].iloc[-1] < MA40:
            position = {"position": "Sell full", "ETH_weight": 0.0, "ETH_target": 0.0, "CASH_weight": 1.0, "Invest_Quantity": ETH}
        else:
            position = {"position": "Sell half", "ETH_weight": 0.495, "ETH_target": ETH * 0.5, "CASH_weight": 0.505, "Invest_Quantity": ETH * 0.5}
    elif ETH_weight == 0.495:
        if data["close"].iloc[-1] >= MA20 and data["close"].iloc[-1] >= MA40:
            position = {"position": "Buy full", "ETH_weight": 0.99, "ETH_target": ETH + ((KRW * 0.99 * 0.9995)/price), "CASH_weight": 0.01, "Invest_Quantity": KRW * 0.99}
        elif data["close"].iloc[-1] < MA20 and data["close"].iloc[-1] < MA40:
            position = {"position": "Sell full", "ETH_weight": 0.0, "ETH_target": 0.0, "CASH_weight": 1.0, "Invest_Quantity": ETH}
        else:
            position = {"position": "Hold state", "ETH_weight": 0.495, "ETH_target": ETH, "CASH_weight": 0.505, "Invest_Quantity": 0.0}
    elif ETH_weight == 0.0:
        if data["close"].iloc[-1] >= MA20 and data["close"].iloc[-1] >= MA40:
            position = {"position": "Buy full", "ETH_weight": 0.99, "ETH_target": ((KRW*0.99*0.9995)/price), "CASH_weight": 0.01, "Invest_Quantity": KRW * 0.99}
        elif data["close"].iloc[-1] < MA20 and data["close"].iloc[-1] < MA40:
            position = {"position": "Hold state", "ETH_weight": 0.0, "ETH_target": 0.0, "CASH_weight": 1.0, "Invest_Quantity": 0.0}
        else:
            position = {"position": "Buy half", "ETH_weight": 0.495, "ETH_target": ((KRW*0.495*0.9995)/price) * 0.5, "CASH_weight": 0.505, "Invest_Quantity": KRW * 0.495}

    return position, Last_day_Total_balance, Last_month_Total_balance, Last_year_Total_balance

# 시간확인 조건문 함수: 8:55 > daily파일 불러와 Signal산출 후 매매 후 TR기록 json생성, 9:05/9:15/9:25> 트레이딩 후 TR기록 9:30 > 트레이딩 후 
def what_time():
    # 현재 시간 가져오기
    now = datetime.now()
    current_time = now.time()

    current_hour = current_time.hour
    current_minute = current_time.minute

    # 시간 비교 시 초 단위까지 정확히 매칭하기 어려우므로 시간 범위로 체크 AWS에서 시간 맞게 인지 되는 지
    if current_hour == 23 and 58 <=current_minute <= 59:  # 23:58
        TR_time = ["0858", 5] # 시간, 분할 횟수
    elif current_hour == 0 and 5 <= current_minute <= 6:  # 00:05
        TR_time = ["0905", 4] # 시간, 분할 횟수
    elif current_hour == 0 and 12 <= current_minute <= 13:  # 00:12
        TR_time = ["0912", 3] # 시간, 분할 횟수
    elif current_hour == 0 and 19 <= current_minute <= 20:  # 00:19
        TR_time = ["0919", 2] # 시간, 분할 횟수
    elif current_hour == 0 and 26 <= current_minute <= 27:  # 00:26
        TR_time = ["0926", 1]
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

# 코해당 인에 걸어진 매수매도주문 모두를 취소한다.
def Cancel_ETH_Order(upbit):
    orders_data = upbit.get_order("KRW-ETH")
    if len(orders_data) > 0:
        for order in orders_data:
            time_module.sleep(0.1)
            print(upbit.cancel_order(order['uuid']))

def partial_selling(current_price, amount_per_times, TR_time, upbit):        
    # TR 분할 매매 가격 계산 & tick size에 맞춰 가격 조정
    prices = []
    for i in range(TR_time[1]):
        price = (current_price * (1+(i*0.002))) # 가격을 0.2%씩 올려 분할 매도 가격 계산
        prices.append(get_tick_size(price = price,  method="floor"))

    # if문으로 TR_time[1]이 3미만이면 현재가 주문을 -2%(유사 시장가) 매도 주문으로 대체
    if TR_time[1] < 3:
        prices[0] = [get_tick_size(price = current_price * 0.98,  method="floor")]
        
    print("분할 매매 가격:", prices) # 완성 후 삭제

    # 주문 실행
    for t in range(TR_time[1]):
        time_module.sleep(0.05) 
        result = upbit.sell_limit_order("KRW-ETH", prices[t], amount_per_times)
        print(result) # 프린트

    return result

def partial_buying(current_price, amount_per_times, TR_time, upbit):        
    # TR 분할 매매 가격 계산 & tick size에 맞춰 가격 조정
    prices = []
    for i in range(TR_time[1]):
        price = (current_price * (1-(i*0.002))) # 가격을 0.2%씩 낮춰 분할 매수 가격 계산
        prices.append(get_tick_size(price = price,  method="floor"))

    # if문으로 TR_time[1]이 3미만이면 현재가 주문을 +2%(유사 시장가) 매수 주문으로 대체
    if TR_time[1] < 3:
        prices[0] = [get_tick_size(price = current_price*1.02,  method="floor")]
        
    print("분할 매매 가격:", prices) # 완성 후 삭제

    # 주문 실행
    for t in range(TR_time[1]):
        time_module.sleep(0.05)
        result = upbit.buy_limit_order("KRW-ETH", prices[t], amount_per_times)
        print(result)

    return result

def Total_balance(upbit):
    KRW = upbit.get_balance_t("KRW")
    ETH = upbit.get_balance_t("ETH")
    Total_balance = KRW + (ETH * pyupbit.get_current_price("KRW-ETH"))*0.9995

    return KRW, ETH, Total_balance