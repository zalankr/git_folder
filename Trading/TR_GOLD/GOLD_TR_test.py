"""
============================================================================
 키움증권 REST API - KRX 금현물 TR 응답 필드 확인용 테스트 코드
 파일명   : GOLD_TR_test.py
 환경     : Python 3.9+

 ── 키움 .NET 공식 래퍼 소스에서 확인한 정확한 규격 ──────────────────────
  [URI — 기능별 공통 엔드포인트]
    시세 ka5xxxx → /api/dostk/mrkcond
    차트 ka5xxxx → /api/dostk/chart
    계좌 kt5xxxx → /api/dostk/acnt
    주문 kt5xxxx → /api/dostk/ordr

  [종목코드]  04020000 (X) → M04020000 (O, 앞에 'M')
    M04020000 : 금 99.99% 1kg 단위
    M04020100 : 미니금 99.99% 100g 단위

  [매매구분 trde_tp]  금현물은 시장가 없음. 지정가만 존재.
    "0"  보통(지정가)   "10" 보통IOC   "20" 보통FOK

  [주문 body]  계좌번호(acnt_no) 불필요 — 키움이 자동 인식
    stk_cd / ord_qty / trde_tp / ord_uv

 실행 방법:
   python3 GOLD_TR_test.py              # 핵심 조회 (자산 영향 없음)
   python3 GOLD_TR_test.py all          # 주문 제외 전체
   python3 GOLD_TR_test.py ka50100 kt50020
   python3 GOLD_TR_test.py order_buy    # ⚠️ 실제 1g 매수 주문
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
GOLD_STOCK_CODE = "M04020000"       # 금 99.99% 1kg (앞에 M 필수)
BASE_URL        = "https://api.kiwoom.com"
TOKEN_SAFETY_MARGIN_MIN = 30
TEST_ORDER_QTY  = 1                 # 주문 테스트 최소 수량 (1g)

try:
    with open(KEY_FILE_PATH, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f.readlines()]
    APP_KEY, APP_SECRET = lines[0], lines[1]
except Exception as e:
    print(f"[ERROR] key 파일 로드 실패: {e}")
    sys.exit(1)


# ===========================================================================
# TR → URI 매핑  (키움 .NET 래퍼 ApiEndpoint.cs 기준)
# ===========================================================================
URI_MRKCOND = "/api/dostk/mrkcond"   # 시세
URI_CHART   = "/api/dostk/chart"     # 차트
URI_ACNT    = "/api/dostk/acnt"      # 계좌
URI_ORDR    = "/api/dostk/ordr"      # 주문

TR_URI_MAP = {
    # 시세
    "ka50100": URI_MRKCOND, "ka50101": URI_MRKCOND, "ka50087": URI_MRKCOND,
    "ka50010": URI_MRKCOND, "ka50012": URI_MRKCOND, "ka52301": URI_MRKCOND,
    # 차트
    "ka50079": URI_CHART, "ka50080": URI_CHART, "ka50081": URI_CHART,
    "ka50082": URI_CHART, "ka50083": URI_CHART, "ka50091": URI_CHART,
    "ka50092": URI_CHART,
    # 계좌
    "kt50020": URI_ACNT, "kt50021": URI_ACNT, "kt50030": URI_ACNT,
    "kt50031": URI_ACNT, "kt50032": URI_ACNT, "kt50075": URI_ACNT,
    # 주문
    "kt50000": URI_ORDR, "kt50001": URI_ORDR,
    "kt50002": URI_ORDR, "kt50003": URI_ORDR,
}


# ===========================================================================
# 공통 유틸
# ===========================================================================
SEP, SEP2 = "=" * 65, "-" * 65


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
    """TR에 맞는 URI로 POST."""
    uri  = TR_URI_MAP.get(api_id, URI_MRKCOND)
    url  = f"{BASE_URL}{uri}"
    resp = requests.post(url, headers=_api_headers(token, api_id), json=body, timeout=timeout)
    data = resp.json() if resp.text else {}
    rc   = data.get("return_code", "?")
    mark = "✅" if rc == 0 else "❌"
    print(f"  {mark} HTTP {resp.status_code} | URI: {uri} | api-id: {api_id} | return_code={rc}")
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
    """금현물 시세정보 — open_pric/high_pric/low_pric/pred_close_pric (현재가 없음!)"""
    print("\n▶ [ka50100] 금현물 시세정보")
    s, d = _post(token, "ka50100", {"stk_cd": GOLD_STOCK_CODE})
    _log("ka50100 금현물 시세정보", d, s)
    return d

def test_ka50101(token):
    """금현물 호가 — gold_bid 리스트, item에 cntr_pric(체결가=현재가) 포함"""
    print("\n▶ [ka50101] 금현물 호가")
    s, d = _post(token, "ka50101", {"stk_cd": GOLD_STOCK_CODE, "tic_scope": "5"})
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
    today = datetime.date.today().strftime("%Y%m%d")
    s, d = _post(token, "ka50012", {"stk_cd": GOLD_STOCK_CODE, "base_dt": today})
    _log("ka50012 금현물 일별추이", d, s)
    return d

def test_ka52301(token):
    print("\n▶ [ka52301] 금현물 투자자현황")
    s, d = _post(token, "ka52301", {"stk_cd": GOLD_STOCK_CODE})
    _log("ka52301 금현물 투자자현황", d, s)
    return d


# ── 차트 ──────────────────────────────────────────────────────────────────

def test_ka50081(token):
    """금현물 일봉차트"""
    print("\n▶ [ka50081] 금현물 일봉차트")
    today = datetime.date.today().strftime("%Y%m%d")
    s, d = _post(token, "ka50081", {"stk_cd": GOLD_STOCK_CODE, "base_dt": today, "upd_stkpc_tp": "1"})
    _log("ka50081 금현물 일봉차트", d, s)
    return d

def test_ka50080(token):
    print("\n▶ [ka50080] 금현물 분봉차트")
    s, d = _post(token, "ka50080", {"stk_cd": GOLD_STOCK_CODE, "tic_scope": "1", "upd_stkpc_tp": "1"})
    _log("ka50080 금현물 분봉차트", d, s)
    return d

def test_ka50079(token):
    print("\n▶ [ka50079] 금현물 틱차트")
    s, d = _post(token, "ka50079", {"stk_cd": GOLD_STOCK_CODE, "tic_scope": "1", "upd_stkpc_tp": "1"})
    _log("ka50079 금현물 틱차트", d, s)
    return d

def test_ka50082(token):
    print("\n▶ [ka50082] 금현물 주봉차트")
    today = datetime.date.today().strftime("%Y%m%d")
    s, d = _post(token, "ka50082", {"stk_cd": GOLD_STOCK_CODE, "base_dt": today, "upd_stkpc_tp": "1"})
    _log("ka50082 금현물 주봉차트", d, s)
    return d

def test_ka50083(token):
    print("\n▶ [ka50083] 금현물 월봉차트")
    today = datetime.date.today().strftime("%Y%m%d")
    s, d = _post(token, "ka50083", {"stk_cd": GOLD_STOCK_CODE, "base_dt": today, "upd_stkpc_tp": "1"})
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
    """금현물 잔고확인 — body 없음(계좌 자동인식).
    응답: 최상위 tot_entr(예수금)/tot_est_amt(잔고평가) +
          gold_acnt_evlt_prst 리스트[real_qty/avg_prc/cur_prc/est_amt/est_lspft/est_ratio/able_qty]
    """
    print("\n▶ [kt50020] 금현물 잔고확인")
    s, d = _post(token, "kt50020", {})
    _log("kt50020 금현물 잔고확인", d, s)
    return d

def test_kt50021(token):
    """금현물 예수금 — entra(예수금)/prsm_entra(추정예수금)"""
    print("\n▶ [kt50021] 금현물 예수금")
    s, d = _post(token, "kt50021", {})
    _log("kt50021 금현물 예수금", d, s)
    return d

def test_kt50030(token):
    """금현물 주문체결전체조회"""
    print("\n▶ [kt50030] 금현물 주문체결전체조회")
    today = datetime.date.today().strftime("%Y%m%d")
    s, d = _post(token, "kt50030", {
        "ord_dt":       today,
        "mrkt_deal_tp": "0",       # 0=전체
        "stk_bond_tp":  "0",
        "slby_tp":      "0",       # 매도매수구분 (필드명 slby_tp 주의)
        "qry_tp":       "1",       # 1=주문순
        "stk_cd":       GOLD_STOCK_CODE,
        "fr_ord_no":    "",
        "dmst_stex_tp": "KRX",
    })
    _log("kt50030 금현물 주문체결전체조회", d, s)
    return d

def test_kt50031(token):
    """금현물 주문체결조회 — 응답: acnt_ord_cntr_prps_dtl 리스트
    item: ord_no/cntr_qty(체결수량)/cntr_uv(체결단가)/ord_remnq(주문잔량)
    """
    print("\n▶ [kt50031] 금현물 주문체결조회")
    today = datetime.date.today().strftime("%Y%m%d")
    s, d = _post(token, "kt50031", {
        "qry_tp":       "1",        # 1=주문순(전체) ※ 0은 무효값
        "stk_bond_tp":  "0",
        "sell_tp":      "0",
        "dmst_stex_tp": "KRX",
        "ord_dt":       today,
        "stk_cd":       GOLD_STOCK_CODE,
        "fr_ord_no":    "",
    })
    _log("kt50031 금현물 주문체결조회", d, s)
    return d

def test_kt50032(token):
    """금현물 거래내역조회"""
    print("\n▶ [kt50032] 금현물 거래내역조회")
    today    = datetime.date.today().strftime("%Y%m%d")
    week_ago = (datetime.date.today() - datetime.timedelta(days=7)).strftime("%Y%m%d")
    s, d = _post(token, "kt50032", {
        "strt_dt": week_ago,
        "end_dt":  today,
        "tp":      "0",          # 0=전체 (필수)
        "stk_cd":  GOLD_STOCK_CODE,
    })
    _log("kt50032 금현물 거래내역조회", d, s)
    return d

def test_kt50075(token):
    """금현물 미체결조회"""
    print("\n▶ [kt50075] 금현물 미체결조회")
    today = datetime.date.today().strftime("%Y%m%d")
    s, d = _post(token, "kt50075", {
        "ord_dt":       today,
        "mrkt_deal_tp": "0",
        "stk_bond_tp":  "0",
        "sell_tp":      "0",
        "qry_tp":       "1",       # 1=주문순
        "stk_cd":       GOLD_STOCK_CODE,
        "fr_ord_no":    "",
        "dmst_stex_tp": "KRX",
    })
    _log("kt50075 금현물 미체결조회", d, s)
    return d


# ── 주문 (⚠️ 실제 주문 발생) ────────────────────────────────────────────

# KRX 금현물 호가단위 10원 고정 — 주문단가 끝자리 0 필수
GOLD_TICK_SIZE = 10

def ceil_to_tick(price, tick=GOLD_TICK_SIZE):
    """호가단위 올림 (매수용)."""
    price = int(price)
    return ((price + tick - 1) // tick) * tick

def floor_to_tick(price, tick=GOLD_TICK_SIZE):
    """호가단위 내림 (매도용)."""
    price = int(price)
    return (price // tick) * tick


def _get_ref_price(token):
    """주문 단가 기준이 될 현재가 추정.
    1순위: kt50020 잔고의 cur_prc / 2순위: ka50100 전일종가
    """
    # 잔고에 보유 종목이 있으면 cur_prc 사용
    _, bal = _post(token, "kt50020", {})
    for item in bal.get("gold_acnt_evlt_prst", []) or []:
        cp = str(item.get("cur_prc", "")).replace(",", "").replace("+", "").replace("-", "").strip()
        if cp and cp != "0":
            return int(float(cp))
    # 없으면 시세의 전일종가
    _, info = _post(token, "ka50100", {"stk_cd": GOLD_STOCK_CODE})
    pc = str(info.get("pred_close_pric", "")).replace(",", "").replace("+", "").replace("-", "").strip()
    return int(float(pc)) if pc and pc != "0" else 0


def test_order_buy(token):
    print(f"\n{'!'*65}")
    print(f"  ⚠️  [kt50000] 금현물 매수주문 — 실제 주문이 발생합니다!")
    print(f"  수량: {TEST_ORDER_QTY}g / 종목: {GOLD_STOCK_CODE}")
    if input("  계속하려면 'yes' 입력: ").strip().lower() != "yes":
        print("  취소됨.")
        return {}

    ref   = _get_ref_price(token)
    price = ceil_to_tick(ref * 1.005) if ref > 0 else GOLD_TICK_SIZE
    print(f"  기준가: {ref:,}원 / 주문단가(+0.5%, 10원올림): {price:,}원")

    # 금현물 주문 body: 계좌번호 불필요, trde_tp="0"(보통/지정가)
    s, d = _post(token, "kt50000", {
        "stk_cd":  GOLD_STOCK_CODE,
        "ord_qty": str(TEST_ORDER_QTY),
        "ord_uv":  str(price),
        "trde_tp": "0",
    })
    _log("kt50000 금현물 매수주문", d, s)
    ord_no = d.get("ord_no", "")
    if ord_no:
        print(f"\n  ✅ 주문번호: {ord_no}")
        print(f"  → test_order_cancel(token, '{ord_no}') 으로 취소 가능")
    return d


def test_order_sell(token):
    print(f"\n{'!'*65}")
    print(f"  ⚠️  [kt50001] 금현물 매도주문 — 실제 주문이 발생합니다!")
    if input("  계속하려면 'yes' 입력: ").strip().lower() != "yes":
        print("  취소됨.")
        return {}

    ref   = _get_ref_price(token)
    price = floor_to_tick(ref * 0.995) if ref > 0 else GOLD_TICK_SIZE
    print(f"  기준가: {ref:,}원 / 주문단가(-0.5%, 10원내림): {price:,}원")

    s, d = _post(token, "kt50001", {
        "stk_cd":  GOLD_STOCK_CODE,
        "ord_qty": str(TEST_ORDER_QTY),
        "ord_uv":  str(price),
        "trde_tp": "0",
    })
    _log("kt50001 금현물 매도주문", d, s)
    ord_no = d.get("ord_no", "")
    if ord_no:
        print(f"\n  ✅ 주문번호: {ord_no}")
    return d


def test_order_cancel(token, ord_no, qty=0):
    """금현물 취소주문 (kt50003). qty=0 이면 잔량 전량 취소."""
    print(f"\n▶ [kt50003] 금현물 취소주문 (원주문: {ord_no}, 수량: {qty or '전량'})")
    s, d = _post(token, "kt50003", {
        "orig_ord_no": str(ord_no),
        "stk_cd":      GOLD_STOCK_CODE,
        "cncl_qty":    str(qty),
    })
    _log("kt50003 금현물 취소주문", d, s)
    return d


# ===========================================================================
# 핵심 필드 요약
# ===========================================================================
ESSENTIAL_TRS = ["ka50100", "ka50101", "kt50020", "kt50021", "kt50075"]

def print_field_summary(results: dict):
    print(f"\n\n{'#'*65}")
    print("  📋 GOLD_TR.py 수정에 필요한 핵심 필드 요약")
    print(f"{'#'*65}")

    checks = [
        ("ka50100 시세정보",  results.get("ka50100", {}),
         ["open_pric", "high_pric", "low_pric", "pred_close_pric"]),
        ("ka50101 호가",      results.get("ka50101", {}), ["gold_bid"]),
        ("kt50020 잔고확인",  results.get("kt50020", {}),
         ["tot_entr", "tot_est_amt", "gold_acnt_evlt_prst"]),
        ("kt50021 예수금",    results.get("kt50021", {}),
         ["entra", "prsm_entra"]),
        ("kt50075 미체결",    results.get("kt50075", {}), ["acnt_ord_oso_prst"]),
    ]

    for tr_name, data, fields in checks:
        print(f"\n  [{tr_name}]")
        if not data:
            print("    (응답 없음 또는 미실행)")
            continue
        rc = data.get("return_code", "?")
        if rc != 0:
            print(f"    ⚠️  return_code={rc}  msg={data.get('return_msg','')}")
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

    print(f"\n{'#'*65}\n")


# ===========================================================================
# TR 목록
# ===========================================================================
TR_MAP = {
    "ka50100": ("금현물 시세정보",     test_ka50100),
    "ka50101": ("금현물 호가",         test_ka50101),
    "ka50087": ("금현물 예상체결",     test_ka50087),
    "ka50010": ("금현물 체결추이",     test_ka50010),
    "ka50012": ("금현물 일별추이",     test_ka50012),
    "ka52301": ("금현물 투자자현황",   test_ka52301),
    "ka50079": ("금현물 틱차트",       test_ka50079),
    "ka50080": ("금현물 분봉차트",     test_ka50080),
    "ka50081": ("금현물 일봉차트",     test_ka50081),
    "ka50082": ("금현물 주봉차트",     test_ka50082),
    "ka50083": ("금현물 월봉차트",     test_ka50083),
    "ka50091": ("금현물 당일틱차트",   test_ka50091),
    "ka50092": ("금현물 당일분봉차트", test_ka50092),
    "kt50020": ("금현물 잔고확인",     test_kt50020),
    "kt50021": ("금현물 예수금",       test_kt50021),
    "kt50030": ("금현물 주문체결전체", test_kt50030),
    "kt50031": ("금현물 주문체결조회", test_kt50031),
    "kt50032": ("금현물 거래내역",     test_kt50032),
    "kt50075": ("금현물 미체결",       test_kt50075),
    "order_buy":  ("금현물 매수주문 ⚠️", test_order_buy),
    "order_sell": ("금현물 매도주문 ⚠️", test_order_sell),
}


# ===========================================================================
# 메인
# ===========================================================================
def main():
    print(f"\n{SEP}")
    print("  키움 금현물 TR 응답 필드 확인 테스트 (정확한 URI/규격 적용)")
    print(f"  실행시각: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  종목코드: {GOLD_STOCK_CODE}")
    print(f"\n  [URI]  시세={URI_MRKCOND}  차트={URI_CHART}")
    print(f"         계좌={URI_ACNT}  주문={URI_ORDR}")
    print(SEP)

    token   = get_access_token()
    args    = sys.argv[1:]
    results = {}

    # ── cancel <주문번호> [수량] : 미체결 주문 취소 ──────────────────────
    if args and args[0] == "cancel":
        if len(args) < 2:
            print("\n  사용법: python3 GOLD_TR_test.py cancel <주문번호> [취소수량]")
            print("  예시:   python3 GOLD_TR_test.py cancel 0229466")
            print("          (취소수량 생략 시 잔량 전량 취소)\n")
            return
        ord_no = args[1]
        qty    = int(args[2]) if len(args) >= 3 else 0
        test_order_cancel(token, ord_no, qty)
        return

    if not args:
        print(f"\n  ※ 인수 없음 → 핵심 조회 TR {ESSENTIAL_TRS} 실행")
        print(f"  ※ 전체: python3 GOLD_TR_test.py all")
        print(f"  ※ 주문 테스트: python3 GOLD_TR_test.py order_buy")
        print(f"  ※ 주문 취소: python3 GOLD_TR_test.py cancel <주문번호>\n")
        targets = ESSENTIAL_TRS
    elif "all" in args:
        targets = [k for k in TR_MAP if not k.startswith("order_")]
        print(f"\n  ※ 'all' → 주문 제외 전체 TR {len(targets)}개 실행")
    else:
        targets = args

    for tr_id in targets:
        if tr_id not in TR_MAP:
            print(f"\n  [WARN] 알 수 없는 TR: {tr_id!r}")
            continue
        tr_name, fn = TR_MAP[tr_id]
        print(f"\n  ── {tr_id} ({tr_name}) ──")
        try:
            result = fn(token)
            results[tr_id] = result if isinstance(result, dict) else {}
        except Exception as e:
            print(f"  [ERROR] {e}")
            results[tr_id] = {}

    if any(k in results for k in ESSENTIAL_TRS):
        print_field_summary(results)

    out_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"gold_tr_test_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"  📁 결과 저장: {out_path}")
    except Exception as e:
        print(f"  [WARN] 결과 저장 실패: {e}")


if __name__ == "__main__":
    main()
