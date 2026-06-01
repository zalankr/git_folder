"""
JP_Hedge_TR.py
일본 시장 헷지 매월 리밸런싱 (단독 실행)

운영 시나리오:
- 매월 1~7일 KST 09:07 (UTC 00:07) ~ 매매시간까지 crontab으로 호출
- 1회차 시작에서 순차 검사:
  (1) "오늘 JPQT 분기 리밸런싱일?" → JPQT_TR.py가 처리 중이면 종료
  (2) "월 첫 거래일?" → 아니면 종료
  (3) 신호 산출 후 "이전 상태와 동일?" → 동일하면 매매 없이 종료 (정기 점검만)
  (4) 상태 전환 발생 → csv 개별주 + 헷지 ETF 통합 target 산출 → 7회차 매매

상태 전환 시 매매 (헷지 전략의 핵심 의도):
- Bull(80/20/0) → Neutral(50/30/20) : 개별주 축소(80→50%) + 금↑ + 채권 신규
- Bull(80/20/0) → Bear(0/60/40)     : 개별주 전량매도 + 금 대폭증액 + 채권 신규
- Neutral → Bull : 개별주 증액 + 금 감액 + 채권 매도
- Neutral → Bear : 개별주 전량매도 + 금 증액 + 채권 증액
- Bear → Neutral / Bull : 개별주 신규/증액 + 헷지 일부 매도

회차: 7회차 × 1일 (상태 전환 발생 시에만)
"""

import sys
import json
import os
import telegram_alert as TA
from datetime import datetime, timezone
import pandas as pd
from collections import defaultdict
import time as time_module
from tendo import singleton
import KIS_JP
import JP_Hedge_signal as HS

try:
    me = singleton.SingleInstance()
except singleton.SingleInstanceException:
    TA.send_tele("JP_Hedge: 이미 실행 중입니다.")
    sys.exit(0)

# ============================================
# KIS instance
# ============================================
key_file_path   = "/var/autobot/KIS/kis63604155nkr.txt"
token_file_path = "/var/autobot/KIS/kis63604155_token.json"
cano = "63604155"
acnt_prdt_cd = "01"
KIS = KIS_JP.KIS_API(key_file_path, token_file_path, cano, acnt_prdt_cd)

fee_rate = KIS.SELL_FEE_RATE

JPQT_target_path     = "/var/autobot/TR_JPQT/JPQT_target.json"  # JPQT 회피 검사용
JPQT_stock_path      = "/var/autobot/TR_JPQT/JPQT_stock.csv"
JP_Hedge_target_path = "/var/autobot/TR_JPQT/JP_Hedge_target.json"
JP_Hedge_state_path  = "/var/autobot/TR_JPQT/JP_Hedge_state.json"
JP_Hedge_result_path = "/var/autobot/TR_JPQT/JP_Hedge_result.json"
JP_Hedge_rebal_path  = "/var/autobot/TR_JPQT/JP_Hedge_rebal.json"

HEDGE_GOLD = HS.HEDGE_GOLD_TICKER  # 1328
HEDGE_BOND = HS.HEDGE_BOND_TICKER  # 1482
HEDGE_TICKERS = {HEDGE_GOLD, HEDGE_BOND}


# ============================================
# 유틸리티
# ============================================

def order_time_1day():
    """1일 7회차 매매 회차 결정"""
    now = datetime.now(timezone.utc)
    current_date = now.date()
    current_time = now.time()

    result = {
        'date': current_date,
        'time': current_time,
        'round': 0,
        'total_round': 7
    }

    hour = current_time.hour
    minute = current_time.minute

    base_round = 0
    if 0 <= minute <= 15:
        am_map = {0: 1, 1: 2, 2: 3}
        base_round = am_map.get(hour, 0)
        if hour == 4:
            base_round = 5
    elif 30 <= minute <= 45:
        pm_map = {3: 4, 4: 6, 5: 7}
        base_round = pm_map.get(hour, 0)

    result['round'] = base_round
    return result


def health_check():
    checks = []
    if not KIS.access_token:
        checks.append("JP_Hedge체크: API 토큰 없음")
    if not os.path.exists(JPQT_stock_path):
        checks.append(f"JP_Hedge체크: csv 없음: {JPQT_stock_path}")
    try:
        import socket
        socket.create_connection(("openapi.koreainvestment.com", 9443), timeout=5)
    except Exception:
        checks.append("JP_Hedge체크: KIS API 서버 접속 불가")
    if checks:
        TA.send_tele("\n".join(checks))
        sys.exit(1)


def save_json(data, path, order):
    msgs = []
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        msgs.append(f"{order['date']} {order['round']}/{order['total_round']}회차 저장: {path}")
    except Exception as e:
        msgs.append(f"{path} 저장 실패: {e}")
        backup_path = f"/var/autobot/TR_JPQT/backup_hedge_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            msgs.append(f"백업: {backup_path}")
        except Exception as be:
            msgs.append(f"백업 실패: {be}")
    return msgs


def split_data(round_num):
    """1일 7회차용 분할"""
    table = {
        1: (5, [1.0100, 1.0075, 1.0050, 1.0025, 0.9950], 5, [0.9875, 0.9900, 0.9925, 0.9950, 0.9975]),
        2: (4, [1.0100, 1.0075, 1.0050, 1.0025],         5, [0.9900, 0.9925, 0.9950, 0.9975, 1.0000]),
        3: (4, [1.0100, 1.0075, 1.0050, 1.0025],         4, [0.9900, 0.9925, 0.9950, 0.9975]),
        4: (4, [1.0075, 1.0050, 1.0025, 1.0000],         4, [0.9900, 0.9925, 0.9950, 0.9975]),
        5: (3, [1.0075, 1.0050, 1.0025],                  4, [0.9925, 0.9950, 0.9975, 1.0000]),
        6: (3, [1.0075, 1.0050, 1.0025],                  3, [0.9925, 0.9950, 0.9975]),
        7: (3, [1.0050, 1.0025, 1.0000],                  3, [0.9925, 0.9950, 0.9975]),
    }
    if round_num not in table:
        TA.send_tele(f"JP_Hedge: 유효하지 않은 round: {round_num}")
        sys.exit(1)
    s_n, s_p, b_n, b_p = table[round_num]
    return {"sell_splits": s_n, "sell_price": s_p, "buy_splits": b_n, "buy_price": b_p}


def cancel_orders():
    try:
        summary, _ = KIS.cancel_all_unfilled_orders()
        return f"JP_Hedge: {summary['success']}/{summary['total']} 취소 성공", summary
    except Exception as e:
        return f"JP_Hedge: 취소 에러 ({e})", {"success": 0, "total": 0, "fail": 0}


def is_JP_trading_day():
    try:
        import exchange_calendars as xcals
        import pytz
        cal = xcals.get_calendar("XTKS")
        jst = pytz.timezone('Asia/Tokyo')
        today_jst = datetime.now(timezone.utc).astimezone(jst).date()
        return cal.is_session(pd.Timestamp(today_jst))
    except Exception:
        try:
            import pytz
            jst = pytz.timezone('Asia/Tokyo')
            weekday = datetime.now(timezone.utc).astimezone(jst).weekday()
        except ImportError:
            weekday = datetime.utcnow().weekday()
        return weekday < 5


def is_first_trading_day_of_month():
    try:
        import exchange_calendars as xcals
        import pytz
        cal = xcals.get_calendar("XTKS")
        jst = pytz.timezone('Asia/Tokyo')
        today_jst = datetime.now(timezone.utc).astimezone(jst).date()
        if not cal.is_session(pd.Timestamp(today_jst)):
            return False
        month_start = today_jst.replace(day=1)
        sessions = cal.sessions_in_range(pd.Timestamp(month_start), pd.Timestamp(today_jst))
        if len(sessions) > 0 and sessions[0].date() == today_jst:
            return True
        return False
    except Exception:
        try:
            import pytz
            jst = pytz.timezone('Asia/Tokyo')
            today_jst = datetime.now(timezone.utc).astimezone(jst).date()
        except ImportError:
            today_jst = datetime.utcnow().date()
        return today_jst.day <= 7 and today_jst.weekday() < 5


def jpqt_is_active_today(today_date) -> bool:
    """오늘 JPQT_TR.py가 분기 리밸런싱 처리 중인지 확인"""
    if not os.path.exists(JPQT_target_path):
        return False
    try:
        with open(JPQT_target_path, 'r', encoding='utf-8') as f:
            jpqt_target = json.load(f)
        target_date = jpqt_target.get('_meta', {}).get('date', '')
        return target_date == str(today_date)
    except Exception:
        return False


def load_hedge_state():
    if not os.path.exists(JP_Hedge_state_path):
        return {}
    try:
        with open(JP_Hedge_state_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        TA.send_tele(f"JP_Hedge_state 로드 실패: {e}")
        return {}


def save_hedge_state(state_data):
    try:
        with open(JP_Hedge_state_path, 'w', encoding='utf-8') as f:
            json.dump(state_data, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        TA.send_tele(f"JP_Hedge_state 저장 실패: {e}")
        return False


def is_hedge_ticker(t):
    return t in HEDGE_TICKERS


def unit_size(ticker):
    """매매 단위: 헷지 ETF는 1주, 개별주는 100주"""
    return 1 if is_hedge_ticker(ticker) else 100


# ============================================
# 메인 로직
# ============================================

if not is_JP_trading_day():
    TA.send_tele("JP_Hedge: 일본 거래일 아님 → 종료")
    sys.exit(0)

health_check()
message = []

order = order_time_1day()

if order['round'] == 0:
    TA.send_tele("JP_Hedge: 매매시간 아님 → 종료")
    sys.exit(0)

is_first_round = (order['round'] == 1)

# (0) 모든 회차 공통: 오늘 JPQT가 헷지를 통합 처리 중이면 전 회차 양보
if jpqt_is_active_today(order['date']):
    TA.send_tele(
        f"JP_Hedge: 오늘({order['date']}) JPQT 분기 리밸런싱과 겹침 "
        f"→ JPQT_TR.py가 헷지 통합 처리 중. {order['round']}회차 종료."
    )
    sys.exit(0)

if is_first_round:
    # (2) 월 첫 거래일이 아니면 종료
    if not is_first_trading_day_of_month():
        TA.send_tele(f"JP_Hedge: {order['date']}은 월 첫 거래일 아님 → 종료")
        sys.exit(0)

    # 이번 달 이미 점검 완료 확인 (7일 윈도우 중복 실행 방지)
    prev_check = load_hedge_state().get('last_check_month', '')
    if prev_check == str(order['date'])[:7]:
        TA.send_tele(f"JP_Hedge: {order['date']} - 이번 달({prev_check}) 이미 점검 완료 → 종료")
        sys.exit(0)

    message.append(f"JP_Hedge: 월 첫 거래일 - {order['round']}/{order['total_round']}회차 시작")

    # ----------------------------------------
    # (3) 신호 산출
    # ----------------------------------------
    signal = HS.compute_signal(KIS, HS.TOPIX_TICKER)
    if signal is None:
        TA.send_tele("JP_Hedge: 신호 산출 실패 → 매매 중단")
        sys.exit(1)

    state = signal['state']
    weights = signal['weights']

    prev_state_data = load_hedge_state()
    prev_state = prev_state_data.get('current_state')
    message.append(HS.format_signal_message(signal, prev_state=prev_state))

    # ----------------------------------------
    # (4) 상태 전환 여부 검사
    # ----------------------------------------
    state_changed = (prev_state != state)

    # 신호 이력은 매월 저장 (매매 여부와 무관)
    new_state_data = {
        "last_signal_date":  signal['date'],
        "last_check_month":  str(order['date'])[:7],   # ← 추가 (예: "2026-06")
        "last_rebal_date":   str(order['date']) if state_changed else prev_state_data.get('last_rebal_date'),
        "current_state":     state,
        "previous_state":    prev_state,
        "weights":           weights,
        "signal_detail": {
            "close": signal['close'],
            "ma200": signal['ma200'],
            "mom12": signal['mom12'],
            "signal_ma":  signal['signal_ma'],
            "signal_mom": signal['signal_mom'],
        },
        "history": (prev_state_data.get('history', []) + [{
            "date":  signal['date'],
            "state": state,
            "ma200": signal['signal_ma'],
            "mom12": signal['signal_mom'],
            "trigger": "monthly_check",
            "rebalanced": state_changed
        }])[-24:]
    }
    save_hedge_state(new_state_data)

    if not state_changed:
        msg = (
            f"JP_Hedge: 상태 유지({state}) → 매매 없이 종료\n"
            f"  비중 유지: 주식 {weights['stock']*100:.0f}% / "
            f"금 {weights['gold']*100:.0f}% / 채권 {weights['bond']*100:.0f}%"
        )
        message.append(msg)
        TA.send_tele(message)
        sys.exit(0)

    message.append(
        f"⚡ 상태 전환 감지: {prev_state} → {state} "
        f"(주식 {prev_state_data.get('weights', {}).get('stock', 0)*100:.0f}% "
        f"→ {weights['stock']*100:.0f}%)"
    )

    # ----------------------------------------
    # (5) csv 로드 (개별주 비중 산출용)
    # ----------------------------------------
    try:
        with open(JPQT_stock_path, 'r', encoding='utf-8') as f:
            Target_df = pd.read_csv(f, dtype={
                "code": str, "name": str, "weight": float, "category": str
            })
    except Exception as e:
        TA.send_tele(f"JPQT_stock.csv 파일 오류: {e}")
        sys.exit(1)

    grouped = Target_df.groupby("code").agg(
        name=("name", "first"),
        weight=("weight", "sum"),
        categories=("category", list)
    ).reset_index()

    csv_stocks = {}
    for _, row in grouped.iterrows():
        code = str(row["code"])
        if code == "CASH":
            continue
        if code in HEDGE_TICKERS:
            message.append(f"JP_Hedge 경고: csv에 헷지 ETF({code}) 발견 → 자동 제외")
            continue
        csv_stocks[code] = {
            "name":       str(row["name"]),
            "weight":     float(row["weight"]),
            "categories": [str(c) for c in row["categories"]],
        }

    csv_weight_sum = sum(v['weight'] for v in csv_stocks.values())
    if csv_weight_sum <= 0:
        TA.send_tele("JP_Hedge: csv weight 합 0 이하 → 종료")
        sys.exit(1)
    for code in csv_stocks:
        csv_stocks[code]['weight'] = csv_stocks[code]['weight'] / csv_weight_sum

    message.append(f"JP_Hedge csv: {len(csv_stocks)}개 종목 (정규화 합=1.0)")

    # ----------------------------------------
    # (6) 총자산 산출
    # ----------------------------------------
    stocks_list = KIS.get_JP_stock_balance()
    if not isinstance(stocks_list, list):
        TA.send_tele(f"JP_Hedge: 잔고 조회 불가 ({stocks_list})")
        sys.exit(1)
    stock_eval_jpy = sum(s['eval_amt'] for s in stocks_list)
    time_module.sleep(0.2)

    orderable_jpy = KIS.get_JP_order_available()
    if orderable_jpy is None:
        TA.send_tele("JP_Hedge: JPY 주문가능금액 조회 불가")
        sys.exit(1)

    total_jpy_asset = stock_eval_jpy + orderable_jpy
    message.append(
        f"JP_Hedge 총자산: ¥{total_jpy_asset:,.0f} "
        f"(주식:¥{stock_eval_jpy:,.0f} + 현금:¥{orderable_jpy:,.0f})"
    )

    # ----------------------------------------
    # (7) 통합 target 구성: csv 개별주 (× stock_ratio) + 헷지 ETF
    # ----------------------------------------
    stock_ratio = weights['stock']
    target = {}

    # csv 개별주
    for code, info in csv_stocks.items():
        target[code] = {
            "name":       info['name'],
            "weight":     info['weight'] * stock_ratio,
            "categories": info['categories'],
        }

    # 헷지 ETF (weight=0이라도 target에 포함 → 매도 가능)
    target[HEDGE_GOLD] = {
        "name":       HS.HEDGE_GOLD_NAME,
        "weight":     float(weights['gold']),
        "categories": ["hedge_gold"]
    }
    target[HEDGE_BOND] = {
        "name":       HS.HEDGE_BOND_NAME,
        "weight":     float(weights['bond']),
        "categories": ["hedge_bond"]
    }

    target_code = list(target.keys())
    total_weight = sum(v['weight'] for v in target.values())
    if abs(total_weight - 1.0) > 0.01:
        message.append(f"JP_Hedge 경고: 최종 weight 합 = {total_weight:.3f}")
    else:
        message.append(
            f"JP_Hedge 비중: 주식 {stock_ratio*100:.0f}% / "
            f"금 {weights['gold']*100:.0f}% / 채권 {weights['bond']*100:.0f}% (합={total_weight:.4f})"
        )

    # ----------------------------------------
    # (8) 현재가 + 목표 수량
    # ----------------------------------------
    for ticker in target_code:
        price = KIS.get_JP_current_price(ticker)
        if not isinstance(price, float) or price <= 0:
            TA.send_tele(f"JP_Hedge: {ticker} 현재가 조회 불가 ({price})")
            sys.exit(1)

        target[ticker]['current_price'] = price
        target[ticker]['target_invest'] = float(target[ticker]['weight'] * total_jpy_asset)

        unit = unit_size(ticker)
        if target[ticker]['target_invest'] <= 0:
            new_target_qty = 0
        else:
            raw_qty = int(target[ticker]['target_invest'] / price)
            new_target_qty = (raw_qty // unit) * unit

        target[ticker]['target_qty'] = new_target_qty
        time_module.sleep(0.15)

    # ----------------------------------------
    # (9) target 저장
    # ----------------------------------------
    target_serializable = {}
    for k, v in target.items():
        target_serializable[k] = {
            key: (float(val) if isinstance(val, float) else
                  int(val) if isinstance(val, int) and not isinstance(val, bool) else
                  val)
            for key, val in v.items()
        }
    target_serializable["_meta"] = {
        "date":             str(order['date']),
        "state":            state,
        "previous_state":   prev_state,
        "stock_ratio":      float(stock_ratio),
        "gold_ratio":       float(weights['gold']),
        "bond_ratio":       float(weights['bond']),
        "total_asset_jpy":  float(total_jpy_asset),
        "trigger":          "state_change"
    }
    save_msgs = save_json(target_serializable, JP_Hedge_target_path, order)
    message.extend(save_msgs)

    # 주요 target 표시
    for hticker in [HEDGE_GOLD, HEDGE_BOND]:
        ht = target[hticker]
        message.append(
            f"JP_Hedge [Hedge] {hticker}({ht['name']}): "
            f"{ht['target_qty']}주 × ¥{ht['current_price']:,.0f} "
            f"= ¥{ht['target_invest']:,.0f} ({ht['weight']*100:.0f}%)"
        )

else:
    # 2~7회차: target 로드 + 일자 검증
    if not os.path.exists(JP_Hedge_target_path):
        TA.send_tele("JP_Hedge: target 파일 없음 (오늘 헷지 매매일 아님) → 종료")
        sys.exit(0)
    try:
        with open(JP_Hedge_target_path, 'r', encoding='utf-8') as f:
            target = json.load(f)
        target_date = target.get('_meta', {}).get('date', '')
        if target_date != str(order['date']):
            TA.send_tele(
                f"JP_Hedge: target 일자({target_date}) ≠ 오늘({order['date']}) → 종료"
            )
            sys.exit(0)
    except Exception as e:
        TA.send_tele(f"JP_Hedge target.json 로드 오류: {e}")
        sys.exit(1)
    message.append(f"JP_Hedge: {order['round']}/{order['total_round']}회차 매매")

target_code = [t for t in target.keys() if t != "_meta"]


# ============================================
# 전회 미체결 취소
# ============================================
cancel_message, _ = cancel_orders()
message.append(cancel_message)
time_module.sleep(3)

MAX_CANCEL_RETRY = 3
for retry_i in range(MAX_CANCEL_RETRY):
    try:
        remaining = KIS.get_unfilled_orders()
    except Exception as e:
        message.append(f"JP_Hedge 미체결 조회 에러: {e}")
        remaining = []
    if isinstance(remaining, list) and len(remaining) == 0:
        if retry_i > 0:
            message.append(f"JP_Hedge 미체결 0건 (재시도 {retry_i}회 후)")
        break
    n_remain = len(remaining) if isinstance(remaining, list) else '?'
    message.append(f"JP_Hedge 미체결 {n_remain}건 → 추가 취소 {retry_i+1}/{MAX_CANCEL_RETRY}")
    retry_msg, retry_summary = cancel_orders()
    message.append(retry_msg)
    time_module.sleep(3)
    if retry_i == MAX_CANCEL_RETRY - 1 and retry_summary.get('success', 0) == 0:
        message.append("JP_Hedge 경고: 취소 실패 상태로 매매 진행")


# ============================================
# 보유 종목 잔고 (전체)
# ============================================
stocks = KIS.get_JP_stock_balance()
if not isinstance(stocks, list):
    TA.send_tele(f"JP_Hedge: 잔고 조회 불가 ({stocks})")
    sys.exit(1)

hold = {}
for stock in stocks:
    ticker = stock["ticker"]
    hold[ticker] = {
        "name":          stock["name"],
        "hold_balance":  stock["eval_amt"],
        "hold_qty":      stock["quantity"],
        "ord_psbl_qty":  stock.get("ord_psbl_qty") or stock["quantity"],
        "current_price": stock["current_price"],
        "exchange":      stock["exchange"],
    }
hold_code = list(hold.keys())


# ============================================
# 매수/매도 산출
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
            sell_qty = min(need_sell, hold[ticker]["ord_psbl_qty"])
            if sell_qty > 0:
                sell[ticker] = sell_qty
            else:
                message.append(
                    f"JP_Hedge 매도스킵: {ticker} 필요{need_sell}주, "
                    f"가능{hold[ticker]['ord_psbl_qty']}주"
                )
    else:
        # target에 없는 보유 종목 → 전량 매도
        sell_qty = min(hold[ticker]["hold_qty"], hold[ticker]["ord_psbl_qty"])
        if sell_qty > 0:
            sell[ticker] = sell_qty
        else:
            message.append(f"JP_Hedge 매도스킵: {ticker} 가능수량 0주")

for ticker in target_code:
    if ticker == "CASH":
        continue
    if ticker not in hold_code:
        if target[ticker]["target_qty"] > 0:
            buy[ticker] = target[ticker]["target_qty"]

# 매매 단위 보정
def floor_unit(t, q):
    u = unit_size(t)
    return (q // u) * u

buy  = {t: floor_unit(t, q) for t, q in buy.items()  if floor_unit(t, q) > 0}
sell = {t: floor_unit(t, q) for t, q in sell.items() if floor_unit(t, q) > 0}


# ============================================
# 분할 주문
# ============================================
round_split = split_data(order['round'])
sell_split = [round_split["sell_splits"], round_split["sell_price"]]
buy_split  = [round_split["buy_splits"],  round_split["buy_price"]]


# ============================================
# 매도 주문
# ============================================
sell_code = list(sell.keys())
if len(sell_code) == 0:
    message.append("JP_Hedge: 매도 종목 없음")
elif sell_split[0] > 0:
    message.append(f"JP_Hedge: {order['round']}회차 - 매도 주문")
    for ticker, qty in sell.items():
        unit = unit_size(ticker)
        local_split_count = sell_split[0]
        local_split_price = sell_split[1][:]
        split_qty = (int(qty // local_split_count) // unit) * unit

        if split_qty < unit:
            local_split_count = 1
            local_split_price = [0.99]
            split_qty = (int(qty) // unit) * unit

        if split_qty < unit:
            message.append(f"JP_Hedge 매도 스킵: {ticker} 수량 {qty}주 ({unit}주 미만)")
            continue

        price = KIS.get_JP_current_price(ticker)
        if not isinstance(price, float) or price <= 0:
            TA.send_tele(f"JP_Hedge: {ticker} 현재가 조회 불가 ({price})")
            sys.exit(1)

        for i in range(local_split_count):
            if i == local_split_count - 1:
                quantity = int(qty - split_qty * (local_split_count - 1))
                quantity = (quantity // unit) * unit
            else:
                quantity = split_qty
            if quantity < unit:
                continue

            order_price = int(round(price * local_split_price[i], 0))
            order_info, order_msgs = KIS.order_sell_JP(ticker, quantity, order_price)
            if order_info is None:
                time_module.sleep(2)
                order_info, order_msgs = KIS.order_sell_JP(ticker, quantity, order_price)
            if order_info is None:
                message.append(f"JP_Hedge 매도 오류: {ticker} {quantity}주 ¥{order_price:,} API 응답 없음")
            elif order_info.get("success"):
                tag = "[H]" if is_hedge_ticker(ticker) else ""
                message.append(
                    f"매도{tag} {ticker} {quantity}주 ¥{order_price:,} "
                    f"주문번호:{order_info.get('order_number','')}"
                )
            else:
                message.append(
                    f"매도 실패 {ticker} {quantity}주: {order_info.get('error_message','')}"
                )
            message.extend(order_msgs)
            time_module.sleep(0.2)
else:
    message.append(f"JP_Hedge: {order['round']}회차 매도 스킵 - 미처분: {list(sell.keys())}")

TA.send_tele(message)
message = []

# ============================================
# 매도-매수 딜레이
# ============================================
time_module.sleep(600)

# ============================================
# 매수 구간
# ============================================
JPY = KIS.get_JP_order_available()
if JPY is None:
    TA.send_tele("JP_Hedge: JPY 주문가능금액 조회 불가")
    sys.exit(1)

orderable_JPY = float(JPY)
target_JPY = 0.0
buy_prices = {}
buy_price_rate = buy_split[1][-1] if buy_split[1] else 1.0

for ticker, qty in buy.items():
    price = KIS.get_JP_current_price(ticker)
    if not isinstance(price, float) or price <= 0:
        TA.send_tele(f"JP_Hedge: {ticker} 가격 조회 불가 ({price})")
        sys.exit(1)
    buy_prices[ticker] = price
    target_JPY += price * buy_price_rate * qty
    time_module.sleep(0.15)

message.append(
    f"JP_Hedge 매수가능: ¥{orderable_JPY:,.0f} | 목표매수금: ¥{target_JPY:,.0f}"
    + (f" | 조정: {orderable_JPY/target_JPY:.4f}" if target_JPY > 0 else "")
)

if target_JPY > orderable_JPY and target_JPY > 0:
    adjust_rate = orderable_JPY / target_JPY
    for ticker, ticker_qty in buy.items():
        unit = unit_size(ticker)
        adjusted = int(ticker_qty * adjust_rate)
        adjusted = (adjusted // unit) * unit
        buy[ticker] = adjusted
    buy = {t: q for t, q in buy.items() if q >= unit_size(t)}
    message.append(f"JP_Hedge 매수수량 조정 (rate={adjust_rate:.4f})")
else:
    message.append("JP_Hedge 매수가능금 충분")

buy = {t: q for t, q in buy.items() if q >= unit_size(t)}
buy_code = list(buy.keys())

if len(buy_code) == 0:
    message.append("JP_Hedge: 매수 종목 없음")
elif buy_split[0] > 0:
    message.append(f"JP_Hedge: {order['round']}회차 - 매수 주문")
    for ticker, qty in buy.items():
        unit = unit_size(ticker)
        local_split_count = buy_split[0]
        local_split_price = buy_split[1][:]
        split_qty = (int(qty // local_split_count) // unit) * unit

        if split_qty < unit:
            if qty < unit:
                message.append(f"JP_Hedge 매수 스킵: {ticker} 수량 {qty}주 ({unit}주 미만)")
                continue
            local_split_count = 1
            local_split_price = [1.01]
            split_qty = (int(qty) // unit) * unit

        price = buy_prices.get(ticker)
        if not isinstance(price, float) or price <= 0:
            TA.send_tele(f"JP_Hedge: {ticker} 현재가 없음")
            sys.exit(1)

        for i in range(local_split_count):
            if i == local_split_count - 1:
                quantity = int(qty - split_qty * (local_split_count - 1))
                quantity = (quantity // unit) * unit
            else:
                quantity = split_qty
            if quantity < unit:
                continue

            order_price = int(round(price * local_split_price[i], 0))
            order_info, order_msgs = KIS.order_buy_JP(ticker, quantity, order_price)
            if order_info is None:
                time_module.sleep(2)
                order_info, order_msgs = KIS.order_buy_JP(ticker, quantity, order_price)
            if order_info is None:
                message.append(f"JP_Hedge 매수 오류: {ticker} {quantity}주 ¥{order_price:,} API 응답 없음")
            elif order_info.get("success"):
                tag = "[H]" if is_hedge_ticker(ticker) else ""
                message.append(
                    f"매수{tag} {ticker} {quantity}주 ¥{order_price:,} "
                    f"주문번호:{order_info.get('order_number','')}"
                )
            else:
                message.append(
                    f"매수 실패 {ticker} {quantity}주 ¥{order_price:,}: "
                    f"{order_info.get('error_message','')}"
                )
            message.extend(order_msgs)
            time_module.sleep(0.2)

TA.send_tele(message)
message = []


# ============================================
# 7회차 종료: 최종 정리
# ============================================
if order['round'] == 7:
    time_module.sleep(120)
    cancel_message, _ = cancel_orders()
    message.append(cancel_message)
    message.append(f"JP_Hedge {order['date']} 헷지 리밸런싱 종료")

    # 최종 잔고
    final_stocks = KIS.get_JP_stock_balance()
    if not isinstance(final_stocks, list):
        TA.send_tele(f"JP_Hedge: 최종 잔고 조회 불가 ({final_stocks})")
        sys.exit(1)
    final_stock_eval = sum(s['eval_amt'] for s in final_stocks)
    time_module.sleep(0.2)

    final_jpy = KIS.get_JP_order_available()
    if final_jpy is None:
        TA.send_tele("JP_Hedge: 최종 JPY 주문가능금액 조회 불가")
        sys.exit(1)

    hedge_holdings = {}
    for s in final_stocks:
        if s['ticker'] in HEDGE_TICKERS:
            hedge_holdings[s['ticker']] = {
                "name":    s['name'],
                "qty":     s['quantity'],
                "balance": s['eval_amt'],
            }

    state_data = load_hedge_state()

    result = {
        "date":         str(order['date']),
        "state":        state_data.get('current_state', 'N/A'),
        "previous_state": state_data.get('previous_state', 'N/A'),
        "total_stocks": float(final_stock_eval),
        "total_cash":   float(final_jpy),
        "total_asset":  float(final_stock_eval) + float(final_jpy),
        "currency":     "JPY",
        "hedge_gold": {
            "code":    HEDGE_GOLD,
            "qty":     hedge_holdings.get(HEDGE_GOLD, {}).get('qty', 0),
            "balance": hedge_holdings.get(HEDGE_GOLD, {}).get('balance', 0),
            "weight":  state_data.get('weights', {}).get('gold', 0)
        },
        "hedge_bond": {
            "code":    HEDGE_BOND,
            "qty":     hedge_holdings.get(HEDGE_BOND, {}).get('qty', 0),
            "balance": hedge_holdings.get(HEDGE_BOND, {}).get('balance', 0),
            "weight":  state_data.get('weights', {}).get('bond', 0)
        }
    }

    json_message = save_json(result, JP_Hedge_result_path, order)
    message.extend(json_message)

    rebal_data = {
        "date":         str(order['date']),
        "state":        result['state'],
        "previous_state": result['previous_state'],
        "total_asset":  result['total_asset'],
        "total_stocks": result['total_stocks'],
        "total_cash":   result['total_cash'],
        "stock_ratio":  state_data.get('weights', {}).get('stock', 0),
        "gold_balance": result['hedge_gold']['balance'],
        "bond_balance": result['hedge_bond']['balance'],
        "gold_ratio":   state_data.get('weights', {}).get('gold', 0),
        "bond_ratio":   state_data.get('weights', {}).get('bond', 0),
        "currency":     "JPY"
    }
    json_message = save_json(rebal_data, JP_Hedge_rebal_path, order)
    message.extend(json_message)

    message.append(f"상태 전환: {result['previous_state']} → {result['state']}")
    message.append(f"총자산: ¥{result['total_asset']:,.0f}")
    message.append(f"주식평가: ¥{result['total_stocks']:,.0f}")
    message.append(f"현금: ¥{result['total_cash']:,.0f}")
    message.append(
        f"금({HEDGE_GOLD}): {result['hedge_gold']['qty']}주, "
        f"¥{result['hedge_gold']['balance']:,.0f} ({result['hedge_gold']['weight']*100:.0f}%)"
    )
    message.append(
        f"채권({HEDGE_BOND}): {result['hedge_bond']['qty']}주, "
        f"¥{result['hedge_bond']['balance']:,.0f} ({result['hedge_bond']['weight']*100:.0f}%)"
    )

    TA.send_tele(message)
    message = []

sys.exit(0)
