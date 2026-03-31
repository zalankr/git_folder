import sys
import json
import telegram_alert as TA
from datetime import datetime, timedelta as time_obj
import pandas as pd
from collections import defaultdict
import gspread_updater as GU
import time as time_module
from tendo import singleton
import KIS_JP

try:
    me = singleton.SingleInstance()
except singleton.SingleInstanceException:
    TA.send_tele("JPQT: 이미 실행 중입니다.")
    sys.exit(0)

# ============================================
# KIS instance 생성
# ============================================
key_file_path = "/var/autobot/KIS/kis63604155nkr.txt"       # 트레이딩 계좌(수수료할인)
token_file_path = "/var/autobot/KIS/kis63604155_token.json" # 트레이딩 계좌(수수료할인)
cano = "63604155"      # ← 계좌번호 수동 입력
acnt_prdt_cd = "01"
KIS = KIS_JP.KIS_API(key_file_path, token_file_path, cano, acnt_prdt_cd)

fee_rate = KIS.SELL_FEE_RATE  # 0.09% 이벤트 계좌
JPQT_day_path = "/var/autobot/TR_JPQT/JPQT_day.json"
JPQT_target_path = "/var/autobot/TR_JPQT/JPQT_target.json"
JPQT_result_path = "/var/autobot/TR_JPQT/JPQT_result.json"
JPQT_daily_path = "/var/autobot/TR_JPQT/JPQT_daily.json"
JPQT_stock_path = "/var/autobot/TR_JPQT/JPQT_stock.csv"

# ============================================
# CSV 형식 (USQT_stock.csv와 동일 구조)
# ============================================
# code,name,weight,category
# CASH,CASH,0.00,CASH
# 9980,Mrk Holdings,0.05,trend
# 3932,Akatsuki,0.05,trend
# ...
# ※ 일본 주식은 4자리 숫자 코드 사용
# ※ CASH 행은 현금 비중 (0이면 전액 투자)

# ============================================
# 유틸리티 함수
# ============================================

def order_time(day=1):
    """
    거래일자와 거래회차 확인 (EC2 = UTC 시간대 기준)
    
    일본 정규장 (KST): 오전 09:00~11:30, 오후 12:30~15:00
    UTC 변환: 오전 00:00~02:30, 오후 03:30~06:00
    
    7회차 x 2일 = 총 14회차
    
    crontab (UTC):
      7 0,1,2,4 리밸런싱일,리밸런싱일+1 분기월 *   → 오전 3회
      37 3,4,5 리밸런싱일,리밸런싱일+1 분기월 *  → 오후 3회 (15:30 제외)
      0 4 리밸런싱일,리밸런싱일+1 분기월 *        → 오후 추가 1회
      (총 7회차 per day)
    
    실제 crontab 예시 (UTC):
      7 0,1,2,4 리밸런싱일,리밸런싱일+1 분기월 *   → 오전3 + 오후1 = 4슬롯
      37 3-5 리밸런싱일,리밸런싱일+1 분기월 *       → 오후3슬롯
      (총 7회차 per day × 2일 = 14회차)
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
    # 일본 정규장 UTC 시간 → round 매핑
    # 오전장 (KST 09:00~11:30 = UTC 00:00~02:30)
    #   UTC 00:00 → round 1
    #   UTC 01:00 → round 2
    #   UTC 02:00 → round 3
    # 오후장 (KST 12:30~15:00 = UTC 03:30~06:00)
    #   UTC 03:30 → round 4
    #   UTC 04:00 → round 5  (또는 04:30)
    #   UTC 04:30 → round 6  (또는 05:00)
    #   UTC 05:30 → round 7
    
    # 오전장: 7분 실행 (crontab: 7 0,1,2 → KST 09:07, 10:07, 11:07)
    if 0 <= minute <= 15:
        am_map = {0: 1, 1: 2, 2: 3}
        base_round = am_map.get(hour, 0)
        # 오후장 정시슬롯: 7 4 → KST 13:07
        if hour == 4:
            base_round = 5

    # 오후장: 37분 실행 (crontab: 37 3,4,5 → KST 12:37, 13:37, 14:37)
    elif 30 <= minute <= 45:
        pm_map = {3: 4, 4: 6, 5: 7}
        base_round = pm_map.get(hour, 0)

    if base_round > 0:
        result['round'] = base_round + (day * 7 - 7)

    return result

def health_check():
    """시스템 상태 확인"""
    checks = []
    
    if not KIS.access_token:
        checks.append("JPQT체크: API 토큰 없음")
    
    import os
    files = [JPQT_day_path, JPQT_stock_path]
    for f in files:
        if not os.path.exists(f):
            checks.append(f"JPQT체크: data파일 없음: {f}")
    
    try:
        import socket
        socket.create_connection(("openapi.koreainvestment.com", 9443), timeout=5)
    except:
        checks.append("JPQT체크: KIS API 서버 접속 불가")
    
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
        backup_path = f"/var/autobot/TR_JPQT/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
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
    일본주식은 정수가격 → 배율 적용 후 int() 처리
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
        TA.send_tele(f"JPQT: 유효하지 않은 round 값: {round_num}")
        sys.exit(1)

    round_split = {
        "sell_splits": sell_splits,
        "sell_price": sell_price,
        "buy_splits": buy_splits,
        "buy_price": buy_price
    }
    return round_split

def cancel_orders():
    """모든 미체결 주문 취소"""
    try:
        summary, cancel_msgs = KIS.cancel_all_unfilled_orders()
        cancel_message = f"JPQT: {summary['success']}/{summary['total']} 주문 취소 성공"
    except Exception as e:
        cancel_message = f"JPQT: 주문 취소 에러발생 ({e})"
    return cancel_message

def is_JP_trading_day():
    """
    일본 거래일 확인 (exchange_calendars 활용)
    EC2 = UTC이므로 UTC→JST 변환하여 JST 기준 날짜로 체크
    (UTC 00시 실행 = JST 09시이므로 날짜 차이 없음)
    """
    try:
        import exchange_calendars as xcals
        import pytz
        cal = xcals.get_calendar("XTKS")  # 도쿄증권거래소
        jst = pytz.timezone('Asia/Tokyo')
        from datetime import timezone
        today_jst = datetime.now(timezone.utc).astimezone(jst).date()
        return cal.is_session(pd.Timestamp(today_jst))
    except ImportError:
        try:
            import pytz
            jst = pytz.timezone('Asia/Tokyo')
            from datetime import timezone
            weekday = datetime.now(timezone.utc).astimezone(jst).weekday()
        except ImportError:
            weekday = datetime.utcnow().weekday()
        return weekday < 5  # 월~금
    except Exception:
        return True  # 확인 불가 시 진행

# ============================================
# 메인 로직 # 분기 리밸런싱 (일본주식)
# ============================================

checkday = is_JP_trading_day()
if not checkday:
    TA.send_tele("JPQT: 일본 거래일이 아닙니다.")
    sys.exit(0)

health_check()
message = []

# JPQT_day.json 불러오기
try:
    with open(JPQT_day_path, 'r', encoding='utf-8') as f:
        TR = json.load(f)
except Exception as e:
    TA.send_tele(f"JPQT_day.json 파일 오류: {e}")
    sys.exit(1)

# 일자와 회차 시간데이터 불러오기
order = order_time(day=TR['day'])

if order['round'] == 0:
    TA.send_tele("JPQT: 매매시간이 아닙니다.")
    sys.exit(0)
message.append(f"JPQT: {order['day']}일차 {order['round']}/{order['total_round']}회차 매매를 시작합니다.")

# 전회 주문 취소
cancel_message = cancel_orders()
message.append(cancel_message)

# ============================================
# 회차별 target 데이터 불러오기 (1, 8회차: 불러오기와 계산)
# ============================================
if order['round'] == 1 or order['round'] == 8:
    # 목표종목 csv파일 불러오기
    try:
        with open(JPQT_stock_path, 'r', encoding='utf-8') as f:
            Target = pd.read_csv(f, dtype={
                "code": str,
                "name": str,
                "weight": float,
                "category": str
            })
    except Exception as e:
        TA.send_tele(f"JPQT_stock.csv 파일 오류: {e}")
        sys.exit(1)

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
    # 총 JPY 평가금액 산출
    # ============================================
    # 일본주식 총자산 = 주식평가금(JPY) + 주문가능현금(JPY)
    stocks_list = KIS.get_JP_stock_balance()
    if not isinstance(stocks_list, list):
        TA.send_tele(f"JPQT: 잔고 조회 불가로 종료합니다. ({stocks_list})")
        sys.exit(1)

    stock_eval_jpy = sum(s['eval_amt'] for s in stocks_list)
    time_module.sleep(0.2)

    # ✅ get_JP_order_available(): TTTS3007R(TKSE) → MTS 주문가능금액과 동일 (엔화)
    orderable_jpy = KIS.get_JP_order_available()
    if orderable_jpy is None:
        TA.send_tele("JPQT: JPY 주문가능금액 조회 불가로 종료합니다.")
        sys.exit(1)

    total_jpy_asset = stock_eval_jpy + orderable_jpy
    message.append(
        f"JPQT 총자산: ¥{total_jpy_asset:,.0f} "
        f"(주식:¥{stock_eval_jpy:,.0f} + 현금:¥{orderable_jpy:,.0f})"
    )

    # ============================================
    # 종목별 목표 투자금액 및 수량 산출
    # ============================================
    target_code = list(target.keys())

    total_weight = sum(v['weight'] for v in target.values())
    if abs(total_weight - 1.0) > 0.01:
        TA.send_tele(f"JPQT 경고: CSV weight 합계 = {total_weight:.3f} (1.0 아님). 계속 진행합니다.")
        message.append(f"weight 합계 경고: {total_weight:.3f}")

    for ticker in target_code:
        if ticker == "CASH":
            target[ticker]['target_invest'] = float(target[ticker]['weight'] * total_jpy_asset)
            target[ticker]['target_qty'] = 0
            continue

        price = KIS.get_JP_current_price(ticker)
        if not isinstance(price, float) or price <= 0:
            TA.send_tele(f"JPQT: {ticker} 현재가 조회 불가로 종료합니다. ({price})")
            sys.exit(1)

        target[ticker]['current_price'] = price
        target[ticker]['target_invest'] = float(target[ticker]['weight'] * total_jpy_asset)
        # ★ 일본주식: 100주 단위 매매 (TSE 매매단위)
        raw_qty = int(target[ticker]['target_invest'] / price)
        target[ticker]['target_qty'] = (raw_qty // 100) * 100  # 100주 단위 절사
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
    json_message = save_json(target_serializable, JPQT_target_path, order)
    message.extend(json_message)
    target_code = list(target.keys())

else:
    # 1회, 8회차가 아닌 경우 불러오기만 시행
    try:
        with open(JPQT_target_path, 'r', encoding='utf-8') as f:
            target = json.load(f)
    except Exception as e:
        TA.send_tele(f"JPQT_target.json 파일 오류: {e}")
        sys.exit(1)
    target_code = list(target.keys())

# ============================================
# 보유 종목 잔고 불러오기
# ============================================
stocks = KIS.get_JP_stock_balance()
if not isinstance(stocks, list):
    TA.send_tele(f"JPQT: 잔고 조회 불가로 종료합니다. ({stocks})")
    sys.exit(1)

hold = {}
for stock in stocks:
    ticker = stock["ticker"]
    hold[ticker] = {
        "name": stock["name"],
        "hold_balance": stock["eval_amt"],      # JPY 평가금액
        "hold_qty": stock["quantity"],           # 체결기준 현재잔고 (ccld_qty_smtl1)
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
            sell[ticker] = hold[ticker]["hold_qty"] - target[ticker]["target_qty"]
    else:
        sell[ticker] = hold[ticker]["hold_qty"]  # 목표에 없는 종목은 전량 매도

for ticker in target_code:
    if ticker == "CASH":
        continue
    if ticker not in hold_code:
        buy[ticker] = target[ticker]["target_qty"]

# ★ 100주 단위 보정 (매수/매도 수량)
buy = {t: (q // 100) * 100 for t, q in buy.items() if (q // 100) * 100 > 0}
sell = {t: (q // 100) * 100 for t, q in sell.items() if (q // 100) * 100 > 0}

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
    message.append("JPQT: 매도 종목 없음")

elif sell_split[0] > 0:
    message.append(f"JPQT: {order['round']}회차 - 매도 주문")
    for ticker, qty in sell.items():
        local_split_count = sell_split[0]
        local_split_price = sell_split[1][:]
        split_qty = int(qty // local_split_count)
        # ★ 100주 단위 보정
        split_qty = (split_qty // 100) * 100
        if split_qty < 100:
            local_split_count = 1
            local_split_price = [0.99]
            split_qty = (int(qty) // 100) * 100

        if split_qty < 100:
            message.append(f"JPQT 매도 스킵: {ticker} 수량 {qty}주 (100주 미만)")
            continue

        price = KIS.get_JP_current_price(ticker)
        if not isinstance(price, float) or price <= 0:
            TA.send_tele(f"JPQT: {ticker} 현재가 조회 불가로 종료합니다. ({price})")
            sys.exit(1)

        for i in range(local_split_count):
            if i == local_split_count - 1:
                quantity = int(qty - split_qty * (local_split_count - 1))
                quantity = (quantity // 100) * 100
            else:
                quantity = split_qty

            if quantity < 100:
                continue

            # ★ 일본주식: 정수 가격
            order_price = int(round(price * local_split_price[i], 0))

            order_info, order_msgs = KIS.order_sell_JP(ticker, quantity, order_price)
            if order_info is None:
                time_module.sleep(2)
                order_info, order_msgs = KIS.order_sell_JP(ticker, quantity, order_price)
            if order_info is None:
                message.append(f"JPQT 매도 오류: {ticker} {quantity}주 ¥{order_price:,} API 응답 없음")
            elif order_info.get("success"):
                message.append(
                    f"매도 {ticker} {quantity}주 ¥{order_price:,} "
                    f"주문번호:{order_info.get('order_number','')}"
                )
            else:
                message.append(
                    f"매도 실패 {ticker} {quantity}주: {order_info.get('error_message','')}"
                )
            message.extend(order_msgs)
            time_module.sleep(0.2)
else:
    message.append(f"JPQT: {order['round']}회차 매도 스킵 - 미처분 잔량: {list(sell.keys())}")

# 회차별 매도 메세지 telegram 출력
TA.send_tele(message)
message = []

# ============================================
# 매도-매수 시간 딜레이
# 일본주식: T+2 결제이나 매도재사용가능
# ============================================
time_module.sleep(600)

# ============================================
# 매수 구간 전환
# ============================================
JPY = KIS.get_JP_order_available()
if JPY is None:
    TA.send_tele("JPQT: JPY 주문가능금액 조회 불가로 종료합니다.")
    sys.exit(1)

orderable_JPY = float(JPY)
target_JPY = 0.0
buy_prices = {}
buy_price_rate = buy_split[1][-1] if buy_split[1] else 1.0

for ticker, qty in buy.items():
    price = KIS.get_JP_current_price(ticker)
    if not isinstance(price, float) or price <= 0:
        TA.send_tele(f"JPQT: {ticker} 현재가 조회 불가로 종료합니다. ({price})")
        sys.exit(1)
    buy_prices[ticker] = price
    ticker_invest = price * buy_price_rate * qty
    target_JPY += ticker_invest
    time_module.sleep(0.15)

message.append(
    f"JPQT 매수가능: ¥{orderable_JPY:,.0f} | 목표매수금: ¥{target_JPY:,.0f}"
    + (f" | 조정비율: {orderable_JPY/target_JPY:.4f}" if target_JPY > 0 else "")
)

if target_JPY > orderable_JPY:
    adjust_rate = orderable_JPY / target_JPY
    for ticker, ticker_qty in buy.items():
        adjusted = int(ticker_qty * adjust_rate)
        # ★ 100주 단위 절사
        adjusted = (adjusted // 100) * 100
        buy[ticker] = adjusted

    buy = {ticker: qty for ticker, qty in buy.items() if qty >= 100}
    message.append(f"JPQT 매수수량 조정 완료 (adjust_rate={adjust_rate:.4f})")
else:
    message.append("JPQT 매수가능금 충분 → 수량 조정 없음")

# ============================================
# 매수 주문
# ============================================
buy = {ticker: qty for ticker, qty in buy.items() if qty >= 100}  # 방어적 100주 미만 제거
buy_code = list(buy.keys())

if len(buy_code) == 0:
    message.append("JPQT: 매수 종목 없음")

elif len(buy_code) > 0 and buy_split[0] > 0:
    message.append(f"JPQT: {order['round']}회차 - 매수 주문")
    for ticker, qty in buy.items():
        local_split_count = buy_split[0]
        local_split_price = buy_split[1][:]
        split_qty = int(qty // local_split_count)
        # ★ 100주 단위 보정
        split_qty = (split_qty // 100) * 100
        if split_qty < 100:
            if qty < 100:
                message.append(f"JPQT 매수 스킵: {ticker} 수량 {qty}주 (100주 미만)")
                continue
            local_split_count = 1
            local_split_price = [1.01]
            split_qty = (int(qty) // 100) * 100

        price = buy_prices.get(ticker)
        if not isinstance(price, float) or price <= 0:
            TA.send_tele(f"JPQT: {ticker} 현재가 없음으로 종료합니다.")
            sys.exit(1)

        for i in range(local_split_count):
            if i == local_split_count - 1:
                quantity = int(qty - split_qty * (local_split_count - 1))
                quantity = (quantity // 100) * 100
            else:
                quantity = split_qty

            if quantity < 100:
                continue

            # ★ 일본주식: 정수 가격
            order_price = int(round(price * local_split_price[i], 0))

            order_info, order_msgs = KIS.order_buy_JP(ticker, quantity, order_price)
            if order_info is None:
                time_module.sleep(2)
                order_info, order_msgs = KIS.order_buy_JP(ticker, quantity, order_price)
            if order_info is None:
                message.append(f"JPQT 매수 오류: {ticker} {quantity}주 ¥{order_price:,} API 응답 없음")
            elif order_info.get("success"):
                message.append(
                    f"매수 {ticker} {quantity}주 ¥{order_price:,} "
                    f"주문번호:{order_info.get('order_number','')}"
                )
            else:
                message.append(
                    f"매수 실패 {ticker} {quantity}주 ¥{order_price:,}: "
                    f"{order_info.get('error_message','')}"
                )
            message.extend(order_msgs)
            time_module.sleep(0.2)

# ============================================
# day 전환 (7회차→day2, 14회차→day1)
# ============================================
if order['round'] == 7:
    TR = {"day": 2}
    json_message = save_json(TR, JPQT_day_path, order)
    message.extend(json_message)

if order['round'] == 14:
    TR = {"day": 1}
    json_message = save_json(TR, JPQT_day_path, order)
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
    cancel_message = cancel_orders()
    message.append(cancel_message)
    message.append(f"JPQT {order['date']} 리밸런싱 종료")

    # 시작목표 불러오기
    try:
        with open(JPQT_stock_path, 'r', encoding='utf-8') as f:
            plan = pd.read_csv(f, dtype={
                "code": str,
                "name": str,
                "weight": float,
                "category": str
            })
    except Exception as e:
        TA.send_tele(f"JPQT_stock.csv 파일 오류: {e}")
        sys.exit(1)

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
    stocks = KIS.get_JP_stock_balance()
    if not isinstance(stocks, list):
        TA.send_tele(f"JPQT: 잔고 조회 불가로 종료합니다. ({stocks})")
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
            balance = f"¥{float(item['balance']):,.0f}"
            message.append(
                f"종목명: {item['name']}, 잔고: {qty}주, 평가금: {balance}, 상태: {item['status']}"
            )

    # 전략결과 저장
    json_message = save_json(result, JPQT_result_path, order)
    message.extend(json_message)
    time_module.sleep(1.0)

    # ============================================
    # 최종 결과 저장
    # ============================================
    final_stocks = KIS.get_JP_stock_balance()
    if not isinstance(final_stocks, list):
        TA.send_tele(f"JPQT: 최종 잔고 조회 불가로 종료합니다. ({final_stocks})")
        sys.exit(1)
    final_stock_eval = sum(s['eval_amt'] for s in final_stocks)
    time_module.sleep(0.2)

    final_jpy = KIS.get_JP_order_available()
    if final_jpy is None:
        TA.send_tele("JPQT: 최종 JPY 주문가능금액 조회 불가로 종료합니다.")
        sys.exit(1)

    daily_data = {
        "date": str(order['date']),
        "total_stocks":    float(final_stock_eval),
        "total_cash":      float(final_jpy),
        "total_asset":     float(final_stock_eval) + float(final_jpy),
        "total_asset_ret": 0.0,
        "currency":        "JPY"
    }

    for category, stocks_list in result.items():
        category_balance = sum(float(item['balance']) for item in stocks_list)
        daily_data[category]          = float(category_balance)
        daily_data[f"{category}_ret"] = 0.0

    # JPQT_daily.json 저장
    try:
        json_message = save_json(daily_data, JPQT_daily_path, order)
        message.extend(json_message)
    except Exception as e:
        error_msg = f"JPQT_daily.json 저장 실패: {e}"
        TA.send_tele(error_msg)
    time_module.sleep(1.0)

    # data 정제 (표시용)
    daily = {
        "date": daily_data["date"],
        "total_stocks":    f"¥{daily_data['total_stocks']:,.0f}",
        "total_cash":      f"¥{daily_data['total_cash']:,.0f}",
        "total_asset":     f"¥{daily_data['total_asset']:,.0f}",
        "total_asset_ret": f"{float(daily_data['total_asset_ret']*100):.2f}%"
    }

    for category, stocks_list in result.items():
        category_balance = sum(float(item['balance']) for item in stocks_list)
        daily[category]          = f"¥{category_balance:,.0f}"
        daily[f"{category}_ret"] = "0.00%"

    """
    # daily balance Google Sheet 저장 보류
    try:
        credentials_file = "/var/autobot/gspread/service_account.json"
        spreadsheet_name = "2026_JPQT_daily"

        spreadsheet = GU.connect_google_sheets(credentials_file, spreadsheet_name)
        current_month = datetime.now().month

        GU.save_to_sheets(spreadsheet, daily, current_month)
        message.append(f"2026_JPQT_daily Google Sheet 업로드 완료")

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
