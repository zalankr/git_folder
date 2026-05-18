"""
============================================================================
 키움증권 REST API - KRX 금현물 분할매매 코드
 파일명   : GOLD_TR.py
 환경     : Python 3.9+ / AWS EC2 Linux + crontab

 종목코드 :
    * 04020000  : 금 99.99K (1g 단위 거래)
    * 04020100  : 미니금 (100g 단위)

 key 파일 : /var/autobot/KIS/kiwgold52953897.txt
    1행 = appkey
    2행 = secretkey

 토큰 캐시: /var/autobot/KIS/kiwgold_token.json

 ── 실제 TR ID 매핑 ──────────────────────────────────────────────────────
  [시세/조회]
    ka50100  금현물 시세정보           ← 현재가, 거래일 확인
    ka50101  금현물 호가
    ka50087  금현물 예상체결
    ka50010  금현물 체결추이
    ka50012  금현물 일별추이
    ka52301  금현물 투자자현황
  [차트]
    ka50079  금현물 틱차트
    ka50080  금현물 분봉차트
    ka50081  금현물 일봉차트
    ka50082  금현물 주봉차트
    ka50083  금현물 월봉차트
    ka50091  금현물 당일틱차트
    ka50092  금현물 당일분봉차트
  [주문]
    kt50000  금현물 매수주문           ← run_buy()
    kt50001  금현물 매도주문           ← run_sell()
    kt50002  금현물 정정주문
    kt50003  금현물 취소주문           ← cancel_gold_order()
  [계좌/체결]
    kt50020  금현물 잔고확인           ← get_gold_holding()
    kt50021  금현물 예수금             ← get_deposit()
    kt50030  금현물 주문체결전체조회
    kt50031  금현물 주문체결조회       ← get_order_execution()
    kt50032  금현물 거래내역조회
    kt50075  금현물 미체결조회         ← get_gold_unexecuted()
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
# 중복 실행 방지 (crontab 겹침 방지)
# ===========================================================================
try:
    me = singleton.SingleInstance()
except singleton.SingleInstanceException:
    TA.send_tele("GOLD: 이미 실행 중입니다.")
    sys.exit(0)


# ===========================================================================
# 1) API 인증 정보 로드  (key 파일에서 읽기)
# ===========================================================================
KEY_FILE_PATH   = "/var/autobot/KIS/kiwgold52953897.txt"
TOKEN_FILE_PATH = "/var/autobot/KIS/kiwgold_token.json"
ACCOUNT_NO      = "5295389780"          # 계좌번호 10자리 (하이픈 제거)

try:
    with open(KEY_FILE_PATH, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines()]
    APP_KEY    = lines[0]
    APP_SECRET = lines[1]
except Exception as e:
    print(f"GOLD: key 파일 로드 실패 → 종료 ({e})")
    try:
        TA.send_tele(f"GOLD: key 파일 로드 실패 → 종료 ({e})")
    except Exception:
        pass
    sys.exit(1)

# 키움 REST API 실전 도메인
BASE_URL = "https://api.kiwoom.com"

# KRX 금현물 종목코드
GOLD_STOCK_CODE = "04020000"            # 금 99.99K (1g 단위)

# 토큰 캐시 만료 안전 마진(분)
TOKEN_SAFETY_MARGIN_MIN = 30


# ===========================================================================
# 2) 매매 설정
# ===========================================================================
# ── 매매 모드 ──────────────────────────────────────────────────────────────
#   "buy"  : 분할매수
#   "sell" : 분할매도
MODE = "buy"

# ── 매수 비율 (주문가능 예수금 대비 %) ────────────────────────────────────
#   MODE="buy"일 때만 사용. 100 = 예수금 전액
BUY_CASH_RATIO = 100        # 단위: %

# ── 매도 비율 (보유수량 대비 %) ──────────────────────────────────────────
#   MODE="sell"일 때만 사용. 100 = 보유수량 전량
SELL_QTY_RATIO = 100        # 단위: %

# ── 총 매매일 수 (crontab 날짜 제어 기준, 표시용) ─────────────────────────
TRADING_DAYS = 3

# ── 1일 분할 횟수 ──────────────────────────────────────────────────────────
#   crontab 호출 횟수와 반드시 일치시킬 것
SPLITS_PER_DAY = 5

# ── 분할 스케줄 (시, 분) ──────────────────────────────────────────────────
#   crontab 권장 스케줄 (평일 KST):
#     13 9  * * 1-5  →  09:13  (1번째)
#     13 10 * * 1-5  →  10:13  (2번째)
#     13 12 * * 1-5  →  12:13  (3번째)
#     13 14 * * 1-5  →  14:13  (4번째)
#     13 15 * * 1-5  →  15:13  (5번째)
SPLIT_SCHEDULE = [
    (9,  13),   # 1번째 분할
    (10, 13),   # 2번째 분할
    (12, 13),   # 3번째 분할
    (14, 13),   # 4번째 분할
    (15, 13),   # 5번째 분할
]

# ── 분할 인덱스 수동 지정 ────────────────────────────────────────────────
#   None = 현재 시각으로 자동 판별 / 1~5 정수 직접 지정 가능
SPLIT_INDEX_OVERRIDE = None

# ── 주문 호가 구분 ────────────────────────────────────────────────────────
#   금현물은 지정가 위주
ORDER_PRICE_TYPE = "limit"   # "limit"=지정가, "market"=시장가
LIMIT_SLIPPAGE   = 0.005     # 지정가 슬리피지 (매수 +0.5%, 매도 -0.5%)


# ===========================================================================
# 로깅 설정
# ===========================================================================
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(
            os.path.join(LOG_DIR, "krx_gold_trading.log"),
            encoding="utf-8"
        ),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("krx_gold")


# ===========================================================================
# 3) 인증 / 토큰 관리
# ===========================================================================
def get_access_token():
    """접근토큰을 캐시에서 로드하거나 신규 발급한다."""
    if os.path.exists(TOKEN_FILE_PATH):
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
        TA.send_tele(f"GOLD: 토큰 발급 실패 → 종료 ({e})")
        sys.exit(1)

    token = data.get("token") or data.get("access_token")
    if not token:
        TA.send_tele(f"GOLD: 토큰 발급 응답 오류 → 종료 ({data})")
        sys.exit(1)

    if data.get("expires_dt"):
        expires_at = datetime.datetime.strptime(data["expires_dt"], "%Y%m%d%H%M%S")
    else:
        expires_in = int(data.get("expires_in", 86400))
        expires_at = datetime.datetime.now() + datetime.timedelta(seconds=expires_in)

    os.makedirs(os.path.dirname(TOKEN_FILE_PATH), exist_ok=True)
    with open(TOKEN_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {"access_token": token, "expires_at": expires_at.isoformat()},
            f, ensure_ascii=False, indent=2
        )
    log.info("접근토큰 신규 발급 완료")
    return token


def _api_headers(token, api_id):
    """공통 요청 헤더 생성."""
    return {
        "Content-Type":  "application/json;charset=UTF-8",
        "authorization": f"Bearer {token}",
        "appkey":        APP_KEY,
        "appsecret":     APP_SECRET,
        "api-id":        api_id,
    }


def _post(token, api_id, body, timeout=10):
    """POST 공통 래퍼 — 응답 dict 반환, 실패 시 예외."""
    url  = f"{BASE_URL}/api/dostk/goldstk"
    resp = requests.post(
        url,
        headers=_api_headers(token, api_id),
        json=body,
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


# ===========================================================================
# 4) 거래일 확인
#    금현물 시세정보(ka50100)의 시가(stck_oprc)가 0이면 휴장으로 판단.
#    API 실패 시 평일(월~금) 기준으로 대체.
# ===========================================================================
def is_gold_trading_day(token):
    """오늘이 KRX 금현물 거래일인지 확인한다."""
    today = datetime.date.today()

    # 1차: 주말이면 즉시 False
    if today.weekday() >= 5:
        log.info(f"거래일 확인: 주말({today}) → 비거래일")
        return False

    # 2차: ka50100 시세정보 조회 → 시가가 0이면 휴장
    try:
        data = _post(token, "ka50100", {"stk_cd": GOLD_STOCK_CODE})
        open_price_str = str(data.get("stck_oprc", "0")).replace(",", "").strip()
        if open_price_str in ("", "0"):
            log.info(f"거래일 확인: {today} → 시가 0 → 휴장일 판단")
            return False
        log.info(f"거래일 확인: {today} → 정상 거래일 (시가: {open_price_str}원)")
        return True
    except Exception as e:
        log.warning(f"거래일 확인 API 실패, 평일 기준 대체: {e}")
        return True   # 평일이면 거래일로 간주


# ===========================================================================
# 5) 조회 API  (실제 TR ID 적용)
# ===========================================================================

def get_gold_current_price(token):
    """금현물 시세정보 (ka50100) → 현재가 정수(원) 반환."""
    data = _post(token, "ka50100", {"stk_cd": GOLD_STOCK_CODE})
    # stck_prpr: 현재가 — 명세서에서 실제 필드명 확인 후 교체
    raw = str(data.get("stck_prpr", "0")).replace(",", "").replace("+", "").strip()
    price = int(float(raw)) if raw else 0
    log.info(f"금현물 현재가: {price:,}원")
    return price


def get_deposit(token):
    """금현물 예수금 (kt50021) → 주문가능금액 정수(원) 반환."""
    data = _post(token, "kt50021", {"acnt_no": ACCOUNT_NO})
    # ord_psbl_amt: 주문가능금액 — 명세서 확인 후 교체
    raw  = str(data.get("ord_psbl_amt", "0")).replace(",", "").strip()
    cash = int(float(raw)) if raw else 0
    log.info(f"주문가능 예수금: {cash:,}원")
    return cash


def get_gold_holding(token):
    """금현물 잔고확인 (kt50020) → 잔고 dict 반환.

    반환 키: hold_qty, avg_price, eval_amt, profit_loss, return_rate
    보유 없으면 모두 0.
    """
    data = _post(token, "kt50020", {"acnt_no": ACCOUNT_NO, "stk_cd": GOLD_STOCK_CODE})

    def _int(v):
        return int(float(str(v).replace(",", "").replace("+", "").strip() or "0"))

    def _float(v):
        return float(str(v).replace(",", "").replace("+", "").replace("%", "").strip() or "0")

    # 명세서 확인 후 실제 응답 필드명으로 교체
    # rmnd_qty  : 잔고수량(g)
    # avg_prc   : 평균단가
    # evlt_amt  : 평가금액
    # evlt_pl   : 평가손익
    # prft_rt   : 수익률(%)
    result = {
        "hold_qty":    _int(data.get("rmnd_qty",  0)),
        "avg_price":   _int(data.get("avg_prc",   0)),
        "eval_amt":    _int(data.get("evlt_amt",  0)),
        "profit_loss": _int(data.get("evlt_pl",   0)),
        "return_rate": _float(data.get("prft_rt", 0)),
    }
    log.info(
        f"금현물 잔고: {result['hold_qty']}g / 평균단가 {result['avg_price']:,}원 / "
        f"평가손익 {result['profit_loss']:,}원 ({result['return_rate']:.2f}%)"
    )
    return result


def get_gold_unexecuted(token):
    """금현물 미체결 조회 (kt50075) → 미체결 리스트 반환."""
    try:
        data = _post(token, "kt50075", {"acnt_no": ACCOUNT_NO, "stk_cd": GOLD_STOCK_CODE})
        return data.get("list", [])
    except Exception as e:
        log.warning(f"미체결 조회 실패: {e}")
        return []


def get_order_execution(token, ord_no):
    """금현물 주문체결조회 (kt50031) → 체결정보 dict 반환. 실패 시 None."""
    try:
        data = _post(token, "kt50031", {
            "acnt_no": ACCOUNT_NO,
            "ord_no":  str(ord_no),
            "stk_cd":  GOLD_STOCK_CODE,
        })
        # 명세서 확인 후 실제 응답 필드명으로 교체
        # ccld_qty: 체결수량, ccld_prc: 체결단가, ccld_amt: 체결금액, ord_stat: 주문상태
        return {
            "ord_no": str(ord_no),
            "qty":    int(float(str(data.get("ccld_qty", "0")).replace(",", "") or "0")),
            "price":  int(float(str(data.get("ccld_prc", "0")).replace(",", "") or "0")),
            "amount": int(float(str(data.get("ccld_amt", "0")).replace(",", "") or "0")),
            "status": str(data.get("ord_stat", "")),
        }
    except Exception as e:
        log.warning(f"주문체결 조회 실패 (주문번호 {ord_no}): {e}")
        return None


# ===========================================================================
# 6) 주문 API  (실제 TR ID 적용)
# ===========================================================================

def place_gold_order(token, side, qty, price):
    """KRX 금현물 주문 실행.

    side  : "buy"(kt50000) 또는 "sell"(kt50001)
    qty   : 주문수량 (g)
    price : 지정가(원). 시장가일 경우 0.
    반환  : 주문번호 문자열 or None
    """
    if qty <= 0:
        log.warning("주문수량 0 이하 → 주문 건너뜀")
        return None

    api_id = "kt50000" if side == "buy" else "kt50001"

    # 호가구분: 00=지정가, 03=시장가 (명세서 확인)
    if ORDER_PRICE_TYPE == "market":
        trde_tp   = "03"
        ord_price = "0"
    else:
        trde_tp   = "00"
        ord_price = str(price)

    body = {
        "acnt_no": ACCOUNT_NO,
        "stk_cd":  GOLD_STOCK_CODE,
        "ord_qty": str(qty),
        "ord_uv":  ord_price,
        "trde_tp": trde_tp,
    }

    data   = _post(token, api_id, body)
    ord_no = data.get("ord_no", "")

    if ord_no:
        log.info(
            f"[{side.upper()}] 주문 완료 — "
            f"수량 {qty}g / 단가 {price:,}원 / 주문번호 {ord_no}"
        )
    else:
        log.warning(f"[{side.upper()}] 주문 응답에 주문번호 없음: {data}")

    return ord_no if ord_no else None


def cancel_gold_order(token, ord_no, qty=0):
    """금현물 취소주문 (kt50003).

    ord_no : 취소할 원주문번호
    qty    : 취소수량 (0이면 전량 취소)
    반환   : 취소 주문번호 or None
    """
    body = {
        "acnt_no":    ACCOUNT_NO,
        "stk_cd":     GOLD_STOCK_CODE,
        "org_ord_no": str(ord_no),
        "cncl_qty":   str(qty),
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
# 7) 분할 수량 계산
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

    now         = datetime.datetime.now()
    now_min     = now.hour * 60 + now.minute
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
# 8) 텔레그램 헬퍼
# ===========================================================================
def _fmt_holding(holding, deposit):
    """잔고 dict + 예수금 → 텔레그램 출력 라인 리스트."""
    if holding is None:
        return ["GOLD: 잔고 조회 실패"]
    return [
        f"보유수량   : {holding['hold_qty']}g",
        f"평균단가   : {holding['avg_price']:,}원",
        f"평가금액   : {holding['eval_amt']:,}원",
        f"평가손익   : {holding['profit_loss']:,}원",
        f"수익률     : {holding['return_rate']:.2f}%",
        f"예수금     : {deposit:,}원",
    ]


# ===========================================================================
# 9) 매수 로직
# ===========================================================================
def run_buy(token, split_index):
    """분할매수 1회 실행 → (메시지 리스트, 주문번호 or None) 반환."""
    msg   = []
    cash  = get_deposit(token)
    price = get_gold_current_price(token)

    target_cash = int(cash * BUY_CASH_RATIO / 100)
    if target_cash <= 0 or price <= 0:
        msg.append("GOLD: 매수 가능 금액 또는 현재가 0 → 매수 중단")
        return msg, None

    # 이번 분할 배정 금액
    per_split = target_cash // SPLITS_PER_DAY
    this_cash = (target_cash - per_split * (SPLITS_PER_DAY - 1)
                 if split_index == SPLITS_PER_DAY else per_split)

    # 주문단가
    if ORDER_PRICE_TYPE == "market":
        order_price, ref_price = 0, price
    else:
        order_price = int(price * (1 + LIMIT_SLIPPAGE))
        ref_price   = order_price

    this_qty = this_cash // ref_price if ref_price > 0 else 0
    if this_qty <= 0:
        msg.append(
            f"GOLD: {split_index}회차 매수수량 0g → 건너뜀 "
            f"(배정금액 {this_cash:,}원 / 현재가 {price:,}원)"
        )
        return msg, None

    msg.append(
        f"[매수] {split_index}/{SPLITS_PER_DAY}회차 | "
        f"배정금액 {this_cash:,}원 | 단가 {order_price:,}원 | 수량 {this_qty}g"
    )

    ord_no = place_gold_order(token, "buy", this_qty, order_price)
    msg.append(
        f"주문 접수 완료 | 주문번호: {ord_no}" if ord_no
        else "GOLD: 매수 주문 응답 이상 (주문번호 없음)"
    )
    return msg, ord_no


# ===========================================================================
# 10) 매도 로직
# ===========================================================================
def run_sell(token, split_index):
    """분할매도 1회 실행 → (메시지 리스트, 주문번호 or None) 반환."""
    msg     = []
    holding = get_gold_holding(token)
    price   = get_gold_current_price(token)

    hold_qty   = holding["hold_qty"]
    target_qty = int(hold_qty * SELL_QTY_RATIO / 100)
    if target_qty <= 0:
        msg.append("GOLD: 매도 가능 수량 0g → 매도 중단")
        return msg, None

    split_list  = split_quantities(target_qty, SPLITS_PER_DAY)
    this_qty    = split_list[split_index - 1]
    order_price = 0 if ORDER_PRICE_TYPE == "market" else int(price * (1 - LIMIT_SLIPPAGE))

    if this_qty <= 0:
        msg.append(f"GOLD: {split_index}회차 매도수량 0g → 건너뜀")
        return msg, None

    msg.append(
        f"[매도] {split_index}/{SPLITS_PER_DAY}회차 | "
        f"보유 {hold_qty}g / 분할 {split_list} | "
        f"이번 {this_qty}g | 단가 {order_price:,}원"
    )

    ord_no = place_gold_order(token, "sell", this_qty, order_price)
    msg.append(
        f"주문 접수 완료 | 주문번호: {ord_no}" if ord_no
        else "GOLD: 매도 주문 응답 이상 (주문번호 없음)"
    )
    return msg, ord_no


# ===========================================================================
# 11) 메인 실행
# ===========================================================================
def main():
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
                f"종목  : 금 99.99K ({GOLD_STOCK_CODE})",
                "━━━━━━━━━━━━━━━━━━━━━━━━",
            ])

        # ── 매매 실행
        if MODE == "buy":
            order_msg, ord_no = run_buy(token, split_index)
        else:
            order_msg, ord_no = run_sell(token, split_index)

        # ── 5초 대기 후 체결 확인 (kt50031)
        time.sleep(5)
        if ord_no:
            exec_info = get_order_execution(token, ord_no)
            if exec_info and exec_info.get("qty", 0) > 0:
                order_msg.append(
                    f"체결확인: {exec_info['qty']}g "
                    f"@ {exec_info['price']:,}원 "
                    f"(총 {exec_info['amount']:,}원)"
                )
            else:
                order_msg.append(f"체결확인: 주문번호 {ord_no} 미체결 또는 조회 실패")

        # ── 잔고(kt50020) & 예수금(kt50021) 조회
        holding = get_gold_holding(token)
        deposit = get_deposit(token)

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
                + _fmt_holding(holding, deposit)
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
# [ crontab 설정 예시 ]  (AWS EC2 Linux, KST 기준)
#   $ crontab -e
#
#   # KRX 금현물 분할 매매 - 평일(월~금) 1일 5회 분할
#   13 9  * * 1-5  /usr/bin/python3 /var/autobot/GOLD_TR.py
#   13 10 * * 1-5  /usr/bin/python3 /var/autobot/GOLD_TR.py
#   13 12 * * 1-5  /usr/bin/python3 /var/autobot/GOLD_TR.py
#   13 14 * * 1-5  /usr/bin/python3 /var/autobot/GOLD_TR.py
#   13 15 * * 1-5  /usr/bin/python3 /var/autobot/GOLD_TR.py
#
#   ※ EC2 시간대를 KST로 설정할 것:
#     $ sudo timedatectl set-timezone Asia/Seoul
#
#   ※ 며칠간 분할매매 시 crontab 날짜 필드 예시:
#     13 9  19-21 * 1-5  /usr/bin/python3 /var/autobot/GOLD_TR.py
#     → 매월 19~21일 평일에만 실행
# ===========================================================================
