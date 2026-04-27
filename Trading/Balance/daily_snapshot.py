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

# 수동 입력 잔고 (IRP 예수금 등 KIS API 조회 불가한 값)
# 없으면 자동 생성, 사용자가 직접 수정 가능
MANUAL_BALANCE_PATH = os.path.join(SNAPSHOT_DIR, "manual_balance.json")

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

    # GBFT: 해외선물옵션 (acnt_prdt_cd=08) — OTFM3118R + OTFM3114R 사용
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

# ── 수동 입력 잔고 (IRP 예수금 등) ────────────────────
# IRP는 KIS API로 예수금(RP 운용자산) 조회 불가 → 사용자가 MTS 보고 직접 입력
# 파일이 없으면 최초 1회 자동 생성, 이후 수동 수정
_MANUAL_DEFAULTS = {
    "43685950_29_IRP_cash": {
        "value": 94976,
        "updated": "2026-04-18",
        "note": "MTS IRP 자산 - 주식평가금액 = 예수금(RP 운용). MTS에서 확인 후 수동 수정"
    }
}

_manual_cache = None

def get_manual_balance(key: str) -> tuple:
    """
    manual_balance.json 에서 수동 입력된 잔고값을 가져옴.
    파일이 없으면 _MANUAL_DEFAULTS 로 최초 생성.
    Returns: (value, updated_date)
    """
    global _manual_cache
    if _manual_cache is None:
        if not os.path.exists(MANUAL_BALANCE_PATH):
            try:
                with open(MANUAL_BALANCE_PATH, "w", encoding="utf-8") as f:
                    json.dump(_MANUAL_DEFAULTS, f, ensure_ascii=False, indent=2)
                _manual_cache = dict(_MANUAL_DEFAULTS)
            except Exception:
                _manual_cache = {}
        else:
            try:
                with open(MANUAL_BALANCE_PATH, encoding="utf-8") as f:
                    _manual_cache = json.load(f)
            except Exception:
                _manual_cache = {}
    entry = _manual_cache.get(key, {})
    if isinstance(entry, dict):
        return (float(entry.get("value", 0) or 0),
                entry.get("updated", ""))
    return (float(entry or 0), "")


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
    한국주식/연금/IRP 계좌 잔고 조회 (페이지네이션 포함)

    계좌 타입별 output2 필드 사용 전략:
    - 위탁계좌  (01):  nass_amt = 순자산(주식+현금) → 신뢰 가능
    - 연금저축  (22):  tot_evlu_amt, dnca_tot_amt, prvs_rcdl_excc_amt 복합
    - IRP       (29):  tot_evlu_amt가 0인 경우 많음 →
                       dnca_tot_amt, prvs_rcdl_excc_amt, nxdy_excc_amt 중 max
                       + TTTC8908R로 nrcvb_buy_amt(미수없는매수금액) 크로스체크

    IRP 예수금 관련 필드:
      - dnca_tot_amt        : 예수금 총액
      - prvs_rcdl_excc_amt  : 가수도정산금액 (D+2 이후 결제완료 예상)
      - nxdy_excc_amt       : 익일정산금액 (D+1 결제)

    Returns:
      {"stocks": [...], "stock_eval": float, "cash": float, "total": float}
    """
    is_pension = acnt_prdt_cd in ("22", "29")

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
    # 연금/IRP 후보 필드 (마지막 페이지 값)
    dnca_tot_amt       = 0.0
    prvs_rcdl_excc_amt = 0.0
    nxdy_excc_amt      = 0.0
    tot_evlu_amt       = 0.0
    nass_amt_last      = 0.0
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
            d2 = out2[0] if out2 else {}

            if is_pension:
                v = float(d2.get("tot_evlu_amt", 0) or 0)
                if v > 0:
                    tot_evlu_amt = v
                v = float(d2.get("dnca_tot_amt", 0) or 0)
                if v > 0:
                    dnca_tot_amt = v
                v = float(d2.get("prvs_rcdl_excc_amt", 0) or 0)
                if v > 0:
                    prvs_rcdl_excc_amt = v
                v = float(d2.get("nxdy_excc_amt", 0) or 0)
                if v > 0:
                    nxdy_excc_amt = v
            else:
                v = float(d2.get("nass_amt", 0) or 0)
                if v > 0:
                    nass_amt_last = v

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

    if is_pension:
        # ── 1차 추정: 3개 예수금 후보 중 최대값 ──
        cash_candidates = [dnca_tot_amt, prvs_rcdl_excc_amt, nxdy_excc_amt]
        cash = max(cash_candidates) if any(c > 0 for c in cash_candidates) else 0.0

        # ── 2차 보강: TTTC8908R (매수가능조회) ──
        # 연금저축(22) 동작, IRP(29)는 빈 {} 반환 (KIS 미지원)
        try:
            time.sleep(API_SLEEP)
            url2 = f"{BASE_URL}/uapi/domestic-stock/v1/trading/inquire-psbl-order"
            h2 = kis_headers(cano, "TTTC8908R")
            params2 = {
                "CANO": cano, "ACNT_PRDT_CD": acnt_prdt_cd,
                "PDNO": "005930",           # 더미 (결과에 영향 없음)
                "ORD_UNPR": "70000",
                "ORD_DVSN": "01",
                "CMA_EVLU_AMT_ICLD_YN": "Y",
                "OVRS_ICLD_YN": "N"
            }
            r2 = requests.get(url2, headers=h2, params=params2, timeout=10)
            r2.raise_for_status()
            d2b = r2.json()
            if d2b.get("rt_cd") == "0":
                out = d2b.get("output", {}) or {}
                nrcvb = float(out.get("nrcvb_buy_amt", 0) or 0)
                if nrcvb > cash:
                    cash = nrcvb
        except Exception:
            pass

        # ── 3차: IRP(29) 전용 — KIS API 조회 불가, manual_balance.json 사용 ──
        # IRP의 예수금(RP 운용자산)은 증권 API에서 조회되지 않음.
        # manual_balance.json 에서 사용자가 MTS 보고 직접 입력한 값 사용.
        manual_note = ""
        manual_cash = 0.0
        if acnt_prdt_cd == "29":
            mv, md = get_manual_balance(f"{cano}_{acnt_prdt_cd}_IRP_cash")
            if mv > 0:
                manual_cash = mv
                manual_note = f"수동입력 예수금 ({md})"
                # API cash 가 0이면 수동값 사용, API에 값이 있으면 둘 중 큰 쪽
                if manual_cash > cash:
                    cash = manual_cash

        # ── 총자산 = 주식평가금 + 현금 (IRP는 수동 예수금 포함) ──
        # IRP(29): tot_evlu_amt = 주식평가액만 이므로, 수동 예수금 반드시 합산
        if acnt_prdt_cd == "29" and manual_cash > 0:
            total = stock_eval + cash
        else:
            # 연금저축(22): 기존 로직 유지
            total = max(stock_eval + cash, tot_evlu_amt)
            if cash <= 0 and tot_evlu_amt > stock_eval:
                cash = tot_evlu_amt - stock_eval

        return {
            "stocks": stocks,
            "stock_eval": stock_eval,
            "cash": cash,
            "total": total,
            "note": manual_note
        }

    else:
        # 위탁계좌
        total = nass_amt_last
        cash = total - stock_eval if total > 0 else 0.0

    return {"stocks": stocks, "stock_eval": stock_eval, "cash": cash, "total": total}


# ══════════════════════════════════════════════════
#  국내선물옵션 잔고 조회 (CTFO6118R)
# ══════════════════════════════════════════════════

def fetch_krft_balance(cano: str, acnt_prdt_cd: str) -> dict:
    """
    국내선물옵션 계좌 잔고 조회 (acnt_prdt_cd="03")
    TR_ID: CTFO6118R (실전투자 전용 / VTFO6118R = 모의)
    URL  : /uapi/domestic-futureoption/v1/trading/inquire-balance

    [KIS 공식 GitHub(koreainvestment/open-trading-api) 검증된 사양]
      필수 파라미터 (정확):
        CANO          : 종합계좌번호
        ACNT_PRDT_CD  : 계좌상품코드 (03)
        MGNA_DVSN     : 증거금 구분 ("01"=개시, "02"=유지)
        EXCC_STAT_CD  : 정산상태코드 ("1"=정산, "2"=본정산)  ※ 1자리!
        CTX_AREA_FK200, CTX_AREA_NK200 : 연속조회

      ※ 기존 코드의 STTL_STTS_CD / EXCC_UNPR_DVSN 은 모두 잘못된 필드명
        → "정산상태코드은(는) 필수입력 항목입니다" 에러 원인

    [응답 필드 - 실 API 검증된 키]
      output1 (포지션 리스트):
        pdno/shtn_pdno    : 종목코드
        prdt_name         : 종목명
        cblc_qty          : 잔고수량
        sll_buy_dvsn_cd   : 01=매도, 02=매수
        pchs_avg_pric     : 평균매입단가
        idx_clpr          : 지수종가(현재가)
        evlu_amt          : 평가금액
        evlu_pfls_amt     : 평가손익
        evlu_pfls_rt      : 평가손익률
      output2 (계좌요약, 단일객체):
        dnca_cash         : 예수금(현금)              ← 실제 예수금
        dnca_sbst         : 예수금(대용)
        tot_dncl_amt      : 총예탁금액
        nxdy_dnca         : 익일예수금
        ord_psbl_cash     : 주문가능현금               ← 사용자 요구#6 'cash'
        ord_psbl_tota     : 주문가능총액
        wdrw_psbl_tot_amt : 인출가능총액
        prsm_dpast        : 추정예탁자산 (총평가)
        evlu_amt_smtl     : 평가금액합계
        evlu_pfls_amt_smtl: 평가손익합계
        futr_evlu_pfls_amt/opt_evlu_pfls_amt : 선/옵 평가손익

    Returns:
      {stocks, stock_eval, cash, total,
       deposit, ord_psbl_cash, today_deposit, wdrw_psbl,
       pos_pl, total_eval}
    """
    url = f"{BASE_URL}/uapi/domestic-futureoption/v1/trading/inquire-balance"
    params = {
        "CANO": cano,
        "ACNT_PRDT_CD": acnt_prdt_cd,
        "MGNA_DVSN":   "01",      # 01=개시증거금
        "EXCC_STAT_CD":"1",       # 1=정산 (필수, 1자리)
        "CTX_AREA_FK200": "",
        "CTX_AREA_NK200": "",
    }

    stocks = []
    out2_acc = {}
    tr_cont_req = ""
    page = 0

    try:
        while True:
            h = kis_headers(cano, "CTFO6118R")
            h["tr_cont"] = tr_cont_req
            time.sleep(API_SLEEP)
            r = requests.get(url, headers=h, params=params, timeout=10)
            if r.status_code != 200:
                return {"error": f"국내선물 HTTP {r.status_code}"}
            data = r.json()
            resp_tr_cont = (r.headers.get("tr_cont", "") or "").strip()

            if data.get("rt_cd") != "0":
                return {"error": f"{data.get('msg_cd','?')} {data.get('msg1','국내선물 API 오류')}"}

            # output1: 보유포지션
            for s in data.get("output1", []) or []:
                qty = float(s.get("cblc_qty", 0) or 0)
                if qty == 0:
                    continue
                evl = float(s.get("evlu_amt", 0) or 0)
                stocks.append({
                    "code": s.get("pdno", "") or s.get("shtn_pdno", ""),
                    "name": s.get("prdt_name", ""),
                    "qty":  qty,
                    "side": s.get("sll_buy_dvsn_cd", ""),
                    "eval_amt": evl,
                    "price": float(s.get("idx_clpr", 0) or 0),
                    "avg_price": float(s.get("pchs_avg_pric", 0) or 0),
                    "profit_rate": float(s.get("evlu_pfls_rt", 0) or 0),
                })

            # output2: 계좌요약 (페이지 진행되더라도 최종값으로 갱신)
            out2 = data.get("output2") or []
            d2 = out2[0] if isinstance(out2, list) and out2 else (out2 if isinstance(out2, dict) else {})
            if d2:
                out2_acc.update(d2)

            page += 1
            if page >= MAX_PAGE:
                break
            if resp_tr_cont in ("D", "E", "F", ""):
                break
            fk = (data.get("ctx_area_fk200") or "").strip()
            nk = (data.get("ctx_area_nk200") or "").strip()
            if not fk or not nk:
                break
            params["CTX_AREA_FK200"] = fk
            params["CTX_AREA_NK200"] = nk
            tr_cont_req = "N"

    except Exception as e:
        return {"error": f"국내선물 조회 예외: {e}"}

    # ── 검증된 응답 필드로 금액 추출 ──
    def _f(*keys):
        for k in keys:
            v = out2_acc.get(k)
            if v in (None, ""):
                continue
            try:
                fv = float(v)
                if fv != 0:
                    return fv
            except (TypeError, ValueError):
                continue
        return 0.0

    deposit       = _f("dnca_cash", "tot_dncl_amt")           # 예수금(현금)
    today_deposit = _f("nxdy_dnca", "nxdy_dncl_amt")           # 익일예수금
    total_eval    = _f("prsm_dpast", "prsm_dpast_amt")         # 추정예탁자산
    ord_psbl_cash = _f("ord_psbl_cash", "ord_psbl_tota")       # 주문가능현금
    wdrw_psbl     = _f("wdrw_psbl_tot_amt")                    # 인출가능총액
    pos_eval_acc  = _f("evlu_amt_smtl")                        # 평가금액합계
    pos_pl        = _f("evlu_pfls_amt_smtl",
                       "futr_evlu_pfls_amt", "opt_evlu_pfls_amt")
    deposit_sbst  = _f("dnca_sbst")

    stock_eval = sum(s["eval_amt"] for s in stocks) or pos_eval_acc

    # 사용자 요구사항 #6: '쉽게 쓰여있는 예수금'이 아니라 정확한 cash
    # → 미결제 포지션 없을 때는 deposit, 있을 때도 deposit이 가장 정확 (증거금 차감 전 보유현금)
    # 단, '주문가능현금'이 0이 아니면 그것이 실제 가용 자금 (사용자 의도 부합)
    cash = ord_psbl_cash if ord_psbl_cash > 0 else deposit

    # 총자산: 추정예탁자산 우선, 없으면 (예수금+대용+포지션평가)
    total = total_eval if total_eval > 0 else (deposit + deposit_sbst + stock_eval)

    return {
        "stocks":         stocks,
        "stock_eval":     stock_eval,
        "cash":           cash,
        "total":          total,
        # 추가 필드 (디버깅/세부 표시용)
        "deposit":        deposit,           # 예수금(현금)
        "deposit_sbst":   deposit_sbst,      # 예수금(대용)
        "today_deposit":  today_deposit,     # 익일예수금
        "ord_psbl_cash":  ord_psbl_cash,     # 주문가능현금
        "wdrw_psbl":      wdrw_psbl,         # 인출가능총액
        "total_eval":     total_eval,        # 추정예탁자산
        "pos_pl":         pos_pl,            # 평가손익합계
    }


# ══════════════════════════════════════════════════
#  해외선물옵션 잔고 조회 (OTFM1412R + OTFM1411R)
# ══════════════════════════════════════════════════

def fetch_gbft_balance(cano: str, acnt_prdt_cd: str, currency: str = "USD") -> dict:
    """
    해외선물옵션 계좌 잔고 조회 (acnt_prdt_cd="08")

    [KIS 공식 GitHub 검증된 정확한 사양]
      미결제잔고: OTFM1412R → /uapi/overseas-futureoption/v1/trading/inquire-unpd
        params: CANO, ACNT_PRDT_CD, FUOP_DVSN("00"=전체), CTX_AREA_FK100/NK100
      예수금:    OTFM1411R → /uapi/overseas-futureoption/v1/trading/inquire-deposit
        params: CANO, ACNT_PRDT_CD, CRCY_CD, INQR_DT (YYYYMMDD)

    [기존 코드 버그] (이전 버전)
      - OTFM3118R + inquire-unpd-brkg-prft-amt → 존재하지 않는 엔드포인트
      - OTFM3114R + inquire-deposit → TR_ID 잘못됨

    [응답 필드 - 실 API 검증]
      예수금(OTFM1411R) output - 모든 필드가 fm_ 접두사:
        fm_dnca_rmnd          : 예수금잔액            ← 실제 예수금
        fm_nxdy_dncl_amt      : 익일예수금잔액
        fm_drwg_psbl_amt      : 인출가능액
        fm_ord_psbl_amt       : 주문가능액            ← cash 후보
        fm_tot_asst_evlu_amt  : 총자산평가금액
        fm_fuop_evlu_pfls_amt : 선물옵션평가손익
        fm_brkg_mgn_amt       : 위탁증거금
        fm_risk_rt            : 위험도
        (환율 필드 없음 → TUS와 KRW 응답 비율로 역산)

    [통화별 조회 전략]
      - currency="USD" 기본 호출 → fm_dnca_rmnd가 실제 USD 예수금
      - 추가로 KRW 호출하여 원화 예수금도 합산 (사용자 환경: KRW 입금 가능)
      - 환율: TUS(총USD환산) ÷ KRW 응답값으로 역산

    Returns:
      {stocks, stock_eval, cash, total, exchange_rate,
       deposit_native, deposit_krw, ord_avail_native, krw_balance}
    """
    stocks = []
    stock_eval_native = 0.0
    svc_available = True

    # ── Step 1: 미결제잔고 (OTFM1412R / inquire-unpd) ──────────
    url1 = f"{BASE_URL}/uapi/overseas-futureoption/v1/trading/inquire-unpd"
    params1 = {
        "CANO": cano,
        "ACNT_PRDT_CD": acnt_prdt_cd,
        "FUOP_DVSN": "00",          # 00=전체, 01=선물, 02=옵션
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": "",
    }
    tr_cont_req = ""
    page = 0

    try:
        while True:
            h1 = kis_headers(cano, "OTFM1412R")
            h1["tr_cont"] = tr_cont_req
            time.sleep(API_SLEEP)
            r1 = requests.get(url1, headers=h1, params=params1, timeout=10)

            # 4xx/5xx → 서비스 비활성 가능성, placeholder 진행
            if r1.status_code >= 400:
                svc_available = False
                break

            d1 = r1.json()
            resp_tr_cont = (r1.headers.get("tr_cont", "") or "").strip()

            if d1.get("rt_cd") != "0":
                msg = d1.get("msg1", "")
                # 서비스 미활성 신호
                if "권한" in msg or "없는 서비스" in msg or "데이터" in msg:
                    svc_available = False
                # 그 외 오류는 미결제 0건으로 간주하고 예수금 단계로 진행
                break

            out = d1.get("output", []) or []
            if isinstance(out, dict):
                out = [out]
            for s in out:
                qty = float(s.get("cblc_qty", 0) or s.get("ccld_qty", 0) or 0)
                if qty == 0:
                    continue
                evl = float(s.get("frcr_evlu_amt", 0) or s.get("evlu_amt", 0) or 0)
                stock_eval_native += evl
                stocks.append({
                    "code":       s.get("ovrs_futr_fx_pdno", "") or s.get("pdno", ""),
                    "name":       s.get("prdt_name", ""),
                    "qty":        qty,
                    "side":       s.get("sll_buy_dvsn_cd", ""),
                    "eval_amt":   evl,
                    "price":      float(s.get("now_pric", 0) or s.get("idx_clpr", 0) or 0),
                    "avg_price":  float(s.get("pchs_avg_pric", 0) or 0),
                    "profit_rate":float(s.get("evlu_pfls_rt", 0) or 0),
                    "currency":   s.get("crcy_cd", currency),
                })

            page += 1
            if page >= MAX_PAGE:
                break
            if resp_tr_cont in ("D", "E", "F", ""):
                break
            fk = (d1.get("ctx_area_fk100") or "").strip()
            nk = (d1.get("ctx_area_nk100") or "").strip()
            if not fk or not nk:
                break
            params1["CTX_AREA_FK100"] = fk
            params1["CTX_AREA_NK100"] = nk
            tr_cont_req = "N"
    except Exception:
        svc_available = False

    # ── Step 2: 예수금 (OTFM1411R / inquire-deposit) ─────────
    inqr_dt = datetime.now().strftime("%Y%m%d")
    url2 = f"{BASE_URL}/uapi/overseas-futureoption/v1/trading/inquire-deposit"

    def _fetch_deposit(crcy_cd: str) -> dict:
        """단일 통화 예수금 조회. 응답의 0이 아닌 fm_* 값을 dict로 반환."""
        try:
            h2 = kis_headers(cano, "OTFM1411R")
            params2 = {
                "CANO": cano,
                "ACNT_PRDT_CD": acnt_prdt_cd,
                "CRCY_CD": crcy_cd,
                "INQR_DT": inqr_dt,
            }
            time.sleep(API_SLEEP)
            r = requests.get(url2, headers=h2, params=params2, timeout=10)
            if r.status_code >= 400:
                return {}
            d = r.json()
            if d.get("rt_cd") != "0":
                return {}
            o = d.get("output", {}) or {}
            if isinstance(o, list):
                o = o[0] if o else {}
            return o
        except Exception:
            return {}

    def _f(d: dict, *keys) -> float:
        for k in keys:
            v = d.get(k)
            if v in (None, ""):
                continue
            try:
                fv = float(v)
                if fv != 0:
                    return fv
            except (TypeError, ValueError):
                continue
        return 0.0

    # native(USD/EUR/HKD/...) + KRW + TUS(총USD환산) 모두 조회
    out_native = _fetch_deposit(currency)
    out_krw    = _fetch_deposit("KRW")
    out_tus    = _fetch_deposit("TUS")

    deposit_native    = _f(out_native, "fm_dnca_rmnd")        # USD 예수금
    ord_avail_native  = _f(out_native, "fm_ord_psbl_amt")     # USD 주문가능
    deposit_krw       = _f(out_krw,    "fm_dnca_rmnd")        # KRW 예수금
    ord_avail_krw     = _f(out_krw,    "fm_ord_psbl_amt")     # KRW 주문가능
    tot_asst_tus      = _f(out_tus,    "fm_tot_asst_evlu_amt")  # 총자산 USD환산
    tot_asst_krw      = _f(out_krw,    "fm_tot_asst_evlu_amt")  # 총자산 KRW
    fuop_pl_native    = _f(out_native, "fm_fuop_evlu_pfls_amt")

    # ── 환율 역산 ──
    # TUS 응답값(=USD환산 총자산)과 KRW 응답값의 비율 → KRW/USD 환율
    if tot_asst_tus > 0 and tot_asst_krw > 0:
        exrt = tot_asst_krw / tot_asst_tus
    elif tot_asst_tus > 0 and deposit_krw > 0:
        exrt = deposit_krw / tot_asst_tus
    else:
        exrt = 0.0

    # 응답이 하나라도 있으면 svc_available 복구 (Step1이 실패해도 예수금만 정상)
    if out_native or out_krw or out_tus:
        svc_available = True

    # ── 서비스 미활성 placeholder ──
    if not svc_available and stock_eval_native == 0:
        return {
            "stocks": [],
            "stock_eval": 0.0,
            "cash": 0.0,
            "total": 0.0,
            "exchange_rate": 0.0,
            "placeholder": True,
            "note": "해외선물옵션 계좌서비스 미활성"
        }

    # ── native 통화 기준 합계 (handle_gbft가 native 단위로 받아 환율로 KRW 변환) ──
    # 핵심 결정:
    #   • cash = 'USD 예수금 + (KRW 예수금 / 환율)' 으로 통합 USD화
    #     (KRW 입금분도 native 합계에 포함되도록)
    #   • 환율이 0이면 KRW 분은 별도로 보존 (handle_gbft에서 KRW 합산)
    if exrt > 0:
        cash_native_combined = deposit_native + (deposit_krw / exrt)
    else:
        cash_native_combined = deposit_native

    total_native = stock_eval_native + cash_native_combined

    return {
        "stocks":          stocks,
        "stock_eval":      stock_eval_native,    # native 평가금
        "cash":            cash_native_combined, # native 통합 cash
        "total":           total_native,
        "exchange_rate":   exrt,
        # 추가 진단 필드 (handle_gbft / 디버그용)
        "deposit_native":  deposit_native,
        "deposit_krw":     deposit_krw,
        "ord_avail_native":ord_avail_native,
        "ord_avail_krw":   ord_avail_krw,
        "tot_asst_tus":    tot_asst_tus,         # USD환산 총자산
        "tot_asst_krw":    tot_asst_krw,         # KRW 총자산
        "fuop_pl_native":  fuop_pl_native,
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
#  KRQT 전용: result.json / rebal.json 기반 분류
# ══════════════════════════════════════════════════

KRQT_RESULT_PATH = "/var/autobot/TR_KRQT/KRQT_result.json"
KRQT_REBAL_PATH  = "/var/autobot/TR_KRQT/KRQT_rebal.json"


def load_krqt_result() -> dict:
    """
    KRQT_result.json 로드.
    구조: {category: [{code, name, qty(분할), balance(분할), weight, status}, ...], ...}
    qty/balance는 KRQT_TR.py에서 split_weight로 이미 분할되어 저장됨.
    """
    if not os.path.exists(KRQT_RESULT_PATH):
        return {}
    try:
        with open(KRQT_RESULT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def load_krqt_rebal() -> dict:
    """
    KRQT_rebal.json 로드 (리밸런싱 시점 카테고리별 자산금).
    구조: {date, total_stocks, total_cash, total_asset, "Small Cap Growth": 금액, ...}
    """
    if not os.path.exists(KRQT_REBAL_PATH):
        return {}
    try:
        with open(KRQT_REBAL_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def split_krqt_by_result(balance: dict, krqt_result: dict, target_cat: str) -> dict:
    """
    실시간 잔고(balance)와 KRQT_result.json을 매칭해 target_cat에 속한 종목만 추출.
    중복종목은 result.json에 저장된 split 비율 (cat_qty / total_qty_across_cats) 로
    실잔고의 평가금/수량을 재분할한다.

    Returns: {"stocks": [...], "stock_eval": float}
    """
    # 1. result.json에서 카테고리별 split된 qty 맵 만들기
    cat_split = {}        # {(code, cat): split_qty}
    total_split = {}      # {code: 모든 cat 합산 split_qty}
    for cat, stocks in krqt_result.items():
        if cat == "remain_last":     # 리밸런싱 매도실패분 제외
            continue
        for s in stocks:
            code = str(s.get("code", "")).zfill(6)
            q = float(s.get("qty", 0) or 0)
            cat_split[(code, cat)] = cat_split.get((code, cat), 0.0) + q
            total_split[code] = total_split.get(code, 0.0) + q

    filtered = []
    stock_eval_sum = 0.0
    for s in balance.get("stocks", []):
        code = str(s.get("code", "")).zfill(6)
        cat_q = cat_split.get((code, target_cat), 0.0)
        if cat_q <= 0:
            continue
        total_q = total_split.get(code, 0.0)
        ratio = cat_q / total_q if total_q > 0 else 1.0

        # 실잔고에 비율 적용 (보유수량/평가금 분할)
        real_qty  = float(s.get("qty", 0) or 0)
        real_eval = float(s.get("eval_amt", 0) or 0)
        split_qty  = real_qty * ratio
        split_eval = real_eval * ratio

        ns = dict(s)              # 원본 보존을 위해 복사
        ns["qty"]      = split_qty
        ns["eval_amt"] = split_eval
        ns["_split_ratio"] = ratio   # 디버그용 (안정화 후 제거 가능)
        filtered.append(ns)
        stock_eval_sum += split_eval

    return {"stocks": filtered, "stock_eval": stock_eval_sum}


# ══════════════════════════════════════════════════
#  USQT 전용: result.json / rebal.json 기반 분류
# ══════════════════════════════════════════════════

USQT_RESULT_PATH = "/var/autobot/TR_USQT/USQT_result.json"
USQT_REBAL_PATH  = "/var/autobot/TR_USQT/USQT_rebal.json"


def load_usqt_result() -> dict:
    """
    USQT_result.json 로드.
    구조: {category: [{code(ticker), name, qty(분할), balance(분할), weight, status}, ...], ...}
    qty/balance는 USQT_TR.py에서 split_weight로 이미 분할되어 저장됨.
    """
    if not os.path.exists(USQT_RESULT_PATH):
        return {}
    try:
        with open(USQT_RESULT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def load_usqt_rebal() -> dict:
    """
    USQT_rebal.json 로드 (리밸런싱 시점 카테고리별 USD 자산금).
    구조: {date, total_stocks, total_cash, total_asset, currency:"USD",
           "SCG": USD금액, "TCM": USD금액, ...}
    """
    if not os.path.exists(USQT_REBAL_PATH):
        return {}
    try:
        with open(USQT_REBAL_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def split_usqt_by_result(balance: dict, usqt_result: dict, target_cat: str) -> dict:
    """
    실시간 USD 잔고(balance)와 USQT_result.json을 매칭해 target_cat 종목만 추출.
    중복종목은 result.json의 split qty 비율로 재분할한다.
    미국 티커는 zfill 처리 없이 그대로 매칭 (대문자 통일).

    Returns: {"stocks": [...], "stock_eval": float}  (USD 단위)
    """
    cat_split = {}
    total_split = {}
    for cat, stocks in usqt_result.items():
        if cat == "remain_last":
            continue
        for s in stocks:
            code = str(s.get("code", "")).strip().upper()
            q = float(s.get("qty", 0) or 0)
            cat_split[(code, cat)] = cat_split.get((code, cat), 0.0) + q
            total_split[code] = total_split.get(code, 0.0) + q

    filtered = []
    stock_eval_sum = 0.0
    for s in balance.get("stocks", []):
        code = str(s.get("code", "")).strip().upper()
        cat_q = cat_split.get((code, target_cat), 0.0)
        if cat_q <= 0:
            continue
        total_q = total_split.get(code, 0.0)
        ratio = cat_q / total_q if total_q > 0 else 1.0

        real_qty  = float(s.get("qty", 0) or 0)
        real_eval = float(s.get("eval_amt", 0) or 0)
        split_qty  = real_qty * ratio
        split_eval = real_eval * ratio

        ns = dict(s)
        ns["qty"]      = split_qty
        ns["eval_amt"] = split_eval
        ns["_split_ratio"] = ratio
        filtered.append(ns)
        stock_eval_sum += split_eval

    return {"stocks": filtered, "stock_eval": stock_eval_sum}


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
    """
    KRQT 계좌 (단일) 의 카테고리별 분리.

    분류 기준: /var/autobot/TR_KRQT/KRQT_result.json
      - 한 종목이 복수 카테고리에 속할 경우 result.json의 split된 qty 비율로
        실잔고의 평가금/수량을 재분할 (이전 csv 1:1 매핑 방식의 중복 누락 버그 해결)
      - 현금은 매핑된 종목의 split 후 평가금 합 기준으로 카테고리별 비례 배분

    수익률(rebal_ret):
      - KRQT_rebal.json의 리밸런싱 시점 카테고리 자산금 대비 현재 (total = 평가금+현금) 수익률 (%)
    """
    category = kwargs["category"]
    key = _cache_key("kr", cano, acnt)
    if key in _account_cache:
        bal = _account_cache[key]
    else:
        bal = fetch_kr_balance(cano, acnt)
        _account_cache[key] = bal
    if "error" in bal:
        return {"error": bal["error"], "currency": "KRW",
                 "total_krw": 0.0, "stock_eval_krw": 0.0,
                 "cash_krw": 0.0, "stocks": []}

    krqt_result = load_krqt_result()
    cat_filtered = split_krqt_by_result(bal, krqt_result, category)

    # ── 계좌 전체 주식평가금(result.json에 매핑된 종목 한정) ──
    cat_keys = [c for c in krqt_result.keys() if c != "remain_last"]
    mapped_codes = set()
    for c in cat_keys:
        for x in krqt_result.get(c, []):
            mapped_codes.add(str(x.get("code", "")).zfill(6))

    account_stock_total = 0.0
    for s in bal.get("stocks", []):
        code = str(s.get("code", "")).zfill(6)
        if code in mapped_codes:
            account_stock_total += float(s.get("eval_amt", 0) or 0)

    # ── 카테고리별 현금 비례 배분 ──
    if account_stock_total > 0:
        ratio = cat_filtered["stock_eval"] / account_stock_total
        cash = bal["cash"] * ratio
    else:
        # edge case: 매핑된 주식 평가금 0 → 첫 카테고리에 몰아줌
        cash = bal["cash"] if category == "Small Cap Growth" else 0.0

    total = cat_filtered["stock_eval"] + cash

    # ── 리밸런싱 시점 대비 수익률 (rebal.json 기반) ──
    rebal = load_krqt_rebal()
    rebal_base = float(rebal.get(category, 0) or 0)
    rebal_date = str(rebal.get("date", "") or "")
    rebal_ret = ((total - rebal_base) / rebal_base * 100) if rebal_base > 0 else 0.0

    return {
        "currency": "KRW",
        "total_krw": total,
        "stock_eval_krw": cat_filtered["stock_eval"],
        "cash_krw": cash,
        "stocks": cat_filtered["stocks"],
        "exchange_rate": 1.0,
        "account_total_krw": bal["total"],
        "rebal_base_krw": rebal_base,    # 리밸런싱 시점 자산
        "rebal_date":     rebal_date,
        "rebal_ret":      rebal_ret      # % (리밸런싱 대비)
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
    """
    USQT 계좌 (단일) 의 카테고리별 분리 (SCG/TCM 등) + 현금 비례 배분.

    분류 기준: /var/autobot/TR_USQT/USQT_result.json
      - 한 티커가 복수 카테고리에 속할 경우 result.json의 split qty 비율로
        실잔고의 평가금/수량을 재분할 (이전 csv 1:1 매핑 누락 버그 해결)
      - 현금은 매핑된 종목의 split 후 평가금 합 기준으로 카테고리별 비례 배분

    수익률(rebal_ret):
      - USQT_rebal.json (USD 기준) 의 리밸런싱 시점 카테고리 자산금 대비
        현재 (total_usd = 평가금+현금) 수익률 (%)
    """
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

    usqt_result = load_usqt_result()
    cat_filtered = split_usqt_by_result(bal, usqt_result, category)

    # ── 계좌 전체 주식평가금(result.json에 매핑된 종목 한정, USD) ──
    cat_keys = [c for c in usqt_result.keys() if c != "remain_last"]
    mapped_codes = set()
    for c in cat_keys:
        for x in usqt_result.get(c, []):
            mapped_codes.add(str(x.get("code", "")).strip().upper())

    account_stock_total = 0.0
    for s in bal.get("stocks", []):
        code = str(s.get("code", "")).strip().upper()
        if code in mapped_codes:
            account_stock_total += float(s.get("eval_amt", 0) or 0)

    # ── 카테고리별 현금 비례 배분 (USD) ──
    if account_stock_total > 0:
        ratio = cat_filtered["stock_eval"] / account_stock_total
        cash = bal["cash"] * ratio
    else:
        # edge case: 매핑된 주식 평가금 0 → 첫 카테고리(SCG)에 몰아줌
        cash = bal["cash"] if category == "SCG" else 0.0

    total_usd = cat_filtered["stock_eval"] + cash
    exrt = bal.get("exchange_rate", 0)

    # ── 리밸런싱 시점 대비 수익률 (rebal.json 기반, USD) ──
    rebal = load_usqt_rebal()
    rebal_base = float(rebal.get(category, 0) or 0)   # USD
    rebal_date = str(rebal.get("date", "") or "")
    rebal_ret = ((total_usd - rebal_base) / rebal_base * 100) if rebal_base > 0 else 0.0

    return {
        "currency": "USD",
        "total_usd": total_usd,
        "stock_eval_usd": cat_filtered["stock_eval"],
        "cash_usd": cash,
        "total_krw": total_usd * exrt if exrt > 0 else 0,
        "stocks": cat_filtered["stocks"],
        "exchange_rate": exrt,
        "account_total_usd": bal.get("total", 0),
        "rebal_base_usd": rebal_base,    # 리밸런싱 시점 자산 (USD)
        "rebal_date":     rebal_date,
        "rebal_ret":      rebal_ret      # % (리밸런싱 대비)
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
        "total_krw":      bal["total"],
        "stock_eval_krw": bal["stock_eval"],
        "cash_krw":       bal["cash"],
        "stocks":         bal["stocks"],
        "exchange_rate":  1.0,
        # 진단용 추가 필드
        "deposit":        bal.get("deposit", 0),         # 예수금(현금)
        "deposit_sbst":   bal.get("deposit_sbst", 0),    # 예수금(대용)
        "ord_psbl_cash":  bal.get("ord_psbl_cash", 0),   # 주문가능현금
        "wdrw_psbl":      bal.get("wdrw_psbl", 0),       # 인출가능
        "total_eval":     bal.get("total_eval", 0),      # 추정예탁자산
        "pos_pl":         bal.get("pos_pl", 0),          # 평가손익
    }


def handle_gbft(cano: str, acnt: str, kwargs: dict) -> dict:
    """해외선물옵션 계좌 잔고 (OTFM1412R + OTFM1411R, USD)

    한 계좌에 여러 sub("Hedge & Boost", "Commodity")가 매핑된 경우:
      - 캐시 키는 (cano, acnt, currency) 단위 → 첫 sub에서 잔고 1회 조회 후 캐시
      - 첫 호출자(=Hedge & Boost)에게 잔고 전체를 부여
      - 두 번째 이후 sub는 0원 (향후 result.json 기반 split 도입 가능)

    fetch_gbft_balance가 placeholder=True 반환시:
      - 에러가 아닌 정상 placeholder로 처리 → 텔레그램 '[미연결] 0원'
    """
    currency = kwargs.get("currency", "USD")
    sub      = kwargs.get("_sub", "")     # collect_accounts에서 주입 (없으면 빈 문자열)

    key = _cache_key("gbft", cano, acnt, currency)
    is_first_caller = (key not in _account_cache)
    if not is_first_caller:
        bal = _account_cache[key]
    else:
        bal = fetch_gbft_balance(cano, acnt, currency)
        _account_cache[key] = bal

    # 서비스 비활성 → placeholder
    if bal.get("placeholder"):
        return {
            "currency": currency,
            "total_krw": 0.0,
            f"total_{currency.lower()}": 0.0,
            f"stock_eval_{currency.lower()}": 0.0,
            f"cash_{currency.lower()}": 0.0,
            "stocks": [],
            "exchange_rate": 0.0,
            "placeholder": True,
            "note": bal.get("note", ""),
            "is_main": is_first_caller,
        }

    if "error" in bal:
        return {"error": bal["error"], "currency": currency,
                 "total_krw": 0.0, f"total_{currency.lower()}": 0.0, "stocks": [],
                 "is_main": is_first_caller}

    exrt         = bal.get("exchange_rate", 0)
    total_native = bal.get("total", 0)
    stock_eval   = bal.get("stock_eval", 0)
    cash         = bal.get("cash", 0)
    stocks       = bal.get("stocks", [])

    # KRW 환산: 1) native total × 환율,   2) 실패 시 KRW 직접값(tot_asst_krw) 사용
    total_krw = (total_native * exrt) if exrt > 0 else bal.get("tot_asst_krw", 0)

    # 첫 호출자(Hedge & Boost)에만 전체 잔고 부여, 나머지는 0
    if not is_first_caller:
        total_native = 0.0
        total_krw    = 0.0
        stock_eval   = 0.0
        cash         = 0.0
        stocks       = []

    return {
        "currency": currency,
        f"total_{currency.lower()}":      total_native,
        f"stock_eval_{currency.lower()}": stock_eval,
        f"cash_{currency.lower()}":       cash,
        "total_krw":     total_krw,
        "stocks":        stocks,
        "exchange_rate": exrt,
        "is_main":       is_first_caller,
        # 진단용 (첫 호출자만 의미있음)
        "deposit_native":  bal.get("deposit_native", 0)  if is_first_caller else 0,
        "deposit_krw":     bal.get("deposit_krw", 0)     if is_first_caller else 0,
        "ord_avail_native":bal.get("ord_avail_native", 0)if is_first_caller else 0,
        "tot_asst_tus":    bal.get("tot_asst_tus", 0)    if is_first_caller else 0,
        "tot_asst_krw":    bal.get("tot_asst_krw", 0)    if is_first_caller else 0,
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
            "account_total_usd": data.get("account_total_usd", 0),
            # KRQT 고유 (리밸런싱 시점 대비 수익률)
            "rebal_base_krw": data.get("rebal_base_krw", 0),
            "rebal_date":     data.get("rebal_date", ""),
            "rebal_ret":      data.get("rebal_ret", 0.0),
            # USQT 고유 (리밸런싱 시점 대비 수익률, USD)
            "rebal_base_usd": data.get("rebal_base_usd", 0)
        })

    return items


# ══════════════════════════════════════════════════
#  JSON 저장
# ══════════════════════════════════════════════════

def purge_old_snapshots(keep_days: int = 10) -> int:
    """
    SNAPSHOT_DIR 에서 오늘 기준 keep_days 일 초과된
    balance_YYYYMMDD.json 파일을 자동 삭제.
    Returns: 삭제된 파일 수
    """
    today = datetime.now().date()
    cutoff = today - timedelta(days=keep_days)
    deleted = 0
    try:
        for fname in os.listdir(SNAPSHOT_DIR):
            if not (fname.startswith("balance_") and fname.endswith(".json")):
                continue
            date_part = fname[len("balance_"):-len(".json")]  # YYYYMMDD
            if len(date_part) != 8 or not date_part.isdigit():
                continue
            try:
                file_date = datetime.strptime(date_part, "%Y%m%d").date()
            except ValueError:
                continue
            if file_date < cutoff:
                os.remove(os.path.join(SNAPSHOT_DIR, fname))
                deleted += 1
    except Exception:
        pass
    return deleted


def save_snapshot(mode: str, items: list) -> str:
    """
    balance_YYYYMMDD.json 에 mode별로 저장 (병합).
    저장 후 10일 초과 파일 자동 삭제.
    """
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

    # 10일 초과 파일 자동 삭제
    purge_old_snapshots(keep_days=10)

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
            is_krqt = (strategy == "KRQT")

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
                    if is_usqt:
                        # USQT 세부: USD 라인에 [리밸 대비 수익률] 표시
                        rebal_ret_usd  = it.get("rebal_ret", 0.0)
                        rebal_date_usd = it.get("rebal_date", "")
                        rebal_base_usd = it.get("rebal_base_usd", 0)
                        if rebal_base_usd > 0:
                            native_str = (f"{fmt_usd(native)}  "
                                          f"[리밸{rebal_date_usd} 대비 {fmt_pct(rebal_ret_usd)}]")
                        else:
                            native_str = f"{fmt_usd(native)}  [리밸기준 없음]"
                    else:
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
                if is_krqt:
                    # KRQT 세부: 리밸런싱 시점 대비 수익률 표시 (일별 변동 대신)
                    rebal_ret  = it.get("rebal_ret", 0.0)
                    rebal_date = it.get("rebal_date", "")
                    rebal_base = it.get("rebal_base_krw", 0)
                    if rebal_base > 0:
                        krw_str = (f"{fmt_krw(total_krw)}  "
                                   f"[리밸{rebal_date} 대비 {fmt_pct(rebal_ret)}]")
                    else:
                        krw_str = f"{fmt_krw(total_krw)}  [리밸기준 없음]"
                elif is_usqt:
                    # USQT KRW은 환율 영향이 섞이므로 일별 KRW 변동만 간단 표기
                    krw_str = f"{fmt_krw(total_krw)} ({fmt_pct(chg_krw)})"
                else:
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
            if strategy == "KRTR":
                msg.append(f"  → {strategy}소계: {fmt_krw(strat_sum_krw)}")
            elif strategy == "KRQT":
                # KRQT 전체 = 계좌 전체. 전일 대비 수익률은 모든 sub 전일 total_krw 합 vs 오늘 합
                prev_strat_sum = 0.0
                for it_chk in sitems:
                    pe = find_prev_entry(prev, it_chk["market"], strategy, it_chk["sub"])
                    prev_strat_sum += pe.get("total_krw", 0)
                acct_chg = calc_day_change(strat_sum_krw, prev_strat_sum)
                msg.append(f"  → KRQT소계(전체): {fmt_krw(strat_sum_krw)} ({fmt_pct(acct_chg)})")
            elif strategy == "USAA":
                msg.append(f"  → USAA소계: {fmt_krw(strat_sum_krw)} / {fmt_usd(strat_sum_native)}")
            elif strategy == "USQT":
                # USQT 전체 = 계좌 전체. 전일 대비는 USD 기준 (환율영향 제거)
                prev_strat_usd = 0.0
                for it_chk in sitems:
                    pe = find_prev_entry(prev, it_chk["market"], strategy, it_chk["sub"])
                    prev_strat_usd += pe.get("total_usd", 0)
                usd_chg = calc_day_change(strat_sum_native, prev_strat_usd)
                msg.append(f"  → USQT소계(전체): {fmt_krw(strat_sum_krw)} / "
                           f"{fmt_usd(strat_sum_native)} ({fmt_pct(usd_chg)})")
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
