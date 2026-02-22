import sys
import json
import kakao_alert as KA
from datetime import datetime, timedelta as time_obj
import pandas as pd
import time as time_module
from tendo import singleton
import KIS_KR

try:
    me = singleton.SingleInstance()
except singleton.SingleInstanceException:
    KA.SendMessage("KRQT: 이미 실행 중입니다.")
    sys.exit(0)

# KIS instance 생성
key_file_path = "/var/autobot/TR_KRQT/kis43018646nkr.txt"
token_file_path = "/var/autobot/TR_KRQT/kis43018646_token.json"
cano = "43018646"
acnt_prdt_cd = "01"
KIS = KIS_KR.KIS_API(key_file_path, token_file_path, cano, acnt_prdt_cd)

sell_tax = KIS.sell_fee_tax  # 매도 수수료 0.014% + 세금 0.2% KRQT계좌
buy_tax = KIS.buy_fee_tax  # 매수 수수료 0.014% KRQT 계좌
KRQT_day_path = "/var/autobot/TR_KRQT/KRQT_day.json" # json
KRQT_target_path = "/var/autobot/TR_KRQT/KRQT_target.json" # json
KRQT_stock_path = "/var/autobot/TR_KRQT/KRQT_stock.csv" # csv

def order_time(day=1):
    """거래일자와 거래회차 확인""" 
    # 현재 날짜와 시간 확인 UTC시간대
    now = datetime.now()
    current_date = now.date()
    current_time = now.time()

    # 수정: 모든 키를 미리 초기화
    order_time = {
        'date': current_date,
        'time': current_time,
        'TR_day': day,          # 기본값
        'round': 0,        # 기본값
        'total_round': 14  # 기본값
    }
    
    current = time_obj(current_time.hour, current_time.minute)
    start = time_obj(0, 0)   # OTC+9 09:00
    end = time_obj(6, 35)    # OTC+15 15:30    
    if start <= current < end:
        order_time['round'] = (current_time.hour + 1) + (day * 7 - 7)

    return order_time

def health_check():
    """시스템 상태 확인"""
    checks = []
    
    # 1. API 토큰 유효성
    if not KIS.access_token:
        checks.append("KRQT 체크: API 토큰 없음")
    
    # 2. data 파일 존재
    import os
    files = [
        "/var/autobot/TR_KRQT/KRQT_TR.json",
        "/var/autobot/TR_KRQT/KRQT_stock.csv"
    ]
    for f in files:
        if not os.path.exists(f):
            checks.append(f"KRQT 체크: data파일 없음: {f}")
    
    # 3. 네트워크 연결
    try:
        import socket
        socket.create_connection(("openapi.koreainvestment.com", 9443), timeout=5)
    except:
        checks.append("KRQT 체크: KIS API 서버 접속 불가")
    
    if checks:
        KA.SendMessage("\n".join(checks))
        sys.exit(1)

def caculate_trading_qty():
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

    # 종목코드 리스트
    target_code = list(target.keys())
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

    return buy, sell

def save_json(data, path):
    """
    저장 실패 시에도 백업 파일 생성
    """  
    try:
        # 정상
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        
    except Exception as e:
        KA.SendMessage(f"JSON 파일 저장 오류: {e}")
    
    return None
    
def split_data(round):
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

def send_messages_in_chunks(message, max_length=1000):
    current_chunk = []
    current_length = 0
    
    for msg in message:
        msg_length = len(msg) + 1  # \n 포함
        if current_length + msg_length > max_length:
            KA.SendMessage("\n".join(current_chunk))
            time_module.sleep(1)
            current_chunk = [msg]
            current_length = msg_length
        else:
            current_chunk.append(msg)
            current_length += msg_length
    
    if current_chunk:
        KA.SendMessage("\n".join(current_chunk))

# ============================================
# 메인 로직 # 분기 리밸런싱
# ============================================
checkday = KIS.is_KR_trading_day()
if checkday == False:
    KA.SendMessage("KRQT: 거래일이 아닙니다.")
    sys.exit(0)
health_check() # 시스템 상태 확인
message = [] # 출력메시지 LIST 생성

# KRQT_TR.json 불러오기
try:
    with open(KRQT_day_path, 'r', encoding='utf-8') as f:
        TR = json.load(f)
except Exception as e:
    KA.SendMessage(f"KRQT_day JSON 파일 오류: {e}")
    sys.exit(0)
    
# 일자와 회차 시간데이터 불러오기
order = order_time(day=TR['day'])

# 전회 주문 취소
summary = KIS.cancel_all_KR_unfilled_orders(side = 'all')
message.extend(f"{summary["success"]}/{summary["total"]} 주문 취소 성공")

# 회차별 target 데이터 불러오기
if order['round'] == 1:
    # 목표종목 csv파일 불러오기 > Dic, JSON 변환
    try:
        with open(KRQT_stock_path, 'r', encoding='utf-8') as f:
            Target = pd.read_csv(f, dtype={
                "code": str,    # 코드 > 문자열
                "name": str,    # 종목 > 문자열
                "weight": float # 비중 > 실수
            })
    except Exception as e:
        KA.SendMessage(f"KRQT_stock.csv 파일 오류: {e}")
        sys.exit(0)

    # day별 목표 수량 산출(1회차, 8회차)
    target = {}
    for _, row in Target.iterrows():
        code = row["code"][1:]
        target[code] = {       # str
            "name":   row["name"],       # str
            "weight": row["weight"],     # float
        }

    # json파일 저장하기
    save_json(target, KRQT_target_path)

elif 1 < order['round'] < 15:
    # 당일 target 불러오기
    target = {}
    try:
        with open(KRQT_target_path, 'r', encoding='utf-8') as f:
            target = json.load(f)
    except Exception as e:
        KA.SendMessage(f"KRQT_target.json 파일 오류: {e}")
        sys.exit(0)
    
# 총 원화 평가금액 > 투자금액(99%) 산출
account = KIS.get_KR_account_summary()
total_invest = account['total_krw_asset'] * 0.99 # cash는 1%유지

# 종목별 목표 매도금액 및 매도수량 산출 
for i in code:
    price = KIS.get_KR_current_price(i)
    if not isinstance(price, float) or price == 0:
        KA.SendMessage(f"KR: 현재가 조회 불가로 종료합니다. ({price})")
        sys.exit(0)
    price = int(price)
    target[i]['target_invest'] = int(target[i]['weight'] * total_invest)
    target[i]['target_qty'] = int(target[i]['target_invest'] / price)
    time_module.sleep(0.125)

# 매도, 매수 주문 수량 구하기
buy, sell = caculate_trading_qty()

# 분할 주문 수량 구하기
round_split = split_data(order_time['round'])
sell_split = [round_split["sell_splits"], round_split["sell_price"]]

# 매도코드
sell_code = list(sell.keys())

# 매도주문
if len(sell_code) > 0 and sell_split[0] > 0:
    for ticker in sell_code:
        total_qty = sell[ticker]
        split_qty = int(total_qty // sell_split[0])
        if split_qty < 1:
            sell_split[0] = 1
            sell_split[1] = [0.99]

        current_price = KIS.get_KR_current_price(ticker)
        if not isinstance(current_price, float) or current_price == 0:
            continue

        for i in range(sell_split[0]):
            split_price = float(current_price * sell_split[1][i])
            order_price= KIS.round_to_tick(price=split_price, market="KR") 
            order_info = KIS.order_sell_KR(ticker, split_qty, order_price, "00")
            # 메세지 만들기
            time_module.sleep(0.125)

# 매도 매수 시간딜레이
time_module.sleep(600)

# 총 원화 평가금액 > 투자금액(99%) 산출 > 주문가능금액 산출
account = KIS.get_KR_account_summary()
if not isinstance(account , dict):
    KA.SendMessage(f"KRQT: 총 원화평가금 조회 불가로 종료합니다. ({account})")
    sys.exit(0)
total_invest = account['total_krw_asset'] * 0.99 # cash는 1%유지
KRW = KIS.get_KR_orderable_cash()
if not isinstance(KRW , float):
    KA.SendMessage(f"KRQT: 현재가 조회 불가로 종료합니다. ({KRW})")
    sys.exit(0)
KRW_rate = KRW / total_invest

# 종목별 목표 매수금액 및 매수수량 산출 
for i in code:
    price = KIS.get_KR_current_price(i)
    if not isinstance(price, float) or price == 0:
        KA.SendMessage(f"KRQT: 현재가 조회 불가로 종료합니다. ({price})")
        sys.exit(0)
    price = int(price)

    target[i]['target_invest'] = int(target[i]['weight'] * total_invest)
    target[i]['target_qty'] = int(target[i]['target_invest'] / price)
    time_module.sleep(0.125)

# 매도, 매수 주문 수량 구하기
buy, sell = caculate_trading_qty()

# 분할 주문 수량 구하기
round_split = split_data(order_time['round'])
buy_split = [round_split["buy_splits"], round_split["buy_price"]]

# 매수코드 + 매수주문 수량 조정(매수주문가능 금액 / 전체 평가금액 비율) 
buy_code = list(buy.keys())
for ticker in buy_code:
    buy[ticker] = int(buy[ticker] * KRW_rate)

# 매수주문
if len(buy_code) > 0 and buy_split[0] > 0:
    message.append(f"-매수 주문-")
    for ticker in buy_code:
        total_qty = buy[ticker]
        split_qty = int(total_qty // buy_split[0])
        if split_qty < 1:
            buy_split[0] = 1
            buy_split[1] = [1.01]

        current_price = KIS.get_KR_current_price(ticker)
        if not isinstance(current_price, float) or current_price == 0:
            continue

        for i in range(buy_split[0]):
            split_price = float(current_price * buy_split[1][i])
            order_price= KIS.round_to_tick(price=split_price, market="KR") 
            order_info = KIS.order_buy_KR(ticker, split_qty, order_price, "00")
            # 메세지 만들기
            time_module.sleep(0.125)

if order_time['round'] == 7:
    TR = {
        "day": 2,
    }
    save_json(TR, KRQT_day_path)

if order_time['round'] == 14:
    message = []
    message.append(f"KRQT: 2일차 14회차 모든 매매완료 정리")
    stocks = KIS.get_KR_stock_balance()
    if isinstance (stocks, list):
        for i in stocks:
            if i["종목명"] in target.keys():
                message.append(f"target주식 {stocks[i]["종목명"]}: {stocks[i]['보유수량']}")
            else:
                message.append(f"target 외 {stocks[i]['종목명']}: {stocks[i]['보유수량']}")
    else:
        message.append(f"KRQT: 잔고 조회 불가로 종료합니다. ({stocks})")

    balance = KIS.get_KR_account_summary()
    if isinstance(balance, dict):
        message.append(f"주식 평가금: {balance['total_krw_asset']}")
        message.append(f"원화 예수금: {balance['cash_balance']}")
        message.append(f"전체 원화자산: {balance['total_krw_asset']}")
    else:
        message.append(f"KRQT: 총 원화평가금액 조회 불가로 종료합니다. ({balance})")

    TR = {
        "day": 1,
    }

    save_json(TR, KRQT_day_path)
    send_messages_in_chunks(message, max_length=1000)

sys.exit(0)

