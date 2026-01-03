# USLA_Trading.py 수정사항
# 아래 두 함수를 원본 파일의 해당 함수와 교체하세요

def Selling(Sell, sell_split):
    """
    매도 주문 실행 함수 - 개선버전 (메시지 통합)
    
    Parameters:
    - Sell: 매도할 종목과 수량 딕셔너리 {ticker: quantity}
    - sell_split: [분할횟수, [가격조정비율 리스트]]
    
    Returns:
    - Sell_order: 주문 결과 리스트 (성공/실패 모두 포함)
    """
    Sell_order = []
    order_messages = []  # ⭐ 주문 메시지를 모을 리스트
    
    if len(Sell.keys()) == 0:
        KA.SendMessage("매도할 종목이 없습니다.")
        return Sell_order
    
    # ⭐ 현재 라운드 정보 가져오기
    order_time = KIS_Calender.check_order_time()
    round_info = f"{order_time['round']}/{order_time['total_round']}회 매도주문"
    order_messages.append(round_info)
    
    for ticker in Sell.keys():
        if Sell[ticker] == 0:
            order_messages.append(f"{ticker} 매도 수량 0")
            continue

        qty_per_split = int(Sell[ticker] // sell_split[0])
        current_price = USLA.get_US_current_price(ticker)

        # 가격 조회 실패 시 기록하고 스킵
        if not isinstance(current_price, (int, float)) or current_price <= 0:
            error_msg = f"{ticker} 가격 조회 실패 - 매도 주문 스킵"
            order_messages.append(error_msg)  # ⭐ 메시지 누적
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
            # 마지막 분할은 남은 수량 전부
            if i == sell_split[0] - 1:
                quantity = Sell[ticker] - qty_per_split * (sell_split[0] - 1)
            else:
                quantity = qty_per_split
            
            if quantity == 0:
                continue
            
            # 주문 가격 계산
            price = round(current_price * sell_split[1][i], 2)
            
            try:
                # 주문
                result = USLA.order_sell_US(ticker, quantity, price)
                
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
                    order_messages.append(f"✅ {ticker} {quantity}주 @${price} (분할{i+1})")  # ⭐ 메시지 누적
                else:
                    # 실패한 주문도 기록
                    error_msg = result.get('error_message', 'Unknown error') if result else 'API 호출 실패'
                    order_messages.append(f"❌ {ticker} {quantity}주 @${price} - {error_msg}")  # ⭐ 메시지 누적
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
                # 예외 발생 시에도 기록
                error_msg = f"Exception: {str(e)}"
                order_messages.append(f"❌ {ticker} {quantity}주 @${price} - {error_msg}")  # ⭐ 메시지 누적
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
    
    # ⭐ 모든 매도 주문을 한 메시지로 전송
    success_count = sum(1 for order in Sell_order if order['success'])
    total_count = len(Sell_order)
    order_messages.append(f"매도 완료: {success_count}/{total_count} 성공")
    
    # ⭐ 한 번에 전송 (주요 변경점!)
    KA.SendMessage("\n".join(order_messages))
    
    return Sell_order


def Buying(Buy_qty, buy_split, TR_usd):
    """
    매수 주문 실행 함수 - 개선버전 (메시지 통합)
    
    Parameters:
    - Buy_qty: 매수할 종목과 수량 딕셔너리 {ticker: quantity}
    - buy_split: [분할횟수, [가격조정비율 리스트]]
    - TR_usd: 매수가능 금액
    
    Returns:
    - Buy_order: 주문 결과 리스트 (성공/실패 모두 포함)
    """
    Buy_order = []
    order_messages = []  # ⭐ 주문 메시지를 모을 리스트
    
    if TR_usd < 0:
        TR_usd = 0
        KA.SendMessage("매수 가능 USD 부족")
    
    if len(Buy_qty.keys()) == 0:
        KA.SendMessage("매수할 종목이 없습니다.")
        return Buy_order
    
    # ⭐ 현재 라운드 정보 가져오기
    order_time = KIS_Calender.check_order_time()
    round_info = f"{order_time['round']}/{order_time['total_round']}회 매수주문"
    order_messages.append(round_info)
    
    for ticker in Buy_qty.keys():
        if Buy_qty[ticker] == 0:
            order_messages.append(f"{ticker} 매수 수량 0")
            continue
        
        qty_per_split = int(Buy_qty[ticker] // buy_split[0])
        current_price = USLA.get_US_current_price(ticker)
        
        # 가격 조회 실패 시 기록하고 스킵
        if not isinstance(current_price, (int, float)) or current_price <= 0:
            error_msg = f"{ticker} 가격 조회 실패 - 주문 스킵"
            order_messages.append(error_msg)  # ⭐ 메시지 누적
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
            # 마지막 분할은 남은 수량 전부
            if i == buy_split[0] - 1:
                quantity = Buy_qty[ticker] - qty_per_split * (buy_split[0] - 1)
            else:
                quantity = qty_per_split
            
            if quantity == 0:
                continue
            
            # 주문 가격 계산
            price = round(current_price * buy_split[1][i], 2)
            
            try:
                # 주문
                result = USLA.order_buy_US(ticker, quantity, price)
                
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
                    order_messages.append(f"✅ {ticker} {quantity}주 @${price} (분할{i+1})")  # ⭐ 메시지 누적
                else:
                    # 실패한 주문도 기록
                    error_msg = result.get('error_message', 'Unknown error') if result else 'API 호출 실패'
                    order_messages.append(f"❌ {ticker} {quantity}주 @${price} - {error_msg}")  # ⭐ 메시지 누적
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
                # 예외 발생 시에도 기록
                error_msg = f"Exception: {str(e)}"
                order_messages.append(f"❌ {ticker} {quantity}주 @${price} - {error_msg}")  # ⭐ 메시지 누적
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
    
    # ⭐ 모든 매수 주문을 한 메시지로 전송
    success_count = sum(1 for order in Buy_order if order['success'])
    total_count = len(Buy_order)
    order_messages.append(f"매수 완료: {success_count}/{total_count} 성공")
    
    # ⭐ 한 번에 전송 (주요 변경점!)
    KA.SendMessage("\n".join(order_messages))
    
    return Buy_order
