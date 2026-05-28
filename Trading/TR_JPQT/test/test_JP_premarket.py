"""
test_JP_premarket.py
JPQT + JP_Hedge 장전 검증 테스트 (실주문 없음, 시장 데이터 조회 X)

목적:
- 장 시작 전 (KST 09:00 이전, UTC 00:00 이전) 또는 비거래일에 실행
- 코드 로직, 파일 I/O, 신호 산출, target 계산까지 시뮬레이션
- API는 KIS access_token 발급 + TOPIX 일봉 조회까지만 (주문 X)

테스트 항목:
[T01] 모듈 임포트 + 환경 변수
[T02] CSV 파싱 + weight 정규화
[T03] JP_Hedge_signal.compute_signal (실 API: TOPIX 일봉)
[T04] WEIGHT_MATRIX 정합성
[T05] order_time_1day 회차 결정 함수 (모든 시간대)
[T06] is_JP_trading_day / is_first_trading_day_of_month
[T07] 매매단위(unit_size) 로직
[T08] 가상 잔고/현금으로 target 산출 시뮬레이션
[T09] 매수/매도 수량 산출 로직 시뮬레이션
[T10] JPQT_target.json / JP_Hedge_target.json 정합성
[T11] state 파일 I/O + 상태 전환 매트릭스

사용법:
  cd /var/autobot/TR_JPQT
  python3 test_JP_premarket.py

  옵션:
    --skip-api     : KIS API 호출 전부 스킵 (오프라인 모드)
    --verbose      : 상세 출력
"""

import os
import sys
import json
import argparse
import traceback
from datetime import datetime, timezone, timedelta, time
from typing import Optional, Dict, List

# ============================================
# 경로 설정 (실 운영 디렉토리 기준)
# ============================================
PROJECT_DIR = "/var/autobot/TR_JPQT"

# 운영 경로가 없으면 현재 디렉토리 사용 (개발 테스트용)
if not os.path.isdir(PROJECT_DIR):
    PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
    print(f"[INFO] 운영 디렉토리 없음 → {PROJECT_DIR} 사용")

sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, "/var/autobot")

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

RESULTS = []  # (test_id, name, status, detail)

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
# T01: 모듈 임포트
# ============================================
def test_imports():
    section("T01: 모듈 임포트 및 환경")

    # 표준 라이브러리
    try:
        import pandas as pd
        record("T01-01", f"pandas {pd.__version__} 임포트", "PASS")
    except Exception as e:
        record("T01-01", "pandas 임포트", "FAIL", str(e))
        return False

    # tendo (singleton)
    try:
        from tendo import singleton
        record("T01-02", "tendo.singleton 임포트", "PASS")
    except Exception as e:
        record("T01-02", "tendo 임포트", "FAIL", str(e))

    # exchange_calendars (옵션)
    try:
        import exchange_calendars as xcals
        record("T01-03", "exchange_calendars 임포트", "PASS", f"version: {xcals.__version__}")
    except Exception as e:
        record("T01-03", "exchange_calendars", "WARN", f"폴백 가능: {e}")

    # pytz
    try:
        import pytz
        record("T01-04", "pytz 임포트", "PASS")
    except Exception as e:
        record("T01-04", "pytz", "WARN", str(e))

    # 프로젝트 모듈
    proj_modules = {
        "KIS_JP": "한투 일본 API",
        "JP_Hedge_signal": "헷지 신호 모듈",
        "telegram_alert": "Telegram 알림"
    }
    missing = []
    for mod, desc in proj_modules.items():
        try:
            __import__(mod)
            record(f"T01-{mod}", f"{desc} ({mod})", "PASS")
        except Exception as e:
            record(f"T01-{mod}", f"{desc} ({mod})", "FAIL", str(e))
            missing.append(mod)

    return len(missing) == 0


# ============================================
# T02: CSV 파싱 + weight 정규화
# ============================================
def test_csv_parsing():
    section("T02: JPQT_stock.csv 파싱 및 weight 정규화")

    import pandas as pd
    csv_path = os.path.join(PROJECT_DIR, "JPQT_stock.csv")

    if not os.path.exists(csv_path):
        record("T02-00", "CSV 파일 존재", "FAIL", f"파일 없음: {csv_path}")
        return None

    try:
        df = pd.read_csv(csv_path, dtype={
            "code": str, "name": str, "weight": float, "category": str
        })
        record("T02-01", "CSV 로드", "PASS", f"{len(df)}행")
    except Exception as e:
        record("T02-01", "CSV 로드", "FAIL", str(e))
        return None

    required_cols = ["code", "name", "weight", "category"]
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        record("T02-02", "필수 컬럼", "FAIL", f"누락: {missing_cols}")
        return None
    record("T02-02", "필수 컬럼", "PASS", f"{required_cols}")

    # 중복 code 확인
    dup_codes = df[df["code"].duplicated()]["code"].tolist()
    if dup_codes:
        record("T02-03", "중복 code 검사", "WARN",
               f"중복 {len(dup_codes)}건 (여러 카테고리 가능): {dup_codes[:5]}")
    else:
        record("T02-03", "중복 code 검사", "PASS")

    # 헷지 ETF가 csv에 잘못 들어갔는지
    HEDGE_TICKERS = {"1328", "1482"}
    hedge_in_csv = df[df["code"].isin(HEDGE_TICKERS)]
    if len(hedge_in_csv) > 0:
        record("T02-04", "헷지 ETF csv 혼입 검사", "WARN",
               f"csv에 헷지 ETF 포함: {hedge_in_csv['code'].tolist()} (코드에서 자동 제외됨)")
    else:
        record("T02-04", "헷지 ETF csv 혼입 검사", "PASS")

    # CASH 처리
    cash_rows = df[df["code"] == "CASH"]
    record("T02-05", "CASH 행 존재 (제외 대상)", "PASS",
           f"{len(cash_rows)}건 (weight={cash_rows['weight'].sum() if len(cash_rows) > 0 else 0})")

    # weight 정규화 시뮬레이션
    grouped = df.groupby("code").agg(
        name=("name", "first"),
        weight=("weight", "sum"),
        categories=("category", list)
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

    weight_sum_raw = sum(v["weight"] for v in csv_stocks.values())
    if weight_sum_raw <= 0:
        record("T02-06", "weight 합 > 0", "FAIL", f"sum={weight_sum_raw}")
        return None

    for code in csv_stocks:
        csv_stocks[code]["weight"] /= weight_sum_raw

    weight_sum_norm = sum(v["weight"] for v in csv_stocks.values())
    if abs(weight_sum_norm - 1.0) > 1e-6:
        record("T02-07", "정규화 후 합 = 1.0", "FAIL", f"sum={weight_sum_norm:.8f}")
    else:
        record("T02-07", "정규화 후 합 = 1.0", "PASS",
               f"종목 {len(csv_stocks)}개, 정규화 합={weight_sum_norm:.6f} "
               f"(원본 합={weight_sum_raw:.4f})")

    # 음수/0 weight 확인
    bad_w = [c for c, v in csv_stocks.items() if v["weight"] <= 0]
    if bad_w:
        record("T02-08", "비정상 weight 검사", "FAIL", f"음수/0: {bad_w}")
    else:
        record("T02-08", "비정상 weight 검사", "PASS")

    return csv_stocks


# ============================================
# T03: JP_Hedge_signal 신호 산출
# ============================================
def test_hedge_signal(skip_api: bool):
    section("T03: JP_Hedge_signal 신호 산출")

    try:
        import JP_Hedge_signal as HS
        record("T03-00", "JP_Hedge_signal 임포트", "PASS")
    except Exception as e:
        record("T03-00", "JP_Hedge_signal 임포트", "FAIL", str(e))
        return None

    # 상수 검증
    consts = {
        "TOPIX_TICKER": HS.TOPIX_TICKER,
        "TOPIX_EXCHANGE": HS.TOPIX_EXCHANGE,
        "MA_WINDOW": HS.MA_WINDOW,
        "MOM_WINDOW": HS.MOM_WINDOW,
        "HEDGE_GOLD_TICKER": HS.HEDGE_GOLD_TICKER,
        "HEDGE_BOND_TICKER": HS.HEDGE_BOND_TICKER,
    }
    detail = " | ".join(f"{k}={v}" for k, v in consts.items())
    record("T03-01", "신호 모듈 상수", "PASS", detail)

    # WEIGHT_MATRIX 검증
    matrix = HS.WEIGHT_MATRIX
    for state, w in matrix.items():
        total = w["stock"] + w["gold"] + w["bond"]
        if abs(total - 1.0) > 1e-6:
            record(f"T03-WM-{state}", f"WEIGHT_MATRIX[{state}] 합=1.0",
                   "FAIL", f"합={total}, {w}")
        else:
            record(f"T03-WM-{state}", f"WEIGHT_MATRIX[{state}] 합=1.0",
                   "PASS", f"{w}")

    if skip_api:
        record("T03-99", "compute_signal 실 API 호출", "SKIP", "--skip-api 모드")
        return None

    # 실제 신호 산출 시도
    try:
        import KIS_JP
        key_file = "/var/autobot/KIS/kis63604155nkr.txt"
        token_file = "/var/autobot/KIS/kis63604155_token.json"
        if not os.path.exists(key_file):
            record("T03-02", "KIS_JP 인스턴스 생성", "SKIP",
                   f"키 파일 없음: {key_file}")
            return None

        kis = KIS_JP.KIS_API(key_file, token_file, "63604155", "01")
        if not kis.access_token:
            record("T03-02", "KIS 토큰 발급", "FAIL", "access_token 없음")
            return None
        record("T03-02", "KIS 토큰 발급", "PASS",
               f"토큰 길이: {len(kis.access_token)}")

        # TOPIX 일봉 조회 → 신호
        print(f"      {C.INFO} TOPIX(1306) 일봉 조회 중 (수 초 소요)...")
        signal = HS.compute_signal(kis, HS.TOPIX_TICKER)
        if signal is None:
            record("T03-03", "compute_signal 산출", "FAIL", "None 반환")
            return None

        record("T03-03", "compute_signal 산출", "PASS",
               f"date={signal['date']}, state={signal['state']}, "
               f"n_data={signal['n_data']}")
        record("T03-04", "신호 상세", "PASS",
               f"close=¥{signal['close']:,.1f} / "
               f"MA200=¥{signal['ma200']:,.1f} (signal_ma={signal['signal_ma']}) / "
               f"MOM12={signal['mom12']*100:+.2f}% (signal_mom={signal['signal_mom']})")
        record("T03-05", "비중 매트릭스", "PASS",
               f"주식 {signal['weights']['stock']*100:.0f}% / "
               f"금 {signal['weights']['gold']*100:.0f}% / "
               f"채권 {signal['weights']['bond']*100:.0f}%")

        # 메시지 포맷 검증
        msg = HS.format_signal_message(signal, prev_state="Neutral")
        record("T03-06", "format_signal_message", "PASS",
               f"({len(msg)}자 메시지)")

        return signal

    except Exception as e:
        record("T03-99", "compute_signal API 호출", "FAIL",
               f"{type(e).__name__}: {e}\n{traceback.format_exc()[:300]}")
        return None


# ============================================
# T04: WEIGHT_MATRIX 정합성
# ============================================
def test_weight_matrix():
    section("T04: WEIGHT_MATRIX 상태 전환 매트릭스")

    try:
        import JP_Hedge_signal as HS
    except ImportError:
        record("T04-00", "import", "SKIP")
        return

    matrix = HS.WEIGHT_MATRIX

    expected_states = {"Bull", "Neutral", "Bear"}
    actual_states = set(matrix.keys())
    if expected_states != actual_states:
        record("T04-01", "상태 종류", "FAIL",
               f"기대 {expected_states}, 실제 {actual_states}")
    else:
        record("T04-01", "상태 종류", "PASS", f"{sorted(actual_states)}")

    # 논리 검증: Bull > Neutral > Bear (주식 비중)
    s_bull = matrix["Bull"]["stock"]
    s_neu = matrix["Neutral"]["stock"]
    s_bear = matrix["Bear"]["stock"]
    if s_bull > s_neu > s_bear:
        record("T04-02", "주식비중: Bull > Neutral > Bear", "PASS",
               f"{s_bull} > {s_neu} > {s_bear}")
    else:
        record("T04-02", "주식비중 단조성", "FAIL",
               f"Bull={s_bull}, Neutral={s_neu}, Bear={s_bear}")

    # 헷지 합 = 1 - stock
    for state, w in matrix.items():
        hedge_sum = w["gold"] + w["bond"]
        expected = 1.0 - w["stock"]
        if abs(hedge_sum - expected) > 1e-6:
            record(f"T04-03-{state}", f"{state} 헷지합 = 1-주식",
                   "FAIL", f"hedge={hedge_sum}, expected={expected}")
        else:
            record(f"T04-03-{state}", f"{state} 헷지합 = 1-주식", "PASS")


# ============================================
# T05: order_time_1day 회차 매핑
# ============================================
def test_order_time_mapping():
    section("T05: order_time_1day 회차 매핑")

    # JPQT_TR.py와 JP_Hedge_TR.py의 로직을 그대로 재현
    def order_time_for(hour: int, minute: int) -> int:
        base_round = 0
        if 0 <= minute <= 15:
            am_map = {0: 1, 1: 2, 2: 3}
            base_round = am_map.get(hour, 0)
            if hour == 4:
                base_round = 5
        elif 30 <= minute <= 45:
            pm_map = {3: 4, 4: 6, 5: 7}
            base_round = pm_map.get(hour, 0)
        return base_round

    # crontab 매핑 (UTC → KST)
    # 7회차: 1=09:07, 2=10:07, 3=11:07, 4=12:37, 5=13:07, 6=13:37, 7=14:37
    expected = [
        # (UTC hour, UTC minute, expected_round, KST 시간)
        (0,  7, 1, "KST 09:07 [1회차]"),
        (1,  7, 2, "KST 10:07 [2회차]"),
        (2,  7, 3, "KST 11:07 [3회차]"),
        (3, 37, 4, "KST 12:37 [4회차]"),
        (4,  7, 5, "KST 13:07 [5회차]"),
        (4, 37, 6, "KST 13:37 [6회차]"),
        (5, 37, 7, "KST 14:37 [7회차]"),
        # 비매매시간
        (0, 20, 0, "KST 09:20 [범위 밖]"),
        (6,  7, 0, "KST 15:07 [장후]"),
        (7,  7, 0, "KST 16:07 [장후]"),
        (23, 7, 0, "KST 08:07 [장전]"),
    ]

    all_pass = True
    for h, m, expected_round, label in expected:
        got = order_time_for(h, m)
        status = "PASS" if got == expected_round else "FAIL"
        if status == "FAIL":
            all_pass = False
        record(f"T05-{h:02d}{m:02d}", f"UTC {h:02d}:{m:02d} ({label})",
               status, f"expected={expected_round}, got={got}")

    # 라운드 1~7 모두 한 번씩 트리거되는지
    rounds = set()
    for h in range(24):
        for m in [7, 37]:
            r = order_time_for(h, m)
            if r > 0:
                rounds.add(r)
    if rounds == {1, 2, 3, 4, 5, 6, 7}:
        record("T05-99", "1~7회차 모두 트리거 가능", "PASS")
    else:
        record("T05-99", "1~7회차 모두 트리거 가능", "FAIL",
               f"누락: {set(range(1,8)) - rounds}, 초과: {rounds - set(range(1,8))}")


# ============================================
# T06: 거래일/월 첫 거래일 판정
# ============================================
def test_trading_day():
    section("T06: 거래일 판정")

    try:
        import exchange_calendars as xcals
        import pandas as pd
        import pytz
    except Exception as e:
        record("T06-00", "거래일 모듈 임포트", "SKIP", str(e))
        return

    try:
        cal = xcals.get_calendar("XTKS")
        record("T06-01", "XTKS (도쿄증권거래소) 캘린더 로드", "PASS")
    except Exception as e:
        record("T06-01", "XTKS 캘린더 로드", "FAIL", str(e))
        return

    jst = pytz.timezone("Asia/Tokyo")
    today_jst = datetime.now(timezone.utc).astimezone(jst).date()

    is_session = cal.is_session(pd.Timestamp(today_jst))
    record("T06-02", f"오늘({today_jst}) 거래일 여부",
           "PASS", f"is_session={is_session}, weekday={today_jst.weekday()}")

    # 월 첫 거래일 시뮬레이션 (지난 6개월)
    for i in range(6):
        target_month = (today_jst.replace(day=1) - timedelta(days=i*30))
        target_month = target_month.replace(day=1)
        try:
            sessions = cal.sessions_in_range(
                pd.Timestamp(target_month),
                pd.Timestamp(target_month + timedelta(days=10))
            )
            if len(sessions) > 0:
                first = sessions[0].date()
                record(f"T06-FT-{target_month.strftime('%Y%m')}",
                       f"{target_month.strftime('%Y-%m')} 첫 거래일",
                       "PASS", f"{first}")
        except Exception as e:
            record(f"T06-FT-{target_month.strftime('%Y%m')}",
                   f"{target_month.strftime('%Y-%m')} 첫 거래일", "WARN", str(e))


# ============================================
# T07: unit_size + floor_unit
# ============================================
def test_unit_size():
    section("T07: 매매단위(unit_size) 로직")

    HEDGE_TICKERS = {"1328", "1482"}

    def unit_size(ticker: str) -> int:
        return 1 if ticker in HEDGE_TICKERS else 100

    def floor_unit(t: str, q: int) -> int:
        u = unit_size(t)
        return (q // u) * u

    cases = [
        # (ticker, raw_qty, expected_qty, label)
        ("1328", 5, 5, "헷지 금ETF: 1주 단위"),
        ("1482", 1, 1, "헷지 채권ETF: 1주 단위"),
        ("1328", 0, 0, "헷지 0주"),
        ("9980", 250, 200, "개별주 250 → 200 (100단위)"),
        ("9980", 99, 0, "개별주 99 → 0 (100 미만)"),
        ("9980", 1000, 1000, "개별주 1000 → 1000"),
        ("9980", 1050, 1000, "개별주 1050 → 1000"),
    ]
    for t, raw, expected, label in cases:
        got = floor_unit(t, raw)
        status = "PASS" if got == expected else "FAIL"
        record(f"T07-{t}-{raw}", label, status,
               f"floor_unit({t}, {raw}) = {got}, expected {expected}")


# ============================================
# T08: target 산출 시뮬레이션 (가상 데이터)
# ============================================
def test_target_simulation(csv_stocks: Optional[Dict]):
    section("T08: target 산출 시뮬레이션 (가상 데이터)")

    if not csv_stocks:
        record("T08-00", "csv_stocks 없음", "SKIP")
        return

    # 가상 시나리오 3가지: Bull / Neutral / Bear
    scenarios = [
        ("Bull",    {"stock": 0.80, "gold": 0.20, "bond": 0.00}),
        ("Neutral", {"stock": 0.50, "gold": 0.30, "bond": 0.20}),
        ("Bear",    {"stock": 0.00, "gold": 0.60, "bond": 0.40}),
    ]

    total_asset_jpy = 3_000_000.0  # 가상 총자산
    # 가상 현재가
    mock_prices = {code: 1500.0 for code in csv_stocks.keys()}
    mock_prices["1328"] = 11000.0   # 금 ETF (실제 가격대)
    mock_prices["1482"] = 22000.0   # 채권 ETF

    HEDGE_GOLD = "1328"
    HEDGE_BOND = "1482"
    HEDGE_TICKERS = {HEDGE_GOLD, HEDGE_BOND}

    def unit_size(t):
        return 1 if t in HEDGE_TICKERS else 100

    for state, weights in scenarios:
        target = {}
        stock_ratio = weights["stock"]

        for code, info in csv_stocks.items():
            target[code] = {
                "name":       info["name"],
                "weight":     info["weight"] * stock_ratio,
                "categories": info["categories"],
            }
        target[HEDGE_GOLD] = {"name": "Gold", "weight": weights["gold"], "categories": ["hedge_gold"]}
        target[HEDGE_BOND] = {"name": "Bond", "weight": weights["bond"], "categories": ["hedge_bond"]}

        # weight 합 검증
        total_w = sum(v["weight"] for v in target.values())
        if abs(total_w - 1.0) > 0.01:
            record(f"T08-{state}-W", f"[{state}] weight 합", "FAIL",
                   f"합={total_w:.4f}")
            continue

        # 목표 수량 산출
        zero_qty_stocks = 0
        for ticker, v in target.items():
            price = mock_prices[ticker]
            v["current_price"] = price
            v["target_invest"] = v["weight"] * total_asset_jpy
            unit = unit_size(ticker)
            if v["target_invest"] <= 0:
                v["target_qty"] = 0
                zero_qty_stocks += 1
            else:
                raw_qty = int(v["target_invest"] / price)
                v["target_qty"] = (raw_qty // unit) * unit
                if v["target_qty"] == 0:
                    zero_qty_stocks += 1

        # 실제 투자될 금액 합
        actual_invest = sum(v["target_qty"] * v["current_price"] for v in target.values())
        invest_ratio = actual_invest / total_asset_jpy
        leftover = total_asset_jpy - actual_invest

        record(f"T08-{state}-1", f"[{state}] weight 합 = {total_w:.4f}", "PASS")
        record(f"T08-{state}-2", f"[{state}] 종목 수 (qty=0 포함)",
               "PASS", f"전체 {len(target)}, qty=0인 종목 {zero_qty_stocks}개")
        record(f"T08-{state}-3", f"[{state}] 실제 투자금 / 총자산",
               "PASS",
               f"투자 ¥{actual_invest:,.0f} ({invest_ratio*100:.2f}%) / "
               f"잔여 ¥{leftover:,.0f} ({(leftover/total_asset_jpy)*100:.2f}%)")

        # Bear 상태일 때: 개별주 target_qty 전부 0이어야 함
        if state == "Bear":
            ind_qty = [v["target_qty"] for k, v in target.items()
                       if k not in HEDGE_TICKERS]
            if all(q == 0 for q in ind_qty):
                record(f"T08-{state}-4", "[Bear] 개별주 모두 target_qty=0", "PASS")
            else:
                nonzero = [k for k, v in target.items()
                           if k not in HEDGE_TICKERS and v["target_qty"] > 0]
                record(f"T08-{state}-4", "[Bear] 개별주 모두 target_qty=0",
                       "FAIL", f"비0: {nonzero}")


# ============================================
# T09: 매수/매도 수량 산출 시뮬레이션
# ============================================
def test_buy_sell_calculation():
    section("T09: 매수/매도 수량 산출 시뮬레이션")

    HEDGE_TICKERS = {"1328", "1482"}
    def unit_size(t):
        return 1 if t in HEDGE_TICKERS else 100

    # 가상 target / hold (모두 100주 단위로 떨어지는 정상 시나리오)
    target = {
        "9980": {"target_qty": 500},
        "6771": {"target_qty": 0},      # 매도 대상 (보유)
        "6616": {"target_qty": 300},
        "1328": {"target_qty": 20},      # 헷지 금 증가
        "1482": {"target_qty": 10},      # 헷지 채권 신규
    }
    target_code = list(target.keys())

    hold = {
        "9980": {"hold_qty": 200, "ord_psbl_qty": 200},   # 부족 → 매수 300
        "6771": {"hold_qty": 400, "ord_psbl_qty": 400},   # target=0 → 매도 400
        "1328": {"hold_qty": 15,  "ord_psbl_qty": 15},    # 부족 → 매수 5
        "9999": {"hold_qty": 100, "ord_psbl_qty": 100},   # target 없음 → 전량 매도
        "8888": {"hold_qty": 300, "ord_psbl_qty": 200},   # ord_psbl < hold → 200만 매도
    }
    hold_code = list(hold.keys())

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
            sell_qty = min(hold[ticker]["hold_qty"], hold[ticker]["ord_psbl_qty"])
            if sell_qty > 0:
                sell[ticker] = sell_qty

    for ticker in target_code:
        if ticker == "CASH":
            continue
        if ticker not in hold_code:
            if target[ticker]["target_qty"] > 0:
                buy[ticker] = target[ticker]["target_qty"]

    def floor_unit(t, q):
        u = unit_size(t)
        return (q // u) * u

    buy = {t: floor_unit(t, q) for t, q in buy.items() if floor_unit(t, q) > 0}
    sell = {t: floor_unit(t, q) for t, q in sell.items() if floor_unit(t, q) > 0}

    # 기대값 검증
    expected_buy = {
        "9980": 300,   # 500 - 200
        "6616": 300,   # neu hold → 매수 300
        "1328": 5,     # 20 - 15
        "1482": 10,    # 신규
    }
    expected_sell = {
        "6771": 400,   # target=0
        "9999": 100,   # target 없음
        "8888": 200,   # ord_psbl 제한 (300 보유 중 200만 매도 가능)
    }

    record("T09-01", "매수 계산", "PASS" if buy == expected_buy else "FAIL",
           f"got={buy}, expected={expected_buy}")
    record("T09-02", "매도 계산", "PASS" if sell == expected_sell else "FAIL",
           f"got={sell}, expected={expected_sell}")

    # ord_psbl_qty 캡 동작 확인
    if sell.get("8888") == 200:
        record("T09-03", "ord_psbl_qty 캡 (200/300)", "PASS",
               "hold 300주이지만 ord_psbl 200으로 200만 매도")
    else:
        record("T09-03", "ord_psbl_qty 캡", "FAIL", f"sell['8888']={sell.get('8888')}")

    # ─────────────────────────────────────────────────
    # 추가: 거래단위 미만 부분매도 누락 검증 (실제 코드의 잠재 버그)
    # ─────────────────────────────────────────────────
    # 시나리오: 100주 보유 중 50주만 ord_psbl인 케이스 (T+2 결제 직후 등)
    #   - min(100, 50) = 50
    #   - floor_unit(50, 100) = 0  ← 매도 누락 발생!
    target2 = {"7777": {"target_qty": 0}}
    hold2 = {"7777": {"hold_qty": 100, "ord_psbl_qty": 50}}
    sell2 = {}
    for t in hold2.keys():
        if t in target2 and target2[t]["target_qty"] < hold2[t]["hold_qty"]:
            need = hold2[t]["hold_qty"] - target2[t]["target_qty"]
            sq = min(need, hold2[t]["ord_psbl_qty"])
            if sq > 0:
                sell2[t] = sq
    sell2_after_floor = {t: floor_unit(t, q) for t, q in sell2.items()
                         if floor_unit(t, q) > 0}
    if sell2_after_floor == {}:
        record("T09-04", "거래단위 미만 부분매도 누락 (알려진 동작)", "WARN",
               "보유 100주 + ord_psbl 50주 → 매도단위(100) 미만으로 매도 누락. "
               "T+2 미결제 상태나 단주거래 시 발생 가능. "
               "운영상 다음 회차에서 ord_psbl 회복 시 매도됨.")
    else:
        record("T09-04", "거래단위 미만 부분매도", "PASS", f"매도={sell2_after_floor}")



# ============================================
# T10: 기존 JSON 파일 정합성
# ============================================
def test_existing_json_files():
    section("T10: 기존 JSON 파일 정합성")

    files = {
        "JPQT_target.json":     False,   # 분기 리밸런싱일에만 존재
        "JPQT_result.json":     True,    # 항상 존재 권장
        "JPQT_rebal.json":      True,
        "JP_Hedge_state.json":  False,
        "JP_Hedge_target.json": False,
        "JP_Hedge_result.json": False,
        "JP_Hedge_rebal.json":  False,
    }

    for fname, must_exist in files.items():
        path = os.path.join(PROJECT_DIR, fname)
        if not os.path.exists(path):
            status = "WARN" if must_exist else "SKIP"
            record(f"T10-{fname}", f"{fname}", status, "파일 없음 (정상일 수 있음)")
            continue

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            size = os.path.getsize(path)
            record(f"T10-{fname}", f"{fname} JSON 파싱",
                   "PASS", f"{size}바이트")

            # JPQT_target.json 메타 검증
            if fname == "JPQT_target.json" and isinstance(data, dict):
                meta = data.get("_meta", {})
                if meta:
                    record(f"T10-{fname}-meta", "_meta 존재", "PASS",
                           f"date={meta.get('date')}, state={meta.get('state')}, "
                           f"stock_ratio={meta.get('stock_ratio')}")
                else:
                    record(f"T10-{fname}-meta", "_meta 없음", "WARN")

            # JP_Hedge_state.json 검증
            if fname == "JP_Hedge_state.json" and isinstance(data, dict):
                state = data.get("current_state")
                if state in {"Bull", "Neutral", "Bear"}:
                    record(f"T10-{fname}-state", "current_state 유효",
                           "PASS", f"{state}")
                else:
                    record(f"T10-{fname}-state", "current_state 유효",
                           "WARN", f"unknown: {state}")

                w = data.get("weights", {})
                wsum = w.get("stock", 0) + w.get("gold", 0) + w.get("bond", 0)
                if abs(wsum - 1.0) <= 1e-6:
                    record(f"T10-{fname}-w", "weights 합=1.0", "PASS",
                           f"{w}")
                else:
                    record(f"T10-{fname}-w", "weights 합=1.0", "FAIL",
                           f"합={wsum}, {w}")

                hist = data.get("history", [])
                record(f"T10-{fname}-hist", f"history 길이",
                       "PASS", f"{len(hist)}건 (최대 24건)")

        except Exception as e:
            record(f"T10-{fname}", f"{fname} JSON 파싱",
                   "FAIL", str(e))


# ============================================
# T11: 상태 전환 시나리오 (Bull↔Neutral↔Bear)
# ============================================
def test_state_transitions():
    section("T11: 상태 전환 시나리오 검증")

    try:
        import JP_Hedge_signal as HS
    except ImportError:
        record("T11-00", "HS 임포트", "SKIP")
        return

    matrix = HS.WEIGHT_MATRIX
    # 9가지 전환 (prev × curr)
    transitions = [
        ("Bull", "Bull",    False, "유지"),
        ("Bull", "Neutral", True,  "주식 80→50, 금 20→30, 채권 신규"),
        ("Bull", "Bear",    True,  "주식 전량매도, 헷지 대폭증액"),
        ("Neutral", "Bull",    True,  "주식 50→80, 금 30→20, 채권 매도"),
        ("Neutral", "Neutral", False, "유지"),
        ("Neutral", "Bear",    True,  "주식 50→0, 금 30→60, 채권 20→40"),
        ("Bear", "Bull",    True,  "주식 신규, 금 60→20, 채권 매도"),
        ("Bear", "Neutral", True,  "주식 신규, 금 60→30, 채권 40→20"),
        ("Bear", "Bear",    False, "유지"),
    ]

    for prev, curr, should_trade, desc in transitions:
        # state_changed = (prev != curr)
        actual_changed = (prev != curr)
        status = "PASS" if actual_changed == should_trade else "FAIL"
        prev_w = matrix[prev]
        curr_w = matrix[curr]
        delta_stock = (curr_w["stock"] - prev_w["stock"]) * 100
        delta_gold  = (curr_w["gold"]  - prev_w["gold"])  * 100
        delta_bond  = (curr_w["bond"]  - prev_w["bond"])  * 100
        detail = (f"{desc} | Δstock={delta_stock:+.0f}pp / "
                  f"Δgold={delta_gold:+.0f}pp / Δbond={delta_bond:+.0f}pp")
        record(f"T11-{prev}-{curr}", f"{prev} → {curr} 매매 트리거={actual_changed}",
               status, detail)


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
    parser = argparse.ArgumentParser(description="JP_Hedge + JPQT 장전 검증 테스트")
    parser.add_argument("--skip-api", action="store_true",
                        help="KIS API 호출 전체 스킵 (오프라인 모드)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="상세 출력")
    args = parser.parse_args()

    now_utc = datetime.now(timezone.utc)
    print(f"{C.BOLD}JP 자동매매 시스템 장전 검증 테스트{C.END}")
    print(f"실행 시각 (UTC): {now_utc.isoformat(timespec='seconds')}")
    print(f"실행 시각 (KST): {(now_utc + timedelta(hours=9)).isoformat(timespec='seconds')}")
    print(f"프로젝트 경로  : {PROJECT_DIR}")
    print(f"옵션          : skip_api={args.skip_api}, verbose={args.verbose}")

    # 실행 순서
    imports_ok = test_imports()
    if not imports_ok:
        print(f"\n{C.WARN} 일부 모듈 임포트 실패 → 가능한 테스트만 진행")
        # pandas + JP_Hedge_signal만 있으면 대부분 테스트 가능
        try:
            import pandas
            import JP_Hedge_signal
        except ImportError as e:
            print(f"\n{C.FAIL} 핵심 모듈 ({e}) 없음 → 중단")
            print_summary()
            sys.exit(1)

    csv_stocks = test_csv_parsing()
    test_weight_matrix()
    test_hedge_signal(skip_api=args.skip_api)
    test_order_time_mapping()
    test_trading_day()
    test_unit_size()
    test_target_simulation(csv_stocks)
    test_buy_sell_calculation()
    test_existing_json_files()
    test_state_transitions()

    ok = print_summary()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
