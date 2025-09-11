import ccxt
import time
import logging
from typing import Dict, List, Optional, Tuple
from decimal import Decimal, ROUND_DOWN
import asyncio

class BinanceTradingBot:
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
        try:
            self.exchange.load_markets()
            market = self.exchange.markets[self.symbol]
            
            # 가격 정밀도 (tick size)
            self.price_precision = market['precision']['price']
            self.amount_precision = market['precision']['amount']
            
            # 최소 주문량
            self.min_cost = market['limits']['cost']['min']  # 최소 USDT 주문금액
            self.min_amount = market['limits']['amount']['min']  # 최소 BTC 주문수량
            
            # tick size 계산
            self.tick_size = 10 ** (-self.price_precision)
            
            self.logger.info(f"Market Info Loaded - Min Cost: {self.min_cost} USDT, Min Amount: {self.min_amount} BTC")
            self.logger.info(f"Price Precision: {self.price_precision}, Tick Size: {self.tick_size}")
            
        except Exception as e:
            self.logger.error(f"Failed to load market info: {e}")
            raise
    
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
    
    def split_buy_orders(self, split_count: int, total_usdt_amount: float) -> List[Dict]:
        """
        분할 매수 주문
        
        Args:
            split_count: 분할 횟수
            total_usdt_amount: 총 매매금액 (USDT)
            
        Returns:
            주문 결과 리스트
        """
        try:
            current_price = self.get_current_price()
            if current_price <= 0:
                raise ValueError("Invalid current price")
            
            # 회당 금액 계산
            amount_per_order = total_usdt_amount / split_count
            
            # 최소 주문금액 확인
            if amount_per_order < self.min_cost:
                raise ValueError(f"Amount per order ({amount_per_order}) is less than minimum cost ({self.min_cost})")
            
            orders = []
            base_price = current_price
            
            for i in range(split_count):
                # 가격 계산 (0.05씩 차감)
                order_price = base_price - (i * 0.05)
                order_price = self._round_to_tick_size(order_price)
                
                # BTC 수량 계산
                btc_amount = amount_per_order / order_price
                btc_amount = self._round_amount(btc_amount)
                
                # 최소 주문수량 확인
                if btc_amount < self.min_amount:
                    self.logger.warning(f"Order {i+1}: BTC amount ({btc_amount}) is less than minimum ({self.min_amount})")
                    continue
                
                try:
                    # 매수 주문 실행
                    order = self.exchange.create_limit_buy_order(
                        self.symbol, 
                        btc_amount, 
                        order_price
                    )
                    
                    orders.append({
                        'order_id': order['id'],
                        'price': order_price,
                        'amount': btc_amount,
                        'cost': btc_amount * order_price,
                        'status': 'success'
                    })
                    
                    self.logger.info(f"Buy Order {i+1}/{split_count}: {btc_amount} BTC @ ${order_price}")
                    time.sleep(0.2)  # Rate limit 방지
                    
                except Exception as e:
                    self.logger.error(f"Failed to create buy order {i+1}: {e}")
                    orders.append({
                        'order_id': None,
                        'price': order_price,
                        'amount': btc_amount,
                        'error': str(e),
                        'status': 'failed'
                    })
            
            self.logger.info(f"Created {len([o for o in orders if o['status'] == 'success'])}/{split_count} buy orders")
            return orders
            
        except Exception as e:
            self.logger.error(f"Failed to create split buy orders: {e}")
            return []
    
    def split_sell_orders(self, split_count: int, total_btc_amount: float) -> List[Dict]:
        """
        분할 매도 주문
        
        Args:
            split_count: 분할 횟수
            total_btc_amount: 총 매매수량 (BTC)
            
        Returns:
            주문 결과 리스트
        """
        try:
            current_price = self.get_current_price()
            if current_price <= 0:
                raise ValueError("Invalid current price")
            
            # 회당 수량 계산
            btc_per_order = total_btc_amount / split_count
            btc_per_order = self._round_amount(btc_per_order)
            
            # 최소 주문수량 확인
            if btc_per_order < self.min_amount:
                raise ValueError(f"BTC per order ({btc_per_order}) is less than minimum amount ({self.min_amount})")
            
            orders = []
            base_price = current_price
            
            for i in range(split_count):
                # 가격 계산 (0.05씩 증가)
                order_price = base_price + (i * 0.05)
                order_price = self._round_to_tick_size(order_price)
                
                # 최소 주문금액 확인
                order_cost = btc_per_order * order_price
                if order_cost < self.min_cost:
                    self.logger.warning(f"Order {i+1}: Order cost ({order_cost}) is less than minimum ({self.min_cost})")
                    continue
                
                try:
                    # 매도 주문 실행
                    order = self.exchange.create_limit_sell_order(
                        self.symbol, 
                        btc_per_order, 
                        order_price
                    )
                    
                    orders.append({
                        'order_id': order['id'],
                        'price': order_price,
                        'amount': btc_per_order,
                        'cost': btc_per_order * order_price,
                        'status': 'success'
                    })
                    
                    self.logger.info(f"Sell Order {i+1}/{split_count}: {btc_per_order} BTC @ ${order_price}")
                    time.sleep(0.2)  # Rate limit 방지
                    
                except Exception as e:
                    self.logger.error(f"Failed to create sell order {i+1}: {e}")
                    orders.append({
                        'order_id': None,
                        'price': order_price,
                        'amount': btc_per_order,
                        'error': str(e),
                        'status': 'failed'
                    })
            
            self.logger.info(f"Created {len([o for o in orders if o['status'] == 'success'])}/{split_count} sell orders")
            return orders
            
        except Exception as e:
            self.logger.error(f"Failed to create split sell orders: {e}")
            return []


# 사용 예시
def main():
    """사용 예시"""
    
    # API 키 설정 (실제 사용시에는 환경변수나 별도 파일에서 관리)
    API_KEY = "your_api_key_here"
    API_SECRET = "your_api_secret_here"
    
    # 봇 인스턴스 생성 (테스트넷 사용)
    bot = BinanceTradingBot(API_KEY, API_SECRET, sandbox=True)
    
    try:
        # 1. 잔고 조회
        print("=== 전체 잔고 조회 ===")
        total_balance = bot.get_balance('total')
        print(f"BTC: {total_balance.get('BTC', {})}")
        print(f"USDT: {total_balance.get('USDT', {})}")
        
        print("\n=== Spot 잔고 조회 ===")
        spot_balance = bot.get_balance('spot')
        print(f"BTC Free: {spot_balance.get('BTC_free', 0)}")
        print(f"USDT Free: {spot_balance.get('USDT_free', 0)}")
        
        # 2. 현재 가격 조회
        current_price = bot.get_current_price()
        print(f"\n현재 BTC 가격: ${current_price}")
        
        # 3. 미체결 주문 조회
        print("\n=== 미체결 주문 조회 ===")
        open_orders = bot.get_open_orders()
        print(f"미체결 주문 수: {len(open_orders)}")
        
        # 4. 분할 매수 주문 예시 (100 USDT를 5번에 나누어 매수)
        print("\n=== 분할 매수 주문 ===")
        buy_orders = bot.split_buy_orders(split_count=5, total_usdt_amount=100)
        for i, order in enumerate(buy_orders):
            print(f"매수 주문 {i+1}: {order}")
        
        # 5. 분할 매도 주문 예시 (0.01 BTC를 3번에 나누어 매도)
        print("\n=== 분할 매도 주문 ===")
        sell_orders = bot.split_sell_orders(split_count=3, total_btc_amount=0.01)
        for i, order in enumerate(sell_orders):
            print(f"매도 주문 {i+1}: {order}")
        
        # 6. 모든 주문 취소
        # print("\n=== 모든 주문 취소 ===")
        # cancel_result = bot.cancel_all_orders()
        # print(f"주문 취소 결과: {cancel_result}")
        
    except Exception as e:
        print(f"Error occurred: {e}")


if __name__ == "__main__":
    main()