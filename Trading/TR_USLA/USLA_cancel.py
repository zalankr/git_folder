import time as time_module  # time 모듈을 별칭으로 import
import kakao_alert as KA
import sys
import KIS_Calender
import USLA_model
from tendo import singleton

try:
    me = singleton.SingleInstance()
except singleton.SingleInstanceException:
    KA.SendMessage("USLA: 이미 실행 중입니다.")
    sys.exit(0)

# USLA모델 instance 생성
key_file_path = "/var/autobot/TR_USLA/kis63721147nkr.txt"
token_file_path = "/var/autobot/TR_USLA/kis63721147_token.json"
cano = "63721147"  # 종합계좌번호 (8자리)
acnt_prdt_cd = "01"  # 계좌상품코드 (2자리)
USLA_ticker = ["UPRO", "TQQQ", "EDC", "TMF", "TMV"]
USLA = USLA_model.USLA_Model(key_file_path, token_file_path, cano, acnt_prdt_cd)

def real_Hold(): # 실제 잔고 확인 함수, Hold 반환
    real_balance = USLA.get_US_stock_balance()
    Hold = {
        "UPRO": 0,
        "TQQQ": 0,
        "EDC": 0,
        "TMF": 0,
        "TMV": 0
    }
    for i in range(len(real_balance)):
        ticker = real_balance[i]['ticker']
        if real_balance[i]['ticker'] in USLA_ticker:
            Hold[ticker] = real_balance[i]['quantity']
    Hold['CASH'] = 0 # 기본값 초기값
    return Hold

def make_target_data(Hold, target_weight): # target qty, target usd 만들기 #### target_weight타
    # 현재 USD환산 USLA 잔고
    hold_usd_value = USLA.calculate_USD_value(Hold) # USD 환산 잔고
    # USLA USD 잔고 X 티커별 비중 = target qty
    target_usd_value = {ticker: target_weight[ticker] * hold_usd_value for ticker in target_weight.keys()} # target_ticker별 USD 배정 dict, 반환X
    target_qty = USLA.calculate_target_qty(target_weight, target_usd_value) # target_ticker별 quantity 반환O
    target_usd = target_qty["CASH"] # 반환O

    return target_qty, target_usd

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
            if Hold[ticker] > 0:
                Sell[ticker] = Hold[ticker]
    return Buy, Sell

def Selling(Sell, sell_split):
    """
    매도 주문 실행 함수
    
    Parameters:
    - Sell: 매도할 종목과 수량 딕셔너리 {ticker: quantity}
    - sell_split: [분할횟수, [가격조정비율 리스트]]
    - is_daytime: True면 주간거래, False면 정규장
    
    Returns:
    - Sell_order: 주문 결과 리스트
    """
    Sell_order = []
    
    # 매도할 종목이 없으면 빈 리스트 반환
    if len(Sell.keys()) == 0:
        KA.SendMessage("매도할 종목이 없습니다.") 
        return Sell_order
    
    # 매도 주문 실행
    for ticker in Sell.keys():
        # 매도 수량이 0이면 스킵
        if Sell[ticker] == 0:
            KA.SendMessage(f"{ticker} 매도 수량 0")
            continue        

        qty_per_split = int(Sell[ticker] // sell_split[0])
        current_price = USLA.get_US_current_price(ticker)

        # 가격 조회 실패 시 스킵
        if not isinstance(current_price, (int, float)) or current_price <= 0:
            KA.SendMessage(f"USLA {ticker} 가격 조회 실패 - 매도 주문 스킵")
            continue        
        
        for i in range(sell_split[0]):
            # 마지막 분할은 남은 수량 전부
            if i == sell_split[0] - 1:
                quantity = Sell[ticker] - qty_per_split * (sell_split[0] - 1)
            else:
                quantity = qty_per_split
            
            # 수량이 0이면 스킵
            if quantity == 0:
                continue
            
            # 주문 가격 계산
            price = round(current_price * sell_split[1][i], 2)
            
            # 주문
            result = USLA.order_sell_US(ticker, quantity, price)
            
            if result.get('success') == True:
                # Response 객체를 제거하고 저장 (JSON 직렬화 오류 방지)
                order_info = {k: v for k, v in result.items() if k != 'response'}
                Sell_order.append(order_info)
            else:
                # 에러 로깅 강화
                KA.SendMessage(f"{ticker} 매도 주문 실패: {result.get('message', 'Unknown error')}")
            
            time_module.sleep(0.2)
    
    return Sell_order

def calculate_Buy_qty(Buy, Hold, target_usd): # USD현재보유량과 목표보유량 비교 매수 수량과 매수 비중 매수 금액 산출
    Buy_value = {} # 티커별 매수거래 usd환산액 
    total_Buy_value = 0 # 전체 매수거래 usd환산액 

    ticker_prices = {}  # 가격 캐싱

    for ticker in Buy.keys():
        price = USLA.get_US_current_price(ticker)

        if isinstance(price, (int, float)) and price > 0:
            ticker_prices[ticker] = price  # 가격 저장
            Buy_value[ticker] = Buy[ticker] * price
            total_Buy_value += Buy_value[ticker]
        else:
            KA.SendMessage(f"{ticker} 가격 조회 실패")
            Buy_value[ticker] = 0
            ticker_prices[ticker] = 0

        time_module.sleep(0.1)

    TR_usd = Hold['CASH'] - target_usd # USD현재보유량에서 목표보유량을 뺀 매수 가능 USD 산출
    if TR_usd < 0: # 거래 가능 usd가 음수인경우 0으로 변환
        TR_usd = 0
        KA.SendMessage(f"매수 가능 USD 부족: ${Hold['CASH']:.2f} (목표: ${target_usd:.2f})")

    Buy_qty = dict() # 금회 티커별 매수거래 수량

    if total_Buy_value == 0:
        KA.SendMessage("매수 가능한 종목이 없습니다.")
        return Buy_qty, TR_usd

    for ticker in Buy_value.keys():
        Buy_weight = Buy_value[ticker] / total_Buy_value
        Buy_usd = TR_usd * Buy_weight
        
        price = ticker_prices[ticker]  # 캐싱된 가격 사용
        
        if price > 0:
            Buy_qty[ticker] = int(Buy_usd / price)
        else:
            Buy_qty[ticker] = 0
        
        time_module.sleep(0.1)

    return Buy_qty, TR_usd

def Buying(Buy_qty, buy_split, TR_usd):
    """
    매수 주문 실행 함수
    
    Parameters:
    - Buy_qty: 매수할 종목과 수량 딕셔너리 {ticker: quantity}
    - buy_split: [분할횟수, [가격조정비율 리스트]]
    - TR_usd: 매수가능 금액
    - is_daytime: True면 주간거래, False면 정규장
    
    Returns:
    - Buy_order: 주문 결과 리스트
    """
    Buy_order = []
    
    # 매수 가능 USD 계산
    if TR_usd < 0:
        TR_usd = 0
        KA.SendMessage("매수 가능 USD 부족")
    
    # 매수할 종목이 없으면 조기 반환
    if len(Buy_qty.keys()) == 0:
        KA.SendMessage("매수할 종목이 없습니다.")
        return Buy_order
    
    # 매수 주문 실행
    for ticker in Buy_qty.keys():
        # 매수 수량이 0이면 스킵
        if Buy_qty[ticker] == 0:
            KA.SendMessage(f"{ticker} 매수 수량 0")
            continue
        
        qty_per_split = int(Buy_qty[ticker] // buy_split[0])
        current_price = USLA.get_US_current_price(ticker)
        
        # 가격 조회 실패 시 스킵
        if not isinstance(current_price, (int, float)) or current_price <= 0:
            KA.SendMessage(f"{ticker} 가격 조회 실패 - 주문 스킵")
            continue
        
        for i in range(buy_split[0]):
            # 마지막 분할은 남은 수량 전부
            if i == buy_split[0] - 1:
                quantity = Buy_qty[ticker] - qty_per_split * (buy_split[0] - 1)
            else:
                quantity = qty_per_split
            
            if quantity == 0:
                continue
            
            # 주문 가격 계산
            price = round(current_price * buy_split[1][i], 2)
            
            # USD 잔액 체크
            order_cost = quantity * price
            if TR_usd < order_cost:
                KA.SendMessage(f"USD 부족 - {ticker} {quantity}주 주문 스킵 (필요: ${order_cost:.2f}, 잔액: ${TR_usd:.2f})")
                continue
            
            # 매수 주문
            result = USLA.order_buy_US(ticker, quantity, price)
            
            if result.get('success') == True:
                order_info = {k: v for k, v in result.items() if k != 'response'}
                Buy_order.append(order_info)

            else:
                KA.SendMessage(f"{ticker} 주문 실패: {result.get('message', 'Unknown error')}")
            
            time_module.sleep(0.1)
    
    return Buy_order

def round_TR_data(Hold_usd, target_weight): # 이번 라운드 실제 잔고 dict 만들고 USLA용 usd 추가  
    Hold = real_Hold()
    # Hold 잔고에 CASH usd 추가
    Hold['CASH'] = Hold_usd # 현재 잔고 TR_data초기버전에는 dict에는 'CASH'만 있으면 됨, make trading data 함수 불필요

    # 목표 수량, 달러화 산출 후 현재 잔고와 비교 조정한 매수 매도 수량 있는 Buy와 Sell dict 만들기
    target_qty, target_usd = make_target_data(Hold, target_weight)
    Buy, Sell = make_Buy_Sell(target_weight, target_qty, Hold)
    KA.SendMessage(f"USLA 매매목표 수량 \nBuy {Buy} \nSell {Sell}")

    # order splits 데이터 산출
    round_split =USLA.make_split_data(order_time['round'])
    sell_split = [round_split['sell_splits'], round_split['sell_price_adjust']]
    buy_split = [round_split['buy_splits'], round_split['buy_price_adjust']]
    return Hold, target_usd, Buy, Sell, sell_split, buy_split

def save_TR_data(order_time, Sell_order, Buy_order, Hold, target_weight): # 필요한 TR data 만들고 저장
    TR_data = {
        'round': order_time['round'],
        'Sell_order': Sell_order, # 매도주문내역
        'Buy_order': Buy_order, # 매수주문내역
        'Hold': Hold, #현재 티커별 잔고
        'target_weight': target_weight, #최초 타겟 티커별 비중
        'CASH': Hold['CASH'] # 체결 전 포함 모든 usd
    } 
    USLA.save_USLA_TR_json(TR_data) # json 파일로 저장
    KA.SendMessage(f"{order_time['date']}, {order_time['season']} 리밸런싱 \n{order_time['time']} {order_time['round']}/{order_time['total_round']}회차 거래저장완료")
    return TR_data


    

# 지난 주문 취소하기
try:
    cancle_result = USLA.cancel_all_unfilled_orders()
except Exception as e:
    KA.SendMessage(f"USLA 주문 취소 오류: {e}")

USLA.order_sell_US("TQQQ", 2, 105)
USLA.order_sell_US("EDC", 2, 50)
time_module.sleep(5)
print(real_Hold())
print(USLA.get_US_dollar_balance())

