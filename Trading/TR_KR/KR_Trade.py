import sys
import telegram_alert as TA
from datetime import datetime
import time as time_module
from tendo import singleton
import KIS_KR

try:
    me = singleton.SingleInstance()
except singleton.SingleInstanceException:
    TA.send_tele("KR체크: 이미 실행 중입니다.")
    sys.exit(0)

# KIS instance 생성
key_file_path = "/var/autobot/KIS/kis63751991nkr.txt"
token_file_path = "/var/autobot/KIS/kis63751991_token.json"
cano = "63751991"
acnt_prdt_cd = "01"
KIS = KIS_KR.KIS_API(key_file_path, token_file_path, cano, acnt_prdt_cd)

sell_tax = KIS.sell_fee_tax  # 매도 수수료 0.014% + 세금 0.2%
buy_tax = KIS.buy_fee_tax    # 매수 수수료 0.014%

# ============================================
# 모드 및 종목 설정
# ============================================
MODE       = "SELL"          # "BUY"(분할매수) 또는 "SELL"(분할매도)
TICKER     = "498400"
TICKER_NM  = "KODEX 200타겟위클리커버드콜"

# ── 매수 모드 설정 ──────────────────────────
BUY_TOTAL_AMT  = 0             # 총 매입 예정금액 (원)
BUY_TRADE_DAYS = 26            # 총 거래일 수 (분할매수일 수)
BUY_SPLIT      = 4             # 일 분할 횟수

# ── 매도 모드 설정 ──────────────────────────
SELL_TOTAL_QTY  = 1701         # 총 매도 수량 (4,787주보유 중인 절반 매도 KRX금 매입))
# SELL_TOTAL_QTY  = None       # 총 매도 수량 (None이면 보유 전량)
SELL_TRADE_DAYS = 3            # 총 거래일 수 (분할매도일 수)
SELL_SPLIT      = 7            # 일 분할 횟수

# ============================================


def health_check():
    """시스템 상태 확인"""
    checks = []

    # 1. API 토큰 유효성
    if not KIS.access_token:
        checks.append("KR체크: API 토큰 없음")

    # 2. 네트워크 연결
    try:
        import socket
        socket.create_connection(("openapi.koreainvestment.com", 9443), timeout=5)
    except Exception:
        checks.append("KR체크: KIS API 서버 접속 불가")

    if checks:
        TA.send_tele(checks)
        sys.exit(1)


def get_current_price():
    """현재가 조회 (정수 반환). 실패 시 종료."""
    price = KIS.get_KR_current_price(ticker=TICKER)
    # get_KR_current_price는 int를 반환한다 (float 아님)
    if not isinstance(price, int) or price <= 0:
        TA.send_tele(f"KR: 현재가 조회 불가로 종료합니다. ({price})")
        sys.exit(0)
    return price


def run_buy(message):
    """분할매수 로직"""
    if BUY_TRADE_DAYS <= 0 or BUY_SPLIT <= 0:
        TA.send_tele("KR: 매수 거래일수/분할횟수 설정 오류로 종료합니다.")
        sys.exit(0)

    # ── 주문가능현금 확인 (D+2 정산 포함)
    KRW = KIS.get_KR_orderable_cash()
    if KRW is None:
        TA.send_tele("KR: 주문가능현금 조회 실패로 종료합니다.")
        sys.exit(0)

    day_invest   = BUY_TOTAL_AMT / BUY_TRADE_DAYS
    split_invest = int(day_invest / BUY_SPLIT)

    if KRW < split_invest:   # 1회 주문금액 기준 비교
        TA.send_tele(
            f"KR: 주문가능금액 부족으로 종료합니다. "
            f"(필요: {split_invest:,}원 / 잔고: {KRW:,.0f}원)"
        )
        sys.exit(0)

    # ── 현재가 조회 + 수수료 가산 (시장가 체결 여유분)
    price = get_current_price()
    eff_price = price + (price * buy_tax)

    # ── 주문 수량 계산
    split_qty = int(split_invest / eff_price)
    if split_qty <= 0:
        TA.send_tele(
            f"KR: 주문 수량 0주 산출로 종료합니다. "
            f"(분할금액: {split_invest:,}원 / 현재가: {price:,}원)"
        )
        sys.exit(0)

    message.append(f"KR: {TICKER_NM} 분할매수 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    message.append(f"KR: 분할금액 {split_invest:,}원 / 현재가 {price:,}원 / 주문수량 {split_qty}주")

    # ── 시장가 매수 주문 (order_buy_KR은 Dict 단일 반환)
    order_info = KIS.order_buy_KR(ticker=TICKER, quantity=split_qty, price=0, ord_dvsn="01")

    if not order_info or not order_info.get("success"):
        err = order_info.get("error_message", "") if isinstance(order_info, dict) else "API 응답 없음"
        TA.send_tele([f"KR: 매수 주문 실패로 종료합니다. ({err})"])
        sys.exit(0)

    message.append(f"매수 주문 접수: {split_qty}주 주문번호:{order_info.get('order_number', '')}")
    return order_info.get("order_number", "")


def run_sell(message):
    """분할매도 로직"""
    if SELL_TRADE_DAYS <= 0 or SELL_SPLIT <= 0:
        TA.send_tele("KR: 매도 거래일수/분할횟수 설정 오류로 종료합니다.")
        sys.exit(0)

    # ── 보유 종목 잔고 조회
    stock = KIS.get_KR_stock_balance_by_ticker(ticker=TICKER)
    if stock is None:
        TA.send_tele(f"KR: {TICKER} 미보유 또는 잔고 조회 실패로 종료합니다.")
        sys.exit(0)

    hold_qty     = stock["보유수량"]        # ccld_qty_smtl1 기반 (당일 체결 포함)
    sellable_qty = stock["매도가능수량"]    # ord_psbl_qty (T+2 정산 가능분)

    if hold_qty <= 0:
        TA.send_tele(f"KR: {TICKER} 보유수량 0주로 종료합니다.")
        sys.exit(0)

    # ── 목표 매도 수량 결정 (None이면 보유 전량)
    #    매 실행 시 현재 보유수량을 재조회하므로, "현재 보유분 중 처분할 잔량"이
    #    곧 남은 목표가 된다. 부분매도가 진행될수록 hold_qty가 줄어 자연 수렴.
    target_total = hold_qty if SELL_TOTAL_QTY is None else min(SELL_TOTAL_QTY, hold_qty)
    remaining_target = target_total

    if remaining_target <= 0:
        TA.send_tele(f"KR: {TICKER} 매도 목표 달성 완료 (잔량 0).")
        sys.exit(0)

    # ── 일별 매도 수량: 남은 잔량을 남은 거래일로 균등 분할
    #    실행 일수를 별도 카운트하지 않고, 매 실행을 1거래일로 간주해
    #    "잔량 / TRADE_DAYS" 를 일 목표로 사용 → 미체결 누적 시 자연 보정
    day_qty = remaining_target // SELL_TRADE_DAYS
    if day_qty < 1:
        day_qty = remaining_target   # 잔량이 거래일수보다 적으면 당일 전량

    # ── 매도가능수량으로 캡핑 (T+2 미정산분 매도 실패 방지)
    day_qty = min(day_qty, sellable_qty)
    if day_qty <= 0:
        TA.send_tele(
            f"KR: {TICKER} 당일 매도가능수량 0주로 종료합니다. "
            f"(보유:{hold_qty} / 매도가능:{sellable_qty})"
        )
        sys.exit(0)

    # ── 일 분할 횟수로 재분할
    split_qty = day_qty // SELL_SPLIT
    remainder = day_qty - split_qty * SELL_SPLIT
    if split_qty < 1:
        # 일 목표가 분할횟수보다 적으면 1회 주문으로 처리
        split_count = 1
        split_qty = day_qty
        remainder = 0
    else:
        split_count = SELL_SPLIT

    message.append(f"KR: {TICKER_NM} 분할매도 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    message.append(
        f"KR: 보유 {hold_qty}주 / 매도가능 {sellable_qty}주 / "
        f"목표잔량 {remaining_target}주 / 당일 {day_qty}주 ({split_count}분할)"
    )

    # ── 분할 시장가 매도 주문
    order_numbers = []
    for i in range(split_count):
        this_qty = split_qty + (remainder if i == split_count - 1 else 0)
        if this_qty < 1:
            continue

        order_info = KIS.order_sell_KR(ticker=TICKER, quantity=this_qty, price=0, ord_dvsn="01")

        if not order_info or not order_info.get("success"):
            err = order_info.get("error_message", "") if isinstance(order_info, dict) else "API 응답 없음"
            message.append(f"매도 실패 {this_qty}주: {err}")
        else:
            order_numbers.append(order_info.get("order_number", ""))
            message.append(f"매도 주문 접수: {this_qty}주 주문번호:{order_info.get('order_number', '')}")

        time_module.sleep(0.2)

    if not order_numbers:
        TA.send_tele(["KR: 매도 주문 전량 실패로 종료합니다."] + message)
        sys.exit(0)

    # 체결 확인용으로 마지막 주문번호 반환
    return order_numbers[-1]


# ============================================
# 메인 실행
# ============================================
if MODE not in ("BUY", "SELL"):
    TA.send_tele(f"KR: MODE 설정 오류 ({MODE}). 'BUY' 또는 'SELL'이어야 합니다.")
    sys.exit(1)

# ── 거래일 확인
if not KIS.is_KR_trading_day():
    TA.send_tele("KR: 거래일이 아닙니다.")
    sys.exit(0)

message = []
health_check()

# ── 모드별 주문 실행
if MODE == "BUY":
    order_number = run_buy(message)
else:
    order_number = run_sell(message)

time_module.sleep(5)

# ── 체결 확인
check = KIS.check_KR_order_execution(order_number=order_number, ticker=TICKER, order_type="00")
if check:
    message.append(
        f"체결확인: {check.get('name')} {check.get('qty')}주 "
        f"@{check.get('price')}원 (총 {check.get('amount')}원)"
    )
else:
    message.append(f"체결확인: 주문번호 {order_number} 미체결 또는 조회 실패")

# ── 잔고 요약
balance = KIS.get_KR_account_summary()
if balance is None:
    message.append("KR: 계좌 원화 조회 실패")
    TA.send_tele(message)
    sys.exit(0)

stock = KIS.get_KR_stock_balance_by_ticker(ticker=TICKER)
if stock is None:
    message.append(f"{TICKER} 종목 잔고 없음 (전량 매도 완료 또는 미보유)")
else:
    message.append(f"KR 보유수량: {stock['보유수량']}주")
    message.append(f"KR 현재가: {stock['현재가']:,}원")
    message.append(f"KR 평가금액: {stock['평가금액']:,}원")
    message.append(f"KR 평가손익: {stock['평가손익']:,}원")
    message.append(f"KR 수익률: {stock['수익률']:.2f}%")

message.append(f"KR 주식평가금액: {balance['stock_eval_amt']:,.0f}원")
message.append(f"KR 원화 잔고: {balance['cash_balance']:,.0f}원")
message.append(f"KR 전체 원화자산: {balance['total_krw_asset']:,.0f}원")

TA.send_tele(message)
sys.exit(0)
