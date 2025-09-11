import ccxt
import pandas as pd
import numpy as np
import time
from datetime import datetime
import logging
from typing import Dict, Optional, Tuple, List

class BinanceSpotTrader:
    """
    Binance Spot Market 자동매매를 위한 클래스
    BTC/USDT 페어를 중심으로 한 현물거래 시스템
    """
    
    def __init__(self, api_key: str, secret_key: str, sandbox: bool = True):
        """
        Binance 거래소 클래스 초기화
        
        Args:
            api_key (str): Binance API 키
            secret_key (str): Binance Secret 키
            sandbox (bool): 테스트넷 사용 여부 (기본값: True)
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.symbol = 'BTC/USDT'
        
        # 로깅 설정
        logging.basicConfig(level=logging.INFO, 
                          format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
        
        # CCXT 거래소 객체 초기화
        self.exchange = ccxt.binance({
            'apiKey': self.api_key,
            'secret': self.secret_key,
            'sandbox': sandbox,  # 테스트넷 사용
            'rateLimit': 1200,  # API 호출 제한
            'enableRateLimit': True,
        })
        
        # 연결 테스트
        self._test_connection()
    
    def _test_connection(self):
        """API 연결 테스트"""
        try:
            self.exchange.load_markets()
            self.logger.info("Binance API 연결 성공")
            
            # 계정 권한 확인
            account_info = self.exchange.fetch_balance()
            self.logger.info("계정 정보 조회 성공")
            
        except Exception as e:
            self.logger.error(f"API 연결 실패: {str(e)}")
            raise
    
    def get_total_balance(self) -> Dict:
        """
        전체 계좌 잔고 조회
        
        Returns:
            Dict: 전체 잔고 정보
        """
        try:
            balance = self.exchange.fetch_balance()
            
            # 0이 아닌 잔고만 필터링
            non_zero_balances = {}
            for currency, amounts in balance['total'].items():
                if amounts > 0:
                    non_zero_balances[currency] = {
                        'free': balance['free'][currency],
                        'used': balance['used'][currency], 
                        'total': amounts
                    }
            
            self.logger.info(f"전체 잔고 조회 완료: {len(non_zero_balances)}개 통화")
            return non_zero_balances
            
        except Exception as e:
            self.logger.error(f"전체 잔고 조회 실패: {str(e)}")
            return {}
    
    def get_spot_balance(self, currencies: List[str] = None) -> Dict:
        """
        현물 거래 계좌 잔고 조회
        
        Args:
            currencies (List[str]): 조회할 통화 목록 (None이면 전체)
            
        Returns:
            Dict: 현물 계좌 잔고 정보
        """
        try:
            balance = self.exchange.fetch_balance({'type': 'spot'})
            
            if currencies is None:
                # BTC, USDT 기본 조회
                currencies = ['BTC', 'USDT']
            
            spot_balances = {}
            for currency in currencies:
                if currency in balance['total']:
                    spot_balances[currency] = {
                        'free': balance['free'][currency],      # 사용 가능
                        'used': balance['used'][currency],      # 주문 중
                        'total': balance['total'][currency]     # 전체
                    }
            
            self.logger.info(f"현물 잔고 조회 완료: {currencies}")
            return spot_balances
            
        except Exception as e:
            self.logger.error(f"현물 잔고 조회 실패: {str(e)}")
            return {}
    
    def get_current_price(self, symbol: str = None) -> float:
        """
        현재 가격 조회
        
        Args:
            symbol (str): 거래쌍 (기본값: BTC/USDT)
            
        Returns:
            float: 현재 가격
        """
        if symbol is None:
            symbol = self.symbol
            
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            self.logger.info(f"{symbol} 현재가: ${current_price:,.2f}")
            return current_price
            
        except Exception as e:
            self.logger.error(f"가격 조회 실패: {str(e)}")
            return 0.0
    
    def get_order_book(self, symbol: str = None, limit: int = 20) -> Dict:
        """
        호가창 정보 조회
        
        Args:
            symbol (str): 거래쌍
            limit (int): 조회할 호가 개수
            
        Returns:
            Dict: 매수/매도 호가 정보
        """
        if symbol is None:
            symbol = self.symbol
            
        try:
            order_book = self.exchange.fetch_order_book(symbol, limit)
            
            return {
                'bids': order_book['bids'][:5],  # 상위 5개 매수 호가
                'asks': order_book['asks'][:5],  # 상위 5개 매도 호가
                'timestamp': order_book['timestamp']
            }
            
        except Exception as e:
            self.logger.error(f"호가창 조회 실패: {str(e)}")
            return {}
    
    def place_market_buy_order(self, amount: float, symbol: str = None) -> Dict:
        """
        시장가 매수 주문
        
        Args:
            amount (float): 매수할 USDT 금액
            symbol (str): 거래쌍
            
        Returns:
            Dict: 주문 정보
        """
        if symbol is None:
            symbol = self.symbol
            
        try:
            # 최소 주문 금액 확인
            markets = self.exchange.load_markets()
            min_cost = markets[symbol]['limits']['cost']['min']
            
            if amount < min_cost:
                self.logger.warning(f"주문 금액이 최소 금액보다 작습니다. 최소: ${min_cost}")
                return {}
            
            order = self.exchange.create_market_buy_order(symbol, None, None, amount)
            self.logger.info(f"시장가 매수 주문 체결: {amount} USDT")
            
            return order
            
        except Exception as e:
            self.logger.error(f"매수 주문 실패: {str(e)}")
            return {}
    
    def place_market_sell_order(self, amount: float, symbol: str = None) -> Dict:
        """
        시장가 매도 주문
        
        Args:
            amount (float): 매도할 BTC 수량
            symbol (str): 거래쌍
            
        Returns:
            Dict: 주문 정보
        """
        if symbol is None:
            symbol = self.symbol
            
        try:
            # 최소 주문 수량 확인
            markets = self.exchange.load_markets()
            min_amount = markets[symbol]['limits']['amount']['min']
            
            if amount < min_amount:
                self.logger.warning(f"주문 수량이 최소 수량보다 작습니다. 최소: {min_amount} BTC")
                return {}
            
            order = self.exchange.create_market_sell_order(symbol, amount)
            self.logger.info(f"시장가 매도 주문 체결: {amount} BTC")
            
            return order
            
        except Exception as e:
            self.logger.error(f"매도 주문 실패: {str(e)}")
            return {}
    
    def place_limit_buy_order(self, amount: float, price: float, symbol: str = None) -> Dict:
        """
        지정가 매수 주문
        
        Args:
            amount (float): 매수할 BTC 수량
            price (float): 지정 가격
            symbol (str): 거래쌍
            
        Returns:
            Dict: 주문 정보
        """
        if symbol is None:
            symbol = self.symbol
            
        try:
            order = self.exchange.create_limit_buy_order(symbol, amount, price)
            self.logger.info(f"지정가 매수 주문: {amount} BTC @ ${price:,.2f}")
            
            return order
            
        except Exception as e:
            self.logger.error(f"지정가 매수 주문 실패: {str(e)}")
            return {}
    
    def place_limit_sell_order(self, amount: float, price: float, symbol: str = None) -> Dict:
        """
        지정가 매도 주문
        
        Args:
            amount (float): 매도할 BTC 수량
            price (float): 지정 가격
            symbol (str): 거래쌍
            
        Returns:
            Dict: 주문 정보
        """
        if symbol is None:
            symbol = self.symbol
            
        try:
            order = self.exchange.create_limit_sell_order(symbol, amount, price)
            self.logger.info(f"지정가 매도 주문: {amount} BTC @ ${price:,.2f}")
            
            return order
            
        except Exception as e:
            self.logger.error(f"지정가 매도 주문 실패: {str(e)}")
            return {}
    
    def get_open_orders(self, symbol: str = None) -> List[Dict]:
        """
        미체결 주문 조회
        
        Args:
            symbol (str): 거래쌍
            
        Returns:
            List[Dict]: 미체결 주문 목록
        """
        if symbol is None:
            symbol = self.symbol
            
        try:
            orders = self.exchange.fetch_open_orders(symbol)
            self.logger.info(f"미체결 주문 {len(orders)}개 조회")
            return orders
            
        except Exception as e:
            self.logger.error(f"미체결 주문 조회 실패: {str(e)}")
            return []
    
    def cancel_order(self, order_id: str, symbol: str = None) -> Dict:
        """
        주문 취소
        
        Args:
            order_id (str): 주문 ID
            symbol (str): 거래쌍
            
        Returns:
            Dict: 취소 결과
        """
        if symbol is None:
            symbol = self.symbol
            
        try:
            result = self.exchange.cancel_order(order_id, symbol)
            self.logger.info(f"주문 취소 완료: {order_id}")
            return result
            
        except Exception as e:
            self.logger.error(f"주문 취소 실패: {str(e)}")
            return {}
    
    def get_trading_history(self, symbol: str = None, limit: int = 50) -> List[Dict]:
        """
        거래 내역 조회
        
        Args:
            symbol (str): 거래쌍
            limit (int): 조회할 거래 개수
            
        Returns:
            List[Dict]: 거래 내역
        """
        if symbol is None:
            symbol = self.symbol
            
        try:
            trades = self.exchange.fetch_my_trades(symbol, limit=limit)
            self.logger.info(f"거래 내역 {len(trades)}개 조회")
            return trades
            
        except Exception as e:
            self.logger.error(f"거래 내역 조회 실패: {str(e)}")
            return []
    
    def display_account_summary(self):
        """계정 요약 정보 출력"""
        print("=" * 60)
        print("🚀 BINANCE BTC/USDT 자동매매 계정 현황")
        print("=" * 60)
        
        # 현재 가격
        current_price = self.get_current_price()
        print(f"📈 BTC/USDT 현재가: ${current_price:,.2f}")
        
        # 현물 잔고
        spot_balance = self.get_spot_balance(['BTC', 'USDT'])
        print("\n💰 현물 계좌 잔고:")
        for currency, balance in spot_balance.items():
            if currency == 'BTC':
                value_usd = balance['total'] * current_price
                print(f"  {currency}: {balance['total']:.8f} (≈ ${value_usd:,.2f})")
            else:
                print(f"  {currency}: ${balance['total']:,.2f}")
        
        # 호가창 정보
        order_book = self.get_order_book()
        if order_book:
            print(f"\n📊 호가창 정보:")
            print(f"  최고 매수가: ${order_book['bids'][0][0]:,.2f}")
            print(f"  최저 매도가: ${order_book['asks'][0][0]:,.2f}")
        
        # 미체결 주문
        open_orders = self.get_open_orders()
        print(f"\n📋 미체결 주문: {len(open_orders)}개")
        
        print("=" * 60)


# 사용 예시
if __name__ == "__main__":
    # ⚠️ 실제 사용 시에는 환경변수나 설정파일에서 API 키를 로드하세요
    API_KEY = "your_binance_api_key_here"
    SECRET_KEY = "your_binance_secret_key_here"
    
    try:
        # 트레이더 인스턴스 생성 (테스트넷)
        trader = BinanceSpotTrader(
            api_key=API_KEY,
            secret_key=SECRET_KEY,
            sandbox=True  # 실제 거래 시 False로 변경
        )
        
        # 계정 정보 출력
        trader.display_account_summary()
        
        # 잔고 조회 예시
        print("\n🔍 상세 잔고 조회:")
        total_balance = trader.get_total_balance()
        for currency, balance in total_balance.items():
            print(f"{currency}: {balance}")
        
        # 현물 잔고 조회
        spot_balance = trader.get_spot_balance(['BTC', 'USDT', 'ETH'])
        print(f"\n현물 잔고: {spot_balance}")
        
        # 매매 예시 (실제로는 전략에 따라 실행)
        # trader.place_market_buy_order(10)  # 10 USDT로 BTC 매수
        # trader.place_limit_sell_order(0.001, 50000)  # 0.001 BTC를 50,000달러에 매도
        
    except Exception as e:
        print(f"오류 발생: {str(e)}")
        print("API 키와 시크릿 키를 확인하세요.")