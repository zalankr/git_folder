import sys
import json
import telegram_alert as TA
from datetime import datetime, timezone, timedelta
import pandas as pd
from collections import defaultdict
import gspread_updater as GU
import time as time_module
from tendo import singleton
import KIS_US

try:
    me = singleton.SingleInstance()
except singleton.SingleInstanceException:
    TA.send_tele("USQT: 이미 실행 중입니다.")
    sys.exit(0)

# ============================================
# KIS instance 생성
# ============================================
key_file_path = "/var/autobot/TR_USQT/kis63604155nkr.txt"       # 트레이딩 계쫘(수수료할인)
token_file_path = "/var/autobot/TR_USQT/kis63604155_token.json" # 트레이딩 계쫘(수수료할인)
cano = "63604155"      # ← 계좌번호 수동 입력
acnt_prdt_cd = "01"
KIS = KIS_US.KIS_API(key_file_path, token_file_path, cano, acnt_prdt_cd)

fee_rate = KIS.SELL_FEE_RATE  # 0.09% 이벤트 계좌
USQT_day_path = "/var/autobot/TR_USQT/USQT_day.json"
USQT_target_path = "/var/autobot/TR_USQT/USQT_target.json"
USQT_result_path = "/var/autobot/TR_USQT/USQT_result.json"
USQT_daily_path = "/var/autobot/TR_USQT/USQT_daily.json"
USQT_stock_path = "/var/autobot/TR_USQT/USQT_stock.csv"

# ============================================
# CSV 형식 (KRQT_stock.csv와 동일 구조)
# ============================================
# code,name,weight,category
# CASH,CASH,0.50,
# AAPL,Apple Inc,0.05,모멘텀
# MSFT,Microsoft Corp,0.05,밸류
# ...
# ※ 미국 주식은 code 앞에 'A' 접두어 없이 티커 그대로 사용

# ============================================
# 유틸리티 함수
# ============================================

def check_dst():
    """
    미국이 현재 DST(서머타임)인지 판단
    DST: 3월 둘째 일요일 02:00 ET ~ 11월 첫째 일요일 02:00 ET
    pytz로 정확히 판단, 미설치 시 간이 판단 fallback
    """
    try:
        import pytz
        from datetime import datetime as dt, timezone
        eastern = pytz.timezone('America/New_York')
        now_et = dt.now(timezone.utc).astimezone(eastern)
        return bool(now_et.dst())
    except ImportError:
        # pytz 미설치 시 간이 판단 (3월~10월)
        from datetime import datetime as dt, timezone
        month = dt.now(timezone.utc).month
        return 3 <= month <= 10

def order_time(day=1):
    """
    거래일자와 거래회차 확인 (EC2 = UTC 시간대 기준)
    
    미국 정규장: ET 09:30~16:00
      DST(EDT=UTC-4): UTC 13:30~20:00
        → crontab 매 정시 30분 실행: UTC 13,14,15,16,17,18,19 = 7슬롯
      EST(UTC-5):     UTC 14:30~21:00
        → crontab 매 정시 30분 실행: UTC 14,15,16,17,18,19,20 = 7슬롯
    
    7회차 x 2일 = 총 14회차
    
    crontab 예시 (UTC):
      DST:  30 13-19 리밸런싱일,리밸런싱일+1 분기월 *
      EST:  30 14-20 리밸런싱일,리밸런싱일+1 분기월 *
    """
    from datetime import datetime as dt, timezone
    now = dt.now(timezone.utc)       # EC2 기본 = UTC
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
    is_dst = check_dst()

    # 정규장 시간대 round 매핑 (UTC 기준, 7회차)
    if is_dst:
        # DST(EDT=UTC-4): 정규장 UTC 13:30~20:00
        # crontab 30분에 실행 → UTC 13,14,15,16,17,18,19
        round_map = {13: 1, 14: 2, 15: 3, 16: 4, 17: 5, 18: 6, 19: 7}
    else:
        # EST(UTC-5): 정규장 UTC 14:30~21:00
        # crontab 30분에 실행 → UTC 14,15,16,17,18,19,20
        round_map = {14: 1, 15: 2, 16: 3, 17: 4, 18: 5, 19: 6, 20: 7}

    base_round = round_map.get(hour, 0)
    if base_round > 0:
        result['round'] = base_round + (day * 7 - 7)  # day=1: 1~7, day=2: 8~14

    return result

def health_check():
    """시스템 상태 확인"""
    checks = []
    
    if not KIS.access_token:
        checks.append("USQT체크: API 토큰 없음")
    
    import os
    files = [USQT_day_path, USQT_stock_path]
    for f in files:
        if not os.path.exists(f):
            checks.append(f"USQT체크: data파일 없음: {f}")
    
    try:
        import socket
        socket.create_connection(("openapi.koreainvestment.com", 9443), timeout=5)
    except:
        checks.append("USQT체크: KIS API 서버 접속 불가")
    
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
        backup_path = f"/var/autobot/TR_USQT/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            result_msgs.append(f"백업 파일 생성: {backup_path}")
        except Exception as backup_error:
            result_msgs.append(f"백업 실패: {backup_error}")
    return result_msgs

def split_data(round_num):
    """
    회차별 분할횟수와 분할당 가격 산출
    소수점 2자리 가격 → 배율로 처리 후 round(price, 2)
    """
    if round_num == 1:
        sell_splits = 5
        sell_price = [1.020, 1.015, 1.010, 1.005, 0.995]
        buy_splits = 5
        buy_price = [0.980, 0.985, 0.990, 0.995, 0.9975]
    elif round_num == 2:
        sell_splits = 4
        sell_price = [1.020, 1.015, 1.010, 1.005]
        buy_splits = 5
        buy_price = [0.980, 0.985, 0.990, 0.995, 1.005]
    elif round_num == 3:
        sell_splits = 4
        sell_price = [1.015, 1.010, 1.005, 1.0025]
        buy_splits = 4
        buy_price = [0.980, 0.985, 0.990, 0.995]
    elif round_num == 4:
        sell_splits = 4
        sell_price = [1.015, 1.010, 1.005, 0.995]
        buy_splits = 4
        buy_price = [0.985, 0.990, 0.995, 0.9975]
    elif round_num == 5:
        sell_splits = 3
        sell_price = [1.015, 1.010, 1.005]
        buy_splits = 4
        buy_price = [0.985, 0.990, 0.995, 1.005]
    elif round_num == 6:
        sell_splits = 3
        sell_price = [1.010, 1.005, 1.0025]
        buy_splits = 3
        buy_price = [0.985, 0.990, 0.995]
    elif round_num == 7:
        sell_splits = 3
        sell_price = [1.010, 1.005, 0.995]
        buy_splits = 3
        buy_price = [0.990, 0.995, 0.9975]
    elif round_num == 8:
        sell_splits = 2
        sell_price = [1.010, 1.005]
        buy_splits = 3
        buy_price = [0.990, 0.995, 1.005]
    elif round_num == 9:
        sell_splits = 2
        sell_price = [1.005, 1.0025]
        buy_splits = 2
        buy_price = [0.990, 0.995]
    elif round_num == 10:
        sell_splits = 2
        sell_price = [1.005, 0.995]
        buy_splits = 2
        buy_price = [0.995, 0.9975]
    elif round_num == 11:
        sell_splits = 1
        sell_price = [1.005]
        buy_splits = 2
        buy_price = [0.995, 1.005]
    elif round_num == 12:
        sell_splits = 1
        sell_price = [1.0025]
        buy_splits = 1
        buy_price = [0.995]
    elif round_num == 13:
        sell_splits = 1
        sell_price = [0.980]
        buy_splits = 1
        buy_price = [0.9975]
    elif round_num == 14:
        sell_splits = 0
        sell_price = []
        buy_splits = 1
        buy_price = [1.020]
    else:
        TA.send_tele(f"USQT: 유효하지 않은 round 값: {round_num}")
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
        cancel_message = f"USQT: {summary['success']}/{summary['total']} 주문 취소 성공"
    except Exception as e:
        cancel_message = f"USQT: 주문 취소 에러발생 ({e})"
    return cancel_message


def is_US_trading_day():
    """
    미국 거래일 확인 (exchange_calendars 활용)
    EC2 = UTC 시간대이므로 datetime.now()는 UTC
    UTC→ET 변환하여 ET 기준 날짜로 거래일 체크
    (UTC 20시 이후 실행 시 ET은 아직 당일 정규장임)
    """
    try:
        import exchange_calendars as xcals
        import pytz
        cal = xcals.get_calendar("XNYS")
        eastern = pytz.timezone('America/New_York')
        from datetime import timezone
        today_et = datetime.now(timezone.utc).astimezone(eastern).date()
        return cal.is_session(pd.Timestamp(today_et))
    except ImportError:
        # exchange_calendars 미설치 시 평일 체크로 대체
        try:
            import pytz
            eastern = pytz.timezone('America/New_York')
            from datetime import timezone
            weekday = datetime.now(timezone.utc).astimezone(eastern).weekday()
        except ImportError:
            # pytz도 없으면 UTC 기준 평일 체크 (UTC와 ET 날짜가 다를 수 있으나 최선)
            weekday = datetime.now(timezone.utc).weekday()
        return weekday < 5  # 월~금
    except Exception:
        return True  # 확인 불가 시 진행


# ============================================
# 메인 로직 # 분기 리밸런싱 (미국주식)
# ============================================

checkday = is_US_trading_day()
if not checkday:
    TA.send_tele("USQT: 미국 거래일이 아닙니다.")
    sys.exit(0)

health_check()
message = []

# USQT_day.json 불러오기
try:
    with open(USQT_day_path, 'r', encoding='utf-8') as f:
        TR = json.load(f)
except Exception as e:
    TA.send_tele(f"USQT_day.json 파일 오류: {e}")
    sys.exit(1)

# 일자와 회차 시간데이터 불러오기
order = order_time(day=TR['day'])

if order['round'] == 0:
    TA.send_tele("USQT: 매매시간이 아닙니다.")
    sys.exit(0)
message.append(f"USQT: {order['day']}일차 {order['round']}/{order['total_round']}회차 매매를 시작합니다.")

# 전회 주문 취소
cancel_message = cancel_orders()
message.append(cancel_message)

# ============================================
# 회차별 target 데이터 불러오기 (1, 8회차: 불러오기와 계산)
# ============================================
if order['round'] == 1 or order['round'] == 8:
    # 목표종목 csv파일 불러오기
    try:
        with open(USQT_stock_path, 'r', encoding='utf-8') as f:
            Target = pd.read_csv(f, dtype={
                "code": str,
                "name": str,
                "weight": float,
                "category": str
            })
    except Exception as e:
        TA.send_tele(f"USQT_stock.csv 파일 오류: {e}")
        sys.exit(1)

    # 미국주식: 코드 앞 'A' 접두어 없음 → 별도 처리 불필요
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
    # 총 USD 평가금액 산출
    # ============================================
    # 미국주식 총자산 = 주식평가금(USD) + 주문가능현금(USD)
    stocks_list = KIS.get_US_stock_balance()
    if not isinstance(stocks_list, list):
        TA.send_tele(f"USQT: 잔고 조회 불가로 종료합니다. ({stocks_list})")
        sys.exit(1)

    stock_eval_usd = sum(s['eval_amt'] for s in stocks_list)
    time_module.sleep(0.2)

    # ✅ get_US_order_available(): TTTS3007R → MTS 주문가능금액과 동일
    #    = 외화예수금 + 매도재사용가능금액(T+2 미결제) - 당일 이미 매수에 사용된 금액
    orderable_usd = KIS.get_US_order_available()
    if orderable_usd is None:
        TA.send_tele("USQT: USD 주문가능금액 조회 불가로 종료합니다.")
        sys.exit(1)

    total_usd_asset = stock_eval_usd + orderable_usd
    message.append(
        f"USQT 총자산: ${total_usd_asset:,.2f} "
        f"(주식:${stock_eval_usd:,.2f} + 현금:${orderable_usd:,.2f})"
    )

    # ============================================
    # 종목별 목표 투자금액 및 수량 산출
    # ============================================
    target_code = list(target.keys())

    total_weight = sum(v['weight'] for v in target.values())
    if abs(total_weight - 1.0) > 0.01:
        TA.send_tele(f"USQT 경고: CSV weight 합계 = {total_weight:.3f} (1.0 아님). 계속 진행합니다.")
        message.append(f"weight 합계 경고: {total_weight:.3f}")

    for ticker in target_code:
        if ticker == "CASH":
            target[ticker]['target_invest'] = float(target[ticker]['weight'] * total_usd_asset)
            target[ticker]['target_qty'] = 0
            continue

        price = KIS.get_US_current_price(ticker)
        if not isinstance(price, float) or price <= 0:
            TA.send_tele(f"USQT: {ticker} 현재가 조회 불가로 종료합니다. ({price})")
            sys.exit(1)

        target[ticker]['current_price'] = price
        target[ticker]['target_invest'] = float(target[ticker]['weight'] * total_usd_asset)
        target[ticker]['target_qty'] = int(target[ticker]['target_invest'] / price)
        time_module.sleep(0.15)

    # 당일 target 저장하기
    # JSON 직렬화를 위해 float/int 명시 변환
    target_serializable = {}
    for k, v in target.items():
        target_serializable[k] = {
            key: (float(val) if isinstance(val, float) else
                  int(val) if isinstance(val, (int,)) and not isinstance(val, bool) else
                  val)
            for key, val in v.items()
        }
    json_message = save_json(target_serializable, USQT_target_path, order)
    message.extend(json_message)
    target_code = list(target.keys())  # 공통 영역에서도 사용하므로 여기서 정의

else:
    # 1회, 8회차가 아닌 경우 불러오기만 시행
    try:
        with open(USQT_target_path, 'r', encoding='utf-8') as f:
            target = json.load(f)
    except Exception as e:
        TA.send_tele(f"USQT_target.json 파일 오류: {e}")
        sys.exit(1)
    target_code = list(target.keys())

# ============================================
# 보유 종목 잔고 불러오기
# ============================================
stocks = KIS.get_US_stock_balance()
if not isinstance(stocks, list):
    TA.send_tele(f"USQT: 잔고 조회 불가로 종료합니다. ({stocks})")
    sys.exit(1)

hold = {}
for stock in stocks:
    ticker = stock["ticker"]
    hold[ticker] = {
        "name": stock["name"],
        "hold_balance": stock["eval_amt"],      # USD 평가금액
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
    message.append("USQT: 매도 종목 없음")

elif sell_split[0] > 0:
    message.append(f"USQT: {order['round']}회차 - 매도 주문")
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

        price = KIS.get_US_current_price(ticker)
        if not isinstance(price, float) or price <= 0:
            TA.send_tele(f"USQT: {ticker} 현재가 조회 불가로 종료합니다. ({price})")
            sys.exit(1)

        raw_excd = hold.get(ticker, {}).get("exchange", "")
        excd_map = {"NAS": "NASD", "NYS": "NYSE", "AMS": "AMEX",
                    "NASD": "NASD", "NYSE": "NYSE", "AMEX": "AMEX"}
        ticker_exchange = excd_map.get(raw_excd, None)

        for i in range(local_split_count):
            this_qty = split_qty + (remainder if i == local_split_count - 1 else 0)
            if this_qty < 1:
                continue

            order_price = round(price * local_split_price[i], 2)

            order_info, order_msgs = KIS.order_sell_US(
                ticker, this_qty, order_price, exchange=ticker_exchange
            )
            if order_info is None:
                time_module.sleep(2)
                order_info, order_msgs = KIS.order_sell_US(
                    ticker, this_qty, order_price, exchange=ticker_exchange
                )
            if order_info is None:
                message.append(f"USQT 매도 오류: {ticker} {this_qty}주 ${order_price:.2f} API 응답 없음")
            elif order_info.get("success"):
                message.append(
                    f"매도 {ticker} {this_qty}주 ${order_price:.2f} "
                    f"주문번호:{order_info.get('order_number','')}"
                )
            else:
                message.append(
                    f"매도 실패 {ticker} {this_qty}주: {order_info.get('error_message','')}"
                )
            message.extend(order_msgs)
            time_module.sleep(0.2)
else:
    # 14회차: 잔량 있어도 매도 스킵
    message.append(f"USQT: {order['round']}회차 매도 스킵 - 미처분 잔량: {list(sell.keys())}")

# 회차별 매도 메세지 telegram 출력
TA.send_tele(message)
message = []

# ============================================
# 매도-매수 시간 딜레이 (미국주식: T+1 결제이나 매도재사용가능)
# ============================================
time_module.sleep(600)

# ============================================
# 매수 구간 전환
# ============================================
# ✅ get_US_order_available() = TTTS3007R → MTS 주문가능금액
#    = 외화예수금 + 매도재사용가능(T+1 미결제) - 당일 이미 매수 사용분
USD = KIS.get_US_order_available()
if USD is None:
    TA.send_tele("USQT: USD 주문가능금액 조회 불가로 종료합니다.")
    sys.exit(1)

orderable_USD = float(USD)
target_USD = 0.0
buy_prices = {}
buy_price_rate = buy_split[1][-1] if buy_split[1] else 1.0  # 최대 배율 기준

for ticker, qty in buy.items():
    price = KIS.get_US_current_price(ticker)
    if not isinstance(price, float) or price <= 0:
        TA.send_tele(f"USQT: {ticker} 현재가 조회 불가로 종료합니다. ({price})")
        sys.exit(1)
    buy_prices[ticker] = price
    ticker_invest = price * buy_price_rate * qty
    target_USD += ticker_invest
    time_module.sleep(0.15)

# 디버그: 매수 가능금액 vs 목표 매수금 비교 로그
message.append(
    f"USQT 매수가능: ${orderable_USD:,.2f} | 목표매수금: ${target_USD:,.2f}"
    + (f" | 조정비율: {orderable_USD/target_USD:.4f}" if target_USD > 0 else "")
)

if target_USD > orderable_USD:
    adjust_rate = orderable_USD / target_USD
    for ticker, ticker_qty in buy.items():
        adjusted = int(ticker_qty * adjust_rate)
        buy[ticker] = adjusted

    buy = {ticker: qty for ticker, qty in buy.items() if qty > 0}
    message.append(f"USQT 매수수량 조정 완료 (adjust_rate={adjust_rate:.4f})")
else:
    message.append("USQT 매수가능금 충분 → 수량 조정 없음")

# ============================================
# 매수 주문
# ============================================
buy = {ticker: qty for ticker, qty in buy.items() if qty > 0}  # 방어적 0주 제거
buy_code = list(buy.keys())

if len(buy_code) == 0:
    message.append("USQT: 매수 종목 없음")

elif len(buy_code) > 0 and buy_split[0] > 0:
    message.append(f"USQT: {order['round']}회차 - 매수 주문")
    for ticker, qty in buy.items():
        local_split_count = buy_split[0]
        local_split_price = buy_split[1][:]
        split_qty = int(qty // local_split_count)
        remainder = int(qty - split_qty * local_split_count)

        if split_qty < 1:
            if qty < 1:
                message.append(f"USQT 매수 스킵: {ticker} 수량 0주 (조정후 제거대상)")
                continue
            local_split_count = 1
            local_split_price = [1.01]
            split_qty = int(qty)
            remainder = 0

        price = buy_prices.get(ticker)
        if not isinstance(price, float) or price <= 0:
            TA.send_tele(f"USQT: {ticker} 현재가 없음으로 종료합니다.")
            sys.exit(1)

        for i in range(local_split_count):
            this_qty = split_qty + (remainder if i == local_split_count - 1 else 0)
            if this_qty < 1:
                continue

            order_price = round(price * local_split_price[i], 2)

            order_info, order_msgs = KIS.order_buy_US(ticker, this_qty, order_price)
            if order_info is None:
                time_module.sleep(2)
                order_info, order_msgs = KIS.order_buy_US(ticker, this_qty, order_price)
            if order_info is None:
                message.append(f"USQT 매수 오류: {ticker} {this_qty}주 ${order_price:.2f} API 응답 없음")
            elif order_info.get("success"):
                message.append(
                    f"매수 {ticker} {this_qty}주 ${order_price:.2f} "
                    f"주문번호:{order_info.get('order_number','')}"
                )
            else:
                message.append(
                    f"매수 실패 {ticker} {this_qty}주 ${order_price:.2f}: "
                    f"{order_info.get('error_message','')}"
                )
            message.extend(order_msgs)
            time_module.sleep(0.2)

# ============================================
# day 전환 (7회차→day2, 14회차→day1)
# ============================================
if order['round'] == 7:
    TR = {"day": 2}
    json_message = save_json(TR, USQT_day_path, order)
    message.extend(json_message)

if order['round'] == 14:
    TR = {"day": 1}
    json_message = save_json(TR, USQT_day_path, order)
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
    message.append(f"USQT {order['date']} 리밸런싱 종료")

    # 시작목표 불러오기
    try:
        with open(USQT_stock_path, 'r', encoding='utf-8') as f:
            plan = pd.read_csv(f, dtype={
                "code": str,
                "name": str,
                "weight": float,
                "category": str
            })
    except Exception as e:
        TA.send_tele(f"USQT_stock.csv 파일 오류: {e}")
        sys.exit(1)

    # A접두어 제거 (혹시 있을 경우)
    if plan["code"].str.startswith("A").any():
        plan["code"] = plan["code"].str.replace(r"^A", "", regex=True)

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
    stocks = KIS.get_US_stock_balance()
    if not isinstance(stocks, list):
        TA.send_tele(f"USQT: 잔고 조회 불가로 종료합니다. ({stocks})")
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
            balance = f"${float(item['balance']):,.2f}"
            message.append(
                f"종목명: {item['name']}, 잔고: {qty}주, 평가금: {balance}, 상태: {item['status']}"
            )

    # 전략결과 저장
    json_message = save_json(result, USQT_result_path, order)
    message.extend(json_message)
    time_module.sleep(1.0)

    # ============================================
    # 최종 결과 저장
    # ============================================
    final_stocks = KIS.get_US_stock_balance()
    if not isinstance(final_stocks, list):
        TA.send_tele(f"USQT: 최종 잔고 조회 불가로 종료합니다. ({final_stocks})")
        sys.exit(1)
    final_stock_eval = sum(s['eval_amt'] for s in final_stocks)
    time_module.sleep(0.2)

    final_usd = KIS.get_US_order_available()
    if final_usd is None:
        TA.send_tele("USQT: 최종 USD 주문가능금액 조회 불가로 종료합니다.")
        sys.exit(1)

    daily_data = {
        "date": str(order['date']),
        "total_stocks":    float(final_stock_eval),
        "total_cash":      float(final_usd),
        "total_asset":     float(final_stock_eval) + float(final_usd),
        "total_asset_ret": 0.0,
        "currency":        "USD"
    }

    # category별 자산
    for category, stocks_list in result.items():
        category_balance = sum(float(item['balance']) for item in stocks_list)
        daily_data[category]          = float(category_balance)
        daily_data[f"{category}_ret"] = 0.0

    # USQT_daily.json 저장
    try:
        json_message = save_json(daily_data, USQT_daily_path, order)
        message.extend(json_message)
    except Exception as e:
        error_msg = f"USQT_daily.json 저장 실패: {e}"
        TA.send_tele(error_msg)
    time_module.sleep(1.0)

    # data 정제 (표시용)
    daily = {
        "date": daily_data["date"],
        "total_stocks":    f"${daily_data['total_stocks']:,.2f}",
        "total_cash":      f"${daily_data['total_cash']:,.2f}",
        "total_asset":     f"${daily_data['total_asset']:,.2f}",
        "total_asset_ret": f"{float(daily_data['total_asset_ret']*100):.2f}%"
    }

    for category, stocks_list in result.items():
        category_balance = sum(float(item['balance']) for item in stocks_list)
        daily[category]          = f"${category_balance:,.2f}"
        daily[f"{category}_ret"] = "0.00%"

    """
    # daily balance Google Sheet 저장 보류
    try:
        credentials_file = "/var/autobot/gspread/service_account.json"
        spreadsheet_name = "2026_USQT_daily"

        spreadsheet = GU.connect_google_sheets(credentials_file, spreadsheet_name)
        current_month = datetime.now().month

        GU.save_to_sheets(spreadsheet, daily, current_month)
        message.append(f"2026_USQT_daily Google Sheet 업로드 완료")

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
