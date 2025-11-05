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
            
            # 시장 시간대에 따라 주문
            result = USLA.order_sell_US(ticker, quantity, price)
            
            if result:
                Sell_order.append(result)
            else:
                pass
            
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
            # KA.SendMessage(f"{ticker} 가격 조회 실패")
            Buy_value[ticker] = 0
            ticker_prices[ticker] = 0

        time_module.sleep(0.1)

    TR_usd = Hold['CASH'] - target_usd # USD현재보유량에서 목표보유량을 뺀 매수 가능 USD 산출
    if TR_usd < 0: # 거래 가능 usd가 음수인경우 0으로 변환
        TR_usd = 0
        # KA.SendMessage(f"매수 가능 USD 부족: ${Hold['CASH']:.2f} (목표: ${target_usd:.2f})")

    Buy_qty = dict() # 금회 티커별 매수거래 수량

    if total_Buy_value == 0:
        # KA.SendMessage("매수 가능한 종목이 없습니다.")
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
    - TR_usd: 남은 거래 가능 USD
    """
    Buy_order = []
    
    # 매수 가능 USD 계산
    if TR_usd < 0:
        TR_usd = 0
        # print("매수 가능 USD 부족")
    
    # 매수할 종목이 없으면 조기 반환
    if len(Buy_qty.keys()) == 0:
        KA.SendMessage("매수할 종목이 없습니다.")
        return Buy_order, TR_usd
    
    # 매수 주문 실행
    for ticker in Buy_qty.keys():
        # 매수 수량이 0이면 스킵
        if Buy_qty[ticker] == 0:
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
            
            # 시장 시간대에 따라 주문
            result = USLA.order_buy_US(ticker, quantity, price)
            
            if result:
                Buy_order.append(result)
                TR_usd -= order_cost
            else:
                pass
            
            time_module.sleep(0.2)
    
    return Buy_order, TR_usd

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

def save_TR_data(order_time, Sell_order, Buy_order, Hold, target_weight, TR_usd): # 필요한 TR data 만들고 저장
    TR_data = {
        'round': order_time['round'],
        'Sell_order': Sell_order, # 매도주문내역
        'Buy_order': Buy_order, # 매수주문내역
        'Hold': Hold, #현재 티커별 잔고
        'target_weight': target_weight, #최초 타겟 티커별 비중
        'CASH': Hold['CASH'], # 체결 전 포함 모든 usd
        'TR_usd': TR_usd # 모든거래 후 예상 매수잔액
    } 
    USLA.save_USLA_TR_json(TR_data) # json 파일로 저장
    KA.SendMessage(f"{order_time['date']}, {order_time['season']} 리밸런싱 {order_time['market']} \n{order_time['time']} {order_time['round']}/{order_time['total_round']}회차 거래완료")
    return TR_data

def health_check():
    """시스템 상태 확인"""
    checks = []
    
    # 1. API 토큰 유효성
    if not USLA.access_token:
        checks.append("USAA 체크: API 토큰 없음")
    
    # 2. JSON 파일 존재
    import os
    files = [
        "/var/autobot/TR_USLA/USLA_rebalancing_day.json",
        "/var/autobot/TR_USLA/USLA_data.json",
        "/var/autobot/TR_USLA/USLA_TR.json"
    ]
    for f in files:
        if not os.path.exists(f):
            checks.append(f"USLA 체크: json 파일 없음: {f}")
    
    # 3. 네트워크 연결
    try:
        import socket
        socket.create_connection(("openapi.koreainvestment.com", 9443), timeout=5)
    except:
        checks.append("USLA 체크: KIS API 서버 접속 불가")
    
    if checks:
        KA.SendMessage("\n".join(checks))
        sys.exit(1)
    
    # KA.SendMessage("USLA 체크: 이상없슴")

# 확인
order_time = KIS_Calender.check_order_time()
order_time['time'] = order_time['time'].replace(second=0, microsecond=0)

if order_time['season'] == "USLA_not_rebalancing":
    KA.SendMessage(f"USLA 리밸런싱일이 아닙니다. \n{order_time['date']}가 USLA_rebalancing_day 리스트에 없습니다.")
    sys.exit(0)

# 메인 로직 시작 전 시스템 상태 확인
health_check()
KA.SendMessage(f"USLA {order_time['date']} 리밸런싱 \n{order_time['time']}, {order_time['round']}/{order_time['total_round']}회차 거래시작")

if order_time['round'] == 1: # round 1회에만 Trading qty를 구하기
    # 목표 데이터 만들기
    target_weight, regime_signal = USLA.target_ticker_weight() # 목표 티커 비중 반환
    USLA_data = USLA.load_USLA_data() # 1회차는 지난 리밸런싱 후의 USLA model usd 불러오기
    Hold_usd = USLA_data['CASH']
    target_ticker = list(target_weight.keys())
    is_daytime = True

    Hold, target_usd, Buy, Sell, sell_split, buy_split = round_TR_data(Hold_usd, target_weight)

    # USLA_data update 1차 당일 리밸런싱 데이터로@update
    USLA_data = {
        'date': str(order_time['date']),
        'regime_signal': regime_signal,
        'target_ticker1': target_ticker[0],
        'target_weight1': target_weight[target_ticker[0]],
        'target_ticker2': target_ticker[1],
        'target_weight2': target_weight[target_ticker[1]],
        'UPRO': Hold['UPRO'],
        'TQQQ': Hold['TQQQ'],
        'EDC': Hold['EDC'],
        'TMF': Hold['TMF'],
        'TMV': Hold['TMV'],
        'CASH': Hold['CASH'],
        'balance': USLA_data['balance'],
        'last_day_balance': USLA_data['last_day_balance'],
        'last_month_balance': USLA_data['last_month_balance'],
        'last_year_balance': USLA_data['last_year_balance'],
        'daily_return': USLA_data['daily_return'],
        'monthly_return': USLA_data['monthly_return'],
        'yearly_return': USLA_data['yearly_return'],
        'exchange_rate': USLA_data['exchange_rate'],
        'balance_KRW': USLA_data['balance_KRW'],
        'last_day_balance_KRW': USLA_data['last_day_balance_KRW'],
        'last_month_balance_KRW': USLA_data['last_month_balance_KRW'],
        'last_year_balance_KRW': USLA_data['last_year_balance_KRW'],
        'daily_return_KRW': USLA_data['daily_return_KRW'],
        'monthly_return_KRW': USLA_data['monthly_return_KRW'],
        'yearly_return_KRW': USLA_data['yearly_return_KRW']
    }

    USLA.save_USLA_data_json(USLA_data)

    # Sell Pre market 주문, Sell주문데이터
    Sell_order = Selling(Sell, sell_split)
    # USD현재보유량과 목표보유량 비교 매수량과 매수 비중 매수금액 산출
    Buy_qty, TR_usd = calculate_Buy_qty(Buy, Hold, target_usd)
    # Buy Pre market 주문, Buy주문데이터+TR_usd주문한 usd
    Buy_order, TR_usd = Buying(Buy_qty, buy_split, TR_usd)

    # 데이터 저장
    save_TR_data(order_time, Sell_order, Buy_order, Hold, target_weight, TR_usd)
    sys.exit(0)
    
elif order_time['round'] in range(2, 25): # Round 2~24회차
    # 지난 주문 취소하기
    try:
        cancle_result = USLA.cancel_all_unfilled_orders(auto_retry=True)
    except Exception as e:
        KA.SendMessage(f"USLA 주문 취소 오류: {e}")

    # 지난 라운드 TR_data 불러오기
    try:
        TR_data = USLA.load_USLA_TR()
        Sell_order = TR_data['Sell_order']
        Buy_order = TR_data['Buy_order']
        Hold_usd = TR_data['CASH']
        target_weight = TR_data['target_weight']
        is_daytime = True
    except Exception as e:
        KA.SendMessage(f"USLA_TR JSON 파일 오류: {e}")
        sys.exit(0)

    # 매수 매도 체결결과 반영 금액 산출
    sell_summary = USLA.calculate_sell_summary(Sell_order)
    Hold_usd += sell_summary['net_amount']  # 매도: 실제 입금액 (수수료 차감)
    buy_summary = USLA.calculate_buy_summary(Buy_order)
    Hold_usd -= buy_summary['total_amount']  # 매수: 실제 출금액 (체결가에 수수료 포함)

    # 목표 비중 만들기
    Hold, target_usd, Buy, Sell, sell_split, buy_split = round_TR_data(Hold_usd, target_weight)

    # Sell Pre market 주문, Sell주문데이터
    Sell_order = Selling(Sell, sell_split)

    # USD현재보유량과 목표보유량 비교 매수량과 매수 비중 매수금액 산출
    Buy_qty, TR_usd = calculate_Buy_qty(Buy, Hold, target_usd)
    # Buy Pre market 주문, Buy주문데이터+TR_usd주문한 usd
    Buy_order, TR_usd = Buying(Buy_qty, buy_split, TR_usd)

    # 데이터 저장
    save_TR_data(order_time, Sell_order, Buy_order, Hold, target_weight, TR_usd)
    sys.exit(0)

elif order_time['round'] == 25: # 25회차 최종기록
    # 지난 주문 취소하기
    try:
        cancle_result = USLA.cancel_all_unfilled_orders(auto_retry=True)
    except Exception as e:
        KA.SendMessage(f"USLA 주문 취소 오류: {e}")

    # 지난 라운드 TR_data 불러오기
    try:
        TR_data = USLA.load_USLA_TR()
        Sell_order = TR_data['Sell_order']
        Buy_order = TR_data['Buy_order']
        Hold_usd = TR_data['CASH']
    except Exception as e:
        print(f"USLA_TR JSON 파일 오류: {e}")
        sys.exit(0)

    # 매수 매도 체결결과 반영 금액 산출
    sell_summary = USLA.calculate_sell_summary(Sell_order)
    Hold_usd += sell_summary['net_amount']  # 입금 (수수료 차감됨)
    buy_summary = USLA.calculate_buy_summary(Buy_order)
    Hold_usd -= buy_summary['total_amount']  # 출금 (수수료 포함됨)

    # USLA_data(월 리벨런싱 데이터)로 json저장
    USLA_data = USLA.load_USLA_data()

    Hold = USLA.get_total_balance()
    Hold_tickers = {}
    if len(Hold['stocks']) > 0:
        for stock in Hold['stocks'] : # Hold['stocks']는 list
            ticker = stock['ticker']
            qty = stock['quantity']
            Hold_tickers[ticker] = qty
    else:
        pass

    UPRO = Hold_tickers.get('UPRO', 0)
    TQQQ = Hold_tickers.get('TQQQ', 0)
    EDC = Hold_tickers.get('EDC', 0)
    TMF = Hold_tickers.get('TMF', 0)
    TMV = Hold_tickers.get('TMV', 0)
    balance = Hold['stock_eval_usd']+Hold_usd
    USLA_data = {
        'date': str(order_time['date']),
        'regime_signal': USLA_data['regime_signal'],
        'target_ticker1': USLA_data['target_ticker1'],
        'target_weight1': USLA_data['target_weight1'],
        'target_ticker2': USLA_data['target_ticker2'],
        'target_weight2': USLA_data['target_weight2'],
        'UPRO': UPRO,
        'TQQQ': TQQQ,
        'EDC': EDC,
        'TMF': TMF,
        'TMV': TMV,
        'CASH': Hold_usd,
        'balance': balance,
        'last_day_balance': USLA_data['last_day_balance'], # 따로 데일리 리턴 계산 안 할 거면 그대로, 지금 계산할거면 ['balance']f로 바꿀 것
        'last_month_balance': USLA_data['last_month_balance'],
        'last_year_balance': USLA_data['last_year_balance'],
        'daily_return': USLA_data['daily_return'],
        'monthly_return': USLA_data['monthly_return'],
        'yearly_return': USLA_data['yearly_return'],
        'exchange_rate': Hold['exchange_rate'],
        'balance_KRW': Hold['stock_eval_krw']+(Hold_usd*Hold['exchange_rate']),
        'last_day_balance_KRW': USLA_data['last_day_balance_KRW'], # 따로 데일리 리턴 계산 안 할 거면 그대로, 지금 계산할거면 ['balance']f로 바꿀 것
        'last_month_balance_KRW': USLA_data['last_month_balance_KRW'],
        'last_year_balance_KRW': USLA_data['last_year_balance_KRW'],
        'daily_return_KRW': USLA_data['daily_return_KRW'],
        'monthly_return_KRW': USLA_data['monthly_return_KRW'],
        'yearly_return_KRW': USLA_data['yearly_return_KRW']
    }
    USLA.save_USLA_data_json(USLA_data) # 일단 저장 수익률과 일간 월간 연간 변화는 다른 일일 기록 코드로(카톡, 수익 기록용)

# 카톡 리밸 종료 결과 보내기 최초 홀딩 잔고 티커2 + 현금 > 최후 잔고티커2 + 현금변화 기록
KA.SendMessage(f"KIS USLA {order_time['date']} \n당월 리벨런싱 완료")
KA.SendMessage(f"KIS USLA regime_signal: {USLA_data['regime_signal']} \ntarget1: {USLA_data['target_ticker1']}, {USLA_data['target_weight1']} \ntarget2: {USLA_data['target_ticker2']}, {USLA_data['target_weight2']}")
KA.SendMessage(f"KIS USLA balance: {balance} \nUPRO: {UPRO}, TQQQ: {TQQQ}, EDC: {EDC}, TMF: {TMF}, TMV: {TMV}")


# 3차 오류 테스트 AWS ec2 실제 서버 오류잡기 &  필요한 것만 & crontab 테스트
# 투자결과는 다른 코드로 현금에 배당 등으로 변화 생긴 경우 변경 시 코드 수정할 부분 알림 메세지도 add_usd = 0,  usd += add_usd
# 실제 투자결과는 daily spreas sheet로 기록
# 신한>한투 이체 실제 진행 11월 중

# US HAA전략도 합치는 방법 연구 후 테스트 실제화 11월 중

# QT도 코딩...... 1~2월 중