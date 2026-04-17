"""
daily_snapshot.py
====================
다계좌 통합 일별 잔고 스냅샷

스케줄 (crontab, UTC):
  0 22 * * *  → KST 07:00 매일: US 모드 (미국주식 + Upbit)
  0  8 * * *  → KST 17:00 매일: ASIA 모드 (전계좌)

사용:
  python3 daily_snapshot.py US
  python3 daily_snapshot.py ASIA

계좌 정보: account_data.csv (CSV 기반 선언적 구성)
미연결 계좌(GOLD, 노라임, 노라송, 퇴직연금): 0원 placeholder
"""

import sys
import os
import json
import time
import requests
from datetime import datetime, timedelta
from collections import OrderedDict

sys.path.insert(0, "/var/autobot")
import telegram_alert as TA

# ══════════════════════════════════════════════════
#  공용 설정
# ══════════════════════════════════════════════════

BASE_URL     = "https://openapi.koreainvestment.com:9443"
KIS_KEY_DIR  = "/var/autobot/KIS"
UPBIT_KEY    = "/var/autobot/TR_Upbit/upnkr.txt"
USAA_TR_PATH = "/var/autobot/TR_USAA/USAA_TR.json"
SNAPSHOT_DIR = "/var/autobot/Balance"
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

MAX_PAGE = 30
API_SLEEP = 0.12    # KIS rate limit: 20/sec 이론, 실사용 ~8/sec

# ══════════════════════════════════════════════════
#  계좌 구성 (account_data.csv 반영)
# ══════════════════════════════════════════════════
# CSV 열 순서대로 출력하기 위해 선언적 리스트로 관리
# each: (market, strategy, sub, cano, acnt_prdt_cd, handler, kwargs)
# handler는 아래 정의된 전략 핸들러 함수명

ACCOUNTS = [
    # ── KR Market ─────────────────────────────────
    ("KR Market", "KRTR", "PEAK",       "43018646", "01", "kr_simple",   {}),
    ("KR Market", "KRTR", "VALUE",      "44036546", "01", "kr_simple",   {}),
    ("KR Market", "KRTR", "MOMENTUM",   "44287475", "01", "kr_simple",   {}),
    ("KR Market", "KRTR", "Coverdcall", "63751991", "01", "kr_simple",   {}),

    # KRQT: 단일 계좌 + 4개 세부전략 (category csv 기반 분류)
    ("KR Market", "KRQT", "Small Cap Growth", "63604155", "01", "kr_krqt_cat", {"category": "Small Cap Growth"}),
    ("KR Market", "KRQT", "Small Cap Simple-Fin", "63604155", "01", "kr_krqt_cat", {"category": "Small Cap Simple-Fin"}),
    ("KR Market", "KRQT", "Middle Cap", "63604155", "01", "kr_krqt_cat", {"category": "Middle Cap"}),
    ("KR Market", "KRQT", "Large Cap",  "63604155", "01", "kr_krqt_cat", {"category": "Large Cap"}),

    # KRFT: 국내선물옵션 (acnt_prdt_cd=03) — CTFO6118R 전용 TR 사용
    ("KR Market", "KRFT", "Hedge & Boost", "64753341", "03", "krft", {"currency": "KRW"}),

    # ── Global Market ────────────────────────────
    # USAA: 단일 계좌 + USLA/HAA (종목 티커 기반 분류)
    ("Global Market", "USAA", "USLA",   "63604155", "01", "us_usaa_sub", {"sub": "USLA"}),
    ("Global Market", "USAA", "HAA",    "63604155", "01", "us_usaa_sub", {"sub": "HAA"}),

    # USQT: 단일 계좌 + SCG/TCM (category csv 기반 분류)
    ("Global Market", "USQT", "SCG",    "63692011", "01", "us_usqt_cat", {"category": "SCG"}),
    ("Global Market", "USQT", "TCM",    "63692011", "01", "us_usqt_cat", {"category": "TCM"}),

    # JPQT: 일본주식
    ("Global Market", "JPQT", "JPQT1", "63604155", "01", "overseas_all", {"natn_cd": "392", "currency": "JPY", "excg": "TKSE", "repr_cd": "7203"}),

    # HKQT: 홍콩주식
    ("Global Market", "HKQT", "HKQ1T", "63604155", "01", "overseas_all", {"natn_cd": "344", "currency": "HKD", "excg": "SEHK", "repr_cd": "00700"}),

    # ETC: 일본 채권 (일본주식 API로 조회)
    ("Global Market", "ETC",  "JPUSbond", "63721147", "01", "overseas_all", {"natn_cd": "392", "currency": "JPY", "excg": "TKSE", "repr_cd": "7203"}),

    # GBFT: 해외선물옵션 (acnt_prdt_cd=08) — OTFR2102R 전용 TR 사용
    ("Global Market", "GBFT", "Hedge & Boost", "64753341", "08", "gbft", {"currency": "USD"}),
    ("Global Market", "GBFT", "Commmodity",    "64753341", "08", "gbft", {"currency": "USD"}),

    # ── Alternative ──────────────────────────────
    ("Alternative", "Gold",   "Gold",   "키움 52953897", "", "placeholder", {"currency": "KRW"}),
    ("Alternative", "Crypto", "Crypto", "ilpus@naver.com", "", "upbit", {}),

    # ── 연금 & ISA ────────────────────────────────
    ("연금&ISA", "ISA",     "ISA",        "43665648", "01", "kr_simple",   {}),
    ("연금&ISA", "ISA",     "윤숙ISA",    "43680827", "01", "kr_simple",   {}),
    ("연금&ISA", "Pension", "연금저축-1", "43685950", "22", "kr_simple",   {}),
    ("연금&ISA", "Pension", "연금저축-2", "44334640", "22", "kr_simple",   {}),
    ("연금&ISA", "Pension", "IRP",        "43685950", "29", "kr_simple",   {}),
    ("연금&ISA", "Pension", "퇴직연금",   "미래에셋", "",   "placeholder", {"currency": "KRW"}),

    # ── 기타 자산 ─────────────────────────────────
    ("기타 자산", "노라임", "노라임", "44249970", "01", "placeholder", {"currency": "KRW"}),
    ("기타 자산", "노라송", "노라송", "44249994", "01", "placeholder", {"currency": "KRW"}),
]

# ASIA 모드에서도 USAA/USQT/Crypto는 **다시 조회**해서 최종 스냅샷으로 덮어씀
# (장중 환율/가격이 저녁까지 바뀌므로)
# 07시 실행 대상
US_MODE_KEYS = {"USAA", "USQT", "Crypto"}


# ══════════════════════════════════════════════════
#  KIS 인증 (계좌별 토큰 관리)
# ══════════════════════════════════════════════════

_token_cache = {}   # {cano: {"appkey":..., "secret":..., "token":...}}

def load_kis_keys(cano: str) -> tuple:
    """계좌별 appkey/secret 로드"""
    path = f"{KIS_KEY_DIR}/kis{cano}nkr.txt"
    if cano == "43680827":
        path = f"{KIS_KEY_DIR}/kis{cano}lys.txt"
    with open(path) as f:
        lines = [l.strip() for l in f.readlines()]
    return lines[0], lines[1]


def get_kis_token(cano: str) -> tuple:
    """
    계좌별 access_token 발급/캐시.
    Returns: (access_token, app_key, app_secret)
    토큰파일: /var/autobot/KIS/kis{cano}_token.json
    동일 appkey를 쓰는 계좌는 토큰도 자동 공유됨 (파일 경로는 cano별이지만 키는 같음)
    """
    if cano in _token_cache:
        c = _token_cache[cano]
        return c["token"], c["appkey"], c["secret"]

    app_key, app_secret = load_kis_keys(cano)
    token_file = f"{KIS_KEY_DIR}/kis{cano}_token.json"

    # 캐시 파일 체크
    if os.path.exists(token_file):
        try:
            with open(token_file) as f:
                td = json.load(f)
            issued = datetime.fromisoformat(td["issued_at"])
            exp = issued + timedelta(seconds=td.get("expires_in", 86400))
            if datetime.now() < exp - timedelta(minutes=60):
                _token_cache[cano] = {"token": td["access_token"],
                                       "appkey": app_key, "secret": app_secret}
                return td["access_token"], app_key, app_secret
        except Exception:
            pass

    # 신규 발급
    body = {"grant_type": "client_credentials", "appkey": app_key, "appsecret": app_secret}
    r = requests.post(f"{BASE_URL}/oauth2/tokenP",
                      headers={"content-type": "application/json"},
                      json=body, timeout=10)
    r.raise_for_status()
    data = r.json()
    td = {"access_token": data["access_token"],
          "issued_at": datetime.now().isoformat(),
          "expires_in": data.get("expires_in", 86400)}
    with open(token_file, "w") as f:
        json.dump(td, f, indent=2)
    _token_cache[cano] = {"token": td["access_token"],
                           "appkey": app_key, "secret": app_secret}
    return td["access_token"], app_key, app_secret


def kis_headers(cano: str, tr_id: str) -> dict:
    tok, ak, sc = get_kis_token(cano)
    return {
        "Content-Type": "application/json",
        "authorization": f"Bearer {tok}",
        "appKey": ak,
        "appSecret": sc,
        "tr_id": tr_id,
        "custtype": "P"
    }


# ══════════════════════════════════════════════════
#  국내주식 잔고 조회 (TTTC8434R)
# ══════════════════════════════════════════════════

def fetch_kr_balance(cano: str, acnt_prdt_cd: str) -> dict:
    """
    한국주식 계좌 잔고 조회 (페이지네이션 포함)
    Returns:
      {"stocks": [{code,name,qty,eval_amt,price,profit_rate}],
       "stock_eval": float, "cash": float, "total": float}
    """
    url = f"{BASE_URL}/uapi/domestic-stock/v1/trading/inquire-balance"
    h = kis_headers(cano, "TTTC8434R")
    params = {
        "CANO": cano, "ACNT_PRDT_CD": acnt_prdt_cd,
        "AFHR_FLPR_YN": "N", "OFL_YN": "", "INQR_DVSN": "00",
        "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N",
        "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00",
        "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""
    }

    stock_eval = 0.0
    total = 0.0
    stocks = []
    tr_cont_req = ""
    page = 0

    try:
        while True:
            h["tr_cont"] = tr_cont_req
            time.sleep(API_SLEEP)
            r = requests.get(url, headers=h, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            resp_tr_cont = r.headers.get("tr_cont", "").strip()

            if data.get("rt_cd") != "0":
                return {"error": data.get("msg1", "API 오류")}

            for s in data.get("output1", []):
                qty = int(s.get("hldg_qty", 0) or 0)
                if qty == 0:
                    continue
                evl = float(s.get("evlu_amt", 0) or 0)
                stock_eval += evl
                stocks.append({
                    "code": s.get("pdno", ""),
                    "name": s.get("prdt_name", ""),
                    "qty": qty,
                    "eval_amt": evl,
                    "price": int(float(s.get("prpr", 0) or 0)),
                    "profit_rate": float(s.get("evlu_pfls_rt", 0) or 0)
                })

            out2 = data.get("output2", [{}])
            nass_page = float((out2[0] if out2 else {}).get("nass_amt", 0) or 0)
            if nass_page > 0:
                total = nass_page

            page += 1
            if page >= MAX_PAGE:
                break
            if resp_tr_cont in ("D", "E", "F"):
                break
            fk = data.get("ctx_area_fk100", "").strip()
            nk = data.get("ctx_area_nk100", "").strip()
            if not fk or not nk:
                break
            params["CTX_AREA_FK100"] = fk
            params["CTX_AREA_NK100"] = nk
            tr_cont_req = "N"

    except Exception as e:
        return {"error": f"KR 조회 예외: {e}"}

    cash = total - stock_eval if total > 0 else 0.0
    return {"stocks": stocks, "stock_eval": stock_eval, "cash": cash, "total": total}


# ══════════════════════════════════════════════════
#  국내선물옵션 잔고 조회 (CTFO6118R)
# ══════════════════════════════════════════════════

def fetch_krft_balance(cano: str, acnt_prdt_cd: str) -> dict:
    """
    국내선물옵션 계좌 잔고 조회 (acnt_prdt_cd="03")
    TR_ID: CTFO6118R (실전투자 전용)
    - output1: 보유 포지션 리스트
    - output2: 예수금/증거금 합계
    Returns:
      {"stocks": [{code,name,qty,eval_amt,price,profit_rate}],
       "stock_eval": float, "cash": float, "total": float}
    ※ output field명(cblc_qty, dncl_amt 등)은 실계좌 첫 응답 후 확인 필요
    """
    url = f"{BASE_URL}/uapi/domestic-futureoption/v1/trading/inquire-balance"
    h = kis_headers(cano, "CTFO6118R")
    params = {
        "CANO": cano, "ACNT_PRDT_CD": acnt_prdt_cd,
        "MGNA_DVSN": "01",       # 증거금 구분: 01=개시증거금
        "EXCC_UNPR_DVSN": "01",  # 정산단가 구분: 01=현재가
        "STTL_STTS_CD": "0",     # 정산상태코드: 0=전체, 1=미결제, 2=정산완료
        "CTX_AREA_FK200": "",
        "CTX_AREA_NK200": ""
    }

    stocks = []
    stock_eval = 0.0
    cash = 0.0
    total = 0.0
    tr_cont_req = ""
    page = 0

    try:
        while True:
            h["tr_cont"] = tr_cont_req
            time.sleep(API_SLEEP)
            r = requests.get(url, headers=h, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            resp_tr_cont = r.headers.get("tr_cont", "").strip()

            if data.get("rt_cd") != "0":
                return {"error": data.get("msg1", "국내선물 API 오류")}

            for s in data.get("output1", []):
                qty = int(float(s.get("cblc_qty", 0) or 0))
                if qty == 0:
                    continue
                evl = float(s.get("evlu_amt", 0) or 0)
                stock_eval += evl
                stocks.append({
                    "code": s.get("pdno", ""),
                    "name": s.get("prdt_name", ""),
                    "qty": qty,
                    "eval_amt": evl,
                    "price": float(s.get("prpr", 0) or 0),
                    "profit_rate": float(s.get("evlu_pfls_rt", 0) or 0)
                })

            out2 = data.get("output2", [{}])
            d2 = out2[0] if out2 else {}
            # dncl_amt: 예수금, tot_asst_amt: 총자산
            cash_page  = float(d2.get("dncl_amt", 0) or 0)
            total_page = float(d2.get("tot_asst_amt", 0) or 0)
            if cash_page > 0:
                cash = cash_page
            if total_page > 0:
                total = total_page

            page += 1
            if page >= MAX_PAGE:
                break
            if resp_tr_cont in ("D", "E", "F"):
                break
            fk = data.get("ctx_area_fk200", "").strip()
            nk = data.get("ctx_area_nk200", "").strip()
            if not fk or not nk:
                break
            params["CTX_AREA_FK200"] = fk
            params["CTX_AREA_NK200"] = nk
            tr_cont_req = "N"

    except Exception as e:
        return {"error": f"국내선물 조회 예외: {e}"}

    if total <= 0:
        total = stock_eval + cash
    return {"stocks": stocks, "stock_eval": stock_eval, "cash": cash, "total": total}


# ══════════════════════════════════════════════════
#  해외선물옵션 잔고 조회 (OTFR2102R)
# ══════════════════════════════════════════════════

def fetch_gbft_balance(cano: str, acnt_prdt_cd: str, currency: str = "USD") -> dict:
    """
    해외선물옵션 예수금/증거금 조회 (acnt_prdt_cd="08")
    TR_ID: OTFR1101R — 해외선물옵션 예수금현황
    잔고 0원 상태에서도 호출 가능 (계좌 개설 후 입고금 없을 때)
    """
    url = f"{BASE_URL}/uapi/overseas-futureoption/v1/trading/inquire-deposit"
    h = kis_headers(cano, "OTFR1101R")
    params = {
        "CANO": cano, "ACNT_PRDT_CD": acnt_prdt_cd,
        "CRCY_CD": currency,    # USD / HKD 등
        "INQR_DVSN_CD": "0",   # 조회구분: 0=전체
    }

    stocks = []
    stock_eval = 0.0
    cash = 0.0
    exrt = 0.0

    try:
        time.sleep(API_SLEEP)
        r = requests.get(url, headers=h, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        if data.get("rt_cd") != "0":
            return {"error": data.get("msg1", "해외선물 예수금 조회 오류")}

        out = data.get("output", {})
        cash = float(out.get("frcr_dncl_amt", 0) or 0)
        exrt = float(out.get("exrt", 0) or 0)

    except Exception as e:
        return {"error": f"해외선물 조회 예외: {e}"}

    return {
        "stocks": stocks, "stock_eval": stock_eval,
        "cash": cash, "total": cash,   # 포지션 없으면 예수금 = 총자산
        "exchange_rate": exrt
    }


# ══════════════════════════════════════════════════
#  해외주식 잔고 조회 (CTRP6504R + TTTS3007R)
# ══════════════════════════════════════════════════

def fetch_overseas_balance(cano: str, acnt_prdt_cd: str,
                             natn_cd: str, currency: str,
                             excg: str, repr_cd: str,
                             price: str = "100") -> dict:
    """
    해외주식 계좌 잔고 조회 + 환율 + 주문가능금액
    Returns:
      {"stocks": [...], "stock_eval": float, "cash": float, "total": float,
       "exchange_rate": float, "frcr_deposit": float,
       "today_sell_amt": float, "today_buy_amt": float,
       "orderable_cash": float, "sll_ruse": float}
    """
    url = f"{BASE_URL}/uapi/overseas-stock/v1/trading/inquire-present-balance"
    h = kis_headers(cano, "CTRP6504R")
    params = {
        "CANO": cano, "ACNT_PRDT_CD": acnt_prdt_cd,
        "WCRC_FRCR_DVSN_CD": "02", "NATN_CD": natn_cd,
        "TR_MKET_CD": "00", "INQR_DVSN_CD": "00",
        "CTX_AREA_FK200": "", "CTX_AREA_NK200": ""
    }

    stocks = []
    stock_eval = 0.0
    today_sell_amt = 0.0
    today_buy_amt  = 0.0
    tr_cont_req = ""
    page = 0

    try:
        while True:
            h["tr_cont"] = tr_cont_req
            time.sleep(API_SLEEP)
            r = requests.get(url, headers=h, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            resp_tr_cont = r.headers.get("tr_cont", "").strip()
            if data.get("rt_cd") != "0":
                return {"error": data.get("msg1", "API 오류")}

            for s in data.get("output1", []):
                today_sell_amt += float(s.get("thdt_sll_ccld_amt2", 0) or 0)
                today_buy_amt  += float(s.get("thdt_buy_ccld_amt2", 0) or 0)
                qty = int(float(s.get("ccld_qty_smtl1", 0) or 0))
                if qty == 0:
                    continue
                evl = float(s.get("frcr_evlu_amt2", 0) or 0)
                stock_eval += evl
                stocks.append({
                    "code": s.get("pdno", ""),
                    "name": s.get("prdt_name", ""),
                    "qty": qty,
                    "eval_amt": evl,
                    "price": float(s.get("ovrs_now_pric1", 0) or 0),
                    "avg_price": float(s.get("avg_unpr3", 0) or 0),
                    "profit_rate": float(s.get("evlu_pfls_rt1", 0) or 0)
                })

            page += 1
            if page >= MAX_PAGE:
                break
            if resp_tr_cont in ("D", "E", "F"):
                break
            FK = data.get("ctx_area_fk200", "").strip()
            NK = data.get("ctx_area_nk200", "").strip()
            if not FK or not NK:
                break
            params["CTX_AREA_FK200"] = FK
            params["CTX_AREA_NK200"] = NK
            tr_cont_req = "N"

    except Exception as e:
        return {"error": f"{currency} 조회 예외: {e}"}

    # TTTS3007R: 통화별 정확 조회
    time.sleep(API_SLEEP)
    url2 = f"{BASE_URL}/uapi/overseas-stock/v1/trading/inquire-psamount"
    params2 = {
        "CANO": cano, "ACNT_PRDT_CD": acnt_prdt_cd,
        "OVRS_EXCG_CD": excg, "ITEM_CD": repr_cd, "OVRS_ORD_UNPR": price
    }
    orderable = 0.0
    frcr_deposit = 0.0
    sll_ruse = 0.0
    exrt = 0.0
    try:
        r2 = requests.get(url2, headers=kis_headers(cano, "TTTS3007R"),
                          params=params2, timeout=10)
        r2.raise_for_status()
        d2 = r2.json()
        if d2.get("rt_cd") == "0":
            out = d2.get("output", {})
            orderable    = float(out.get("ovrs_ord_psbl_amt", 0) or 0)
            frcr_deposit = float(out.get("ord_psbl_frcr_amt", 0) or 0)
            sll_ruse     = float(out.get("sll_ruse_psbl_amt", 0) or 0)
            exrt         = float(out.get("exrt", 0) or 0)
    except Exception:
        pass

    real_deposit = frcr_deposit + today_sell_amt - today_buy_amt

    return {
        "stocks": stocks,
        "stock_eval": stock_eval,
        "cash": real_deposit,
        "total": stock_eval + real_deposit,
        "exchange_rate": exrt,
        "frcr_deposit": frcr_deposit,
        "today_sell_amt": today_sell_amt,
        "today_buy_amt": today_buy_amt,
        "orderable_cash": orderable,
        "sll_ruse": sll_ruse
    }


# ══════════════════════════════════════════════════
#  Upbit 잔고 조회 (pyupbit 사용)
# ══════════════════════════════════════════════════

def load_upbit_keys() -> tuple:
    with open(UPBIT_KEY) as f:
        lines = [l.strip() for l in f.readlines()]
    return lines[0], lines[1]


def fetch_upbit_balance() -> dict:
    """
    업비트 전체 잔고 조회 (pyupbit 사용)
    - get_balance_t("KRW"): 원화 잔고
    - get_balances(): 전체 코인 보유 리스트
    - get_current_price(ticker): 종목별 현재가 (상폐/미존재 코인 대응)

    상장폐지되거나 BTC 마켓 전용 코인(KRW-xxx 없음)은 현재가 조회 실패해도
    eval_amt=0으로 기록하고 계속 진행 (전체 404 터지지 않도록).
    """
    try:
        import pyupbit
    except ImportError:
        return {"error": "pyupbit 모듈 미설치 (pip install pyupbit)"}

    try:
        ak, sk = load_upbit_keys()
    except Exception as e:
        return {"error": f"Upbit 키 로드 실패: {e}"}

    try:
        upbit = pyupbit.Upbit(ak, sk)
    except Exception as e:
        return {"error": f"Upbit 접속 실패: {e}"}

    # KRW 잔고
    try:
        cash = float(upbit.get_balance_t("KRW") or 0)
    except Exception as e:
        return {"error": f"Upbit KRW 잔고 오류: {e}"}

    # 전체 보유 자산 (KRW 포함됨)
    try:
        balances = upbit.get_balances()
    except Exception as e:
        return {"error": f"Upbit 잔고 목록 오류: {e}"}

    if not isinstance(balances, list):
        return {"error": f"Upbit get_balances 응답 이상: {type(balances)}"}

    stocks = []
    stock_eval = 0.0

    for a in balances:
        cur = a.get("currency", "")
        if cur == "KRW":
            continue
        bal = float(a.get("balance", 0) or 0) + float(a.get("locked", 0) or 0)
        if bal <= 0:
            continue
        avg = float(a.get("avg_buy_price", 0) or 0)
        ticker = f"KRW-{cur}"

        # 현재가 조회 - 실패해도 건너뛰지 말고 avg_buy_price로 대체
        try:
            price = pyupbit.get_current_price(ticker)
            price = float(price) if price is not None else 0.0
        except Exception:
            price = 0.0

        if price <= 0:
            # KRW 마켓에 없는 코인(BTC/USDT 마켓 전용 또는 상폐)
            # 평균매입가로 대체 평가
            price = avg
            note = "현재가조회불가 (매입가 대체)"
        else:
            note = ""

        evl = bal * price
        stock_eval += evl
        profit_rate = ((price / avg) - 1.0) * 100 if avg > 0 else 0.0
        item = {
            "code": cur,
            "name": cur,
            "qty": bal,
            "eval_amt": evl,
            "price": price,
            "profit_rate": profit_rate,
            "avg_price": avg
        }
        if note:
            item["note"] = note
        stocks.append(item)

    return {
        "stocks": stocks,
        "stock_eval": stock_eval,
        "cash": cash,
        "total": stock_eval + cash,
        "currency": "KRW"
    }


# ══════════════════════════════════════════════════
#  USAA 서브전략 분류 (USLA / HAA)
# ══════════════════════════════════════════════════

USLA_TICKERS = {"UPRO", "TQQQ", "EDC", "TMV", "TMF"}
HAA_TICKERS  = {"SPY", "IWM", "VEA", "VWO", "PDBC", "VNQ", "TLT", "IEF", "BIL"}


def load_usaa_tr() -> dict:
    """USAA_TR.json 로드"""
    if not os.path.exists(USAA_TR_PATH):
        return {}
    try:
        with open(USAA_TR_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def split_usaa(usd_balance: dict, usaa_tr: dict) -> dict:
    """
    USD 잔고를 USLA/HAA로 분리
    외화RP 보정이 들어간 usd_balance["cash"]를 그대로 사용
    """
    usla_usd_json = float(usaa_tr.get("USD_USLA", 0))
    haa_usd_json  = float(usaa_tr.get("USD_HAA", 0))
    usla_mode     = usaa_tr.get("USLA_Mode", "알수없음")
    haa_mode      = usaa_tr.get("HAA_Mode",  "알수없음")

    usla_stocks = []
    usla_eval = 0.0
    haa_stocks = []
    haa_eval = 0.0

    for s in usd_balance.get("stocks", []):
        if s["code"] in USLA_TICKERS:
            usla_stocks.append(s)
            usla_eval += s["eval_amt"]
        else:
            haa_stocks.append(s)
            haa_eval += s["eval_amt"]

    total_cash = usd_balance.get("cash", 0)

    if usla_mode == "헷징모드" or usla_eval == 0:
        usla_cash = min(usla_usd_json, total_cash)
        haa_cash  = total_cash - usla_cash
    else:
        jt = usla_usd_json + haa_usd_json
        ratio = (usla_usd_json / jt) if jt > 0 else 0.66
        usla_cash = total_cash * ratio
        haa_cash  = total_cash - usla_cash

    return {
        "USLA_Mode": usla_mode,
        "HAA_Mode": haa_mode,
        "USLA": {"total_usd": usla_eval + usla_cash,
                  "stock_eval": usla_eval, "cash": usla_cash,
                  "stocks": usla_stocks},
        "HAA":  {"total_usd": haa_eval + haa_cash,
                  "stock_eval": haa_eval, "cash": haa_cash,
                  "stocks": haa_stocks}
    }


# ══════════════════════════════════════════════════
#  외화RP 보정 (USAA 헷징/수비모드 대응)
# ══════════════════════════════════════════════════

def get_prev_usd_cash(max_lookback_days: int = 10) -> tuple:
    """
    전일 USD 현금 조회 (balance JSON에서).
    신/구 두 가지 포맷을 모두 지원하여 연속성 유지.

    - 신 포맷: US.categories.USAA.items[USLA].usd_raw.cash(_adjusted)
    - 구 포맷: US.USD.cash_adjusted → US.USD.cash (단일계좌 버전)
    """
    today = datetime.now().date()
    for i in range(1, max_lookback_days + 1):
        d = today - timedelta(days=i)
        fp = os.path.join(SNAPSHOT_DIR, f"balance_{d.strftime('%Y%m%d')}.json")
        if not os.path.exists(fp):
            continue
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
            prev = 0.0

            # ① 신 포맷: categories.USAA.items 중 USLA 엔트리의 usd_raw
            us_block = data.get("US", {})
            cats = us_block.get("categories", {}) if isinstance(us_block, dict) else {}
            usaa_items = cats.get("USAA", {}).get("items", []) if isinstance(cats, dict) else []
            for it in usaa_items:
                urw = it.get("usd_raw", {}) if isinstance(it, dict) else {}
                if urw:
                    prev = float(urw.get("cash_adjusted", urw.get("cash", 0)) or 0)
                    if prev > 0:
                        break

            # ② 구 포맷 fallback: US.USD.cash_adjusted 또는 US.USD.cash
            if prev <= 0 and isinstance(us_block, dict):
                usd_old = us_block.get("USD", {})
                if isinstance(usd_old, dict):
                    prev = float(usd_old.get("cash_adjusted",
                                 usd_old.get("cash", 0)) or 0)

            if prev > 0:
                return prev, d.strftime("%Y%m%d")
        except Exception:
            continue
    return 0.0, ""


def apply_rp_adjustment(usd_raw: dict, usaa_tr: dict) -> tuple:
    """
    외화RP 보정 적용
    Returns: (adjusted_usd, rp_adjusted_bool, rp_prev_date, original_cash)
    """
    original_cash = usd_raw.get("cash", 0)
    usla_mode = usaa_tr.get("USLA_Mode", "")
    haa_mode  = usaa_tr.get("HAA_Mode", "")
    is_defensive = (usla_mode == "헷징모드") or (haa_mode == "수비모드")
    if not (is_defensive and original_cash < 10.0):
        return usd_raw, False, "", original_cash

    prev_cash, prev_date = get_prev_usd_cash()
    if prev_cash <= 0:
        return usd_raw, False, "", original_cash

    usd_raw["cash"] = prev_cash
    usd_raw["total"] = usd_raw["stock_eval"] + prev_cash
    usd_raw["cash_adjusted"] = prev_cash
    usd_raw["cash_adjustment_reason"] = "외화RP 추정 (전일값 승계)"
    return usd_raw, True, prev_date, original_cash


# ══════════════════════════════════════════════════
#  KRQT/USQT 카테고리 분류 (CSV 기반)
# ══════════════════════════════════════════════════

def load_category_map(csv_path: str, us: bool = False) -> dict:
    """
    stock.csv 로드 → {code: category}
    code는 국내: 'A삼성' → '005930' (첫글자 제거), 미국: 그대로
    같은 code가 여러 category에 속하면 첫 번째만 사용 (경고)
    """
    if not os.path.exists(csv_path):
        return {}
    mapping = {}
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        # header 파싱
        header = [h.strip() for h in lines[0].strip().split(",")]
        ci = {h: i for i, h in enumerate(header)}
        for raw in lines[1:]:
            parts = [p.strip() for p in raw.strip().split(",")]
            if len(parts) < len(header):
                continue
            code = parts[ci.get("code", 0)]
            cat  = parts[ci.get("category", 3)]
            if not code or not cat or cat.lower() == "nan":
                continue
            # 국내주식: A 접두어 제거
            if not us and code.startswith(("A", "a")):
                code = code[1:]
            if code == "CASH":
                continue
            if code not in mapping:
                mapping[code] = cat
    except Exception:
        return {}
    return mapping


def filter_by_category(balance: dict, code_to_cat: dict, target_cat: str) -> dict:
    """balance의 stocks를 category로 필터링해 반환 (eval_amt만 재합산)"""
    filtered = []
    stock_eval = 0.0
    for s in balance.get("stocks", []):
        if code_to_cat.get(s["code"]) == target_cat:
            filtered.append(s)
            stock_eval += s["eval_amt"]
    return {"stocks": filtered, "stock_eval": stock_eval}


# ══════════════════════════════════════════════════
#  전일 대비 변동율 계산
# ══════════════════════════════════════════════════

def get_prev_snapshot() -> dict:
    """전일 balance JSON 전체 로드"""
    today = datetime.now().date()
    for i in range(1, 10):
        d = today - timedelta(days=i)
        fp = os.path.join(SNAPSHOT_DIR, f"balance_{d.strftime('%Y%m%d')}.json")
        if os.path.exists(fp):
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                continue
    return {}


def calc_day_change(curr: float, prev: float) -> float:
    """전일 대비 변동율 (%). 전일 0이면 0.0"""
    if prev <= 0:
        return 0.0
    return ((curr - prev) / prev) * 100


def find_prev_entry(prev_snapshot: dict, market: str, strategy: str, sub: str) -> dict:
    """전일 JSON에서 동일 (market, strategy, sub) 항목 찾기"""
    for mode in ("ASIA", "US"):
        cats = prev_snapshot.get(mode, {}).get("categories", {})
        for k, v in cats.items():
            if not isinstance(v, dict):
                continue
            items = v.get("items", [])
            for it in items:
                if (it.get("market") == market and
                    it.get("strategy") == strategy and
                    it.get("sub") == sub):
                    return it
    return {}


def find_prev_stock(prev_entry: dict, code: str) -> dict:
    """전일 entry의 stocks 리스트에서 code 검색"""
    for s in prev_entry.get("stocks", []):
        if s.get("code") == code:
            return s
    return {}


# ══════════════════════════════════════════════════
#  전략 핸들러 — 하나의 (market, strategy, sub) 항목 처리
# ══════════════════════════════════════════════════

# 계좌 단위 캐시 (동일 계좌 재조회 방지)
_account_cache = {}


def _cache_key(handler: str, cano: str, acnt_prdt_cd: str, extra: str = "") -> str:
    return f"{handler}:{cano}:{acnt_prdt_cd}:{extra}"


def handle_kr_simple(cano: str, acnt: str, kwargs: dict) -> dict:
    """일반 한국주식 계좌 전체 잔고 반환 (KRW 기준)"""
    key = _cache_key("kr", cano, acnt)
    if key in _account_cache:
        bal = _account_cache[key]
    else:
        bal = fetch_kr_balance(cano, acnt)
        _account_cache[key] = bal
    if "error" in bal:
        return {"error": bal["error"], "currency": "KRW",
                 "total_krw": 0.0, "stock_eval_krw": 0.0, "cash_krw": 0.0, "stocks": []}
    return {
        "currency": "KRW",
        "total_krw": bal["total"],
        "stock_eval_krw": bal["stock_eval"],
        "cash_krw": bal["cash"],
        "stocks": bal["stocks"],
        "exchange_rate": 1.0
    }


def handle_kr_krqt_cat(cano: str, acnt: str, kwargs: dict) -> dict:
    """KRQT 계좌의 카테고리별 분리"""
    category = kwargs["category"]
    key = _cache_key("kr", cano, acnt)
    if key in _account_cache:
        bal = _account_cache[key]
    else:
        bal = fetch_kr_balance(cano, acnt)
        _account_cache[key] = bal
    if "error" in bal:
        return {"error": bal["error"], "currency": "KRW",
                 "total_krw": 0.0, "stock_eval_krw": 0.0, "cash_krw": 0.0, "stocks": []}

    csv_path = "/var/autobot/TR_KRQT/KRQT_stock.csv"
    cat_map = load_category_map(csv_path, us=False)
    cat_filtered = filter_by_category(bal, cat_map, category)

    # KRQT의 4개 세부전략은 cash를 SCG에만 몰아주지 않고, 카테고리별 주식평가금에 비례 배분하지 않음
    # → 서브전략별 표시는 주식평가금만. 계좌 전체 cash는 SCG(메인)에만 기록
    is_main = (category == "SCG")
    cash = bal["cash"] if is_main else 0.0
    total = cat_filtered["stock_eval"] + cash

    return {
        "currency": "KRW",
        "total_krw": total,
        "stock_eval_krw": cat_filtered["stock_eval"],
        "cash_krw": cash,
        "stocks": cat_filtered["stocks"],
        "exchange_rate": 1.0,
        "is_main": is_main,
        "account_total_krw": bal["total"]  # 계좌 전체 합계 (KRQT소계 산출용)
    }


def handle_us_usaa_sub(cano: str, acnt: str, kwargs: dict) -> dict:
    """USAA 계좌의 USLA/HAA 분리 (외화RP 보정 적용)"""
    sub = kwargs["sub"]
    key = _cache_key("us_usaa", cano, acnt)
    if key in _account_cache:
        cached = _account_cache[key]
        usd_raw  = cached["usd_raw"]
        split    = cached["split"]
        rp_info  = cached["rp_info"]
    else:
        usd_raw = fetch_overseas_balance(cano, acnt, "840", "USD", "NASD", "AAPL")
        if "error" in usd_raw:
            _account_cache[key] = {"usd_raw": usd_raw, "split": {}, "rp_info": (False, "", 0)}
            return {"error": usd_raw["error"], "currency": "USD",
                     "total_krw": 0.0, "total_usd": 0.0, "stocks": []}
        usaa_tr = load_usaa_tr()
        usd_raw, rp_adj, rp_date, orig = apply_rp_adjustment(usd_raw, usaa_tr)
        split = split_usaa(usd_raw, usaa_tr)
        rp_info = (rp_adj, rp_date, orig)
        _account_cache[key] = {"usd_raw": usd_raw, "split": split, "rp_info": rp_info}

    if "error" in usd_raw:
        return {"error": usd_raw["error"], "currency": "USD",
                 "total_krw": 0.0, "total_usd": 0.0, "stocks": []}

    exrt = usd_raw.get("exchange_rate", 0)
    sub_data = split.get(sub, {})
    total_usd = sub_data.get("total_usd", 0)
    total_krw = total_usd * exrt if exrt > 0 else 0

    return {
        "currency": "USD",
        "total_usd": total_usd,
        "stock_eval_usd": sub_data.get("stock_eval", 0),
        "cash_usd": sub_data.get("cash", 0),
        "total_krw": total_krw,
        "stocks": sub_data.get("stocks", []),
        "exchange_rate": exrt,
        "mode": split.get(f"{sub}_Mode", ""),
        "rp_adjusted": rp_info[0] if sub == "USLA" else False,
        "rp_prev_date": rp_info[1] if sub == "USLA" else "",
        "usd_raw": usd_raw if sub == "USLA" else {}  # USLA 측에만 raw 보관
    }


def handle_us_usqt_cat(cano: str, acnt: str, kwargs: dict) -> dict:
    """USQT 계좌의 카테고리별 분리 (SCG/TCM)"""
    category = kwargs["category"]
    key = _cache_key("us_usqt", cano, acnt)
    if key in _account_cache:
        bal = _account_cache[key]
    else:
        bal = fetch_overseas_balance(cano, acnt, "840", "USD", "NASD", "AAPL")
        _account_cache[key] = bal
    if "error" in bal:
        return {"error": bal["error"], "currency": "USD",
                 "total_krw": 0.0, "total_usd": 0.0, "stocks": []}

    csv_path = "/var/autobot/TR_USQT/USQT_stock.csv"
    cat_map = load_category_map(csv_path, us=True)
    cat_filtered = filter_by_category(bal, cat_map, category)

    is_main = (category == "SCG")
    cash = bal["cash"] if is_main else 0.0
    total_usd = cat_filtered["stock_eval"] + cash
    exrt = bal.get("exchange_rate", 0)

    return {
        "currency": "USD",
        "total_usd": total_usd,
        "stock_eval_usd": cat_filtered["stock_eval"],
        "cash_usd": cash,
        "total_krw": total_usd * exrt if exrt > 0 else 0,
        "stocks": cat_filtered["stocks"],
        "exchange_rate": exrt,
        "is_main": is_main,
        "account_total_usd": bal.get("total", 0)
    }


def handle_overseas_all(cano: str, acnt: str, kwargs: dict) -> dict:
    """해외주식 계좌 전체 (JP/HK/ETC)"""
    natn_cd = kwargs["natn_cd"]
    currency = kwargs["currency"]
    excg = kwargs["excg"]
    repr_cd = kwargs["repr_cd"]
    price = kwargs.get("price", "1000" if currency == "JPY" else "100")

    key = _cache_key("overseas", cano, acnt, currency)
    if key in _account_cache:
        bal = _account_cache[key]
    else:
        bal = fetch_overseas_balance(cano, acnt, natn_cd, currency, excg, repr_cd, price)
        _account_cache[key] = bal
    if "error" in bal:
        return {"error": bal["error"], "currency": currency,
                 "total_krw": 0.0, f"total_{currency.lower()}": 0.0, "stocks": []}

    exrt = bal.get("exchange_rate", 0)
    total_native = bal.get("total", 0)

    return {
        "currency": currency,
        f"total_{currency.lower()}": total_native,
        f"stock_eval_{currency.lower()}": bal.get("stock_eval", 0),
        f"cash_{currency.lower()}": bal.get("cash", 0),
        "total_krw": total_native * exrt if exrt > 0 else 0,
        "stocks": bal.get("stocks", []),
        "exchange_rate": exrt
    }


def handle_upbit(cano: str, acnt: str, kwargs: dict) -> dict:
    """Upbit 전체 잔고"""
    bal = fetch_upbit_balance()
    if "error" in bal:
        return {"error": bal["error"], "currency": "KRW",
                 "total_krw": 0.0, "stock_eval_krw": 0.0, "cash_krw": 0.0, "stocks": []}
    return {
        "currency": "KRW",
        "total_krw": bal["total"],
        "stock_eval_krw": bal["stock_eval"],
        "cash_krw": bal["cash"],
        "stocks": bal["stocks"],
        "exchange_rate": 1.0
    }


def handle_krft(cano: str, acnt: str, kwargs: dict) -> dict:
    """국내선물옵션 계좌 잔고 (CTFO6118R, KRW)"""
    key = _cache_key("krft", cano, acnt)
    if key in _account_cache:
        bal = _account_cache[key]
    else:
        bal = fetch_krft_balance(cano, acnt)
        _account_cache[key] = bal
    if "error" in bal:
        return {"error": bal["error"], "currency": "KRW",
                 "total_krw": 0.0, "stock_eval_krw": 0.0, "cash_krw": 0.0, "stocks": []}
    return {
        "currency": "KRW",
        "total_krw": bal["total"],
        "stock_eval_krw": bal["stock_eval"],
        "cash_krw": bal["cash"],
        "stocks": bal["stocks"],
        "exchange_rate": 1.0
    }


def handle_gbft(cano: str, acnt: str, kwargs: dict) -> dict:
    """해외선물옵션 계좌 잔고 (OTFR2102R, USD)"""
    currency = kwargs.get("currency", "USD")
    key = _cache_key("gbft", cano, acnt, currency)
    if key in _account_cache:
        bal = _account_cache[key]
    else:
        bal = fetch_gbft_balance(cano, acnt, currency)
        _account_cache[key] = bal
    if "error" in bal:
        return {"error": bal["error"], "currency": currency,
                 "total_krw": 0.0, f"total_{currency.lower()}": 0.0, "stocks": []}
    exrt = bal.get("exchange_rate", 0)
    total_native = bal.get("total", 0)
    return {
        "currency": currency,
        f"total_{currency.lower()}": total_native,
        f"stock_eval_{currency.lower()}": bal.get("stock_eval", 0),
        f"cash_{currency.lower()}": bal.get("cash", 0),
        "total_krw": total_native * exrt if exrt > 0 else 0,
        "stocks": bal.get("stocks", []),
        "exchange_rate": exrt
    }


def handle_placeholder(cano: str, acnt: str, kwargs: dict) -> dict:
    """미연결 계좌: 0원 반환"""
    cur = kwargs.get("currency", "KRW")
    return {
        "currency": cur,
        "total_krw": 0.0,
        "stock_eval_krw": 0.0,
        "cash_krw": 0.0,
        "stocks": [],
        "exchange_rate": 1.0,
        "placeholder": True
    }


HANDLERS = {
    "kr_simple":     handle_kr_simple,
    "kr_krqt_cat":   handle_kr_krqt_cat,
    "us_usaa_sub":   handle_us_usaa_sub,
    "us_usqt_cat":   handle_us_usqt_cat,
    "overseas_all":  handle_overseas_all,
    "upbit":         handle_upbit,
    "krft":          handle_krft,
    "gbft":          handle_gbft,
    "placeholder":   handle_placeholder,
}


# ══════════════════════════════════════════════════
#  메인 수집 루프
# ══════════════════════════════════════════════════

def collect_accounts(mode: str) -> list:
    """
    ACCOUNTS 리스트를 순회하며 각 항목의 잔고를 수집.
    mode = "US": US_MODE_KEYS(USAA/USQT/Crypto)만
    mode = "ASIA": 전체
    """
    prev = get_prev_snapshot()
    items = []

    for (market, strategy, sub, cano, acnt, handler_name, kwargs) in ACCOUNTS:
        if mode == "US" and strategy not in US_MODE_KEYS:
            continue

        handler = HANDLERS.get(handler_name, handle_placeholder)
        try:
            data = handler(cano, acnt, kwargs)
        except Exception as e:
            data = {"error": f"{handler_name} 예외: {e}", "currency": "KRW",
                     "total_krw": 0.0, "stocks": []}

        # 전일 대비 변동율
        prev_entry = find_prev_entry(prev, market, strategy, sub)
        prev_total_krw = prev_entry.get("total_krw", 0)
        day_change_krw = calc_day_change(data.get("total_krw", 0), prev_total_krw)

        # 종목별 전일 대비 (평가금 기준)
        for s in data.get("stocks", []):
            prev_s = find_prev_stock(prev_entry, s["code"])
            s["day_change_rate"] = calc_day_change(
                s.get("eval_amt", 0),
                prev_s.get("eval_amt", 0)
            )

        # 통화별 전일 대비 (USAA/USQT/JPQT/HKQT/ETC)
        day_change_native = 0.0
        if data.get("currency") != "KRW":
            cur_l = data["currency"].lower()
            prev_native = prev_entry.get(f"total_{cur_l}",
                            prev_entry.get("total_usd", 0))
            curr_native = data.get(f"total_{cur_l}",
                            data.get("total_usd", 0))
            day_change_native = calc_day_change(curr_native, prev_native)

        items.append({
            "market": market,
            "strategy": strategy,
            "sub": sub,
            "cano": cano,
            "acnt_prdt_cd": acnt,
            "currency": data.get("currency", "KRW"),
            "total_krw": data.get("total_krw", 0),
            "day_change_krw_rate": day_change_krw,
            "day_change_native_rate": day_change_native,
            "exchange_rate": data.get("exchange_rate", 0),
            "placeholder": data.get("placeholder", False),
            "error": data.get("error", ""),
            "stocks": data.get("stocks", []),
            # 세부 (통화별)
            **{k: v for k, v in data.items() if k.startswith(("total_", "stock_eval_", "cash_"))},
            # USAA 고유
            "mode": data.get("mode", ""),
            "rp_adjusted": data.get("rp_adjusted", False),
            "rp_prev_date": data.get("rp_prev_date", ""),
            "usd_raw": data.get("usd_raw", {}),
            "is_main": data.get("is_main", True),
            "account_total_krw": data.get("account_total_krw", 0),
            "account_total_usd": data.get("account_total_usd", 0)
        })

    return items


# ══════════════════════════════════════════════════
#  JSON 저장
# ══════════════════════════════════════════════════

def save_snapshot(mode: str, items: list) -> str:
    """balance_YYYYMMDD.json 에 mode별로 저장 (병합)"""
    date_str = datetime.now().strftime("%Y%m%d")
    fp = os.path.join(SNAPSHOT_DIR, f"balance_{date_str}.json")

    existing = {}
    if os.path.exists(fp):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = {}

    # 카테고리(strategy)별 그룹화
    cats = OrderedDict()
    for it in items:
        k = it["strategy"]
        if k not in cats:
            cats[k] = {"items": []}
        cats[k]["items"].append(it)

    existing["date"] = datetime.now().strftime("%Y-%m-%d")
    existing[mode] = {
        "timestamp": datetime.now().isoformat(),
        "categories": cats
    }

    with open(fp, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2, default=str)
    return fp


# ══════════════════════════════════════════════════
#  Telegram 포맷 (CSV 순서대로)
# ══════════════════════════════════════════════════

def fmt_pct(v: float) -> str:
    return f"{v:+.2f}%"

def fmt_krw(v: float) -> str:
    return f"₩{v:,.0f}"

def fmt_usd(v: float) -> str:
    return f"${v:,.2f}"

def fmt_jpy(v: float) -> str:
    return f"¥{v:,.0f}"

def fmt_hkd(v: float) -> str:
    return f"HK${v:,.0f}"


def _currency_symbol(cur: str) -> str:
    return {"KRW": "₩", "USD": "$", "JPY": "¥", "HKD": "HK$"}.get(cur, "")


def format_report(mode: str, items: list, prev: dict) -> list:
    """
    텔레그램 메시지 생성 (CSV 순서대로)
    mode별로 분할: 헤더 → 총자산 → 시장별 그룹 → 소계 → 전략별 종목 상세
    """
    msg = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    msg.append(f"📊 일별잔고 스냅샷 [{mode}] {now}")

    # ── 총자산 ──
    grand_total = sum(it.get("total_krw", 0) for it in items)
    prev_grand = 0
    for m in ("ASIA", "US"):
        for cat in prev.get(m, {}).get("categories", {}).values():
            for it in cat.get("items", []):
                prev_grand += it.get("total_krw", 0)
    grand_chg = calc_day_change(grand_total, prev_grand)

    if mode == "ASIA":
        msg.append(f"💰 총자산 합계: {fmt_krw(grand_total)} ({fmt_pct(grand_chg)})")
    else:
        msg.append(f"💰 [US조회] 해당분 합계: {fmt_krw(grand_total)} ({fmt_pct(grand_chg)})")

    # ── 시장 그룹별 출력 ──
    markets = OrderedDict()
    for it in items:
        markets.setdefault(it["market"], []).append(it)

    for market, mkt_items in markets.items():
        msg.append("")
        msg.append(f"━━━ {market} ━━━")

        # 전략별 그룹화
        strat_groups = OrderedDict()
        for it in mkt_items:
            strat_groups.setdefault(it["strategy"], []).append(it)

        market_sum_krw = 0.0

        for strategy, sitems in strat_groups.items():
            msg.append("")
            msg.append(f"【{strategy}】")

            # USAA/USQT: 메인(is_main=True) 항목에만 MODE / 통화소계 표기
            is_usaa = (strategy == "USAA")
            is_usqt = (strategy == "USQT")
            is_jp_hk = strategy in ("JPQT", "HKQT", "ETC")
            is_gbft = (strategy == "GBFT")

            strat_sum_krw = 0.0
            strat_sum_native = 0.0
            native_cur = sitems[0].get("currency", "KRW")

            # USAA 전략 상단: 외화RP 보정 여부 먼저 고지 (눈에 띄게)
            if is_usaa:
                for it in sitems:
                    if it.get("rp_adjusted"):
                        urw = it.get("usd_raw", {})
                        orig = 0.0
                        prev = 0.0
                        if isinstance(urw, dict):
                            # cash_adjusted = 승계값, 원래 API cash는 덮어써졌음 → 0 근사
                            prev = float(urw.get("cash_adjusted", 0) or 0)
                        prev_date = it.get("rp_prev_date", "")
                        msg.append(f"  💱 외화RP 보정: API현금≈$0 → 전일값 {fmt_usd(prev)} ({prev_date})")
                        break

            for it in sitems:
                sub = it["sub"]
                total_krw = it.get("total_krw", 0)
                chg_krw = it.get("day_change_krw_rate", 0)
                cur = it.get("currency", "KRW")
                err = it.get("error", "")
                placeholder = it.get("placeholder", False)

                if placeholder:
                    msg.append(f"  · {sub}: [미연결] {fmt_krw(0)}")
                    continue
                if err:
                    msg.append(f"  · {sub}: ❌ {err}")
                    continue

                strat_sum_krw += total_krw

                # 통화별 금액
                if cur == "USD":
                    native = it.get("total_usd", 0)
                    strat_sum_native += native
                    native_str = f"{fmt_usd(native)} ({fmt_pct(it.get('day_change_native_rate',0))})"
                elif cur == "JPY":
                    native = it.get("total_jpy", 0)
                    strat_sum_native += native
                    native_str = f"{fmt_jpy(native)} ({fmt_pct(it.get('day_change_native_rate',0))})"
                elif cur == "HKD":
                    native = it.get("total_hkd", 0)
                    strat_sum_native += native
                    native_str = f"{fmt_hkd(native)} ({fmt_pct(it.get('day_change_native_rate',0))})"
                else:
                    native_str = ""

                # 기본 라인: 전략 sub + 원화 평가금 + 변동
                krw_str = f"{fmt_krw(total_krw)} ({fmt_pct(chg_krw)})"
                line = f"  · {sub}: {krw_str}"
                if native_str:
                    line += f"  /  {native_str}"

                # USAA MODE 표시
                if is_usaa:
                    mode_str = it.get("mode", "")
                    if mode_str:
                        line += f"  [{mode_str}]"
                    if it.get("rp_adjusted"):
                        line += f"  💱RP({it.get('rp_prev_date','')})"

                msg.append(line)

            # 소계 (KRQT/USQT/USAA/GBFT/JPQT/HKQT/ETC)
            if strategy in ("KRTR", "KRQT"):
                msg.append(f"  → {strategy}소계: {fmt_krw(strat_sum_krw)}")
            elif strategy == "USAA":
                msg.append(f"  → USAA소계: {fmt_krw(strat_sum_krw)} / {fmt_usd(strat_sum_native)}")
            elif strategy == "USQT":
                msg.append(f"  → USQT소계: {fmt_krw(strat_sum_krw)} / {fmt_usd(strat_sum_native)}")
            elif strategy == "GBFT":
                msg.append(f"  → GBFT소계: {fmt_krw(strat_sum_krw)} / {fmt_usd(strat_sum_native)}")

            market_sum_krw += strat_sum_krw

        # 시장 소계 (ASIA 모드에서만 의미 있음)
        msg.append("")
        msg.append(f"▶ {market} 소계: {fmt_krw(market_sum_krw)}")

    return msg


def format_holdings_detail(items: list) -> list:
    """전략별 종목 상세 (두 번째 메시지로 분리)"""
    msg = []
    msg.append("📋 보유종목 상세")

    groups = OrderedDict()
    for it in items:
        if not it.get("stocks"):
            continue
        key = f"{it['strategy']} / {it['sub']}"
        groups.setdefault(key, []).append(it)

    for key, gitems in groups.items():
        for it in gitems:
            stocks = it.get("stocks", [])
            if not stocks:
                continue
            cur = it.get("currency", "KRW")
            msg.append("")
            msg.append(f"─ {key} ({cur}) ─")
            sym = _currency_symbol(cur)
            for s in stocks:
                code = s.get("code", "")
                name = s.get("name", "") or code
                qty = s.get("qty", 0)
                evl = s.get("eval_amt", 0)
                chg = s.get("day_change_rate", 0)
                if cur == "KRW":
                    qty_str = f"{int(qty)}주"
                    evl_str = f"{sym}{evl:,.0f}"
                elif cur == "USD":
                    qty_str = f"{qty:g}주"
                    evl_str = f"{sym}{evl:,.2f}"
                else:
                    qty_str = f"{qty:g}주"
                    evl_str = f"{sym}{evl:,.0f}"
                msg.append(f"  {code} {name}: {qty_str} / {evl_str} ({fmt_pct(chg)})")

    return msg


# ══════════════════════════════════════════════════
#  메인
# ══════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 daily_snapshot.py [US|ASIA]")
        sys.exit(1)

    mode = sys.argv[1].upper()
    if mode not in ("US", "ASIA"):
        print(f"Unknown mode: {mode}")
        sys.exit(1)

    prev = get_prev_snapshot()

    # 1. 계좌별 수집
    items = collect_accounts(mode)

    # 2. JSON 저장 (최우선)
    try:
        path = save_snapshot(mode, items)
    except Exception as e:
        TA.send_tele(f"❌ JSON 저장 실패: {e}")
        path = ""

    # 3. 텔레그램 메시지 생성
    summary_msg  = format_report(mode, items, prev)
    holdings_msg = format_holdings_detail(items)

    if path:
        summary_msg.append(f"\n✅ JSON: {path}")

    # 4. 메시지 분할 전송 (요약 → 종목상세)
    TA.send_tele(summary_msg)
    if holdings_msg and len(holdings_msg) > 1:
        time.sleep(1.2)
        TA.send_tele(holdings_msg)


if __name__ == "__main__":
    main()
