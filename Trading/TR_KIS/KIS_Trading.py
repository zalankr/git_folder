from datetime import datetime, timedelta
import time as time_module  # time 모듈을 별칭으로 import
import json
import sys
import KIS_Calender
import USLA_model
import KIS_US

"""
crontab 설정
30분 단위 > 전회 주문 데이터 불러오기 주문취소 후 매수 매도 체결금액 usd에 더하기 빼기 할 것 > 비중 계산 주문
0,30 9-21 1 11 * python3 /TR_KIS/KIS_Trading.py 일반 시간대 UTC 21시 정규장 종료 > 장종류 time.sleep하고 난 후주문 취소 체결확인 기록 등 시행 
0,30 8-20 1 4 * python3 /TR_KIS/KIS_Trading.py 서머타임 시간대 UTC 20시 정규장 종료 > 장종류 time.sleep하고 난 후주문 취소 체결확인 기록 등 시행 
"""

# USLA모델 instance 생성
key_file_path = "C:/Users/ilpus/Desktop/NKL_invest/kis63721147nkr.txt"
token_file_path = "C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/kis63721147_token.json"
cano = "63721147"  # 종합계좌번호 (8자리)
acnt_prdt_cd = "01"  # 계좌상품코드 (2자리)
USLA = USLA_model.USLA_Model(key_file_path, token_file_path, cano, acnt_prdt_cd)
USLA_ticker = ["UPRO", "TQQQ", "EDC", "TMF", "TMV"]

def real_Hold(): # 실제 잔고 확인 함수, Hold 반환
    real_balance = USLA.get_US_stock_balance()
    Hold = dict()
    for i in range(len(real_balance)):
        ticker = real_balance[i]['ticker']
        if real_balance[i]['ticker'] in USLA_ticker:
            Hold[ticker] = real_balance[i]['quantity']
    return Hold

def make_target_data(Hold): # target weight, target qty, target usd 만들기
    # Target ticker와 weight dict 만들기
    target_weight = USLA.target_ticker_weight() # 목표 티커 비중 반환O
    print(target_weight)
    # 현재 USD환산 USLA 잔고
    hold_usd_value = USLA.calculate_USD_value(Hold) # 반환X
    print(hold_usd_value)
    # USLA USD 잔고 X 티커별 비중 = target qty
    target_usd_value = {ticker: target_weight[ticker] * hold_usd_value for ticker in target_weight.keys()} # target_ticker별 USD 배정 dict, 반환X
    target_qty = USLA.calculate_target_qty(target_weight, target_usd_value) # target_ticker별 quantity 반환O
    target_usd = target_qty["CASH"] # 반환O

    return target_weight, target_qty, target_usd

def make_Buy_Sell(target_weight, target_qty, Hold): # target qty, hold qty 비교 조정 후 Buy와 Sell dict 만들고 반환하는 함수
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
    return Buy, Sell

def Sell_daytime(Sell, sell_split): # Pre market 매도 주문하기
    Sell_order = []
    if len(Sell.keys()) > 0:
        for ticker in Sell.keys():
            qty_per_split = int(Sell[ticker] // sell_split[0])
            current_price = USLA.get_US_open_price(ticker)
            for i in range(sell_split[0]):
                if i == sell_split[0] - 1:
                    quantity = Sell[ticker] - qty_per_split * (sell_split[0] - 1)
                else:
                    quantity = qty_per_split
                price = round(current_price * sell_split[1][i], 2)
                if quantity == 0:
                    continue
                Sell_order.append(USLA.order_daytime_sell_US(ticker, quantity, price))
                print(f"{i}회차 분할 sell {ticker} {quantity} {price}")
                time_module.sleep(0.2)
    return Sell_order

def calculate_Buy_qty(Buy, Hold, target_usd): # USD현재보유량과 목표보유량 비교 매수 수량과 매수 비중 매수 금액 산출
    Buy_value = dict() # 티커별 매수거래 usd환산액 
    total_Buy_value = 0 # 전체 매수거래 usd환산액 
    for ticker in Buy.keys():
        Buy_value[ticker] = Buy[ticker] * USLA.get_US_open_price(ticker) # 티커별 매수 주식수 usd환산액
        total_Buy_value += Buy_value[ticker] # 티커별 매수 주식수 usd환산액의 합
        time_module.sleep(0.1)

    TR_usd = Hold['CASH'] - target_usd # USD현재보유량에서 목표보유량을 뺀 매수 가능 USD 산출
    if TR_usd < 0: # 거래 가능 usd가 음수인경우 0으로 변환
        TR_usd = 0
    Buy_weight = dict() # 금회 티커별 매수거래 비중
    Buy_usd = dict() # 금회 티커별 매수거래 USD
    Buy_qty = dict() # 금회 티커별 매수거래 수량
    for ticker in Buy_value.keys():
        Buy_weight[ticker] = Buy_value[ticker] / total_Buy_value # 전체 USD중 티커별 매수거래 비중
        Buy_usd[ticker] = TR_usd * Buy_weight[ticker] # 금회 티커별 매수거래 비중을 곱한 USD, 0이거나 값이 있거나
        Buy_qty[ticker] = Buy_usd[ticker] // (USLA.get_US_open_price(ticker)*(1+USLA.tax_rate)) # 금회 티커별 매수거래 수량, 0이거나 값이 있거나
        time_module.sleep(0.1)

    return Buy_qty, Buy_weight, Buy_usd

def Buy_daytime(Buy_qty, buy_split): # Pre market 매도 주문하기
    Buy_order = []
    for ticker in Buy_qty.keys():
        qty_per_split = int(Buy_qty[ticker] // buy_split[0]) # 분할 횟수당 수량, 0이거나 값이 있거나
        current_price = USLA.get_US_open_price(ticker) # 현재가
        for i in range(buy_split[0]):
            if i == buy_split[0] - 1: # 마지막 주문 나머지 수량으로 조정
                quantity = Buy_qty[ticker] - qty_per_split * (buy_split[0] - 1)
            else:
                quantity = qty_per_split
            if quantity == 0: 
                continue
            price = round(current_price * buy_split[1][i], 2) # 분할당 가격: 미국주식 매수가격 기준인 소숫점 2자리로 주문 가격 만들기
            Buy_order.append(USLA.order_daytime_buy_US(ticker, quantity, price)) # 매수 주문
            print(f"{i}회차 분할 buy {ticker} {quantity} {price}")
            TR_usd -= quantity * (price * (1+USLA.tax_rate)) # 주문 후 usd 변화 계산
            time_module.sleep(0.2) 
    return Buy_order, TR_usd



# 밑에 부분 테스트용, 정식버전은 KIS_Calender해당 메써드의 current_date, current_time 수정
# 별도 일수익변화 체크 코드는 따로 운영
order_time = KIS_Calender.check_order_time()
if order_time['season'] == "USAA_not_rebalancing":
    print("오늘은 리밸런싱일이 아닙니다. 프로그램을 종료합니다.")
    sys.exit(0)

print(f"USLA {order_time['market']} 리밸런싱 {order_time['round']}/{order_time['total_round']}회차")
print(f"{order_time['date']}, {order_time['season']} 리밸런싱 {order_time['market']} \n{order_time['time']} {order_time['round']}/{order_time['total_round']}회차 거래시작")

if order_time['market'] == "Pre-market" and order_time['round'] == 1: # Pre-market round 1회에만 Trading qty를 구하기
    # Hold 실제 잔고 dict 만들기
    Hold = real_Hold()
    # Hold 잔고에 CASH usd 추가
    TR_data = USLA.load_USLA_data() # 1회차는 지난 리밸런싱 후의 USLA model usd 불러오기
    Hold['CASH'] = TR_data['CASH'] # 현재 잔고 TR_data초기버전에는 dict에는 'CASH'만 있으면 됨, make trading data 함수 불필요

    # 목표 비중, 수량, 달러화 산출 후 현재 잔고와 비교 조정한 매수 매도 수량 있는 Buy와 Sell dict 만들기
    target_weight, target_qty, target_usd = make_target_data(Hold)
    Buy, Sell = make_Buy_Sell(target_weight, target_qty, Hold)
    print(f"Buy: {Buy}")
    print(f"Sell: {Sell}")

    # Pre-market Round1 order splits
    round_split =USLA.make_split_data(order_time['market'], order_time['round'])
    sell_split = [round_split['sell_splits'], round_split['sell_price_adjust']]
    buy_split = [round_split['buy_splits'], round_split['buy_price_adjust']]

    # Sell Pre market 주문, Sell주문데이터
    Sell_order = Sell_daytime(Sell, sell_split)

    # USD현재보유량과 목표보유량 비교 매수 수량과 매수 비중 매수 금액 산출
    Buy_qty, Buy_weight, Buy_usd = calculate_Buy_qty(Buy, Hold, target_usd)

    # Buy Pre market 주문, Buy주문데이터+TR_usd주문한 usd
    Buy_order, TR_usd = Buy_daytime(Buy_qty, buy_split)
    
    # 필요한 TR data 만들고 저장
    TR_data = {
        'market': order_time['market'],
        'round': order_time['round'],
        'Sell_order': Sell_order, # 매도주문내역
        'Buy_order': Buy_order, # 매수주문내역
        'Hold': Hold, #현재 티커별 잔고
        'target_weight': target_weight, #최초 타겟 티커별 비중
        'CASH': Hold['CASH'], # 체결 전 포함 모든 usd
        'TR_usd': TR_usd # 체결주문 중인 usd
    } 
    USLA.save_kis_tr_json(TR_data) # json 파일로 저장
    print(f"{order_time['date']}, {order_time['season']} 리밸런싱 {order_time['market']} \n{order_time['time']} {order_time['round']}/{order_time['total_round']}회차 거래롼료.")


elif order_time['market'] == "Pre-market" and order_time['round'] in range(2, 12): # Pre-market Round2~66
    # Pre-market 09:00~14:30 / 30분 단위 > 전회 주문 데이터 불러오기 주문취소 후 매수 매도 체결금액 usd에 더하기 빼기 할 것 > 비중 계산 주문

    # 지난 주문 취소하기
    

    # 지난 라운드 TR_data 불러오기
    file_path = "C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/USLA_TR_data.json"
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            TR_data = json.load(f)
    except Exception as e:
        print(f"JSON 파일 오류: {e}")
        exit()








    # 체결내역 확인
    # Hold['CASH']에서 매도금액은 더하고 매수금액은 빼기
    # 실제 티커별 잔고 불러오기 Hold + Hold['CASH']추가하기

    # 다시 이 번 라운드 목표 비중, 수량, 달러화 산출 후 현재 잔고와 비교 조정한 매수 매도 수량 있는 Buy와 Sell dict 만들기
    # Pre-market Round2~66 order splits
    # Sell 전 티커별 현재 주문 잔여 미체결 수량과 목표 매도주문 수량 비교 후 동일하면 유지
    # TR_data의 Sell_order의 티커별 주문수량, 금액과 체결내역의 주문수량과 금액 비교 후 차감해 남은 주문량 산출 > 모든 값의 usd환산가치 계산
    # Sell Pre market 주문, Sell주문데이터
    # 다시 금번 라운드용 USD현재보유량과 목표보유량 비교 매수 수량과 매수 비중 매수 금액 산출
    # Buy Pre market 주문, Buy주문데이터+TR_usd주문한 usd
    # 필요한 TR data 만들기



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



