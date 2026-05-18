"""
============================================================================
 키움증권 REST API - KRX 금현물 TR 응답 필드 확인용 테스트 코드
 파일명   : GOLD_TR_test.py
 환경     : Python 3.9+ / AWS EC2 Linux (또는 로컬)
 목적     : 각 TR의 실제 응답 구조(필드명/값)를 출력하여
            GOLD_TR.py의 응답 파싱 코드 교체에 활용

 실행 방법:
   python3 GOLD_TR_test.py              # 전체 TR 테스트
   python3 GOLD_TR_test.py ka50100      # 특정 TR만 테스트
   python3 GOLD_TR_test.py order_buy    # 매수 주문 테스트 (실제 주문 발생!)
   python3 GOLD_TR_test.py order_sell   # 매도 주문 테스트 (실제 주문 발생!)

 ⚠️  주의사항:
   - order_buy / order_sell 는 실제 주문이 발생합니다.
     최소 수량(1g)으로 테스트 후 즉시 취소(kt50003) 확인 권장.
   - 나머지 TR은 조회 전용이므로 자산에 영향 없음.
============================================================================
"""

import os
import sys
import json
import datetime
import requests
import pprint

# ===========================================================================
# 설정
# ===========================================================================
KEY_FILE_PATH   = "/var/autobot/KIS/kiwgold52953897.txt"
TOKEN_FILE_PATH = "/var/autobot/KIS/kiwgold_token.json"
ACCOUNT_NO      = "5295389780"
GOLD_STOCK_CODE = "04020000"    # 금 99.99K
BASE_URL        = "https://api.kiwoom.com"
TOKEN_SAFETY_MARGIN_MIN = 30

# 매수/매도 테스트 시 사용할 최소 수량 (1g)
TEST_ORDER_QTY  = 1

try:
    with open(KEY_FILE_PATH, "r", encoding="utf-8") as f:
        lines      = [l.strip() for l in f.readlines()]
    APP_KEY    = lines[0]
    APP_SECRET = lines[1]
except Exception as e:
    print(f"[ERROR] key 파일 로드 실패: {e}")
    sys.exit(1)


# ===========================================================================
# 공통 유틸
# ===========================================================================
SEP  = "=" * 65
SEP2 = "-" * 65

def _log(label, data):
    """TR 응답을 보기 좋게 출력."""
    print(f"\n{SEP}")
    print(f"  TR: {label}")
    print(SEP)
    if isinstance(data, dict):
        # 최상위 키 목록 먼저 출력
        print(f"  [최상위 키 목록]")
        for k, v in data.items():
            vtype = type(v).__name__
            if isinstance(v, list):
                print(f"    {k!r:30s} : list (len={len(v)})")
            elif isinstance(v, dict):
                print(f"    {k!r:30s} : dict (keys={list(v.keys())})")
            else:
                print(f"    {k!r:30s} : {vtype} = {v!r}")
        # 리스트 필드는 첫 번째 원소도 전개
        for k, v in data.items():
            if isinstance(v, list) and v:
                print(f"\n  [{k}][0] 상세:")
                if isinstance(v[0], dict):
                    for kk, vv in v[0].items():
                        print(f"    {kk!r:30s} = {vv!r}")
                else:
                    print(f"    {v[0]!r}")
    else:
        pprint.pprint(data, indent=4)
    print(f"\n  [RAW JSON]")
    print(json.dumps(data, ensure_ascii=False, indent=2)[:2000])
    print(SEP2)


def _api_headers(token, api_id):
    return {
        "Content-Type":  "application/json;charset=UTF-8",
        "authorization": f"Bearer {token}",
        "appkey":        APP_KEY,
        "appsecret":     APP_SECRET,
        "api-id":        api_id,
    }


def _post(token, api_id, body, timeout=10):
    url  = f"{BASE_URL}/api/dostk/goldstk"
    resp = requests.post(
        url,
        headers=_api_headers(token, api_id),
        json=body,
        timeout=timeout,
    )
    print(f"  HTTP {resp.status_code} | URL: {url} | api-id: {api_id}")
    if resp.status_code != 200:
        print(f"  [WARN] 비정상 응답: {resp.text[:500]}")
    return resp.status_code, resp.json() if resp.text else {}


# ===========================================================================
# 토큰 관리
# ===========================================================================
def get_access_token():
    if os.path.exists(TOKEN_FILE_PATH):
        try:
            with open(TOKEN_FILE_PATH, "r", encoding="utf-8") as f:
                cached = json.load(f)
            expires_at = datetime.datetime.fromisoformat(cached["expires_at"])
            margin = datetime.timedelta(minutes=TOKEN_SAFETY_MARGIN_MIN)
            if datetime.datetime.now() < expires_at - margin:
                print("[토큰] 캐시된 접근토큰 사용")
                return cached["access_token"]
        except Exception as e:
            print(f"[토큰] 캐시 로드 실패, 신규 발급: {e}")

    url     = f"{BASE_URL}/oauth2/token"
    headers = {"Content-Type": "application/json;charset=UTF-8"}
    body    = {
        "grant_type": "client_credentials",
        "appkey":     APP_KEY,
        "secretkey":  APP_SECRET,
    }
    resp = requests.post(url, headers=headers, json=body, timeout=10)
    print(f"[토큰] HTTP {resp.status_code}")
    resp.raise_for_status()
    data = resp.json()

    token = data.get("token") or data.get("access_token")
    if not token:
        print(f"[토큰] 발급 실패: {data}")
        sys.exit(1)

    if data.get("expires_dt"):
        expires_at = datetime.datetime.strptime(data["expires_dt"], "%Y%m%d%H%M%S")
    else:
        expires_in = int(data.get("expires_in", 86400))
        expires_at = datetime.datetime.now() + datetime.timedelta(seconds=expires_in)

    os.makedirs(os.path.dirname(TOKEN_FILE_PATH), exist_ok=True)
    with open(TOKEN_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump({"access_token": token, "expires_at": expires_at.isoformat()},
                  f, ensure_ascii=False, indent=2)
    print(f"[토큰] 신규 발급 완료 (만료: {expires_at})")

    # 토큰 발급 응답 전체 구조도 출력
    _log("oauth2/token (토큰발급 응답)", data)
    return token


# ===========================================================================
# 개별 TR 테스트 함수
# ===========================================================================

def test_ka50100(token):
    """금현물 시세정보 — 현재가, 시가, 고가, 저가 등"""
    print("\n▶ [ka50100] 금현물 시세정보")
    status, data = _post(token, "ka50100", {"stk_cd": GOLD_STOCK_CODE})
    _log("ka50100 금현물 시세정보", data)
    return data


def test_ka50101(token):
    """금현물 호가 — 매수/매도 5단계 호가"""
    print("\n▶ [ka50101] 금현물 호가")
    status, data = _post(token, "ka50101", {"stk_cd": GOLD_STOCK_CODE})
    _log("ka50101 금현물 호가", data)
    return data


def test_ka50087(token):
    """금현물 예상체결"""
    print("\n▶ [ka50087] 금현물 예상체결")
    status, data = _post(token, "ka50087", {"stk_cd": GOLD_STOCK_CODE})
    _log("ka50087 금현물 예상체결", data)
    return data


def test_ka50010(token):
    """금현물 체결추이"""
    print("\n▶ [ka50010] 금현물 체결추이")
    status, data = _post(token, "ka50010", {"stk_cd": GOLD_STOCK_CODE})
    _log("ka50010 금현물 체결추이", data)
    return data


def test_ka50012(token):
    """금현물 일별추이"""
    print("\n▶ [ka50012] 금현물 일별추이")
    today = datetime.date.today().strftime("%Y%m%d")
    status, data = _post(token, "ka50012", {
        "stk_cd":   GOLD_STOCK_CODE,
        "inq_stdt": (datetime.date.today() - datetime.timedelta(days=30)).strftime("%Y%m%d"),
        "inq_endt": today,
    })
    _log("ka50012 금현물 일별추이", data)
    return data


def test_ka52301(token):
    """금현물 투자자현황"""
    print("\n▶ [ka52301] 금현물 투자자현황")
    status, data = _post(token, "ka52301", {"stk_cd": GOLD_STOCK_CODE})
    _log("ka52301 금현물 투자자현황", data)
    return data


# ── 차트 ──────────────────────────────────────────────────────────────────

def test_ka50079(token):
    """금현물 틱차트"""
    print("\n▶ [ka50079] 금현물 틱차트")
    status, data = _post(token, "ka50079", {
        "stk_cd": GOLD_STOCK_CODE,
        "tic_scope": "1",       # 틱 범위 (명세서 확인)
    })
    _log("ka50079 금현물 틱차트", data)
    return data


def test_ka50080(token):
    """금현물 분봉차트"""
    print("\n▶ [ka50080] 금현물 분봉차트")
    status, data = _post(token, "ka50080", {
        "stk_cd":   GOLD_STOCK_CODE,
        "tic_scope": "1",       # 분 단위 (1, 3, 5, 10, 30 등 — 명세서 확인)
    })
    _log("ka50080 금현물 분봉차트", data)
    return data


def test_ka50081(token):
    """금현물 일봉차트"""
    print("\n▶ [ka50081] 금현물 일봉차트")
    today = datetime.date.today().strftime("%Y%m%d")
    status, data = _post(token, "ka50081", {
        "stk_cd":   GOLD_STOCK_CODE,
        "inq_stdt": (datetime.date.today() - datetime.timedelta(days=30)).strftime("%Y%m%d"),
        "inq_endt": today,
    })
    _log("ka50081 금현물 일봉차트", data)
    return data


def test_ka50082(token):
    """금현물 주봉차트"""
    print("\n▶ [ka50082] 금현물 주봉차트")
    status, data = _post(token, "ka50082", {"stk_cd": GOLD_STOCK_CODE})
    _log("ka50082 금현물 주봉차트", data)
    return data


def test_ka50083(token):
    """금현물 월봉차트"""
    print("\n▶ [ka50083] 금현물 월봉차트")
    status, data = _post(token, "ka50083", {"stk_cd": GOLD_STOCK_CODE})
    _log("ka50083 금현물 월봉차트", data)
    return data


def test_ka50091(token):
    """금현물 당일틱차트"""
    print("\n▶ [ka50091] 금현물 당일틱차트")
    status, data = _post(token, "ka50091", {
        "stk_cd":    GOLD_STOCK_CODE,
        "tic_scope": "1",
    })
    _log("ka50091 금현물 당일틱차트", data)
    return data


def test_ka50092(token):
    """금현물 당일분봉차트"""
    print("\n▶ [ka50092] 금현물 당일분봉차트")
    status, data = _post(token, "ka50092", {
        "stk_cd":    GOLD_STOCK_CODE,
        "tic_scope": "1",
    })
    _log("ka50092 금현물 당일분봉차트", data)
    return data


# ── 계좌/체결 ─────────────────────────────────────────────────────────────

def test_kt50020(token):
    """금현물 잔고확인 — 보유수량, 평균단가, 평가손익"""
    print("\n▶ [kt50020] 금현물 잔고확인")
    status, data = _post(token, "kt50020", {
        "acnt_no": ACCOUNT_NO,
        "stk_cd":  GOLD_STOCK_CODE,
    })
    _log("kt50020 금현물 잔고확인", data)
    return data


def test_kt50021(token):
    """금현물 예수금 — 주문가능금액, 총 예수금"""
    print("\n▶ [kt50021] 금현물 예수금")
    status, data = _post(token, "kt50021", {"acnt_no": ACCOUNT_NO})
    _log("kt50021 금현물 예수금", data)
    return data


def test_kt50030(token):
    """금현물 주문체결전체조회 — 당일 전체 주문 내역"""
    print("\n▶ [kt50030] 금현물 주문체결전체조회")
    today = datetime.date.today().strftime("%Y%m%d")
    status, data = _post(token, "kt50030", {
        "acnt_no":  ACCOUNT_NO,
        "inq_stdt": today,
        "inq_endt": today,
    })
    _log("kt50030 금현물 주문체결전체조회", data)
    return data


def test_kt50031(token, ord_no=""):
    """금현물 주문체결조회 — 특정 주문번호 체결 상세"""
    print(f"\n▶ [kt50031] 금현물 주문체결조회 (주문번호: {ord_no or '미입력'})")
    if not ord_no:
        print("  [SKIP] 주문번호가 없어 건너뜁니다. ord_no 파라미터로 전달하세요.")
        return {}
    status, data = _post(token, "kt50031", {
        "acnt_no": ACCOUNT_NO,
        "ord_no":  str(ord_no),
        "stk_cd":  GOLD_STOCK_CODE,
    })
    _log("kt50031 금현물 주문체결조회", data)
    return data


def test_kt50032(token):
    """금현물 거래내역조회"""
    print("\n▶ [kt50032] 금현물 거래내역조회")
    today = datetime.date.today().strftime("%Y%m%d")
    week_ago = (datetime.date.today() - datetime.timedelta(days=7)).strftime("%Y%m%d")
    status, data = _post(token, "kt50032", {
        "acnt_no":  ACCOUNT_NO,
        "inq_stdt": week_ago,
        "inq_endt": today,
    })
    _log("kt50032 금현물 거래내역조회", data)
    return data


def test_kt50075(token):
    """금현물 미체결조회"""
    print("\n▶ [kt50075] 금현물 미체결조회")
    status, data = _post(token, "kt50075", {
        "acnt_no": ACCOUNT_NO,
        "stk_cd":  GOLD_STOCK_CODE,
    })
    _log("kt50075 금현물 미체결조회", data)
    return data


# ── 주문 테스트 (실제 주문 발생 ⚠️) ─────────────────────────────────────

def test_order_buy(token):
    """금현물 매수주문 (kt50000) — 최소 1g 지정가 테스트.
    ⚠️  실제 주문 발생. 즉시 취소 확인 필요.
    """
    print(f"\n{'!'*65}")
    print(f"  ⚠️  [kt50000] 금현물 매수주문 — 실제 주문이 발생합니다!")
    print(f"  수량: {TEST_ORDER_QTY}g / 종목: {GOLD_STOCK_CODE}")
    confirm = input("  계속하려면 'yes' 입력: ").strip().lower()
    if confirm != "yes":
        print("  취소됨.")
        return {}

    # 현재가 조회 후 +0.5% 지정가
    _, price_data = _post(token, "ka50100", {"stk_cd": GOLD_STOCK_CODE})
    raw_price     = str(price_data.get("stck_prpr", "0")).replace(",", "").strip()
    cur_price     = int(float(raw_price)) if raw_price else 0
    order_price   = int(cur_price * 1.005) if cur_price > 0 else 1

    print(f"  현재가: {cur_price:,}원 / 주문단가: {order_price:,}원")

    body = {
        "acnt_no": ACCOUNT_NO,
        "stk_cd":  GOLD_STOCK_CODE,
        "ord_qty": str(TEST_ORDER_QTY),
        "ord_uv":  str(order_price),
        "trde_tp": "00",    # 00=지정가
    }
    status, data = _post(token, "kt50000", body)
    _log("kt50000 금현물 매수주문", data)

    ord_no = data.get("ord_no", "")
    if ord_no:
        print(f"\n  ✅ 주문번호: {ord_no}")
        print(f"  → test_kt50031(token, '{ord_no}') 으로 체결 확인 가능")
        print(f"  → test_order_cancel(token, '{ord_no}') 으로 취소 가능")
    return data


def test_order_sell(token):
    """금현물 매도주문 (kt50001) — 최소 1g 지정가 테스트.
    ⚠️  실제 주문 발생. 보유수량이 있어야 함.
    """
    print(f"\n{'!'*65}")
    print(f"  ⚠️  [kt50001] 금현물 매도주문 — 실제 주문이 발생합니다!")
    print(f"  수량: {TEST_ORDER_QTY}g / 종목: {GOLD_STOCK_CODE}")
    confirm = input("  계속하려면 'yes' 입력: ").strip().lower()
    if confirm != "yes":
        print("  취소됨.")
        return {}

    # 현재가 조회 후 -0.5% 지정가
    _, price_data = _post(token, "ka50100", {"stk_cd": GOLD_STOCK_CODE})
    raw_price     = str(price_data.get("stck_prpr", "0")).replace(",", "").strip()
    cur_price     = int(float(raw_price)) if raw_price else 0
    order_price   = int(cur_price * 0.995) if cur_price > 0 else 1

    print(f"  현재가: {cur_price:,}원 / 주문단가: {order_price:,}원")

    body = {
        "acnt_no": ACCOUNT_NO,
        "stk_cd":  GOLD_STOCK_CODE,
        "ord_qty": str(TEST_ORDER_QTY),
        "ord_uv":  str(order_price),
        "trde_tp": "00",
    }
    status, data = _post(token, "kt50001", body)
    _log("kt50001 금현물 매도주문", data)

    ord_no = data.get("ord_no", "")
    if ord_no:
        print(f"\n  ✅ 주문번호: {ord_no}")
    return data


def test_order_cancel(token, ord_no, qty=0):
    """금현물 취소주문 (kt50003).
    ord_no : 취소할 원주문번호
    qty    : 취소수량 (0=전량)
    """
    print(f"\n▶ [kt50003] 금현물 취소주문 (원주문: {ord_no}, 수량: {qty or '전량'})")
    body = {
        "acnt_no":    ACCOUNT_NO,
        "stk_cd":     GOLD_STOCK_CODE,
        "org_ord_no": str(ord_no),
        "cncl_qty":   str(qty),
    }
    status, data = _post(token, "kt50003", body)
    _log("kt50003 금현물 취소주문", data)
    return data


# ===========================================================================
# 결과 요약 출력
# ===========================================================================
def print_field_summary(results: dict):
    """전체 테스트 결과에서 핵심 필드를 요약 출력."""
    print(f"\n\n{'#'*65}")
    print("  📋 GOLD_TR.py 수정에 필요한 핵심 필드 요약")
    print(f"{'#'*65}")

    checks = [
        # (TR명,           응답dict,                      확인할 필드들)
        ("ka50100 시세정보",  results.get("ka50100",  {}), ["stck_prpr", "stck_oprc", "stck_hgpr", "stck_lwpr"]),
        ("kt50021 예수금",   results.get("kt50021",  {}), ["ord_psbl_amt", "dpst_amt", "dnca_tot_amt"]),
        ("kt50020 잔고확인", results.get("kt50020",  {}), ["rmnd_qty", "avg_prc", "evlt_amt", "evlt_pl", "prft_rt"]),
        ("kt50075 미체결",   results.get("kt50075",  {}), ["list"]),
        ("kt50030 체결전체", results.get("kt50030",  {}), ["list"]),
    ]

    for tr_name, data, fields in checks:
        print(f"\n  [{tr_name}]")
        if not data:
            print("    (응답 없음 또는 테스트 미실행)")
            continue
        for f in fields:
            val = data.get(f, "⚠️ 없음")
            if isinstance(val, list):
                print(f"    {f!r:25s} : list(len={len(val)})", end="")
                if val and isinstance(val[0], dict):
                    print(f" → 첫 원소 키: {list(val[0].keys())}")
                else:
                    print()
            else:
                print(f"    {f!r:25s} : {val!r}")

    print(f"\n{'#'*65}")
    print("  ✅ 위 결과를 GOLD_TR.py의 data.get() 필드명과 대조하여 수정하세요.")
    print(f"{'#'*65}\n")


# ===========================================================================
# TR 목록 정의 (단독 실행 인수에서 선택 가능)
# ===========================================================================
TR_MAP = {
    # 시세
    "ka50100":   ("금현물 시세정보",      test_ka50100),
    "ka50101":   ("금현물 호가",          test_ka50101),
    "ka50087":   ("금현물 예상체결",      test_ka50087),
    "ka50010":   ("금현물 체결추이",      test_ka50010),
    "ka50012":   ("금현물 일별추이",      test_ka50012),
    "ka52301":   ("금현물 투자자현황",    test_ka52301),
    # 차트
    "ka50079":   ("금현물 틱차트",        test_ka50079),
    "ka50080":   ("금현물 분봉차트",      test_ka50080),
    "ka50081":   ("금현물 일봉차트",      test_ka50081),
    "ka50082":   ("금현물 주봉차트",      test_ka50082),
    "ka50083":   ("금현물 월봉차트",      test_ka50083),
    "ka50091":   ("금현물 당일틱차트",    test_ka50091),
    "ka50092":   ("금현물 당일분봉차트",  test_ka50092),
    # 계좌
    "kt50020":   ("금현물 잔고확인",      test_kt50020),
    "kt50021":   ("금현물 예수금",        test_kt50021),
    "kt50030":   ("금현물 주문체결전체",  test_kt50030),
    "kt50032":   ("금현물 거래내역",      test_kt50032),
    "kt50075":   ("금현물 미체결",        test_kt50075),
    # 주문 (실제 주문 발생)
    "order_buy":    ("금현물 매수주문 ⚠️",  test_order_buy),
    "order_sell":   ("금현물 매도주문 ⚠️",  test_order_sell),
}

# GOLD_TR.py 수정에 꼭 필요한 조회 TR 목록 (주문 제외)
ESSENTIAL_TRS = ["ka50100", "kt50021", "kt50020", "kt50075", "kt50030"]


# ===========================================================================
# 메인
# ===========================================================================
def main():
    print(f"\n{SEP}")
    print("  키움 금현물 TR 응답 필드 확인 테스트")
    print(f"  실행시각: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  계좌번호: {ACCOUNT_NO}  |  종목: {GOLD_STOCK_CODE}")
    print(SEP)

    # 토큰 발급
    token = get_access_token()

    args    = sys.argv[1:]          # 명령행 인수 (TR ID 또는 특수 키워드)
    results = {}

    if not args:
        # 인수 없으면 ESSENTIAL_TRS (조회 전용) 전체 실행
        print(f"\n  ※ 인수 없음 → 핵심 조회 TR {ESSENTIAL_TRS} 실행")
        print(f"  ※ 전체 실행: python3 GOLD_TR_test.py all")
        print(f"  ※ 특정 TR:  python3 GOLD_TR_test.py ka50100 kt50021")
        print(f"  ※ 주문 테스트: python3 GOLD_TR_test.py order_buy\n")
        targets = ESSENTIAL_TRS

    elif "all" in args:
        # 주문 제외 전체
        targets = [k for k in TR_MAP if not k.startswith("order_")]
        print(f"\n  ※ 'all' → 주문 제외 전체 TR {len(targets)}개 실행")

    else:
        targets = args

    for tr_id in targets:
        if tr_id not in TR_MAP:
            print(f"\n  [WARN] 알 수 없는 TR ID: {tr_id!r} → 건너뜀")
            print(f"  사용 가능: {list(TR_MAP.keys())}")
            continue

        tr_name, fn = TR_MAP[tr_id]
        print(f"\n  ── {tr_id} ({tr_name}) ──")

        try:
            result = fn(token)
            results[tr_id] = result if isinstance(result, dict) else {}
        except requests.exceptions.HTTPError as e:
            err = getattr(e.response, "text", "")[:300]
            print(f"  [ERROR] HTTP 오류: {e}")
            print(f"  응답: {err}")
            results[tr_id] = {}
        except Exception as e:
            print(f"  [ERROR] {e}")
            results[tr_id] = {}

    # 핵심 필드 요약 출력 (조회 TR이 포함된 경우에만)
    if any(k in results for k in ESSENTIAL_TRS):
        print_field_summary(results)

    # 전체 결과를 JSON 파일로도 저장
    out_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"gold_tr_test_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n  📁 결과 저장: {out_path}")
    except Exception as e:
        print(f"  [WARN] 결과 파일 저장 실패: {e}")


if __name__ == "__main__":
    main()
