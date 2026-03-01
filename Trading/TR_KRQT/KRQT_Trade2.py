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
KRQT_day_path = "/var/autobot/TR_KRQT/KRQT_day.json" # json
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
            # 최후의 수단: 텔레그램으로 데이터 전송
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
    with open(KRQT_day_path, 'r', encoding='utf-8') as f:
        TR = json.load(f)
except Exception as e:
    TA.send_tele(f"KRQT_day.json 파일 오류: {e}")
    sys.exit(1)
    
# 일자와 회차 시간데이터 불러오기
order = order_time(day=TR['day'])
message.append(f"KRQT: {order['day']}일차 {order['round']}/{order['total_round']}회차 매매를 시작합니다.")

# 전회 주문 취소
summary = KIS.cancel_all_KR_unfilled_orders(side = 'all')
if isinstance(summary, dict):
    message.append(f"KRQT: {summary['success']}/{summary['total']} 주문 취소 성공")
else:
    message.append(f"KRQT: 주문 취소 에러발생")

# 회차별 target 데이터 불러오기 (1, 8회차 불러오기와 계산)
if order['round'] == 1 or order['round'] == 8:
    # 목표종목 csv파일 불러오기 > Dic, JSON 변환
    try:
        with open(KRQT_stock_path, 'r', encoding='utf-8') as f:
            Target = pd.read_csv(f, dtype={
                "code": str,
                "name": str,
                "weight": float,
                "category": str
            })
    except Exception as e:
        TA.send_tele(f"KRQT_stock.csv 파일 오류: {e}")
        sys.exit(1)

    # 중복 종목 비중 합산
    Target["code"] = Target["code"].str[1:]

    grouped = Target.groupby("code").agg(
        name=("name", "first"),
        weight=("weight", "sum"),
        categories=("category", list)  # 전략 목록 보존
    ).reset_index()

    target = {
        str(row["code"]): {
            "name":       str(row["name"]),
            "weight":     float(row["weight"]),
            "categories": [str(c) for c in row["categories"]],  # ['모멘텀'] or ['모멘텀', '피크']
        }
        for _, row in grouped.iterrows()
    }

    # 총 원화 평가금액 > 투자금액(99%) 산출
    account = KIS.get_KR_account_summary()
    if isinstance(account, dict):
        total_invest = account['total_krw_asset'] * 0.99 # cash는 1%유지
    else:
        TA.send_tele(f"KRQT: 총 원화평가금 조회 불가로 종료합니다. ({account})")
        sys.exit(1)

    # 종목별 목표 투자금액 및 수량 산출 
    target_code = list(target.keys())
    for i in target_code:
        price = KIS.get_KR_current_price(i)
        if price == 0 or not isinstance(price, int):
            TA.send_tele(f"KRQT: 현재가 조회 불가로 종료합니다. ({price})")
            sys.exit(0)
        target[i]['target_invest'] = int(target[i]['weight'] * total_invest)
        target[i]['target_qty'] = int(target[i]['target_invest'] / price)
        time_module.sleep(0.1)

    # 당일 target 저장하기
    json_message = save_json(target, KRQT_target_path)
    message.extend(json_message)

else: # 1회, 8회차가 아닌 경우 불러오기만 시행
    # 당일 target 불러오기
    target = {}
    try:
        with open(KRQT_target_path, 'r', encoding='utf-8') as f:
            target = json.load(f)
    except Exception as e:
        TA.send_tele(f"KRQT_target.json 파일 오류: {e}")
        sys.exit(1)
    target_code = list(target.keys())

# 보유 종목 잔고 불러오기
stocks = KIS.get_KR_stock_balance()
if not isinstance(stocks, list):
    TA.send_tele(f"KRQT: 잔고 조회 불가로 종료합니다. ({stocks})")
    sys.exit(1)

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
    message.append("KRQT:매도 종목 없음")

elif len(sell_code) > 0 and sell_split[0] > 0:
    message.append(f"KRQT: {order_time['round']}회차 - 매도 주문")
    for code, qty in sell.items():
        split_qty = int(qty // sell_split[0])
        if split_qty < 1:
            sell_split[0] = 1
            sell_split[1] = [0.99]
            split_qty = int(qty)

        price = KIS.get_KR_current_price(code)
        if price == 0 or not isinstance(price, int):
            message.append(f"KRQT: 현재가 조회 불가로 종료합니다. ({price})")
            sys.exit(1)

        for i in range(sell_split[0]):
            split_price = float(price * sell_split[1][i])
            order_price= KIS.round_to_tick(price=split_price, market="KR") 
            order_info = KIS.order_sell_KR(code, split_qty, order_price, "00")
            message.extend(order_info)
            time_module.sleep(0.125)

# 매도 매수 시간딜레이
time_module.sleep(600)
# 매수구간 전환
# 주문가능 금액 조회 및 주문수량 구하기
KRW = KIS.get_KR_orderable_cash()
if not isinstance(KRW, float):
    TA.send_tele(f"KRQT: 주문가능현금 조회 불가로 종료합니다. ({KRW})")
    sys.exit(1)

# 주문가능금액에 맞춰 매수잔고 재조정
orderable_KRW = KRW
target_KRW = 0

for code, qty in buy.items():
    price = KIS.get_KR_current_price(code)
    if not isinstance(price, int) or price == 0:
        message.append(f"KRQT: 현재가 조회 불가로 종료합니다. ({price})")
        sys.exit(1)
    ticker_invest = price * qty
    target_KRW += ticker_invest
    time_module.sleep(0.125)

if target_KRW > orderable_KRW:
    adjust_rate = orderable_KRW / target_KRW
    for ticker, ticker_qty in buy.items():
        buy[ticker] = int(ticker_qty * adjust_rate)
else:
    pass # 예수금이 충분할 경우 조정 없음

# 매수주문
buy_code = list(buy.keys())

if len(buy_code) == 0:
    message.append("KRQT:매수 종목 없음")

elif len(buy_code) > 0 and buy_split[0] > 0:
    message.append(f"KRQT: {order_time['round']}회차 - 매수 주문")
    for code, qty in buy.items():
        split_qty = int(qty // sell_split[0])
        if split_qty < 1:
            sell_split[0] = 1
            sell_split[1] = [1.01]
            split_qty = int(qty)

        price = KIS.get_KR_current_price(ticker)
        if not isinstance(price, int) or price == 0:
            message.append(f"KRQT: 현재가 조회 불가로 종료합니다. ({price})")
            sys.exit(1)

        for i in range(buy_split[0]):
            split_price = float(price * sell_split[1][i])
            order_price= KIS.round_to_tick(price=split_price, market="KR") 
            order_info = KIS.order_buy_KR(code, split_qty, order_price, "00")
            message.extend(order_info)
            time_module.sleep(0.125)

# 7회차에는 day = 2로 전환
if order_time['round'] == 7:
    TR = {
        "day": 2
    }
    json_message = save_json(TR, KRQT_day_path)
    message.extend(json_message)

# 14회차에는 day = 1로 전환 및 최종 매매 데이터 telegram 출력 및 Google sheet 전략별 잔고 - 종목별 매입량 매입가 기록
if order_time['round'] == 14:
    TR = {
        "day": 1
    }
    json_message = save_json(TR, KRQT_day_path)
    message.extend(json_message)








#     sys.exit(0)

# elif order_time['round'] == 25:  # 최종기록
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






"""
수익률 추적 시에는 categories를 기준으로 전략별로 역산하면 됩니다.
예: 전략별 종목/비중 역산
중복 종목의 경우 합산 비중(0.2)을 전략 수(2)로 나눠 각 전략에 원래 비중(0.1)을 돌려놓는 방식이라
나중에 전략별 수익률 계산할 때 비중 왜곡 없이 쓸 수 있어요.

strategy_stocks = {}
for code, info in target.items():
    for cat in info["categories"]:
        if cat not in strategy_stocks:
            strategy_stocks[cat] = {}
        strategy_stocks[cat][code] = {
            "name": info["name"],
            "weight": info["weight"] / len(info["categories"])  # 전략별 원래 비중으로 분리
        } 
"""