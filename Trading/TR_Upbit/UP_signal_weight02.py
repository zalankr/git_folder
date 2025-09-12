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
def make_position(ETH, KRW): # Upbit모듈로 이더리움과 원화 잔고 불러 삽입
    # 어제의 json값 불러오기
    Upbit_data_path = '/var/autobot/TR_Upbit/Upbit_data.json'
    try:
        with open(Upbit_data_path, 'r', encoding='utf-8') as f:
            Upbit_data = json.load(f)

    except Exception as e:
        print("Exception File")

    # JSON에서 어제의 데이터 추출
    ETH_weight = Upbit_data["ETH_weight"]
    Last_day_Total_balance = Upbit_data["Total_balance"]
    Last_month_Total_balance = Upbit_data["Last_month_Total_balance"]
    Last_year_Total_balance = Upbit_data["Last_year_Total_balance"]
    Daily_return = Upbit_data["Daily_return"]
    Monthly_return = Upbit_data["Monthly_return"]
    Yearly_return = Upbit_data["Yearly_return"]

    # ETH 가격자료 불러오기
    data = pyupbit.get_ohlcv(ticker="KRW-ETH", interval="day")
    price = data["close"].iloc[-1]

    # 이동평균선 계산
    MA20 = getMA(data, 20, -1)
    MA40 = getMA(data, 40, -1)
    # 포지션 산출
    if ETH_weight == 0.99 :
        if data["close"].iloc[-1] >= MA20 and data["close"].iloc[-1] >= MA40:
            position = {"position": "Hold state", "ETH_weight": 0.99, "ETH_target": ETH, "CASH_weight": 0.01, "Invest_quantity": 0.0}
        elif data["close"].iloc[-1] < MA20 and data["close"].iloc[-1] < MA40:
            position = {"position": "Sell full", "ETH_weight": 0.0, "ETH_target": 0.0, "CASH_weight": 1.0, "Invest_quantity": ETH}
        else:
            position = {"position": "Sell half", "ETH_weight": 0.495, "ETH_target": ETH * 0.5, "CASH_weight": 0.505, "Invest_quantity": ETH * 0.5}
    elif ETH_weight == 0.495:
        if data["close"].iloc[-1] >= MA20 and data["close"].iloc[-1] >= MA40:
            position = {"position": "Buy full", "ETH_weight": 0.99, "ETH_target": ETH + ((KRW * 0.99 * 0.9995)/price), "CASH_weight": 0.01, "Invest_quantity": KRW * 0.99}
        elif data["close"].iloc[-1] < MA20 and data["close"].iloc[-1] < MA40:
            position = {"position": "Sell full", "ETH_weight": 0.0, "ETH_target": 0.0, "CASH_weight": 1.0, "Invest_quantity": ETH}
        else:
            position = {"position": "Hold state", "ETH_weight": 0.495, "ETH_target": ETH, "CASH_weight": 0.505, "Invest_quantity": 0.0}
    elif ETH_weight == 0.0:
        if data["close"].iloc[-1] >= MA20 and data["close"].iloc[-1] >= MA40:
            position = {"position": "Buy full", "ETH_weight": 0.99, "ETH_target": ((KRW*0.99*0.9995)/price), "CASH_weight": 0.01, "Invest_quantity": KRW * 0.99}
        elif data["close"].iloc[-1] < MA20 and data["close"].iloc[-1] < MA40:
            position = {"position": "Hold state", "ETH_weight": 0.0, "ETH_target": 0.0, "CASH_weight": 1.0, "Invest_quantity": 0.0}
        else:
            position = {"position": "Buy half", "ETH_weight": 0.495, "ETH_target": ((KRW*0.495*0.9995)/price) * 0.5, "CASH_weight": 0.505, "Invest_quantity": KRW * 0.495}

    return position, Last_day_Total_balance, Last_month_Total_balance, Last_year_Total_balance, Daily_return, Monthly_return, Yearly_return

# 시간확인 조건문 함수: 8:55 > daily파일 불러와 Signal산출 후 매매 후 TR기록 json생성, 9:05/9:15/9:25> 트레이딩 후 TR기록 9:30 > 트레이딩 후 
def what_time():
    # 현재 시간 가져오기
    now = datetime.now()
    current_time = now.time()

    current_hour = current_time.hour
    current_minute = current_time.minute

    # 시간 비교 시 초 단위까지 정확히 매칭하기 어려우므로 시간 범위로 체크
    if current_hour == 23 and 57 < current_minute <= 59:  # 23:58
        TR_time = ["0858", 5] # 시간, 분할 횟수
    elif current_hour == 0 and 4 < current_minute <= 6:  # 00:05
        TR_time = ["0905", 4] # 시간, 분할 횟수
    elif current_hour == 0 and 11 < current_minute <= 13:  # 00:12
        TR_time = ["0912", 3] # 시간, 분할 횟수
    elif current_hour == 0 and 18 < current_minute <= 20:  # 00:19
        TR_time = ["0919", 2] # 시간, 분할 횟수
    elif current_hour == 0 and 25 < current_minute <= 30:  # 00:26
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

# 매수매도주문 모두 취소
def Cancel_ETH_Order(upbit):
    orders_data = upbit.get_order("KRW-ETH")
    result = []
    if len(orders_data) > 0:
        for order in orders_data:
            time_module.sleep(0.1)
            result.append(upbit.cancel_order(order['uuid']))
    return result

def partial_selling(current_price, amount_per_times, TR_time, upbit):        
    # TR 분할 매매 가격 계산 & tick size에 맞춰 가격 조정
    prices = []
    for i in range(TR_time[1]):
        i += 1
        price = (current_price * (1+(i*0.0005))) # 가격을 0.05%씩 올려 분할 매도 가격 계산
        prices.append(get_tick_size(price = price,  method="floor"))

    # if문으로 TR_time[1]이 3미만이면 현재가 주문을 -2%(유사 시장가) 매도 주문으로 대체
    if TR_time[1] < 3:
        prices[0] = get_tick_size(price = current_price * 0.98,  method="floor")

    # 주문 실행
    result = None  # result 초기화
    for t in range(TR_time[1]):
        try:
            time_module.sleep(0.05)

            # prices[t]가 리스트인지 확인하고 처리
            if isinstance(prices[t], list):
                price = prices[t][0]  # 리스트면 첫 번째 요소 사용
            else:
                price = prices[t]  # 이미 값이면 그대로 사용
            
            volume = round(amount_per_times / price, 8)

            # 주문량이 너무 작으면 건너뜀
            if volume * price < 1000:
                print(f"주문 {t+1}회차: 주문량이 너무 작아서 건너뜀 (금액: {volume * price}원)")
                continue

            result = upbit.sell_limit_order("KRW-ETH", price, volume)
            print(f"주문 {t+1}회차 결과:", result)

            if result and 'price' in result:
                KA.SendMessage(f"Upbit {TR_time[0]} 매도주문 {t+1}회차: {result['price']}원")
            else:
                print(f"주문 {t+1}회차 실패:", result)

        except Exception as order_error:
            print(f"주문 {t+1}회차 오류: {order_error}")
            KA.SendMessage(f"Upbit {TR_time[0]} 매도주문 {t+1}회차 오류: {order_error}")           

    return result

def partial_buying(current_price, amount_per_times, TR_time, upbit):        
    # TR 분할 매매 가격 계산 & tick size에 맞춰 가격 조정
    prices = []
    for i in range(TR_time[1]):
        i += 1
        price = (current_price * (1-(i*0.0005))) # 가격을 0.05%씩 낮춰 분할 매수 가격 계산
        prices.append(get_tick_size(price = price,  method="floor"))

    # if문으로 TR_time[1]이 3미만이면 현재가 주문을 +2%(유사 시장가) 매수 주문으로 대체
    if TR_time[1] < 3:
        # 리스트가 아닌 값으로 할당 (문제 해결)
        prices[0] = get_tick_size(price = current_price*1.02,  method="floor")

    # 주문 실행
    result = None  # result 초기화
    for t in range(TR_time[1]):
        try:
            time_module.sleep(0.05)
            
            # prices[t]가 리스트인지 확인하고 처리
            if isinstance(prices[t], list):
                price = prices[t][0]  # 리스트면 첫 번째 요소 사용
            else:
                price = prices[t]  # 이미 값이면 그대로 사용
            
            volume = round(amount_per_times / price, 8)
            
            # 주문량이 너무 작으면 건너뜀
            if volume * price < 1000:
                print(f"주문 {t+1}회차: 주문량이 너무 작아서 건너뜀 (금액: {volume * price}원)")
                continue
                
            result = upbit.buy_limit_order("KRW-ETH", price, volume)
            print(f"주문 {t+1}회차 결과:", result)
            
            if result and 'price' in result:
                KA.SendMessage(f"Upbit {TR_time[0]} 매수주문 {t+1}회차: {result['price']}원")
            else:
                print(f"주문 {t+1}회차 실패:", result)
                
        except Exception as order_error:
            print(f"주문 {t+1}회차 오류: {order_error}")
            KA.SendMessage(f"Upbit {TR_time[0]} 매수주문 {t+1}회차 오류: {order_error}")

    return result

def Total_balance(upbit):

    # 현재가 조회 (재시도 로직 추가)
    current_price = None
    for retry in range(3):  # 최대 3번 재시도
        try:
            current_price = pyupbit.get_current_price("KRW-ETH")
            if current_price is not None:
                break
            else:
                print(f"현재가 조회 실패, 재시도 {retry + 1}/3")
                time_module.sleep(1)
        except Exception as price_error:                
            print(f"현재가 조회 오류 (재시도 {retry + 1}/3): {price_error}")
            time_module.sleep(1)
        
        if current_price is None:
            raise ValueError("현재가를 조회할 수 없습니다.")

    # KRW 잔고조회 (재시도 로직 추가)
    KRW = None
    for retry in range(3):  # 최대 3번 재시도
        try:
            KRW = upbit.get_balance_t("KRW")
            if KRW is not None:
                break
            else:
                print(f"KRW 조회 실패, 재시도 {retry + 1}/3")
                time_module.sleep(1)
        except Exception as price_error:                
            print(f"KRW 조회 오류 (재시도 {retry + 1}/3): {price_error}")
            time_module.sleep(1)
        
        if current_price is None:
            raise ValueError("KRW를 조회할 수 없습니다.")
    # ETH 잔고조회 (재시도 로직 추가)
    ETH = None
    for retry in range(3):  # 최대 3번 재시도
        try:
            ETH = upbit.get_balance_t("ETH")
            if ETH is not None:
                break
            else:
                print(f"ETH 조회 실패, 재시도 {retry + 1}/3")
                time_module.sleep(1)
        except Exception as price_error:                
            print(f"ETH 조회 오류 (재시도 {retry + 1}/3): {price_error}")
            time_module.sleep(1)
        
        if current_price is None:
            raise ValueError("ETH를 조회할 수 없습니다.")    

    Total_balance = KRW + (ETH * current_price)*0.9995

    return KRW, ETH, Total_balance