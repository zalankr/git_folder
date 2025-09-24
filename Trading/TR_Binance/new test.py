# 개선된 분할매도 주문

    
# 개선된 분할매수 주문
def split_buy(self, splits: int, usdt_amount: float) -> List[Dict]:
    """
    분할매수 주문
    
    Args:
        splits: 분할 횟수
        usdt_amount: 총 매수할 USDT 금액
        
    Returns:
        주문 결과 리스트
    """
    try:
        current_price = self.get_current_price()
        
        # 분할당 USDT 금액 (소수점 오차 방지)
        usdt_per_split = usdt_amount / splits
        orders = []
        total_used = 0.0  # 실제 사용된 금액 추적
        
        self.logger.info(f"Starting split buy: {splits} splits, {usdt_amount:.2f} USDT total")
        self.logger.info(f"Current BTC price: {current_price} USDT")
        
        for i in range(splits):
            try:
                # 마지막 주문에서는 남은 금액 모두 사용
                if i == splits - 1:
                    usdt_for_order = usdt_amount - total_used
                else:
                    usdt_for_order = usdt_per_split
                
                # 가격 계산
                if splits <= 2 and i == 0:
                    # 분할 횟수가 2회 이하면 첫 번째 주문만 현재가보다 1% 높게
                    order_price = current_price * 1.01
                else:
                    # 일반적인 경우: 현재가보다 0.05%씩 낮게
                    price_reduction = 0.0005 * (i + 1)  # 0.05% = 0.0005
                    order_price = current_price * (1 - price_reduction)
                
                # tick size에 맞게 가격 조정
                order_price = self._round_to_tick_size(order_price)
                
                # BTC 매수 수량 계산
                btc_amount = usdt_for_order / order_price
                btc_amount = self._round_amount(btc_amount)
                
                # 실제 주문 비용 재계산
                actual_order_cost = btc_amount * order_price
                
                # 최소 주문 금액 확인
                if actual_order_cost < self.min_cost or btc_amount < self.min_amount:
                    self.logger.warning(f"Split {i+1}: Order too small (Cost: {actual_order_cost:.2f} USDT, Amount: {btc_amount:.8f} BTC) - Skipping")
                    continue
                
                # 남은 잔고 재확인 (마지막 주문 전)
                if i == splits - 1:
                    try:
                        balance = self.exchange.fetch_balance()
                        available_usdt = balance['USDT']['free']
                        if actual_order_cost > available_usdt:
                            # 사용 가능한 USDT로 재계산
                            usdt_for_order = available_usdt * 0.99
                            btc_amount = usdt_for_order / order_price
                            btc_amount = self._round_amount(btc_amount)
                            actual_order_cost = btc_amount * order_price
                            self.logger.info(f"Final order amount adjusted to: {btc_amount:.8f} BTC (Cost: {actual_order_cost:.2f} USDT)")
                    except Exception as e:
                        self.logger.warning(f"Could not recheck balance for final order: {e}")
                
                # 재시도 로직을 포함한 매수 주문 실행
                max_retries = 3
                retry_count = 0
                order_success = False
                
                while retry_count < max_retries and not order_success:
                    try:
                        # 고유한 client order id 생성 (선택사항)
                        client_order_id = f"buy_split_{int(time.time() * 1000)}_{i+1}"
                        
                        order = self.exchange.create_limit_buy_order(
                            symbol=self.symbol,
                            amount=btc_amount,
                            price=order_price,
                            params={'newClientOrderId': client_order_id}  # 고유 ID 지정
                        )
                        
                        orders.append({
                            'split': i + 1,
                            'order_id': order['id'],
                            'client_order_id': client_order_id,
                            'price': order_price,
                            'amount': btc_amount,
                            'cost': actual_order_cost,
                            'status': 'success'
                        })
                        
                        total_used += actual_order_cost
                        order_success = True
                        
                        self.logger.info(f"Split {i+1} buy order placed: {btc_amount:.8f} BTC at {order_price:.2f} USDT (Cost: {actual_order_cost:.2f} USDT)")
                        
                    except Exception as e:
                        retry_count += 1
                        self.logger.warning(f"Split {i+1} order attempt {retry_count} failed: {e}")
                        
                        if retry_count < max_retries:
                            time.sleep(0.5)  # 재시도 전 대기 0.5초
                        else:
                            # 최대 재시도 후에도 실패
                            orders.append({
                                'split': i + 1,
                                'error': str(e),
                                'status': 'failed'
                            })
                            self.logger.error(f"Split {i+1} order failed after {max_retries} attempts: {e}")
                
                # 주문 간 대기 시간 증가 (Rate Limit 방지)
                if i < splits - 1:  # 마지막 주문이 아닌 경우만
                    time.sleep(0.5)  # 0.2초 → 0.5초로 증가
                
            except Exception as e:
                self.logger.error(f"Unexpected error in split {i+1}: {e}")
                orders.append({
                    'split': i + 1,
                    'error': str(e),
                    'status': 'failed'
                })
        
        successful_orders = len([o for o in orders if o.get('status') == 'success'])
        self.logger.info(f"Split buy completed: {successful_orders}/{splits} orders placed")
        KA.SendMessage(f"Split buy completed: {successful_orders}/{splits} orders placed")
        return orders
        
    except Exception as e:
        self.logger.error(f"Split buy failed: {e}")
        return []