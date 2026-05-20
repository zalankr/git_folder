#!/usr/bin/env python3
"""
KRQT_TR.py 사전 검증 스크립트

실행 환경: EC2 (실제 운영 환경) 또는 동일 디렉터리 구조
실행 시점: 1회차/8회차 실행 직전 (KST 09:00 이전) — 장중 실행 금지
실행 방법: python3 KRQT_TR_check.py

검증 항목:
  [1] 정적 검증 (코드 자체)
      - 파이썬 문법 (py_compile)
      - 위험 패턴 (sys.exit이 매수/매도 루프 안에 있는지)
      - 행 372의 잘못된 target[i] 참조 잔존 여부
      - suspended_codes 로드 로직 존재 여부

  [2] 파일 시스템 검증
      - 필수 파일 존재 (KRQT_day.json, KRQT_stock.csv, KIS keys)
      - suspended_codes.json 형식
      - 디렉터리 쓰기 권한

  [3] CSV vs suspended_codes 정합성
      - 거래정지 종목이 CSV에 실제 존재하는지
      - 비중(weight) 합계 1.0 확인

  [4] KIS API 연결 검증
      - 토큰 유효성
      - 거래일 확인
      - 잔고 조회 가능
      - 주문가능현금 조회 가능

  [5] 거래정지 종목 실거래 시뮬레이션
      - suspended_codes 종목 각각에 대해 현재가 조회 시도
      - 매도가능수량 확인
      - 만약 매도/매수 시도된다면 어떻게 처리될지 추적

  [6] 자산 계산 사전 시뮬레이션
      - 거래정지 종목 평가금 합계
      - effective_asset 산출
      - target_qty 분포 시뮬레이션
      - adjust_rate 예측

주의:
  - 실제 주문은 절대 실행하지 않음 (조회 API만 사용)
  - 실행 후 텔레그램 알림 발송 (선택)
"""
import sys
import os
import json
import time
import traceback
import re
from datetime import datetime
from typing import Dict, List, Tuple

# ============================================================================
# 설정
# ============================================================================
KRQT_TR_PATH         = "/var/autobot/TR_KRQT/KRQT_TR.py"
KRQT_DAY_PATH        = "/var/autobot/TR_KRQT/KRQT_day.json"
KRQT_STOCK_PATH      = "/var/autobot/TR_KRQT/KRQT_stock.csv"
KRQT_SUSPENDED_PATH  = "/var/autobot/TR_KRQT/suspended_codes.json"
KRQT_TARGET_PATH     = "/var/autobot/TR_KRQT/KRQT_target.json"
KIS_KEY_PATH         = "/var/autobot/KIS/kis63604155nkr.txt"
KIS_TOKEN_PATH       = "/var/autobot/KIS/kis63604155_token.json"
CANO                 = "63604155"
ACNT_PRDT_CD         = "01"

# 출력 색상
COLOR_OK   = "\033[92m"   # 녹색
COLOR_WARN = "\033[93m"   # 노랑
COLOR_FAIL = "\033[91m"   # 빨강
COLOR_END  = "\033[0m"

# 결과 집계
result_summary = {
    "ok":   [],
    "warn": [],
    "fail": []
}

def log_ok(msg: str):
    print(f"{COLOR_OK}[ OK ]{COLOR_END} {msg}")
    result_summary["ok"].append(msg)

def log_warn(msg: str):
    print(f"{COLOR_WARN}[WARN]{COLOR_END} {msg}")
    result_summary["warn"].append(msg)

def log_fail(msg: str):
    print(f"{COLOR_FAIL}[FAIL]{COLOR_END} {msg}")
    result_summary["fail"].append(msg)

def section(title: str):
    print(f"\n{'='*72}")
    print(f"  {title}")
    print(f"{'='*72}")


# ============================================================================
# [1] 정적 검증
# ============================================================================
def check_static_code():
    section("[1] 정적 코드 검증")

    # 파일 존재
    if not os.path.exists(KRQT_TR_PATH):
        log_fail(f"KRQT_TR.py 파일 없음: {KRQT_TR_PATH}")
        return
    log_ok(f"KRQT_TR.py 파일 존재")

    # 1-1. 문법 검사
    import py_compile
    try:
        py_compile.compile(KRQT_TR_PATH, doraise=True)
        log_ok("파이썬 문법 정상")
    except py_compile.PyCompileError as e:
        log_fail(f"파이썬 문법 오류: {e}")
        return

    # 1-2. 소스 코드 읽기
    with open(KRQT_TR_PATH, 'r', encoding='utf-8') as f:
        source = f.read()
    lines = source.split('\n')

    # 1-3. suspended_codes 로드 로직 존재 여부
    if "suspended_codes = set()" in source and "KRQT_suspended_path" in source:
        log_ok("suspended_codes 로드 로직 존재")
    else:
        log_fail("suspended_codes 로드 로직 누락 → 거래정지 종목 인식 불가")

    # 1-4. 행 372 버그 패턴 (잘못된 target[i] 참조)
    #     매도 산출 분기 안에 target[i] 참조가 있으면 NameError 발생
    bug_pattern = re.compile(r"target\[i\]\['target_qty'\]\s*!=\s*0")
    bug_lines = []
    for idx, line in enumerate(lines, 1):
        if bug_pattern.search(line):
            bug_lines.append((idx, line.strip()))
    if bug_lines:
        for ln, txt in bug_lines:
            log_fail(f"행 {ln}: 잘못된 target[i] 참조 잔존 → {txt}")
    else:
        log_ok("매도 산출 블록의 target[i] 버그 제거됨")

    # 1-5. 매도/매수 루프 안의 sys.exit 검출
    #     안전한 sys.exit: 초기화/잔고조회/매수가능금 조회 등 메인 흐름
    #     위험한 sys.exit: for 루프 안에서 호출되면 거래정지 종목 1개로 전체 중단
    in_for_loop = False
    indent_for = 0
    suspect_exits = []
    for idx, line in enumerate(lines, 1):
        stripped = line.lstrip()
        if not stripped:
            continue
        indent = len(line) - len(stripped)
        # for 루프 진입 (매도/매수 관련)
        if stripped.startswith("for code") or stripped.startswith("for ticker"):
            in_for_loop = True
            indent_for = indent
            continue
        if in_for_loop and indent <= indent_for and stripped:
            in_for_loop = False
        if in_for_loop and "sys.exit" in stripped and not stripped.startswith("#"):
            suspect_exits.append((idx, line.strip()))

    if suspect_exits:
        for ln, txt in suspect_exits:
            log_warn(f"행 {ln}: for 루프 내 sys.exit 의심 → {txt}")
    else:
        log_ok("매도/매수 for 루프 안에 sys.exit 없음")

    # 1-6. hold 변수 정의 위치 확인
    #     target 산출 분기(round==1 or 8) 안에서 hold가 참조되는데,
    #     hold가 분기 이전에 정의되어 있어야 함
    hold_first_def = None
    hold_use_in_target_branch = False
    target_branch_line = None
    for idx, line in enumerate(lines, 1):
        if "hold = {}" in line and hold_first_def is None:
            hold_first_def = idx
        if "if order['round'] == 1 or order['round'] == 8" in line:
            target_branch_line = idx
        if target_branch_line and idx > target_branch_line and "hold.get(i" in line:
            hold_use_in_target_branch = True
            hold_use_line = idx
            break

    if hold_first_def and target_branch_line:
        if hold_first_def < target_branch_line:
            log_ok(f"hold 정의(행 {hold_first_def})가 target 분기(행 {target_branch_line}) 이전 → NameError 방지")
        else:
            if hold_use_in_target_branch:
                log_fail(f"hold 정의(행 {hold_first_def})가 target 분기(행 {target_branch_line}) 이후 → 행 {hold_use_line}에서 NameError 발생")
            else:
                log_warn(f"hold 정의가 target 분기 이후이나, 분기 내부에서 사용되지 않음")

    # 1-7. price_cache 도입 여부 (API 중복 호출 방지)
    if "price_cache" in source:
        log_ok("price_cache 도입 → 거래정지 재산출 시 API 중복 호출 방지")
    else:
        log_warn("price_cache 미도입 → API 중복 호출 가능 (속도 저하만, 동작은 정상)")


# ============================================================================
# [2] 파일 시스템 검증
# ============================================================================
def check_filesystem():
    section("[2] 파일 시스템 검증")

    files = {
        "KRQT_day.json":        KRQT_DAY_PATH,
        "KRQT_stock.csv":       KRQT_STOCK_PATH,
        "suspended_codes.json": KRQT_SUSPENDED_PATH,
        "KIS API Key":          KIS_KEY_PATH,
    }
    for name, path in files.items():
        if os.path.exists(path):
            size = os.path.getsize(path)
            log_ok(f"{name} 존재 ({size} bytes) — {path}")
        else:
            if name == "suspended_codes.json":
                log_warn(f"{name} 없음 → 거래정지 사전등록 없이 진행됨 — {path}")
            else:
                log_fail(f"{name} 없음 — {path}")

    # 디렉터리 쓰기 권한
    target_dir = os.path.dirname(KRQT_TARGET_PATH)
    if os.access(target_dir, os.W_OK):
        log_ok(f"디렉터리 쓰기 권한 정상: {target_dir}")
    else:
        log_fail(f"디렉터리 쓰기 권한 없음: {target_dir}")

    # KRQT_day.json 내용
    try:
        with open(KRQT_DAY_PATH, 'r', encoding='utf-8') as f:
            day_data = json.load(f)
        day = day_data.get("day")
        if day in (1, 2):
            log_ok(f"KRQT_day.json: day={day} (정상)")
        else:
            log_fail(f"KRQT_day.json: day={day} (1 또는 2 아님)")
    except Exception as e:
        log_fail(f"KRQT_day.json 읽기 실패: {e}")


# ============================================================================
# [3] CSV vs suspended_codes 정합성
# ============================================================================
def check_csv_suspended_consistency() -> Tuple[Dict, set]:
    section("[3] CSV ↔ suspended_codes 정합성")

    if not os.path.exists(KRQT_STOCK_PATH):
        log_fail("KRQT_stock.csv 없음 → 검증 불가")
        return {}, set()

    try:
        import pandas as pd
        df = pd.read_csv(KRQT_STOCK_PATH, dtype={
            "code": str, "name": str, "weight": float, "category": str
        })
    except Exception as e:
        log_fail(f"KRQT_stock.csv 파싱 실패: {e}")
        return {}, set()

    df["code"] = df["code"].str[1:]   # 'A' 접두사 제거

    # 중복 종목 비중 합산
    grouped = df.groupby("code")["weight"].sum().to_dict()
    log_ok(f"CSV 종목 수: {len(grouped)}개 (중복합산 후)")

    # weight 합계
    total_weight = sum(grouped.values())
    if abs(total_weight - 1.0) < 0.01:
        log_ok(f"weight 합계 = {total_weight:.4f} (1.0±0.01 범위)")
    else:
        log_warn(f"weight 합계 = {total_weight:.4f} (1.0과 차이 큼 → 코드는 진행하지만 경고 발생)")

    # suspended_codes 로드
    suspended = set()
    if os.path.exists(KRQT_SUSPENDED_PATH):
        try:
            with open(KRQT_SUSPENDED_PATH, 'r', encoding='utf-8') as f:
                sc_data = json.load(f)
            for c in sc_data.get("suspended", []):
                c_str = str(c).strip()
                if c_str.startswith("A") and len(c_str) == 7:
                    c_str = c_str[1:]
                if c_str:
                    suspended.add(c_str)
            log_ok(f"suspended_codes: {len(suspended)}개 — {sorted(suspended)}")
        except Exception as e:
            log_fail(f"suspended_codes.json 파싱 실패: {e}")

    # suspended 종목이 CSV에 있는지
    csv_codes = set(grouped.keys())
    for code in suspended:
        if code in csv_codes:
            log_ok(f"  ✓ {code}: CSV에 존재 (weight={grouped[code]:.4f})")
        else:
            log_warn(f"  ⚠ {code}: CSV에 없음 → 보유분만 매도 시도되나, target에 없으면 전량 매도 대상")

    # CSH 종목 확인
    if "CASH" in csv_codes:
        log_ok(f"CASH 종목 존재 (weight={grouped['CASH']:.4f})")
    else:
        log_warn("CASH 종목 없음 → 전 종목 100% 투자")

    return grouped, suspended


# ============================================================================
# [4] KIS API 연결 검증
# ============================================================================
def check_kis_api():
    section("[4] KIS API 연결 검증")

    # KIS_KR 모듈 임포트
    sys.path.insert(0, "/var/autobot/TR_KRQT")
    sys.path.insert(0, "/var/autobot")
    try:
        import KIS_KR
    except Exception as e:
        log_fail(f"KIS_KR 모듈 임포트 실패: {e}")
        return None

    # API 인스턴스 생성
    try:
        KIS = KIS_KR.KIS_API(KIS_KEY_PATH, KIS_TOKEN_PATH, CANO, ACNT_PRDT_CD)
    except SystemExit:
        log_fail("KIS API 인스턴스 생성 시 sys.exit (토큰/키 파일 문제)")
        return None
    except Exception as e:
        log_fail(f"KIS API 인스턴스 생성 실패: {e}")
        return None

    if KIS.access_token:
        log_ok(f"토큰 발급 정상 (앞 10자리: {KIS.access_token[:10]}...)")
    else:
        log_fail("토큰 없음")
        return None

    # 거래일 확인
    try:
        is_trading = KIS.is_KR_trading_day()
        if is_trading:
            log_ok(f"오늘({datetime.now().strftime('%Y-%m-%d')}) 거래일")
        else:
            log_warn(f"오늘({datetime.now().strftime('%Y-%m-%d')}) 비거래일 → 본 코드는 시작 직후 sys.exit(0)")
    except Exception as e:
        log_warn(f"거래일 확인 실패: {e}")

    # 잔고 조회
    try:
        stocks = KIS.get_KR_stock_balance()
        if isinstance(stocks, list):
            log_ok(f"잔고 조회 정상 → 보유 종목 {len(stocks)}개")
        else:
            log_fail(f"잔고 조회 실패: {stocks}")
            return None
    except Exception as e:
        log_fail(f"잔고 조회 예외: {e}")
        return None

    # 계좌 요약
    try:
        account = KIS.get_KR_account_summary()
        if isinstance(account, dict):
            log_ok(f"계좌요약: 총자산 {int(account['total_krw_asset']):,}원 (주식 {int(account['stock_eval_amt']):,} + 현금 {int(account['cash_balance']):,})")
        else:
            log_fail(f"계좌요약 조회 실패: {account}")
    except Exception as e:
        log_fail(f"계좌요약 예외: {e}")

    # 주문가능현금
    try:
        cash = KIS.get_KR_orderable_cash()
        if isinstance(cash, (int, float)):
            log_ok(f"주문가능현금: {int(cash):,}원")
        else:
            log_fail(f"주문가능현금 조회 실패: {cash}")
    except Exception as e:
        log_fail(f"주문가능현금 예외: {e}")

    return KIS


# ============================================================================
# [5] 거래정지 종목 실거래 시뮬레이션
# ============================================================================
def simulate_suspended_handling(KIS, suspended: set):
    section("[5] 거래정지 종목 실거래 시뮬레이션")

    if KIS is None:
        log_warn("KIS API 미연결 → 시뮬레이션 건너뜀")
        return

    if not suspended:
        log_ok("suspended_codes 비어있음 → 시뮬레이션 불필요")
        return

    # 현재 보유 종목 조회
    stocks = KIS.get_KR_stock_balance()
    if not isinstance(stocks, list):
        log_fail("잔고 조회 실패 → 시뮬레이션 불가")
        return

    hold_map = {s["종목코드"]: s for s in stocks}

    for code in sorted(suspended):
        print(f"\n  ── 종목 {code} 시뮬레이션 ──")

        # 보유 여부
        if code in hold_map:
            h = hold_map[code]
            log_ok(f"    보유 중: {h['종목명']} {h['보유수량']}주 (매도가능 {h['매도가능수량']}주), 평가금 {h['평가금액']:,}원")
        else:
            log_warn(f"    보유 없음 → 매도 대상 아님 (CSV에 있으면 매수 시도하나 사전등록으로 차단됨)")

        # 현재가 조회 (KIS API가 거래정지 종목에도 마지막 종가를 반환하는지 확인)
        try:
            price = KIS.get_KR_current_price(code)
            if isinstance(price, int) and price > 0:
                log_warn(f"    현재가 조회됨: {price:,}원 → KIS가 마지막 종가 반환. 사전등록이 없으면 정상종목으로 잘못 처리될 수 있음")
            else:
                log_ok(f"    현재가 조회 실패/0 → 이중 안전망(현재가 0 분기)으로도 거래정지 처리됨")
        except Exception as e:
            log_warn(f"    현재가 조회 예외: {e}")

        time.sleep(0.15)

    print()


# ============================================================================
# [6] 자산 계산 사전 시뮬레이션
# ============================================================================
def simulate_target_calculation(KIS, csv_weights: Dict, suspended: set):
    section("[6] 자산 계산 사전 시뮬레이션 (target_qty / adjust_rate 예측)")

    if KIS is None:
        log_warn("KIS API 미연결 → 시뮬레이션 건너뜀")
        return

    if not csv_weights:
        log_warn("CSV 데이터 없음 → 시뮬레이션 불가")
        return

    # 계좌 요약
    account = KIS.get_KR_account_summary()
    if not isinstance(account, dict):
        log_fail("계좌요약 조회 실패")
        return

    total_krw_asset = account['total_krw_asset']
    log_ok(f"기준 총자산: {int(total_krw_asset):,}원")

    # 현재 보유
    stocks = KIS.get_KR_stock_balance()
    if not isinstance(stocks, list):
        log_fail("잔고 조회 실패")
        return
    hold_map = {s["종목코드"]: s for s in stocks}

    # 거래정지 종목 평가금 합산
    suspended_asset = 0
    for code in suspended:
        if code in hold_map:
            bal = hold_map[code]["평가금액"]
            suspended_asset += bal

    effective_asset = total_krw_asset - suspended_asset
    log_ok(f"거래정지 자산 차감: {int(suspended_asset):,}원")
    log_ok(f"유효자산 (effective_asset): {int(effective_asset):,}원")

    if suspended_asset > 0:
        ratio = suspended_asset / total_krw_asset * 100
        if ratio > 5:
            log_warn(f"거래정지 자산 비중 {ratio:.2f}% — 5% 초과, target_qty 영향 큼")
        else:
            log_ok(f"거래정지 자산 비중 {ratio:.2f}% — 5% 이하")

    # target_invest 시뮬레이션 (상위 5개만 출력)
    print("\n  ── target_invest 예상 (상위 5종목) ──")
    sorted_codes = sorted(csv_weights.items(), key=lambda x: -x[1])
    shown = 0
    for code, weight in sorted_codes:
        if code == "CASH":
            continue
        if code in suspended:
            print(f"    {code}: 거래정지 → target_qty=0")
            shown += 1
            if shown >= 5:
                break
            continue
        try:
            price = KIS.get_KR_current_price(code)
            if not isinstance(price, int) or price == 0:
                print(f"    {code}: 현재가 조회 불가")
                continue
            target_invest = int(weight * effective_asset)
            target_qty = int(target_invest / price)
            print(f"    {code}: weight={weight:.4f}, price={price:,}원, target_qty={target_qty}주, 투자금≈{target_invest:,}원")
            shown += 1
            if shown >= 5:
                break
            time.sleep(0.15)
        except Exception as e:
            print(f"    {code}: 시뮬레이션 실패 ({e})")

    # 매수 필요금액 추정 (보수적으로 effective_asset × 0.99)
    estimated_buy_total = effective_asset * 0.99
    orderable_cash = KIS.get_KR_orderable_cash()
    if isinstance(orderable_cash, (int, float)):
        if orderable_cash >= estimated_buy_total:
            log_ok(f"주문가능현금({int(orderable_cash):,}원) ≥ 예상 매수금({int(estimated_buy_total):,}원) → adjust_rate 축소 없음")
        else:
            adjust = orderable_cash / estimated_buy_total if estimated_buy_total > 0 else 1.0
            log_warn(f"주문가능현금({int(orderable_cash):,}원) < 예상 매수금({int(estimated_buy_total):,}원) → 1·2회차에는 예상되는 정상 동작 (매도가 아직 안 됨)")
            log_warn(f"  예상 adjust_rate ≈ {adjust:.4f}")


# ============================================================================
# [최종] 요약
# ============================================================================
def print_summary():
    section("검증 결과 요약")
    print(f"  {COLOR_OK}OK   : {len(result_summary['ok'])}개{COLOR_END}")
    print(f"  {COLOR_WARN}WARN : {len(result_summary['warn'])}개{COLOR_END}")
    print(f"  {COLOR_FAIL}FAIL : {len(result_summary['fail'])}개{COLOR_END}")
    print()
    if result_summary["fail"]:
        print(f"{COLOR_FAIL}❌ 치명적 문제 발견 — 실행 전 반드시 해결할 것:{COLOR_END}")
        for msg in result_summary["fail"]:
            print(f"   • {msg}")
        return 1
    elif result_summary["warn"]:
        print(f"{COLOR_WARN}⚠️  경고 사항 (실행은 가능하나 확인 권장):{COLOR_END}")
        for msg in result_summary["warn"]:
            print(f"   • {msg}")
        print()
        print(f"{COLOR_OK}✅ 치명적 문제는 없음 → KRQT_TR.py 실행 가능{COLOR_END}")
        return 0
    else:
        print(f"{COLOR_OK}✅ 모든 검증 통과 → KRQT_TR.py 실행 가능{COLOR_END}")
        return 0


# ============================================================================
# main
# ============================================================================
def main():
    print(f"\n{'#'*72}")
    print(f"#  KRQT_TR.py 사전 검증 스크립트")
    print(f"#  실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*72}")

    # 장중 실행 경고
    now = datetime.now()
    hour = now.hour
    # EC2가 UTC라 가정 (KST = UTC+9). KST 09:00 = UTC 00:00, KST 15:30 = UTC 06:30
    if 0 <= hour < 7:
        log_warn(f"현재 시각이 한국 장중일 가능성 있음 (UTC {hour}시) → 본 스크립트는 조회 API만 사용하나 주의")

    try:
        check_static_code()
        check_filesystem()
        csv_weights, suspended = check_csv_suspended_consistency()
        KIS = check_kis_api()
        simulate_suspended_handling(KIS, suspended)
        simulate_target_calculation(KIS, csv_weights, suspended)
    except Exception as e:
        log_fail(f"검증 중 예기치 못한 예외: {e}")
        traceback.print_exc()

    return print_summary()


if __name__ == "__main__":
    sys.exit(main())
