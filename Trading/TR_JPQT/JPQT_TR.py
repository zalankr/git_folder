"""
JPQT_TR.py
일본 주식 분기 리밸런싱 (JPQT 개별주) + 헷지 자동 통합 매매

운영 시나리오:
- 분기 월(3, 6, 9, 12) 중 사용자가 crontab으로 지정한 1일에 7회차 분할 매매
- 1회차 시작 시점에 항상 다음을 자동 처리:
  1) 헷지 신호 재산출 (TOPIX 200MA + 12M 모멘텀)
  2) state 갱신 → JP_Hedge_state.json 저장
  3) 만약 오늘이 동시에 "월 첫 거래일"이면 → 매월 헷지 매매도 이 스크립트가 통합 처리
  4) 월 첫 거래일이 아니어도 → 최신 신호를 stock_ratio에 반영하여 csv 종목 비중 축소
     (예: Bull stock_ratio=0.80, Bear 0.00)
  5) 헷지 ETF(금 1328, 채권 1482) target_qty도 자동 산출 → 통합 매매

비중 결합:
- csv 종목 weight (CASH 제외 후 정규화 합=1.0) × stock_ratio → 개별주 비중
- 헷지 ETF: 상태별 gold_ratio + bond_ratio 그대로

회차: 7회차 × 1일 (JPQT 매매일 == 헷지 매매일이면 통합, 아니면 JPQT만)
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
    TA.send_tele("JPQT: 이미 실행 중입니다.")
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

JPQT_target_path     = "/var/autobot/TR_JPQT/JPQT_target.json"
JPQT_result_path     = "/var/autobot/TR_JPQT/JPQT_result.json"
JPQT_rebal_path      = "/var/autobot/TR_JPQT/JPQT_rebal.json"
JPQT_stock_path      = "/var/autobot/TR_JPQT/JPQT_stock.csv"
JP_Hedge_state_path  = "/var/autobot/TR_JPQT/JP_Hedge_state.json"

# 헷지 ETF
HEDGE_GOLD = HS.HEDGE_GOLD_TICKER  # 1328
HEDGE_BOND = HS.HEDGE_BOND_TICKER  # 1482
HEDGE_TICKERS = {HEDGE_GOLD, HEDGE_BOND}


# ============================================
# 유틸리티
# ============================================

def order_time_1day():
    """
    1일 7회차 매매 회차 결정 (EC2 = UTC)
    오전장 KST 09:00~11:30 = UTC 00:00~02:30
    오후장 KST 12:30~15:00 = UTC 03:30~06:00
    """
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
    # 오전장: crontab 7분 실행 (UTC 00:07, 01:07, 02:07)
    if 0 <= minute <= 15:
        am_map = {0: 1, 1: 2, 2: 3}
        base_round = am_map.get(hour, 0)
        # UTC 04:07 = KST 13:07 (오후 정시 슬롯)
        if hour == 4:
            base_round = 5
    # 오후장: crontab 37분 실행 (UTC 03:37, 04:37, 05:37)
    elif 30 <= minute <= 45:
        pm_map = {3: 4, 4: 6, 5: 7}
        base_round = pm_map.get(hour, 0)

    result['round'] = base_round
    return result


def health_check():
    checks = []
    if not KIS.access_token:
        checks.append("JPQT체크: API 토큰 없음")

    if not os.path.exists(JPQT_stock_path):
        checks.append(f"JPQT체크: data파일 없음: {JPQT_stock_path}")

    try:
        import socket
        socket.create_connection(("openapi.koreainvestment.com", 9443), timeout=5)
    except Exception:
        checks.append("JPQT체크: KIS API 서버 접속 불가")

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
        backup_path = f"/var/autobot/TR_JPQT/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            msgs.append(f"백업: {backup_path}")
        except Exception as be:
            msgs.append(f"백업 실패: {be}")
    return msgs


def split_data(round_num):
    """1일 7회차 분할 데이터 (기존 1~7회차 그대로)"""
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
        TA.send_tele(f"JPQT: 유효하지 않은 round: {round_num}")
        sys.exit(1)
    s_n, s_p, b_n, b_p = table[round_num]
    return {"sell_splits": s_n, "sell_price": s_p, "buy_splits": b_n, "buy_price": b_p}


def cancel_orders():
    try:
        summary, _ = KIS.cancel_all_unfilled_orders()
        msg = f"JPQT: {summary['success']}/{summary['total']} 주문 취소 성공"
        if summary.get('failed', 0) > 0 and summary.get('failed_list'):
            err = summary['failed_list'][0].get('error', '')
            msg += f" | 실패사유: {err}"
        return msg, summary
    except Exception as e:
        return f"JPQT: 주문 취소 에러 ({e})", {"success": 0, "total": 0, "fail": 0}


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
    """오늘이 이번 달 첫 거래일인지 (JST 기준)"""
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
        return today_jst.day <= 5 and today_jst.weekday() < 5


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
    TA.send_tele("JPQT: 일본 거래일이 아닙니다.")
    sys.exit(0)

health_check()
message = []

order = order_time_1day()

if order['round'] == 0:
    TA.send_tele("JPQT: 매매시간이 아닙니다.")
    sys.exit(0)

message.append(f"JPQT: {order['round']}/{order['total_round']}회차 매매 시작")

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
        message.append(f"JPQT 미체결 조회 에러: {e}")
        remaining = []
    if isinstance(remaining, list) and len(remaining) == 0:
        if retry_i > 0:
            message.append(f"JPQT 미체결 0건 확인 (재시도 {retry_i}회 후)")
        break
    n_remain = len(remaining) if isinstance(remaining, list) else '?'
    message.append(f"JPQT 미체결 잔존 {n_remain}건 → 추가 취소 {retry_i+1}/{MAX_CANCEL_RETRY}")
    retry_msg, retry_summary = cancel_orders()
    message.append(retry_msg)
    time_module.sleep(3)
    if retry_i == MAX_CANCEL_RETRY - 1 and retry_summary.get('success', 0) == 0:
        message.append("JPQT 경고: 취소 실패 상태로 매매 진행")


# ============================================
# 1회차: target 재계산 + 헷지 신호 산출 + 통합
# ============================================
if order['round'] == 1:

    # ----------------------------------------
    # 1) CSV 로드 + 정규화
    # ----------------------------------------
    try:
        with open(JPQT_stock_path, 'r', encoding='utf-8') as f:
            Target_df = pd.read_csv(f, dtype={
                "code": str, "name": str, "weight": float, "category": str
            })
    except Exception as e:
        TA.send_tele(f"JPQT_stock.csv 파일 오류: {e}")
        sys.exit(1)

    # 중복 종목 비중 합산 (여러 카테고리에 동일 종목 가능)
    grouped = Target_df.groupby("code").agg(
        name=("name", "first"),
        weight=("weight", "sum"),
        categories=("category", list)
    ).reset_index()

    # csv 종목 추출: CASH 제외, 헷지 ETF가 csv에 잘못 들어가면 자동 제외
    csv_stocks = {}
    for _, row in grouped.iterrows():
        code = str(row["code"])
        if code == "CASH":
            continue
        if code in HEDGE_TICKERS:
            message.append(f"JPQT 경고: csv에 헷지 ETF({code}) 발견 → 자동 제외")
            continue
        csv_stocks[code] = {
            "name":       str(row["name"]),
            "weight":     float(row["weight"]),
            "categories": [str(c) for c in row["categories"]],
        }

    # csv weight 정규화 (CASH 제외 후 합=1.0)
    csv_weight_sum = sum(v['weight'] for v in csv_stocks.values())
    if csv_weight_sum <= 0:
        TA.send_tele("JPQT: csv 종목 weight 합이 0 이하 → 종료")
        sys.exit(1)
    for code in csv_stocks:
        csv_stocks[code]['weight'] = csv_stocks[code]['weight'] / csv_weight_sum

    message.append(f"JPQT csv: {len(csv_stocks)}개 종목 (weight 정규화 합=1.0)")

    # ----------------------------------------
    # 2) 헷지 신호 산출 (분기 리밸런싱일은 항상 최신 신호 사용)
    # ----------------------------------------
    is_first_td = is_first_trading_day_of_month()
    if is_first_td:
        message.append("JPQT: 오늘은 월 첫 거래일과 겹침 → 헷지 통합 매매 (월 정기 + 분기 리밸런싱)")
    else:
        message.append("JPQT: 분기 리밸런싱일 → 헷지 신호 재산출 후 통합 매매")

    signal = HS.compute_signal(KIS, HS.TOPIX_TICKER)
    if signal is None:
        TA.send_tele("JPQT: 헷지 신호 산출 실패 → 보수적 처리 (직전 상태 사용)")
        prev = load_hedge_state()
        if prev and 'current_state' in prev:
            state = prev['current_state']
            weights = prev['weights']
            stock_ratio = weights['stock']
            message.append(f"JPQT: 직전 상태({state}) 사용. stock_ratio={stock_ratio:.2f}")
        else:
            state = "Bull"
            weights = HS.WEIGHT_MATRIX["Bull"]
            stock_ratio = weights['stock']
            message.append("JPQT: 직전 상태 없음 → Bull(주식 80%)로 처리")
        signal_for_save = None
    else:
        state = signal['state']
        weights = signal['weights']
        stock_ratio = weights['stock']
        prev = load_hedge_state()
        prev_state = prev.get('current_state')
        message.append(HS.format_signal_message(signal, prev_state=prev_state))
        signal_for_save = signal

        # 헷지 상태 저장
        new_state_data = {
            "last_signal_date":  signal['date'],
            "last_rebal_date":   str(order['date']),
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
            "history": (prev.get('history', []) + [{
                "date":  signal['date'],
                "state": state,
                "ma200": signal['signal_ma'],
                "mom12": signal['signal_mom'],
                "trigger": "JPQT_quarterly"
            }])[-24:]
        }
        save_hedge_state(new_state_data)

    # ----------------------------------------
    # 3) 총자산 산출 (JPY)
    # ----------------------------------------
    stocks_list = KIS.get_JP_stock_balance()
    if not isinstance(stocks_list, list):
        TA.send_tele(f"JPQT: 잔고 조회 불가 ({stocks_list})")
        sys.exit(1)
    stock_eval_jpy = sum(s['eval_amt'] for s in stocks_list)
    time_module.sleep(0.2)

    orderable_jpy = KIS.get_JP_order_available()
    if orderable_jpy is None:
        TA.send_tele("JPQT: JPY 주문가능금액 조회 불가")
        sys.exit(1)

    total_jpy_asset = stock_eval_jpy + orderable_jpy
    message.append(
        f"JPQT 총자산: ¥{total_jpy_asset:,.0f} "
        f"(주식:¥{stock_eval_jpy:,.0f} + 현금:¥{orderable_jpy:,.0f})"
    )

    # ----------------------------------------
    # 4) target 구성: csv 종목 (× stock_ratio) + 헷지 ETF
    # ----------------------------------------
    target = {}

    # csv 개별주
    for code, info in csv_stocks.items():
        target[code] = {
            "name":       info['name'],
            "weight":     info['weight'] * stock_ratio,
            "categories": info['categories'],
        }

    # 헷지 ETF (weight=0이라도 target에 포함시켜 매도 가능 종목으로 등록)
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

    # weight 합 검증
    target_code = list(target.keys())
    total_weight = sum(v['weight'] for v in target.values())
    if abs(total_weight - 1.0) > 0.01:
        message.append(f"JPQT 경고: 최종 weight 합계 = {total_weight:.3f} (1.0 아님)")
    else:
        message.append(f"JPQT 비중 OK: 합계={total_weight:.4f} | "
                       f"주식={stock_ratio*100:.0f}% / 금={weights['gold']*100:.0f}% / 채권={weights['bond']*100:.0f}%")

    # ----------------------------------------
    # 5) 종목별 현재가 + 목표 수량
    # ----------------------------------------
    for ticker in target_code:
        price = KIS.get_JP_current_price(ticker)
        if not isinstance(price, float) or price <= 0:
            TA.send_tele(f"JPQT: {ticker} 현재가 조회 불가 ({price})")
            sys.exit(1)

        target[ticker]['current_price'] = price
        target[ticker]['target_invest'] = float(target[ticker]['weight'] * total_jpy_asset)

        # 매매 단위: 헷지 ETF는 1주, 개별주는 100주
        unit = unit_size(ticker)
        if target[ticker]['target_invest'] <= 0:
            new_target_qty = 0
        else:
            raw_qty = int(target[ticker]['target_invest'] / price)
            new_target_qty = (raw_qty // unit) * unit

        target[ticker]['target_qty'] = new_target_qty
        time_module.sleep(0.15)

    # ----------------------------------------
    # 6) target 저장
    # ----------------------------------------
    target_serializable = {}
    for k, v in target.items():
        target_serializable[k] = {
            key: (float(val) if isinstance(val, float) else
                  int(val) if isinstance(val, int) and not isinstance(val, bool) else
                  val)
            for key, val in v.items()
        }
    # 메타 정보
    target_serializable["_meta"] = {
        "date":             str(order['date']),
        "state":            state,
        "stock_ratio":      float(stock_ratio),
        "gold_ratio":       float(weights['gold']),
        "bond_ratio":       float(weights['bond']),
        "total_asset_jpy":  float(total_jpy_asset),
        "is_first_td":      bool(is_first_td)
    }
    json_message = save_json(target_serializable, JPQT_target_path, order)
    message.extend(json_message)

    # 헷지 ETF target 표시
    for hticker in [HEDGE_GOLD, HEDGE_BOND]:
        ht = target[hticker]
        message.append(
            f"JPQT [Hedge] {hticker}({ht['name']}): "
            f"{ht['target_qty']}주 × ¥{ht['current_price']:,.0f} "
            f"= ¥{ht['target_invest']:,.0f} ({ht['weight']*100:.0f}%)"
        )

else:
    # 2~7회차: target 파일 로드
    try:
        with open(JPQT_target_path, 'r', encoding='utf-8') as f:
            target = json.load(f)
    except Exception as e:
        TA.send_tele(f"JPQT_target.json 파일 오류: {e}")
        sys.exit(1)

    # ✅ 추가: _meta 키 자체가 없는 구버전/손상 파일 차단
    if "_meta" not in target:
        TA.send_tele(
            f"JPQT 경고: target에 _meta 없음 (구버전 잔존 파일 가능성). "
            f"1회차 미생성 상태로 판단 → 매매 중단."
        )
        sys.exit(1)

    # 메타 검증
    target_date = target.get('_meta', {}).get('date', '')
    if target_date != str(order['date']):
        TA.send_tele(
            f"JPQT 경고: target 일자({target_date}) ≠ 오늘({order['date']}). "
            f"전일 잔존 target일 가능성. 매매 중단."
        )
        sys.exit(1)

target_code = [k for k in target.keys() if k != "_meta"]


# ============================================
# 보유 종목 잔고
# ============================================
stocks = KIS.get_JP_stock_balance()
if not isinstance(stocks, list):
    TA.send_tele(f"JPQT: 잔고 조회 불가 ({stocks})")
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
# 매수/매도 수량 산출
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
                    f"JPQT 매도스킵: {ticker} 필요{need_sell}주, 가능{hold[ticker]['ord_psbl_qty']}주"
                )
    else:
        # target에 없는 보유 종목 → 전량 매도
        sell_qty = min(hold[ticker]["hold_qty"], hold[ticker]["ord_psbl_qty"])
        if sell_qty > 0:
            sell[ticker] = sell_qty
        else:
            message.append(f"JPQT 매도스킵: {ticker} 가능수량 0주")

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
# 분할 주문 데이터
# ============================================
round_split = split_data(order['round'])
sell_split = [round_split["sell_splits"], round_split["sell_price"]]
buy_split  = [round_split["buy_splits"],  round_split["buy_price"]]


# ============================================
# 매도 주문
# ============================================
sell_code = list(sell.keys())

if len(sell_code) == 0:
    message.append("JPQT: 매도 종목 없음")
elif sell_split[0] > 0:
    message.append(f"JPQT: {order['round']}회차 - 매도 주문")
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
            message.append(f"JPQT 매도 스킵: {ticker} 수량 {qty}주 ({unit}주 미만)")
            continue

        price = KIS.get_JP_current_price(ticker)
        if not isinstance(price, float) or price <= 0:
            TA.send_tele(f"JPQT: {ticker} 현재가 조회 불가 ({price})")
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
                message.append(f"JPQT 매도 오류: {ticker} {quantity}주 ¥{order_price:,} API 응답 없음")
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
    message.append(f"JPQT: {order['round']}회차 매도 스킵 - 미처분: {list(sell.keys())}")

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
    TA.send_tele("JPQT: JPY 주문가능금액 조회 불가")
    sys.exit(1)

orderable_JPY = float(JPY)
target_JPY = 0.0
buy_prices = {}
buy_price_rate = buy_split[1][-1] if buy_split[1] else 1.0

for ticker, qty in buy.items():
    price = KIS.get_JP_current_price(ticker)
    if not isinstance(price, float) or price <= 0:
        TA.send_tele(f"JPQT: {ticker} 현재가 조회 불가 ({price})")
        sys.exit(1)
    buy_prices[ticker] = price
    target_JPY += price * buy_price_rate * qty
    time_module.sleep(0.15)

message.append(
    f"JPQT 매수가능: ¥{orderable_JPY:,.0f} | 목표매수금: ¥{target_JPY:,.0f}"
    + (f" | 조정비율: {orderable_JPY/target_JPY:.4f}" if target_JPY > 0 else "")
)

if target_JPY > orderable_JPY and target_JPY > 0:
    adjust_rate = orderable_JPY / target_JPY
    for ticker, ticker_qty in buy.items():
        unit = unit_size(ticker)
        adjusted = int(ticker_qty * adjust_rate)
        adjusted = (adjusted // unit) * unit
        buy[ticker] = adjusted
    buy = {t: q for t, q in buy.items() if q >= unit_size(t)}
    message.append(f"JPQT 매수수량 조정 (adjust_rate={adjust_rate:.4f})")
else:
    message.append("JPQT 매수가능금 충분 → 수량 조정 없음")

buy = {t: q for t, q in buy.items() if q >= unit_size(t)}
buy_code = list(buy.keys())

if len(buy_code) == 0:
    message.append("JPQT: 매수 종목 없음")
elif buy_split[0] > 0:
    message.append(f"JPQT: {order['round']}회차 - 매수 주문")
    for ticker, qty in buy.items():
        unit = unit_size(ticker)
        local_split_count = buy_split[0]
        local_split_price = buy_split[1][:]
        split_qty = (int(qty // local_split_count) // unit) * unit

        if split_qty < unit:
            if qty < unit:
                message.append(f"JPQT 매수 스킵: {ticker} 수량 {qty}주 ({unit}주 미만)")
                continue
            local_split_count = 1
            local_split_price = [1.01]
            split_qty = (int(qty) // unit) * unit

        price = buy_prices.get(ticker)
        if not isinstance(price, float) or price <= 0:
            TA.send_tele(f"JPQT: {ticker} 현재가 없음")
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
                message.append(f"JPQT 매수 오류: {ticker} {quantity}주 ¥{order_price:,} API 응답 없음")
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
# 7회차 종료 시: 최종 결과 정리
# ============================================
if order['round'] == 7:
    time_module.sleep(120)
    cancel_message, _ = cancel_orders()
    message.append(cancel_message)
    message.append(f"JPQT {order['date']} 리밸런싱 종료")

    # csv 다시 로드 (결과 분류용 - 사용자가 카테고리 변경 가능)
    try:
        with open(JPQT_stock_path, 'r', encoding='utf-8') as f:
            plan_df = pd.read_csv(f, dtype={
                "code": str, "name": str, "weight": float, "category": str
            })
    except Exception as e:
        TA.send_tele(f"JPQT_stock.csv 파일 오류: {e}")
        sys.exit(1)

    # csv 카테고리별 그룹핑 (CASH/헷지 제외, NaN 제외)
    plan_raw = defaultdict(list)
    for _, row in plan_df.iterrows():
        code = str(row["code"])
        if code == "CASH":
            continue
        if code in HEDGE_TICKERS:
            continue
        if pd.isna(row["category"]):
            continue
        plan_raw[str(row["category"])].append({
            "code":   code,
            "name":   str(row["name"]),
            "weight": float(row["weight"]),
        })
    plan = dict(plan_raw)

    # 헷지 카테고리 추가 (state 기반)
    state_data = load_hedge_state()
    if state_data and 'weights' in state_data:
        w = state_data['weights']
        plan["hedge_gold"] = [{"code": HEDGE_GOLD, "name": HS.HEDGE_GOLD_NAME, "weight": w.get('gold', 0.0)}]
        plan["hedge_bond"] = [{"code": HEDGE_BOND, "name": HS.HEDGE_BOND_NAME, "weight": w.get('bond', 0.0)}]

    # 잔고
    stocks = KIS.get_JP_stock_balance()
    if not isinstance(stocks, list):
        TA.send_tele(f"JPQT: 최종 잔고 조회 불가 ({stocks})")
        sys.exit(1)

    hold = {}
    for stock in stocks:
        ticker = stock["ticker"]
        hold[ticker] = {
            "name":         stock["name"],
            "hold_balance": stock["eval_amt"],
            "hold_qty":     stock["quantity"],
        }
    hold_code = list(hold.keys())

    # 결과 분류
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
                # target의 weight로 split (동일 종목이 여러 카테고리에 들어있을 때 비례 분할)
                tgt_w = target.get(stock_code, {}).get('weight', 0)
                if tgt_w == 0 or stock_code in HEDGE_TICKERS:
                    split_weight = 1.0  # 헷지는 단일 카테고리이므로 그대로
                else:
                    split_weight = stock['weight'] / tgt_w if tgt_w > 0 else 1.0

                result[category].append({
                    "code":    stock_code,
                    "name":    stock['name'],
                    "qty":     hold[stock_code]['hold_qty'] * split_weight,
                    "balance": hold[stock_code]['hold_balance'] * split_weight,
                    "weight":  stock['weight'],
                    "status":  "리밸런싱"
                })

    # remain_last (target에 없는데 보유)
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

    # 표시
    for category, stocks_list in result.items():
        message.append(f"{order['date']} [{category}] 결과")
        for item in stocks_list:
            q = int(item['qty'])
            b = f"¥{float(item['balance']):,.0f}"
            message.append(
                f"  {item['name']}({item['code']}): {q}주, {b}, {item['status']}"
            )

    json_message = save_json(result, JPQT_result_path, order)
    message.extend(json_message)
    time_module.sleep(1.0)

    # 최종 자산 요약
    final_stocks = KIS.get_JP_stock_balance()
    if not isinstance(final_stocks, list):
        TA.send_tele(f"JPQT: 최종 잔고 조회 불가 ({final_stocks})")
        sys.exit(1)
    final_stock_eval = sum(s['eval_amt'] for s in final_stocks)
    time_module.sleep(0.2)

    final_jpy = KIS.get_JP_order_available()
    if final_jpy is None:
        TA.send_tele("JPQT: 최종 JPY 주문가능금액 조회 불가")
        sys.exit(1)

    rebal_data = {
        "date":            str(order['date']),
        "total_stocks":    float(final_stock_eval),
        "total_cash":      float(final_jpy),
        "total_asset":     float(final_stock_eval) + float(final_jpy),
        "total_asset_ret": 0.0,
        "currency":        "JPY",
        "hedge_state":     state_data.get('current_state', 'N/A'),
        "stock_ratio":     state_data.get('weights', {}).get('stock', 1.0),
        "gold_ratio":      state_data.get('weights', {}).get('gold', 0.0),
        "bond_ratio":      state_data.get('weights', {}).get('bond', 0.0),
    }

    for category, stocks_list in result.items():
        category_balance = sum(float(item['balance']) for item in stocks_list)
        rebal_data[category]          = float(category_balance)
        rebal_data[f"{category}_ret"] = 0.0

    json_message = save_json(rebal_data, JPQT_rebal_path, order)
    message.extend(json_message)
    time_module.sleep(1.0)

    # 표시용
    rebal = {
        "date":            rebal_data["date"],
        "total_stocks":    f"¥{rebal_data['total_stocks']:,.0f}",
        "total_cash":      f"¥{rebal_data['total_cash']:,.0f}",
        "total_asset":     f"¥{rebal_data['total_asset']:,.0f}",
        "total_asset_ret": f"{float(rebal_data['total_asset_ret']*100):.2f}%",
        "hedge_state":     rebal_data["hedge_state"],
        "stock/gold/bond": (
            f"{rebal_data['stock_ratio']*100:.0f}% / "
            f"{rebal_data['gold_ratio']*100:.0f}% / "
            f"{rebal_data['bond_ratio']*100:.0f}%"
        )
    }
    for category, stocks_list in result.items():
        category_balance = sum(float(item['balance']) for item in stocks_list)
        rebal[category]          = f"¥{category_balance:,.0f}"
        rebal[f"{category}_ret"] = "0.00%"

    for k, v in rebal.items():
        message.append(f"{k} : {v}")

    TA.send_tele(message)
    message = []

sys.exit(0)
