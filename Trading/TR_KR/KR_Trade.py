import sys
import kakao_alert as KA
from datetime import datetime
import time as time_module
from tendo import singleton
import KIS_KR

try:
    me = singleton.SingleInstance()
except singleton.SingleInstanceException:
    KA.SendMessage("KRQT: 이미 실행 중입니다.")
    sys.exit(0)

# KIS instance 생성
key_file_path = "/var/autobot/TR_KR/kis44036546nkr.txt"
token_file_path = "/var/autobot/TR_KR/kis44036546_token.json"
cano = "44036546"
acnt_prdt_cd = "01"
KIS = KIS_KR.KIS_API(key_file_path, token_file_path, cano, acnt_prdt_cd)

sell_tax = KIS.sell_fee_tax  # 매도 수수료 0.014% + 세금 0.2% KRQT계좌
buy_tax = KIS.buy_fee_tax  # 매수 수수료 0.014% KRQT 계좌

def health_check(): # 점검 완료
    """시스템 상태 확인"""
    checks = []
    
    # 1. API 토큰 유효성
    if not KIS.access_token:
        checks.append("KRQT 체크: API 토큰 없음")
    
    # 2. 네트워크 연결
    try:
        import socket
        socket.create_connection(("openapi.koreainvestment.com", 9443), timeout=5)
    except:
        checks.append("KRQT 체크: KIS API 서버 접속 불가")
    
    if checks:
        KA.SendMessage("\n".join(checks))
        sys.exit(1)

def send_messages_in_chunks(message, max_length=1000):
    current_chunk = []
    current_length = 0
    
    for msg in message:
        msg_length = len(msg) + 1  # \n 포함
        if current_length + msg_length > max_length:
            KA.SendMessage("\n".join(current_chunk))
            time_module.sleep(1)
            current_chunk = [msg]
            current_length = msg_length
        else:
            current_chunk.append(msg)
            current_length += msg_length
    
    if current_chunk:
        KA.SendMessage("\n".join(current_chunk))

# ============================================
# 메인 로직 # 분할매입
# ============================================
TICKER     = "498400"
TICKER_NM  = "KODEX 200타겟위클리커버드콜"
TOTAL_AMT  = 125_811_360   # 총 매입 예정금액 (원)
TRADE_DAYS = 26            # 총 거래일 수
SPLIT      = 4             # 일 분할 횟수

# ── 거래일 확인
if not KIS.is_KR_trading_day():
    KA.SendMessage("KR: 거래일이 아닙니다.")
    sys.exit(0)

message = []
health_check()

# ── 예수금 확인
KRW = KIS.get_KR_orderable_cash()
if KRW is None:
    KA.SendMessage("KR: 예수금 조회 실패로 종료합니다.")
    sys.exit(0)

day_invest   = TOTAL_AMT / TRADE_DAYS
split_invest = int(day_invest / SPLIT)

if KRW < split_invest:   # ★ 1회 주문금액 기준으로 비교 (4회치 전액 아님)
    KA.SendMessage(f"KR: 주문가능금액 부족으로 종료합니다. (필요: {split_invest:,}원 / 잔고: {KRW:,.0f}원)")
    sys.exit(0)

# ── 현재가 조회
simple_price = KIS.get_KR_current_price(ticker=TICKER)
if not isinstance(simple_price, float):
    KA.SendMessage(f"KR: 현재가 조회 불가로 종료합니다. ({simple_price})")
    sys.exit(0)
price = simple_price + (simple_price * buy_tax)

# ── 주문 수량 계산
split_qty = int(split_invest / price)
if split_qty <= 0:
    KA.SendMessage(f"KR: 주문 수량 0주 산출로 종료합니다. (분할금액: {split_invest:,}원 / 현재가: {price:,}원)")
    sys.exit(0)

message.append(f"{TICKER_NM} 매입시작 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
message.append(f"분할금액: {split_invest:,}원 / 현재가: {price:,}원 / 주문수량: {split_qty}주")

# ── 시장가 매수 주문
order_info, order_buy_message = KIS.order_buy_KR(ticker=TICKER, quantity=split_qty, price=0, ord_dvsn="01")
message.extend(order_buy_message)

if not order_info or not order_info.get('success'):
    KA.SendMessage("KR: 매수 주문 실패로 종료합니다.\n" + "\n".join(order_buy_message))
    sys.exit(0)

order_number = order_info['order_number']
time_module.sleep(5)

# ── 체결 확인
check = KIS.check_KR_order_execution(order_number=order_number, ticker=TICKER, order_type="02")
if check:
    message.append(f"체결확인: {check.get('name')} {check.get('qty')}주 @{check.get('price')}원 (총 {check.get('amount')}원)")
else:
    message.append(f"체결확인: 주문번호 {order_number} 미체결 또는 조회 실패")

# ── 잔고 요약
balance = KIS.get_KR_account_summary()
if balance is None:
    message.append("계좌 요약 조회 실패")
    send_messages_in_chunks(message)
    sys.exit(0)

stock = KIS.get_KR_stock_balance_by_ticker(ticker=TICKER)
if stock is None:
    message.append("종목 잔고 조회 실패 (체결 지연 또는 API 오류 — 계좌 직접 확인 필요)")
    send_messages_in_chunks(message)
    sys.exit(0)

message.append(f"보유수량: {stock['보유수량']}주")
message.append(f"현재가: {stock['현재가']:,}원")
message.append(f"평가금액: {stock['평가금액']:,}원")
message.append(f"평가손익: {stock['평가손익']:,}원")
message.append(f"수익률: {stock['수익률']:.2f}%")
message.append(f"주식평가금액: {balance['stock_eval_amt']:,.0f}원")
message.append(f"원화 잔고: {balance['cash_balance']:,.0f}원")
message.append(f"전체 원화자산: {balance['total_krw_asset']:,.0f}원")

send_messages_in_chunks(message)
sys.exit(0)