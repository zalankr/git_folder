import json
from datetime import datetime
import USLA
import KIS_US


key_file_path = "C:/Users/ilpus/Desktop/NKL_invest/kis63721147nkr.txt"
token_file_path = "C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/kis63721147_token.json"
USLA_data_path = "C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/USLA_data.json"
cano = "63721147" # 종합계좌번호 (8자리)
acnt_prdt_cd = "01"  # 계좌상품코드 (2자리)

# Instance 생성
kis = KIS_US.KIS_API(key_file_path, token_file_path, cano, acnt_prdt_cd)
usla = USLA.USLAS()

# 현재 일자와 시간 구하기
now = datetime.now()

# Model data 불러오기    
try:
    with open(USLA_data_path, 'r', encoding='utf-8') as f:
        USLA_data = json.load(f)
        holding_weight = {"usd_quntity": USLA_data['usd_quntity'], "hold1_quantity": USLA_data['ticker1_quntity'], 
                          "hold2_quantity": USLA_data['ticker2_quntity'], "hold1": USLA_data['ticker1'], "hold2": USLA_data['ticker2']}
    
except Exception as e:
    print(f"JSON 파일 오류: {e}")
    # KA.SendMessage(f"{} JSON 파일 오류: {e}")
    exit()

# USLA 실행, target ticker와 weight 구하기
invest = usla.run_strategy()

target_weight = {
    ticker: weight 
    for ticker, weight in invest['allocation'].items() 
    if weight > 0
}

print(target_weight)

##테스트를 위해서 2000으로 TMF 0.7와 UPRO 0.29 CASH 0.01로 맞추고 테스트
# 최초 수량 뽑기 비교 > 먼저 홀딩된 자산을 수량에 현재가를 곱해서 USD로 모두 환산(tax_rate = 0.0009 계산)하고 타겟비중으로 환산금액을 곱하고 현재가로 나누기

# print(target_weight)
# print(holding_weight)




# 미국주식 주문단위 가격은 0.01, 주문금액 최소 1$이상으로



# else:
#     print(f"Regime Signal: {regime_signal:.2f} ≥ 0 → 투자 모드")
#     signal = USLA.run_strategy(target_month=None, target_year=None)

# print("="*30)
# print(signal['allocation']['ticker'])






# regime_signal = signal['regime_signal']
# momentum_scores = signal['momentum_scores']
# allocation = signal['allocation']
# current_prices = signal['current_prices']

# print("\n=== 투자 전략 시그널 ===")
# print(f"Regime Signal: {regime_signal:.2f}")  # Regime Signal 출력 (regime_signal)
# print("\n모멘텀 점수:")
# print(momentum_scores.round(4))  # 모멘텀 점수 출력 (momentum_scores)
# print("\n투자 전략:")
# print(allocation)  # 투자 전략 출력 (allocation)
# print("\n현재 가격:")
# print(current_prices)  # 현재 가격 출력 (current_prices)



# 사용 예시
# price = KIS.current_price_US("TQQQ")[1]
# print(price)

# print("\n=== 거래소 찾기 테스트 ===")
# aapl_exchange = KIS.get_US_exchange("AAPL")
# print(f"AAPL 거래소: {aapl_exchange}\n")

# 주문 시 자동으로 거래소 찾아서 사용
# ticker = "TQQQ"
# exchange = KIS.get_US_exchange(ticker)
# if exchange:
#     # result = order_buy_US(ticker, 1, 150.50, exchange)
#     print(f"{ticker} 매수 주문 준비 완료 (거래소: {exchange})")

# 매수 주문 예시 (실제 주문 시 주석 해제)
# result = KIS.order_buy_US("AAPL", 1, 150.50, "NASD")
# print("매수 주문 결과:", result.json())

# 매도 주문 예시 (실제 주문 시 주석 해제)
# result = KIS.order_sell_US("AAPL", 1, 160.00, "NASD")
# print("매도 주문 결과:", result.json())

# 1. 종목만 보기
# stocks = KIS.get_US_stock_balance()
# print(stocks)
# 2. USD만 보기
# usd = KIS.get_US_dollar_balance()
# print(usd)
# 3. 전체 계좌 보기 (예쁘게 출력)
# balance = KIS.get_total_balance()
# print(balance['stock_count'])
# print(balance['usd_deposit'])
# print(KIS.get_total_balance())