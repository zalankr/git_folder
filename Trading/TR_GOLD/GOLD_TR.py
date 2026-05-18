"""
============================================================================
 키움증권 REST API - KRX 금현물(金 現物) 분할 매매 자동화 코드
 파일명 : krx_gold_trading.py
 환경   : Python 3.9+ / AWS EC2 Linux + crontab
============================================================================

[ 0. KRX 금현물이란 ]
 - 한국거래소(KRX)가 운영하는 금시장에서 거래되는 '금 현물' 상품.
 - 금 ETF 대비 매매차익 비과세, 별도 운용보수 없음, 1kg 단위 실물인출 가능.
 - 키움증권 REST API에서 KRX금시장 시세조회 / 계좌조회 / 주문이 지원됨.
 - 종목코드 예시:
     * 04020000  : 금 99.99K (1g 단위 거래) ← 일반 개인투자자 거래 종목
     * 04020100  : 미니금 (100g 단위)
   ※ 실제 종목코드는 키움 REST API 문서 또는 종목정보 조회 API로
     반드시 재확인 후 GOLD_STOCK_CODE 에 입력할 것.

----------------------------------------------------------------------------
[ 1. API Key 발급 신청 방법 ]  ※ 아래 키 값들은 모두 가상(placeholder)입니다.
----------------------------------------------------------------------------
 (1) 키움증권 계좌 개설
     - 키움증권 홈페이지 또는 영웅문에서 위탁계좌 개설.
     - KRX금현물 거래를 위해 '금현물 거래' 약관 동의 / 거래 신청이 별도로
       필요할 수 있음 (HTS·MTS에서 'KRX금시장' 메뉴 확인).

 (2) 키움 REST API 서비스 사용 신청
     - 접속: https://openapi.kiwoom.com  (키움 REST API 포털)
     - [로그인] → [API 신청 / 마이페이지]에서 서비스 사용 등록.
     - 모의투자 서버는 별도 신청 필요(상시 모의투자). 본 코드는 '실전투자' 기준.

 (3) App Key / App Secret 발급
     - API 포털의 [앱 관리] 메뉴에서 앱을 생성하면
       APP_KEY 와 APP_SECRET 이 발급됨.
     - 이 두 값으로 매번 '접근토큰(access token)'을 발급받아 API 호출에 사용.

 (4) 계좌번호 확인
     - 계좌번호는 보통 10자리. (예: 1234567890)
     - 키움 REST API는 일반적으로 계좌번호 전체를 한 필드로 사용.

 (5) 보안 주의
     - APP_KEY / APP_SECRET / 계좌번호는 절대 외부 노출 금지.
     - 운영 시에는 아래처럼 코드에 직접 쓰지 말고 환경변수나
       별도 설정파일(.env, config.json)로 분리할 것을 강력 권장.
         예) APP_KEY = os.environ["KIWOOM_APP_KEY"]
----------------------------------------------------------------------------
"""

import os
import sys
import json
import time
import logging
import datetime
import requests


# ===========================================================================
# 1) API 인증 정보  ─  ※ 전부 가상값. 실제 발급값으로 교체하세요.
# ===========================================================================
APP_KEY     = "YOUR_APP_KEY_HERE"          # 키움 REST API 포털에서 발급
APP_SECRET  = "YOUR_APP_SECRET_HERE"       # 키움 REST API 포털에서 발급
ACCOUNT_NO  = "0000000000"                 # 10자리 계좌번호 (가상)

# 실전투자 서버 (모의투자 미사용)
BASE_URL    = "https://api.kiwoom.com"     # 키움 REST API 실전 도메인
IS_REAL     = True                         # True=실전, False=모의 (본 코드는 실전)

# KRX 금현물 종목코드 ─ 반드시 키움 종목정보로 재확인 후 사용
GOLD_STOCK_CODE = "04020000"               # 금 99.99K (1g 단위) - 예시값

# 토큰 캐시 파일 (24시간 만료 → 30분 안전마진)
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "data", "kiwoom_gold_token.json")
TOKEN_SAFETY_MARGIN_MIN = 30


# ===========================================================================
# 2) 매매 설정 변수  ─  실행 시마다 수시 변경하는 부분
# ===========================================================================
# ---- (2-1) 매매 모드 -------------------------------------------------------
#   "buy"  : 매수
#   "sell" : 매도
MODE = "buy"

# ---- (2-2) 매수 비율 (예수금 대비 %) ---------------------------------------
#   MODE="buy" 일 때만 사용. default 100 = 예수금 전액 사용
BUY_CASH_RATIO = 100        # 단위: %  (예: 50 → 예수금의 50%로 매수)

# ---- (2-3) 매도 비율 (보유수량 대비 %) -------------------------------------
#   MODE="sell" 일 때만 사용. default 100 = 보유수량 전량 매도
SELL_QTY_RATIO = 100        # 단위: %  (예: 30 → 보유수량의 30% 매도)

# ---- (2-4) 매매일 수 -------------------------------------------------------
#   전체 매매를 며칠에 걸쳐 진행할지 표시용 변수.
#   실제 '며칠째인지' 제어는 crontab(실행 날짜)에서 담당하며,
#   이 코드는 1회 실행 시 '하루치 분할 주문 1건'만 처리한다.
TRADING_DAYS = 1            # 단위: 일 (단순 총 일수 표시용)

# ---- (2-5) 1일 분할주문 수 -------------------------------------------------
#   하루 동안 몇 번에 나눠 주문할지. default 5회.
#   crontab 권장 스케줄(평일):
#     13 9  * * 1-5   →  09:13
#     13 10 * * 1-5   →  10:13
#     13 12 * * 1-5   →  12:13
#     13 14 * * 1-5   →  14:13
#     13 15 * * 1-5   →  15:13
SPLITS_PER_DAY = 5          # 단위: 회

# ---- (2-6) 이번 실행이 하루 중 몇 번째 분할인지 -----------------------------
#   crontab 실행 시각으로 자동 판별(아래 SPLIT_SCHEDULE 참고).
#   수동 테스트 시에는 1~SPLITS_PER_DAY 사이 정수를 직접 지정해도 됨.
SPLIT_INDEX_OVERRIDE = None   # None = 현재시각으로 자동판별, 또는 1~5 정수

# 분할 스케줄 (시, 분) ─ SPLITS_PER_DAY 와 개수를 맞출 것
SPLIT_SCHEDULE = [
    (9, 13),    # 1번째 분할
    (10, 13),   # 2번째 분할
    (12, 13),   # 3번째 분할
    (14, 13),   # 4번째 분할
    (15, 13),   # 5번째 분할
]

# ---- (2-7) 주문 호가구분 ---------------------------------------------------
#   금현물은 지정가 위주. 시장가 미지원 가능성 → 현재가 기준 지정가 사용 권장.
ORDER_PRICE_TYPE = "limit"   # "limit"=지정가, "market"=시장가
LIMIT_SLIPPAGE   = 0.005     # 지정가 사용 시 슬리피지(매수 +0.5%, 매도 -0.5%)


# ===========================================================================
# 로깅 설정
# ===========================================================================
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "krx_gold_trading.log"),
                            encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("krx_gold")


# ===========================================================================
# 3) 인증 / 토큰 관리
# ===========================================================================
def get_access_token():
    """접근토큰을 캐시에서 로드하거나 신규 발급한다."""
    # 캐시 확인
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
            expires_at = datetime.datetime.fromisoformat(cached["expires_at"])
            margin = datetime.timedelta(minutes=TOKEN_SAFETY_MARGIN_MIN)
            if datetime.datetime.now() < expires_at - margin:
                log.info("캐시된 접근토큰 사용")
                return cached["access_token"]
        except Exception as e:
            log.warning(f"토큰 캐시 로드 실패, 신규발급 진행: {e}")

    # 신규 발급 (키움 REST API: POST /oauth2/token)
    url = f"{BASE_URL}/oauth2/token"
    headers = {"Content-Type": "application/json;charset=UTF-8"}
    body = {
        "grant_type": "client_credentials",
        "appkey":     APP_KEY,
        "secretkey":  APP_SECRET,
    }
    resp = requests.post(url, headers=headers, json=body, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    token = data.get("token") or data.get("access_token")
    if not token:
        raise RuntimeError(f"토큰 발급 실패 응답: {data}")

    # 만료시각: 응답의 expires_dt(YYYYMMDDHHMMSS) 또는 expires_in(초) 대응
    if data.get("expires_dt"):
        expires_at = datetime.datetime.strptime(data["expires_dt"], "%Y%m%d%H%M%S")
    else:
        expires_in = int(data.get("expires_in", 86400))
        expires_at = datetime.datetime.now() + datetime.timedelta(seconds=expires_in)

    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump({"access_token": token,
                   "expires_at": expires_at.isoformat()},
                  f, ensure_ascii=False, indent=2)
    log.info("접근토큰 신규 발급 완료")
    return token


def _api_headers(token, api_id):
    """공통 요청 헤더 생성.
    api_id : 키움 REST API의 TR ID (각 API 명세서에서 확인).
    """
    return {
        "Content-Type":  "application/json;charset=UTF-8",
        "authorization": f"Bearer {token}",
        "appkey":        APP_KEY,
        "appsecret":     APP_SECRET,
        "api-id":        api_id,
    }


# ===========================================================================
# 4) 조회 API  (KRX 금현물)
#    ※ 아래 api-id / 엔드포인트 / 응답필드명은 키움 REST API 명세서를 보고
#      실제 값으로 반드시 교체·검증해야 합니다. (금현물 전용 TR 사용)
# ===========================================================================
def get_gold_current_price(token, stock_code=GOLD_STOCK_CODE):
    """KRX 금현물 현재가 조회 → 정수(원) 반환."""
    url = f"{BASE_URL}/api/dostk/goldstk"          # 금현물 시세 엔드포인트(예시)
    headers = _api_headers(token, api_id="kg10001")  # 금현물 현재가 TR(예시)
    body = {"stk_cd": stock_code}

    resp = requests.post(url, headers=headers, json=body, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    # 응답 필드명은 명세서 확인 후 교체 (예: cur_prc)
    price_str = str(data.get("cur_prc", "0")).replace(",", "").replace("+", "").replace("-", "")
    price = int(float(price_str))
    log.info(f"금현물 현재가: {price:,}원 (종목 {stock_code})")
    return price


def get_deposit(token):
    """주문가능 예수금 조회 → 정수(원) 반환."""
    url = f"{BASE_URL}/api/dostk/goldstk"
    headers = _api_headers(token, api_id="kg10002")  # 금현물 예수금/잔고 TR(예시)
    body = {
        "qry_tp":  "1",            # 조회구분(예시)
        "stk_cd":  GOLD_STOCK_CODE,
    }
    resp = requests.post(url, headers=headers, json=body, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    # 주문가능금액 필드명은 명세서 확인 후 교체 (예: ord_psbl_amt)
    cash_str = str(data.get("ord_psbl_amt", "0")).replace(",", "")
    cash = int(float(cash_str))
    log.info(f"주문가능 예수금: {cash:,}원")
    return cash


def get_gold_holding_qty(token, stock_code=GOLD_STOCK_CODE):
    """KRX 금현물 보유수량 조회 → 정수(g) 반환."""
    url = f"{BASE_URL}/api/dostk/goldstk"
    headers = _api_headers(token, api_id="kg10003")  # 금현물 잔고 TR(예시)
    body = {
        "qry_tp":  "2",
        "stk_cd":  stock_code,
    }
    resp = requests.post(url, headers=headers, json=body, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    # 잔고 리스트에서 해당 종목의 보유수량 추출 (필드명 명세서 확인)
    qty = 0
    for item in data.get("gold_bal", []):
        if item.get("stk_cd") == stock_code:
            qty = int(float(str(item.get("rmnd_qty", "0")).replace(",", "")))
            break
    log.info(f"금현물 보유수량: {qty}g (종목 {stock_code})")
    return qty


# ===========================================================================
# 5) 주문 API  (KRX 금현물 매수/매도)
# ===========================================================================
def place_gold_order(token, side, qty, price, stock_code=GOLD_STOCK_CODE):
    """KRX 금현물 주문 실행.
    side  : "buy" 또는 "sell"
    qty   : 주문수량(g)
    price : 지정가(원). 시장가일 경우 0.
    """
    if qty <= 0:
        log.warning("주문수량이 0 이하 → 주문 건너뜀")
        return None

    url = f"{BASE_URL}/api/dostk/goldstk"

    # 매수/매도 TR ID (예시 - 명세서 확인 후 교체)
    if side == "buy":
        api_id = "kg00001"     # 금현물 매수주문 TR(예시)
    elif side == "sell":
        api_id = "kg00002"     # 금현물 매도주문 TR(예시)
    else:
        raise ValueError(f"잘못된 side: {side}")

    headers = _api_headers(token, api_id=api_id)

    # 호가구분: 00=지정가, 03=시장가 (명세서 확인)
    if ORDER_PRICE_TYPE == "market":
        trde_tp   = "03"
        ord_price = "0"
    else:
        trde_tp   = "00"
        ord_price = str(price)

    body = {
        "stk_cd":   stock_code,      # 종목코드
        "ord_qty":  str(qty),        # 주문수량
        "ord_uv":   ord_price,       # 주문단가
        "trde_tp":  trde_tp,         # 매매구분(호가)
        # 필요 시 계좌 관련 필드 추가 (명세서 확인)
    }

    resp = requests.post(url, headers=headers, json=body, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    ord_no = data.get("ord_no", "N/A")
    log.info(f"[{side.upper()}] 주문전송 완료 - 수량 {qty}g, 단가 {price:,}원, "
             f"주문번호 {ord_no}")
    return data


# ===========================================================================
# 6) 분할 수량 계산 로직  (핵심)
# ===========================================================================
def split_quantities(total_qty, splits):
    """전체 수량(total_qty)을 splits 회로 분할.

    - 기본: 몫(base)을 각 분할에 균등 배분.
    - 나머지(remainder): 1개씩 앞쪽 분할부터 더해줌.
      예) total=23, splits=5 → 몫 4, 나머지 3
          → [5, 5, 5, 4, 4]  (앞 3개 분할에 +1)
      예) total=4,  splits=5 → 몫 0, 나머지 4
          → [1, 1, 1, 1, 0]  (앞 4개 분할에 1개씩, 5번째는 0)
      예) total=2,  splits=5 → 몫 0, 나머지 2
          → [1, 1, 0, 0, 0]

    반환: 길이 splits 의 리스트.
    """
    if splits <= 0:
        raise ValueError("splits 는 1 이상이어야 합니다.")
    if total_qty < 0:
        total_qty = 0

    base      = total_qty // splits     # 각 분할 기본 수량
    remainder = total_qty % splits      # 나머지

    result = []
    for i in range(splits):
        qty = base
        if i < remainder:               # 앞쪽 분할부터 나머지 1개씩 배분
            qty += 1
        result.append(qty)
    return result


def get_today_split_index():
    """현재 시각으로 '오늘 몇 번째 분할'인지 판별 (1-base).

    crontab 실행 시각(SPLIT_SCHEDULE)과 가장 가까운(±30분 이내) 분할을 찾는다.
    SPLIT_INDEX_OVERRIDE 가 지정되면 그 값을 그대로 사용.
    """
    if SPLIT_INDEX_OVERRIDE is not None:
        log.info(f"분할 인덱스 수동지정: {SPLIT_INDEX_OVERRIDE}")
        return SPLIT_INDEX_OVERRIDE

    now = datetime.datetime.now()
    now_minutes = now.hour * 60 + now.minute

    best_idx, best_diff = None, None
    for idx, (h, m) in enumerate(SPLIT_SCHEDULE[:SPLITS_PER_DAY], start=1):
        sched_minutes = h * 60 + m
        diff = abs(now_minutes - sched_minutes)
        if best_diff is None or diff < best_diff:
            best_idx, best_diff = idx, diff

    # 스케줄과 30분 이상 벗어나면 경고 (수동 실행 가능성)
    if best_diff is not None and best_diff > 30:
        log.warning(f"현재시각이 분할 스케줄과 {best_diff}분 차이 → "
                    f"{best_idx}번째 분할로 처리하지만 확인 필요")
    log.info(f"오늘 분할 인덱스: {best_idx} / {SPLITS_PER_DAY}")
    return best_idx


# ===========================================================================
# 7) 메인 매매 로직
# ===========================================================================
def run_buy(token, split_index):
    """매수: 예수금의 BUY_CASH_RATIO% 를 금액 기준으로 분할 매수.

    - 매수는 '금액 기준' 분할: (예수금 × 비율)을 SPLITS_PER_DAY 로 나눈 뒤
      이번 분할 금액을 현재가로 나눠 주문수량(g)을 산출.
    """
    cash    = get_deposit(token)
    price   = get_gold_current_price(token)

    target_cash = int(cash * BUY_CASH_RATIO / 100)      # 매수에 쓸 총 금액
    if target_cash <= 0 or price <= 0:
        log.warning("매수 가능 금액 또는 현재가가 0 → 매수 중단")
        return

    # 이번 분할에 사용할 금액 = 총 금액 / 분할수 (마지막 분할은 잔여 금액)
    per_split_cash = target_cash // SPLITS_PER_DAY
    if split_index == SPLITS_PER_DAY:
        # 마지막 분할: 누락 금액 보정을 위해 잔여 전액 사용
        used_before = per_split_cash * (SPLITS_PER_DAY - 1)
        this_cash   = target_cash - used_before
    else:
        this_cash = per_split_cash

    # 지정가 산출 (매수는 슬리피지 +)
    if ORDER_PRICE_TYPE == "market":
        order_price = 0
        ref_price   = price
    else:
        order_price = int(price * (1 + LIMIT_SLIPPAGE))
        ref_price   = order_price

    # 이번 분할 매수 수량(g) = 이번 분할 금액 / 주문기준가
    this_qty = this_cash // ref_price if ref_price > 0 else 0

    log.info(f"[매수] 총매수금액 {target_cash:,}원 / {SPLITS_PER_DAY}분할 → "
             f"이번({split_index}분할) 배정금액 {this_cash:,}원 → "
             f"주문수량 {this_qty}g @ {order_price:,}원")

    if this_qty <= 0:
        log.warning("이번 분할 매수수량이 0 → 주문 건너뜀")
        return

    place_gold_order(token, side="buy", qty=this_qty, price=order_price)


def run_sell(token, split_index):
    """매도: 보유수량의 SELL_QTY_RATIO% 를 수량 기준으로 분할 매도.

    - 매도는 '수량 기준' 분할: (보유수량 × 비율)을 SPLITS_PER_DAY 로
      split_quantities() 로 나눠 이번 분할 수량만 주문.
    - 나머지 처리: split_quantities() 가 앞쪽 분할에 1개씩 배분.
    """
    holding = get_gold_holding_qty(token)
    price   = get_gold_current_price(token)

    target_qty = int(holding * SELL_QTY_RATIO / 100)    # 매도할 총 수량(g)
    if target_qty <= 0:
        log.warning("매도 가능 수량이 0 → 매도 중단")
        return

    # 전체 매도수량을 분할 → 이번 분할 수량 추출
    split_list = split_quantities(target_qty, SPLITS_PER_DAY)
    this_qty   = split_list[split_index - 1]            # split_index는 1-base

    # 지정가 산출 (매도는 슬리피지 -)
    if ORDER_PRICE_TYPE == "market":
        order_price = 0
    else:
        order_price = int(price * (1 - LIMIT_SLIPPAGE))

    log.info(f"[매도] 총매도수량 {target_qty}g 분할내역 {split_list} → "
             f"이번({split_index}분할) 주문수량 {this_qty}g @ {order_price:,}원")

    if this_qty <= 0:
        log.warning("이번 분할 매도수량이 0 → 주문 건너뜀")
        return

    place_gold_order(token, side="sell", qty=this_qty, price=order_price)


def main():
    log.info("=" * 60)
    log.info(f"KRX 금현물 자동매매 시작 | MODE={MODE} | "
             f"매매일수(표시용)={TRADING_DAYS}일 | 1일분할={SPLITS_PER_DAY}회")

    # 설정값 유효성 검사
    if MODE not in ("buy", "sell"):
        log.error(f"잘못된 MODE: {MODE} (buy/sell 만 허용)")
        sys.exit(1)
    if len(SPLIT_SCHEDULE) < SPLITS_PER_DAY:
        log.error("SPLIT_SCHEDULE 개수가 SPLITS_PER_DAY보다 적습니다.")
        sys.exit(1)

    try:
        token       = get_access_token()
        split_index = get_today_split_index()

        if MODE == "buy":
            run_buy(token, split_index)
        else:
            run_sell(token, split_index)

        log.info("KRX 금현물 자동매매 정상 종료")

    except requests.exceptions.HTTPError as e:
        log.error(f"API HTTP 오류: {e} | 응답: "
                  f"{getattr(e.response, 'text', '')}")
        sys.exit(1)
    except Exception as e:
        log.error(f"실행 중 오류: {e}", exc_info=True)
        sys.exit(1)
    finally:
        log.info("=" * 60)


if __name__ == "__main__":
    main()


# ===========================================================================
# [ crontab 설정 예시 ]  (AWS EC2 Linux)
#   $ crontab -e
#
#   # KRX 금현물 분할 매매 - 평일(월~금) 1일 5회 분할
#   13 9  * * 1-5  /usr/bin/python3 /home/ec2-user/krx_gold_trading.py
#   13 10 * * 1-5  /usr/bin/python3 /home/ec2-user/krx_gold_trading.py
#   13 12 * * 1-5  /usr/bin/python3 /home/ec2-user/krx_gold_trading.py
#   13 14 * * 1-5  /usr/bin/python3 /home/ec2-user/krx_gold_trading.py
#   13 15 * * 1-5  /usr/bin/python3 /home/ec2-user/krx_gold_trading.py
#
#   ※ 며칠에 걸쳐 매매하려면 crontab의 '일(day)' 필드로 날짜를 제어.
#     본 코드 자체는 1회 실행 = 하루치 분할 1건만 처리한다.
#   ※ EC2 서버 시간대(timezone)를 KST로 맞출 것:
#     $ sudo timedatectl set-timezone Asia/Seoul
# ===========================================================================
