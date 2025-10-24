from datetime import datetime, timedelta
import json
import sys
import KIS_Calender
import USLA_model
import KIS_US

"""
crontab 설정
1. 25년~26년 1년치 월 첫 거래일 USAA(USLA+HAA) Rebalancing
*/5 9-21 1 11 * python3 /TR_KIS/KIS_Trading.py 일반 시간대 UTC 21시 정규장 종료 > 장종류 time.sleep하고 난 후주문 취소 체결확인 기록 등 시행 
*/5 8-20 1 4 * python3 /TR_KIS/KIS_Trading.py 서머타임 시간대 UTC 20시 정규장 종료 > 장종류 time.sleep하고 난 후주문 취소 체결확인 기록 등 시행 
2. 25년~26년 1년치 월 마지막 거래일 USAA(USLA+HAA) 'BIL'매도 후 USD CASH로 전환(이자수익용 BIL)
30 20 31 10 * python3 /TR_KIS/KIS_Trading.py 일반 시간대 UTC 21시 정규장 종료 > 장종류 time.sleep하고 난 후주문 취소 체결확인 기록 등 시행 
30 19 31 3 * python3 /TR_KIS/KIS_Trading.py 서머타임 시간대 UTC 20시 정규장 종료 > 장종류 time.sleep하고 난 후주문 취소 체결확인 기록 등 시행 
"""

# USLA모델 instance 생성
key_file_path = "C:/Users/ilpus/Desktop/NKL_invest/kis63721147nkr.txt"
token_file_path = "C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/kis63721147_token.json"
cano = "63721147"  # 종합계좌번호 (8자리)
acnt_prdt_cd = "01"  # 계좌상품코드 (2자리)
USLA = USLA_model.USLA_Model(key_file_path, token_file_path, cano, acnt_prdt_cd)

# 날짜를 받아 USAA 리밸런싱일이 맞는 지, summer or winter time 시간대인지 확인
# 리밸런싱일인 경우 시간을 받아 장전, 장중거래 시간대인지, 거래회차는 몇회차인지 확인
# 밑에 부분 테스트용, 정식버전은 KIS_Calender해당 메써드의 current_date, current_time 수정
# 별도 일수익변화 체크 코드는 따로 운영
order_time = KIS_Calender.check_order_time()
if order_time['season'] == "USAA_not_rebalancing":
    print("오늘은 리밸런싱일이 아닙니다. 프로그램을 종료합니다.")
    sys.exit(0)

print(f"USLA {order_time['market']} 리밸런싱 {order_time['round']}/{order_time['total_round']}회차")
print(f"{order_time['date']}, {order_time['season']} 리밸런싱 {order_time['market']} \n{order_time['time']} {order_time['round']}/{order_time['total_round']}회차 거래입니다.")

USLA_ticker = ["UPRO", "TQQQ", "EDC", "TMF", "TMV"]

# Pre-market round 1회에만 Trading qty를 구하기
if order_time['market'] == "Pre-market" and order_time['round'] == 1:
    # Hold 실제 잔고 dict 만들기
    real_balance = USLA.get_US_stock_balance()
    Hold = dict()
    for i in range(len(real_balance)):
        ticker = real_balance[i]['ticker']
        if real_balance[i]['ticker'] in USLA_ticker:
            Hold[ticker] = real_balance[i]['quantity']

    TR_data = USLA.load_USLA_data()
    Hold['CASH'] = TR_data['CASH'] # 현재 잔고

    # Target ticker와 weight dict 만들기
    target_weight = USLA.target_ticker_weight() # 목표 티커 비중
    print(target_weight)

    # 현재 USD환산 USLA 잔고
    hold_usd_value = USLA.calculate_USD_value(Hold)
    print(hold_usd_value)

    # USLA USD 잔고 X 티커별 비중 = target qty
    target_usd_value = {ticker: target_weight[ticker] * hold_usd_value for ticker in target_weight.keys()} # target_ticker별 USD 배정 dict
    target_qty = USLA.calculate_target_qty(target_weight, target_usd_value) # target_ticker별 quantity
    
    # target qty hold qty 비교 조정
    Buy = dict()
    Sell = dict()

    # target에 있는 종목 처리
    for ticker in target_weight.keys():
        if ticker == "CASH":
            continue
        hold_qty = Hold.get(ticker, 0)  # Hold에 없으면 0
        target = target_qty[ticker]
        
        if target > hold_qty:
            Buy[ticker] = target - hold_qty
        elif target < hold_qty:
            Sell[ticker] = hold_qty - target

    # Hold에만 있고 target에 없는 종목 처리 (전량 매도)
    for ticker in Hold.keys():
        if ticker == "CASH":
            continue
        if ticker not in target_weight.keys():
            Sell[ticker] = Hold[ticker]

    print(f"Buy: {Buy}")
    print(f"Sell: {Sell}")

    # Pre-market Round1 order splits
    round_split =USLA.make_split_data(order_time['market'], order_time['round'])
    sell_splits = round_split['sell_splits']
    sell_price_adjust = round_split['sell_price_adjust']
    buy_splits = round_split['buy_splits']
    buy_price_adjust = round_split['buy_price_adjust']

    # 매도 주문하기
    Sell_order = []
    if len(Sell.keys()) > 0:
        for ticker in Sell.keys():
            qty_per_split = int(Sell[ticker] // sell_splits)
            current_price = USLA.get_US_open_price(ticker)
            for i in range(sell_splits):
                if i == sell_splits - 1:
                    quantity = Sell[ticker] - qty_per_split * (sell_splits - 1)
                else:
                    quantity = qty_per_split
                price = round(current_price * sell_price_adjust[i], 2)
                # Sell_order.append(USLA.order_daytime_sell_US(ticker, quantity, price))
                print(f"{i}회차 분할 sell {ticker} {quantity} {price}")

    # 매수 주문하기 코드 앞 도입부 함수로 빼기
    Buy_order = []
    if len(Buy.keys()) > 0:
        for ticker in Buy.keys():
            qty_per_split = int(Buy[ticker] // buy_splits)
            current_price = USLA.get_US_open_price(ticker)
            for i in range(buy_splits):
                if i == buy_splits - 1:
                    quantity = Buy[ticker] - qty_per_split * (buy_splits - 1)
                else:
                    quantity = qty_per_split
                price = round(current_price * buy_price_adjust[i], 2)
                # Buy_order.append(USLA.order_daytime_buy_US(ticker, quantity, price))
                print(f"{i}회차 분할 buy {ticker} {quantity} {price}")

    ### 주문 후 CASH 재계산 ####
    
    
    
    # TR data 만들기(임시 데이터)
    TR_data = {
        'market': order_time['market'],
        'round': order_time['round'],
        'Sell_order': Sell_order,
        'Buy_order': Buy_order,
        'Hold': Hold,
        'target_weight': target_weight,
        'CASH': Hold['CASH'] ##### 재계산
    } 
    USLA.save_kis_tr_json(TR_data)

elif order_time['market'] == "Pre-market" and order_time['round'] in range(2, 67):
    TR_data = USLA.load_USLA_data()
    Sell_order = TR_data['Sell_order']
    Buy_order = TR_data['Buy_order']

    # 지난 매도 주문체결내역 확인 > 매도 체결 금액 확인  > 매도 없었으면 시스템종료!!!!
    sell_summary = USLA.calculate_sell_summary(Sell_order)

    if not sell_summary['success']: # 체결 매도금액이 없으면 빠른 종료
        print("체결된 매도 주문이 없습니다.")
        sys.exit(0)

    # 간단 출력 #
    print(f"\n 매도 체결 완료: {sell_summary['count']}개 주문\n")
    print(f"\n 총 매도 금액: ${sell_summary['total_amount']:,.2f}\n")
    total_sell_amount = sell_summary['total_amount']
    # for ticker, data in sell_summary['by_ticker'].items():
    #     print(f"  {ticker}: {data['quantity']}주 x ${data['avg_price']:.2f} = ${data['amount']:,.2f}")

    ################################################### 총매도금액 + TR CASH(지난 번 안 쓴 USD) >> 가용 추가금액
    cash = Hold['CASH']
    total_sell_amount += cash
    Hold['CASH'] = total_sell_amount



    # 매수주문확인
    

    
    # 지난 매수 주문체결내역 확인 > 티커별 매수 체결 수량 확인 Claude로 
    # > 매도체결금액+USLA_USD+매수주문대기 = 3가지 합쳐서 USD환산 잔고 * 티커별 비중 > 다시 티버별 매수 수량추가
    # 추가 매수주문 > 다시TRdata 저장



