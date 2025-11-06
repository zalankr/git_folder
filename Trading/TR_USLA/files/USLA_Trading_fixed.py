import time as time_module
import kakao_alert as KA
import sys
import KIS_Calender
import USLA_model
from tendo import singleton
import json
from datetime import datetime

try:
    me = singleton.SingleInstance()
except singleton.SingleInstanceException:
    KA.SendMessage("USLA: 이미 실행 중입니다.")
    sys.exit(0)

# USLA모델 instance 생성
key_file_path = "/var/autobot/TR_USLA/kis63721147nkr.txt"
token_file_path = "/var/autobot/TR_USLA/kis63721147_token.json"
cano = "63721147"
acnt_prdt_cd = "01"
USLA_ticker = ["UPRO", "TQQQ", "EDC", "TMF", "TMV"]
USLA = USLA_model.USLA_Model(key_file_path, token_file_path, cano, acnt_prdt_cd)

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

def make_target_data(Hold, target_weight):
    """target qty, target usd 만들기"""
    hold_usd_value = USLA.calculate_USD_value(Hold)
    target_usd_value = {ticker: target_weight[ticker] * hold_usd_value for ticker in target_weight.keys()}
    target_qty = USLA.calculate_target_qty(target_weight, target_usd_value)
    target_usd = target_qty["CASH"]
    return target_qty, target_usd

def make_Buy_Sell(target_weight, target_qty, Hold):
    """target qty, hold qty 비교 조정 후 Buy와 Sell dict 만들고 반환하는 함수"""
    Buy = dict()
    Sell = dict()
    
    for ticker in target_weight.keys():
        if ticker == "CASH":
            continue
        hold_qty = Hold.get(ticker, 0)
        target = target_qty[ticker]

        if target > hold_qty:
            Buy[ticker] = target - hold_qty
        elif target < hold_qty:
            Sell[ticker] = hold_qty - target

    for ticker in Hold.keys():
        if ticker == "CASH":
            continue
        if ticker not in target_weight.keys():
            if Hold[ticker] > 0:
                Sell[ticker] = Hold[ticker]
    
    return Buy, Sell

def Selling(Sell, sell_split):
    """
    매도 주문 실행 함수 - 개선버전
    
    Parameters:
    - Sell: 매도할 종목과 수량 딕셔너리 {ticker: quantity}
    - sell_split: [분할횟수, [가격조정비율 리스트]]
    
    Returns:
    - Sell_order: 주문 결과 리스트 (성공/실패 모두 포함)
    """
    Sell_order = []
    
    if len(Sell.keys()) == 0:
        KA.SendMessage("매도할 종목이 없습니다.")
        return Sell_order
    
    for ticker in Sell.keys():
        if Sell[ticker] == 0:
            KA.SendMessage(f"{ticker} 매도 수량 0")
            continue

        qty_per_split = int(Sell[ticker] // sell_split[0])
        current_price = USLA.get_US_current_price(ticker)

        if not isinstance(current_price, (int, float)) or current_price <= 0:
            error_msg = f"USLA {ticker} 가격 조회 실패 - 매도 주문 스킵"
            KA.SendMessage(error_msg)
            # ⭐ 실패 정보도 저장 (추적을 위해)
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
                result = USLA.order_sell_US(ticker, quantity, price)
                
                # ⭐ 성공/실패 관계없이 모두 저장
                if result and result.get('success') == True:
                    order_info = {
                        'success': True,
                        'ticker': ticker,
                        'quantity': quantity,
                        'price': price,
                        'order_number': result.get('order_number', ''),
                        'order_time': result.get('order_time', ''),
                        'org_number': result.get('org_number', ''),
                        'message': result.get('message', ''),
                        'split_index': i
                    }
                    Sell_order.append(order_info)
                else:
                    error_msg = result.get('error_message', 'Unknown error') if result else 'API 호출 실패'
                    KA.SendMessage(f"{ticker} 매도 주문 실패: {error_msg}")
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
                KA.SendMessage(f"{ticker} 매도 주문 예외: {error_msg}")
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
    
    # ⭐ 매도 주문 요약
    success_count = sum(1 for order in Sell_order if order['success'])
    total_count = len(Sell_order)
    KA.SendMessage(f"매도 주문 완료: {success_count}/{total_count} 성공")
    
    return Sell_order

def calculate_Buy_qty(Buy, Hold, target_usd):
    """USD현재보유량과 목표보유량 비교 매수 수량과 매수 비중 매수 금액 산출"""
    Buy_value = {}
    total_Buy_value = 0
    ticker_prices = {}

    for ticker in Buy.keys():
        price = USLA.get_US_current_price(ticker)

        if isinstance(price, (int, float)) and price > 0:
            ticker_prices[ticker] = price
            Buy_value[ticker] = Buy[ticker] * price
            total_Buy_value += Buy_value[ticker]
        else:
            KA.SendMessage(f"{ticker} 가격 조회 실패")
            Buy_value[ticker] = 0
            ticker_prices[ticker] = 0

        time_module.sleep(0.1)

    TR_usd = Hold['CASH'] - target_usd
    if TR_usd < 0:
        TR_usd = 0
        KA.SendMessage(f"⚠️ 매수 가능 USD 부족: ${Hold['CASH']:.2f} (목표: ${target_usd:.2f})")

    Buy_qty = dict()

    if total_Buy_value == 0:
        KA.SendMessage("매수 가능한 종목이 없습니다.")
        return Buy_qty, TR_usd

    for ticker in Buy_value.keys():
        Buy_weight = Buy_value[ticker] / total_Buy_value
        Buy_usd = TR_usd * Buy_weight
        
        price = ticker_prices[ticker]
        
        if price > 0:
            Buy_qty[ticker] = int(Buy_usd / price)
        else:
            Buy_qty[ticker] = 0
        
        time_module.sleep(0.1)

    return Buy_qty, TR_usd

def Buying(Buy_qty, buy_split, TR_usd):
    """
    매수 주문 실행 함수 - 개선버전
    
    Parameters:
    - Buy_qty: 매수할 종목과 수량 딕셔너리 {ticker: quantity}
    - buy_split: [분할횟수, [가격조정비율 리스트]]
    - TR_usd: 매수가능 금액
    
    Returns:
    - Buy_order: 주문 결과 리스트 (성공/실패 모두 포함)
    """
    Buy_order = []
    
    if TR_usd < 0:
        TR_usd = 0
        KA.SendMessage("매수 가능 USD 부족")
    
    if len(Buy_qty.keys()) == 0:
        KA.SendMessage("매수할 종목이 없습니다.")
        return Buy_order
    
    for ticker in Buy_qty.keys():
        if Buy_qty[ticker] == 0:
            KA.SendMessage(f"{ticker} 매수 수량 0")
            continue
        
        qty_per_split = int(Buy_qty[ticker] // buy_split[0])
        current_price = USLA.get_US_current_price(ticker)
        
        if not isinstance(current_price, (int, float)) or current_price <= 0:
            error_msg = f"{ticker} 가격 조회 실패 - 주문 스킵"
            KA.SendMessage(error_msg)
            # ⭐ 실패 정보도 저장
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
                result = USLA.order_buy_US(ticker, quantity, price)
                
                # ⭐ 성공/실패 관계없이 모두 저장
                if result and result.get('success') == True:
                    order_info = {
                        'success': True,
                        'ticker': ticker,
                        'quantity': quantity,
                        'price': price,
                        'order_number': result.get('order_number', ''),
                        'order_time': result.get('order_time', ''),
                        'org_number': result.get('org_number', ''),
                        'message': result.get('message', ''),
                        'split_index': i
                    }
                    Buy_order.append(order_info)
                else:
                    error_msg = result.get('error_message', 'Unknown error') if result else 'API 호출 실패'
                    KA.SendMessage(f"{ticker} 매수 주문 실패: {error_msg}")
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
                KA.SendMessage(f"{ticker} 매수 주문 예외: {error_msg}")
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
    
    # ⭐ 매수 주문 요약
    success_count = sum(1 for order in Buy_order if order['success'])
    total_count = len(Buy_order)
    KA.SendMessage(f"매수 주문 완료: {success_count}/{total_count} 성공")
    
    return Buy_order

def round_TR_data(Hold_usd, target_weight):
    """라운드별 거래 데이터 생성"""
    order_time = KIS_Calender.check_order_time()
    round = order_time['round']
    
    round_split = USLA.make_split_data(round)
    sell_split = [round_split["sell_splits"], round_split["sell_price_adjust"]]
    buy_split = [round_split["buy_splits"], round_split["buy_price_adjust"]]

    Hold = real_Hold()
    Hold['CASH'] = Hold_usd
    
    target_qty, target_usd = make_target_data(Hold, target_weight)
    Buy, Sell = make_Buy_Sell(target_weight, target_qty, Hold)

    return Hold, target_usd, Buy, Sell, sell_split, buy_split

def validate_usd_consistency(prev_usd, sell_amount, buy_amount, current_usd, tolerance=5.0):
    """
    ⭐ USD 예수금 내부 일관성 검증
    
    공식: 이전 USD + 매도 체결액 - 매수 체결액 = 현재 USD
    
    Parameters:
    - prev_usd: 이전 라운드 USD
    - sell_amount: 매도 체결액 (수수료 차감 후)
    - buy_amount: 매수 체결액 (수수료 포함)
    - current_usd: 현재 계산된 USD
    - tolerance: 허용 오차 (달러)
    
    Returns:
    - is_valid: 검증 통과 여부
    - expected_usd: 예상 USD
    - diff: 차이 금액
    """
    expected_usd = prev_usd + sell_amount - buy_amount
    diff = abs(current_usd - expected_usd)
    is_valid = diff <= tolerance
    
    if not is_valid:
        KA.SendMessage(
            f"⚠️ USD 예수금 계산 불일치\n"
            f"이전: ${prev_usd:.2f}\n"
            f"매도: +${sell_amount:.2f}\n"
            f"매수: -${buy_amount:.2f}\n"
            f"예상: ${expected_usd:.2f}\n"
            f"실제: ${current_usd:.2f}\n"
            f"차이: ${diff:.2f}"
        )
    else:
        KA.SendMessage(
            f"✓ USD 검증 통과 (차이: ${diff:.2f})\n"
            f"${prev_usd:.2f} → ${current_usd:.2f}"
        )
    
    return is_valid, expected_usd, diff

def save_TR_data(order_time, Sell_order, Buy_order, Hold, target_weight):
    """
    거래 데이터 저장 - 개선버전
    ⭐ 저장 실패 시에도 백업 파일 생성
    """
    TR_data = {
        "round": order_time['round'],
        "timestamp": datetime.now().isoformat(),
        "Sell_order": Sell_order,
        "Buy_order": Buy_order,
        "CASH": Hold['CASH'],
        "target_weight": target_weight,
        "sell_success_rate": f"{sum(1 for o in Sell_order if o.get('success', False))}/{len(Sell_order)}" if Sell_order else "0/0",
        "buy_success_rate": f"{sum(1 for o in Buy_order if o.get('success', False))}/{len(Buy_order)}" if Buy_order else "0/0"
    }
    
    try:
        # 정상 저장
        save_result = USLA.save_USLA_TR_json(TR_data)
        
        if not save_result:
            raise Exception("save_USLA_TR_json returned False")
        
        KA.SendMessage(
            f"{order_time['date']}, {order_time['season']} 리밸런싱\n"
            f"{order_time['time']} {order_time['round']}/{order_time['total_round']}회차 저장완료\n"
            f"매도: {TR_data['sell_success_rate']}, 매수: {TR_data['buy_success_rate']}"
        )
        
    except Exception as e:
        # ⭐ 저장 실패 시 백업 파일 생성
        error_msg = f"TR 데이터 저장 실패: {e}"
        KA.SendMessage(error_msg)
        
        backup_path = f"/var/autobot/TR_USLA/USLA_TR_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(TR_data, f, ensure_ascii=False, indent=4)
            KA.SendMessage(f"✓ 백업 파일 생성: {backup_path}")
        except Exception as backup_error:
            KA.SendMessage(f"✗ 백업 파일 생성도 실패: {backup_error}")
            # ⭐ 최후의 수단: 카카오로 데이터 전송
            try:
                summary = {
                    'round': TR_data['round'],
                    'CASH': TR_data['CASH'],
                    'sell_count': len(Sell_order),
                    'buy_count': len(Buy_order),
                    'timestamp': TR_data['timestamp']
                }
                KA.SendMessage(f"TR 요약: {json.dumps(summary, ensure_ascii=False)}")
            except:
                pass
    
    return TR_data

def health_check():
    """시스템 상태 확인"""
    checks = []
    
    if not USLA.access_token:
        checks.append("USLA 체크: API 토큰 없음")
    
    import os
    files = [
        "/var/autobot/TR_USLA/USLA_rebalancing_day.json",
        "/var/autobot/TR_USLA/USLA_data.json",
        "/var/autobot/TR_USLA/USLA_TR.json"
    ]
    for f in files:
        if not os.path.exists(f):
            checks.append(f"USLA 체크: json 파일 없음: {f}")
    
    try:
        import socket
        socket.create_connection(("openapi.koreainvestment.com", 9443), timeout=5)
    except:
        checks.append("USLA 체크: KIS API 서버 접속 불가")
    
    if checks:
        KA.SendMessage("\n".join(checks))
        sys.exit(1)

# ============================================
# 메인 로직
# ============================================

order_time = KIS_Calender.check_order_time()
order_time['time'] = order_time['time'].replace(second=0, microsecond=0)

if order_time['season'] == "USLA_not_rebalancing" or order_time['round'] == 0:
    KA.SendMessage(f"USLA 리밸런싱일이 아닙니다.\n{order_time['date']}가 USLA_rebalancing_day 리스트에 없습니다.")
    sys.exit(0)

health_check()
KA.SendMessage(f"USLA {order_time['date']} 리밸런싱\n{order_time['time']}, {order_time['round']}/{order_time['total_round']}회차 거래시작")

if order_time['round'] == 1:
    # 목표 데이터 만들기
    target_weight, regime_signal = USLA.target_ticker_weight()
    USLA_data = USLA.load_USLA_data()
    Hold_usd = USLA_data['CASH']
    target_ticker = list(target_weight.keys())

    # ⭐ Round 1 초기 USD 로깅
    KA.SendMessage(f"Round 1 시작 USD: ${Hold_usd:.2f}")

    Hold, target_usd, Buy, Sell, sell_split, buy_split = round_TR_data(Hold_usd, target_weight)

    # USLA_data update 1차
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

    # Sell주문
    Sell_order = Selling(Sell, sell_split)
    # Buy 수량 계산
    Buy_qty, TR_usd = calculate_Buy_qty(Buy, Hold, target_usd)
    # Buy주문
    Buy_order = Buying(Buy_qty, buy_split, TR_usd)

    # 데이터 저장
    save_TR_data(order_time, Sell_order, Buy_order, Hold, target_weight)

    sys.exit(0)

elif order_time['round'] in range(2, 25):
    # 지난 주문 취소하기
    try:
        cancel_result = USLA.cancel_all_unfilled_orders()
        if cancel_result['total'] > 0:
            KA.SendMessage(f"미체결 주문 취소: {cancel_result['success']}/{cancel_result['total']}")
    except Exception as e:
        KA.SendMessage(f"USLA 주문 취소 오류: {e}")

    # 지난 라운드 TR_data 불러오기
    try:
        TR_data = USLA.load_USLA_TR()
        Sell_order = TR_data['Sell_order']
        Buy_order = TR_data['Buy_order']
        Hold_usd = TR_data['CASH']
        target_weight = TR_data['target_weight']
        
        # ⭐ 이전 라운드 USD 저장 (검증용)
        prev_round_usd = Hold_usd
        
    except Exception as e:
        KA.SendMessage(f"USLA_TR JSON 파일 오류: {e}")
        sys.exit(0)

    # ⭐ 성공한 주문만 필터링하여 체결 확인
    successful_sell_orders = [o for o in Sell_order if o.get('success', False)]
    successful_buy_orders = [o for o in Buy_order if o.get('success', False)]

    # 체결 금액 초기화
    sell_net_amount = 0.0
    buy_total_amount = 0.0

    # 매도 체결 확인
    if len(successful_sell_orders) > 0:
        sell_summary = USLA.calculate_sell_summary(successful_sell_orders)
        sell_net_amount = sell_summary['net_amount']
        Hold_usd += sell_net_amount
    
    # 매수 체결 확인
    if len(successful_buy_orders) > 0:
        buy_summary = USLA.calculate_buy_summary(successful_buy_orders)
        buy_total_amount = buy_summary['total_amount']
        Hold_usd -= buy_total_amount

    # ⭐ USD 내부 일관성 검증
    validate_usd_consistency(
        prev_usd=prev_round_usd,
        sell_amount=sell_net_amount,
        buy_amount=buy_total_amount,
        current_usd=Hold_usd,
        tolerance=5.0
    )

    # 목표 비중 만들기
    Hold, target_usd, Buy, Sell, sell_split, buy_split = round_TR_data(Hold_usd, target_weight)

    # Sell 주문
    Sell_order = Selling(Sell, sell_split)
    # Buy 수량 계산
    Buy_qty, TR_usd = calculate_Buy_qty(Buy, Hold, target_usd)
    # Buy 주문
    Buy_order = Buying(Buy_qty, buy_split, TR_usd)

    # 데이터 저장
    save_TR_data(order_time, Sell_order, Buy_order, Hold, target_weight)

    sys.exit(0)

elif order_time['round'] == 25:
    # 지난 주문 취소하기
    try:
        cancel_result = USLA.cancel_all_unfilled_orders()
        if cancel_result['total'] > 0:
            KA.SendMessage(f"최종 미체결 주문 취소: {cancel_result['success']}/{cancel_result['total']}")
    except Exception as e:
        KA.SendMessage(f"USLA 주문 취소 오류: {e}")

    # 지난 라운드 TR_data 불러오기
    try:
        TR_data = USLA.load_USLA_TR()
        Sell_order = TR_data['Sell_order']
        Buy_order = TR_data['Buy_order']
        Hold_usd = TR_data['CASH']
        
        prev_round_usd = Hold_usd
        
    except Exception as e:
        print(f"USLA_TR JSON 파일 오류: {e}")
        sys.exit(0)

    # ⭐ 성공한 주문만 필터링
    successful_sell_orders = [o for o in Sell_order if o.get('success', False)]
    successful_buy_orders = [o for o in Buy_order if o.get('success', False)]

    # 체결 금액 초기화
    sell_net_amount = 0.0
    buy_total_amount = 0.0

    # 매도 체결 확인
    if len(successful_sell_orders) > 0:
        sell_summary = USLA.calculate_sell_summary(successful_sell_orders)
        sell_net_amount = sell_summary['net_amount']
        Hold_usd += sell_net_amount
    
    # 매수 체결 확인
    if len(successful_buy_orders) > 0:
        buy_summary = USLA.calculate_buy_summary(successful_buy_orders)
        buy_total_amount = buy_summary['total_amount']
        Hold_usd -= buy_total_amount

    # ⭐ 최종 라운드 USD 검증
    validate_usd_consistency(
        prev_usd=prev_round_usd,
        sell_amount=sell_net_amount,
        buy_amount=buy_total_amount,
        current_usd=Hold_usd,
        tolerance=10.0  # 최종 라운드는 허용 오차 증가
    )

    # ⭐ 실제 보유 주식과 비교 (USLA 전략 보유분만)
    Hold = USLA.get_total_balance()
    Hold_tickers = {}
    if len(Hold['stocks']) > 0:
        for stock in Hold['stocks']:
            ticker = stock['ticker']
            if ticker in USLA_ticker:  # ⭐ USLA 전략 티커만
                qty = stock['quantity']
                Hold_tickers[ticker] = qty

    UPRO = Hold_tickers.get('UPRO', 0)
    TQQQ = Hold_tickers.get('TQQQ', 0)
    EDC = Hold_tickers.get('EDC', 0)
    TMF = Hold_tickers.get('TMF', 0)
    TMV = Hold_tickers.get('TMV', 0)
    
    # ⭐ USLA 전략 주식 평가액 계산
    usla_stock_value = 0.0
    for ticker in USLA_ticker:
        qty = Hold_tickers.get(ticker, 0)
        if qty > 0:
            price = USLA.get_US_current_price(ticker)
            if isinstance(price, (int, float)) and price > 0:
                usla_stock_value += qty * price
    
    balance = usla_stock_value + Hold_usd
    
    # USLA_data 최종 업데이트
    USLA_data = USLA.load_USLA_data()
    
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
        'last_day_balance': USLA_data['last_day_balance'],
        'last_month_balance': USLA_data['last_month_balance'],
        'last_year_balance': USLA_data['last_year_balance'],
        'daily_return': USLA_data['daily_return'],
        'monthly_return': USLA_data['monthly_return'],
        'yearly_return': USLA_data['yearly_return'],
        'exchange_rate': Hold['exchange_rate'],
        'balance_KRW': usla_stock_value * Hold['exchange_rate'] + (Hold_usd * Hold['exchange_rate']),
        'last_day_balance_KRW': USLA_data['last_day_balance_KRW'],
        'last_month_balance_KRW': USLA_data['last_month_balance_KRW'],
        'last_year_balance_KRW': USLA_data['last_year_balance_KRW'],
        'daily_return_KRW': USLA_data['daily_return_KRW'],
        'monthly_return_KRW': USLA_data['monthly_return_KRW'],
        'yearly_return_KRW': USLA_data['yearly_return_KRW']
    }
    USLA.save_USLA_data_json(USLA_data)

# 카톡 리밸 종료 결과
KA.SendMessage(f"KIS USLA {order_time['date']}\n당월 리밸런싱 완료")
KA.SendMessage(
    f"KIS USLA regime_signal: {USLA_data['regime_signal']}\n"
    f"target1: {USLA_data['target_ticker1']}, {USLA_data['target_weight1']}\n"
    f"target2: {USLA_data['target_ticker2']}, {USLA_data['target_weight2']}"
)
KA.SendMessage(
    f"KIS USLA balance: ${balance:.2f}\n"
    f"UPRO: {UPRO}, TQQQ: {TQQQ}, EDC: {EDC}, TMF: {TMF}, TMV: {TMV}\n"
    f"CASH: ${Hold_usd:.2f}"
)
