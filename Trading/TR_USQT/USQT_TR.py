"""
USQT 분기 리밸런싱 14회차 매매 + 헤지 비중 통합 처리
경로: /var/autobot/TR_USQT/USQT_TR.py

운영 개념 (Q1=2번: 통합 처리):
- 분기 리밸런싱일에는 USQT_Hedge.py 가 자동 종료하고 이 스크립트가 헤지까지 책임짐
- 1·8회차에서 헤지 신호 상태(USQT_hedge_state.json) 를 읽어 다음 비중 결정:
  * 오늘이 '월말 정기 신호 익일 매매일' 또는 '주간 RSI 익일 매매일' 이면 → 신호 재계산 + 상태 갱신
  * 둘 다 아니면 → 상태 파일의 current_target 그대로 사용
- target 구성:
    csv 의 USQT 종목 weight (CASH 제외 정규화) × hedge_usqt_ratio   → 개별종목 target_qty
    IAU  비중 × total_usd_asset                                      → IAU  target_qty
    BOND 비중 × total_usd_asset  (IEF or SGOV)                       → BOND target_qty
    CASH = 1 - (USQT_ratio + IAU_ratio + BOND_ratio + csv_CASH_w*usqt_ratio)  → 매매 없음
- 14회차 마무리 결과는 plan(csv 종목) + 헤지 자산을 통합 보고

크론 (UTC, USQT_day.json 의 rebal_dates 와 일치하는 두 날만 실제 동작):
  DST:  32 13-19 * * 1-5  timeout -s 9 35m /usr/bin/python3 /var/autobot/TR_USQT/USQT_TR.py
  EST:  32 14-20 * * 1-5  timeout -s 9 35m /usr/bin/python3 /var/autobot/TR_USQT/USQT_TR.py
  (스크립트 내부에서 rebal_dates 등록일이 아니면 즉시 종료)
"""

import sys
import os
import json
import time as time_module
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

import pandas as pd
from tendo import singleton

import telegram_alert as TA
import KIS_US

# USAA 폴더 공용 캘린더 (USQT_Calender.py 도 /var/autobot/TR_USAA/ 에 위치)
sys.path.insert(0, "/var/autobot/TR_USAA")
import USQT_Calender

# 로컬 신호 모듈
sys.path.insert(0, "/var/autobot/TR_USQT")
import USQT_Hedge_signal as Sig


# ============================================
# 싱글톤
# ============================================
try:
    me = singleton.SingleInstance()
except singleton.SingleInstanceException:
    TA.send_tele("USQT: 이미 실행 중입니다.")
    sys.exit(0)


# ============================================
# KIS 인스턴스
# ============================================
key_file_path   = "/var/autobot/KIS/kis63692011nkr.txt"
token_file_path = "/var/autobot/KIS/kis63692011_token.json"
cano            = "63692011"
acnt_prdt_cd    = "01"
KIS = KIS_US.KIS_API(key_file_path, token_file_path, cano, acnt_prdt_cd)

fee_rate                = KIS.SELL_FEE_RATE
USQT_day_path           = "/var/autobot/TR_USQT/USQT_day.json"
USQT_target_path        = "/var/autobot/TR_USQT/USQT_target.json"
USQT_result_path        = "/var/autobot/TR_USQT/USQT_result.json"
USQT_rebal_path         = "/var/autobot/TR_USQT/USQT_rebal.json"
USQT_stock_path         = "/var/autobot/TR_USQT/USQT_stock.csv"
USQT_hedge_state_path   = "/var/autobot/TR_USQT/USQT_hedge_state.json"


# ============================================
# DST / order_time / health_check / save_json / cancel_orders / is_US_trading_day
# (기존 코드와 동일)
# ============================================
def check_dst():
    try:
        import pytz
        eastern = pytz.timezone('America/New_York')
        now_et = datetime.now(timezone.utc).astimezone(eastern)
        return bool(now_et.dst())
    except ImportError:
        month = datetime.now(timezone.utc).month
        return 3 <= month <= 10


def order_time(day=1):
    """기존 패턴 그대로 14회차 매핑 (UTC)."""
    now = datetime.now(timezone.utc)
    current_date = now.date()
    current_time = now.time()

    result = {
        'date': current_date, 'time': current_time,
        'day':  day, 'round': 0, 'total_round': 14
    }
    hour = current_time.hour
    if check_dst():
        round_map = {13:1, 14:2, 15:3, 16:4, 17:5, 18:6, 19:7}
    else:
        round_map = {14:1, 15:2, 16:3, 17:4, 18:5, 19:6, 20:7}
    base = round_map.get(hour, 0)
    if base > 0:
        result['round'] = base + (day * 7 - 7)
    return result


def health_check():
    checks = []
    if not KIS.access_token:
        checks.append("USQT체크: API 토큰 없음")
    for f in (USQT_day_path, USQT_stock_path):
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
    msgs = []
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4, default=str)
        msgs.append(f"{order['date']} {order['round']}/{order['total_round']}회차 저장 완료: {path}")
    except Exception as e:
        msgs.append(f"{path} 저장 실패: {e}")
        bp = f"/var/autobot/TR_USQT/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(bp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4, default=str)
            msgs.append(f"백업 파일 생성: {bp}")
        except Exception as be:
            msgs.append(f"백업 실패: {be}")
    return msgs


def cancel_orders():
    try:
        summary, cm = KIS.cancel_all_unfilled_orders()
        return f"USQT: {summary['success']}/{summary['total']} 주문 취소", summary
    except Exception as e:
        return f"USQT: 주문 취소 에러 ({e})", {"success": 0, "total": 0, "fail": 0}


def is_US_trading_day():
    try:
        import exchange_calendars as xcals
        import pytz
        cal = xcals.get_calendar("XNYS")
        eastern = pytz.timezone('America/New_York')
        today_et = datetime.now(timezone.utc).astimezone(eastern).date()
        return cal.is_session(pd.Timestamp(today_et))
    except ImportError:
        try:
            import pytz
            eastern = pytz.timezone('America/New_York')
            wd = datetime.now(timezone.utc).astimezone(eastern).weekday()
        except ImportError:
            wd = datetime.now(timezone.utc).weekday()
        return wd < 5
    except Exception:
        return True


# ============================================
# split_data (기존 그대로)
# ============================================
def split_data(round_num):
    if round_num == 1:
        sell_splits = 5; sell_price = [1.0100, 1.0075, 1.0050, 1.0025, 0.9950]
        buy_splits  = 5; buy_price  = [0.9875, 0.9900, 0.9925, 0.9950, 0.9975]
    elif round_num == 2:
        sell_splits = 4; sell_price = [1.0100, 1.0075, 1.0050, 1.0025]
        buy_splits  = 5; buy_price  = [0.9900, 0.9925, 0.9950, 0.9975, 1.0000]
    elif round_num == 3:
        sell_splits = 4; sell_price = [1.0100, 1.0075, 1.0050, 1.0025]
        buy_splits  = 4; buy_price  = [0.9900, 0.9925, 0.9950, 0.9975]
    elif round_num == 4:
        sell_splits = 4; sell_price = [1.0075, 1.0050, 1.0025, 1.0000]
        buy_splits  = 4; buy_price  = [0.9900, 0.9925, 0.9950, 0.9975]
    elif round_num == 5:
        sell_splits = 3; sell_price = [1.0075, 1.0050, 1.0025]
        buy_splits  = 4; buy_price  = [0.9925, 0.9950, 0.9975, 1.0000]
    elif round_num == 6:
        sell_splits = 3; sell_price = [1.0075, 1.0050, 1.0025]
        buy_splits  = 3; buy_price  = [0.9925, 0.9950, 0.9975]
    elif round_num == 7:
        sell_splits = 3; sell_price = [1.0050, 1.0025, 1.0000]
        buy_splits  = 3; buy_price  = [0.9925, 0.9950, 0.9975]
    elif round_num == 8:
        sell_splits = 2; sell_price = [1.0050, 1.0025]
        buy_splits  = 3; buy_price  = [0.9950, 0.9975, 1.0000]
    elif round_num == 9:
        sell_splits = 2; sell_price = [1.0050, 1.0025]
        buy_splits  = 2; buy_price  = [0.9950, 0.9975]
    elif round_num == 10:
        sell_splits = 2; sell_price = [1.0025, 1.0000]
        buy_splits  = 2; buy_price  = [0.9950, 0.9975]
    elif round_num == 11:
        sell_splits = 1; sell_price = [1.0025]
        buy_splits  = 2; buy_price  = [0.9975, 1.0000]
    elif round_num == 12:
        sell_splits = 1; sell_price = [1.0025]
        buy_splits  = 1; buy_price  = [0.9975]
    elif round_num == 13:
        sell_splits = 1; sell_price = [0.9800]
        buy_splits  = 1; buy_price  = [0.9975]
    elif round_num == 14:
        sell_splits = 0; sell_price = []
        buy_splits  = 1; buy_price  = [1.0200]
    else:
        TA.send_tele(f"USQT: 유효하지 않은 round 값: {round_num}")
        sys.exit(1)

    return {"sell_splits": sell_splits, "sell_price": sell_price,
            "buy_splits":  buy_splits,  "buy_price":  buy_price}


# ============================================
# ✅ [신규] 헤지 상태 로드/세이브 + 신호 통합
# ============================================
def load_hedge_state():
    default = {
        "in_rsi_hedge": False,
        "last_monthly_target": {"USQT": 1.0, "IAU": 0.0, "BOND": 0.0, "bond_ticker": "IEF"},
        "last_monthly_state": "Bull",
        "last_monthly_vol":   0.15,
        "last_signal_date":   "1970-01-01",
        "current_target":     {"USQT": 1.0, "IAU": 0.0, "BOND": 0.0, "bond_ticker": "IEF"},
        "active_since":       "1970-01-01"
    }
    if not os.path.exists(USQT_hedge_state_path):
        return default
    try:
        with open(USQT_hedge_state_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def save_hedge_state(state):
    try:
        with open(USQT_hedge_state_path, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=4, default=str)
    except Exception as e:
        TA.send_tele(f"USQT 헤지상태 저장 실패: {e}")


def determine_applied_target(today, message):
    """오늘 적용할 헤지 비중 결정.
    분기 리밸 day1 이 신호일과 겹치면 신호 재계산 후 상태 갱신.
    그렇지 않으면 상태 파일의 current_target 사용.
    """
    state = load_hedge_state()
    today_str = str(today)

    # 신호일 판정: today 의 weekday 가 0(월) 이거나, today 가 월의 첫 거래일이면 신호 재계산
    is_friday_signal_day  = today.weekday() == 0          # 월요일 = 금요일 종가의 익일 매매
    is_month_end_signal_day = False
    # 월말 신호 판정: 이번 달의 첫 거래일이면 True (간이판정: 직전 영업일의 월이 다르면)
    try:
        with open(USQT_Calender.USQT_HEDGE_DAY_PATH, 'r', encoding='utf-8') as f:
            hd = json.load(f)
        all_days = sorted(set(hd.get("summer_dst", []) + hd.get("winter_standard", [])))
        # rebal_dates 자체는 hedge_day 에 없지만, 직전 영업일의 월 비교는 가능
        # → today 가 이번 달 첫 거래일인지: 직전 영업일(today-1 ~ today-5) 중 가장 가까운 영업일의 월 ≠ today.month
        for back in range(1, 8):
            prev = today - timedelta(days=back)
            # 영업일 가정(평일)
            if prev.weekday() < 5:
                if prev.month != today.month:
                    is_month_end_signal_day = True
                break
    except Exception:
        pass

    if not (is_friday_signal_day or is_month_end_signal_day):
        # 신호 재계산 불필요 → 직전 current_target 그대로
        message.append(
            f"USQT: 분기 리밸일이나 신호일 아님 → 직전 헤지 비중 그대로 적용 "
            f"(in_rsi_hedge={state['in_rsi_hedge']}, current={state['current_target']})"
        )
        return state["current_target"], "no_signal_recalc"

    # 신호 재계산
    signals = Sig.compute_signals(KIS)
    if signals is None:
        message.append("USQT: 신호 계산 실패 → 직전 헤지 비중 유지")
        return state["current_target"], "signal_fail"

    message.append(
        f"USQT 신호 [{signals['asof_date']}]: SPY={signals['spy_close']:.2f}/{signals['spy_ma200']:.2f} "
        f"ab200={signals['ab200']} MOM12={signals['mom12']*100:+.1f}% "
        f"VOL20={signals['vol20']*100:.1f}%({signals['vol_band']}) RSI14={signals['rsi14']:.1f} "
        f"bond={signals['bond_ticker']} state={signals['state']}"
    )

    applied, mode, log = Sig.decide_target(signals, state, is_month_end_signal_day, is_friday_signal_day)
    for l in log:
        message.append("USQT 결정: " + l)

    # 상태 갱신
    new = dict(state)
    new["last_signal_date"] = today_str
    new["current_target"]   = applied
    new["active_since"]     = today_str
    if mode == "monthly":
        new["in_rsi_hedge"]        = False
        new["last_monthly_target"] = signals["monthly_target"]
        new["last_monthly_state"]  = signals["state"]
        new["last_monthly_vol"]    = signals["vol20"]
    elif mode == "rsi_enter":
        new["in_rsi_hedge"] = True
    elif mode == "rsi_exit":
        new["in_rsi_hedge"] = False
    save_hedge_state(new)

    return applied, mode


# ============================================
# 메인 로직 시작
# ============================================
checkday = is_US_trading_day()
if not checkday:
    TA.send_tele("USQT: 미국 거래일이 아닙니다.")
    sys.exit(0)

health_check()
message = []

# USQT_day.json 로드
try:
    with open(USQT_day_path, 'r', encoding='utf-8') as f:
        TR_day = json.load(f)
except Exception as e:
    TA.send_tele(f"USQT_day.json 파일 오류: {e}")
    sys.exit(1)

# ✅ 분기 리밸일 체크 (rebal_dates 에 등록된 날만 실행)
# 리밸일이 아니면 알림 없이 조용히 종료 (크론을 항상 켜둬도 텔레그램 스팸 안 발생)
today_utc = datetime.now(timezone.utc).date()
if str(today_utc) not in TR_day.get("rebal_dates", []):
    sys.exit(0)

order = order_time(day=TR_day['day'])
if order['round'] == 0:
    TA.send_tele("USQT: 매매시간이 아닙니다.")
    sys.exit(0)
message.append(f"USQT: {order['day']}일차 {order['round']}/{order['total_round']}회차 매매 시작 (헤지 통합)")

# 전회 주문 취소
cm, _ = cancel_orders()
message.append(cm)
time_module.sleep(3)

# 미체결 잔존 재취소 루프
MAX_CANCEL_RETRY = 3
for retry_i in range(MAX_CANCEL_RETRY):
    try:
        remaining = KIS.get_unfilled_orders()
    except Exception as e:
        message.append(f"USQT 미체결 조회 에러: {e}")
        remaining = []
    if isinstance(remaining, list) and len(remaining) == 0:
        if retry_i > 0:
            message.append(f"USQT 미체결 0건 (재시도 {retry_i}회 후)")
        break
    n = len(remaining) if isinstance(remaining, list) else '?'
    message.append(f"USQT 미체결 잔존 {n}건 → 추가 취소 {retry_i+1}/{MAX_CANCEL_RETRY}")
    rmsg, rs = cancel_orders()
    message.append(rmsg)
    time_module.sleep(3)
    if retry_i == MAX_CANCEL_RETRY - 1 and rs.get('success', 0) == 0:
        message.append("USQT 경고: 취소 실패 상태로 매매 진행")


# ============================================
# 1·8회차: target 산출 (csv × 헤지비중 + IAU + BOND)
# ============================================
if order['round'] == 1 or order['round'] == 8:
    # ✅ [신규] 적용 헤지 비중 결정
    applied, mode = determine_applied_target(today_utc, message)
    usqt_ratio   = float(applied.get("USQT", 1.0))
    iau_ratio    = float(applied.get("IAU",  0.0))
    bond_ratio   = float(applied.get("BOND", 0.0))
    bond_ticker  = applied.get("bond_ticker", "IEF")
    message.append(f"USQT 적용비중[{mode}]: USQT={usqt_ratio:.2%}, IAU={iau_ratio:.2%}, "
                   f"BOND({bond_ticker})={bond_ratio:.2%}")

    # CSV 로드
    try:
        with open(USQT_stock_path, 'r', encoding='utf-8') as f:
            Target = pd.read_csv(f, dtype={"code":str,"name":str,"weight":float,"category":str})
    except Exception as e:
        TA.send_tele(f"USQT_stock.csv 파일 오류: {e}")
        sys.exit(1)

    grouped = Target.groupby("code").agg(
        name=("name","first"),
        weight=("weight","sum"),
        categories=("category", list)
    ).reset_index()

    csv_rows = {
        str(row["code"]): {
            "name":       str(row["name"]),
            "weight":     float(row["weight"]),
            "categories": [str(c) for c in row["categories"]]
        }
        for _, row in grouped.iterrows()
    }

    # CASH 제외 종목 weight 합 (정규화용)
    stock_weight_sum = sum(v["weight"] for k, v in csv_rows.items() if k != "CASH")
    csv_cash_w       = csv_rows.get("CASH", {}).get("weight", 0.0)

    # 총자산
    stocks_list = KIS.get_US_stock_balance()
    if not isinstance(stocks_list, list):
        TA.send_tele(f"USQT: 잔고 조회 불가 ({stocks_list})")
        sys.exit(1)
    stock_eval_usd = sum(s['eval_amt'] for s in stocks_list)
    time_module.sleep(0.2)
    orderable_usd  = KIS.get_US_order_available()
    if orderable_usd is None:
        TA.send_tele("USQT: USD 주문가능금액 조회 불가")
        sys.exit(1)
    total_usd_asset = float(stock_eval_usd) + float(orderable_usd)
    message.append(f"USQT 총자산: ${total_usd_asset:,.2f} "
                   f"(주식:${stock_eval_usd:,.2f} + 현금:${orderable_usd:,.2f})")

    # 종목별 target_invest / target_qty
    target = {}

    # 1) USQT 개별종목 (csv weight 정규화 후 × usqt_ratio)
    for code, v in csv_rows.items():
        if code == "CASH":
            # CASH: csv 의 CASH 비중도 usqt_ratio 영역 안에 비례 (실제로 csv가 1.0 가정이라
            # CASH weight × usqt_ratio 만큼 현금 → 매매 X)
            cash_eff = csv_cash_w * usqt_ratio if stock_weight_sum > 0 else usqt_ratio
            target["CASH"] = {
                "name": "CASH", "weight": cash_eff,
                "target_invest": cash_eff * total_usd_asset,
                "target_qty":    0,
                "kind":          "CASH"
            }
            continue

        # 정규화 weight × usqt_ratio
        if stock_weight_sum > 0:
            w_eff = (v["weight"] / stock_weight_sum) * usqt_ratio * (1 - csv_cash_w)
            # 위 공식 설명:
            #   csv 의 CASH 제외 종목 합계가 stock_weight_sum
            #   정규화하면 stock_weight_sum → 1
            #   usqt_ratio 영역 중 csv_cash_w 만큼은 CASH 로 → 종목 영역 = usqt_ratio × (1 - csv_cash_w)
            #   각 종목 = (csv_w / stock_weight_sum) × usqt_ratio × (1 - csv_cash_w)
        else:
            w_eff = 0.0

        price = KIS.get_US_current_price(code)
        if not isinstance(price, float) or price <= 0:
            TA.send_tele(f"USQT: {code} 현재가 조회 불가")
            sys.exit(1)

        invest      = w_eff * total_usd_asset
        new_tgt_qty = int(invest / price)

        # ✅ 8회차(2일차): target_qty 가 현재 보유보다 줄어들면 보유수량으로 floor
        #    (1일차 매수분 T+1 미결제로 매도 불가)
        if order['round'] == 8:
            cur = 0
            for s in stocks_list:
                if s['ticker'] == code:
                    cur = s['quantity']
                    break
            if new_tgt_qty < cur:
                new_tgt_qty = cur

        target[code] = {
            "name":          v["name"],
            "weight":        w_eff,
            "categories":    v["categories"],
            "current_price": price,
            "target_invest": invest,
            "target_qty":    new_tgt_qty,
            "kind":          "USQT"
        }
        time_module.sleep(0.15)

    # 2) IAU
    if iau_ratio > 0:
        price = KIS.get_US_current_price("IAU")
        if isinstance(price, float) and price > 0:
            invest = iau_ratio * total_usd_asset
            new_q  = int(invest / price)
            if order['round'] == 8:
                cur = next((s['quantity'] for s in stocks_list if s['ticker'] == "IAU"), 0)
                if new_q < cur:
                    new_q = cur
            target["IAU"] = {
                "name": "iShares Gold Trust", "weight": iau_ratio,
                "categories": ["HEDGE_IAU"],
                "current_price": price, "target_invest": invest,
                "target_qty": new_q, "kind": "IAU"
            }
        else:
            TA.send_tele("USQT: IAU 현재가 조회 실패 - 헤지 자산 일부 누락")
        time_module.sleep(0.15)

    # 3) BOND
    if bond_ratio > 0:
        price = KIS.get_US_current_price(bond_ticker)
        if isinstance(price, float) and price > 0:
            invest = bond_ratio * total_usd_asset
            new_q  = int(invest / price)
            if order['round'] == 8:
                cur = next((s['quantity'] for s in stocks_list if s['ticker'] == bond_ticker), 0)
                if new_q < cur:
                    new_q = cur
            target[bond_ticker] = {
                "name": bond_ticker, "weight": bond_ratio,
                "categories": ["HEDGE_BOND"],
                "current_price": price, "target_invest": invest,
                "target_qty": new_q, "kind": "BOND"
            }
        else:
            TA.send_tele(f"USQT: {bond_ticker} 현재가 조회 실패")
        time_module.sleep(0.15)

    # 4) 반대 채권은 target_qty=0 명시 (보유 시 전량 매도)
    other_bond = "SGOV" if bond_ticker == "IEF" else "IEF"
    if other_bond not in target:
        target[other_bond] = {
            "name": other_bond, "weight": 0.0, "categories": ["HEDGE_BOND_OTHER"],
            "current_price": 0.0, "target_invest": 0.0,
            "target_qty": 0, "kind": "BOND_OTHER"
        }

    # 저장
    ser = {}
    for k, v in target.items():
        ser[k] = {kk: (float(vv) if isinstance(vv, float)
                       else int(vv) if isinstance(vv, int) and not isinstance(vv, bool)
                       else vv)
                  for kk, vv in v.items()}
    json_msg = save_json(ser, USQT_target_path, order)
    message.extend(json_msg)
    target_code = list(target.keys())

else:
    # 2~7, 9~14회차: target.json 로드
    try:
        with open(USQT_target_path, 'r', encoding='utf-8') as f:
            target = json.load(f)
    except Exception as e:
        TA.send_tele(f"USQT_target.json 파일 오류: {e}")
        sys.exit(1)
    target_code = list(target.keys())


# ============================================
# 보유 잔고
# ============================================
stocks = KIS.get_US_stock_balance()
if not isinstance(stocks, list):
    TA.send_tele(f"USQT: 잔고 조회 불가 ({stocks})")
    sys.exit(1)

hold = {}
for s in stocks:
    t = s["ticker"]
    hold[t] = {
        "name":          s["name"],
        "hold_balance":  s["eval_amt"],
        "hold_qty":      s["quantity"],
        "ord_psbl_qty":  s.get("ord_psbl_qty") or s["quantity"],
        "current_price": s["current_price"],
        "exchange":      s["exchange"],
    }
hold_code = list(hold.keys())


# ============================================
# 매수/매도 수량
# ============================================
buy, sell = {}, {}
for t in hold_code:
    if t in target_code:
        if t == "CASH":
            continue
        tgt = int(target[t].get("target_qty", 0))
        hld = int(hold[t]["hold_qty"])
        if tgt > hld:
            buy[t] = tgt - hld
        elif tgt < hld:
            need = hld - tgt
            sellable = min(need, hold[t]["ord_psbl_qty"])
            if sellable > 0:
                sell[t] = sellable
            else:
                message.append(f"USQT 매도스킵: {t} 필요{need}, 가능{hold[t]['ord_psbl_qty']}")
    else:
        sellable = min(hold[t]["hold_qty"], hold[t]["ord_psbl_qty"])
        if sellable > 0:
            sell[t] = sellable
        else:
            message.append(f"USQT 매도스킵: {t} 가능수량 0")

for t in target_code:
    if t == "CASH":
        continue
    tgt = int(target[t].get("target_qty", 0))
    if t not in hold_code and tgt > 0:
        buy[t] = tgt


# ============================================
# 분할 매매
# ============================================
rsplit = split_data(order['round'])
sell_split = [rsplit["sell_splits"], rsplit["sell_price"]]
buy_split  = [rsplit["buy_splits"],  rsplit["buy_price"]]

# 매도
if not sell:
    message.append("USQT: 매도 종목 없음")
elif sell_split[0] > 0:
    message.append(f"USQT: {order['round']}회차 - 매도 주문")
    for t, qty in sell.items():
        sc = sell_split[0]
        sp = sell_split[1][:]
        sq = int(qty // sc)
        rm = int(qty - sq * sc)
        if sq < 1:
            sc = 1; sp = [0.99]; sq = int(qty); rm = 0

        price = KIS.get_US_current_price(t)
        if not isinstance(price, float) or price <= 0:
            TA.send_tele(f"USQT: {t} 현재가 조회 불가")
            continue

        raw_excd = hold.get(t, {}).get("exchange", "")
        excd_map = {"NAS":"NASD","NYS":"NYSE","AMS":"AMEX","NASD":"NASD","NYSE":"NYSE","AMEX":"AMEX"}
        tex = excd_map.get(raw_excd, None)

        for i in range(sc):
            tq = sq + (rm if i == sc - 1 else 0)
            if tq < 1:
                continue
            op = round(price * sp[i], 2)
            oi, om = KIS.order_sell_US(t, tq, op, exchange=tex)
            if oi is None:
                time_module.sleep(2)
                oi, om = KIS.order_sell_US(t, tq, op, exchange=tex)
            if oi is None:
                message.append(f"USQT 매도 오류: {t} {tq}주 ${op:.2f}")
            elif oi.get("success"):
                message.append(f"매도 {t} {tq}주 ${op:.2f} #{oi.get('order_number','')}")
            else:
                message.append(f"매도 실패 {t} {tq}주: {oi.get('error_message','')}")
            time_module.sleep(0.2)
else:
    message.append(f"USQT: {order['round']}회차 매도 스킵 - 미처분 잔량: {list(sell.keys())}")

TA.send_tele(message)
message = []

# 매도-매수 갭
time_module.sleep(600)

# 매수 전 USD 가용 + 비례조정
USD = KIS.get_US_order_available()
if USD is None:
    TA.send_tele("USQT: USD 조회 불가")
    sys.exit(1)
orderable_USD = float(USD)

target_USD = 0.0
buy_prices = {}
buy_price_rate = buy_split[1][-1] if buy_split[1] else 1.0
for t, qty in buy.items():
    price = KIS.get_US_current_price(t)
    if not isinstance(price, float) or price <= 0:
        TA.send_tele(f"USQT: {t} 현재가 조회 불가")
        sys.exit(1)
    buy_prices[t] = price
    target_USD += price * buy_price_rate * qty
    time_module.sleep(0.15)

message.append(f"USQT 매수가능: ${orderable_USD:,.2f} | 목표매수금: ${target_USD:,.2f}"
               + (f" | 조정: {orderable_USD/target_USD:.4f}" if target_USD > 0 else ""))

if target_USD > orderable_USD and target_USD > 0:
    adj = orderable_USD / target_USD
    for t in list(buy.keys()):
        buy[t] = int(buy[t] * adj)
    buy = {t: q for t, q in buy.items() if q > 0}
    message.append(f"USQT 매수수량 조정 (adjust={adj:.4f})")

buy = {t: q for t, q in buy.items() if q > 0}
buy_code = list(buy.keys())

if not buy_code:
    message.append("USQT: 매수 종목 없음")
elif buy_split[0] > 0:
    message.append(f"USQT: {order['round']}회차 - 매수 주문")
    for t, qty in buy.items():
        bc = buy_split[0]
        bp = buy_split[1][:]
        sq = int(qty // bc)
        rm = int(qty - sq * bc)
        if sq < 1:
            if qty < 1:
                continue
            bc = 1; bp = [1.01]; sq = int(qty); rm = 0
        price = buy_prices.get(t)
        if not isinstance(price, float) or price <= 0:
            TA.send_tele(f"USQT: {t} 현재가 없음")
            sys.exit(1)
        for i in range(bc):
            tq = sq + (rm if i == bc - 1 else 0)
            if tq < 1:
                continue
            op = round(price * bp[i], 2)
            oi, om = KIS.order_buy_US(t, tq, op)
            if oi is None:
                time_module.sleep(2)
                oi, om = KIS.order_buy_US(t, tq, op)
            if oi is None:
                message.append(f"USQT 매수 오류: {t} {tq}주 ${op:.2f}")
            elif oi.get("success"):
                message.append(f"매수 {t} {tq}주 ${op:.2f} #{oi.get('order_number','')}")
            else:
                message.append(f"매수 실패 {t} {tq}주: {oi.get('error_message','')}")
            time_module.sleep(0.2)


# ============================================
# day 전환
# ============================================
if order['round'] == 7:
    TR_day["day"] = 2
    save_json(TR_day, USQT_day_path, order)
if order['round'] == 14:
    TR_day["day"] = 1
    save_json(TR_day, USQT_day_path, order)

TA.send_tele(message)
message = []


# ============================================
# 14회차 마무리
# ============================================
if order['round'] == 14:
    time_module.sleep(120)
    cm, _ = cancel_orders()
    message.append(cm)
    message.append(f"USQT {order['date']} 리밸런싱(헤지 통합) 종료")

    try:
        with open(USQT_stock_path, 'r', encoding='utf-8') as f:
            plan = pd.read_csv(f, dtype={"code":str,"name":str,"weight":float,"category":str})
    except Exception as e:
        TA.send_tele(f"USQT_stock.csv 파일 오류: {e}")
        sys.exit(1)

    plan_raw = defaultdict(list)
    for _, row in plan.iterrows():
        if str(row["code"]) == "CASH":
            continue
        if pd.isna(row["category"]):
            continue
        plan_raw[str(row["category"])].append({
            "code":   str(row["code"]),
            "name":   str(row["name"]),
            "weight": float(row["weight"]),
        })
    plan = dict(plan_raw)

    stocks2 = KIS.get_US_stock_balance()
    if not isinstance(stocks2, list):
        TA.send_tele(f"USQT: 최종 잔고 조회 불가 ({stocks2})")
        sys.exit(1)
    hold2 = {s["ticker"]: {"name": s["name"], "hold_balance": s["eval_amt"], "hold_qty": s["quantity"]}
             for s in stocks2}
    hold2_code = list(hold2.keys())

    result = {}
    # USQT 카테고리별
    for category in plan.keys():
        result[category] = []
        for st in plan[category]:
            code = st['code']
            if code not in hold2_code:
                result[category].append({
                    "code": code, "name": st['name'],
                    "qty": 0, "balance": 0,
                    "weight": st['weight'], "status": "리밸런싱 매수실패"
                })
            else:
                total_w = target.get(code, {}).get("weight", 0)
                if total_w == 0:
                    split_w = 1.0
                else:
                    # csv 의 동일 종목이 여러 카테고리에 있을 경우 비례 분배
                    split_w = st['weight'] / sum(
                        x['weight'] for cat in plan.values() for x in cat if x['code'] == code
                    )
                result[category].append({
                    "code":    code, "name": st['name'],
                    "qty":     hold2[code]['hold_qty'] * split_w,
                    "balance": hold2[code]['hold_balance'] * split_w,
                    "weight":  st['weight'],
                    "status":  "리밸런싱"
                })

    # 헤지 자산 결과 (별도 카테고리)
    hedge_items = []
    for hticker in ("IAU", "IEF", "SGOV"):
        if hticker in target_code:
            tgt_qty = int(target[hticker].get("target_qty", 0))
            tgt_w   = float(target[hticker].get("weight", 0))
            if hticker in hold2_code:
                hedge_items.append({
                    "code": hticker, "name": target[hticker].get("name", hticker),
                    "qty":  hold2[hticker]['hold_qty'],
                    "balance": hold2[hticker]['hold_balance'],
                    "weight": tgt_w,
                    "status": "헤지보유" if hold2[hticker]['hold_qty'] > 0 else "헤지매수실패"
                })
            elif tgt_qty > 0:
                hedge_items.append({
                    "code": hticker, "name": target[hticker].get("name", hticker),
                    "qty": 0, "balance": 0, "weight": tgt_w,
                    "status": "헤지매수실패"
                })
    if hedge_items:
        result["HEDGE"] = hedge_items

    # 잔여 종목
    remain_items = []
    for t in hold2_code:
        if t not in target_code:
            remain_items.append({
                "code": t, "name": hold2[t]['name'],
                "qty":  hold2[t]['hold_qty'],
                "balance": hold2[t]['hold_balance'],
                "weight": 0, "status": "리밸런싱 매도실패"
            })
    if remain_items:
        result["remain_last"] = remain_items

    for category, lst in result.items():
        message.append(f"{order['date']}일 카테고리:{category} 결과")
        for item in lst:
            message.append(
                f"종목명: {item['name']}, 잔고: {int(item['qty'])}주, "
                f"평가금: ${float(item['balance']):,.2f}, 상태: {item['status']}"
            )

    json_msg = save_json(result, USQT_result_path, order)
    message.extend(json_msg)
    time_module.sleep(1.0)

    # rebal 저장
    final_stocks = KIS.get_US_stock_balance()
    final_eval = sum(s['eval_amt'] for s in final_stocks) if isinstance(final_stocks, list) else 0.0
    time_module.sleep(0.2)
    final_usd = KIS.get_US_order_available() or 0.0

    rebal_data = {
        "date": str(order['date']),
        "total_stocks":    float(final_eval),
        "total_cash":      float(final_usd),
        "total_asset":     float(final_eval) + float(final_usd),
        "total_asset_ret": 0.0,
        "currency":        "USD",
        "hedge_state":     load_hedge_state()
    }
    for category, lst in result.items():
        cat_bal = sum(float(item['balance']) for item in lst)
        rebal_data[category]          = float(cat_bal)
        rebal_data[f"{category}_ret"] = 0.0

    save_json(rebal_data, USQT_rebal_path, order)

    rebal = {
        "date":            rebal_data["date"],
        "total_stocks":    f"${rebal_data['total_stocks']:,.2f}",
        "total_cash":      f"${rebal_data['total_cash']:,.2f}",
        "total_asset":     f"${rebal_data['total_asset']:,.2f}",
        "total_asset_ret": f"{float(rebal_data['total_asset_ret']*100):.2f}%"
    }
    for category, lst in result.items():
        cat_bal = sum(float(item['balance']) for item in lst)
        rebal[category]          = f"${cat_bal:,.2f}"
        rebal[f"{category}_ret"] = "0.00%"

    for k, v in rebal.items():
        message.append(f"{k} : {v}")

    TA.send_tele(message)

sys.exit(0)
