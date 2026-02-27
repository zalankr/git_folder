import sys
import json
import telegram_alert as TA
from datetime import datetime, timedelta as time_obj
import pandas as pd
import requests
import calendar
import time as time_module
from tendo import singleton
import KIS_KR

try:
    me = singleton.SingleInstance()
except singleton.SingleInstanceException:
    TA.send_tele("KRQT: 이미 실행 중입니다.")
    sys.exit(0)

# KIS instance 생성
key_file_path = "/var/autobot/TR_KRQT/kis43018646nkr.txt"
token_file_path = "/var/autobot/TR_KRQT/kis43018646_token.json"
cano = "43018646"
acnt_prdt_cd = "01"
KIS = KIS_KR.KIS_API(key_file_path, token_file_path, cano, acnt_prdt_cd)

sell_tax = KIS.sell_fee_tax  # 매도 수수료 0.014% + 세금 0.2% KRQT계좌
buy_tax = KIS.buy_fee_tax  # 매수 수수료 0.014% KRQT 계좌
KRQT_TR_path = "/var/autobot/TR_KRQT/KRQT_TR.json" # json
KRQT_target_path = "/var/autobot/TR_KRQT/KRQT_target.json" # json
KRQT_stock_path = "/var/autobot/TR_KRQT/KRQT_stock.csv" # csv

def order_time(day=1): #
    """거래일자와 거래회차 확인""" 
    # 현재 날짜와 시간 확인 UTC시간대
    now = datetime.now()
    current_date = now.date()
    current_time = now.time()

    # 수정: 모든 키를 미리 초기화
    order_time = {
        'date': current_date,
        'time': current_time,
        'day': day,          # 기본값
        'round': 0,        # 기본값
        'total_round': 14  # 기본값
    }
    
    current = time_obj(current_time.hour, current_time.minute)
    start = time_obj(0, 0)   # OTC+9 09:00
    end = time_obj(6, 35)    # OTC+15 15:30    
    if start <= current < end:
        order_time['round'] = (current_time.hour + 1) + (day * 7 - 7)

    return order_time

def health_check(): #
    """시스템 상태 확인"""
    checks = []
    
    # 1. API 토큰 유효성
    if not KIS.access_token:
        checks.append("KRQT체크: API 토큰 없음")
    
    # 2. data 파일 존재
    import os
    files = [
        "/var/autobot/TR_KRQT/KRQT_TR.json",
        "/var/autobot/TR_KRQT/KRQT_stock.csv"
    ]
    for f in files:
        if not os.path.exists(f):
            checks.append(f"KRQT체크: data파일 없음: {f}")
    
    # 3. 네트워크 연결
    try:
        import socket
        socket.create_connection(("openapi.koreainvestment.com", 9443), timeout=5)
    except:
        checks.append("KRQT체크: KIS API 서버 접속 불가")
    
    if checks:
        TA.send_tele("\n".join(checks))
        sys.exit(1)

def get_balance():
    # 현재의 종합잔고를 USLA, HAA, CASH별로 산출 & 총잔고 계산
    USD_account = KIS.get_US_dollar_balance()
    if USD_account:
        USD = USD_account.get('withdrawable', 0)  # 키가 없을 경우 0 반환
    else:
        USD = 0  # API 호출 실패 시 처리
    time_module.sleep(0.1)

    USLA_balance = 0 # 해당 모델 현재 달러화 잔고
    USLA_qty = {} # 해당 티커 현재 보유량
    USLA_price  = {} # 해당 티커 현재 가격
    for ticker in USLA_ticker:
        balance = KIS.get_ticker_balance(ticker)
        if isinstance(balance, dict):  # 딕셔너리인 경우만 처리
            eval_amount = balance.get('eval_amount', 0)
            USLA_qty[ticker] = balance.get('holding_qty', 0)
            USLA_price[ticker] = balance.get('current_price', 0)
        else:
            eval_amount = 0  # 문자열(에러) 반환 시 처리
            USLA_qty[ticker] = 0
            USLA_price[ticker] = 0
        USLA_balance += eval_amount
        time_module.sleep(0.1)

    HAA_balance = 0 # 해당 모델 현재 달러화 잔고
    HAA_qty = {} # 해당 티커 현재 보유량
    HAA_price  = {} # 해당 티커 현재 가격
    for ticker in HAA_ticker:
        if ticker == 'TIP':
            continue # TIP은 Regime signal 확인용으로 투자, 보유용이 아니라서 제외
        balance = KIS.get_ticker_balance(ticker)
        if isinstance(balance, dict):  # 딕셔너리인 경우만 처리
            eval_amount = balance.get('eval_amount', 0)
            HAA_qty[ticker] = balance.get('holding_qty', 0)
            HAA_price[ticker] = balance.get('current_price', 0)
        else:
            eval_amount = 0  # 문자열(에러) 반환 시 처리
            HAA_qty[ticker] = 0
            HAA_price[ticker] = 0
        HAA_balance += eval_amount
        time_module.sleep(0.1)

    Total_balance = USLA_balance + HAA_balance + USD # 전체 잔고

    return USD, USLA_balance, USLA_qty, USLA_price, HAA_balance, HAA_qty, HAA_price, Total_balance

def Selling(USLA, HAA, sell_split_USLA, sell_split_HAA, order_time):
    """
    매도 주문 실행 함수 - 개선버전 (메시지 통합)
    
    Parameters:
    - USLA: USLA 모델 내 티커별 트레이딩 딕셔너리
    - HAA: HAA 모델 내 티커별 트레이딩 딕셔너리
    - sell_split_USLA: USLA 모델의 분할 정보 [분할횟수, [가격조정비율 리스트]]
    - sell_split_HAA: HAA 모델의 분할 정보 [분할횟수, [가격조정비율 리스트]]
    - order_time: 현재 주문 시간 정보 딕셔너리  # 추가
    
    Returns:
    - Sell_order: 주문 결과 리스트 (성공/실패 모두 포함)
    """  
    Sell_order = []
    order_messages = []
    
    # 수정: 함수 내부에서 호출하지 않고 매개변수로 받음
    round_info = f"{order_time['round']}/{order_time['total_round']}회 매도주문"
    order_messages.append(round_info)

    Sell_USLA = {}
    for ticker in USLA.keys():
        if USLA[ticker]['sell_qty'] > 0:
            Sell_USLA[ticker] = int(USLA[ticker]['sell_qty'])

    Sell_HAA = {}
    for ticker in HAA.keys():
        if HAA[ticker]['sell_qty'] > 0:
            Sell_HAA[ticker] = int(HAA[ticker]['sell_qty'])

    Sell = {**Sell_USLA, **Sell_HAA}

    if len(Sell.keys()) == 0:
        order_messages.append("매도 종목이 없습니다.")
        return Sell_order, order_messages

    for ticker in Sell.keys():
        if Sell[ticker] == 0:
            continue
        
        # ✅ 핵심 수정: 티커별로 올바른 분할 설정 사용
        if ticker in USLA_ticker:
            split_count = sell_split_USLA[0]
            price_multipliers = sell_split_USLA[1]
        else:
            split_count = sell_split_HAA[0]
            price_multipliers = sell_split_HAA[1]
        
        qty_per_split = int(Sell[ticker] // split_count)

        if ticker in USLA_ticker:
            current_price = USLA[ticker].get("current_price", 0)
        else:
            current_price = HAA[ticker].get("current_price", 0)

        if not isinstance(current_price, (int, float)) or current_price <= 0:
            error_msg = f"{ticker} 가격 조회 실패 - 매도 주문 스킵"
            order_messages.append(error_msg)
            Sell_order.append({
                'success': False,
                'ticker': ticker,
                'quantity': Sell[ticker],
                'price': 0,
                'order_number': '',
                'order_time': datetime.now().strftime('%H%M%S'),
                'error_message': error_msg,
                'split_index': -1
            })
            continue

        for i in range(split_count):
            if i == split_count - 1:
                quantity = int(Sell[ticker] - qty_per_split * (split_count - 1))
            else:
                quantity = qty_per_split
            
            if quantity == 0:
                continue

            price = round(current_price * price_multipliers[i], 2)
                
            try:
                order_info, order_sell_message = KIS.order_sell_US(ticker, quantity, price)
                order_messages.extend(order_sell_message)
                
                if order_info and order_info.get('success') == True:
                    order_info = {
                        'success': True,
                        'ticker': ticker,
                        'quantity': quantity,
                        'price': price,
                        'order_number': order_info.get('order_number', ''),
                        'order_time': order_info.get('order_time', ''),
                        'org_number': order_info.get('org_number', ''),
                        'message': order_info.get('message', ''),
                        'split_index': i
                    }
                    Sell_order.append(order_info)
                else:
                    error_msg = order_info.get('error_message', 'Unknown error') if order_info else 'API 호출 실패'
                    Sell_order.append({
                        'success': False,
                        'ticker': ticker,
                        'quantity': quantity,
                        'price': price,
                        'order_number': '',
                        'order_time': datetime.now().strftime('%H%M%S'),
                        'error_message': error_msg,
                        'split_index': i
                    })
            except Exception as e:
                error_msg = f"Exception: {str(e)}"
                order_messages.append(f"❌ {ticker} {quantity}주 @${price} - {error_msg}")
                Sell_order.append({
                    'success': False,
                    'ticker': ticker,
                    'quantity': quantity,
                    'price': price,
                    'order_number': '',
                    'order_time': datetime.now().strftime('%H%M%S'),
                    'error_message': error_msg,
                    'split_index': i
                })
            
            # 같은 티커의 분할 주문 사이는0.2초, 다른 티커로 넘어갈 때는 0.2초
            if i < split_count - 1:
                time_module.sleep(0.2)
            else:
                time_module.sleep(0.2)
    
    success_count = sum(1 for order in Sell_order if order['success'])
    total_count = len(Sell_order)
    order_messages.append(f"매도 주문: {success_count}/{total_count} 완료")
    
    return Sell_order, order_messages

def Buying(USLA, HAA, buy_split_USLA, buy_split_HAA, order_time):
    """
    매수 주문 실행 함수 - 버그 수정 버전
    
    Parameters:
    - USLA: USLA 모델 내 티커별 트레이딩 딕셔너리
    - HAA: HAA 모델 내 티커별 트레이딩 딕셔너리
    - buy_split_USLA: USLA 모델의 분할 정보 [분할횟수, [가격조정비율 리스트]]
    - buy_split_HAA: HAA 모델의 분할 정보 [분할횟수, [가격조정비율 리스트]]
    - order_time: 현재 주문 시간 정보 딕셔너리
    
    Returns:
    - Buy_order: 주문 결과 리스트 (성공/실패 모두 포함)
    """
    Buy_order = []
    order_messages = []

    round_info = f"{order_time['round']}/{order_time['total_round']}회 매수주문"
    order_messages.append(round_info)    
    
    Buy_USLA = {}
    for ticker in USLA.keys():
        if USLA[ticker]['buy_qty'] > 0:
            Buy_USLA[ticker] = int(USLA[ticker]['buy_qty'])

    Buy_HAA = {}
    for ticker in HAA.keys():
        if HAA[ticker]['buy_qty'] > 0:
            Buy_HAA[ticker] = int(HAA[ticker]['buy_qty'])

    Buy = {**Buy_USLA, **Buy_HAA}
    
    if len(Buy.keys()) == 0:
        order_messages.append("매수할 종목이 없습니다.")
        return Buy_order, order_messages
    
    for ticker in Buy.keys():
        if Buy[ticker] == 0:
            order_messages.append(f"{ticker} 매수 수량 0")
            continue
        
        # ✅ 핵심 수정: 티커별로 올바른 분할 설정 사용
        if ticker in USLA_ticker:
            split_count = buy_split_USLA[0]
            price_multipliers = buy_split_USLA[1]
        else:
            split_count = buy_split_HAA[0]
            price_multipliers = buy_split_HAA[1]
        
        qty_per_split = int(Buy[ticker] // split_count)

        if ticker in USLA_ticker:
            current_price = USLA[ticker].get("current_price", 0)
        else:
            current_price = HAA[ticker].get("current_price", 0)
        
        if not isinstance(current_price, (int, float)) or current_price <= 0:
            error_msg = f"{ticker} 가격 조회 실패 - 주문 스킵"
            order_messages.append(error_msg)
            Buy_order.append({
                'success': False,
                'ticker': ticker,
                'quantity': Buy[ticker],
                'price': 0,
                'order_number': '',
                'order_time': datetime.now().strftime('%H%M%S'),
                'error_message': error_msg,
                'split_index': -1
            })
            continue

        for i in range(split_count):
            if i == split_count - 1:
                quantity = int(Buy[ticker] - qty_per_split * (split_count - 1))
            else:
                quantity = qty_per_split
            
            if quantity == 0:
                continue

            price = round(current_price * price_multipliers[i], 2)
                
            try:
                order_info, order_buy_message = KIS.order_buy_US(ticker, quantity, price)
                order_messages.extend(order_buy_message)
                
                if order_info and order_info.get('success') == True:
                    order_info = {
                        'success': True,
                        'ticker': ticker,
                        'quantity': quantity,
                        'price': price,
                        'order_number': order_info.get('order_number', ''),
                        'order_time': order_info.get('order_time', ''),
                        'org_number': order_info.get('org_number', ''),
                        'message': order_info.get('message', ''),
                        'split_index': i
                    }
                    Buy_order.append(order_info)
                else:
                    error_msg = order_info.get('error_message', 'Unknown error') if order_info else 'API 호출 실패'
                    Buy_order.append({
                        'success': False,
                        'ticker': ticker,
                        'quantity': quantity,
                        'price': price,
                        'order_number': '',
                        'order_time': datetime.now().strftime('%H%M%S'),
                        'error_message': error_msg,
                        'split_index': i
                    })
            except Exception as e:
                error_msg = f"Exception: {str(e)}"
                order_messages.append(f"❌ {ticker} {quantity}주 @${price} - {error_msg}")
                Buy_order.append({
                    'success': False,
                    'ticker': ticker,
                    'quantity': quantity,
                    'price': price,
                    'order_number': '',
                    'order_time': datetime.now().strftime('%H%M%S'),
                    'error_message': error_msg,
                    'split_index': i
                })

            # 같은 티커의 분할 주문 사이는 0.2초, 다른 티커로 넘어갈 때는 0.2초
            if i < split_count - 1:
                time_module.sleep(0.2)
            else:
                time_module.sleep(0.2)

    success_count = sum(1 for order in Buy_order if order['success'])
    total_count = len(Buy_order)
    order_messages.append(f"매수 주문: {success_count}/{total_count} 완료")

    return Buy_order, order_messages

def save_json(data, path): #
    """
    저장 실패 시에도 백업 파일 생성
    """  
    try:
        # 정상
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        message.append(f"{order_time['time']} {order_time['round']}/{order_time['total_round']}회차 {data} 저장 완료")
        
    except Exception as e:
        # 저장 실패 시 백업 파일 생성
        message.append(f"{data} 저장 실패: {e}")
        
        backup_path = f"/var/autobot/TR_KRQT/{data}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            message.append(f"KRQT {data}백업 파일 생성: {backup_path}")
        except Exception as backup_error:
            message.append(f"KRQT {data}백업 파일 생성도 실패: {backup_error}")
            # 최후의 수단: 카카오로 데이터 전송
            message.append(f"KRQT {data}백업: {json.dumps(data, ensure_ascii=False)[:1000]}")

    return message
    
def split_data(round): #
    '''회차별 분할횟수와 분할당 가격산출'''
    if round == 1:
        sell_splits = 5
        sell_price = [1.020, 1.015, 1.010, 1.005, 0.990]
        buy_splits = 5
        buy_price = [0.980, 0.985, 0.990, 0.995, 1.000]
    elif round == 2:
        sell_splits = 4
        sell_price = [1.020, 1.015, 1.010, 1.005]
        buy_splits = 5
        buy_price = [0.980, 0.985, 0.990, 0.995, 1.010]
    elif round == 3:
        sell_splits = 4
        sell_price = [1.015, 1.010, 1.005, 1.000]
        buy_splits = 4
        buy_price = [0.980, 0.985, 0.990, 0.995]
    elif round == 4:
        sell_splits = 4
        sell_price = [1.015, 1.010, 1.005, 0.990]
        buy_splits = 4
        buy_price = [0.985, 0.990, 0.995, 1.000]
    elif round == 5:
        sell_splits = 3
        sell_price = [1.015, 1.010, 1.005]
        buy_splits = 4
        buy_price = [0.985, 0.990, 0.995, 1.010]
    elif round == 6:
        sell_splits = 3
        sell_price = [1.010, 1.005, 1.000]
        buy_splits = 3
        buy_price = [0.985, 0.990, 0.995]
    elif round == 7:
        sell_splits = 3
        sell_price = [1.010, 1.005, 0.990]
        buy_splits = 3
        buy_price = [0.990, 0.995, 1.000]
    elif round == 8:
        sell_splits = 2
        sell_price = [1.010, 1.005]
        buy_splits = 3
        buy_price = [0.990, 0.995, 1.010]
    elif round == 9:
        sell_splits = 2
        sell_price = [1.005, 1.000]
        buy_splits = 2
        buy_price = [0.990, 0.995]
    elif round == 10:
        sell_splits = 2
        sell_price = [1.005, 0.990]
        buy_splits = 2
        buy_price = [0.995, 1.000]
    elif round == 11:
        sell_splits = 1
        sell_price = [1.005]
        buy_splits = 2
        buy_price = [0.995, 1.010]
    elif round == 12:
        sell_splits = 1
        sell_price = [1.000]
        buy_splits = 1
        buy_price = [0.995]
    elif round == 13:
        sell_splits = 1
        sell_price = [0.970]
        buy_splits = 1
        buy_price = [1.000]
    elif round == 14:
        sell_splits = 0
        sell_price = []
        buy_splits = 1
        buy_price = [1.030]
        
    round_split = {
        "sell_splits": sell_splits, 
        "sell_price": sell_price,
        "buy_splits": buy_splits, 
        "buy_price": buy_price
    }

    return round_split

# ============================================
# 메인 로직 # 분기 리밸런싱
# ============================================
checkday = KIS.is_KR_trading_day()
# if checkday == False:
#     TA.send_tele("KR: 거래일이 아닙니다.")
#     sys.exit(0)
health_check() # 시스템 상태 확인
message = [] # 출력메시지 LIST 생성

# KRQT_TR.json 불러오기
try:
    with open(KRQT_TR_path, 'r', encoding='utf-8') as f:
        TR = json.load(f)
except Exception as e:
    TA.send_tele(f"KRQT_TR JSON 파일 오류: {e}")
    sys.exit(0)
    
# 일자와 회차 시간데이터 불러오기
order = order_time(day=TR['day'])
message.append(f"KRQT: {order['day']}일차 {order['round']}/{order['total_round']}회차 매매를 시작합니다.")

# 전회 주문 취소
summary = KIS.cancel_all_KR_unfilled_orders(side = 'all')
if isinstance(summary, dict):
    message.append(f"{summary['success']}/{summary['total']} 주문 취소 성공")
else:
    message.append(f"주문 취소 에러발생")

# 회차별 target 데이터 불러오기 (1, 8회차는 불러오기 및 계산)
if order['round'] == 1 or order['round'] == 8:
    # 목표종목 csv파일 불러오기 > Dic, JSON 변환
    try:
        with open(KRQT_stock_path, 'r', encoding='utf-8') as f:
            Target = pd.read_csv(f, dtype={
                "code": str,    # 코드 > 문자열
                "name": str,    # 종목 > 문자열
                "weight": float # 비중 > 실수
            })
    except Exception as e:
        TA.send_tele(f"KRQT_stock.csv 파일 오류: {e}")
        sys.exit(1)

    # day별 목표 수량 산출(1회차, 8회차)
    target = {}
    for _, row in Target.iterrows():
        code = row["code"][1:]
        target[code] = {       # str
            "name":   row["name"],       # str
            "weight": row["weight"],     # float
        }

    # 총 원화 평가금액 > 투자금액(99%) 산출
    account = KIS.get_KR_account_summary()
    if isinstance(account, dict):
        total_invest = account['total_krw_asset'] * 0.99 # cash는 1%유지
    else:
        TA.send_tele(f"KRQT: 총 원화평가금 조회 불가로 종료합니다. ({account})")
        sys.exit(0)

    # 종목별 목표 투자금액 및 수량 산출 
    target_code = list(target.keys())
    for i in code:
        price = int(KIS.get_KR_current_price(i))
        if price == 0 or not isinstance(price, int):
            TA.send_tele(f"KRQT: 현재가 조회 불가로 종료합니다. ({price})")
            sys.exit(0)
        target[i]['target_invest'] = int(target[i]['weight'] * total_invest)
        target[i]['target_qty'] = int(target[i]['target_invest'] / price)
        time_module.sleep(0.1)

    # 당일 target 저장하기 ########################################
    json_message = save_json(target, KRQT_target_path)
    message.append(json_message)
else:
    # 당일 target 불러오기
    target = {}
    try:
        with open(KRQT_target_path, 'r', encoding='utf-8') as f:
            target = json.load(f)
    except Exception as e:
        KA.SendMessage(f"KRQT_target.json 파일 오류: {e}")
        sys.exit(0)
    target_code = list(target.keys())

# 보유 종목 잔고 불러오기
stocks = KIS.get_KR_stock_balance()
if not isinstance(stocks, list):
    KA.SendMessage(f"KRQT: 잔고 조회 불가로 종료합니다. ({stocks})")
    sys.exit(0)

hold = {}
for stock in stocks:
    code = stock["종목코드"]
    hold[code] = {
        "name": stock["종목명"],
        "hold_balance": stock["평가금액"],
        "hold_qty": stock["보유수량"],
    }

hold_code = list(hold.keys())

# 투자수량과 잔고수량 비교해서 매수매도수량 산출하기
buy = {}
sell = {}
for code in hold_code:
    if code in target_code:
        if target[code]["target_qty"] > hold[code]["hold_qty"]:
            buy[code] = target[code]["target_qty"] - hold[code]["hold_qty"]
        elif target[code]["target_qty"] < hold[code]["hold_qty"]:
            sell[code] = hold[code]["hold_qty"] - target[code]["target_qty"]
    else:
        sell[code] = hold[code]["hold_qty"]

for code in target_code:
    if code not in hold_code:
        buy[code] = target[code]["target_qty"]

# 분할 주문 수량 구하기
round_split = split_data(order_time['round'])
sell_split = [round_split["sell_splits"], round_split["sell_price"]]
buy_split = [round_split["buy_splits"], round_split["buy_price"]]

# 매도주문
sell_code = list(sell.keys())

if len(sell_code) == 0:
    message.append("매도 종목 없음")

elif len(sell_code) > 0 and sell_split[0] > 0:
    message.append(f"-매도 주문-")
    for ticker in sell_code:
        total_qty = sell[ticker]
        split_qty = int(total_qty // sell_split[0])
        if split_qty < 1:
            sell_split[0] = 1
            sell_split[1] = [0.99]

        current_price = int(KIS.get_KR_current_price(ticker))

        for i in range(sell_split[0]):
            split_price = float(current_price * sell_split[1][i])
            order_price= KIS.round_to_tick(price=split_price, market="KR") 
            order_info, order_message = KIS.order_sell_KR(ticker, split_qty, order_price, "00")
            message.extend(order_message)
            order_message - [] # 메세지 초기화
            time_module.sleep(0.125)

# 매도 매수 시간딜레이
time_module.sleep(600)

# 주문가능 금액 조회 및 주문수량 구하기
KRW = KIS.get_KR_orderable_cash()

if not isinstance(KRW, float):
    KA.SendMessage(f"KRQT: 주문가능현금 조회 불가로 종료합니다. ({KRW})")
    sys.exit(0)

# 주문가능금액에 맞춰 매수잔고 재조정
"""
매수금액 합계보다 주문가능 금액이 모자라면 
"""





# 매수주문
buy_code = list(buy.keys())


    
#     # 예수금에 맞는 주문수량 구하기
#     FULL_BUYUSD = 0
#     price_error = False
    
#     for ticker in USLA_ticker:
#         if USLA[ticker]['current_price'] <= 0:
#             message.append(f"⚠️ {ticker} 가격 조회 실패 - 매수 스킵")
#             USLA[ticker]['buy_qty'] = 0
#             price_error = True
#             continue
#         invest = USLA[ticker]['buy_qty'] * USLA[ticker]['current_price']
#         FULL_BUYUSD += invest
        
#     for ticker in HAA_ticker:
#         if ticker == 'TIP':
#             continue
#         if HAA[ticker]['current_price'] <= 0:
#             message.append(f"⚠️ {ticker} 가격 조회 실패 - 매수 스킵")
#             HAA[ticker]['buy_qty'] = 0
#             price_error = True
#             continue
#         invest = HAA[ticker]['buy_qty'] * HAA[ticker]['current_price']
#         FULL_BUYUSD += invest
        
#     if price_error:
#         message.append("⚠️ 일부 종목 가격 조회 실패로 매수 수량 조정됨")   
        
#     if FULL_BUYUSD > USD:
#         ADJUST_RATE = USD / FULL_BUYUSD
#         for ticker in USLA_ticker:
#             USLA[ticker]['buy_qty'] = int(USLA[ticker]['buy_qty'] * ADJUST_RATE)
#         for ticker in HAA_ticker:
#             HAA[ticker]['buy_qty'] = int(HAA[ticker]['buy_qty'] * ADJUST_RATE)
#     else:
#         pass  # 예수금이 충분할 경우 조정 없음

#     # 매수주문
#     Buy_order, order_messages = Buying(USLA, HAA, buy_split_USLA, buy_split_HAA, order_time)
#     message.extend(order_messages)

#     # 다음 order time으로 넘길 Trading data json 데이터 저장
#     saveTR_message = save_TR_data(order_time, Sell_order, Buy_order, USLA, HAA)
#     message.extend(saveTR_message)
#     send_messages_in_chunks(message, max_length=1000)

#     sys.exit(0)

# elif order_time['round'] in range(2, 25):  # Round 2~24회차
#     # ====================================
#     # 1단계: 지난 라운드 TR_data 불러오기
#     # ====================================
#     try:
#         with open(USAA_TR_path, 'r', encoding='utf-8') as f:
#             TR_data = json.load(f)
#     except Exception as e:
#         message.append(f"USAA_TR JSON 파일 오류: {e}")
#         sys.exit(0)

#     # ============================================
#     # 2단계: 미체결 주문 취소
#     # ============================================
#     try:
#         cancel_summary, cancel_messages = KIS.cancel_all_unfilled_orders()
#         message.extend(cancel_messages)
#         if cancel_summary['total'] > 0:
#             message.append(f"미체결 주문 취소: {cancel_summary['success']}/{cancel_summary['total']}")
#     except Exception as e:
#         message.append(f"USAA 주문 취소 오류: {e}")

#     # ============================================
#     # 3단계: 새로운 주문 준비 및 실행
#     # ============================================
#     # 계좌잔고 조회
#     USD, USLA_balance, USLA_qty, USLA_price, HAA_balance, HAA_qty, HAA_price, Total_balance = get_balance()
    
#     # 목표 비중 만들기
#     USLA = TR_data["USLA"]
#     for ticker in USLA_ticker:
#         USLA[ticker]['hold_qty'] = int(USLA_qty.get(ticker, 0)), # 현재 보유량 업데이트
#         current_price = KIS.get_US_current_price(ticker)
#         time_module.sleep(0.15)
#         USLA[ticker]['current_price'] = current_price # 해당 티커의 현재가
        
#         if current_price <= 0:
#             message.append(f"⚠️ {ticker} 가격 조회 실패 - 거래 스킵")
#             USLA[ticker]['target_qty'] = int(USLA_qty.get(ticker, 0))  # ← 현재 수량 유지 (핵심!)
#             USLA[ticker]['target_balance'] = 0
#             USLA[ticker]['buy_qty'] = 0
#             USLA[ticker]['sell_qty'] = 0
#             continue

#         USLA_target_qty = int((USLA[ticker]['target_weight'] * Total_balance) / USLA[ticker]['current_price'])
#         USLA_target_balance = USLA[ticker]['target_weight'] * Total_balance
#         USLA[ticker]['target_balance'] = USLA_target_balance  # 목표투자금 업데이트
#         USLA[ticker]['target_qty'] = USLA_target_qty  # 목표수량 업데이트
#         USLA[ticker]['buy_qty'] = int(USLA_target_qty - USLA_qty[ticker] if USLA_target_qty > USLA_qty[ticker] else 0)  # 매수 수량 업데이트
#         USLA[ticker]['sell_qty'] = int(USLA_qty[ticker] - USLA_target_qty if USLA_target_qty < USLA_qty[ticker] else 0)  # 매도 수량 업데이트

#     HAA = TR_data["HAA"]
#     for ticker in HAA_ticker:
#         # TIP은 건너뛰기
#         if ticker == 'TIP':
#             continue
#         HAA[ticker]['hold_qty'] = int(HAA_qty.get(ticker, 0))  # 현재 보유량 업데이트
#         current_price = KIS.get_US_current_price(ticker)
#         time_module.sleep(0.15)
#         HAA[ticker]['current_price'] = current_price # 해당 티커의 현재가
#         if current_price <= 0:
#             HAA_target_qty = 0
#             message.append(f"⚠️ {ticker} 가격 조회 실패 - 거래 스킵")
#             HAA[ticker]['target_qty'] = int(HAA_qty.get(ticker, 0))  # ← 현재 수량 유지 (핵심!)
#             HAA[ticker]['target_balance'] = 0
#             HAA[ticker]['buy_qty'] = 0
#             HAA[ticker]['sell_qty'] = 0
#             continue

#         HAA_target_qty = int((HAA[ticker]['target_weight'] * Total_balance) / HAA[ticker]['current_price'])
#         HAA_target_balance = HAA[ticker]['target_weight'] * Total_balance
#         HAA[ticker]['target_balance'] = HAA_target_balance  # 목표투자금 업데이트
#         HAA[ticker]['target_qty'] = HAA_target_qty  # 목표수량 업데이트
#         HAA[ticker]['buy_qty'] = int(HAA_target_qty - HAA_qty[ticker] if HAA_target_qty > HAA_qty[ticker] else 0)  # 매수 수량 업데이트
#         HAA[ticker]['sell_qty'] = int(HAA_qty[ticker] - HAA_target_qty if HAA_target_qty < HAA_qty[ticker] else 0)  # 매도 수량 업데이트

#     # 목표비중 합계 검증
#     total_weight = 0
#     for ticker in USLA.keys():
#         total_weight += USLA[ticker].get('target_weight', 0)
#     for ticker in HAA.keys():
#         total_weight += HAA[ticker].get('target_weight', 0)

#     if total_weight > 1.01:
#         error_msg = f"❌ 목표 비중 초과: {total_weight:.2%}"
#         message.append(error_msg)
#         KA.SendMessage("\n".join(message))
#         sys.exit(1)
#     elif total_weight < 0.90:
#         message.append(f"⚠️ 목표 비중 부족: {total_weight:.2%}")
#     else:
#         message.append(f"✓ 목표 비중 합계: {total_weight:.2%}")

#     # 회차별 분할 데이터 트레이딩
#     round_split = split_data(order_time['round'])
#     sell_split_USLA = [round_split["sell_splits"], round_split["sell_price_USLA"]]
#     buy_split_USLA = [round_split["buy_splits"], round_split["buy_price_USLA"]]
#     sell_split_HAA = [round_split["sell_splits"], round_split["sell_price_HAA"]]
#     buy_split_HAA = [round_split["buy_splits"], round_split["buy_price_HAA"]]

#     # 매도주문
#     Sell_order, order_messages = Selling(USLA, HAA, sell_split_USLA, sell_split_HAA, order_time)
#     message.extend(order_messages)
#     order_messages = [] # 메세지 초기화
    
#     # 예수금에 맞는 주문수량 구하기
#     FULL_BUYUSD = 0
#     price_error = False
    
#     for ticker in USLA_ticker:
#         if USLA[ticker]['current_price'] <= 0:
#             message.append(f"⚠️ {ticker} 가격 조회 실패 - 매수 스킵")
#             USLA[ticker]['buy_qty'] = 0
#             price_error = True
#             continue
#         invest = USLA[ticker]['buy_qty'] * USLA[ticker]['current_price']
#         FULL_BUYUSD += invest

#     for ticker in HAA_ticker:
#         if ticker == 'TIP':
#             continue
#         if HAA[ticker]['current_price'] <= 0:
#             message.append(f"⚠️ {ticker} 가격 조회 실패 - 매수 스킵")
#             HAA[ticker]['buy_qty'] = 0
#             price_error = True
#             continue
#         invest = HAA[ticker]['buy_qty'] * HAA[ticker]['current_price']
#         FULL_BUYUSD += invest

#     if price_error:
#         message.append("⚠️ 일부 종목 가격 조회 실패로 매수 수량 조정됨")   
        
#     if FULL_BUYUSD > USD:
#         ADJUST_RATE = USD / FULL_BUYUSD
#         for ticker in USLA_ticker:
#             USLA[ticker]['buy_qty'] = int(USLA[ticker]['buy_qty'] * ADJUST_RATE)
#         for ticker in HAA_ticker:
#             HAA[ticker]['buy_qty'] = int(HAA[ticker]['buy_qty'] * ADJUST_RATE)
#     else:
#         pass  # 예수금이 충분할 경우 조정 없음
    
#     # 매수주문
#     Buy_order, buy_order_messages = Buying(USLA, HAA, buy_split_USLA, buy_split_HAA, order_time)
#     message.extend(buy_order_messages)

#     # 다음 order time으로 넘길 Trading data json 데이터 저장
#     saveTR_message = save_TR_data(order_time, Sell_order, Buy_order, USLA, HAA)
#     message.extend(saveTR_message)

#     # 메세지 출력
#     send_messages_in_chunks(message, max_length=1000)

#     sys.exit(0)

# elif order_time['round'] == 25:  # 최종기록
#     # ============================================
#     # 1단계: 최종 미체결 주문 취소
#     # ============================================
#     try:
#         cancel_summary, cancel_messages = KIS.cancel_all_unfilled_orders()
#         message.extend(cancel_messages)
#         if cancel_summary['total'] > 0:
#             message.append(f"미체결 주문 취소: {cancel_summary['success']}/{cancel_summary['total']}")
#     except Exception as e:
#         message.append(f"USAA 주문 취소 오류: {e}")
        
#     # ============================================
#     # 2단계: 최종 데이터 출력
#     # ============================================
#     message.append(f"USAA {order_time['date']} 리밸런싱 종료")
    
#     # 계좌잔고 조회
#     USD, USLA_balance, USLA_qty, USLA_price, HAA_balance, HAA_qty, HAA_price, Total_balance = get_balance()

#     USLA_target, USLA_regime, USLA_message = USLA_target_regime()
#     message.append(f"USLA Regime: {USLA_regime}")
#     for i in USLA_target.keys():
#         balance = float(USLA_qty[i]) * float(USLA_price[i])
#         weight = float(balance) / float(Total_balance)
#         message.append(f"USLA {i} - weight:{weight:.2%}, qty:{int(USLA_qty[i])}")
#     HAA_target, HAA_regime, HAA_message = HAA_target_regime()
#     message.append(f"HAA Regime: {HAA_regime}")
#     for i in HAA_target.keys():
#         balance = float(HAA_qty[i]) * float(HAA_price[i])
#         weight = float(balance) / float(Total_balance)
#         message.append(f"HAA {i} - weight:{weight:.2%}, qty:{int(HAA_qty[i])}")
#     message.append(f"USLA 평가금: {USLA_balance:,.2f} USD")
#     message.append(f"HAA 평가금: {HAA_balance:,.2f} USD")
#     message.append(f"USD 평가금: {USD:,.2f} USD")
#     message.append(f"총 평가금: {Total_balance:,.2f} USD")

#     # 카톡 리밸 종료 결과 보내기
#     send_messages_in_chunks(message, max_length=1000)
    
#     sys.exit(0)
# sys.exit(0)

# price = int(KIS.get_KR_current_price("005930"))
# print(f"삼성전자현재가: {price}원")
# result = KIS.get_KR_stock_balance()
# print("\n".join(result))
# balance = KIS.get_KR_account_summary()
# socksbalance = balance['stock_eval_amt']
# cash_balance = balance['cash_balance']
# total_krw_asset = balance['total_krw_asset']
# print(f"주식평가금액: {socksbalance}원 \n원화 잔고: {cash_balance}원 \n전체 원화자산: {total_krw_asset}원")
# KRW =KIS.get_KR_orderable_cash()
# print(f"원화주문가능금액: {KRW}원")