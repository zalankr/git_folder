import ccxt
import time
import logging
from typing import Dict, List, Optional, Tuple
from decimal import Decimal, ROUND_DOWN
import asyncio

class BinanceTrader:
    """
    바이낸스 BTC/USDT 자동매매 클래스
    CCXT 라이브러리를 사용한 spot market 거래
    """
    
    def __init__(self, api_key: str, api_secret: str, sandbox: bool = False):
        """
        초기화
        
        Args:
            api_key: 바이낸스 API 키
            api_secret: 바이낸스 API 시크릿
            sandbox: 테스트넷 사용 여부
        """
        self.symbol = 'BTC/USDT'
        self.exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'sandbox': sandbox,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot'  # spot market 거래
            }
        })
        
        # 로깅 설정
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
        # 심볼 정보 로드
        self._load_market_info()

    def _load_market_info(self):
        """마켓 정보 로드 (tick size, 최소 주문량 등)"""
            # 방법 1: 공개 API를 사용한 마켓 정보 로드 (권장)
        try:
            # 공개 API로 마켓 정보 로드 (인증 불필요)
            self.exchange.load_markets()
            market = self.exchange.markets[self.symbol]
            
            # 가격 정밀도 (tick size)
            self.price_precision = market['precision']['price']
            self.amount_precision = market['precision']['amount']
            
            # 최소 주문량
            self.min_cost = market['limits']['cost']['min'] if market['limits']['cost']['min'] else 5.0  # 기본값 5 USDT
            self.min_amount = market['limits']['amount']['min'] if market['limits']['amount']['min'] else 0.00001  # 기본값
            
            # tick size 계산
            self.tick_size = 10 ** (-self.price_precision)
            
            self.logger.info(f"Market Info Loaded via public API - Min Cost: {self.min_cost} USDT, Min Amount: {self.min_amount} BTC")
            self.logger.info(f"Price Precision: {self.price_precision}, Tick Size: {self.tick_size}")
            
        except Exception as public_api_error:
            self.logger.warning(f"Public API failed, trying direct API call: {public_api_error}")
    
    def get_balance(self, account_type: str = 'total') -> Dict:
        """
        잔고 조회
        
        Args:
            account_type: 'total' (전체 계좌) 또는 'spot' (spot market 계좌)
            
        Returns:
            잔고 정보 딕셔너리
        """
        try:
            balance = self.exchange.fetch_balance()
            
            if account_type == 'total':
                return {
                    'BTC': {
                        'free': balance['BTC']['free'],
                        'used': balance['BTC']['used'],
                        'total': balance['BTC']['total']
                    },
                    'USDT': {
                        'free': balance['USDT']['free'],
                        'used': balance['USDT']['used'],
                        'total': balance['USDT']['total']
                    },
                    'info': balance['info']
                }
            elif account_type == 'spot':
                # Spot 계좌 전용 잔고 (바이낸스에서는 기본이 spot)
                return {
                    'BTC_free': balance['BTC']['free'],
                    'BTC_locked': balance['BTC']['used'],
                    'USDT_free': balance['USDT']['free'],
                    'USDT_locked': balance['USDT']['used']
                }
                
        except Exception as e:
            self.logger.error(f"Failed to get balance: {e}")
            return {}
    
    def get_open_orders(self) -> List[Dict]:
        """
        주문 확인 (미체결 주문 조회)
        
        Returns:
            미체결 주문 리스트
        """
        try:
            open_orders = self.exchange.fetch_open_orders(self.symbol)
            self.logger.info(f"Open orders count: {len(open_orders)}")
            return open_orders
            
        except Exception as e:
            self.logger.error(f"Failed to get open orders: {e}")
            return []
    
    def cancel_all_orders(self) -> bool:
        """
        주문 확인된 전체 주문의 취소 주문
        
        Returns:
            성공 여부
        """
        try:
            open_orders = self.get_open_orders()
            
            if not open_orders:
                self.logger.info("No open orders to cancel")
                return True
            
            # 모든 주문 취소
            cancelled_count = 0
            for order in open_orders:
                try:
                    self.exchange.cancel_order(order['id'], self.symbol)
                    cancelled_count += 1
                    self.logger.info(f"Cancelled order: {order['id']}")
                    time.sleep(0.1)  # Rate limit 방지
                except Exception as e:
                    self.logger.error(f"Failed to cancel order {order['id']}: {e}")
            
            self.logger.info(f"Cancelled {cancelled_count}/{len(open_orders)} orders")
            return cancelled_count > 0
            
        except Exception as e:
            self.logger.error(f"Failed to cancel all orders: {e}")
            return False
    
    def _round_to_tick_size(self, price: float) -> float:
        """가격을 tick size에 맞게 반올림"""
        decimal_price = Decimal(str(price))
        decimal_tick = Decimal(str(self.tick_size))
        rounded = (decimal_price / decimal_tick).quantize(Decimal('1'), rounding=ROUND_DOWN) * decimal_tick
        return float(rounded)
    
    def _round_amount(self, amount: float) -> float:
        """수량을 정밀도에 맞게 반올림"""
        return round(amount, self.amount_precision)
    
    def get_current_price(self) -> float:
        """현재 시장 가격 조회"""
        try:
            ticker = self.exchange.fetch_ticker(self.symbol)
            return ticker['last']
        except Exception as e:
            self.logger.error(f"Failed to get current price: {e}")
            return 0.0
    
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
            if current_price <= 0:
                self.logger.error("Failed to get current price for split buy")
                return []
            
            # 분할당 USDT 금액
            usdt_per_split = usdt_amount / splits
            orders = []
            
            self.logger.info(f"Starting split buy: {splits} splits, {usdt_amount} USDT total")
            self.logger.info(f"Current BTC price: {current_price} USDT")
            
            for i in range(splits):
                try:
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
                    btc_amount = usdt_per_split / order_price
                    btc_amount = self._round_amount(btc_amount)
                    
                    # 최소 주문 금액 확인
                    order_cost = btc_amount * order_price
                    if order_cost < self.min_cost or btc_amount < self.min_amount:
                        self.logger.warning(f"Split {i+1}: Order too small (Cost: {order_cost:.2f} USDT, Amount: {btc_amount:.8f} BTC) - Skipping")
                        continue
                    
                    # 매수 주문 실행
                    order = self.exchange.create_limit_buy_order(
                        symbol=self.symbol,
                        amount=btc_amount,
                        price=order_price
                    )
                    
                    orders.append({
                        'split': i + 1,
                        'order_id': order['id'],
                        'price': order_price,
                        'amount': btc_amount,
                        'cost': order_cost,
                        'status': 'success'
                    })
                    
                    self.logger.info(f"Split {i+1} buy order placed: {btc_amount:.8f} BTC at {order_price:.2f} USDT (Cost: {order_cost:.2f} USDT)")
                    time.sleep(0.1)  # Rate limit 방지
                    
                except Exception as e:
                    self.logger.error(f"Failed to place split {i+1} buy order: {e}")
                    orders.append({
                        'split': i + 1,
                        'error': str(e),
                        'status': 'failed'
                    })
            
            self.logger.info(f"Split buy completed: {len([o for o in orders if o.get('status') == 'success'])}/{splits} orders placed")
            return orders
            
        except Exception as e:
            self.logger.error(f"Split buy failed: {e}")
            return []
    
    def split_sell(self, splits: int, btc_amount: float) -> List[Dict]:
        """
        분할매도 주문
        
        Args:
            splits: 분할 횟수
            btc_amount: 총 매도할 BTC 수량
            
        Returns:
            주문 결과 리스트
        """
        try:
            current_price = self.get_current_price()
            if current_price <= 0:
                self.logger.error("Failed to get current price for split sell")
                return []
            
            # 분할당 BTC 수량
            btc_per_split = btc_amount / splits
            orders = []
            
            self.logger.info(f"Starting split sell: {splits} splits, {btc_amount:.8f} BTC total")
            self.logger.info(f"Current BTC price: {current_price} USDT")
            
            for i in range(splits):
                try:
                    # 가격 계산
                    if splits <= 2 and i == 0:
                        # 분할 횟수가 2회 이하면 첫 번째 주문만 현재가보다 1% 낮게
                        order_price = current_price * 0.99
                    else:
                        # 일반적인 경우: 현재가보다 0.05%씩 높게
                        price_increase = 0.0005 * (i + 1)  # 0.05% = 0.0005
                        order_price = current_price * (1 + price_increase)
                    
                    # tick size에 맞게 가격 조정
                    order_price = self._round_to_tick_size(order_price)
                    
                    # BTC 매도 수량 조정
                    sell_amount = self._round_amount(btc_per_split)
                    
                    # 최소 주문 금액 확인
                    order_cost = sell_amount * order_price
                    if order_cost < self.min_cost or sell_amount < self.min_amount:
                        self.logger.warning(f"Split {i+1}: Order too small (Cost: {order_cost:.2f} USDT, Amount: {sell_amount:.8f} BTC) - Skipping")
                        continue
                    
                    # 매도 주문 실행
                    order = self.exchange.create_limit_sell_order(
                        symbol=self.symbol,
                        amount=sell_amount,
                        price=order_price
                    )
                    
                    orders.append({
                        'split': i + 1,
                        'order_id': order['id'],
                        'price': order_price,
                        'amount': sell_amount,
                        'cost': order_cost,
                        'status': 'success'
                    })
                    
                    self.logger.info(f"Split {i+1} sell order placed: {sell_amount:.8f} BTC at {order_price:.2f} USDT (Cost: {order_cost:.2f} USDT)")
                    time.sleep(0.1)  # Rate limit 방지
                    
                except Exception as e:
                    self.logger.error(f"Failed to place split {i+1} sell order: {e}")
                    orders.append({
                        'split': i + 1,
                        'error': str(e),
                        'status': 'failed'
                    })
            
            self.logger.info(f"Split sell completed: {len([o for o in orders if o.get('status') == 'success'])}/{splits} orders placed")
            return orders
            
        except Exception as e:
            self.logger.error(f"Split sell failed: {e}")
            return []
        

# API 키 불러오기
with open("C:/Users/ilpus/Desktop/NKL_invest/bnnkr.txt") as f:
    API_KEY, API_SECRET = [line.strip() for line in f.readlines()]

# 매니저 인스턴스 생성
BinanceTrader = BinanceTrader(API_KEY, API_SECRET)
# shift+tab 내어쓰기

# # 1. 잔고 조회
# print("=== 전체 잔고 조회 ===")
# total_balance = BinanceTrader.get_balance('total')
# print(f"BTC: {total_balance.get('BTC', {})}")
# print(f"USDT: {total_balance.get('USDT', {})}")

print("\n=== Spot 잔고 조회 ===") # 트레이딩 시 기본으로 Spot잔고를 쓰는게 단순함
spot_balance = BinanceTrader.get_balance('spot')
print(f"BTC Free: {spot_balance.get('BTC_free', 0)}")
print(f"USDT Free: {spot_balance.get('USDT_free', 0)}")

# 2. 현재 가격 조회
current_price = BinanceTrader.get_current_price()
print(f"\n현재 BTC 가격: ${current_price}")

# # 3. 미체결 주문 조회
# print("\n=== 미체결 주문 조회 ===")
# open_orders = BinanceTrader.get_open_orders()
# print(f"미체결 주문 수: {len(open_orders)}")

# # 6. 모든 주문 취소
# print("\n=== 모든 주문 취소 ===")
# cancel_result = BinanceTrader.cancel_all_orders()
# print(f"주문 취소 결과: {cancel_result}")

# # 5. 분할 매도 주문 예시 (0.01 BTC를 3번에 나누어 매도)
# print("\n=== 분할 매도 주문 ===")
# sell_orders = BinanceTrader.split_sell_orders(split_count=3, total_btc_amount=0.0005)
# for i, order in enumerate(sell_orders):
#     print(f"매도 주문 {i+1}: {order}")