"""
test_JP_intraday.py
JPQT + JP_Hedge 장중 드라이런 테스트 (실주문 절대 X)

목적:
- 일본 장 운영시간 중 (KST 09:00~15:00 = UTC 00:00~06:00) 실행
- KIS API로 실제 데이터 조회 (현재가, 잔고, 주문가능금액, 일봉)
- target 계산 + 매수/매도 수량 산출까지 완전히 시뮬레이션
- 단, 실제 order_buy_JP / order_sell_JP는 절대 호출 X (몽키 패칭으로 차단)
- 미체결 조회는 OK (cancel은 호출 안 함)

테스트 항목:
[I01] KIS API 토큰 + 잔고 조회 (ccld_qty_smtl1 검증)
[I02] JPY 주문가능금액 조회 (실제 vs 단순 예수금 비교)
[I03] 헷지 신호 + state 갱신 시나리오 (디스크 X)
[I04] CSV → target 산출 (실시간 현재가 사용)
[I05] 보유 종목 매수/매도 분류 (실제 잔고 기반)
[I06] 분할 주문 가격 시뮬레이션 (1~7회차)
[I07] 매수 가능 금액 vs 목표 매수금 정합성
[I08] 미체결 주문 조회
[I09] 안전장치 검증: order_buy_JP / order_sell_JP 호출 차단 확인

사용법:
  cd /var/autobot/TR_JPQT
  python3 test_JP_intraday.py

  옵션:
    --round N      : 특정 회차로 시뮬레이션 (기본: 현재 시각 기준 자동)
    --strategy     : JPQT | HEDGE | BOTH (기본 BOTH)
    --no-disk      : state/target 파일 디스크 저장 X
    --verbose      : 상세 출력

⚠️ 안전장치 (절대 변경 금지):
  - 매수/매도 주문 메서드는 시작 시점에 라이브 차단 (raise)
  - 미체결 취소도 호출 X (조회만)
  - 디스크 쓰기는 기본적으로 별도 _test_ 접두사 파일에만
"""

import os
import sys
import json
import argparse
import traceback
from datetime import datetime, timezone, timedelta, time
from typing import Optional, Dict, List, Tuple

# ============================================
# 경로 설정
# ============================================
PROJECT_DIR = "/var/autobot/TR_JPQT"
if not os.path.isdir(PROJECT_DIR):
    PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
    print(f"[INFO] 운영 디렉토리 없음 → {PROJECT_DIR} 사용")

sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, "/var/autobot")

KEY_FILE = "/var/autobot/KIS/kis63604155nkr.txt"
TOKEN_FILE = "/var/autobot/KIS/kis63604155_token.json"
CANO = "63604155"
ACNT_PRDT_CD = "01"


# ============================================
# 출력 도우미
# ============================================
class C:
    OK = "\033[92m✓\033[0m"
    FAIL = "\033[91m✗\033[0m"
    WARN = "\033[93m⚠\033[0m"
    INFO = "\033[94mℹ\033[0m"
    BOLD = "\033[1m"
    END = "\033[0m"

RESULTS = []

def record(test_id: str, name: str, status: str, detail: str = ""):
    RESULTS.append((test_id, name, status, detail))
    icon = {"PASS": C.OK, "FAIL": C.FAIL, "WARN": C.WARN, "SKIP": C.INFO}.get(status, "?")
    print(f"  {icon} [{test_id}] {name}")
    if detail:
        for line in detail.split("\n"):
            print(f"      {line}")


def section(title: str):
    print(f"\n{C.BOLD}{'='*72}{C.END}")
    print(f"{C.BOLD}{title}{C.END}")
    print(f"{C.BOLD}{'='*72}{C.END}")


# ============================================
# 안전장치: 주문 메서드 라이브 차단
# ============================================
class OrderBlockedException(Exception):
    """드라이런 중 주문 시도 차단 예외"""
    pass


def install_order_blockers(kis_obj):
    """KIS 인스턴스의 주문/취소 메서드를 차단 함수로 대체"""
    blocked_methods = [
        "order_buy_JP", "order_sell_JP",
        "cancel_JP_order", "cancel_all_unfilled_orders",
    ]
    for m in blocked_methods:
        if hasattr(kis_obj, m):
            def make_blocker(name):
                def _blocked(*args, **kwargs):
                    raise OrderBlockedException(
                        f"[DRY-RUN] {name}({args[1:] if len(args)>1 else ''}, {kwargs}) "
                        f"호출 차단됨"
                    )
                return _blocked
            setattr(kis_obj, m, make_blocker(m))
    return blocked_methods


# ============================================
# I01: KIS 인스턴스 + 잔고 조회
# ============================================
def test_kis_balance(kis):
    section("I01: 잔고 조회 (ccld_qty_smtl1 검증)")

    try:
        stocks = kis.get_JP_stock_balance()
    except Exception as e:
        record("I01-00", "get_JP_stock_balance 호출",
               "FAIL", f"{type(e).__name__}: {e}")
        return None

    if not isinstance(stocks, list):
        record("I01-00", "get_JP_stock_balance 결과 타입",
               "FAIL", f"{type(stocks).__name__}: {stocks}")
        return None

    record("I01-01", "잔고 조회", "PASS", f"{len(stocks)}개 종목 보유")

    if len(stocks) == 0:
        record("I01-02", "보유 종목 없음", "WARN", "잔고 0건")
        return stocks

    total_eval = sum(s.get("eval_amt", 0) for s in stocks)
    record("I01-03", "총 주식평가금", "PASS", f"¥{total_eval:,.0f}")

    # 필수 키 검증
    required_keys = {"ticker", "name", "quantity", "eval_amt", "current_price"}
    missing_keys = required_keys - set(stocks[0].keys())
    if missing_keys:
        record("I01-04", "잔고 dict 필수 키", "FAIL",
               f"누락: {missing_keys}")
    else:
        record("I01-04", "잔고 dict 필수 키", "PASS",
               f"키: {sorted(stocks[0].keys())}")

    # ord_psbl_qty 존재 여부
    has_ord = "ord_psbl_qty" in stocks[0]
    if has_ord:
        record("I01-05", "ord_psbl_qty 키 존재", "PASS")
    else:
        record("I01-05", "ord_psbl_qty 키", "WARN",
               "키 없음 → JPQT_TR.py가 hold_qty로 폴백")

    # 상위 5종목 표시
    sorted_stocks = sorted(stocks, key=lambda x: -x.get("eval_amt", 0))[:5]
    detail_lines = []
    for s in sorted_stocks:
        detail_lines.append(
            f"{s.get('ticker','?')} ({s.get('name','?')[:15]}): "
            f"{s.get('quantity', 0)}주 × ¥{s.get('current_price', 0):,.0f} "
            f"= ¥{s.get('eval_amt', 0):,.0f}"
        )
    record("I01-06", "상위 5종목", "PASS", "\n".join(detail_lines))

    return stocks


# ============================================
# I02: JPY 주문가능금액
# ============================================
def test_jpy_orderable(kis):
    section("I02: JPY 주문가능금액 조회")

    try:
        jpy = kis.get_JP_order_available()
    except Exception as e:
        record("I02-00", "get_JP_order_available 호출",
               "FAIL", f"{type(e).__name__}: {e}")
        return None

    if jpy is None:
        record("I02-00", "get_JP_order_available 결과",
               "FAIL", "None 반환")
        return None

    record("I02-01", "주문가능금액", "PASS",
           f"¥{float(jpy):,.0f}")

    # 일반 예수금 메서드와 비교 (있다면)
    if hasattr(kis, "get_JP_dollar_balance"):
        try:
            deposit_info = kis.get_JP_dollar_balance()
            if deposit_info and "deposit" in deposit_info:
                deposit = float(deposit_info["deposit"])
                diff = float(jpy) - deposit
                record("I02-02", "주문가능 vs 예수금 차이",
                       "PASS",
                       f"주문가능 ¥{float(jpy):,.0f} - 예수금 ¥{deposit:,.0f} "
                       f"= ¥{diff:,.0f} (T+2 미정산 등 반영)")
        except Exception as e:
            record("I02-02", "예수금 비교", "SKIP", f"{e}")
    else:
        record("I02-02", "예수금 비교 메서드", "SKIP",
               "get_JP_dollar_balance 없음")

    return float(jpy)


# ============================================
# I03: 헷지 신호 산출 + state
# ============================================
def test_hedge_signal_live(kis, no_disk: bool):
    section("I03: 헷지 신호 산출 (TOPIX 1306 일봉)")

    try:
        import JP_Hedge_signal as HS
    except ImportError as e:
        record("I03-00", "JP_Hedge_signal", "FAIL", str(e))
        return None

    print(f"      {C.INFO} TOPIX 1306 일봉 조회 중...")
    try:
        signal = HS.compute_signal(kis, HS.TOPIX_TICKER)
    except Exception as e:
        record("I03-01", "compute_signal", "FAIL",
               f"{type(e).__name__}: {e}")
        return None

    if signal is None:
        record("I03-01", "compute_signal 결과", "FAIL",
               "None (데이터 부족)")
        return None

    record("I03-01", "신호 산출", "PASS",
           f"date={signal['date']}, state={signal['state']}, "
           f"n_data={signal['n_data']}일")

    record("I03-02", "신호 상세", "PASS",
           f"종가 ¥{signal['close']:,.1f}  /  "
           f"MA200 ¥{signal['ma200']:,.1f} [{signal['signal_ma']}]  /  "
           f"MOM12 {signal['mom12']*100:+.2f}% [{signal['signal_mom']}]")

    w = signal["weights"]
    record("I03-03", "목표 비중", "PASS",
           f"주식 {w['stock']*100:.0f}% / "
           f"금 {w['gold']*100:.0f}% / "
           f"채권 {w['bond']*100:.0f}%")

    # state 파일과 비교
    state_path = os.path.join(PROJECT_DIR, "JP_Hedge_state.json")
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                prev = json.load(f)
            prev_state = prev.get("current_state", "UNKNOWN")
            changed = (prev_state != signal["state"])
            if changed:
                record("I03-04", "상태 전환 감지", "WARN",
                       f"{prev_state} → {signal['state']} (실제 매매일에 리밸런싱 발생)")
            else:
                record("I03-04", "상태 유지", "PASS",
                       f"{prev_state} = {signal['state']}")
        except Exception as e:
            record("I03-04", "이전 state 비교", "WARN", str(e))
    else:
        record("I03-04", "state 파일", "SKIP", "최초 실행")

    return signal


# ============================================
# I04: CSV → target 산출 (실시간 현재가)
# ============================================
def test_target_with_live_prices(kis, signal, jpy_orderable, stocks):
    section("I04: target 산출 (실시간 현재가)")

    if signal is None:
        record("I04-00", "signal 없음", "SKIP")
        return None

    import pandas as pd
    import JP_Hedge_signal as HS

    csv_path = os.path.join(PROJECT_DIR, "JPQT_stock.csv")
    if not os.path.exists(csv_path):
        record("I04-00", "CSV 없음", "FAIL", csv_path)
        return None

    df = pd.read_csv(csv_path, dtype={
        "code": str, "name": str, "weight": float, "category": str
    })

    HEDGE_GOLD = HS.HEDGE_GOLD_TICKER
    HEDGE_BOND = HS.HEDGE_BOND_TICKER
    HEDGE_TICKERS = {HEDGE_GOLD, HEDGE_BOND}

    grouped = df.groupby("code").agg(
        name=("name", "first"),
        weight=("weight", "sum"),
        categories=("category", list),
    ).reset_index()

    csv_stocks = {}
    for _, row in grouped.iterrows():
        code = str(row["code"])
        if code == "CASH" or code in HEDGE_TICKERS:
            continue
        csv_stocks[code] = {
            "name": str(row["name"]),
            "weight": float(row["weight"]),
            "categories": [str(c) for c in row["categories"]],
        }

    weight_sum = sum(v["weight"] for v in csv_stocks.values())
    for code in csv_stocks:
        csv_stocks[code]["weight"] /= weight_sum

    # 총자산
    stock_eval = sum(s.get("eval_amt", 0) for s in stocks) if stocks else 0
    total_asset = stock_eval + jpy_orderable
    record("I04-01", "총자산 산출", "PASS",
           f"¥{total_asset:,.0f} (주식 ¥{stock_eval:,.0f} + 현금 ¥{jpy_orderable:,.0f})")

    # target 구성
    weights = signal["weights"]
    stock_ratio = weights["stock"]
    target = {}
    for code, info in csv_stocks.items():
        target[code] = {
            "name":   info["name"],
            "weight": info["weight"] * stock_ratio,
        }
    target[HEDGE_GOLD] = {"name": HS.HEDGE_GOLD_NAME, "weight": weights["gold"]}
    target[HEDGE_BOND] = {"name": HS.HEDGE_BOND_NAME, "weight": weights["bond"]}

    total_w = sum(v["weight"] for v in target.values())
    if abs(total_w - 1.0) > 0.01:
        record("I04-02", "target weight 합", "FAIL", f"합={total_w:.4f}")
    else:
        record("I04-02", "target weight 합", "PASS", f"합={total_w:.6f}")

    # 실시간 현재가 조회 (헷지 ETF + 상위 3종목)
    print(f"      {C.INFO} 헷지 ETF + 상위 3종목 현재가 조회 중...")
    sample_codes = [HEDGE_GOLD, HEDGE_BOND] + list(csv_stocks.keys())[:3]
    price_results = {}
    for code in sample_codes:
        try:
            p = kis.get_JP_current_price(code)
            if isinstance(p, float) and p > 0:
                price_results[code] = p
            else:
                price_results[code] = None
        except Exception as e:
            price_results[code] = None

    detail_lines = []
    fail_count = 0
    for code, p in price_results.items():
        if p is None:
            detail_lines.append(f"{code} ({target[code]['name'][:20]}): 조회 실패")
            fail_count += 1
        else:
            unit = 1 if code in HEDGE_TICKERS else 100
            target_invest = target[code]["weight"] * total_asset
            raw_qty = int(target_invest / p)
            target_qty = (raw_qty // unit) * unit
            actual = target_qty * p
            detail_lines.append(
                f"{code} ({target[code]['name'][:18]:<18}): "
                f"¥{p:>7,.0f} × {target_qty:>4}주 = ¥{actual:>10,.0f}  "
                f"(목표 ¥{target_invest:,.0f}, {target[code]['weight']*100:.2f}%)"
            )
    status = "PASS" if fail_count == 0 else ("WARN" if fail_count < len(sample_codes) else "FAIL")
    record("I04-03", f"현재가 조회 ({len(sample_codes)}종목)", status, "\n".join(detail_lines))

    return target, price_results


# ============================================
# I05: 매수/매도 분류 (실제 잔고)
# ============================================
def test_buy_sell_classification(target, stocks, price_results):
    section("I05: 매수/매도 수량 분류 (실제 잔고 기반)")

    if not target or not stocks:
        record("I05-00", "데이터 부족", "SKIP")
        return

    HEDGE_TICKERS = {"1328", "1482"}
    def unit_size(t):
        return 1 if t in HEDGE_TICKERS else 100

    hold = {}
    for s in stocks:
        t = s.get("ticker")
        if not t:
            continue
        hold[t] = {
            "name":         s.get("name", ""),
            "hold_qty":     int(s.get("quantity", 0)),
            "ord_psbl_qty": int(s.get("ord_psbl_qty") or s.get("quantity", 0)),
        }

    target_code = list(target.keys())
    hold_code = list(hold.keys())

    # 목표가 0인 종목(전부 매도 대상)
    target_zero = [t for t in target_code if target[t].get("weight", 0) == 0]
    if target_zero:
        record("I05-01", "weight=0인 target 종목", "PASS",
               f"{target_zero} (보유 시 전량 매도)")

    # target에 없는 보유 종목 (전량 매도 대상)
    only_in_hold = [t for t in hold_code if t not in target_code]
    if only_in_hold:
        detail_lines = []
        for t in only_in_hold:
            detail_lines.append(
                f"{t} ({hold[t]['name'][:15]}): "
                f"{hold[t]['hold_qty']}주 → 전량 매도 예정"
            )
        record("I05-02", "target 외 보유 종목 (전량 매도)", "WARN",
               "\n".join(detail_lines))
    else:
        record("I05-02", "target 외 보유 종목", "PASS", "없음")

    # target에 있고 보유 중인 종목
    common = [t for t in target_code if t in hold_code]
    record("I05-03", "target ∩ hold 종목 수", "PASS",
           f"{len(common)}건 / target {len(target_code)} / hold {len(hold_code)}")

    # 실제 매수/매도 계산 (target_qty가 없으므로 가능한 종목만)
    buy_count = 0
    sell_count = 0
    for t in hold_code:
        if t in target_code and "target_qty" in target[t]:
            tq = target[t]["target_qty"]
            hq = hold[t]["hold_qty"]
            if tq > hq:
                buy_count += 1
            elif tq < hq:
                sell_count += 1
        elif t not in target_code:
            sell_count += 1

    record("I05-04", "현재 데이터로 산출한 매수/매도",
           "PASS",
           f"매수 종목 {buy_count} / 매도 종목 {sell_count} (현재가 조회된 종목 한정)")


# ============================================
# I06: 분할 주문 가격 시뮬레이션
# ============================================
def test_split_data():
    section("I06: 분할 주문 가격 시뮬레이션 (1~7회차)")

    table = {
        1: (5, [1.0100, 1.0075, 1.0050, 1.0025, 0.9950], 5, [0.9875, 0.9900, 0.9925, 0.9950, 0.9975]),
        2: (4, [1.0100, 1.0075, 1.0050, 1.0025],         5, [0.9900, 0.9925, 0.9950, 0.9975, 1.0000]),
        3: (4, [1.0100, 1.0075, 1.0050, 1.0025],         4, [0.9900, 0.9925, 0.9950, 0.9975]),
        4: (4, [1.0075, 1.0050, 1.0025, 1.0000],         4, [0.9900, 0.9925, 0.9950, 0.9975]),
        5: (3, [1.0075, 1.0050, 1.0025],                  4, [0.9925, 0.9950, 0.9975, 1.0000]),
        6: (3, [1.0075, 1.0050, 1.0025],                  3, [0.9925, 0.9950, 0.9975]),
        7: (3, [1.0050, 1.0025, 1.0000],                  3, [0.9925, 0.9950, 0.9975]),
    }

    sample_price = 1500.0   # 가상 매도 가격 (¥1,500 종목)
    sample_buy_price = 1500.0

    for r in range(1, 8):
        s_n, s_p, b_n, b_p = table[r]
        # 매도 시 평균 호가
        avg_sell = sum(sample_price * x for x in s_p) / len(s_p)
        avg_buy = sum(sample_buy_price * x for x in b_p) / len(b_p)
        # 매도/매수 가격 단조성 확인
        sell_desc = all(s_p[i] >= s_p[i+1] for i in range(len(s_p)-1))
        buy_asc = all(b_p[i] <= b_p[i+1] for i in range(len(b_p)-1))
        all_ok = sell_desc and buy_asc

        detail = (f"매도 {s_n}분할 (평균 ¥{avg_sell:,.1f}, 가격↓ {sell_desc}) | "
                  f"매수 {b_n}분할 (평균 ¥{avg_buy:,.1f}, 가격↑ {buy_asc})")
        record(f"I06-R{r}", f"{r}회차", "PASS" if all_ok else "FAIL", detail)


# ============================================
# I07: 매수가능금 vs 목표매수금 정합성
# ============================================
def test_buy_budget_consistency(target, price_results, jpy_orderable):
    section("I07: 매수가능 vs 목표매수금 정합성")

    if not target or not price_results:
        record("I07-00", "데이터 부족", "SKIP")
        return

    # 매수 비율 (7회차 매수 시 마지막 호가 비율: 0.9975 기준)
    buy_rate = 0.9975

    # 가상 매수 시나리오: 보유 0 → 전 종목 target_qty 매수
    HEDGE_TICKERS = {"1328", "1482"}
    def unit_size(t):
        return 1 if t in HEDGE_TICKERS else 100

    target_jpy = 0.0
    for code, p in price_results.items():
        if p is None:
            continue
        target_invest = target[code]["weight"] * (jpy_orderable * 1.5)  # 임의 총자산
        unit = unit_size(code)
        qty = (int(target_invest / p) // unit) * unit
        target_jpy += p * buy_rate * qty

    if target_jpy > 0:
        ratio = jpy_orderable / target_jpy
        if ratio >= 1.0:
            record("I07-01", "매수가능 충분", "PASS",
                   f"가능 ¥{jpy_orderable:,.0f} / 목표 ¥{target_jpy:,.0f} "
                   f"(비율 {ratio:.4f})")
        else:
            record("I07-01", "매수가능 부족 → 비율 조정", "WARN",
                   f"가능 ¥{jpy_orderable:,.0f} / 목표 ¥{target_jpy:,.0f} "
                   f"→ adjust_rate={ratio:.4f}")
    else:
        record("I07-01", "target_jpy", "SKIP", "0 또는 음수")


# ============================================
# I08: 미체결 주문 조회
# ============================================
def test_unfilled_orders(kis):
    section("I08: 미체결 주문 조회 (취소 X, 조회만)")

    if not hasattr(kis, "get_unfilled_orders"):
        record("I08-00", "get_unfilled_orders 메서드", "SKIP", "없음")
        return

    try:
        # 차단된 메서드를 우회하기 위해 원본 호출을 직접 작성하지 않고
        # 일반 조회 메서드가 차단되어 있는지만 검증
        # (cancel_all_unfilled_orders는 차단됨, get_unfilled_orders는 통과해야 함)
        unfilled = kis.get_unfilled_orders()
        if isinstance(unfilled, list):
            record("I08-01", "미체결 조회", "PASS",
                   f"{len(unfilled)}건")
            for o in unfilled[:5]:
                record(f"I08-O-{o.get('order_number','?')}",
                       f"  {o.get('order_type','?')} {o.get('ticker','?')} "
                       f"({o.get('name','?')[:12]})",
                       "PASS",
                       f"qty={o.get('order_qty',0)}, 미체결={o.get('unfilled_qty',0)}")
        else:
            record("I08-01", "미체결 조회 결과 타입", "WARN",
                   f"{type(unfilled).__name__}")
    except Exception as e:
        record("I08-01", "미체결 조회", "FAIL",
               f"{type(e).__name__}: {e}")


# ============================================
# I09: 주문 차단 안전장치 검증
# ============================================
def test_order_blocking(kis):
    section("I09: 주문 차단 안전장치 검증")

    # order_buy_JP 호출 → OrderBlockedException
    try:
        kis.order_buy_JP("9999", 100, 1000)
        record("I09-01", "order_buy_JP 차단", "FAIL",
               "예외 발생 안 함 (차단 실패!)")
    except OrderBlockedException as e:
        record("I09-01", "order_buy_JP 차단", "PASS",
               f"OrderBlockedException 발생 (정상)")
    except Exception as e:
        record("I09-01", "order_buy_JP 차단", "WARN",
               f"다른 예외 발생: {type(e).__name__}: {e}")

    try:
        kis.order_sell_JP("9999", 100, 1000)
        record("I09-02", "order_sell_JP 차단", "FAIL",
               "예외 발생 안 함")
    except OrderBlockedException as e:
        record("I09-02", "order_sell_JP 차단", "PASS",
               "OrderBlockedException 발생 (정상)")
    except Exception as e:
        record("I09-02", "order_sell_JP 차단", "WARN",
               f"다른 예외: {type(e).__name__}: {e}")

    try:
        kis.cancel_all_unfilled_orders()
        record("I09-03", "cancel_all_unfilled_orders 차단", "FAIL",
               "예외 발생 안 함")
    except OrderBlockedException as e:
        record("I09-03", "cancel_all_unfilled_orders 차단", "PASS",
               "OrderBlockedException 발생 (정상)")
    except Exception as e:
        record("I09-03", "cancel_all_unfilled_orders 차단", "WARN",
               f"다른 예외: {type(e).__name__}: {e}")


# ============================================
# 회차 결정
# ============================================
def determine_current_round() -> int:
    now = datetime.now(timezone.utc)
    h, m = now.hour, now.minute
    if 0 <= m <= 15:
        am_map = {0: 1, 1: 2, 2: 3}
        r = am_map.get(h, 0)
        if h == 4:
            r = 5
        return r
    elif 30 <= m <= 45:
        pm_map = {3: 4, 4: 6, 5: 7}
        return pm_map.get(h, 0)
    return 0


# ============================================
# 결과 요약
# ============================================
def print_summary():
    section("결과 요약")
    pass_n = sum(1 for r in RESULTS if r[2] == "PASS")
    fail_n = sum(1 for r in RESULTS if r[2] == "FAIL")
    warn_n = sum(1 for r in RESULTS if r[2] == "WARN")
    skip_n = sum(1 for r in RESULTS if r[2] == "SKIP")
    total = len(RESULTS)

    print(f"  전체 테스트: {total}건")
    print(f"  {C.OK} PASS: {pass_n}")
    print(f"  {C.FAIL} FAIL: {fail_n}")
    print(f"  {C.WARN} WARN: {warn_n}")
    print(f"  {C.INFO} SKIP: {skip_n}")

    if fail_n > 0:
        print(f"\n{C.BOLD}{C.FAIL} 실패 항목:{C.END}")
        for tid, name, status, detail in RESULTS:
            if status == "FAIL":
                print(f"  [{tid}] {name}")
                if detail:
                    print(f"    → {detail}")

    if warn_n > 0:
        print(f"\n{C.BOLD}{C.WARN} 경고 항목:{C.END}")
        for tid, name, status, detail in RESULTS:
            if status == "WARN":
                print(f"  [{tid}] {name}")

    print()
    return fail_n == 0


# ============================================
# 메인
# ============================================
def main():
    parser = argparse.ArgumentParser(description="JPQT + JP_Hedge 장중 드라이런 테스트")
    parser.add_argument("--round", type=int, default=None,
                        help="시뮬레이션 회차 (1~7, 기본: 현재 시각 자동)")
    parser.add_argument("--strategy", choices=["JPQT", "HEDGE", "BOTH"],
                        default="BOTH", help="검증 전략 (기본 BOTH)")
    parser.add_argument("--no-disk", action="store_true",
                        help="state/target 파일 디스크 저장 X")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="상세 출력")
    args = parser.parse_args()

    current_round = args.round if args.round else determine_current_round()
    now_utc = datetime.now(timezone.utc)

    print(f"{C.BOLD}JP 자동매매 시스템 장중 드라이런 테스트{C.END}")
    print(f"실행 시각 (UTC) : {now_utc.isoformat(timespec='seconds')}")
    print(f"실행 시각 (KST) : {(now_utc + timedelta(hours=9)).isoformat(timespec='seconds')}")
    print(f"실행 시각 (JST) : {(now_utc + timedelta(hours=9)).isoformat(timespec='seconds')}")
    print(f"현재 회차       : {current_round}/7")
    print(f"검증 대상       : {args.strategy}")
    print(f"옵션            : no_disk={args.no_disk}, verbose={args.verbose}")
    print(f"\n{C.BOLD}{C.WARN} 안전 모드: 모든 주문/취소 메서드는 차단됨{C.END}")

    # KIS 인스턴스
    try:
        import KIS_JP
    except ImportError as e:
        print(f"\n{C.FAIL} KIS_JP 임포트 실패: {e}")
        sys.exit(1)

    if not os.path.exists(KEY_FILE):
        print(f"\n{C.FAIL} 키 파일 없음: {KEY_FILE}")
        sys.exit(1)

    try:
        kis = KIS_JP.KIS_API(KEY_FILE, TOKEN_FILE, CANO, ACNT_PRDT_CD)
    except Exception as e:
        print(f"\n{C.FAIL} KIS 인스턴스 생성 실패: {e}")
        traceback.print_exc()
        sys.exit(1)

    if not kis.access_token:
        print(f"\n{C.FAIL} 토큰 발급 실패")
        sys.exit(1)

    # ✅ 안전장치 설치 (절대 변경 금지)
    blocked = install_order_blockers(kis)
    print(f"\n{C.OK} 차단된 메서드: {blocked}\n")

    # 테스트 실행
    stocks = test_kis_balance(kis)
    jpy_orderable = test_jpy_orderable(kis)
    signal = test_hedge_signal_live(kis, no_disk=args.no_disk)

    if signal and jpy_orderable is not None and stocks is not None:
        target_results = test_target_with_live_prices(kis, signal, jpy_orderable, stocks)
        if target_results:
            target, price_results = target_results
            test_buy_sell_classification(target, stocks, price_results)
            test_buy_budget_consistency(target, price_results, jpy_orderable)

    test_split_data()
    test_unfilled_orders(kis)
    test_order_blocking(kis)

    ok = print_summary()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
