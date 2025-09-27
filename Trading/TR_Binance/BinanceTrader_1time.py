import ccxt
import time
import logging
import pandas as pd
import numpy as np
import kakao_alert as KA
import json
import asyncio
from typing import Dict, List, Optional, Tuple
from decimal import Decimal, ROUND_DOWN
from datetime import timedelta
from datetime import datetime
import math


# 로컬에서는 시간 지금 동기화 필요

class BinanceT:
    """
    바이낸스 BTC/USDT 자동매매 클래스
    CCXT 라이브러리를 사용한 spot market 거래
    """

    # 클래스 인스턴스 생성
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

    # 마켓 정보 로드
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

    # 잔고 조회    
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
                    'BTC' : balance['BTC']['total'],
                    'USDT_free': balance['USDT']['free'],
                    'USDT_locked': balance['USDT']['used'],
                    'USDT': balance['USDT']['total']    
                }
                
        except Exception as e:
            self.logger.error(f"Failed to get balance: {e}")
            return {}

    # 주문 확인   
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

    # 주문 취소 
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
                message = "취소할 주문이 없습니다."
                return message
            
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
            message = f"취소주문 {cancelled_count}/{len(open_orders)}건 실행"
            return message
            
        except Exception as e:
            self.logger.error(f"Failed to cancel all orders: {e}")
            message = f"Failed to cancel all orders: {e}"
            return message
    
    # 가격을 tick size에 맞게 반올림
    def _round_to_tick_size(self, price: float) -> float:
        """가격을 tick size에 맞게 반올림"""
        decimal_price = Decimal(str(price))
        decimal_tick = Decimal(str(self.tick_size))
        rounded = (decimal_price / decimal_tick).quantize(Decimal('1'), rounding=ROUND_DOWN) * decimal_tick
        return float(rounded)
    
    # 수량을 정밀도에 맞게 반올림
    def _round_amount(self, amount: float) -> float:
        """수량을 정밀도에 맞게 반올림"""
        return round(amount, self.amount_precision)
    
    # 현재 시장 가격 조회
    def get_current_price(self) -> float:
        """현재 시장 가격 조회"""
        try:
            ticker = self.exchange.fetch_ticker(self.symbol)
            return ticker['last']
        except Exception as e:
            self.logger.error(f"Failed to get current price: {e}")
            return 0.0
    
    def market_buy(self, usdt_amount: float) -> Optional[Dict]:
        """
        시장가 매수 주문
        
        Args:
            usdt_amount: 매수할 USDT 금액
            
        Returns:
            주문 결과 딕셔너리 또는 None
        """
        try:
            # 현재 가격 확인
            current_price = self.get_current_price()
            if current_price <= 0:
                self.logger.error("Failed to get current price for market buy")
                return None
            
            # USDT 잔고 확인
            try:
                balance = self.exchange.fetch_balance()
                available_usdt = balance['USDT']['free']
                self.logger.info(f"Available USDT balance: {available_usdt:.2f}")
                
                if usdt_amount > available_usdt:
                    self.logger.error(f"Insufficient USDT balance. Requested: {usdt_amount:.2f}, Available: {available_usdt:.2f}")
                    return None
                    
            except Exception as e:
                self.logger.error(f"Failed to fetch USDT balance: {e}")
                return None
            
            # USDT 금액을 최소 주문 금액에 맞게 조정 (내림 처리)
            # 바이낸스 BTC/USDT 최소 주문 금액은 보통 10 USDT
            if usdt_amount < self.min_cost:
                self.logger.error(f"Order amount too small. Minimum: {self.min_cost} USDT, Requested: {usdt_amount:.2f} USDT")
                return None
            
            # USDT 금액을 소수점 2자리로 내림 처리
            adjusted_usdt = math.floor(usdt_amount * 100) / 100
            
            # 예상 BTC 수량 계산 (로깅용)
            estimated_btc = adjusted_usdt / current_price
            
            self.logger.info(f"Market buy order: {adjusted_usdt:.2f} USDT (estimated {estimated_btc:.8f} BTC at ~{current_price:.2f})")
            
            # 시장가 매수 주문 실행
            try:
                client_order_id = f"market_buy_{int(time.time() * 1000)}"
                
                order = self.exchange.create_market_buy_order(
                    symbol=self.symbol,
                    amount=None,  # amount는 None으로
                    params={
                        'quoteOrderQty': adjusted_usdt,  # USDT 금액으로 주문
                        'newClientOrderId': client_order_id
                    }
                )
                
                # 실제 체결 정보
                filled_btc = order.get('filled', 0)
                avg_price = order.get('average', current_price)
                actual_cost = order.get('cost', adjusted_usdt)
                
                result = {
                    'order_id': order['id'],
                    'client_order_id': client_order_id,
                    'symbol': self.symbol,
                    'side': 'buy',
                    'type': 'market',
                    'amount': filled_btc,
                    'price': avg_price,
                    'cost': actual_cost,
                    'filled': filled_btc,
                    'status': order.get('status', 'filled'),
                    'timestamp': order.get('timestamp'),
                    'datetime': order.get('datetime')
                }
                
                self.logger.info(f"Market buy completed: {filled_btc:.8f} BTC at {avg_price:.2f} USDT (Total: {actual_cost:.2f} USDT)")
                KA.SendMessage(f"Market Buy Order Completed\nBTC: {filled_btc:.8f}\nPrice: {avg_price:.2f} USDT\nTotal Cost: {actual_cost:.2f} USDT")
                
                return result
                
            except Exception as e:
                self.logger.error(f"Market buy order failed: {e}")
                KA.SendMessage(f"Market Buy Order Failed: {e}")
                return None
                
        except Exception as e:
            self.logger.error(f"Market buy function failed: {e}")
            return None

    def market_sell(self, btc_amount: float) -> Optional[Dict]:
        """
        시장가 매도 주문
        
        Args:
            btc_amount: 매도할 BTC 수량
            
        Returns:
            주문 결과 딕셔너리 또는 None
        """
        try:
            # 현재 가격 확인
            current_price = self.get_current_price()
            if current_price <= 0:
                self.logger.error("Failed to get current price for market sell")
                return None
            
            # BTC 잔고 확인
            try:
                balance = self.exchange.fetch_balance()
                available_btc = balance['BTC']['free']
                self.logger.info(f"Available BTC balance: {available_btc:.8f}")
                
                if btc_amount > available_btc:
                    self.logger.error(f"Insufficient BTC balance. Requested: {btc_amount:.8f}, Available: {available_btc:.8f}")
                    return None
                    
            except Exception as e:
                self.logger.error(f"Failed to fetch BTC balance: {e}")
                return None
            
            # BTC 수량을 최소 주문 수량에 맞게 조정 (내림 처리)
            if btc_amount < self.min_amount:
                self.logger.error(f"Order amount too small. Minimum: {self.min_amount} BTC, Requested: {btc_amount:.8f} BTC")
                return None
            
            # BTC 수량을 tick size에 맞게 내림 처리
            # 바이낸스 BTC/USDT의 stepSize는 보통 0.00001 (5자리)
            tick_size = 0.00001  # stepSize, 실제로는 self.step_size 사용
            adjusted_btc = math.floor(btc_amount / tick_size) * tick_size
            adjusted_btc = round(adjusted_btc, 8)  # 부동소수점 오차 제거
            
            # 최소 주문 금액 재확인
            estimated_cost = adjusted_btc * current_price
            if estimated_cost < self.min_cost:
                self.logger.error(f"Order cost too small after adjustment. Minimum: {self.min_cost} USDT, Estimated: {estimated_cost:.2f} USDT")
                return None
            
            self.logger.info(f"Market sell order: {adjusted_btc:.8f} BTC (estimated {estimated_cost:.2f} USDT at ~{current_price:.2f})")
            
            # 시장가 매도 주문 실행
            try:
                client_order_id = f"market_sell_{int(time.time() * 1000)}"
                
                order = self.exchange.create_market_sell_order(
                    symbol=self.symbol,
                    amount=adjusted_btc,
                    params={'newClientOrderId': client_order_id}
                )
                
                # 실제 체결 정보
                filled_btc = order.get('filled', adjusted_btc)
                avg_price = order.get('average', current_price)
                actual_proceeds = order.get('cost', estimated_cost)
                
                result = {
                    'order_id': order['id'],
                    'client_order_id': client_order_id,
                    'symbol': self.symbol,
                    'side': 'sell',
                    'type': 'market',
                    'amount': filled_btc,
                    'price': avg_price,
                    'cost': actual_proceeds,
                    'filled': filled_btc,
                    'status': order.get('status', 'filled'),
                    'timestamp': order.get('timestamp'),
                    'datetime': order.get('datetime')
                    
                }
                
                self.logger.info(f"Market sell completed: {filled_btc:.8f} BTC at {avg_price:.2f} USDT (Total: {actual_proceeds:.2f} USDT)")
                KA.SendMessage(f"Market Sell Order Completed\nBTC: {filled_btc:.8f}\nPrice: {avg_price:.2f} USDT\nTotal Proceeds: {actual_proceeds:.2f} USDT")
                
                return result
                
            except Exception as e:
                self.logger.error(f"Market sell order failed: {e}")
                KA.SendMessage(f"Market Sell Order Failed: {e}")
                return None
                
        except Exception as e:
            self.logger.error(f"Market sell function failed: {e}")
            return None
    
    # 일봉 가격 데이터 
    def get_daily_ohlcv(self, days: int = 365) -> pd.DataFrame:
        """
        일봉 OHLCV 데이터 조회
        
        Args:
            days: 조회할 일수 (기본값: 365일)
            
        Returns:
            OHLCV 데이터프레임 (datetime index)
        """
        try:
            # 시작 날짜 계산 (현재 시간 - days)
            since = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
            
            # 일봉 데이터 조회 (timeframe: '1d')
            ohlcv = self.exchange.fetch_ohlcv(
                symbol=self.symbol,
                timeframe='1d',
                since=since,
                limit=days
            )
            
            # 데이터프레임으로 변환
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # timestamp를 datetime으로 변환하고 인덱스로 설정
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('datetime', inplace=True)
            df.drop('timestamp', axis=1, inplace=True)
            
            # 데이터 타입을 float으로 변환
            df = df.astype(float)
            
            self.logger.info(f"Fetched {len(df)} days of OHLCV data")
            return df
            
        except Exception as e:
            self.logger.error(f"Failed to fetch daily OHLCV data: {e}")
            return pd.DataFrame()

    # 이동평균선 계산        
    def moving_average(self, period: int, reference_day: int = -1, data_days: int = 365) -> Dict:
        """
        일봉 기준 이동평균선 계산 및 특정 날짜의 이동평균 반환
        
        Args:
            period: 이동평균 기간 (예: 5, 20, 50, 200)
            reference_day: 기준일 (음수: 최근일부터 역산, -1=최근일, -2=하루전)
            data_days: 전체 데이터 기간 (기본값: 365일)
            
        Returns:
            이동평균 정보 딕셔너리
        """
        try:
            # 일봉 데이터 조회
            df = self.get_daily_ohlcv(data_days)
            
            # 종가 기준 이동평균 계산
            df[f'MA_{period}'] = df['close'].rolling(window=period).mean()
            
            # 기준일의 데이터 선택
            if abs(reference_day) > len(df):
                self.logger.error(f"Reference day {reference_day} exceeds available data length {len(df)}")
                return {}
            
            reference_data = df.iloc[reference_day]
            
            # 이동평균이 계산되었는지 확인 (NaN 체크)
            ma_value = reference_data[f'MA_{period}']
            if pd.isna(ma_value):
                self.logger.error(f"Not enough data to calculate {period}-day MA at reference day {reference_day}")
                return {}
            
            # 현재가와 이동평균 비교
            current_price = reference_data['close']
            price_diff = current_price - ma_value
            
            # 추세 판단
            signal = "Buy" if price_diff >= 0 else "Sell"
            
            result = {
                'period': period,
                'signal': signal
            }
            
            self.logger.info(f"{period}일 이동평균 계산 완료. 신호: {signal}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to calculate moving average: {e}")
            return {}

    # 어제 포지션을 불러서 오늘 포지션으로 변경 함수
    def make_position(self): # 어제 저장된 binance_data.json 파일을 불러서 오늘 포지션으로 변경하는 함수
        # 어제의 json값 불러오기
        data_path = '/var/autobot/TR_Binance/binance_data_1time.json' # test 후수정 ##############################################################
        # data_path = "C:/Users/ilpus/Desktop/git_folder/Trading/TR_Binance/binance_data.json"
        try:
            with open(data_path, 'r', encoding='utf-8') as f:
                binance_data = json.load(f)
        except Exception as e:
            print("Exception File")

        # JSON에서 어제의 데이터 추출
        BTC_weight = binance_data["BTC_weight"]
        Last_day_Total_balance = binance_data["Total_balance"]
        Last_month_Total_balance = binance_data["Last_month_Total_balance"]
        Last_year_Total_balance = binance_data["Last_year_Total_balance"]
        Daily_return = binance_data["Daily_return"]
        Monthly_return = binance_data["Monthly_return"]
        Yearly_return = binance_data["Yearly_return"]

        # 이동평균선 계산
        MA120 = self.moving_average(period = 120, reference_day = -1, data_days = 365)
        MA120signal = MA120["signal"]
        MA45 = self.moving_average(period = 45, reference_day = -1, data_days = 365)
        MA45signal = MA45["signal"]
        price = self.get_current_price()
        balance = self.get_balance('spot')
        BTC = balance.get('BTC', {})
        USDT = balance.get('USDT', {})

        # 포지션 산출
        if BTC_weight == 1.0 :
            if MA45signal == "Buy" and MA120signal == "Buy":
                position = {"position": "Hold state", "BTC_weight": 1.0, "BTC_target": BTC, "CASH_weight": 0.0, "Invest_quantity": 0.0}
            elif MA45signal == "Sell" and MA120signal == "Sell":
                position = {"position": "Sell full", "BTC_weight": 0.0, "BTC_target": 0.0, "CASH_weight": 1.0, "Invest_quantity": BTC * 0.99}
            else:
                position = {"position": "Sell half", "BTC_weight": 0.5, "BTC_target": BTC * 0.5, "CASH_weight": 0.5, "Invest_quantity": BTC * 0.5 * 0.99}            
        elif BTC_weight == 0.5:
            if MA45signal == "Buy" and MA120signal == "Buy":
                position = {"position": "Buy full", "BTC_weight": 1.0, "BTC_target": BTC + ((USDT * 0.9995)/price), "CASH_weight": 0.0, "Invest_quantity": USDT * 0.99}
            elif MA45signal == "Sell" and MA120signal == "Sell":
                position = {"position": "Sell full", "BTC_weight": 0.0, "BTC_target": 0.0, "CASH_weight": 1.0, "Invest_quantity": BTC * 0.99}
            else:
                position = {"position": "Hold state", "BTC_weight": 0.5, "BTC_target": BTC, "CASH_weight": 0.5, "Invest_quantity": 0.0}
        elif BTC_weight == 0.0:
            if MA45signal == "Buy" and MA120signal == "Buy":
                position = {"position": "Buy full", "BTC_weight": 1.0, "BTC_target": ((USDT*0.9995)/price), "CASH_weight": 0.0, "Invest_quantity": USDT * 0.99}
            elif MA45signal == "Sell" and MA120signal == "Sell":
                position = {"position": "Hold state", "BTC_weight": 0.0, "BTC_target": 0.0, "CASH_weight": 1.0, "Invest_quantity": 0.0}
            else:
                position = {"position": "Buy half", "BTC_weight": 0.5, "BTC_target": ((USDT*0.5*0.9995)/price) * 0.5, "CASH_weight": 0.5, "Invest_quantity": USDT * 0.5 *0.99}

        return position, Last_day_Total_balance, Last_month_Total_balance, Last_year_Total_balance, Daily_return, Monthly_return, Yearly_return, BTC, USDT