import sys
import json
import kakao_alert as KA
from datetime import datetime, timedelta
import pandas as pd
import requests
import calendar
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
KR_TR_path = "/var/autobot/TR_KR/KR_TR.json" # json

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
checkday = KIS.is_KR_trading_day()
if checkday == False:
    KA.SendMessage("KR: 거래일이 아닙니다.")
    sys.exit(0)

message = [] # 출력메시지 LIST 생성
health_check() # 시스템 상태 확인

# 매수가능 원화 조회 
KRW = KIS.get_KR_orderable_cash()
# 1일 매입금액 산출
day_invest = 125811360/ 26
split_invest = int(day_invest / 4)
# 당일 매입금액 충분여부 확인
if KRW < day_invest :
    KA.SendMessage("KR:주문가능금액이 4800000원 이하로 종료합니다.")
    sys.exit(0)

# 주문수량확인
price = KIS.get_KR_current_price(ticker="498400")
if not isinstance(price, float):
    KA.SendMessage(f"KR: 현재가 조회 불가로 종료합니다. ({price})")
    sys.exit(0)

message.append(f"KODEX 200타켓위클리커버드콜 매입시작 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
split_qty = int(split_invest / price)

# 시장가 주문하기
order_info, order_buy_message = KIS.order_buy_KR(ticker="498400", quantity=split_qty, price=0, ord_dvsn="01")
message.extend(order_buy_message)

if not order_info or not order_info.get('success'):
    KA.SendMessage(f"KR: 매수 주문 실패로 종료합니다.\n" + "\n".join(order_buy_message))
    sys.exit(0)

order_number = order_info['order_number']
time_module.sleep(5)

# 체결 확인하기
check = KIS.check_KR_order_execution(order_number=order_number, ticker="498400", order_type="02")
if check:
    message.append(f"체결확인: {check.get('name')} {check.get('qty')}주 @{check.get('price')}원 (총 {check.get('amount')}원)")
else:
    message.append(f"체결확인: 주문번호 {order_number} 미체결 또는 조회 실패")
time_module.sleep(0.1)

# 정리하기
balance = KIS.get_KR_account_summary()

stock_eval_amt = balance['stock_eval_amt']
cash_balance = balance['cash_balance']
total_krw_asset = balance['total_krw_asset']

stock = KIS.get_KR_stock_balance_by_ticker(ticker="498400")

message.append(f"보유수량: {stock['보유수량']}")
message.append(f"현재가: {stock['현재가']}")
message.append(f"평가금액: {stock['평가금액']}")
message.append(f"평가손익: {stock['평가손익']}")
message.append(f"수익률: {stock['수익률']}")
message.append(f"주식평가금액: {stock_eval_amt}")
message.append(f"원화 잔고: {cash_balance}")
message.append(f"전체 원화자산: {total_krw_asset}")

send_messages_in_chunks(message, max_length=1000)

sys.exit(0)