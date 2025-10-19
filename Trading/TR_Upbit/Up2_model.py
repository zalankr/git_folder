import pyupbit
from datetime import datetime, timedelta, timezone
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
def make_position(upbit):
    # 어제의 json값 불러오기
    TR_data_path = '/var/autobot/TR_Upbit/TR_data2.json'
    try:
        with open(TR_data_path, 'r', encoding='utf-8') as f:
            TR_data = json.load(f)
    except FileNotFoundError:
        print("JSON 파일 없음 - 기본값 사용")
        TR_data = {
            "ETH_weight": 0.0,
            "BTC_weight": 0.0
        }
        KA.SendMessage("TR_data 파일 없음, 초기값으로 시작")
    except Exception as e:
        print(f"JSON 파일 오류: {e}")
        raise
    # JSON data에서 티커별 어제의 목표비중 불러오기
    Last_ETH_weight = TR_data.get("ETH_weight", 0.0)
    Last_BTC_weight = TR_data.get("BTC_weight", 0.0) #어제의 티커별 목표비중

    # 현재 날짜 구하기
    now = datetime.now()

    # ETH, BTC, 원화 잔고 불러오rh data에 저장
    KRW, ETH, BTC, Total = Total_balance(upbit)

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

    # 전일 ETH/KRW/원화환산 잔고, 전월말, 전년말 원화환산 잔고

    # ETH포지션 산출
    if Last_ETH_weight == 0.5 : # 어제
        if ETH_price >= ETH_MA20 and ETH_price >= ETH_MA40:
            ETH_Position = "Hold_state"
            ETH_weight = 0.5 # 오늘
            ETH_target = ETH
            ETHKRW_sell = 0.0
            KRWETH_buy = 0.0
        elif ETH_price < ETH_MA20 and ETH_price < ETH_MA40:
            ETH_Position = "Sell_full"
            ETH_weight = 0.0 # 오늘
            ETH_target = 0.0
            ETHKRW_sell = ETH
            KRWETH_buy = 0.0
        else:
            ETH_Position = "Sell_half"
            ETH_weight = 0.25 # 오늘
            ETH_target = ETH * 0.5
            ETHKRW_sell = ETH * 0.5
            KRWETH_buy = 0.0
    elif Last_ETH_weight == 0.25 : # 어제
        if ETH_price >= ETH_MA20 and ETH_price >= ETH_MA40:
            ETH_Position = "Buy_full"
            ETH_weight = 0.5 # 오늘
            if Last_BTC_weight == 0.5: #어제
                KRWETH_buy = KRW
            elif Last_BTC_weight == 0.25: #어제
                KRWETH_buy = KRW * 0.5
            elif Last_BTC_weight == 0.0: #어제
                KRWETH_buy = KRW / 3
            ETH_target = ETH + ((KRWETH_buy*0.99) / ETH_price)
            ETHKRW_sell = 0.0
        elif ETH_price < ETH_MA20 and ETH_price < ETH_MA40:
            ETH_Position = "Sell_full"
            ETH_weight = 0.0 # 오늘
            ETH_target = 0.0
            ETHKRW_sell = ETH
            KRWETH_buy = 0.0
        else:
            ETH_Position = "Hold_state"
            ETH_weight = 0.25 # 오늘
            ETH_target = ETH
            ETHKRW_sell = 0.0
            KRWETH_buy = 0.0
    elif Last_ETH_weight == 0.0 : # 어제
        if ETH_price >= ETH_MA20 and ETH_price >= ETH_MA40:
            ETH_Position = "Buy_full"
            ETH_weight = 0.5 # 오늘
            if Last_BTC_weight == 0.5: #어제
                KRWETH_buy = KRW
            elif Last_BTC_weight == 0.25: #어제
                KRWETH_buy = KRW * 2 / 3
            elif Last_BTC_weight == 0.0: #어제
                KRWETH_buy = KRW * 0.5
            ETH_target = (KRWETH_buy * 0.99) / ETH_price
            ETHKRW_sell = 0.0
        elif ETH_price < ETH_MA20 and ETH_price < ETH_MA40:
            ETH_Position = "Hold_state"
            ETH_weight = 0.0 # 오늘
            ETH_target = 0.0
            ETHKRW_sell = 0.0
            KRWETH_buy = 0.0
        else:
            ETH_Position = "Buy_half"
            ETH_weight = 0.25 # 오늘
            if Last_BTC_weight == 0.5: #어제
                KRWETH_buy = KRW * 0.5
            elif Last_BTC_weight == 0.25: #어제
                KRWETH_buy = KRW / 3
            elif Last_BTC_weight == 0.0: #어제
                KRWETH_buy = KRW * 0.25
            ETH_target = (KRWETH_buy * 0.99) / ETH_price
            ETHKRW_sell = 0.0

    # BTC포지션 산출
    if Last_BTC_weight == 0.5 : #어제
        if BTC_price >= BTC_MA45 and BTC_price >= BTC_MA120:
            BTC_Position = "Hold_state"
            BTC_weight = 0.5 # 오늘
            BTC_target = BTC
            BTCKRW_sell = 0.0
            KRWBTC_buy = 0.0
        elif BTC_price < BTC_MA45 and BTC_price < BTC_MA120:
            BTC_Position = "Sell_full"
            BTC_weight = 0.0 # 오늘
            BTC_target = 0.0
            BTCKRW_sell = BTC
            KRWBTC_buy = 0.0
        else:
            BTC_Position = "Sell_half"
            BTC_weight = 0.25 # 오늘
            BTC_target = BTC * 0.5
            BTCKRW_sell = BTC * 0.5
            KRWBTC_buy = 0.0
    elif Last_BTC_weight == 0.25 : #어제
        if BTC_price >= BTC_MA45 and BTC_price >= BTC_MA120:
            BTC_Position = "Buy_full"
            BTC_weight = 0.5 # 오늘
            if Last_ETH_weight == 0.5: #어제
                KRWBTC_buy = KRW
            elif Last_ETH_weight == 0.25: #어제
                KRWBTC_buy = KRW * 0.5
            elif Last_ETH_weight == 0.0: #어제
                KRWBTC_buy = KRW / 3
            BTC_target = BTC + ((KRWBTC_buy*0.99) / BTC_price)
            BTCKRW_sell = 0.0
        elif BTC_price < BTC_MA45 and BTC_price < BTC_MA120:
            BTC_Position = "Sell_full"
            BTC_weight = 0.0 # 오늘
            BTC_target = 0.0
            BTCKRW_sell = BTC
            KRWBTC_buy = 0.0
        else:
            BTC_Position = "Hold_state"
            BTC_weight = 0.25 # 오늘
            BTC_target = BTC
            BTCKRW_sell = 0.0
            KRWBTC_buy = 0.0
    elif Last_BTC_weight == 0.0 : #어제
        if BTC_price >= BTC_MA45 and BTC_price >= BTC_MA120:
            BTC_Position = "Buy_full"
            BTC_weight = 0.5 # 오늘
            if Last_ETH_weight == 0.5: #어제
                KRWBTC_buy = KRW
            elif Last_ETH_weight == 0.25: #어제
                KRWBTC_buy = KRW * 2 / 3
            elif Last_ETH_weight == 0.0: #어제
                KRWBTC_buy = KRW * 0.5
            BTC_target = (KRWBTC_buy * 0.99) / BTC_price
            BTCKRW_sell = 0.0
        elif BTC_price < BTC_MA45 and BTC_price < BTC_MA120:
            BTC_Position = "Hold_state"
            BTC_weight = 0.0 # 오늘
            BTC_target = 0.0
            BTCKRW_sell = 0.0
            KRWBTC_buy = 0.0
        else:
            BTC_Position = "Buy_half"
            BTC_weight = 0.25 # 오늘
            if Last_ETH_weight == 0.5: #어제
                KRWBTC_buy = KRW * 0.5
            elif Last_ETH_weight == 0.25: #어제
                KRWBTC_buy = KRW / 3
            elif Last_ETH_weight == 0.0: #어제
                KRWBTC_buy = KRW * 0.25
            BTC_target = (KRWBTC_buy * 0.99) / BTC_price
            BTCKRW_sell = 0.0
    
    TR_data = {
        "Date": str(now.date()),
        "ETH": ETH,
        "BTC": BTC,
        "KRW": KRW,
        "ETH_Position": ETH_Position,
        "BTC_Position": BTC_Position,
        "Last_ETH_weight": Last_ETH_weight,
        "Last_BTC_weight": Last_BTC_weight,
        "ETH_weight": ETH_weight,
        "BTC_weight": BTC_weight,
        "ETH_target": ETH_target,
        "BTC_target": BTC_target,
        "ETHKRW_sell": ETHKRW_sell,
        "BTCKRW_sell": BTCKRW_sell,
        "KRWETH_buy": KRWETH_buy,
        "KRWBTC_buy": KRWBTC_buy,
        "ETHKRW_balance": ETH * ETH_price * 0.9995,
        "BTCKRW_balance": BTC * BTC_price * 0.9995,
        "KRW_balance": KRW,
        "Total_balance": Total
    }

    return TR_data

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
def partial_selling(ticker, current_price, amount_per_times, TR_time, upbit):
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
            time_module.sleep(0.2)

            if isinstance(prices[t], list):
                price = prices[t][0]
            else:
                price = prices[t]
            volume = round(amount_per_times, 8)

            # 주문 금액 체크 - 실제 주문 금액으로 검증
            order_amount = volume * price
            if order_amount < 5500:  # 5500원으로 체크
                KA.SendMessage(f"Upbit {TR_time[0]}, {t+1}회차 {ticker} 주문금액 부족으로 스킵")
                continue

            result = upbit.sell_limit_order(ticker, price, volume)
            print(f"{TR_time[0]}차 {t+1}/{TR_time[1]} {ticker} 분할 매도:", result)

            if result and 'price' in result:
                KA.SendMessage(f"Upbit {TR_time[0]}, {t+1}/{TR_time[1]}, {ticker} 분할 매도 수량: {volume}")
            else:
                KA.SendMessage(f"Upbit {TR_time[0]}, {t+1}/{TR_time[1]} {ticker} 주문 실패")

        except Exception as order_error:
            print(f"주문 {t+1}회차 오류: {order_error}")
            KA.SendMessage(f"Upbit {TR_time[0]}, {t+1}/{TR_time[1]} {ticker} 분할 매도 오류: {order_error}")

    return result
# 매수주문
def partial_buying(ticker, current_price, krw_per_times, TR_time, upbit):        
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
            time_module.sleep(0.2)
            
            if isinstance(prices[t], list):
                price = prices[t][0]
            else:
                price = prices[t]
            volume = round(krw_per_times / price, 8)
            
            # 주문 금액 체크 - 실제 주문 금액으로 검증
            order_amount = volume * price
            if order_amount < 5500:  # 5500원으로 체크
                KA.SendMessage(f"Upbit {TR_time[0]}, {t+1}회차 {ticker} 주문금액 부족으로 스킵")
                continue
                
            result = upbit.buy_limit_order(ticker, price, volume)
            print(f"{TR_time[0]}차 {t+1}/{TR_time[1]} {ticker} 분할 매수", result)
            
            if result and 'price' in result:
                KA.SendMessage(f"Upbit {TR_time[0]}, {t+1}/{TR_time[1]} {ticker} 분할 매수 수량: {volume}")
            else:
                KA.SendMessage(f"Upbit {TR_time[0]}, {t+1}/{TR_time[1]} {ticker} 분할 매수 오류")
                
        except Exception as order_error:
            print(f"주문 {t+1}회차 오류: {order_error}")
            KA.SendMessage(f"Upbit {TR_time[0]}, {t+1}/{TR_time[1]} {ticker} 분할 매수 오류: {order_error}")

    return result

# 직전 1시간 체결 주문 확인 함수
def check_filled_orders_last_hour(upbit, ticker):
    """
    Args:
        upbit: Upbit 객체
        ticker: "KRW-ETH" 또는 "KRW-BTC"
    
    Returns:
        tuple: (사용된 총 KRW, 체결된 총 수량)
    """
    total_krw_used = 0.0
    total_volume_filled = 0.0
    
    try:
        # UTC 타임존으로 현재 시간 계산
        utc_tz = timezone.utc
        now = datetime.now(utc_tz)
        one_hour_ago = now - timedelta(hours=1)
        
        # 체결 완료된 주문 조회 (최근 100개)
        filled_orders = upbit.get_order(ticker, state='done', limit=100)
        
        if not filled_orders:
            print(f"{ticker} 직전 1시간 체결 내역 없음")
            return 0.0, 0.0
        
        for filled_order in filled_orders:
            # 주문 체결 시간 파싱
            created_at_str = filled_order.get('created_at', '')
            if not created_at_str:
                continue
            
            # ISO 8601 형식 파싱 (타임존 정보 포함)
            try:
                # Python 3.7+ 지원: fromisoformat으로 타임존 자동 처리
                created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
            except:
                continue
            
            # 1시간 이내의 주문만 확인 (타임존 자동 변환되어 비교)
            if created_at < one_hour_ago:
                continue
            
            # 매수 주문만 확인
            if filled_order['side'] == 'bid':
                executed_volume = float(filled_order.get('executed_volume', 0))
                avg_price = float(filled_order.get('avg_price', 0))
                paid_fee = float(filled_order.get('paid_fee', 0))
                
                krw_used = (executed_volume * avg_price) + paid_fee
                total_krw_used += krw_used
                total_volume_filled += executed_volume
                
                print(f"체결 확인: {ticker} 매수 {executed_volume:.8f}개, "
                      f"평균가 {avg_price:.0f}원, 수수료 {paid_fee:.0f}원, "
                      f"시간: {created_at_str}")
        
        KA.SendMessage(f"{ticker} 직전 1시간 체결 요약: 사용 KRW {total_krw_used:.0f}원")
        KA.SendMessage(f"체결량 {total_volume_filled:.8f}개")
        
        return total_krw_used, total_volume_filled
    
    except Exception as e:
        print(f"{ticker} 체결 확인 중 오류: {e}")
        KA.SendMessage(f"Upbit {ticker} 체결 확인 오류: {e}")
        return 0.0, 0.0

# ETH와 BTC 모두의 직전 1시간 매수 체결 내역을 확인하는 래퍼 함수
def check_all_filled_orders_last_hour(upbit):
    """
    Args:
        upbit: Upbit 객체
    
    Returns:
        dict: {
            'ETH_krw_used': float,
            'ETH_volume_filled': float,
            'BTC_krw_used': float,
            'BTC_volume_filled': float,
            'total_krw_used': float
        }
    """
    # ETH 체결 확인
    eth_krw, eth_volume = check_filled_orders_last_hour(upbit, "KRW-ETH")
    
    # BTC 체결 확인
    btc_krw, btc_volume = check_filled_orders_last_hour(upbit, "KRW-BTC")
    
    result = {
        'KRWETH_used': eth_krw,
        'ETH_volume_filled': eth_volume,
        'KRWBTC_used': btc_krw,
        'BTC_volume_filled': btc_volume,
    }
    
    return result

# 종합 잔고조회
def Total_balance(upbit):
    KRW = upbit.get_balance_t("KRW")
    ETH = upbit.get_balance_t("ETH")
    BTC = upbit.get_balance_t("BTC")
    Total = KRW + (ETH * pyupbit.get_current_price("KRW-ETH") * 0.9995) + (BTC * pyupbit.get_current_price("KRW-BTC") * 0.9995)

    return KRW, ETH, BTC, Total