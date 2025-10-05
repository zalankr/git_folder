import json
from datetime import datetime
import USLA
import KIS_US

# Account연결 data
key_file_path = "C:/Users/ilpus/Desktop/NKL_invest/kis63721147nkr.txt"
token_file_path = "C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/kis63721147_token.json"
cano = "63721147" # 종합계좌번호 (8자리)
acnt_prdt_cd = "01"  # 계좌상품코드 (2자리)

# Instance 생성
kis = KIS_US.KIS_API(key_file_path, token_file_path, cano, acnt_prdt_cd)
usla = USLA.USLAS()

# USLA data 불러오기
def get_USLA_data():
    USLA_data_path = "C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/USLA_data.json"    
    try:
        with open(USLA_data_path, 'r', encoding='utf-8') as f:
            USLA_data = json.load(f)
        return USLA_data

    except Exception as e:
        print(f"JSON 파일 오류: {e}")
        # KA.SendMessage(f"{} JSON 파일 오류: {e}")
        exit()

# USD로 환산 잔고 계산
def calculate_USD_value(holding):
    holding_USD_value = 0
    for t in holding.keys():
        if t == "CASH":
            holding_USD_value += holding[t]
        else:
            price = kis.get_US_current_price(t)
            value = price * holding[t] * (1 - usla.tax_rate)
            holding_USD_value += value

    return holding_USD_value

# USLA 모델 실행, target ticker와 weight 구하기
def invest_target():
    invest = usla.run_strategy()
    target = {
        ticker: weight 
        for ticker, weight in invest['allocation'].items() 
        if weight > 0
    }

    return target

# target비중에 맞춰 환산금액을 곱하고 현재가로 나누기 > ticker별 수량 반환+USD금액 반환
def calculate_target_quantity(target,target_usd_value):
    target_quantity = {}
    target_stock_value = 0
    for ticker in target.keys():
        if ticker != "CASH":
            try:
                price = kis.get_US_current_price(ticker)
                if price and price > 0:
                    target_quantity[ticker] = int(target_usd_value[ticker] / price)
                    target_stock_value += target_quantity[ticker] * price * (1 + usla.tax_rate)
                else:
                    print(f"{ticker}: 가격 정보 없음")
                    target_quantity[ticker] = 0
            except Exception as e:
                print(f"{ticker}: 수량 계산 오류 - {e}")
                target_quantity[ticker] = 0

    target_quantity["CASH"] = sum(target_usd_value.values()) - target_stock_value

    return target_quantity, target_stock_value

# target비중 계산, Json데이터에서 holding ticker와 quantity 구하기
target = invest_target()
USLA_data = get_USLA_data()
holding = dict(zip(USLA_data['ticker'], USLA_data['quantity']))
holding_ticker = list(holding.keys())
holding_USD_value = calculate_USD_value(holding)

# 보유 $기준 잔고를 바탕으로 목표 비중에 맞춰 ticker별 quantity 계산
target_usd_value = {ticker: target[ticker] * holding_USD_value for ticker in target.keys()}

# target비중에 맞춰 환산금액을 곱하고 현재가로 나누기 > ticker별 수량 반환+USD금액 반환
target_quantity, target_stock_value = calculate_target_quantity(target,target_usd_value)
print(target_quantity)
print(target_quantity["CASH"]+target_stock_value)

# 비교 하기

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