import time as time_module
import kakao_alert as KA
import sys
import HAA_Calender
import HAA_model
from tendo import singleton
import json
from datetime import datetime

try:
    me = singleton.SingleInstance()
except singleton.SingleInstanceException:
    KA.SendMessage("HAA: 이미 실행 중입니다.")
    sys.exit(0)

# USLA모델 instance 생성
key_file_path = "/var/autobot/TR_USLA/kis63721147nkr.txt"
token_file_path = "/var/autobot/TR_USLA/kis63721147_token.json"
cano = "63721147"
acnt_prdt_cd = "01"
HAA_ticker = ['TIP', 'SPY', 'IWM', 'VEA', 'VWO', 'PDBC', 'VNQ', 'TLT', 'IEF', 'BIL']
HAA = HAA_model.HAA(key_file_path, token_file_path, cano, acnt_prdt_cd)

def real_Hold():
    """실제 잔고 확인 함수, Hold 반환"""
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
    Hold['CASH'] = 0  # 기본값 초기값
    return Hold

def make_target_data(Hold, target_weight): #수수료 포함
    """target qty, target usd 만들기"""
    # 현재 USD환산 USLA 잔고
    hold_usd_value = USLA.calculate_USD_value(Hold)
    # USLA USD 잔고 X 티커별 비중 = target qty
    target_usd_value = {ticker: target_weight[ticker] * hold_usd_value for ticker in target_weight.keys()}
    target_qty = USLA.calculate_target_qty(target_weight, target_usd_value)
    target_usd = target_qty["CASH"]

    return target_qty, target_usd

def make_Buy_Sell(target_weight, target_qty, Hold):
    """target qty, hold qty 비교 조정 후 Buy와 Sell dict 만들고 반환하는 함수"""
    Buy = dict()
    Sell = dict()
    # target에 있는 종목 처리
    for ticker in target_weight.keys():
        if ticker == "CASH":
            continue
        hold_qty = Hold.get(ticker, 0)
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

def Selling(Sell, sell_split, order_time):  # ✅ order_time 매개변수 추가
    """
    매도 주문 실행 함수 - 개선버전 (메시지 통합)
    
    Parameters:
    - Sell: 매도할 종목과 수량 딕셔너리 {ticker: quantity}
    - sell_split: [분할횟수, [가격조정비율 리스트]]
    - order_time: 현재 주문 시간 정보 딕셔너리  # ✅ 추가
    
    Returns:
    - Sell_order: 주문 결과 리스트 (성공/실패 모두 포함)
    """
    Sell_order = []
    order_messages = []
    
    if len(Sell.keys()) == 0:
        KA.SendMessage("매도할 종목이 없습니다.")
        return Sell_order
    
    # ✅ 수정: 함수 내부에서 호출하지 않고 매개변수로 받음
    round_info = f"{order_time['round']}/{order_time['total_round']}회 매도주문"
    order_messages.append(round_info)
    
    for ticker in Sell.keys():
        if Sell[ticker] == 0:
            order_messages.append(f"{ticker} 매도 수량 0")
            continue

        qty_per_split = int(Sell[ticker] // sell_split[0])
        current_price = USLA.get_US_current_price(ticker)

        if not isinstance(current_price, (int, float)) or current_price <= 0:
            error_msg = f"{ticker} 가격 조회 실패 - 매도 주문 스킵"
            order_messages.append(error_msg)
            Sell_order.append({
                'success': False,
                'ticker': ticker,
                'quantity': Sell[ticker],
                'price': 0,
                'order_number': '',
                'order_time': datetime.now().strftime('%H%M%S'),
                'error_message': error_msg,
                'split_index': -1
            })
            continue
        
        for i in range(sell_split[0]):
            if i == sell_split[0] - 1:
                quantity = Sell[ticker] - qty_per_split * (sell_split[0] - 1)
            else:
                quantity = qty_per_split
            
            if quantity == 0:
                continue
            
            price = round(current_price * sell_split[1][i], 2)
            
            try:
                order_info, order_sell_message = USLA.order_sell_US(ticker, quantity, price)
                
                if order_info and order_info.get('success') == True:
                    order_info = {
                        'success': True,
                        'ticker': ticker,
                        'quantity': quantity,
                        'price': price,
                        'order_number': order_info.get('order_number', ''),
                        'order_time': order_info.get('order_time', ''),
                        'org_number': order_info.get('org_number', ''),
                        'message': order_info.get('message', ''),
                        'split_index': i
                    }
                    Sell_order.append(order_info)
                    
                    # ✅ 수정: 변수명 변경 (i → j) 또는 extend 사용
                    if order_sell_message and len(order_sell_message) > 0:
                        order_messages.extend(order_sell_message)  # ✅ extend 사용
                    order_messages.append(f"✅ {ticker} {quantity}주 @${price} (분할{i+1})")
                else:
                    error_msg = order_info.get('error_message', 'Unknown error') if order_info else 'API 호출 실패'
                    if order_sell_message and len(order_sell_message) > 0:
                        order_messages.extend(order_sell_message)  # ✅ extend 사용
                    order_messages.append(f"❌ {ticker} {quantity}주 @${price} - {error_msg}")
                    Sell_order.append({
                        'success': False,
                        'ticker': ticker,
                        'quantity': quantity,
                        'price': price,
                        'order_number': '',
                        'order_time': datetime.now().strftime('%H%M%S'),
                        'error_message': error_msg,
                        'split_index': i
                    })
            except Exception as e:
                error_msg = f"Exception: {str(e)}"
                order_messages.append(f"❌ {ticker} {quantity}주 @${price} - {error_msg}")
                Sell_order.append({
                    'success': False,
                    'ticker': ticker,
                    'quantity': quantity,
                    'price': price,
                    'order_number': '',
                    'order_time': datetime.now().strftime('%H%M%S'),
                    'error_message': error_msg,
                    'split_index': i
                })
            
            time_module.sleep(0.2)
    
    success_count = sum(1 for order in Sell_order if order['success'])
    total_count = len(Sell_order)
    order_messages.append(f"매도 주문: {success_count}/{total_count} 완료")
    
    KA.SendMessage("\n".join(order_messages))
    
    return Sell_order

def calculate_Buy_qty(Buy, Hold, target_usd):
    """USD현재보유량과 목표보유량 비교 매수 수량과 매수 비중 매수 금액 산출"""
    Buy_value = {}
    total_Buy_value = 0
    ticker_prices = {}
    order_messages = []  # 주문 메시지를 모을 리스트

    for ticker in Buy.keys():
        price = USLA.get_US_current_price(ticker)

        if isinstance(price, (int, float)) and price > 0:
            ticker_prices[ticker] = price
            Buy_value[ticker] = Buy[ticker] * (price * (1 + USLA.fee))
            total_Buy_value += Buy_value[ticker]
        else:
            order_messages.append(f"❌ {ticker} 가격 조회 실패")
            Buy_value[ticker] = 0
            ticker_prices[ticker] = 0

        time_module.sleep(0.1)

    TR_usd = Hold['CASH'] - target_usd
    if TR_usd < 0:
        TR_usd = 0
        order_messages.append(f"⚠️ 매수 가능 USD 부족: ${Hold['CASH']:.2f} (목표: ${target_usd:.2f})")

    Buy_qty = dict()

    if total_Buy_value == 0:
        order_messages.append("매수 가능한 종목이 없습니다.")
        return Buy_qty, TR_usd

    for ticker in Buy_value.keys():
        Buy_weight = Buy_value[ticker] / total_Buy_value
        Buy_usd = TR_usd * Buy_weight
        
        price = ticker_prices[ticker]
        
        if price > 0:
            Buy_qty[ticker] = int(Buy_usd / (price * (1 + USLA.fee)))  # 수수료 포함
        else:
            Buy_qty[ticker] = 0
        
        time_module.sleep(0.1)
    
    # 한 번에 전송
    KA.SendMessage("\n".join(order_messages))
    return Buy_qty, TR_usd

def Buying(Buy_qty, buy_split, TR_usd, order_time):  # ✅ order_time 매개변수 추가
    """
    매수 주문 실행 함수 - 개선버전 (메시지 통합)
    
    Parameters:
    - Buy_qty: 매수할 종목과 수량 딕셔너리 {ticker: quantity}
    - buy_split: [분할횟수, [가격조정비율 리스트]]
    - TR_usd: 매수가능 금액
    - order_time: 현재 주문 시간 정보 딕셔너리  # ✅ 추가
    
    Returns:
    - Buy_order: 주문 결과 리스트 (성공/실패 모두 포함)
    """
    Buy_order = []
    order_messages = []
    
    if TR_usd < 0:
        TR_usd = 0
        order_messages.append("매수 가능 USD 부족")
    
    if len(Buy_qty.keys()) == 0:
        KA.SendMessage("매수할 종목이 없습니다.")
        return Buy_order
    
    # ✅ 수정: 함수 내부에서 호출하지 않고 매개변수로 받음
    round_info = f"{order_time['round']}/{order_time['total_round']}회 매수주문"
    order_messages.append(round_info)
    
    for ticker in Buy_qty.keys():
        if Buy_qty[ticker] == 0:
            order_messages.append(f"{ticker} 매수 수량 0")
            continue
        
        qty_per_split = int(Buy_qty[ticker] // buy_split[0])
        current_price = USLA.get_US_current_price(ticker)
        
        if not isinstance(current_price, (int, float)) or current_price <= 0:
            error_msg = f"{ticker} 가격 조회 실패 - 주문 스킵"
            order_messages.append(error_msg)
            Buy_order.append({
                'success': False,
                'ticker': ticker,
                'quantity': Buy_qty[ticker],
                'price': 0,
                'order_number': '',
                'order_time': datetime.now().strftime('%H%M%S'),
                'error_message': error_msg,
                'split_index': -1
            })
            continue
        
        for i in range(buy_split[0]):
            if i == buy_split[0] - 1:
                quantity = Buy_qty[ticker] - qty_per_split * (buy_split[0] - 1)
            else:
                quantity = qty_per_split
            
            if quantity == 0:
                continue
            
            price = round(current_price * buy_split[1][i], 2)
            
            try:
                order_info, order_buy_message = USLA.order_buy_US(ticker, quantity, price)
                
                if order_info and order_info.get('success') == True:
                    order_info = {
                        'success': True,
                        'ticker': ticker,
                        'quantity': quantity,
                        'price': price,
                        'order_number': order_info.get('order_number', ''),
                        'order_time': order_info.get('order_time', ''),
                        'org_number': order_info.get('org_number', ''),
                        'message': order_info.get('message', ''),
                        'split_index': i
                    }
                    Buy_order.append(order_info)

                    # ✅ 수정: 변수명 변경 (i → j) 또는 extend 사용
                    if order_buy_message and len(order_buy_message) > 0:
                        order_messages.extend(order_buy_message)  # ✅ extend 사용
                    order_messages.append(f"✅ {ticker} {quantity}주 @${price} (분할{i+1})")
                else:
                    error_msg = order_info.get('error_message', 'Unknown error') if order_info else 'API 호출 실패'
                    if order_buy_message and len(order_buy_message) > 0:
                        order_messages.extend(order_buy_message)  # ✅ extend 사용
                    order_messages.append(f"❌ {ticker} {quantity}주 @${price} - {error_msg}")
                    Buy_order.append({
                        'success': False,
                        'ticker': ticker,
                        'quantity': quantity,
                        'price': price,
                        'order_number': '',
                        'order_time': datetime.now().strftime('%H%M%S'),
                        'error_message': error_msg,
                        'split_index': i
                    })
            except Exception as e:
                error_msg = f"Exception: {str(e)}"
                order_messages.append(f"❌ {ticker} {quantity}주 @${price} - {error_msg}")
                Buy_order.append({
                    'success': False,
                    'ticker': ticker,
                    'quantity': quantity,
                    'price': price,
                    'order_number': '',
                    'order_time': datetime.now().strftime('%H%M%S'),
                    'error_message': error_msg,
                    'split_index': i
                })
            
            time_module.sleep(0.2)
    
    success_count = sum(1 for order in Buy_order if order['success'])
    total_count = len(Buy_order)
    order_messages.append(f"매수 주문: {success_count}/{total_count} 완료")
    
    KA.SendMessage("\n".join(order_messages))
    
    return Buy_order

def save_TR_data(order_time, Sell_order, Buy_order, Hold_usd, target_weight, target_qty):
    """
    저장 실패 시에도 백업 파일 생성
    """
    TR_data = {
        "round": order_time['round'],
        "timestamp": datetime.now().isoformat(),  # 타임스탬프 추가
        "Sell_order": Sell_order,
        "Buy_order": Buy_order,
        "CASH": Hold_usd,
        "target_weight": target_weight,
        "target_qty": target_qty
    }
    
    try:
        # 정상 저장
        save_result = USLA.save_USLA_TR_json(TR_data)
        
        if not save_result:
            raise Exception("save_USLA_TR_json returned False")
        
        KA.SendMessage(
            f"{order_time['date']}, {order_time['season']} 리밸런싱\n"
            f"{order_time['time']} {order_time['round']}/{order_time['total_round']}회차 거래저장완료\n"
        )
        
    except Exception as e:
        # 저장 실패 시 백업 파일 생성
        error_msg = f"TR 데이터 저장 실패: {e}"
        KA.SendMessage(error_msg)
        
        backup_path = f"/var/autobot/TR_USLA/USLA_TR_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(TR_data, f, ensure_ascii=False, indent=4)
            KA.SendMessage(f"백업 파일 생성: {backup_path}")
        except Exception as backup_error:
            KA.SendMessage(f"백업 파일 생성도 실패: {backup_error}")
            # 최후의 수단: 카카오로 데이터 전송
            KA.SendMessage(f"TR_data: {json.dumps(TR_data, ensure_ascii=False)[:1000]}")
    
    return TR_data

def health_check():
    """시스템 상태 확인"""
    checks = []
    
    # 1. API 토큰 유효성
    if not HAA.access_token:
        checks.append("USLA 체크: API 토큰 없음")
    
    # 2. JSON 파일 존재
    import os
    files = [
        "/var/autobot/TR_HAA/HAA_day.json",
        "/var/autobot/TR_HAA/HAA_data.json",
        "/var/autobot/TR_HAA/HAA_TR.json"
    ]
    for f in files:
        if not os.path.exists(f):
            checks.append(f"HAA 체크: json 파일 없음: {f}")
    
    # 3. 네트워크 연결
    try:
        import socket
        socket.create_connection(("openapi.koreainvestment.com", 9443), timeout=5)
    except:
        checks.append("HAA 체크: KIS API 서버 접속 불가")
    
    if checks:
        KA.SendMessage("\n".join(checks))
        sys.exit(1)

# ============================================
# 메인 로직
# ============================================

# 날짜 체크
order_time = HAA_Calender.check_order_time()
order_time['time'] = order_time['time'].replace(second=0, microsecond=0)

if order_time['season'] == "HAA_not_rebalancing" or order_time['round'] == 0:
    KA.SendMessage(f"HAA 리밸런싱일이 아닙니다.\n{order_time['date']}가 HAA_day 리스트에 없습니다.")
    sys.exit(0)

# 메인로직 시작 전 시스템 상태 확인
health_check()
KA.SendMessage(f"HAA {order_time['date']} 리밸런싱\n{order_time['time']}, {order_time['round']}/{order_time['total_round']}회차 거래시작")

if order_time['round'] == 1:  # round 1회에만 Trading qty를 구하기
    result = HAA.HAA_momentum()
    target_weight = result['target_weight']  # target_weight
    regime_signal = result['regime_score']

    HAA_data = HAA.load_HAA_data()
    Hold_usd = HAA_data['CASH']
    target_ticker = list(target_weight.keys())
##################################################################



    Hold = real_Hold()
    Hold['CASH'] = Hold_usd
    target_qty, target_usd = make_target_data(Hold, target_weight)
    Buy, Sell = make_Buy_Sell(target_weight, target_qty, Hold)

    round_split = USLA.make_split_data(order_time['round'])
    sell_split = [round_split["sell_splits"], round_split["sell_price_adjust"]]
    buy_split = [round_split["buy_splits"], round_split["buy_price_adjust"]]

    # USLA_data update 1차
    regime_signal = float("{:.2f}".format(regime_signal))
    target_weight1 = float("{:.2f}".format(target_weight[target_ticker[0]]))
    target_ticker1_qty = target_qty[target_ticker[0]]
    target_weight2 = float("{:.2f}".format(target_weight[target_ticker[1]]))
    target_ticker2_qty = target_qty[target_ticker[1]]

    # 당일 티커별 평가금 산출 - 수수료 포함
    UPRO_eval = Hold['UPRO'] * (USLA.get_US_current_price('UPRO') * (1-USLA.fee))
    TQQQ_eval = Hold['TQQQ'] * (USLA.get_US_current_price('TQQQ') * (1-USLA.fee))
    EDC_eval = Hold['EDC'] * (USLA.get_US_current_price('EDC') * (1-USLA.fee))
    TMF_eval = Hold['TMF'] * (USLA.get_US_current_price('TMF') * (1-USLA.fee))
    TMV_eval = Hold['TMV'] * (USLA.get_US_current_price('TMV') * (1-USLA.fee))

    result = USLA.get_US_dollar_balance()
    exchange_rate = result['exchange_rate']
    time_module.sleep(0.2)

    # 데이터 조정
    today_eval = UPRO_eval + TQQQ_eval + EDC_eval + TMF_eval + TMV_eval + Hold['CASH']
    today_eval_KRW = int(today_eval * exchange_rate)
    today_eval = float("{:.2f}".format(today_eval))

    USLA_data = {
        'date': str(order_time['date']),
        'regime_signal': regime_signal,
        'target_ticker1': target_ticker[0],
        'target_weight1': target_weight1,
        'target_ticker1_qty': target_ticker1_qty,
        'target_ticker2': target_ticker[1],
        'target_weight2': target_weight2,
        'target_ticker2_qty': target_ticker2_qty,
        'UPRO': Hold['UPRO'],
        'TQQQ': Hold['TQQQ'],
        'EDC': Hold['EDC'],
        'TMF': Hold['TMF'],
        'TMV': Hold['TMV'],
        'CASH': Hold['CASH'],
        'balance': today_eval,
        'last_day_balance': USLA_data['last_day_balance'],
        'last_month_balance': USLA_data['last_month_balance'],
        'last_year_balance': USLA_data['last_year_balance'],
        'daily_return': USLA_data['daily_return'],
        'monthly_return': USLA_data['monthly_return'],
        'yearly_return': USLA_data['yearly_return'],
        'exchange_rate': USLA_data['exchange_rate'],
        'balance_KRW': today_eval_KRW,
        'last_day_balance_KRW': USLA_data['last_day_balance_KRW'],
        'last_month_balance_KRW': USLA_data['last_month_balance_KRW'],
        'last_year_balance_KRW': USLA_data['last_year_balance_KRW'],
        'daily_return_KRW': USLA_data['daily_return_KRW'],
        'monthly_return_KRW': USLA_data['monthly_return_KRW'],
        'yearly_return_KRW': USLA_data['yearly_return_KRW']
    }

    USLA.save_USLA_data_json(USLA_data)

    # Sell주문
    Sell_order = Selling(Sell, sell_split, order_time) 
    # Buy 수량 계산
    Buy_qty, TR_usd = calculate_Buy_qty(Buy, Hold, target_usd)
    # Buy주문
    Buy_order = Buying(Buy_qty, buy_split, TR_usd, order_time)

    # 데이터 저장
    save_TR_data(order_time, Sell_order, Buy_order, Hold_usd, target_weight, target_qty)
    sys.exit(0)

elif order_time['round'] in range(2, 25):  # Round 2~24회차
    # ============================================
    # 1단계: 지난 라운드 TR_data 불러오기
    # ============================================
    try:
        TR_data = USLA.load_USLA_TR()
        Sell_order = TR_data['Sell_order']
        Buy_order = TR_data['Buy_order']
        Hold_usd = TR_data['CASH']
        target_weight = TR_data['target_weight']
        target_qty = TR_data['target_qty']
        target_usd = target_qty['CASH']
        # 이전 라운드 USD 저장 (검증용)
        prev_round_usd = Hold_usd
    
    except Exception as e:
        KA.SendMessage(f"USLA_TR JSON 파일 오류: {e}")
        sys.exit(0)

    # ============================================
    # 2단계: 체결 내역 확인 (주문 취소 전!)
    # ============================================
    # 성공한 주문만 필터링하여 체결 확인
    successful_sell_orders = [o for o in Sell_order if o.get('success', False)]
    successful_buy_orders = [o for o in Buy_order if o.get('success', False)]

    report_message = [] # 출력메세지 모으기

    # 매도 체결결과 반영
    if len(successful_sell_orders) > 0:
        sell_summary, message = USLA.calculate_sell_summary(successful_sell_orders)
        Hold_usd += sell_summary['net_amount']
        for i in message:
            report_message.append(i)
        report_message.append(f"매도 체결: ${sell_summary['net_amount']:.2f} (수수료 차감 후)")
    
    # 매수 체결결과 반영
    if len(successful_buy_orders) > 0:
        buy_summary, message = USLA.calculate_buy_summary(successful_buy_orders)
        Hold_usd -= buy_summary['total_amount']
        for i in message:
            report_message.append(i)
        report_message.append(f"매수 체결: ${buy_summary['total_amount']:.2f} (수수료 포함)")

    # USD 잔고 변화 로깅
    usd_change = Hold_usd - prev_round_usd
    report_message.append(f"USD 변화: ${usd_change:+.2f} (이전: ${prev_round_usd:.2f} → 현재: ${Hold_usd:.2f})")
    
    # ============================================
    # 3단계: 미체결 주문 취소 (체결 확인 후!)
    # ============================================
    try:
        cancel_result, cancel_messages = USLA.cancel_all_unfilled_orders()
        report_message.extend(cancel_messages)
        if cancel_result['total'] > 0:
            report_message.append(f"미체결 주문 취소: {cancel_result['success']}/{cancel_result['total']}")
    except Exception as e:
        report_message.append(f"USLA 주문 취소 오류: {e}")
        
    # 출력
    KA.SendMessage("\n".join(report_message))

    # ============================================
    # 4단계: 새로운 주문 준비 및 실행
    # ============================================
    # 목표 비중 만들기
    Hold = real_Hold() #실제보유
    
    Buy = dict()
    Sell = dict()
    # target에 있는 종목 처리
    for ticker in target_qty.keys():
        hold_qty = Hold.get(ticker, 0)
        target = target_qty[ticker]
        if ticker == "CASH":
            continue
        if target > hold_qty:
            Buy[ticker] = target - hold_qty
        elif target < hold_qty:
            Sell[ticker] = hold_qty - target
    # Hold에만 있고 target에 없는 종목 처리 (전량 매도)
    for ticker in Hold.keys():
        if ticker == "CASH":
            continue
        if ticker not in target_qty.keys():
            if Hold[ticker] > 0:
                Sell[ticker] = Hold[ticker]
    
    # Buy USD환산총액이 현재 Hold['CASH']보다 클 경우 매수수량 조정
    TR_usd = Hold_usd - target_usd  # 매수가능 USD
    needs_usd = 0
    for ticker in Buy.keys(): # Buy USD환산총액 계산
        price = USLA.get_US_current_price(ticker)
        if isinstance(price, (int, float)) and price > 0:
            needs_usd += Buy[ticker] * (price * (1 + USLA.fee))
        else:
            needs_usd += 0
        time_module.sleep(0.1)
    Buy_qty = dict()
    ratio = TR_usd / needs_usd if needs_usd > 0 else 0
    if ratio < 1.0:
        for ticker in Buy.keys():
            original_qty = Buy[ticker]
            adjusted_qty = int(original_qty * ratio)
            Buy_qty[ticker] = adjusted_qty
    else:
        Buy_qty = Buy
    
    # split 데이터 만들기      
    round_split = USLA.make_split_data(order_time['round'])
    sell_split = [round_split["sell_splits"], round_split["sell_price_adjust"]]
    buy_split = [round_split["buy_splits"], round_split["buy_price_adjust"]]
    
    # Sell 주문
    Sell_order = Selling(Sell, sell_split, order_time)
    
    # Buy 주문
    Buy_order = Buying(Buy_qty, buy_split, TR_usd, order_time)

    # 데이터 저장
    save_TR_data(order_time, Sell_order, Buy_order, Hold_usd, target_weight, target_qty)

    sys.exit(0)

elif order_time['round'] == 25:  # 25회차 최종기록
    # ============================================
    # 1단계: 지난 라운드 TR_data 불러오기
    # ============================================
    try:
        TR_data = USLA.load_USLA_TR()
        Sell_order = TR_data['Sell_order']
        Buy_order = TR_data['Buy_order']
        Hold_usd = TR_data['CASH']
        target_weight = TR_data['target_weight']
        target_qty = TR_data['target_qty']
        target_usd = target_qty['CASH']
        # 이전 라운드 USD 저장 (검증용)
        prev_round_usd = Hold_usd
    
    except Exception as e:
        KA.SendMessage(f"USLA_TR JSON 파일 오류: {e}")
        sys.exit(0)    

    # ============================================
    # 2단계: 최종 체결 내역 확인 (주문 취소 전!)
    # ============================================
    # 성공한 주문만 필터링
    successful_sell_orders = [o for o in Sell_order if o.get('success', False)]
    successful_buy_orders = [o for o in Buy_order if o.get('success', False)]

    report_message = [] # 출력메세지 모으기

    # 매도 체결결과 반영
    if len(successful_sell_orders) > 0:
        sell_summary, message = USLA.calculate_sell_summary(successful_sell_orders)
        Hold_usd += sell_summary['net_amount']
        for i in message:
            report_message.append(i)
        report_message.append(f"매도 체결: ${sell_summary['net_amount']:.2f} (수수료 차감 후)")
    
    # 매수 체결결과 반영
    if len(successful_buy_orders) > 0:
        buy_summary, message = USLA.calculate_buy_summary(successful_buy_orders)
        Hold_usd -= buy_summary['total_amount']
        for i in message:
            report_message.append(i)
        report_message.append(f"매수 체결: ${buy_summary['total_amount']:.2f} (수수료 포함)")

    # USD 잔고 변화 로깅
    usd_change = Hold_usd - prev_round_usd
    report_message.append(f"USD 변화: ${usd_change:+.2f} (이전: ${prev_round_usd:.2f} → 현재: ${Hold_usd:.2f})")

    # ============================================
    # 3단계: 최종 미체결 주문 취소 (체결 확인 후!)
    # ============================================
    try:
        cancel_result, cancel_messages = USLA.cancel_all_unfilled_orders()
        report_message.extend(cancel_messages)
        if cancel_result['total'] > 0:
            report_message.append(f"미체결 주문 취소: {cancel_result['success']}/{cancel_result['total']}")
    except Exception as e:
        report_message.append(f"USLA 주문 취소 오류: {e}")
        
    # 출력
    KA.SendMessage("\n".join(report_message))    

    # ============================================
    # 4단계: 최종 데이터 저장 (USLA_data.json)
    # ============================================
    USLA_data = USLA.load_USLA_data()
    
    Hold = real_Hold()
    
    UPRO = Hold.get('UPRO', 0)
    TQQQ = Hold.get('TQQQ', 0)
    EDC = Hold.get('EDC', 0)
    TMF = Hold.get('TMF', 0)
    TMV = Hold.get('TMV', 0)
    CASH = Hold_usd
    
    # 당일 티커별 평가금 산출 - 수수료 포함
    UPRO_eval = Hold['UPRO'] * (USLA.get_US_current_price('UPRO') * (1-USLA.fee))
    TQQQ_eval = Hold['TQQQ'] * (USLA.get_US_current_price('TQQQ') * (1-USLA.fee))
    EDC_eval = Hold['EDC'] * (USLA.get_US_current_price('EDC') * (1-USLA.fee))
    TMF_eval = Hold['TMF'] * (USLA.get_US_current_price('TMF') * (1-USLA.fee))
    TMV_eval = Hold['TMV'] * (USLA.get_US_current_price('TMV') * (1-USLA.fee))
    stocks_eval_usd = UPRO_eval + TQQQ_eval + EDC_eval + TMF_eval + TMV_eval    
    balance = stocks_eval_usd + Hold_usd
    balanceKRW = int(balance * USLA.get_US_dollar_balance()['exchange_rate'])
    
    #data 조정
    USLA_data = {
        'date': str(order_time['date']),
        'regime_signal': USLA_data['regime_signal'],
        'target_ticker1': USLA_data['target_ticker1'],
        'target_weight1': USLA_data['target_weight1'],
        'target_ticker1_qty': USLA_data['target_ticker1_qty'],
        'target_ticker2': USLA_data['target_ticker2'],
        'target_weight2': USLA_data['target_weight2'],
        'target_ticker2_qty': USLA_data['target_ticker2_qty'],
        'UPRO': UPRO,
        'TQQQ': TQQQ,
        'EDC': EDC,
        'TMF': TMF,
        'TMV': TMV,
        'CASH': CASH,
        'balance': balance,
        'last_day_balance': USLA_data['last_day_balance'],
        'last_month_balance': USLA_data['last_month_balance'],
        'last_year_balance': USLA_data['last_year_balance'],
        'daily_return': USLA_data['daily_return'],
        'monthly_return': USLA_data['monthly_return'],
        'yearly_return': USLA_data['yearly_return'],
        'exchange_rate': USLA_data['exchange_rate'],
        'balance_KRW': balanceKRW,
        'last_day_balance_KRW': USLA_data['last_day_balance_KRW'],
        'last_month_balance_KRW': USLA_data['last_month_balance_KRW'],
        'last_year_balance_KRW': USLA_data['last_year_balance_KRW'],
        'daily_return_KRW': USLA_data['daily_return_KRW'],
        'monthly_return_KRW': USLA_data['monthly_return_KRW'],
        'yearly_return_KRW': USLA_data['yearly_return_KRW']
    }    
    
    USLA.save_USLA_data_json(USLA_data)

# 카톡 리밸 종료 결과 보내기
KA.SendMessage(f"KIS USLA {order_time['date']}\n당월 리벨런싱 완료")
KA.SendMessage(
    f"KIS USLA regime_signal: {USLA_data['regime_signal']}\n"
    f"target1: {USLA_data['target_ticker1']}, {USLA_data['target_weight1']}\n"
    f"target2: {USLA_data['target_ticker2']}, {USLA_data['target_weight2']}\n"
    f"KIS USLA balance: {balance}\n"
    f"UPRO: {UPRO}, TQQQ: {TQQQ}, EDC: {EDC}, TMF: {TMF}, TMV: {TMV}\n"
    f"CASH: ${Hold_usd:.2f}, Risk regime USD RP 월말일까지 투자"
)
