"""
============================================================================
 키움증권 REST API - KRX 금현물 분할매매 자동화 (일반화 버전)
 파일명   : GOLD_monthlyTR.py
 환경     : Python 3.9+ / AWS EC2 Linux + crontab (시스템 시간 UTC)

 ── 이 코드의 일반화 포인트 ─────────────────────────────────────────────────
   기존 GOLD_TR.py 는 "연속된 N일" 만 지원했지만, 본 코드는
     · 연속된 일 기간      (예: 6월 1일~3일, 3거래일 연속)
     · 연속된 월 기간       (예: 6월~11월, 매월 1거래일)
     · 일 단위 주기          (예: 거래일 기준 1일/2일 주기로 N회)
     · 월 단위 주기          (예: 매월 1회/2회 등)
     · 매수/매도 모드        (분할매수 / 분할매도)
     · 거래일별 분할 횟수    (도입부 SPLITS_PER_DAY 로 지정)
   를 모두 동일 코드로 처리한다.

   매매일 결정 우선순위:
     1) SCHEDULED_TRADING_DATES 직접 명시 (가장 안전, 권장)
     2) 1)이 비어있으면 SCHEDULE_MODE/PERIOD_* 설정으로 자동 생성

   매월 1일이 휴장일이면 "그 달의 다음 영업일"로 자동 보정.
   매일 cron 호출 시 오늘 날짜가 SCHEDULED_TRADING_DATES 에 없으면 즉시 종료.

 ── crontab 사용 예 (2026년 6~11월 매월 1거래일, 일 5회 분할) ────────────────
   2026년 매월 1일이 거래일인 달과 아닌 달이 섞여 있어 2줄로 분리:
     · 6/1(월), 7/1(수), 9/1(화), 10/1(목)  → 매월 1일 그룹
     · 8/3(월), 11/3(화)                    → 매월 3일 그룹
       (8/1·11/1은 토요일이라 다음 영업일로 보정)

   crontab (UTC 기준, KST = UTC+9):
     ※ 한국 장중 KST 09~16시는 UTC 00~07시 → UTC 기준 일자/요일이 KST와 동일
     ※ 6~11월 모두 한국·UTC 날짜 동일 (한국은 DST 없음)

   # KRX 금현물 분할매매 — 매월 1일 그룹 (6/1·7/1·9/1·10/1)
   13 0 1 6,7,9,10 *  timeout -s 9 10m /usr/bin/python3 /var/autobot/TR_GOLD/GOLD_TR.py
   13 1 1 6,7,9,10 *  timeout -s 9 10m /usr/bin/python3 /var/autobot/TR_GOLD/GOLD_TR.py
   13 3 1 6,7,9,10 *  timeout -s 9 10m /usr/bin/python3 /var/autobot/TR_GOLD/GOLD_TR.py
   13 4 1 6,7,9,10 *  timeout -s 9 10m /usr/bin/python3 /var/autobot/TR_GOLD/GOLD_TR.py
   20 6 1 6,7,9,10 *  timeout -s 9 10m /usr/bin/python3 /var/autobot/TR_GOLD/GOLD_TR.py

   # KRX 금현물 분할매매 — 매월 3일 그룹 (8/3·11/3)
   13 0 3 8,11 *      timeout -s 9 10m /usr/bin/python3 /var/autobot/TR_GOLD/GOLD_TR.py
   13 1 3 8,11 *      timeout -s 9 10m /usr/bin/python3 /var/autobot/TR_GOLD/GOLD_TR.py
   13 3 3 8,11 *      timeout -s 9 10m /usr/bin/python3 /var/autobot/TR_GOLD/GOLD_TR.py
   13 4 3 8,11 *      timeout -s 9 10m /usr/bin/python3 /var/autobot/TR_GOLD/GOLD_TR.py
   20 6 3 8,11 *      timeout -s 9 10m /usr/bin/python3 /var/autobot/TR_GOLD/GOLD_TR.py

 key 파일 : /var/autobot/KIS/kiwgold52953897.txt
 토큰 캐시: /var/autobot/KIS/kiwgold_token.json
============================================================================
"""

import os
import sys
import json
import time
import logging
import datetime
import requests
from tendo import singleton
import telegram_alert as TA


# ===========================================================================
# 1) API 인증 정보
# ===========================================================================
KEY_FILE_PATH   = "/var/autobot/KIS/kiwgold52953897.txt"
TOKEN_FILE_PATH = "/var/autobot/KIS/kiwgold_token.json"

BASE_URL        = "https://api.kiwoom.com"
GOLD_STOCK_CODE = "M04020000"           # 금 99.99% 1kg (앞에 M 필수)
TOKEN_SAFETY_MARGIN_MIN = 30

URI_MRKCOND = "/api/dostk/mrkcond"
URI_CHART   = "/api/dostk/chart"
URI_ACNT    = "/api/dostk/acnt"
URI_ORDR    = "/api/dostk/ordr"

TR_URI_MAP = {
    "ka50100": URI_MRKCOND,
    "kt50020": URI_ACNT, "kt50021": URI_ACNT,
    "kt50031": URI_ACNT, "kt50075": URI_ACNT,
    "kt50000": URI_ORDR, "kt50001": URI_ORDR, "kt50003": URI_ORDR,
}

APP_KEY    = None
APP_SECRET = None


# ===========================================================================
# 2) 매매 설정  ── 모든 시나리오의 진입점
# ===========================================================================

# ── 매매 모드 ──────────────────────────────────────────────────────────────
#   "buy"  : 분할매수 / "sell" : 분할매도
MODE = "buy"

# ── 매수/매도 비율 ─────────────────────────────────────────────────────────
#   buy  : 주문가능 예수금 대비 % (100=전액 분할매수)
#   sell : 현재 보유수량 대비 % (100=전량 분할매도)
BUY_CASH_RATIO = 100
SELL_QTY_RATIO = 100

# ── 1일 분할 횟수 ──────────────────────────────────────────────────────────
#   cron 1일 호출 횟수와 반드시 일치시킬 것.
SPLITS_PER_DAY = 5

# ── 1일 분할 시각 (UTC 기준; KST = UTC+9) ───────────────────────────────────
#   분할     KST          UTC(코드/crontab)
#   1번째    09:13        00:13
#   2번째    10:13        01:13
#   3번째    12:13        03:13
#   4번째    13:13        04:13
#   5번째    15:20        06:20
#   ※ SPLITS_PER_DAY 개수와 길이를 일치시킬 것 (앞에서부터 사용).
SPLIT_SCHEDULE = [
    (0,  13),
    (1,  13),
    (3,  13),
    (4,  13),
    (6,  20),
]

# ── 매매일 직접 명시 (권장; 비어있으면 SCHEDULE_MODE 자동 생성 사용) ──────
#   YYYY-MM-DD 문자열 리스트. crontab 날짜와 1:1 매칭되어야 한다.
#   ※ 운영자 의도가 가장 명확히 드러나는 방식이므로 권장.
#   ※ 본 예시: 2026년 6~11월, 매월 1거래일 기준.
#     8/1(토)·11/1(토) → 다음 영업일 8/3(월)·11/3(화)로 보정.
SCHEDULED_TRADING_DATES = [
    "2026-06-01",   # 월
    "2026-07-01",   # 수
    "2026-08-03",   # 월 (8/1 토요일 보정)
    "2026-09-01",   # 화
    "2026-10-01",   # 목
    "2026-11-03",   # 화 (11/1 토요일 보정)
]

# ── (옵션) SCHEDULED_TRADING_DATES 가 비어있을 때 자동 생성 규칙 ──────────
#   향후 다른 시나리오로 운영할 때를 위한 일반화된 규칙.
#   사용하려면 SCHEDULED_TRADING_DATES = [] 로 두고 아래를 채울 것.
#
#   SCHEDULE_MODE :
#     "daily"    : START_DATE 부터 영업일 기준 STEP_DAYS 주기로 TOTAL_OCCURRENCES 회
#     "monthly"  : START_DATE 의 달부터 STEP_MONTHS 주기로 TOTAL_OCCURRENCES 회,
#                  각 달의 "DAY_OF_MONTH" 일을 기본으로 하되 휴장일이면 다음 영업일.
#                  PICKS_PER_MONTH 가 2 이상이면 그 달의 N번째 영업일까지 추가.
SCHEDULE_MODE      = "monthly"
START_DATE         = "2026-06-01"
STEP_DAYS          = 1      # daily 모드: 영업일 기준 N일 주기
STEP_MONTHS        = 1      # monthly 모드: N개월 주기
TOTAL_OCCURRENCES  = 6      # 총 매매일 수
DAY_OF_MONTH       = 1      # monthly 모드: 매월 며칠을 기준일로?
PICKS_PER_MONTH    = 1      # monthly 모드: 그 달에 매매할 거래일 수

# ── 분할/일자 수동 오버라이드 (디버깅/리커버리 용도) ──────────────────────
SPLIT_INDEX_OVERRIDE = None   # None=현재 시각으로 자동 판별
DAY_INDEX_OVERRIDE   = None   # None=오늘 날짜로 SCHEDULED 리스트에서 자동 검색

# ── 지정가 슬리피지 ────────────────────────────────────────────────────────
LIMIT_SLIPPAGE_BUY  = 0.005
LIMIT_SLIPPAGE_SELL = 0.005

# ── 매매구분 ───────────────────────────────────────────────────────────────
TRADE_TYPE = "0"        # "0"=지정가 / "10"=IOC / "20"=FOK


# ===========================================================================
# 로깅
# ===========================================================================
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "krx_gold_trading.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("krx_gold")


# ===========================================================================
# 3) 공통 유틸
# ===========================================================================
def _to_int(val):
    s = str(val).replace(",", "").replace("+", "").strip()
    if not s or s in ("-", ""):
        return 0
    return int(float(s))


def _to_float(val):
    s = str(val).replace(",", "").replace("+", "").replace("%", "").strip()
    if not s or s in ("-", ""):
        return 0.0
    return float(s)


GOLD_TICK_SIZE = 10

def ceil_to_tick(price, tick=GOLD_TICK_SIZE):
    price = int(price)
    return ((price + tick - 1) // tick) * tick

def floor_to_tick(price, tick=GOLD_TICK_SIZE):
    price = int(price)
    return (price // tick) * tick


def acquire_singleton():
    try:
        return singleton.SingleInstance()
    except singleton.SingleInstanceException:
        TA.send_tele("GOLD: 이미 실행 중입니다.")
        sys.exit(0)


def load_api_keys():
    global APP_KEY, APP_SECRET
    if APP_KEY and APP_SECRET:
        return APP_KEY, APP_SECRET
    try:
        with open(KEY_FILE_PATH, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f.readlines()]
        APP_KEY, APP_SECRET = lines[0], lines[1]
        return APP_KEY, APP_SECRET
    except Exception as e:
        raise RuntimeError(f"GOLD: key 파일 로드 실패: {e}")


# ===========================================================================
# 4) 인증 / 토큰 / API 호출
# ===========================================================================
def get_access_token(force_new: bool = False):
    load_api_keys()
    if not force_new and os.path.exists(TOKEN_FILE_PATH):
        try:
            with open(TOKEN_FILE_PATH, "r", encoding="utf-8") as f:
                cached = json.load(f)
            expires_at = datetime.datetime.fromisoformat(cached["expires_at"])
            margin = datetime.timedelta(minutes=TOKEN_SAFETY_MARGIN_MIN)
            if datetime.datetime.now() < expires_at - margin:
                log.info("캐시된 접근토큰 사용")
                return cached["access_token"]
        except Exception as e:
            log.warning(f"토큰 캐시 로드 실패, 신규 발급: {e}")

    url     = f"{BASE_URL}/oauth2/token"
    headers = {"Content-Type": "application/json;charset=UTF-8"}
    body    = {"grant_type": "client_credentials",
               "appkey": APP_KEY, "secretkey": APP_SECRET}
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        raise RuntimeError(f"GOLD: 토큰 발급 API 실패: {e}")

    token = data.get("token") or data.get("access_token")
    if not token:
        raise RuntimeError(f"GOLD: 토큰 발급 응답에 토큰 없음: {data}")

    if data.get("expires_dt"):
        expires_at = datetime.datetime.strptime(data["expires_dt"], "%Y%m%d%H%M%S")
    else:
        expires_in = int(data.get("expires_in", 86400))
        expires_at = datetime.datetime.now() + datetime.timedelta(seconds=expires_in)

    os.makedirs(os.path.dirname(TOKEN_FILE_PATH), exist_ok=True)
    with open(TOKEN_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump({"access_token": token, "expires_at": expires_at.isoformat()},
                  f, ensure_ascii=False, indent=2)
    log.info(f"접근토큰 신규 발급 완료{' (강제)' if force_new else ''}")
    return token


_TOKEN_ERR_KEYWORDS = ("8005", "토큰", "token", "유효하지 않")
_CURRENT_TOKEN = None


def _api_headers(token, api_id):
    return {
        "Content-Type":  "application/json;charset=UTF-8",
        "authorization": f"Bearer {token}",
        "appkey":        APP_KEY,
        "appsecret":     APP_SECRET,
        "api-id":        api_id,
    }


def _post(token, api_id, body, timeout=10, _token_retry=True):
    global _CURRENT_TOKEN
    uri  = TR_URI_MAP.get(api_id)
    if uri is None:
        raise ValueError(f"알 수 없는 TR: {api_id}")
    url  = f"{BASE_URL}{uri}"
    resp = requests.post(url, headers=_api_headers(token, api_id), json=body, timeout=timeout)
    resp.raise_for_status()
    data = resp.json() if resp.text else {}

    rc = data.get("return_code", -1)
    if rc != 0:
        msg = data.get("return_msg", "")
        is_token_err = any(kw in str(msg) for kw in _TOKEN_ERR_KEYWORDS)
        if is_token_err and _token_retry:
            log.warning(f"[{api_id}] 토큰 무효({msg}) → 강제 재발급 후 재시도")
            new_token = get_access_token(force_new=True)
            _CURRENT_TOKEN = new_token
            return _post(new_token, api_id, body, timeout=timeout, _token_retry=False)
        raise RuntimeError(f"[{api_id}] return_code={rc} | {msg}")
    return data


# ===========================================================================
# 5) 거래일 / 시세 / 계좌 (원본 GOLD_TR.py 와 동일)
# ===========================================================================
def is_gold_trading_day_via_api(token, date: datetime.date = None) -> bool:
    """주어진 날짜가 금현물 거래일인지 확인 (오늘이 기본).

    ※ ka50100 은 '오늘' 시세만 응답하므로 date 가 오늘이 아닐 때는
       주말만 걸러내고 평일은 True 로 가정한다 (스케줄 자동 생성용).
    """
    if date is None:
        date = datetime.date.today()
    if date.weekday() >= 5:
        return False
    if date != datetime.date.today():
        return True   # 미래 평일은 일단 거래일로 가정(스케줄 산출용)
    try:
        data = _post(token, "ka50100", {"stk_cd": GOLD_STOCK_CODE})
        volume = _to_int(data.get("trde_qty", 0))
        if volume <= 0:
            log.info(f"거래일 확인: {date} → 당일 거래량 0 → 휴장")
            return False
        log.info(f"거래일 확인: {date} → 정상 (거래량 {volume:,})")
        return True
    except Exception as e:
        log.warning(f"거래일 확인 API 실패, 평일 기준으로 대체: {e}")
        return True


def get_gold_current_price(token):
    data = _post(token, "ka50100", {"stk_cd": GOLD_STOCK_CODE})
    pred_close = _to_int(data.get("pred_close_pric", 0))
    pre_raw    = str(data.get("pred_pre", "0")).replace(",", "").strip()
    pred_pre   = int(float(pre_raw)) if pre_raw and pre_raw not in ("-", "") else 0
    price = pred_close + pred_pre
    if price <= 0:
        price = pred_close
    log.info(f"금현물 현재가(추정): {price:,}원 (전일종가 {pred_close:,} {pred_pre:+,})")
    return price


def get_gold_balance(token):
    """금현물 잔고확인(kt50020). 원본과 동일."""
    data = _post(token, "kt50020", {})

    deposit     = _to_int(data.get("net_entr", 0))
    deposit_raw = _to_int(data.get("tot_entr", 0))
    if deposit <= 0:
        try:
            dep_data = _post(token, "kt50021", {})
            deposit = _to_int(dep_data.get("prsm_entra", 0))
            if deposit <= 0:
                deposit = _to_int(dep_data.get("prsm_pymn_alow_amt", 0))
            if deposit <= 0:
                buy_exct = _to_int(dep_data.get("buy_exct_amt", 0))
                deposit = max(deposit_raw - buy_exct, 0)
            log.warning(f"net_entr 0 → kt50021 보강: {deposit:,}원")
        except Exception as e:
            log.warning(f"kt50021 보강 실패, tot_entr 사용: {e}")
            deposit = deposit_raw

    result = {
        "deposit":          deposit,
        "deposit_raw":      deposit_raw,
        "eval_amt":         0,
        "total_amt":        0,
        "hold_qty":         0,
        "avg_price":        0,
        "cur_price":        0,
        "profit_loss":      0,
        "return_rate":      0.0,
        "sellable_qty":     0,
        "tot_dep_amt_raw":  _to_int(data.get("tot_dep_amt", 0)),
    }

    for item in data.get("gold_acnt_evlt_prst", []) or []:
        if item.get("stk_cd") == GOLD_STOCK_CODE:
            result["hold_qty"]     = _to_int(item.get("real_qty", 0))
            result["avg_price"]    = _to_int(item.get("avg_prc", 0))
            result["cur_price"]    = _to_int(item.get("cur_prc", 0))
            result["eval_amt"]     = _to_int(item.get("est_amt", 0))
            pl_raw = str(item.get("est_lspft", "0")).replace(",", "").replace("+", "").strip()
            result["profit_loss"]  = int(float(pl_raw)) if pl_raw and pl_raw != "-" else 0
            rr_raw = str(item.get("est_ratio", "0")).replace(",", "").replace("+", "").replace("%", "").strip()
            result["return_rate"]  = float(rr_raw) if rr_raw and rr_raw != "-" else 0.0
            result["sellable_qty"] = _to_int(item.get("able_qty", 0))
            break

    if result["eval_amt"] <= 0 and result["hold_qty"] > 0:
        if result["cur_price"] <= 0:
            try:
                result["cur_price"] = get_gold_current_price(token)
            except Exception as e:
                log.warning(f"현재가 보강 실패: {e}")
        result["eval_amt"] = result["cur_price"] * result["hold_qty"]
        log.warning(f"est_amt=0 → cur_prc×수량 폴백: {result['eval_amt']:,}원")

    result["total_amt"] = result["eval_amt"] + deposit

    log.info(
        f"잔고: 보유 {result['hold_qty']}g / 매도가능 {result['sellable_qty']}g / "
        f"현재가 {result['cur_price']:,}원 / 금평가금 {result['eval_amt']:,}원 / "
        f"예수금 {result['deposit']:,}원(정산반영) / 총평가금 {result['total_amt']:,}원"
    )
    return result


def get_orderable_cash(token):
    try:
        data = _post(token, "kt50021", {})
        cash = _to_int(data.get("ord_alow_amt", 0))
        if cash <= 0:
            cash = _to_int(data.get("entra", 0))
        log.info(f"주문가능금액: {cash:,}원")
        return cash
    except Exception as e:
        log.warning(f"예수금 조회 실패, 잔고 예수금으로 폴백: {e}")
        return get_gold_balance(token)["deposit"]


def get_today_execution(token):
    today = datetime.date.today().strftime("%Y%m%d")
    try:
        data = _post(token, "kt50031", {
            "qry_tp": "1", "stk_bond_tp": "0", "sell_tp": "0",
            "dmst_stex_tp": "KRX", "ord_dt": today,
            "stk_cd": GOLD_STOCK_CODE, "fr_ord_no": "",
        })
    except Exception as e:
        log.warning(f"주문체결조회 실패: {e}")
        return {"filled_qty": 0, "filled_amt": 0, "count": 0}

    filled_qty = filled_amt = count = 0
    for item in data.get("acnt_ord_cntr_prps_dtl", []) or []:
        ord_no = str(item.get("ord_no", "")).strip().lstrip("0")
        if not ord_no:
            continue
        if item.get("stk_cd") and item.get("stk_cd") != GOLD_STOCK_CODE:
            continue
        cq = _to_int(item.get("cntr_qty", 0))
        cu = _to_int(item.get("cntr_uv", 0))
        if cq > 0:
            filled_qty += cq
            filled_amt += cq * cu
            count      += 1
    log.info(f"당일 체결: {count}건 / {filled_qty}g / {filled_amt:,}원")
    return {"filled_qty": filled_qty, "filled_amt": filled_amt, "count": count}


def get_unfilled_qty(token):
    today = datetime.date.today().strftime("%Y%m%d")
    try:
        data = _post(token, "kt50075", {
            "ord_dt": today, "mrkt_deal_tp": "0", "stk_bond_tp": "0",
            "sell_tp": "0", "qry_tp": "1", "stk_cd": GOLD_STOCK_CODE,
            "fr_ord_no": "", "dmst_stex_tp": "KRX",
        })
    except Exception as e:
        log.warning(f"미체결조회 실패: {e}")
        return 0

    total = 0
    for item in data.get("acnt_ord_oso_prst", []) or []:
        total += _to_int(item.get("ord_remnq", item.get("ord_qty", 0)))
    if total:
        log.info(f"미체결 잔량: {total}g")
    return total


# ===========================================================================
# 6) 주문 API
# ===========================================================================
def place_gold_order(token, side, qty, price):
    if qty <= 0:
        log.warning("주문수량 0 이하 → 건너뜀")
        return None
    api_id = "kt50000" if side == "buy" else "kt50001"
    body = {
        "stk_cd":  GOLD_STOCK_CODE,
        "ord_qty": str(qty),
        "ord_uv":  str(price),
        "trde_tp": TRADE_TYPE,
    }
    data   = _post(token, api_id, body)
    ord_no = data.get("ord_no", "")
    if ord_no:
        log.info(f"[{side.upper()}] 주문 완료 — {qty}g @ {price:,}원 / 주문번호 {ord_no}")
    else:
        log.warning(f"[{side.upper()}] 주문 응답에 주문번호 없음: {data}")
    return ord_no if ord_no else None


def cancel_gold_order(token, ord_no, qty=0):
    body = {"orig_ord_no": str(ord_no), "stk_cd": GOLD_STOCK_CODE,
            "cncl_qty": str(qty)}
    try:
        data    = _post(token, "kt50003", body)
        cncl_no = data.get("ord_no", "")
        log.info(f"취소주문 완료 — 원주문 {ord_no} / 취소번호 {cncl_no}")
        return cncl_no if cncl_no else None
    except Exception as e:
        log.error(f"취소주문 실패 (원주문 {ord_no}): {e}")
        return None


# ===========================================================================
# 7) 매매일 결정 (핵심 신규 로직)
# ===========================================================================
def _is_weekday(d: datetime.date) -> bool:
    return d.weekday() < 5


def _next_business_day(d: datetime.date) -> datetime.date:
    """주말이면 다음 평일로. (공휴일은 본 함수에선 처리 불가 → ka50100 거래량 체크가 최종 방어선)"""
    while not _is_weekday(d):
        d += datetime.timedelta(days=1)
    return d


def _add_months(d: datetime.date, months: int) -> datetime.date:
    """연/월 wrap-around 처리한 월 가산. 일자는 그대로 유지(없는 일자는 말일로)."""
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    day = d.day
    # 해당 월에 그 일자가 없으면 말일로 보정
    while True:
        try:
            return datetime.date(y, m, day)
        except ValueError:
            day -= 1
            if day < 1:
                raise


def build_schedule_from_rules() -> list:
    """SCHEDULE_MODE 설정에 따라 매매일 리스트 자동 생성.
    SCHEDULED_TRADING_DATES 가 비어있을 때만 사용.
    """
    try:
        start = datetime.date.fromisoformat(START_DATE)
    except Exception as e:
        raise ValueError(f"START_DATE 파싱 오류({START_DATE}): {e}")

    dates: list = []

    if SCHEDULE_MODE == "daily":
        # 영업일 기준 STEP_DAYS 주기로 TOTAL_OCCURRENCES 회
        cur = _next_business_day(start)
        for _ in range(TOTAL_OCCURRENCES):
            dates.append(cur)
            # STEP_DAYS 만큼 영업일 진행
            advanced = 0
            nxt = cur
            while advanced < STEP_DAYS:
                nxt += datetime.timedelta(days=1)
                if _is_weekday(nxt):
                    advanced += 1
            cur = nxt

    elif SCHEDULE_MODE == "monthly":
        # 매월(STEP_MONTHS 주기) DAY_OF_MONTH 기준일 → 영업일로 보정,
        # PICKS_PER_MONTH>=2 면 그 달의 N번째 영업일까지 추가.
        # TOTAL_OCCURRENCES 가 채워질 때까지 반복.
        anchor = datetime.date(start.year, start.month, DAY_OF_MONTH)
        produced = 0
        while produced < TOTAL_OCCURRENCES:
            # 그 달의 기준일을 영업일로 보정
            first_day = _next_business_day(anchor)
            month_picks = [first_day]
            # 같은 달 안에서 다음 영업일들 추가
            extra = first_day
            for _ in range(PICKS_PER_MONTH - 1):
                extra += datetime.timedelta(days=1)
                extra = _next_business_day(extra)
                # 같은 달 안에 있을 때만 추가 (월 경계 넘어가면 중단)
                if extra.month == first_day.month and extra.year == first_day.year:
                    month_picks.append(extra)
                else:
                    break
            for d in month_picks:
                if produced >= TOTAL_OCCURRENCES:
                    break
                dates.append(d)
                produced += 1
            # 다음 달 기준일로 이동
            anchor = _add_months(anchor, STEP_MONTHS)
    else:
        raise ValueError(f"알 수 없는 SCHEDULE_MODE: {SCHEDULE_MODE}")

    return [d.isoformat() for d in dates]


def resolve_schedule() -> list:
    """최종 매매일 리스트 반환 (YYYY-MM-DD 문자열, 오름차순).
    1) SCHEDULED_TRADING_DATES 가 채워져 있으면 그대로 사용
    2) 비어있으면 build_schedule_from_rules() 로 자동 생성
    """
    if SCHEDULED_TRADING_DATES:
        raw = list(SCHEDULED_TRADING_DATES)
    else:
        raw = build_schedule_from_rules()
    # 정규화 + 정렬 + 중복 제거
    dates = sorted(set(datetime.date.fromisoformat(s) for s in raw))
    return [d.isoformat() for d in dates]


def get_day_index(schedule: list) -> int:
    """오늘이 매매일 리스트의 몇 번째인지(1-base) 반환. 매매일 아니면 0."""
    if DAY_INDEX_OVERRIDE is not None:
        log.info(f"매매 일차 수동 지정: {DAY_INDEX_OVERRIDE}")
        return DAY_INDEX_OVERRIDE
    today_iso = datetime.date.today().isoformat()
    if today_iso in schedule:
        idx = schedule.index(today_iso) + 1
        log.info(f"매매 일차: {idx} / {len(schedule)} (오늘 {today_iso})")
        return idx
    log.info(f"오늘({today_iso})은 매매일 아님 (전체 {len(schedule)}일)")
    return 0


def get_today_split_index() -> int:
    """현재 시각으로 오늘 몇 번째 분할인지 (1-base, UTC 기준)."""
    if SPLIT_INDEX_OVERRIDE is not None:
        log.info(f"분할 인덱스 수동 지정: {SPLIT_INDEX_OVERRIDE}")
        return SPLIT_INDEX_OVERRIDE

    now     = datetime.datetime.utcnow()    # crontab/SPLIT_SCHEDULE 모두 UTC
    now_min = now.hour * 60 + now.minute
    best_idx, best_diff = None, None
    for idx, (h, m) in enumerate(SPLIT_SCHEDULE[:SPLITS_PER_DAY], start=1):
        diff = abs(now_min - (h * 60 + m))
        if best_diff is None or diff < best_diff:
            best_idx, best_diff = idx, diff
    if best_diff is not None and best_diff > 30:
        log.warning(f"현재시각이 분할 스케줄과 {best_diff}분 차이 → {best_idx}번째로 처리")
    log.info(f"오늘 분할 인덱스: {best_idx} / {SPLITS_PER_DAY}")
    return best_idx


# ===========================================================================
# 8) 텔레그램 헬퍼
# ===========================================================================
def _fmt_balance(bal):
    return [
        f"보유수량   : {bal['hold_qty']}g",
        f"매도가능   : {bal['sellable_qty']}g",
        f"매입단가   : {bal['avg_price']:,}원/g",
        f"현재가     : {bal['cur_price']:,}원/g",
        f"금평가금   : {bal['eval_amt']:,}원",
        f"평가손익   : {bal['profit_loss']:,}원",
        f"수익률     : {bal['return_rate']:.2f}%",
        f"예수금     : {bal['deposit']:,}원  (정산반영)",
        f"총평가금   : {bal['total_amt']:,}원  (금평가금+예수금)",
    ]


# ===========================================================================
# 9) 매수 / 매도 로직 ── 호출 1회 = 주문 1회
# ===========================================================================
def run_buy(token, split_index, day_index, total_trading_days):
    """분할매수 1회. 전체 잔여 분할 횟수로 균등 배분 → 부분체결 자동 보정."""
    msg   = []
    cash  = get_orderable_cash(token)
    price = get_gold_current_price(token)

    target_cash = int(cash * BUY_CASH_RATIO / 100)
    if target_cash <= 0 or price <= 0:
        msg.append("GOLD: 매수가능금액 또는 현재가 0 → 매수 중단")
        return msg, None

    total_splits     = total_trading_days * SPLITS_PER_DAY
    global_index     = (day_index - 1) * SPLITS_PER_DAY + split_index
    global_index     = max(1, min(global_index, total_splits))
    remaining_splits = max(1, total_splits - (global_index - 1))

    this_cash   = target_cash // remaining_splits
    order_price = ceil_to_tick(price * (1 + LIMIT_SLIPPAGE_BUY))
    this_qty    = this_cash // order_price if order_price > 0 else 0

    if this_qty <= 0:
        msg.append(
            f"GOLD: {split_index}회차 매수수량 0g → 건너뜀 "
            f"(배정 {this_cash:,}원 / 단가 {order_price:,}원)"
        )
        return msg, None

    msg.append(
        f"[매수] {split_index}/{SPLITS_PER_DAY}회차 "
        f"({day_index}/{total_trading_days}일차, 전체 {global_index}/{total_splits}회) | "
        f"배정 {this_cash:,}원 | 지정가 {order_price:,}원 | 수량 {this_qty}g"
    )
    ord_no = place_gold_order(token, "buy", this_qty, order_price)
    msg.append(f"주문 접수 완료 | 주문번호: {ord_no}" if ord_no
               else "GOLD: 매수 주문 응답 이상 (주문번호 없음)")
    return msg, ord_no


def run_sell(token, split_index, day_index, total_trading_days):
    """분할매도 1회. 매 호출 시 보유/매도가능을 재조회 → 부분체결 자동 보정."""
    msg = []
    bal = get_gold_balance(token)

    hold_qty     = bal["hold_qty"]
    sellable_qty = bal["sellable_qty"]
    price        = bal["cur_price"] or get_gold_current_price(token)

    if hold_qty <= 0:
        msg.append("GOLD: 보유수량 0g → 매도 중단")
        return msg, None

    target_qty = int(hold_qty * SELL_QTY_RATIO / 100)
    if target_qty <= 0:
        msg.append("GOLD: 매도 목표수량 0g → 매도 중단")
        return msg, None

    total_splits     = total_trading_days * SPLITS_PER_DAY
    global_index     = (day_index - 1) * SPLITS_PER_DAY + split_index
    global_index     = max(1, min(global_index, total_splits))
    remaining_splits = max(1, total_splits - (global_index - 1))

    this_qty = target_qty // remaining_splits
    if this_qty < 1:
        this_qty = target_qty       # 분할단위 미만이면 잔량 전량

    this_qty = min(this_qty, sellable_qty)
    if this_qty <= 0:
        msg.append(
            f"GOLD: 매도가능수량 0g → 건너뜀 (보유 {hold_qty}g / 매도가능 {sellable_qty}g)"
        )
        return msg, None

    order_price = floor_to_tick(price * (1 - LIMIT_SLIPPAGE_SELL))
    msg.append(
        f"[매도] {split_index}/{SPLITS_PER_DAY}회차 "
        f"({day_index}/{total_trading_days}일차, 전체 {global_index}/{total_splits}회) | "
        f"보유 {hold_qty}g / 매도가능 {sellable_qty}g | 이번 {this_qty}g | "
        f"지정가 {order_price:,}원"
    )
    ord_no = place_gold_order(token, "sell", this_qty, order_price)
    msg.append(f"주문 접수 완료 | 주문번호: {ord_no}" if ord_no
               else "GOLD: 매도 주문 응답 이상 (주문번호 없음)")
    return msg, ord_no


# ===========================================================================
# 10) 메인
# ===========================================================================
def main():
    me = acquire_singleton()
    now_str  = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mode_kor = "매수" if MODE == "buy" else "매도"

    log.info("=" * 60)
    log.info(f"KRX 금현물 자동매매 시작 | MODE={MODE} | 1일분할={SPLITS_PER_DAY}회")

    # ── 설정값 유효성
    if MODE not in ("buy", "sell"):
        TA.send_tele(f"GOLD: MODE 설정 오류 ({MODE}) → 종료")
        sys.exit(1)
    if len(SPLIT_SCHEDULE) < SPLITS_PER_DAY:
        TA.send_tele("GOLD: SPLIT_SCHEDULE 개수 부족 → 종료")
        sys.exit(1)

    # ── 매매일 스케줄 확정
    try:
        schedule = resolve_schedule()
    except Exception as e:
        TA.send_tele(f"GOLD: 매매일 스케줄 생성 오류 → 종료\n{e}")
        sys.exit(1)

    total_trading_days = len(schedule)
    log.info(f"매매일 스케줄 (전체 {total_trading_days}일): {schedule}")

    try:
        token = get_access_token()

        # ── 오늘이 매매일인지 검사 (cron 날짜와 SCHEDULED 불일치 방어)
        day_index = get_day_index(schedule)
        if day_index == 0:
            log.info("오늘은 매매일이 아님 → 종료")
            sys.exit(0)

        # ── 거래일(휴장) 재확인 — ka50100 거래량 기반
        if not is_gold_trading_day_via_api(token):
            TA.send_tele(f"GOLD: 거래일이 아님(휴장 추정, {datetime.date.today()}) → 종료")
            sys.exit(0)

        split_index = get_today_split_index()

        # ── 하루 첫 분할: 시작 알림
        if split_index == 1:
            total_splits = total_trading_days * SPLITS_PER_DAY
            global_index = (day_index - 1) * SPLITS_PER_DAY + split_index
            TA.send_tele([
                "━━━━━━━━━━━━━━━━━━━━━━━━",
                "🥇 KRX 금현물 자동매매 시작",
                f"일시  : {now_str}",
                f"모드  : {mode_kor} ({SPLITS_PER_DAY}회 분할 / 매매일 {total_trading_days}일)",
                f"진행  : {day_index}일차 | 전체 {global_index}/{total_splits}회차",
                f"종목  : 금 99.99% 1kg ({GOLD_STOCK_CODE})",
                "━━━━━━━━━━━━━━━━━━━━━━━━",
            ])

        # ── 매매 실행
        if MODE == "buy":
            order_msg, ord_no = run_buy(token, split_index, day_index, total_trading_days)
        else:
            order_msg, ord_no = run_sell(token, split_index, day_index, total_trading_days)

        # ── 체결 확인
        time.sleep(5)
        exec_info = get_today_execution(token)
        unfilled  = get_unfilled_qty(token)
        if exec_info["count"] > 0:
            order_msg.append(
                f"당일 체결누계: {exec_info['count']}건 / "
                f"{exec_info['filled_qty']}g / {exec_info['filled_amt']:,}원"
            )
        if unfilled > 0:
            order_msg.append(f"미체결 잔량: {unfilled}g (장 마감 시 자동 소멸)")

        bal = get_gold_balance(token)

        # ── 하루 마지막 분할: 일일 요약
        if split_index == SPLITS_PER_DAY:
            TA.send_tele(
                [
                    "━━━━━━━━━━━━━━━━━━━━━━━━",
                    "🥇 KRX 금현물 일일 매매 완료",
                    f"일시  : {now_str}",
                    f"모드  : {mode_kor}",
                    f"진행  : {day_index}/{total_trading_days}일차",
                    "━━━━━━━━━━━━━━━━━━━━━━━━",
                ]
                + order_msg
                + ["─────────────────────────"]
                + _fmt_balance(bal)
                + ["━━━━━━━━━━━━━━━━━━━━━━━━"]
            )
        else:
            TA.send_tele(
                [f"🥇 GOLD {mode_kor} {split_index}/{SPLITS_PER_DAY}회차 | {now_str}"]
                + order_msg
            )

        log.info("KRX 금현물 자동매매 정상 종료")

    except requests.exceptions.HTTPError as e:
        err_text = getattr(e.response, "text", "")[:300]
        log.error(f"API HTTP 오류: {e} | {err_text}")
        TA.send_tele([f"GOLD: API HTTP 오류 → 종료", str(e), err_text])
        sys.exit(1)
    except Exception as e:
        log.error(f"실행 중 오류: {e}", exc_info=True)
        TA.send_tele(f"GOLD: 예외 발생 → 종료\n{e}")
        sys.exit(1)
    finally:
        log.info("=" * 60)


if __name__ == "__main__":
    main()


# ===========================================================================
# [ crontab 설정 — 2026년 6~11월 매월 1거래일, 일 5회 분할 ]
#  EC2는 UTC. KST = UTC + 9. 한국 6~11월은 DST 없음 → UTC 날짜 == KST 날짜.
#  
#  매월 1일이 거래일인 달과 아닌 달이 섞여 있어 2그룹으로 분리:
#    · 6/1(월), 7/1(수), 9/1(화), 10/1(목)        ← "1일" 그룹
#    · 8/3(월), 11/3(화)  (8/1·11/1은 토요일 보정) ← "3일" 그룹
#
#  ※ SCHEDULED_TRADING_DATES 가 최종 권한 → cron 이 비매매일에 호출돼도
#    day_index=0 으로 즉시 종료되므로 안전. cron 은 "낭비 없이 정확히 호출"
#    하기 위한 보조 게이트일 뿐.
#
#   $ crontab -e
#
#   # KRX 금현물 분할매매 — 매월 1일 그룹 (6/1·7/1·9/1·10/1)
#   13 0 1 6,7,9,10 *  timeout -s 9 10m /usr/bin/python3 /var/autobot/TR_GOLD/GOLD_TR.py
#   13 1 1 6,7,9,10 *  timeout -s 9 10m /usr/bin/python3 /var/autobot/TR_GOLD/GOLD_TR.py
#   13 3 1 6,7,9,10 *  timeout -s 9 10m /usr/bin/python3 /var/autobot/TR_GOLD/GOLD_TR.py
#   13 4 1 6,7,9,10 *  timeout -s 9 10m /usr/bin/python3 /var/autobot/TR_GOLD/GOLD_TR.py
#   20 6 1 6,7,9,10 *  timeout -s 9 10m /usr/bin/python3 /var/autobot/TR_GOLD/GOLD_TR.py
#
#   # KRX 금현물 분할매매 — 매월 3일 그룹 (8/3·11/3)
#   13 0 3 8,11 *      timeout -s 9 10m /usr/bin/python3 /var/autobot/TR_GOLD/GOLD_TR.py
#   13 1 3 8,11 *      timeout -s 9 10m /usr/bin/python3 /var/autobot/TR_GOLD/GOLD_TR.py
#   13 3 3 8,11 *      timeout -s 9 10m /usr/bin/python3 /var/autobot/TR_GOLD/GOLD_TR.py
#   13 4 3 8,11 *      timeout -s 9 10m /usr/bin/python3 /var/autobot/TR_GOLD/GOLD_TR.py
#   20 6 3 8,11 *      timeout -s 9 10m /usr/bin/python3 /var/autobot/TR_GOLD/GOLD_TR.py
# ===========================================================================
