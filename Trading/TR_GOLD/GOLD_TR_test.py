"""
============================================================================
 키움증권 REST API - KRX 금현물 TR 응답 필드 확인용 테스트 코드
 파일명   : GOLD_TR_test.py
 환경     : Python 3.9+ / AWS EC2 Linux (또는 로컬)

 ── 핵심 수정 내용 ────────────────────────────────────────────────────────
  에러원인: 1504 - 모든 TR을 /api/dostk/goldstk 한 곳으로 보냈었음.
  키움 REST API는 TR 종류(시세/차트/주문/계좌)마다 URI가 다르다.

  URI 매핑 (키움 공식 가이드 기준):
    /api/dostk/goldstk   ← ka5xxxx  금현물 시세/차트 조회
    /api/dostk/goldacnt  ← kt5xxxx  금현물 계좌/주문
    ※ 위 URI가 틀릴 경우: 주식 패턴(/api/dostk/stk, /api/dostk/acnt)을
       참고하여 아래 TR_URI_MAP 을 직접 수정하세요.

 실행 방법:
   python3 GOLD_TR_test.py              # 핵심 조회 5개 (자산 영향 없음)
   python3 GOLD_TR_test.py all          # 주문 제외 전체
   python3 GOLD_TR_test.py ka50100      # 특정 TR만
   python3 GOLD_TR_test.py ka50100 kt50021 kt50020
   python3 GOLD_TR_test.py order_buy    # ⚠️ 실제 1g 매수 주문 발생
   python3 GOLD_TR_test.py order_sell   # ⚠️ 실제 1g 매도 주문 발생
============================================================================
"""

import os
import sys
import json
import time
import datetime
import requests
import pprint

# ===========================================================================
# 설정
# ===========================================================================
KEY_FILE_PATH   = "/var/autobot/KIS/kiwgold52953897.txt"
TOKEN_FILE_PATH = "/var/autobot/KIS/kiwgold_token.json"
ACCOUNT_NO      = "5295389780"
GOLD_STOCK_CODE = "04020000"        # 금 99.99K
BASE_URL        = "https://api.kiwoom.com"
TOKEN_SAFETY_MARGIN_MIN = 30
TEST_ORDER_QTY  = 1                 # 주문 테스트 최소 수량 (1g)

try:
    with open(KEY_FILE_PATH, "r", encoding="utf-8") as f:
        lines      = [l.strip() for l in f.readlines()]
    APP_KEY    = lines[0]
    APP_SECRET = lines[1]
except Exception as e:
    print(f"[ERROR] key 파일 로드 실패: {e}")
    sys.exit(1)


# ===========================================================================
# TR → URI 매핑
# ===========================================================================
# 키움 REST API는 TR prefix에 따라 URI가 다르다.
# 에러 1504가 다시 나오면 아래 URI를 실제 명세서 값으로 교체할 것.
#
# 추론 근거:
#   주식 시세  ka1xxxx → /api/dostk/stk
#   주식 계좌  kt0xxxx → /api/dostk/acnt
#   주식 주문  kt1xxxx → /api/dostk/ordr
#   금현물 시세/차트 ka5xxxx → /api/dostk/goldstk   (원래 코드 그대로)
#   금현물 계좌/주문 kt5xxxx → /api/dostk/goldacnt  (← 이번에 분리)
#
TR_URI_MAP = {
    # ── 금현물 시세/차트 조회 (ka5xxxx) ──────────────────────────────────
    "ka50100": "/api/dostk/goldstk",   # 금현물 시세정보
    "ka50101": "/api/dostk/goldstk",   # 금현물 호가
    "ka50087": "/api/dostk/goldstk",   # 금현물 예상체결
    "ka50010": "/api/dostk/goldstk",   # 금현물 체결추이
    "ka50012": "/api/dostk/goldstk",   # 금현물 일별추이
    "ka52301": "/api/dostk/goldstk",   # 금현물 투자자현황
    "ka50079": "/api/dostk/goldstk",   # 금현물 틱차트
    "ka50080": "/api/dostk/goldstk",   # 금현물 분봉차트
    "ka50081": "/api/dostk/goldstk",   # 금현물 일봉차트
    "ka50082": "/api/dostk/goldstk",   # 금현물 주봉차트
    "ka50083": "/api/dostk/goldstk",   # 금현물 월봉차트
    "ka50091": "/api/dostk/goldstk",   # 금현물 당일틱차트
    "ka50092": "/api/dostk/goldstk",   # 금현물 당일분봉차트

    # ── 금현물 계좌/주문 (kt5xxxx) ────────────────────────────────────────
    # URI 후보: /api/dostk/goldacnt 또는 /api/dostk/goldordr
    # 1504 에러가 다시 나오면 아래 URI를 직접 수정
    "kt50020": "/api/dostk/goldacnt",  # 금현물 잔고확인
    "kt50021": "/api/dostk/goldacnt",  # 금현물 예수금
    "kt50030": "/api/dostk/goldacnt",  # 금현물 주문체결전체조회
    "kt50031": "/api/dostk/goldacnt",  # 금현물 주문체결조회
    "kt50032": "/api/dostk/goldacnt",  # 금현물 거래내역조회
    "kt50075": "/api/dostk/goldacnt",  # 금현물 미체결조회
    "kt50000": "/api/dostk/goldacnt",  # 금현물 매수주문
    "kt50001": "/api/dostk/goldacnt",  # 금현물 매도주문
    "kt50002": "/api/dostk/goldacnt",  # 금현물 정정주문
    "kt50003": "/api/dostk/goldacnt",  # 금현물 취소주문
}

# URI 후보 목록: 1504 에러 시 자동 재시도할 URI 순서
URI_CANDIDATES = {
    # kt5xxxx 계좌/주문 후보
    "kt": [
        "/api/dostk/goldacnt",
        "/api/dostk/goldordr",
        "/api/dostk/gold",
        "/api/dostk/goldstk",   # 마지막 시도
    ],
    # ka5xxxx 시세 후보 (원래 맞았지만 혹시 몰라 포함)
    "ka": [
        "/api/dostk/goldstk",
        "/api/dostk/gold",
    ],
}


# ===========================================================================
# 공통 유틸
# ===========================================================================
SEP  = "=" * 65
SEP2 = "-" * 65


def _log(label, data, http_status=None):
    print(f"\n{SEP}")
    print(f"  TR: {label}" + (f"  (HTTP {http_status})" if http_status else ""))
    print(SEP)
    if not data:
        print("  (빈 응답)")
        print(SEP2)
        return

    if isinstance(data, dict):
        print("  [최상위 키 목록]")
        for k, v in data.items():
            if isinstance(v, list):
                print(f"    {k!r:30s} : list (len={len(v)})")
            elif isinstance(v, dict):
                print(f"    {k!r:30s} : dict  keys={list(v.keys())}")
            else:
                print(f"    {k!r:30s} : {type(v).__name__} = {v!r}")

        # 리스트 내부 첫 원소 전개
        for k, v in data.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                print(f"\n  [{k}][0] 상세:")
                for kk, vv in v[0].items():
                    print(f"    {kk!r:30s} = {vv!r}")
    else:
        pprint.pprint(data, indent=4)

    print(f"\n  [RAW JSON (앞 3000자)]")
    print(json.dumps(data, ensure_ascii=False, indent=2)[:3000])
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
    """TR에 맞는 URI로 POST. 1504 에러 시 후보 URI 순서대로 재시도."""
    uri = TR_URI_MAP.get(api_id, "/api/dostk/goldstk")

    # 1차 시도
    url  = f"{BASE_URL}{uri}"
    resp = requests.post(url, headers=_api_headers(token, api_id), json=body, timeout=timeout)
    data = resp.json() if resp.text else {}

    # 1504 에러면 다른 URI 후보 자동 재시도
    if data.get("return_code") == 1 and "1504" in data.get("return_msg", ""):
        prefix = "kt" if api_id.startswith("kt") else "ka"
        candidates = URI_CANDIDATES.get(prefix, [])
        tried = {uri}
        for alt_uri in candidates:
            if alt_uri in tried:
                continue
            tried.add(alt_uri)
            alt_url = f"{BASE_URL}{alt_uri}"
            print(f"  ⚠️  1504 에러 → URI 재시도: {alt_uri}")
            resp = requests.post(
                alt_url,
                headers=_api_headers(token, api_id),
                json=body,
                timeout=timeout,
            )
            data = resp.json() if resp.text else {}
            if data.get("return_code") != 1 or "1504" not in data.get("return_msg", ""):
                print(f"  ✅ 성공 URI: {alt_uri}  ← TR_URI_MAP 에 반영 필요")
                # 런타임 업데이트
                TR_URI_MAP[api_id] = alt_uri
                break
        else:
            print(f"  ❌ 모든 URI 후보 실패. 키움 명세서에서 {api_id} 의 URI 직접 확인 필요.")

    print(f"  HTTP {resp.status_code} | URI: {TR_URI_MAP.get(api_id, uri)} | api-id: {api_id}")
    return resp.status_code, data


# ===========================================================================
# 토큰 관리
# ===========================================================================
def get_access_token():
    if os.path.exists(TOKEN_FILE_PATH):
        try:
            with open(TOKEN_FILE_PATH, "r", encoding="utf-8") as f:
                cached = json.load(f)
            expires_at = datetime.datetime.fromisoformat(cached["expires_at"])
            if datetime.datetime.now() < expires_at - datetime.timedelta(minutes=TOKEN_SAFETY_MARGIN_MIN):
                print("[토큰] 캐시된 접근토큰 사용")
                return cached["access_token"]
        except Exception as e:
            print(f"[토큰] 캐시 로드 실패, 신규 발급: {e}")

    url  = f"{BASE_URL}/oauth2/token"
    body = {"grant_type": "client_credentials", "appkey": APP_KEY, "secretkey": APP_SECRET}
    resp = requests.post(url, headers={"Content-Type": "application/json;charset=UTF-8"}, json=body, timeout=10)
    print(f"[토큰] HTTP {resp.status_code}")
    resp.raise_for_status()
    data = resp.json()

    token = data.get("token") or data.get("access_token")
    if not token:
        print(f"[토큰] 발급 실패: {data}")
        sys.exit(1)

    expires_at = (
        datetime.datetime.strptime(data["expires_dt"], "%Y%m%d%H%M%S")
        if data.get("expires_dt")
        else datetime.datetime.now() + datetime.timedelta(seconds=int(data.get("expires_in", 86400)))
    )
    os.makedirs(os.path.dirname(TOKEN_FILE_PATH), exist_ok=True)
    with open(TOKEN_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump({"access_token": token, "expires_at": expires_at.isoformat()}, f, ensure_ascii=False, indent=2)
    print(f"[토큰] 신규 발급 완료 (만료: {expires_at})")
    return token


# ===========================================================================
# 개별 TR 테스트 함수
# ===========================================================================

# ── 시세 ──────────────────────────────────────────────────────────────────

def test_ka50100(token):
    print("\n▶ [ka50100] 금현물 시세정보")
    s, d = _post(token, "ka50100", {"stk_cd": GOLD_STOCK_CODE})
    _log("ka50100 금현물 시세정보", d, s)
    return d

def test_ka50101(token):
    print("\n▶ [ka50101] 금현물 호가")
    s, d = _post(token, "ka50101", {"stk_cd": GOLD_STOCK_CODE})
    _log("ka50101 금현물 호가", d, s)
    return d

def test_ka50087(token):
    print("\n▶ [ka50087] 금현물 예상체결")
    s, d = _post(token, "ka50087", {"stk_cd": GOLD_STOCK_CODE})
    _log("ka50087 금현물 예상체결", d, s)
    return d

def test_ka50010(token):
    print("\n▶ [ka50010] 금현물 체결추이")
    s, d = _post(token, "ka50010", {"stk_cd": GOLD_STOCK_CODE})
    _log("ka50010 금현물 체결추이", d, s)
    return d

def test_ka50012(token):
    print("\n▶ [ka50012] 금현물 일별추이")
    today    = datetime.date.today().strftime("%Y%m%d")
    week_ago = (datetime.date.today() - datetime.timedelta(days=7)).strftime("%Y%m%d")
    s, d = _post(token, "ka50012", {"stk_cd": GOLD_STOCK_CODE, "inq_stdt": week_ago, "inq_endt": today})
    _log("ka50012 금현물 일별추이", d, s)
    return d

def test_ka52301(token):
    print("\n▶ [ka52301] 금현물 투자자현황")
    s, d = _post(token, "ka52301", {"stk_cd": GOLD_STOCK_CODE})
    _log("ka52301 금현물 투자자현황", d, s)
    return d


# ── 차트 ──────────────────────────────────────────────────────────────────

def test_ka50079(token):
    print("\n▶ [ka50079] 금현물 틱차트")
    s, d = _post(token, "ka50079", {"stk_cd": GOLD_STOCK_CODE, "tic_scope": "1"})
    _log("ka50079 금현물 틱차트", d, s)
    return d

def test_ka50080(token):
    print("\n▶ [ka50080] 금현물 분봉차트")
    s, d = _post(token, "ka50080", {"stk_cd": GOLD_STOCK_CODE, "tic_scope": "1"})
    _log("ka50080 금현물 분봉차트", d, s)
    return d

def test_ka50081(token):
    print("\n▶ [ka50081] 금현물 일봉차트")
    today    = datetime.date.today().strftime("%Y%m%d")
    week_ago = (datetime.date.today() - datetime.timedelta(days=30)).strftime("%Y%m%d")
    s, d = _post(token, "ka50081", {"stk_cd": GOLD_STOCK_CODE, "inq_stdt": week_ago, "inq_endt": today})
    _log("ka50081 금현물 일봉차트", d, s)
    return d

def test_ka50082(token):
    print("\n▶ [ka50082] 금현물 주봉차트")
    s, d = _post(token, "ka50082", {"stk_cd": GOLD_STOCK_CODE})
    _log("ka50082 금현물 주봉차트", d, s)
    return d

def test_ka50083(token):
    print("\n▶ [ka50083] 금현물 월봉차트")
    s, d = _post(token, "ka50083", {"stk_cd": GOLD_STOCK_CODE})
    _log("ka50083 금현물 월봉차트", d, s)
    return d

def test_ka50091(token):
    print("\n▶ [ka50091] 금현물 당일틱차트")
    s, d = _post(token, "ka50091", {"stk_cd": GOLD_STOCK_CODE, "tic_scope": "1"})
    _log("ka50091 금현물 당일틱차트", d, s)
    return d

def test_ka50092(token):
    print("\n▶ [ka50092] 금현물 당일분봉차트")
    s, d = _post(token, "ka50092", {"stk_cd": GOLD_STOCK_CODE, "tic_scope": "1"})
    _log("ka50092 금현물 당일분봉차트", d, s)
    return d


# ── 계좌 ──────────────────────────────────────────────────────────────────

def test_kt50020(token):
    print("\n▶ [kt50020] 금현물 잔고확인")
    s, d = _post(token, "kt50020", {"acnt_no": ACCOUNT_NO, "stk_cd": GOLD_STOCK_CODE})
    _log("kt50020 금현물 잔고확인", d, s)
    return d

def test_kt50021(token):
    print("\n▶ [kt50021] 금현물 예수금")
    s, d = _post(token, "kt50021", {"acnt_no": ACCOUNT_NO})
    _log("kt50021 금현물 예수금", d, s)
    return d

def test_kt50030(token):
    print("\n▶ [kt50030] 금현물 주문체결전체조회")
    today = datetime.date.today().strftime("%Y%m%d")
    s, d = _post(token, "kt50030", {"acnt_no": ACCOUNT_NO, "inq_stdt": today, "inq_endt": today})
    _log("kt50030 금현물 주문체결전체조회", d, s)
    return d

def test_kt50031(token, ord_no=""):
    print(f"\n▶ [kt50031] 금현물 주문체결조회 (주문번호: {ord_no or '미입력'})")
    if not ord_no:
        print("  [SKIP] 주문번호 없음. test_kt50031(token, '주문번호') 로 직접 호출하세요.")
        return {}
    s, d = _post(token, "kt50031", {"acnt_no": ACCOUNT_NO, "ord_no": str(ord_no), "stk_cd": GOLD_STOCK_CODE})
    _log("kt50031 금현물 주문체결조회", d, s)
    return d

def test_kt50032(token):
    print("\n▶ [kt50032] 금현물 거래내역조회")
    today    = datetime.date.today().strftime("%Y%m%d")
    week_ago = (datetime.date.today() - datetime.timedelta(days=7)).strftime("%Y%m%d")
    s, d = _post(token, "kt50032", {"acnt_no": ACCOUNT_NO, "inq_stdt": week_ago, "inq_endt": today})
    _log("kt50032 금현물 거래내역조회", d, s)
    return d

def test_kt50075(token):
    print("\n▶ [kt50075] 금현물 미체결조회")
    s, d = _post(token, "kt50075", {"acnt_no": ACCOUNT_NO, "stk_cd": GOLD_STOCK_CODE})
    _log("kt50075 금현물 미체결조회", d, s)
    return d


# ── 주문 테스트 (⚠️ 실제 주문 발생) ─────────────────────────────────────

def test_order_buy(token):
    print(f"\n{'!'*65}")
    print(f"  ⚠️  [kt50000] 금현물 매수주문 — 실제 주문이 발생합니다!")
    print(f"  수량: {TEST_ORDER_QTY}g / 종목: {GOLD_STOCK_CODE}")
    confirm = input("  계속하려면 'yes' 입력: ").strip().lower()
    if confirm != "yes":
        print("  취소됨.")
        return {}

    _, price_data = _post(token, "ka50100", {"stk_cd": GOLD_STOCK_CODE})
    # 응답 필드명은 ka50100 테스트 결과를 보고 수정
    raw_price   = str(price_data.get("stck_prpr", "0")).replace(",", "").strip()
    cur_price   = int(float(raw_price)) if raw_price and raw_price != "0" else 0
    order_price = int(cur_price * 1.005) if cur_price > 0 else 1
    print(f"  현재가: {cur_price:,}원 / 주문단가(+0.5%): {order_price:,}원")

    body = {
        "acnt_no": ACCOUNT_NO,
        "stk_cd":  GOLD_STOCK_CODE,
        "ord_qty": str(TEST_ORDER_QTY),
        "ord_uv":  str(order_price),
        "trde_tp": "00",
    }
    s, d = _post(token, "kt50000", body)
    _log("kt50000 금현물 매수주문", d, s)
    ord_no = d.get("ord_no", "")
    if ord_no:
        print(f"\n  ✅ 주문번호: {ord_no}")
        print(f"  → test_kt50031(token, '{ord_no}')  으로 체결 확인")
        print(f"  → test_order_cancel(token, '{ord_no}')  으로 취소")
    return d


def test_order_sell(token):
    print(f"\n{'!'*65}")
    print(f"  ⚠️  [kt50001] 금현물 매도주문 — 실제 주문이 발생합니다!")
    confirm = input("  계속하려면 'yes' 입력: ").strip().lower()
    if confirm != "yes":
        print("  취소됨.")
        return {}

    _, price_data = _post(token, "ka50100", {"stk_cd": GOLD_STOCK_CODE})
    raw_price   = str(price_data.get("stck_prpr", "0")).replace(",", "").strip()
    cur_price   = int(float(raw_price)) if raw_price and raw_price != "0" else 0
    order_price = int(cur_price * 0.995) if cur_price > 0 else 1
    print(f"  현재가: {cur_price:,}원 / 주문단가(-0.5%): {order_price:,}원")

    body = {
        "acnt_no": ACCOUNT_NO,
        "stk_cd":  GOLD_STOCK_CODE,
        "ord_qty": str(TEST_ORDER_QTY),
        "ord_uv":  str(order_price),
        "trde_tp": "00",
    }
    s, d = _post(token, "kt50001", body)
    _log("kt50001 금현물 매도주문", d, s)
    ord_no = d.get("ord_no", "")
    if ord_no:
        print(f"\n  ✅ 주문번호: {ord_no}")
    return d


def test_order_cancel(token, ord_no, qty=0):
    print(f"\n▶ [kt50003] 금현물 취소주문 (원주문: {ord_no}, 수량: {qty or '전량'})")
    body = {
        "acnt_no":    ACCOUNT_NO,
        "stk_cd":     GOLD_STOCK_CODE,
        "org_ord_no": str(ord_no),
        "cncl_qty":   str(qty),
    }
    s, d = _post(token, "kt50003", body)
    _log("kt50003 금현물 취소주문", d, s)
    return d


# ===========================================================================
# 1504 에러 발생 시 성공 URI 요약 출력
# ===========================================================================
def print_uri_result():
    print(f"\n{'#'*65}")
    print("  📋 확인된 URI 매핑 결과 (GOLD_TR.py 에 반영하세요)")
    print(f"{'#'*65}")
    for api_id, uri in TR_URI_MAP.items():
        print(f"    {api_id!r:12s} → {uri}")
    print(f"{'#'*65}\n")


# ===========================================================================
# 핵심 필드 요약
# ===========================================================================
ESSENTIAL_TRS = ["ka50100", "kt50021", "kt50020", "kt50075", "kt50030"]

def print_field_summary(results: dict):
    print(f"\n\n{'#'*65}")
    print("  📋 GOLD_TR.py 수정에 필요한 핵심 필드 요약")
    print(f"{'#'*65}")

    checks = [
        ("ka50100 시세정보",  results.get("ka50100", {}),
         ["stck_prpr", "stck_oprc", "stck_hgpr", "stck_lwpr", "stck_clpr"]),
        ("kt50021 예수금",    results.get("kt50021", {}),
         ["ord_psbl_amt", "dpst_amt", "dnca_tot_amt"]),
        ("kt50020 잔고확인",  results.get("kt50020", {}),
         ["rmnd_qty", "avg_prc", "evlt_amt", "evlt_pl", "prft_rt"]),
        ("kt50075 미체결",    results.get("kt50075", {}), ["list"]),
        ("kt50030 체결전체",  results.get("kt50030", {}), ["list"]),
    ]

    for tr_name, data, fields in checks:
        print(f"\n  [{tr_name}]")
        if not data:
            print("    (응답 없음 또는 테스트 미실행)")
            continue
        rc = data.get("return_code", "?")
        rm = data.get("return_msg", "")
        if rc != 0:
            print(f"    ⚠️  return_code={rc}  msg={rm}")
            continue
        for f in fields:
            val = data.get(f, "⚠️ 없음")
            if isinstance(val, list):
                print(f"    {f!r:25s} : list(len={len(val)})", end="")
                if val and isinstance(val[0], dict):
                    print(f"  → 첫 원소 키: {list(val[0].keys())}")
                else:
                    print()
            else:
                print(f"    {f!r:25s} : {val!r}")

    print(f"\n{'#'*65}")
    print("  ✅ 위 필드명을 GOLD_TR.py의 data.get() 에 반영하세요.")
    print(f"{'#'*65}\n")


# ===========================================================================
# TR 목록
# ===========================================================================
TR_MAP = {
    "ka50100":   ("금현물 시세정보",      test_ka50100),
    "ka50101":   ("금현물 호가",          test_ka50101),
    "ka50087":   ("금현물 예상체결",      test_ka50087),
    "ka50010":   ("금현물 체결추이",      test_ka50010),
    "ka50012":   ("금현물 일별추이",      test_ka50012),
    "ka52301":   ("금현물 투자자현황",    test_ka52301),
    "ka50079":   ("금현물 틱차트",        test_ka50079),
    "ka50080":   ("금현물 분봉차트",      test_ka50080),
    "ka50081":   ("금현물 일봉차트",      test_ka50081),
    "ka50082":   ("금현물 주봉차트",      test_ka50082),
    "ka50083":   ("금현물 월봉차트",      test_ka50083),
    "ka50091":   ("금현물 당일틱차트",    test_ka50091),
    "ka50092":   ("금현물 당일분봉차트",  test_ka50092),
    "kt50020":   ("금현물 잔고확인",      test_kt50020),
    "kt50021":   ("금현물 예수금",        test_kt50021),
    "kt50030":   ("금현물 주문체결전체",  test_kt50030),
    "kt50032":   ("금현물 거래내역",      test_kt50032),
    "kt50075":   ("금현물 미체결",        test_kt50075),
    "order_buy":  ("금현물 매수주문 ⚠️",  test_order_buy),
    "order_sell": ("금현물 매도주문 ⚠️",  test_order_sell),
}


# ===========================================================================
# 메인
# ===========================================================================
def main():
    print(f"\n{SEP}")
    print("  키움 금현물 TR 응답 필드 확인 테스트 (URI 분리 적용)")
    print(f"  실행시각: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  계좌번호: {ACCOUNT_NO}  |  종목: {GOLD_STOCK_CODE}")
    print(f"\n  [URI 매핑]")
    print(f"    ka5xxxx → /api/dostk/goldstk   (금현물 시세/차트)")
    print(f"    kt5xxxx → /api/dostk/goldacnt   (금현물 계좌/주문)")
    print(f"    ※ 1504 에러 발생 시 후보 URI 자동 재시도")
    print(SEP)

    token   = get_access_token()
    args    = sys.argv[1:]
    results = {}

    if not args:
        print(f"\n  ※ 인수 없음 → 핵심 조회 TR {ESSENTIAL_TRS} 실행")
        print(f"  ※ 전체 실행: python3 GOLD_TR_test.py all")
        print(f"  ※ 특정 TR:  python3 GOLD_TR_test.py ka50100 kt50021")
        print(f"  ※ 주문 테스트: python3 GOLD_TR_test.py order_buy\n")
        targets = ESSENTIAL_TRS
    elif "all" in args:
        targets = [k for k in TR_MAP if not k.startswith("order_")]
        print(f"\n  ※ 'all' → 주문 제외 전체 TR {len(targets)}개 실행")
    else:
        targets = args

    for tr_id in targets:
        if tr_id not in TR_MAP:
            print(f"\n  [WARN] 알 수 없는 TR: {tr_id!r}")
            print(f"  사용 가능: {list(TR_MAP.keys())}")
            continue

        tr_name, fn = TR_MAP[tr_id]
        print(f"\n  ── {tr_id} ({tr_name}) ──")
        try:
            result = fn(token)
            results[tr_id] = result if isinstance(result, dict) else {}
        except requests.exceptions.HTTPError as e:
            print(f"  [ERROR] HTTP: {e}  {getattr(e.response,'text','')[:200]}")
            results[tr_id] = {}
        except Exception as e:
            print(f"  [ERROR] {e}")
            results[tr_id] = {}

    # 핵심 필드 요약
    if any(k in results for k in ESSENTIAL_TRS):
        print_field_summary(results)

    # URI 최종 결과 출력
    print_uri_result()

    # 결과 JSON 저장
    out_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"gold_tr_test_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"  📁 결과 저장: {out_path}")
    except Exception as e:
        print(f"  [WARN] 결과 파일 저장 실패: {e}")


if __name__ == "__main__":
    main()
