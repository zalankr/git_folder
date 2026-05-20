"""
============================================================================
 키움증권 REST API - KRX 금현물 분할매매 자동화 코드
 파일명   : GOLD_TR.py
 환경     : Python 3.9+ / AWS EC2 Linux + crontab

 ── 검증 완료 (2026-05-18 실데이터 테스트) ───────────────────────────────
  URI:  시세 /api/dostk/mrkcond | 차트 /api/dostk/chart
        계좌 /api/dostk/acnt    | 주문 /api/dostk/ordr
  종목: M04020000 (금 99.99% 1kg, 1g 단위 거래) — 앞에 'M' 필수

  사용 TR:
    ka50100  금현물 시세정보   → 현재가 계산(전일종가+전일대비), 거래일 판단
    kt50020  금현물 잔고확인   → 보유수량/평단/평가손익/예수금 (핵심)
    kt50021  금현물 예수금     → 주문가능금액(ord_alow_amt)
    kt50075  금현물 미체결조회 → 미체결 잔량 확인
    kt50031  금현물 주문체결조회 → 당일 체결 확인
    kt50000  금현물 매수주문
    kt50001  금현물 매도주문
    kt50003  금현물 취소주문

  주문 규격:
    - body: stk_cd / ord_qty / trde_tp / ord_uv  (계좌번호 불필요)
    - trde_tp: "0"=보통(지정가), "10"=IOC, "20"=FOK  ※ 시장가 없음
    - 호가단위 10원 고정 → 주문단가 끝자리 0 필수 (아니면 857024 오류)
    - 금현물은 지정가만 가능 → 미체결 방지용 슬리피지 적용
      (매수 현재가 +0.5% 후 10원 올림, 매도 -0.5% 후 10원 내림)
    - 응답: ord_no (주문번호)

 key 파일 : /var/autobot/KIS/kiwgold52953897.txt
    1행 = appkey / 2행 = secretkey
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
# 1) API 인증 정보 로드
# ===========================================================================
KEY_FILE_PATH   = "/var/autobot/KIS/kiwgold52953897.txt"
TOKEN_FILE_PATH = "/var/autobot/KIS/kiwgold_token.json"

BASE_URL        = "https://api.kiwoom.com"
GOLD_STOCK_CODE = "M04020000"           # 금 99.99% 1kg (앞에 M 필수)
TOKEN_SAFETY_MARGIN_MIN = 30

# TR 기능별 공통 URI
URI_MRKCOND = "/api/dostk/mrkcond"      # 시세
URI_CHART   = "/api/dostk/chart"        # 차트
URI_ACNT    = "/api/dostk/acnt"         # 계좌
URI_ORDR    = "/api/dostk/ordr"         # 주문

TR_URI_MAP = {
    "ka50100": URI_MRKCOND,
    "kt50020": URI_ACNT, "kt50021": URI_ACNT,
    "kt50031": URI_ACNT, "kt50075": URI_ACNT,
    "kt50000": URI_ORDR, "kt50001": URI_ORDR, "kt50003": URI_ORDR,
}

# appkey/secret 은 load_api_keys() 호출 시 채워짐 (import 시점엔 None)
APP_KEY    = None
APP_SECRET = None

def acquire_singleton():
    """crontab 중복 실행 방지 락 획득. 직접 실행(main)에서만 호출."""
    try:
        return singleton.SingleInstance()
    except singleton.SingleInstanceException:
        TA.send_tele("GOLD: 이미 실행 중입니다.")
        sys.exit(0)

def load_api_keys():
    """키움 appkey/secret 로드 → 전역 APP_KEY/APP_SECRET 설정.
    실패 시 RuntimeError 발생 (sys.exit 아님 → import한 쪽이 잡을 수 있음)."""
    global APP_KEY, APP_SECRET
    if APP_KEY and APP_SECRET:          # 이미 로드됨 → 재사용
        return APP_KEY, APP_SECRET
    try:
        with open(KEY_FILE_PATH, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f.readlines()]
        APP_KEY, APP_SECRET = lines[0], lines[1]
        return APP_KEY, APP_SECRET
    except Exception as e:
        raise RuntimeError(f"GOLD: key 파일 로드 실패: {e}")

# ===========================================================================
# 2) 매매 설정  (상황에 맞게 자유롭게 수정)
# ===========================================================================
# ── 매매 모드 ──────────────────────────────────────────────────────────────
#   "buy"  : 분할매수 / "sell" : 분할매도
MODE = "buy"

# ── 매수 비율 (주문가능 예수금 대비 %) ────────────────────────────────────
#   MODE="buy"일 때만 사용. 100 = 전체 목표금액 기준
BUY_CASH_RATIO = 100        # 단위: %

# ── 매도 비율 (보유수량 대비 %) ──────────────────────────────────────────
#   MODE="sell"일 때만 사용. 100 = 보유수량 전량
SELL_QTY_RATIO = 100        # 단위: %

# ── 분할 구조 ──────────────────────────────────────────────────────────────
#   총 TRADING_DAYS 일 동안, 하루 SPLITS_PER_DAY 회 분할
#   → cron이 하루 SPLITS_PER_DAY 회 호출하며, 매 호출 = 1주문
#   ※ SPLITS_PER_DAY 는 cron 1일 호출 횟수와 반드시 일치시킬 것
TRADING_DAYS   = 3          # 총 매매일 수
SPLITS_PER_DAY = 5          # 1일 분할 횟수 = 1일 cron 호출 횟수

# ── 분할 스케줄 (시, 분) — 현재 시각으로 몇 번째 분할인지 자동 판별 ───────
#   ※ EC2가 UTC로 동작하므로 SPLIT_SCHEDULE / crontab 모두 UTC 기준!
#     UTC = KST - 9시간
#
#   분할     KST(장중)    UTC(코드/crontab)
#   ────────────────────────────────────────
#   1번째    09:13        00:13
#   2번째    10:13        01:13
#   3번째    12:13        03:13
#   4번째    13:13        04:13
#   5번째    15:20        06:20   ※ 정규장 KST 15:30 마감 전
#
#   crontab 권장 (UTC, 평일):
#     13 0 * * 1-5  → UTC 00:13 (KST 09:13, 1번째)
#     13 1 * * 1-5  → UTC 01:13 (KST 10:13, 2번째)
#     13 3 * * 1-5  → UTC 03:13 (KST 12:13, 3번째)
#     13 4 * * 1-5  → UTC 04:13 (KST 13:13, 4번째)
#     20 6 * * 1-5  → UTC 06:20 (KST 15:20, 5번째)
SPLIT_SCHEDULE = [
    (0,  13),   # 1번째 분할  (UTC 00:13 = KST 09:13)
    (1,  13),   # 2번째 분할  (UTC 01:13 = KST 10:13)
    (3,  13),   # 3번째 분할  (UTC 03:13 = KST 12:13)
    (4,  13),   # 4번째 분할  (UTC 04:13 = KST 13:13)
    (6,  20),   # 5번째 분할  (UTC 06:20 = KST 15:20)
]

# ── 분할 인덱스 수동 지정 (None=현재 시각 자동 판별 / 1~N 직접 지정) ──────
SPLIT_INDEX_OVERRIDE = None

# ── 지정가 슬리피지 (금현물은 시장가 없음 → 지정가로 체결 유도) ──────────
LIMIT_SLIPPAGE_BUY  = 0.005     # 매수: 현재가 +0.5%
LIMIT_SLIPPAGE_SELL = 0.005     # 매도: 현재가 -0.5%

# ── 매매구분 (trde_tp): "0"=보통(지정가) / "10"=IOC / "20"=FOK ────────────
TRADE_TYPE = "0"


# ===========================================================================
# 로깅 설정
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
    """키움 응답 문자열(zero-padded, +/- 부호 포함) → 정수."""
    s = str(val).replace(",", "").replace("+", "").strip()
    if not s or s in ("-", ""):
        return 0
    return int(float(s))


def _to_float(val):
    """키움 응답 문자열 → 실수 (수익률 등)."""
    s = str(val).replace(",", "").replace("+", "").replace("%", "").strip()
    if not s or s in ("-", ""):
        return 0.0
    return float(s)


# ── 호가단위 처리 ──────────────────────────────────────────────────────────
#   KRX 금현물 호가단위는 10원 고정. 주문단가 끝자리는 반드시 0이어야 한다.
#   (10원 단위가 아니면 키움 857024 '호가단위를 확인하세요' 오류로 거부됨)
GOLD_TICK_SIZE = 10

def ceil_to_tick(price, tick=GOLD_TICK_SIZE):
    """가격을 호가단위로 올림 (매수 지정가용 — 체결 유리하게)."""
    price = int(price)
    return ((price + tick - 1) // tick) * tick

def floor_to_tick(price, tick=GOLD_TICK_SIZE):
    """가격을 호가단위로 내림 (매도 지정가용 — 체결 유리하게)."""
    price = int(price)
    return (price // tick) * tick


# ===========================================================================
# 4) 인증 / 토큰 관리
# ===========================================================================
def get_access_token(force_new: bool = False):
    """접근토큰을 캐시에서 로드하거나 신규 발급.

    force_new=True 면 캐시를 무시하고 무조건 신규 발급한다.
    (kt50020 등이 8005 '유효하지 않은 토큰' 오류를 낼 때 _post 가 호출)

    ※ 캐시 토큰이 만료시각상으론 유효해 보여도 키움 서버에서 무효화된
      경우가 있다(같은 앱키로 다른 프로세스가 재발급 시 이전 토큰 무효화).
      그 경우 force_new=True 로 강제 재발급해야 한다.
    """
    load_api_keys()                      # APP_KEY/APP_SECRET 보장
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
            log.warning(f"토큰 캐시 로드 실패, 신규 발급 진행: {e}")

    url     = f"{BASE_URL}/oauth2/token"
    headers = {"Content-Type": "application/json;charset=UTF-8"}
    body    = {
        "grant_type": "client_credentials",
        "appkey":     APP_KEY,
        "secretkey":  APP_SECRET,
    }
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        # sys.exit 대신 RuntimeError: import한 쪽(fetch_gold_balance)이 잡을 수 있도록
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


# 8005 등 토큰 무효 오류 감지용 키워드
_TOKEN_ERR_KEYWORDS = ("8005", "토큰", "token", "유효하지 않")


def _api_headers(token, api_id):
    """공통 요청 헤더."""
    return {
        "Content-Type":  "application/json;charset=UTF-8",
        "authorization": f"Bearer {token}",
        "appkey":        APP_KEY,
        "appsecret":     APP_SECRET,
        "api-id":        api_id,
    }


# 현재 유효 토큰 보관 (8005 오류 시 _post 가 재발급하여 갱신)
_CURRENT_TOKEN = None

def _post(token, api_id, body, timeout=10, _token_retry=True):
    """TR에 맞는 URI로 POST → 응답 dict 반환. return_code != 0 이면 예외.

    응답이 8005(토큰 무효) 계열 오류이면 토큰을 강제 재발급하여 1회 재시도한다.
    재발급된 토큰은 모듈 전역 _CURRENT_TOKEN 에 반영되므로, 호출 측은
    이후 get_current_token() 으로 최신 토큰을 다시 받을 수 있다.
    """
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
        # ── 토큰 무효(8005 등) → 강제 재발급 후 1회 재시도 ──
        is_token_err = any(kw in str(msg) for kw in _TOKEN_ERR_KEYWORDS)
        if is_token_err and _token_retry:
            log.warning(f"[{api_id}] 토큰 무효 감지({msg}) → 토큰 강제 재발급 후 재시도")
            new_token = get_access_token(force_new=True)
            _CURRENT_TOKEN = new_token
            # 재시도는 1회만 (_token_retry=False)
            return _post(new_token, api_id, body, timeout=timeout, _token_retry=False)
        raise RuntimeError(f"[{api_id}] return_code={rc} | {msg}")
    return data


def get_current_token():
    """_post 가 8005 재시도 중 재발급했을 수 있는 최신 토큰 반환.
    재발급이 없었으면 None → 호출 측은 기존 토큰을 그대로 쓰면 된다."""
    return _CURRENT_TOKEN


# ===========================================================================
# 5) 거래일 확인
#    ka50100 시세정보 조회 성공 + 당일 거래량(trde_qty) > 0 이면 거래일.
#    휴장일에는 거래량이 0이거나 조회가 실패한다.
#    ※ EC2는 UTC로 동작하지만, 금현물 장중(UTC 00~07시)은 UTC 날짜·요일이
#      KST와 동일하므로 today.weekday() 주말 판정에 문제없음.
#      설령 경계시간에 요일이 어긋나도 2차 거래량 0 체크로 휴장일이 걸러진다.
# ===========================================================================
def is_gold_trading_day(token):
    """오늘이 KRX 금현물 거래일인지 확인."""
    today = datetime.date.today()

    # 1차: 주말이면 즉시 False
    if today.weekday() >= 5:
        log.info(f"거래일 확인: 주말({today}) → 비거래일")
        return False

    # 2차: ka50100 시세 조회 → 당일 거래량으로 판단
    try:
        data = _post(token, "ka50100", {"stk_cd": GOLD_STOCK_CODE})
        volume = _to_int(data.get("trde_qty", 0))
        if volume <= 0:
            log.info(f"거래일 확인: {today} → 당일 거래량 0 → 휴장일 판단")
            return False
        log.info(f"거래일 확인: {today} → 정상 거래일 (거래량 {volume:,})")
        return True
    except Exception as e:
        log.warning(f"거래일 확인 API 실패, 평일 기준 대체: {e}")
        return True   # 평일이면 거래일로 간주 (보수적 운영)


# ===========================================================================
# 6) 시세 조회
# ===========================================================================
def get_gold_current_price(token):
    """금현물 현재가 추정 → 정수(원).

    ka50100 시세정보에는 '현재가' 필드가 없으므로
    전일종가(pred_close_pric) + 전일대비(pred_pre, 부호 포함)로 계산한다.
    """
    data = _post(token, "ka50100", {"stk_cd": GOLD_STOCK_CODE})

    pred_close = _to_int(data.get("pred_close_pric", 0))    # 전일종가
    # 전일대비는 부호 유지 필요 (하락 시 음수)
    pre_raw    = str(data.get("pred_pre", "0")).replace(",", "").strip()
    pred_pre   = int(float(pre_raw)) if pre_raw and pre_raw not in ("-", "") else 0

    price = pred_close + pred_pre
    if price <= 0:
        # 폴백: 전일종가라도 사용
        price = pred_close
    log.info(f"금현물 현재가(추정): {price:,}원 (전일종가 {pred_close:,} {pred_pre:+,})")
    return price


# ===========================================================================
# 7) 계좌 조회
# ===========================================================================
def get_gold_balance(token):
    """금현물 잔고확인(kt50020) → 계좌 종합 dict.

    반환 키:
      deposit       예수금(원)               ← net_entr (정산반영 순예수금)
      eval_amt      금 평가금액(원)          ← gold_acnt_evlt_prst[].est_amt
      total_amt     계좌 총평가금(원)        ← eval_amt + deposit (파생)
      hold_qty      보유수량(g)              ← real_qty
      avg_price     평균매입단가(원/g)       ← avg_prc
      cur_price     현재가(원/g)             ← cur_prc
      profit_loss   평가손익(원)             ← est_lspft
      return_rate   수익률(%)                ← est_ratio
      sellable_qty  매도가능수량(g)          ← able_qty
      deposit_raw   미정산 예수금(원)        ← tot_entr (참조용, 사용 안 함)
    보유 종목이 없으면 수량/단가/손익은 0.

    ※ 평가금 산출 방식 (실데이터 + 매수체결금액 교차검증, 2026-05-19):
      금 평가금 = kt50020 종목배열의 est_amt. 검증 근거:
        - 오늘 28g 매수 체결금액(kt50021 buy_exct_amt) = 6,144,136원
          → 1g 매수단가 ≈ 219,400원 (kt50031 체결가 cntr_uv 219,560 과 일치)
        - 보유 56g × 약 219,000원/g ≈ 1,228만원 → est_amt(12,147,453) 와 일치

    ※ 예수금 필드 선택 (중요 — 이중계산 방지):
      kt50020 의 예수금 필드는 tot_entr 와 net_entr 두 가지다.
        - tot_entr(24,716,370): 당일 매수 체결대금이 아직 차감 안 된 '미정산 예수금'
        - net_entr(18,572,234): 당일 매수 체결분이 차감된 '정산반영 순예수금' ★
      tot_entr 를 쓰면 당일 매수분이 금 평가금(est_amt)과 예수금에 이중 계산되어
      총잔고가 매수대금(6,144,136)만큼 부풀려진다.
        tot_entr 사용 시: 금 12,147,453 + 예수금 24,716,370 = 36,863,823 ❌
        net_entr 사용 시: 금 12,147,453 + 예수금 18,572,234 = 30,719,687 ✅
      → net_entr 를 예수금으로 사용한다 (KIS 한국주식 D+2 정산 반영과 동일 원칙).
      net_entr 가 비정상(0)이면 kt50021 의 prsm_entra(추정예수금)로 보강한다.
      ※ prsm_entra 는 kt50020 응답에는 없고 kt50021 응답에만 존재한다.
    """
    data = _post(token, "kt50020", {})

    # 예수금: net_entr(kt50020, 정산반영 순예수금) 우선. 0이면 kt50021 보강.
    deposit     = _to_int(data.get("net_entr", 0))        # 정산반영 순예수금 (정답)
    deposit_raw = _to_int(data.get("tot_entr", 0))        # 미정산 예수금 (참조용)
    if deposit <= 0:
        # net_entr 미제공/0 → kt50021 의 prsm_entra(추정예수금)로 보강
        try:
            dep_data = _post(token, "kt50021", {})
            deposit = _to_int(dep_data.get("prsm_entra", 0))
            if deposit <= 0:
                deposit = _to_int(dep_data.get("prsm_pymn_alow_amt", 0))
            if deposit <= 0:
                # 최후 폴백: 미정산예수금 - 당일매수체결금
                buy_exct = _to_int(dep_data.get("buy_exct_amt", 0))
                deposit = max(deposit_raw - buy_exct, 0)
            log.warning(f"kt50020 net_entr 없음 → kt50021 로 예수금 보강: {deposit:,}원")
        except Exception as e:
            log.warning(f"kt50021 예수금 보강 실패, tot_entr 사용: {e}")
            deposit = deposit_raw

    result = {
        "deposit":          deposit,
        "deposit_raw":      deposit_raw,    # 미정산 예수금 (참조용)
        "eval_amt":         0,
        "total_amt":        0,
        "hold_qty":         0,
        "avg_price":        0,
        "cur_price":        0,
        "profit_loss":      0,
        "return_rate":      0.0,
        "sellable_qty":     0,
        "tot_dep_amt_raw":  _to_int(data.get("tot_dep_amt", 0)),  # 참조용(미사용)
    }

    for item in data.get("gold_acnt_evlt_prst", []) or []:
        if item.get("stk_cd") == GOLD_STOCK_CODE:
            result["hold_qty"]     = _to_int(item.get("real_qty", 0))
            result["avg_price"]    = _to_int(item.get("avg_prc", 0))
            result["cur_price"]    = _to_int(item.get("cur_prc", 0))
            result["eval_amt"]     = _to_int(item.get("est_amt", 0))   # ★ 금 평가금 정답
            # 평가손익은 부호 유지
            pl_raw = str(item.get("est_lspft", "0")).replace(",", "").replace("+", "").strip()
            result["profit_loss"]  = int(float(pl_raw)) if pl_raw and pl_raw != "-" else 0
            rr_raw = str(item.get("est_ratio", "0")).replace(",", "").replace("+", "").replace("%", "").strip()
            result["return_rate"]  = float(rr_raw) if rr_raw and rr_raw != "-" else 0.0
            result["sellable_qty"] = _to_int(item.get("able_qty", 0))
            break

    # ── 금 평가금이 비어있으면 cur_prc × hold_qty 로 폴백 ──
    if result["eval_amt"] <= 0 and result["hold_qty"] > 0:
        if result["cur_price"] <= 0:
            try:
                result["cur_price"] = get_gold_current_price(token)
            except Exception as e:
                log.warning(f"현재가 보강 실패(get_gold_current_price): {e}")
        result["eval_amt"] = result["cur_price"] * result["hold_qty"]
        log.warning(
            f"kt50020 est_amt=0 → cur_prc×수량으로 폴백 산출: "
            f"{result['eval_amt']:,}원"
        )

    # ── 계좌 총평가금 = 금 평가금 + 예수금(정산반영) ──
    result["total_amt"] = result["eval_amt"] + deposit

    log.info(
        f"잔고: 보유 {result['hold_qty']}g / 매도가능 {result['sellable_qty']}g / "
        f"현재가 {result['cur_price']:,}원/g / 금평가금 {result['eval_amt']:,}원 / "
        f"예수금 {result['deposit']:,}원(정산반영) / 총평가금 {result['total_amt']:,}원 / "
        f"손익 {result['profit_loss']:,}원 ({result['return_rate']:.2f}%) "
        f"[미정산예수금 tot_entr={result['deposit_raw']:,}원·미사용]"
    )
    return result


def get_orderable_cash(token):
    """금현물 예수금(kt50021) → 주문가능금액(원). 실패 시 잔고의 예수금으로 폴백."""
    try:
        data = _post(token, "kt50021", {})
        # ord_alow_amt(주문가능금액)이 가장 정확
        cash = _to_int(data.get("ord_alow_amt", 0))
        if cash <= 0:
            cash = _to_int(data.get("entra", 0))
        log.info(f"주문가능금액: {cash:,}원")
        return cash
    except Exception as e:
        log.warning(f"예수금 조회 실패, 잔고 예수금으로 폴백: {e}")
        return get_gold_balance(token)["deposit"]


def get_today_execution(token):
    """금현물 주문체결조회(kt50031) → 당일 체결 합계 dict.

    반환: {"filled_qty": 체결수량합, "filled_amt": 체결금액합, "count": 주문건수}
    """
    today = datetime.date.today().strftime("%Y%m%d")
    try:
        data = _post(token, "kt50031", {
            "qry_tp":       "1",        # 1=주문순(전체) ※ 0은 무효값
            "stk_bond_tp":  "0",
            "sell_tp":      "0",
            "dmst_stex_tp": "KRX",
            "ord_dt":       today,
            "stk_cd":       GOLD_STOCK_CODE,
            "fr_ord_no":    "",
        })
    except Exception as e:
        log.warning(f"주문체결조회 실패: {e}")
        return {"filled_qty": 0, "filled_amt": 0, "count": 0}

    filled_qty = 0
    filled_amt = 0
    count      = 0
    for item in data.get("acnt_ord_cntr_prps_dtl", []) or []:
        # 빈 더미 레코드 제외 (ord_no="0000000" 또는 stk_cd 빈 값)
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
    """금현물 미체결조회(kt50075) → 미체결 잔량 합계(g)."""
    today = datetime.date.today().strftime("%Y%m%d")
    try:
        data = _post(token, "kt50075", {
            "ord_dt":       today,
            "mrkt_deal_tp": "0",
            "stk_bond_tp":  "0",
            "sell_tp":      "0",
            "qry_tp":       "1",        # 1=주문순
            "stk_cd":       GOLD_STOCK_CODE,
            "fr_ord_no":    "",
            "dmst_stex_tp": "KRX",
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
# 8) 주문 API
# ===========================================================================
def place_gold_order(token, side, qty, price):
    """금현물 주문 실행.

    side  : "buy"(kt50000) / "sell"(kt50001)
    qty   : 주문수량(g)
    price : 지정가(원)
    반환  : 주문번호 문자열 or None
    """
    if qty <= 0:
        log.warning("주문수량 0 이하 → 주문 건너뜀")
        return None

    api_id = "kt50000" if side == "buy" else "kt50001"
    body = {
        "stk_cd":  GOLD_STOCK_CODE,
        "ord_qty": str(qty),
        "ord_uv":  str(price),
        "trde_tp": TRADE_TYPE,      # "0"=보통(지정가)
    }
    data   = _post(token, api_id, body)
    ord_no = data.get("ord_no", "")

    if ord_no:
        log.info(f"[{side.upper()}] 주문 완료 — {qty}g @ {price:,}원 / 주문번호 {ord_no}")
    else:
        log.warning(f"[{side.upper()}] 주문 응답에 주문번호 없음: {data}")
    return ord_no if ord_no else None


def cancel_gold_order(token, ord_no, qty=0):
    """금현물 취소주문(kt50003). qty=0 이면 잔량 전량 취소."""
    body = {
        "orig_ord_no": str(ord_no),
        "stk_cd":      GOLD_STOCK_CODE,
        "cncl_qty":    str(qty),
    }
    try:
        data    = _post(token, "kt50003", body)
        cncl_no = data.get("ord_no", "")
        log.info(f"취소주문 완료 — 원주문 {ord_no} / 취소번호 {cncl_no}")
        return cncl_no if cncl_no else None
    except Exception as e:
        log.error(f"취소주문 실패 (원주문 {ord_no}): {e}")
        return None


# ===========================================================================
# 9) 분할 계산
# ===========================================================================
def split_quantities(total_qty, splits):
    """전체 수량을 splits 회로 분할 (나머지는 앞쪽 분할부터 1g씩 배분)."""
    if splits <= 0:
        raise ValueError("splits는 1 이상이어야 합니다.")
    total_qty = max(total_qty, 0)
    base      = total_qty // splits
    remainder = total_qty % splits
    return [base + (1 if i < remainder else 0) for i in range(splits)]


def get_today_split_index():
    """현재 시각으로 오늘 몇 번째 분할인지 판별 (1-base)."""
    if SPLIT_INDEX_OVERRIDE is not None:
        log.info(f"분할 인덱스 수동 지정: {SPLIT_INDEX_OVERRIDE}")
        return SPLIT_INDEX_OVERRIDE

    now     = datetime.datetime.now()
    now_min = now.hour * 60 + now.minute
    best_idx, best_diff = None, None
    for idx, (h, m) in enumerate(SPLIT_SCHEDULE[:SPLITS_PER_DAY], start=1):
        diff = abs(now_min - (h * 60 + m))
        if best_diff is None or diff < best_diff:
            best_idx, best_diff = idx, diff

    if best_diff is not None and best_diff > 30:
        log.warning(
            f"현재시각이 분할 스케줄과 {best_diff}분 차이 → "
            f"{best_idx}번째 분할로 처리 (확인 필요)"
        )
    log.info(f"오늘 분할 인덱스: {best_idx} / {SPLITS_PER_DAY}")
    return best_idx


# ===========================================================================
# 10) 텔레그램 헬퍼
# ===========================================================================
def _fmt_balance(bal):
    """잔고 dict → 텔레그램 출력 라인 리스트.

    cur_price/avg_price 는 1g 기준 정상 시세(매수체결금액으로 검증됨).
    예수금은 prsm_entra(당일 매수 정산반영) 기준 — tot_entr 사용 시
    당일 매수분이 금·현금 이중계산되므로 prsm_entra 가 정답.
    금평가금 = est_amt, 총평가금 = est_amt + 예수금(정산반영).
    """
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
# 11) 매수 로직 — 호출 1회 = 주문 1회
# ===========================================================================
def run_buy(token, split_index):
    """분할매수 1회 실행 → (메시지 리스트, 주문번호 or None).

    1회 주문금액 = (주문가능금액 × BUY_CASH_RATIO%) / SPLITS_PER_DAY
    ※ 매 호출 시 예수금을 재조회하므로, 일자가 바뀌어도 자연스럽게 분할됨.
       하루 안에서는 SPLITS_PER_DAY 등분.
    """
    msg   = []
    cash  = get_orderable_cash(token)
    price = get_gold_current_price(token)

    target_cash = int(cash * BUY_CASH_RATIO / 100)
    if target_cash <= 0 or price <= 0:
        msg.append("GOLD: 매수가능금액 또는 현재가 0 → 매수 중단")
        return msg, None

    # 이번 분할 배정금액 = 남은 예수금 / (남은 분할 횟수)
    #   split_index 가 진행될수록 직전 분할이 이미 소진되어 cash가 줄어듦
    remaining_splits = SPLITS_PER_DAY - (split_index - 1)
    if remaining_splits < 1:
        remaining_splits = 1
    this_cash = target_cash // remaining_splits

    # 지정가 = 현재가 + 슬리피지 → 10원 호가단위로 올림
    order_price = ceil_to_tick(price * (1 + LIMIT_SLIPPAGE_BUY))

    this_qty = this_cash // order_price if order_price > 0 else 0
    if this_qty <= 0:
        msg.append(
            f"GOLD: {split_index}회차 매수수량 0g → 건너뜀 "
            f"(배정금액 {this_cash:,}원 / 지정가 {order_price:,}원)"
        )
        return msg, None

    msg.append(
        f"[매수] {split_index}/{SPLITS_PER_DAY}회차 | "
        f"배정금액 {this_cash:,}원 | 지정가 {order_price:,}원 | 수량 {this_qty}g"
    )

    ord_no = place_gold_order(token, "buy", this_qty, order_price)
    msg.append(
        f"주문 접수 완료 | 주문번호: {ord_no}" if ord_no
        else "GOLD: 매수 주문 응답 이상 (주문번호 없음)"
    )
    return msg, ord_no


# ===========================================================================
# 12) 매도 로직 — 호출 1회 = 주문 1회
# ===========================================================================
def run_sell(token, split_index):
    """분할매도 1회 실행 → (메시지 리스트, 주문번호 or None).

    1회 주문수량 = (매도가능수량 × SELL_QTY_RATIO%) / (남은 분할 횟수)
    ※ 매 호출 시 보유/매도가능수량을 재조회 → 부분체결 자연 보정.
    """
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

    # 이번 분할 수량 = 남은 목표 / 남은 분할 횟수
    remaining_splits = SPLITS_PER_DAY - (split_index - 1)
    if remaining_splits < 1:
        remaining_splits = 1
    this_qty = target_qty // remaining_splits
    if this_qty < 1:
        this_qty = target_qty       # 잔량이 분할 수보다 적으면 당일 전량

    # 매도가능수량으로 캡핑 (T+n 미정산분 매도 실패 방지)
    this_qty = min(this_qty, sellable_qty)
    if this_qty <= 0:
        msg.append(
            f"GOLD: 매도가능수량 0g → 건너뜀 "
            f"(보유 {hold_qty}g / 매도가능 {sellable_qty}g)"
        )
        return msg, None

    # 지정가 = 현재가 - 슬리피지 → 10원 호가단위로 내림
    order_price = floor_to_tick(price * (1 - LIMIT_SLIPPAGE_SELL))

    msg.append(
        f"[매도] {split_index}/{SPLITS_PER_DAY}회차 | "
        f"보유 {hold_qty}g / 매도가능 {sellable_qty}g | "
        f"이번 {this_qty}g | 지정가 {order_price:,}원"
    )

    ord_no = place_gold_order(token, "sell", this_qty, order_price)
    msg.append(
        f"주문 접수 완료 | 주문번호: {ord_no}" if ord_no
        else "GOLD: 매도 주문 응답 이상 (주문번호 없음)"
    )
    return msg, ord_no


# ===========================================================================
# 13) 메인 실행
# ===========================================================================
def main():
    me = acquire_singleton()             # ← 추가: cron 실행 시에만 락 획득
    now_str  = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mode_kor = "매수" if MODE == "buy" else "매도"

    log.info("=" * 60)
    log.info(
        f"KRX 금현물 자동매매 시작 | MODE={MODE} | "
        f"매매일수={TRADING_DAYS}일 | 1일분할={SPLITS_PER_DAY}회"
    )

    # ── 설정값 유효성 검사
    if MODE not in ("buy", "sell"):
        TA.send_tele(f"GOLD: MODE 설정 오류 ({MODE}). buy/sell 만 허용 → 종료")
        sys.exit(1)
    if len(SPLIT_SCHEDULE) < SPLITS_PER_DAY:
        TA.send_tele("GOLD: SPLIT_SCHEDULE 개수가 SPLITS_PER_DAY보다 적습니다 → 종료")
        sys.exit(1)

    try:
        # ── 토큰 발급
        token = get_access_token()

        # ── 거래일 확인
        if not is_gold_trading_day(token):
            TA.send_tele(f"GOLD: 거래일이 아닙니다 ({datetime.date.today()}) → 종료")
            sys.exit(0)

        # ── 분할 인덱스 결정
        split_index = get_today_split_index()

        # ── 하루 첫 번째 분할: 매매 시작 알림
        if split_index == 1:
            TA.send_tele([
                "━━━━━━━━━━━━━━━━━━━━━━━━",
                "🥇 KRX 금현물 자동매매 시작",
                f"일시  : {now_str}",
                f"모드  : {mode_kor} ({SPLITS_PER_DAY}회 분할 / {TRADING_DAYS}일간)",
                f"종목  : 금 99.99% 1kg ({GOLD_STOCK_CODE})",
                "━━━━━━━━━━━━━━━━━━━━━━━━",
            ])

        # ── 매매 실행
        if MODE == "buy":
            order_msg, ord_no = run_buy(token, split_index)
        else:
            order_msg, ord_no = run_sell(token, split_index)

        # ── 5초 대기 후 당일 체결 확인
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

        # ── 잔고 조회
        bal = get_gold_balance(token)

        # ── 하루 마지막 분할: 일일 종료 요약 알림
        if split_index == SPLITS_PER_DAY:
            TA.send_tele(
                [
                    "━━━━━━━━━━━━━━━━━━━━━━━━",
                    "🥇 KRX 금현물 일일 매매 완료",
                    f"일시  : {now_str}",
                    f"모드  : {mode_kor}",
                    "━━━━━━━━━━━━━━━━━━━━━━━━",
                ]
                + order_msg
                + ["─────────────────────────"]
                + _fmt_balance(bal)
                + ["━━━━━━━━━━━━━━━━━━━━━━━━"]
            )
        else:
            # 중간 분할: 주문 결과만 간략 전송
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
# [ crontab 설정 예시 ]  (AWS EC2 Linux — UTC 기준!)
#   $ crontab -e
#
#   ※ EC2 시스템 시간대는 UTC 유지. crontab 시각도 UTC로 작성.
#     UTC = KST - 9시간
#
#   # KRX 금현물 분할 매매 - 평일(월~금) 1일 5회 분할 (UTC 시각)
#   13 0 * * 1-5  /usr/bin/python3 /var/autobot/TR_GOLD/GOLD_TR.py   # KST 09:13
#   13 1 * * 1-5  /usr/bin/python3 /var/autobot/TR_GOLD/GOLD_TR.py   # KST 10:13
#   13 3 * * 1-5  /usr/bin/python3 /var/autobot/TR_GOLD/GOLD_TR.py   # KST 12:13
#   13 4 * * 1-5  /usr/bin/python3 /var/autobot/TR_GOLD/GOLD_TR.py   # KST 13:13
#   20 6 * * 1-5  /usr/bin/python3 /var/autobot/TR_GOLD/GOLD_TR.py   # KST 15:20
#
#   ※ SPLIT_SCHEDULE 의 (시,분) 5개와 위 cron 시각 5개를 일치시킬 것 (둘 다 UTC)
#   ※ crontab의 요일(1-5)도 UTC 기준. 한국 월~금 장중 시간대(UTC 00~07시)는
#     UTC 요일과 KST 요일이 동일하므로 1-5 그대로 사용 가능.
#   ※ 며칠간만 매매 시 날짜 필드로 제한 (날짜도 UTC 기준):
#       13 0 19-21 * 1-5  → 매월 19~21일 평일 KST 09:13 실행
# ===========================================================================
