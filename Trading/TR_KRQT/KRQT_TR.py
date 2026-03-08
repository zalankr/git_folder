import sys
import json
import telegram_alert as TA
from datetime import datetime, timedelta as time_obj
import pandas as pd
from collections import defaultdict
import gspread_updater as GU
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
KRQT_result_path = "/var/autobot/TR_KRQT/KRQT_result.json" # json
KRQT_stock_path = "/var/autobot/TR_KRQT/KRQT_stock.csv" # csv

def order_time(day=1):
    """거래일자와 거래회차 확인""" 
    # 현재 날짜와 시간 확인 UTC시간대
    now = datetime.now()
    current_date = now.date()
    current_time = now.time()

    # 수정: 모든 키를 미리 초기화
    result = {
        'date': current_date,
        'time': current_time,
        'day': day,          # 기본값
        'round': 0,        # 기본값
        'total_round': 14  # 기본값
    }
    
    current = time_obj(current_time.hour, current_time.minute)
    start = time_obj(0, 0)   # OTC+9 09:00
    end = time_obj(6, 30)    # OTC+15 15:30    
    if start <= current < end:
        result['round'] = (current_time.hour + 1) + (day * 7 - 7)

    return result

def health_check():
    """시스템 상태 확인"""
    checks = []
    
    # 1. API 토큰 유효성
    if not KIS.access_token:
        checks.append("KRQT체크: API 토큰 없음")
    
    # 2. data 파일 존재
    import os
    files = [
        "/var/autobot/TR_KRQT/KRQT_day.json",
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

def save_json(data, path, order):
    """
    저장 실패 시에도 백업 파일 생성
    """
    result_msgs = []
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        result_msgs.append(f"{order['date']} {order['round']}/{order['total_round']}회차 저장 완료: {path}")
    except Exception as e:
        result_msgs.append(f"{path} 저장 실패: {e}")
        backup_path = f"/var/autobot/TR_KRQT/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            result_msgs.append(f"백업 파일 생성: {backup_path}")
        except Exception as backup_error:
            result_msgs.append(f"백업 실패: {backup_error}")
    return result_msgs   # 새 리스트 반환
    
def split_data(round):
    '''회차별 분할횟수와 분할당 가격산출'''
    if round == 1:
        sell_splits = 5
        sell_price = [1.020, 1.015, 1.010, 1.005, 0.995]
        buy_splits = 5
        buy_price = [0.980, 0.985, 0.990, 0.995, 0.9975]
    elif round == 2:
        sell_splits = 4
        sell_price = [1.020, 1.015, 1.010, 1.005]
        buy_splits = 5
        buy_price = [0.980, 0.985, 0.990, 0.995, 1.005]
    elif round == 3:
        sell_splits = 4
        sell_price = [1.015, 1.010, 1.005, 1.0025]
        buy_splits = 4
        buy_price = [0.980, 0.985, 0.990, 0.995]
    elif round == 4:
        sell_splits = 4
        sell_price = [1.015, 1.010, 1.005, 0.995]
        buy_splits = 4
        buy_price = [0.985, 0.990, 0.995, 0.9975]
    elif round == 5:
        sell_splits = 3
        sell_price = [1.015, 1.010, 1.005]
        buy_splits = 4
        buy_price = [0.985, 0.990, 0.995, 1.005]
    elif round == 6:
        sell_splits = 3
        sell_price = [1.010, 1.005, 1.0025]
        buy_splits = 3
        buy_price = [0.985, 0.990, 0.995]
    elif round == 7:
        sell_splits = 3
        sell_price = [1.010, 1.005, 0.995]
        buy_splits = 3
        buy_price = [0.990, 0.995, 0.9975]
    elif round == 8:
        sell_splits = 2
        sell_price = [1.010, 1.005]
        buy_splits = 3
        buy_price = [0.990, 0.995, 1.005]
    elif round == 9:
        sell_splits = 2
        sell_price = [1.005, 1.0025]
        buy_splits = 2
        buy_price = [0.990, 0.995]
    elif round == 10:
        sell_splits = 2
        sell_price = [1.005, 0.995]
        buy_splits = 2
        buy_price = [0.995, 0.9975]
    elif round == 11:
        sell_splits = 1
        sell_price = [1.005]
        buy_splits = 2
        buy_price = [0.995, 1.005]
    elif round == 12:
        sell_splits = 1
        sell_price = [1.0025]
        buy_splits = 1
        buy_price = [0.995]
    elif round == 13:
        sell_splits = 1
        sell_price = [0.980]
        buy_splits = 1
        buy_price = [0.9975]
    elif round == 14:
        sell_splits = 0
        sell_price = []
        buy_splits = 1
        buy_price = [1.020]
        
    round_split = {
        "sell_splits": sell_splits, 
        "sell_price": sell_price,
        "buy_splits": buy_splits, 
        "buy_price": buy_price
    }

    return round_split

def cancel_orders(side: str="all"):
    """모든 주문 취소"""
    summary = KIS.cancel_all_KR_unfilled_orders(side)
    if isinstance(summary, dict):
        cancel_message = f"KRQT: {summary['success']}/{summary['total']} 주문 취소 성공"
    else:
        cancel_message = f"KRQT: 주문 취소 에러발생"
    return cancel_message

# ============================================
# 메인 로직 # 분기 리밸런싱
# ============================================
checkday = KIS.is_KR_trading_day()
if checkday == False:
    TA.send_tele("KRQT: 거래일이 아닙니다.")
    sys.exit(0)
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

if order['round'] == 0:
    TA.send_tele(f"KRQT: 매매시간이 아닙니다.")
    sys.exit(0)
message.append(f"KRQT: {order['day']}일차 {order['round']}/{order['total_round']}회차 매매를 시작합니다.")

# 전회 주문 취소
cancel_message = cancel_orders(side='all')
message.append(cancel_message)

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
    if not isinstance(account, dict):
        TA.send_tele(f"KRQT: 총 원화평가금 조회 불가로 종료합니다. ({account})")
        sys.exit(1)

    orderable_cash_init = KIS.get_KR_orderable_cash()    # 수수료·세금 반영 실투자가능금액
    if not isinstance(orderable_cash_init, (int, float)):
        TA.send_tele(f"KRQT: 주문가능현금 조회 불가로 종료합니다. ({orderable_cash_init})")
        sys.exit(1)

    total_krw_asset = account['stock_eval_amt'] + float(orderable_cash_init)  # 총자산 재산출
    cash_weight = target["CASH"]["weight"] if "CASH" in target else 0.0
    stock_weight = 1.0 - cash_weight
    total_invest = total_krw_asset * stock_weight           # 주문가능현금 기준 투자금 산출

    # 종목별 목표 투자금액 및 수량 산출 
    target_code = list(target.keys())
    
    total_weight = sum(v['weight'] for v in target.values())
    if abs(total_weight - 1.0) > 0.01:   # 1% 오차 허용
        TA.send_tele(f"KRQT 경고: CSV weight 합계 = {total_weight:.3f} (1.0 아님). 계속 진행합니다.")
        message.append(f"weight 합계 경고: {total_weight:.3f}")
    
    for i in target_code:
        if i == "CASH":                        # CASH는 주식 아님 → 스킵
            target[i]['target_invest'] = int(target[i]['weight'] * total_krw_asset)
            target[i]['target_qty'] = 0
            continue
        price = KIS.get_KR_current_price(i)
        if price == 0 or not isinstance(price, int):
            TA.send_tele(f"KRQT: 현재가 조회 불가로 종료합니다. ({price})")
            sys.exit(1)
        target[i]['target_invest'] = int(target[i]['weight'] * total_invest)
        target[i]['target_qty'] = int(target[i]['target_invest'] / price)
        time_module.sleep(0.1)

    # 당일 target 저장하기
    json_message = save_json(target, KRQT_target_path, order)
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
        if code == "CASH":                 # CASH는 매매 대상 아님
            continue
        if target[code]["target_qty"] > hold[code]["hold_qty"]:
            buy[code] = target[code]["target_qty"] - hold[code]["hold_qty"]
        elif target[code]["target_qty"] < hold[code]["hold_qty"]:
            sell[code] = hold[code]["hold_qty"] - target[code]["target_qty"]
    else:
        sell[code] = hold[code]["hold_qty"]

for code in target_code:
    if code == "CASH":                     # CASH는 매매 대상 아님
        continue
    if code not in hold_code:
        buy[code] = target[code]["target_qty"]

# 분할 주문 수량 구하기
round_split = split_data(order['round'])
sell_split = [round_split["sell_splits"], round_split["sell_price"]]
buy_split = [round_split["buy_splits"], round_split["buy_price"]]   
    
# 매도주문
sell_code = list(sell.keys())

if len(sell_code) == 0:
    message.append("KRQT:매도 종목 없음")

elif sell_split[0] > 0:
    message.append(f"KRQT: {order['round']}회차 - 매도 주문")
    for code, qty in sell.items():
        local_split_count = sell_split[0]    # 루프마다 원본에서 복사
        local_split_price = sell_split[1][:]
        split_qty = int(qty // local_split_count)
        if split_qty < 1:
            local_split_count = 1
            local_split_price = [0.99]
            split_qty = int(qty)

        price = KIS.get_KR_current_price(code)
        if price == 0 or not isinstance(price, int):
            TA.send_tele(f"KRQT: 현재가 조회 불가로 종료합니다. ({price})")
            sys.exit(1)

        for i in range(local_split_count):
            split_price = float(price * local_split_price[i])
            order_price= KIS.round_to_tick(price=split_price, market="KR") 
            order_info = KIS.order_sell_KR(code, split_qty, order_price, "00")
            if order_info is None:
                message.append(f"KRQT 매도 오류: {code} API 응답 없음")
            elif order_info.get("success"):
                message.append(f"매도 {code} {split_qty}주 {order_price:,}원 주문번호:{order_info.get('order_number','')}")
            else:
                message.append(f"매도 실패 {code}: {order_info.get('error_message','')}")
            time_module.sleep(0.125)
else:
    # 14회차: 잔량 있어도 매도 스킵 — 알림만
    message.append(f"KRQT: {order['round']}회차 매도 스킵 - 미처분 잔량: {list(sell.keys())}")    

# 회차별 매도 메세지 telegram 출력
TA.send_tele(message)
message = []

# 매도 매수 시간딜레이
time_module.sleep(600)

# 매수구간 전환
# 주문가능 금액 조회 및 주문수량 구하기
KRW = KIS.get_KR_orderable_cash()
if not isinstance(KRW, (int, float)):
    TA.send_tele(f"KRQT: 주문가능현금 조회 불가로 종료합니다. ({KRW})")
    sys.exit(1)

# 주문가능금액에 맞춰 매수잔고 재조정
orderable_KRW = float(KRW)
orderable_KRW = float(KRW)
target_KRW = 0
buy_prices = {}                              # 현재가 저장 (매수 루프에서 재사용)
buy_price_rate = buy_split[1][-1] if buy_split[1] else 1.0  # 최대 배율 기준

for code, qty in buy.items():
    price = KIS.get_KR_current_price(code)
    if not isinstance(price, int) or price == 0:
        TA.send_tele(f"KRQT: 현재가 조회 불가로 종료합니다. ({price})")
        sys.exit(1)
    buy_prices[code] = price                                 # 저장
    ticker_invest = price * buy_price_rate * qty             # 최대 배율 반영
    target_KRW += ticker_invest
    time_module.sleep(0.125)

if target_KRW > orderable_KRW:
    adjust_rate = orderable_KRW / target_KRW
    for ticker, ticker_qty in buy.items():
        adjusted = int(ticker_qty * adjust_rate)
        buy[ticker] = adjusted

    buy = {ticker: qty for ticker, qty in buy.items() if qty > 0}   # 0주 제거
    buy_code = list(buy.keys())
else:
    pass # 예수금이 충분할 경우 조정 없음

# 매수주문
buy_code = list(buy.keys())

if len(buy_code) == 0:
    message.append("KRQT:매수 종목 없음")

elif len(buy_code) > 0 and buy_split[0] > 0:
    message.append(f"KRQT: {order['round']}회차 - 매수 주문")
    for code, qty in buy.items():
        local_split_count = buy_split[0]
        local_split_price = buy_split[1][:]
        split_qty = int(qty // local_split_count)
        if split_qty < 1:
            local_split_count = 1
            local_split_price = [1.01]
            split_qty = int(qty)

        price = buy_prices.get(code)         # 재조회 없이 저장값 사용
        if not isinstance(price, int) or price == 0:
            TA.send_tele(f"KRQT: 현재가 조회 불가로 종료합니다. ({price})")
            sys.exit(1)

        for i in range(local_split_count):
            split_price = float(price * local_split_price[i])
            order_price = KIS.round_to_tick(price=split_price, market="KR")
            order_info = KIS.order_buy_KR(code, split_qty, order_price, "00")
            if order_info is None:
                message.append(f"KRQT 매수 오류: {code} API 응답 없음")
            elif order_info.get("success"):
                message.append(f"매수 {code} {split_qty}주 {order_price:,}원 주문번호:{order_info.get('order_number','')}")
            else:
                message.append(f"매수 실패 {code}: {order_info.get('error_message','')}")
            time_module.sleep(0.125)

# 7회차에는 day = 2로 전환
if order['round'] == 7:
    TR = {
        "day": 2
    }
    json_message = save_json(TR, KRQT_day_path, order)
    message.extend(json_message)

# 14회차에는 day = 1로 전환
if order['round'] == 14:
    TR = {
        "day": 1
    }
    json_message = save_json(TR, KRQT_day_path, order)
    message.extend(json_message)

# 회차별 매수 메세지 telegram 출력
TA.send_tele(message)
message = []

# 최종 매매 데이터 telegram 출력 및 Google sheet 전략별 잔고 - 종목별 매입량 매입가 기록
if order['round'] == 14:
    time_module.sleep(300)
    # 전회 주문 취소
    cancel_message = cancel_orders(side='all')
    message.append(cancel_message)
    message.append(f"KRQT {order['date']} 리밸런싱 종료")

    # 시작목표 불러오기
    try:
        with open(KRQT_stock_path, 'r', encoding='utf-8') as f:
            plan = pd.read_csv(f, dtype={
                "code": str,
                "name": str,
                "weight": float,
                "category": str
            })
    except Exception as e:
        TA.send_tele(f"KRQT_stock.csv 파일 오류: {e}")
        sys.exit(1)

    plan["code"] = plan["code"].str[1:]

    plan_raw = defaultdict(list)
    for _, row in plan.iterrows():
        if str(row["code"]) == "CASH":        # CASH는 결과 리포트 대상 아님
            continue
        if pd.isna(row["category"]):          # category 빈값 행 스킵
            continue
        plan_raw[str(row["category"])].append({
            "code": str(row["code"]),
            "name": str(row["name"]),
            "weight": float(row["weight"]),
        })

    plan = dict(plan_raw)

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

    result = {}
    for category in plan.keys():
        result[category] = []       # 카테고리별 리스트로 초기화
        for stock in plan[category]:
            stock_code = stock['code']
            if stock_code not in hold_code:
                result[category].append({
                    "code":    stock_code,
                    "name":    stock['name'],
                    "qty":     0,
                    "balance": 0,
                    "weight":  stock['weight'],
                    "status":  "리밸런싱 매수실패"
                })
            else:
                total_w = target[stock_code]['weight']
                if total_w == 0:
                    split_weight = 1.0   # 단일 전략 종목으로 처리
                    message.append(f"경고: {stock_code} weight=0, split_weight=1.0으로 처리")
                else:
                    split_weight = stock['weight'] / total_w
                    
                result[category].append({
                    "code":    stock_code,
                    "name":    stock['name'],
                    "qty":     hold[stock_code]['hold_qty'] * split_weight,  # stock_code 사용
                    "balance": hold[stock_code]['hold_balance'] * split_weight,  # stock_code 사용
                    "weight":  stock['weight'],
                    "status":  "리밸런싱"
                })

    remain_items = []
    for code in hold_code:
        if code not in target_code:
            remain_items.append({
                "code":    code,
                "name":    hold[code]['name'],
                "qty":     hold[code]['hold_qty'],
                "balance": hold[code]['hold_balance'],
                "weight":  0,
                "status":  "리밸런싱 매도실패"
            })
    if remain_items:                      # 항목이 있을 때만 result에 추가
        result["remain_last"] = remain_items

    for category, stocks_list in result.items():
        message.append(f"{order['date']}일 리밸런싱 전략명:{category} 결과")
        for item in stocks_list:
            qty     = int(item['qty'])
            balance = f"{int(item['balance']):,}"
            message.append(f"종목명: {item['name']}, 잔고: {qty}주, 평가금: {balance}원, 상태: {item['status']}")

    # 전략결과 저장
    json_message = save_json(result, KRQT_result_path, order)
    message.extend(json_message)

    # 최종 daily balance
    # 전체 자산
    all_balance = KIS.get_KR_account_summary()
    if not isinstance(all_balance, dict):
        TA.send_tele(f"KRQT: 전체 자산 조회 불가로 종료합니다. ({all_balance})")
        sys.exit(1)

    orderable_cash = KIS.get_KR_orderable_cash()    # 주문가능현금 추가 조회
    if not isinstance(orderable_cash, (int, float)):
        TA.send_tele(f"KRQT: 주문가능현금 조회 불가로 종료합니다. ({orderable_cash})")
        sys.exit(1)

    daily_data = {
        "date": str(order['date']),
        "total_stocks":     all_balance['stock_eval_amt'],
        "total_stocks_ret": 0.0,
        "total_cash":       float(orderable_cash),                          # ← 주문가능현금
        "total_asset":      all_balance['stock_eval_amt'] + float(orderable_cash),  # ← 재산출
        "total_asset_ret":  0.0
    }

    # category별 자산
    for category, stocks_list in result.items():
        category_balance = sum(item['balance'] for item in stocks_list)
        daily_data[category]            = category_balance
        daily_data[f"{category}_ret"]   = 0.0

    # daily balance google sheet 저장
    try:
        credentials_file = "/var/autobot/gspread/service_account.json"
        spreadsheet_name = "2026_KRQT_daily"

        # Google 스프레드시트 연결
        spreadsheet = GU.connect_google_sheets(credentials_file, spreadsheet_name)

        # 현재 월 계산
        current_date = datetime.now()
        current_month = current_date.month

        # 데이터 저장
        GU.save_to_sheets(spreadsheet, daily_data, current_month)
    except Exception as e:
        error_msg = f"Google Sheet 업로드 실패: {e}"
        TA.send_tele(error_msg)
        # Google Sheet 업로드 실패는 전체 프로세스를 중단하지 않음

    TA.send_tele(message)

message = []

sys.exit(0)