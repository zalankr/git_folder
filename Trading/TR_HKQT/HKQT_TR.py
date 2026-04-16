import sys
import json
import telegram_alert as TA
from datetime import datetime, timedelta as time_obj
import pandas as pd
from collections import defaultdict
import gspread_updater as GU
import time as time_module
from tendo import singleton
import KIS_HK

try:
    me = singleton.SingleInstance()
except singleton.SingleInstanceException:
    TA.send_tele("HKQT: 이미 실행 중입니다.")
    sys.exit(0)

# ============================================
# KIS instance 생성
# ============================================
key_file_path = "/var/autobot/KIS/kis63604155nkr.txt"       # 트레이딩 계좌(수수료할인)
token_file_path = "/var/autobot/KIS/kis63604155_token.json" # 트레이딩 계좌(수수료할인)
cano = "63604155"      # ← 계좌번호 수동 입력
acnt_prdt_cd = "01"
KIS = KIS_HK.KIS_API(key_file_path, token_file_path, cano, acnt_prdt_cd)

fee_rate = KIS.SELL_FEE_RATE  # 0.09% 이벤트 계좌
HKQT_day_path = "/var/autobot/TR_HKQT/HKQT_day.json"
HKQT_target_path = "/var/autobot/TR_HKQT/HKQT_target.json"
HKQT_result_path = "/var/autobot/TR_HKQT/HKQT_result.json"
HKQT_daily_path = "/var/autobot/TR_HKQT/HKQT_daily.json"
HKQT_stock_path = "/var/autobot/TR_HKQT/HKQT_stock.csv"

# ============================================
# CSV 형식
# ============================================
# code,name,weight,category
# CASH,CASH,0.00,CASH
# A01179,H World Group,0.075,trend
# A00857,Petrochina H,0.075,trend
# ...
# ※ 홍콩 주식은 5자리 숫자 코드 (CSV에서 "A" 접두어 사용 → 파싱 시 제거)
# ※ CASH 행은 현금 비중 (0이면 전액 투자)

# ============================================
# 유틸리티 함수
# ============================================

def order_time(day=1):
    """
    거래일자와 거래회차 확인 (EC2 = UTC 시간대 기준)
    
    홍콩 정규장 (KST): 오전 10:30~13:00, 오후 14:00~17:00
    UTC 변환: 오전 01:30~04:00, 오후 05:00~08:00
    
    7회차 x 2일 = 총 14회차
    
    crontab (UTC):
      오전장 3회: 34 1,2,3 리밸런싱일,리밸런싱일+1 반기월 *
        → KST 10:37, 11:37, 12:37
      오후장 4회: 4 5,6,7 리밸런싱일,리밸런싱일+1 반기월 *
                  34 5 리밸런싱일,리밸런싱일+1 반기월 *
        → KST 14:07, 14:37, 15:07, 16:07
      (총 7회차 per day × 2일 = 14회차)
    
    실제 crontab 예시 (UTC):
      34 1,2,3 리밸런싱일,리밸런싱일+1 반기월 *   → 오전 3슬롯
      4 5,6,7 리밸런싱일,리밸런싱일+1 반기월 *     → 오후 3슬롯
      34 5 리밸런싱일,리밸런싱일+1 반기월 *         → 오후 1슬롯
      (총 7회차 per day)
    """
    from datetime import datetime as dt, timezone
    now = dt.now(timezone.utc)
    current_date = now.date()
    current_time = now.time()

    result = {
        'date': current_date,
        'time': current_time,
        'day': day,
        'round': 0,
        'total_round': 14  # 7회차 x 2일
    }

    hour = current_time.hour
    minute = current_time.minute

    base_round = 0
    # 홍콩 정규장 UTC 시간 → round 매핑
    # 오전장 (KST 10:30~13:00 = UTC 01:30~04:00)
    #   UTC 01:37 → round 1  (KST 10:37)
    #   UTC 02:37 → round 2  (KST 11:37)
    #   UTC 03:37 → round 3  (KST 12:37)
    # 오후장 (KST 14:00~17:00 = UTC 05:00~08:00)
    #   UTC 05:07 → round 4  (KST 14:07)
    #   UTC 05:37 → round 5  (KST 14:37)
    #   UTC 06:07 → round 6  (KST 15:07)
    #   UTC 07:07 → round 7  (KST 16:07)
    
    # 오전장: 37분 실행 (crontab: 37 1,2,3)
    if 30 <= minute <= 45:
        am_map = {1: 1, 2: 2, 3: 3}
        base_round = am_map.get(hour, 0)
        # 오후장 37분 슬롯: 37 5 → KST 14:37
        if hour == 5:
            base_round = 5

    # 오후장: 7분 실행 (crontab: 7 5,6,7)
    elif 0 <= minute <= 15:
        pm_map = {5: 4, 6: 6, 7: 7}
        base_round = pm_map.get(hour, 0)

    if base_round > 0:
        result['round'] = base_round + (day * 7 - 7)

    return result

def health_check():
    """시스템 상태 확인"""
    checks = []
    
    if not KIS.access_token:
        checks.append("HKQT체크: API 토큰 없음")
    
    import os
    files = [HKQT_day_path, HKQT_stock_path]
    for f in files:
        if not os.path.exists(f):
            checks.append(f"HKQT체크: data파일 없음: {f}")
    
    try:
        import socket
        socket.create_connection(("openapi.koreainvestment.com", 9443), timeout=5)
    except:
        checks.append("HKQT체크: KIS API 서버 접속 불가")
    
    if checks:
        TA.send_tele("\n".join(checks))
        sys.exit(1)

def save_json(data, path, order):
    """저장 실패 시에도 백업 파일 생성"""
    result_msgs = []
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        result_msgs.append(f"{order['date']} {order['round']}/{order['total_round']}회차 저장 완료: {path}")
    except Exception as e:
        result_msgs.append(f"{path} 저장 실패: {e}")
        backup_path = f"/var/autobot/TR_HKQT/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            result_msgs.append(f"백업 파일 생성: {backup_path}")
        except Exception as backup_error:
            result_msgs.append(f"백업 실패: {backup_error}")
    return result_msgs

def split_data(round_num):
    """
    회차별 분할횟수와 분할당 가격 배율 산출
    홍콩주식은 HKD 소수점 2자리 → 배율 적용 후 round(price, 2)
    """
    if round_num == 1:
        sell_splits = 5
        sell_price = [1.0100, 1.0075, 1.0050, 1.0025, 0.9950]
        buy_splits = 5
        buy_price = [0.9875, 0.9900, 0.9925, 0.9950, 0.9975]
    elif round_num == 2:
        sell_splits = 4
        sell_price = [1.0100, 1.0075, 1.0050, 1.0025]
        buy_splits = 5
        buy_price = [0.9900, 0.9925, 0.9950, 0.9975, 1.0000]
    elif round_num == 3:
        sell_splits = 4
        sell_price = [1.0100, 1.0075, 1.0050, 1.0025]
        buy_splits = 4
        buy_price = [0.9900, 0.9925, 0.9950, 0.9975]
    elif round_num == 4:
        sell_splits = 4
        sell_price = [1.0075, 1.0050, 1.0025, 1.0000]
        buy_splits = 4
        buy_price = [0.9900, 0.9925, 0.9950, 0.9975]
    elif round_num == 5:
        sell_splits = 3
        sell_price = [1.0075, 1.0050, 1.0025]
        buy_splits = 4
        buy_price = [0.9925, 0.9950, 0.9975, 1.0000]
    elif round_num == 6:
        sell_splits = 3
        sell_price = [1.0075, 1.0050, 1.0025]
        buy_splits = 3
        buy_price = [0.9925, 0.9950, 0.9975]
    elif round_num == 7: 
        sell_splits = 3
        sell_price = [1.0050, 1.0025, 1.0000]
        buy_splits = 3
        buy_price = [0.9925, 0.9950, 0.9975]
    elif round_num == 8: 
        sell_splits = 2
        sell_price = [1.0050, 1.0025]
        buy_splits = 3
        buy_price = [0.9950, 0.9975, 1.0000]
    elif round_num == 9: 
        sell_splits = 2
        sell_price = [1.0050, 1.0025]
        buy_splits = 2
        buy_price = [0.9950, 0.9975]
    elif round_num == 10:
        sell_splits = 2
        sell_price = [1.0025, 1.0000]
        buy_splits = 2
        buy_price = [0.9950, 0.9975]
    elif round_num == 11:
        sell_splits = 1
        sell_price = [1.0025]
        buy_splits = 2
        buy_price = [0.9975, 1.0000]
    elif round_num == 12:
        sell_splits = 1
        sell_price = [1.0025]
        buy_splits = 1
        buy_price = [0.9975]
    elif round_num == 13:
        sell_splits = 1
        sell_price = [0.9800]
        buy_splits = 1
        buy_price = [0.9975]
    elif round_num == 14:
        sell_splits = 0
        sell_price = []
        buy_splits = 1
        buy_price = [1.0200]
    else:
        TA.send_tele(f"HKQT: 유효하지 않은 round 값: {round_num}")
        sys.exit(1)

    round_split = {
        "sell_splits": sell_splits,
        "sell_price": sell_price,
        "buy_splits": buy_splits,
        "buy_price": buy_price
    }
    return round_split

def cancel_orders():
    """모든 미체결 주문 취소. (메시지, summary dict) 튜플 반환."""
    try:
        summary, cancel_msgs = KIS.cancel_all_unfilled_orders()
        cancel_message = f"HKQT: {summary['success']}/{summary['total']} 주문 취소 성공"
        return cancel_message, summary
    except Exception as e:
        cancel_message = f"HKQT: 주문 취소 에러발생 ({e})"
        return cancel_message, {"success": 0, "total": 0, "fail": 0}

def is_HK_trading_day():
    """
    홍콩 거래일 확인 (exchange_calendars 활용)
    EC2 = UTC이므로 UTC→HKT 변환하여 HKT 기준 날짜로 체크
    (UTC 01시 실행 = HKT 09시이므로 날짜 차이 없음)
    """
    try:
        import exchange_calendars as xcals
        import pytz
        cal = xcals.get_calendar("XHKG")  # 홍콩증권거래소
        hkt = pytz.timezone('Asia/Hong_Kong')
        from datetime import timezone
        today_hkt = datetime.now(timezone.utc).astimezone(hkt).date()
        return cal.is_session(pd.Timestamp(today_hkt))
    except ImportError:
        try:
            import pytz
            hkt = pytz.timezone('Asia/Hong_Kong')
            from datetime import timezone
            weekday = datetime.now(timezone.utc).astimezone(hkt).weekday()
        except ImportError:
            weekday = datetime.utcnow().weekday()
        return weekday < 5  # 월~금
    except Exception:
        return True  # 확인 불가 시 진행

# ============================================
# 메인 로직 # 반기 리밸런싱 (홍콩주식)
# ============================================

checkday = is_HK_trading_day()
if not checkday:
    TA.send_tele("HKQT: 홍콩 거래일이 아닙니다.")
    sys.exit(0)

health_check()
message = []

# HKQT_day.json 불러오기
try:
    with open(HKQT_day_path, 'r', encoding='utf-8') as f:
        TR = json.load(f)
except Exception as e:
    TA.send_tele(f"HKQT_day.json 파일 오류: {e}")
    sys.exit(1)

# 일자와 회차 시간데이터 불러오기
order = order_time(day=TR['day'])

if order['round'] == 0:
    TA.send_tele("HKQT: 매매시간이 아닙니다.")
    sys.exit(0)
message.append(f"HKQT: {order['day']}일차 {order['round']}/{order['total_round']}회차 매매를 시작합니다.")

# ============================================
# 전회 주문 취소 + 미체결 잔존 확인 루프
# ============================================
cancel_message, _ = cancel_orders()
message.append(cancel_message)
time_module.sleep(3)

MAX_CANCEL_RETRY = 3
for retry_i in range(MAX_CANCEL_RETRY):
    try:
        remaining = KIS.get_unfilled_orders()
    except Exception as e:
        message.append(f"HKQT 미체결 조회 에러: {e}")
        remaining = []

    if isinstance(remaining, list) and len(remaining) == 0:
        if retry_i > 0:
            message.append(f"HKQT 미체결 0건 확인 (재시도 {retry_i}회 후)")
        break

    n_remain = len(remaining) if isinstance(remaining, list) else '?'
    message.append(f"HKQT 미체결 잔존 {n_remain}건 → 추가 취소 {retry_i+1}/{MAX_CANCEL_RETRY}")
    retry_msg, retry_summary = cancel_orders()
    message.append(retry_msg)
    time_module.sleep(3)

    if retry_i == MAX_CANCEL_RETRY - 1 and retry_summary.get('success', 0) == 0:
        message.append("HKQT 경고: 취소 실패 상태로 매매 진행 → 매도가능수량 clamp로 방어")

# ============================================
# 회차별 target 데이터 불러오기 (1, 8회차: 불러오기와 계산)
# ============================================
if order['round'] == 1 or order['round'] == 8:
    # 목표종목 csv파일 불러오기
    try:
        with open(HKQT_stock_path, 'r', encoding='utf-8') as f:
            Target = pd.read_csv(f, dtype={
                "code": str,
                "name": str,
                "weight": float,
                "category": str
            })
    except Exception as e:
        TA.send_tele(f"HKQT_stock.csv 파일 오류: {e}")
        sys.exit(1)

    # ★ 홍콩주식: CSV에서 "A" 접두어 제거 (5자리 숫자 코드 보전)
    # CASH 행은 제외하고 처리
    Target["code"] = Target["code"].apply(
        lambda x: x[1:] if isinstance(x, str) and x.upper().startswith("A") and x.upper() != "ACASH" else x
    )
    # CASH 행의 code가 "ASH"로 변환되는 것 방지 (원본이 "CASH")
    # → CASH는 "A"로 시작하지 않으므로 위 로직에서 안전

    # 중복 종목 비중 합산 (여러 카테고리에 동일 종목이 있을 수 있음)
    grouped = Target.groupby("code").agg(
        name=("name", "first"),
        weight=("weight", "sum"),
        categories=("category", list)
    ).reset_index()

    target = {
        str(row["code"]): {
            "name":       str(row["name"]),
            "weight":     float(row["weight"]),
            "categories": [str(c) for c in row["categories"]],
        }
        for _, row in grouped.iterrows()
    }

    # ============================================
    # 총 HKD 평가금액 산출
    # ============================================
    # 홍콩주식 총자산 = 주식평가금(HKD) + 주문가능현금(HKD)
    stocks_list = KIS.get_HK_stock_balance()
    if not isinstance(stocks_list, list):
        TA.send_tele(f"HKQT: 잔고 조회 불가로 종료합니다. ({stocks_list})")
        sys.exit(1)

    stock_eval_hkd = sum(s['eval_amt'] for s in stocks_list)
    time_module.sleep(0.2)

    # ✅ get_HK_order_available(): TTTS3007R(SEHK) → MTS 주문가능금액과 동일 (HKD)
    orderable_hkd = KIS.get_HK_order_available()
    if orderable_hkd is None:
        TA.send_tele("HKQT: HKD 주문가능금액 조회 불가로 종료합니다.")
        sys.exit(1)

    total_hkd_asset = stock_eval_hkd + orderable_hkd
    message.append(
        f"HKQT 총자산: HK${total_hkd_asset:,.2f} "
        f"(주식:HK${stock_eval_hkd:,.2f} + 현금:HK${orderable_hkd:,.2f})"
    )

    # ============================================
    # 종목별 목표 투자금액 및 수량 산출
    # ============================================
    target_code = list(target.keys())

    total_weight = sum(v['weight'] for v in target.values())
    if abs(total_weight - 1.0) > 0.01:
        TA.send_tele(f"HKQT 경고: CSV weight 합계 = {total_weight:.3f} (1.0 아님). 계속 진행합니다.")
        message.append(f"weight 합계 경고: {total_weight:.3f}")

    for ticker in target_code:
        if ticker == "CASH":
            target[ticker]['target_invest'] = float(target[ticker]['weight'] * total_hkd_asset)
            target[ticker]['target_qty'] = 0
            continue

        price = KIS.get_HK_current_price(ticker)
        if not isinstance(price, float) or price <= 0:
            TA.send_tele(f"HKQT: {ticker} 현재가 조회 불가로 종료합니다. ({price})")
            sys.exit(1)

        target[ticker]['current_price'] = price
        target[ticker]['target_invest'] = float(target[ticker]['weight'] * total_hkd_asset)
        # ★ 홍콩주식: 1주 단위 매매 (KIS API 기준)
        new_target_qty = int(target[ticker]['target_invest'] / price)

        # ✅ 8회차(2일차): target_qty가 현재 보유보다 줄어들면 보유수량으로 고정
        #    → 1일차 매수분이 T+2 미결제 상태라 매도 불가하므로
        if order['round'] == 8:
            current_hold = 0
            for s in stocks_list:
                if s['ticker'] == ticker:
                    current_hold = s['quantity']
                    break
            if new_target_qty < current_hold:
                new_target_qty = current_hold

        target[ticker]['target_qty'] = new_target_qty
        time_module.sleep(0.15)

    # 당일 target 저장하기
    target_serializable = {}
    for k, v in target.items():
        target_serializable[k] = {
            key: (float(val) if isinstance(val, float) else
                  int(val) if isinstance(val, (int,)) and not isinstance(val, bool) else
                  val)
            for key, val in v.items()
        }
    json_message = save_json(target_serializable, HKQT_target_path, order)
    message.extend(json_message)
    target_code = list(target.keys())

else:
    # 1회, 8회차가 아닌 경우 불러오기만 시행
    try:
        with open(HKQT_target_path, 'r', encoding='utf-8') as f:
            target = json.load(f)
    except Exception as e:
        TA.send_tele(f"HKQT_target.json 파일 오류: {e}")
        sys.exit(1)
    target_code = list(target.keys())

# ============================================
# 보유 종목 잔고 불러오기
# ============================================
stocks = KIS.get_HK_stock_balance()
if not isinstance(stocks, list):
    TA.send_tele(f"HKQT: 잔고 조회 불가로 종료합니다. ({stocks})")
    sys.exit(1)

hold = {}
for stock in stocks:
    ticker = stock["ticker"]
    hold[ticker] = {
        "name": stock["name"],
        "hold_balance": stock["eval_amt"],
        "hold_qty": stock["quantity"],
        "ord_psbl_qty": stock.get("ord_psbl_qty", 0),   # ✅ 매도가능수량
        "current_price": stock["current_price"],
        "exchange": stock["exchange"],
    }

hold_code = list(hold.keys())

# ============================================
# 투자수량과 잔고수량 비교해서 매수/매도 수량 산출
# ============================================
buy = {}
sell = {}
for ticker in hold_code:
    if ticker in target_code:
        if ticker == "CASH":
            continue
        if target[ticker]["target_qty"] > hold[ticker]["hold_qty"]:
            buy[ticker] = target[ticker]["target_qty"] - hold[ticker]["hold_qty"]
        elif target[ticker]["target_qty"] < hold[ticker]["hold_qty"]:
            need_sell = hold[ticker]["hold_qty"] - target[ticker]["target_qty"]
            # ✅ 매도가능수량으로 상한 제한
            sell_qty = min(need_sell, hold[ticker]["ord_psbl_qty"])
            if sell_qty > 0:
                sell[ticker] = sell_qty
            else:
                message.append(f"HKQT 매도스킵: {ticker} 필요{need_sell}주, 가능{hold[ticker]['ord_psbl_qty']}주")
    else:
        sell_qty = min(hold[ticker]["hold_qty"], hold[ticker]["ord_psbl_qty"])
        if sell_qty > 0:
            sell[ticker] = sell_qty
        else:
            message.append(f"HKQT 매도스킵: {ticker} 가능수량 0주")

for ticker in target_code:
    if ticker == "CASH":
        continue
    if ticker not in hold_code:
        buy[ticker] = target[ticker]["target_qty"]

# ★ 홍콩주식: 1주 단위 매매이므로 0주 초과 필터링만 적용
buy = {t: q for t, q in buy.items() if q > 0}
sell = {t: q for t, q in sell.items() if q > 0}

# ============================================
# 분할 주문 수량 구하기
# ============================================
round_split = split_data(order['round'])
sell_split = [round_split["sell_splits"], round_split["sell_price"]]
buy_split = [round_split["buy_splits"], round_split["buy_price"]]

# ============================================
# 매도 주문
# ============================================
sell_code = list(sell.keys())

if len(sell_code) == 0:
    message.append("HKQT: 매도 종목 없음")

elif sell_split[0] > 0:
    message.append(f"HKQT: {order['round']}회차 - 매도 주문")
    for ticker, qty in sell.items():
        local_split_count = sell_split[0]
        local_split_price = sell_split[1][:]
        split_qty = int(qty // local_split_count)
        remainder = int(qty - split_qty * local_split_count)

        if split_qty < 1:
            local_split_count = 1
            local_split_price = [0.99]
            split_qty = int(qty)
            remainder = 0

        price = KIS.get_HK_current_price(ticker)
        if not isinstance(price, float) or price <= 0:
            TA.send_tele(f"HKQT: {ticker} 현재가 조회 불가로 종료합니다. ({price})")
            sys.exit(1)

        for i in range(local_split_count):
            this_qty = split_qty + (remainder if i == local_split_count - 1 else 0)
            if this_qty < 1:
                continue

            order_price = round(price * local_split_price[i], 2)

            order_info, order_msgs = KIS.order_sell_HK(ticker, this_qty, order_price)
            if order_info is None:
                time_module.sleep(2)
                order_info, order_msgs = KIS.order_sell_HK(ticker, this_qty, order_price)
            if order_info is None:
                message.append(f"HKQT 매도 오류: {ticker} {this_qty}주 HK${order_price:,.2f} API 응답 없음")
            elif order_info.get("success"):
                message.append(
                    f"매도 {ticker} {this_qty}주 HK${order_price:,.2f} "
                    f"주문번호:{order_info.get('order_number','')}"
                )
            else:
                message.append(
                    f"매도 실패 {ticker} {this_qty}주: {order_info.get('error_message','')}"
                )
            message.extend(order_msgs)
            time_module.sleep(0.2)
else:
    message.append(f"HKQT: {order['round']}회차 매도 스킵 - 미처분 잔량: {list(sell.keys())}")

# 회차별 매도 메세지 telegram 출력
TA.send_tele(message)
message = []

# ============================================
# 매도-매수 시간 딜레이
# 홍콩주식: T+2 결제이나 매도재사용가능
# ============================================
time_module.sleep(600)

# ============================================
# 매수 구간 전환
# ============================================
HKD = KIS.get_HK_order_available()
if HKD is None:
    TA.send_tele("HKQT: HKD 주문가능금액 조회 불가로 종료합니다.")
    sys.exit(1)

orderable_HKD = float(HKD)
target_HKD = 0.0
buy_prices = {}
buy_price_rate = buy_split[1][-1] if buy_split[1] else 1.0

for ticker, qty in buy.items():
    price = KIS.get_HK_current_price(ticker)
    if not isinstance(price, float) or price <= 0:
        TA.send_tele(f"HKQT: {ticker} 현재가 조회 불가로 종료합니다. ({price})")
        sys.exit(1)
    buy_prices[ticker] = price
    ticker_invest = price * buy_price_rate * qty
    target_HKD += ticker_invest
    time_module.sleep(0.15)

message.append(
    f"HKQT 매수가능: HK${orderable_HKD:,.2f} | 목표매수금: HK${target_HKD:,.2f}"
    + (f" | 조정비율: {orderable_HKD/target_HKD:.4f}" if target_HKD > 0 else "")
)

if target_HKD > orderable_HKD:
    adjust_rate = orderable_HKD / target_HKD
    for ticker, ticker_qty in buy.items():
        adjusted = int(ticker_qty * adjust_rate)
        buy[ticker] = adjusted

    buy = {ticker: qty for ticker, qty in buy.items() if qty > 0}
    message.append(f"HKQT 매수수량 조정 완료 (adjust_rate={adjust_rate:.4f})")
else:
    message.append("HKQT 매수가능금 충분 → 수량 조정 없음")

# ============================================
# 매수 주문
# ============================================
buy = {ticker: qty for ticker, qty in buy.items() if qty > 0}  # 방어적 0주 제거
buy_code = list(buy.keys())

if len(buy_code) == 0:
    message.append("HKQT: 매수 종목 없음")

elif len(buy_code) > 0 and buy_split[0] > 0:
    message.append(f"HKQT: {order['round']}회차 - 매수 주문")
    for ticker, qty in buy.items():
        local_split_count = buy_split[0]
        local_split_price = buy_split[1][:]
        split_qty = int(qty // local_split_count)
        remainder = int(qty - split_qty * local_split_count)

        if split_qty < 1:
            if qty < 1:
                message.append(f"HKQT 매수 스킵: {ticker} 수량 0주 (조정후 제거대상)")
                continue
            local_split_count = 1
            local_split_price = [1.01]
            split_qty = int(qty)
            remainder = 0

        price = buy_prices.get(ticker)
        if not isinstance(price, float) or price <= 0:
            TA.send_tele(f"HKQT: {ticker} 현재가 없음으로 종료합니다.")
            sys.exit(1)

        for i in range(local_split_count):
            this_qty = split_qty + (remainder if i == local_split_count - 1 else 0)
            if this_qty < 1:
                continue

            order_price = round(price * local_split_price[i], 2)

            order_info, order_msgs = KIS.order_buy_HK(ticker, this_qty, order_price)
            if order_info is None:
                time_module.sleep(2)
                order_info, order_msgs = KIS.order_buy_HK(ticker, this_qty, order_price)
            if order_info is None:
                message.append(f"HKQT 매수 오류: {ticker} {this_qty}주 HK${order_price:,.2f} API 응답 없음")
            elif order_info.get("success"):
                message.append(
                    f"매수 {ticker} {this_qty}주 HK${order_price:,.2f} "
                    f"주문번호:{order_info.get('order_number','')}"
                )
            else:
                message.append(
                    f"매수 실패 {ticker} {this_qty}주 HK${order_price:,.2f}: "
                    f"{order_info.get('error_message','')}"
                )
            message.extend(order_msgs)
            time_module.sleep(0.2)

# ============================================
# day 전환 (7회차→day2, 14회차→day1)
# ============================================
if order['round'] == 7:
    TR = {"day": 2}
    json_message = save_json(TR, HKQT_day_path, order)
    message.extend(json_message)

if order['round'] == 14:
    TR = {"day": 1}
    json_message = save_json(TR, HKQT_day_path, order)
    message.extend(json_message)

# 회차별 매수 메세지 telegram 출력
TA.send_tele(message)
message = []

# ============================================
# 최종 매매 데이터 telegram 출력 및 Google Sheet 기록 (14회차)
# ============================================
if order['round'] == 14:
    time_module.sleep(120)
    # 전회 주문 취소
    cancel_message, _ = cancel_orders()
    message.append(cancel_message)
    message.append(f"HKQT {order['date']} 리밸런싱 종료")

    # 시작목표 불러오기
    try:
        with open(HKQT_stock_path, 'r', encoding='utf-8') as f:
            plan = pd.read_csv(f, dtype={
                "code": str,
                "name": str,
                "weight": float,
                "category": str
            })
    except Exception as e:
        TA.send_tele(f"HKQT_stock.csv 파일 오류: {e}")
        sys.exit(1)

    # ★ A접두어 제거
    plan["code"] = plan["code"].apply(
        lambda x: x[1:] if isinstance(x, str) and x.upper().startswith("A") and x.upper() != "ACASH" else x
    )

    plan_raw = defaultdict(list)
    for _, row in plan.iterrows():
        if str(row["code"]) == "CASH":
            continue
        if pd.isna(row["category"]):
            continue
        plan_raw[str(row["category"])].append({
            "code": str(row["code"]),
            "name": str(row["name"]),
            "weight": float(row["weight"]),
        })
    plan = dict(plan_raw)

    # 보유 종목 잔고 불러오기
    stocks = KIS.get_HK_stock_balance()
    if not isinstance(stocks, list):
        TA.send_tele(f"HKQT: 잔고 조회 불가로 종료합니다. ({stocks})")
        sys.exit(1)

    hold = {}
    for stock in stocks:
        ticker = stock["ticker"]
        hold[ticker] = {
            "name": stock["name"],
            "hold_balance": stock["eval_amt"],
            "hold_qty": stock["quantity"],
        }
    hold_code = list(hold.keys())

    result = {}
    for category in plan.keys():
        result[category] = []
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
                    split_weight = 1.0
                    message.append(f"경고: {stock_code} weight=0, split_weight=1.0으로 처리")
                else:
                    split_weight = stock['weight'] / total_w

                result[category].append({
                    "code":    stock_code,
                    "name":    stock['name'],
                    "qty":     hold[stock_code]['hold_qty'] * split_weight,
                    "balance": hold[stock_code]['hold_balance'] * split_weight,
                    "weight":  stock['weight'],
                    "status":  "리밸런싱"
                })

    remain_items = []
    for ticker in hold_code:
        if ticker not in target_code:
            remain_items.append({
                "code":    ticker,
                "name":    hold[ticker]['name'],
                "qty":     hold[ticker]['hold_qty'],
                "balance": hold[ticker]['hold_balance'],
                "weight":  0,
                "status":  "리밸런싱 매도실패"
            })
    if remain_items:
        result["remain_last"] = remain_items

    for category, stocks_list in result.items():
        message.append(f"{order['date']}일 리밸런싱 전략명:{category} 결과")
        for item in stocks_list:
            qty     = int(item['qty'])
            balance = f"HK${float(item['balance']):,.2f}"
            message.append(
                f"종목명: {item['name']}, 잔고: {qty}주, 평가금: {balance}, 상태: {item['status']}"
            )

    # 전략결과 저장
    json_message = save_json(result, HKQT_result_path, order)
    message.extend(json_message)
    time_module.sleep(1.0)

    # ============================================
    # 최종 결과 저장
    # ============================================
    final_stocks = KIS.get_HK_stock_balance()
    if not isinstance(final_stocks, list):
        TA.send_tele(f"HKQT: 최종 잔고 조회 불가로 종료합니다. ({final_stocks})")
        sys.exit(1)
    final_stock_eval = sum(s['eval_amt'] for s in final_stocks)
    time_module.sleep(0.2)

    final_hkd = KIS.get_HK_order_available()
    if final_hkd is None:
        TA.send_tele("HKQT: 최종 HKD 주문가능금액 조회 불가로 종료합니다.")
        sys.exit(1)

    daily_data = {
        "date": str(order['date']),
        "total_stocks":    float(final_stock_eval),
        "total_cash":      float(final_hkd),
        "total_asset":     float(final_stock_eval) + float(final_hkd),
        "total_asset_ret": 0.0,
        "currency":        "HKD"
    }

    for category, stocks_list in result.items():
        category_balance = sum(float(item['balance']) for item in stocks_list)
        daily_data[category]          = float(category_balance)
        daily_data[f"{category}_ret"] = 0.0

    # HKQT_daily.json 저장
    try:
        json_message = save_json(daily_data, HKQT_daily_path, order)
        message.extend(json_message)
    except Exception as e:
        error_msg = f"HKQT_daily.json 저장 실패: {e}"
        TA.send_tele(error_msg)
    time_module.sleep(1.0)

    # data 정제 (표시용)
    daily = {
        "date": daily_data["date"],
        "total_stocks":    f"HK${daily_data['total_stocks']:,.2f}",
        "total_cash":      f"HK${daily_data['total_cash']:,.2f}",
        "total_asset":     f"HK${daily_data['total_asset']:,.2f}",
        "total_asset_ret": f"{float(daily_data['total_asset_ret']*100):.2f}%"
    }

    for category, stocks_list in result.items():
        category_balance = sum(float(item['balance']) for item in stocks_list)
        daily[category]          = f"HK${category_balance:,.2f}"
        daily[f"{category}_ret"] = "0.00%"

    """
    # daily balance Google Sheet 저장 보류
    try:
        credentials_file = "/var/autobot/gspread/service_account.json"
        spreadsheet_name = "2026_HKQT_daily"

        spreadsheet = GU.connect_google_sheets(credentials_file, spreadsheet_name)
        current_month = datetime.now().month

        GU.save_to_sheets(spreadsheet, daily, current_month)
        message.append(f"2026_HKQT_daily Google Sheet 업로드 완료")

    except Exception as e:
        error_msg = f"Google Sheet 업로드 실패: {e}"
        TA.send_tele(error_msg)
    """

    # telegram message
    for k, v in daily.items():
        message.append(f"{k} : {v}")

    TA.send_tele(message)
    message = []

sys.exit(0)
