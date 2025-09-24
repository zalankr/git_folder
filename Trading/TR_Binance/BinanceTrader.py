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
    
    # 분할매수 주문
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
            usdt_per_split = (usdt_amount*0.999) / splits
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
                    time.sleep(0.2)  # Rate limit 방지
                    
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
      
    # 분할매도 주문
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
                    time.sleep(0.2)  # Rate limit 방지
                    
                except Exception as e:
                    self.logger.error(f"Failed to place split {i+1} sell order: {e}")
                    orders.append({
                        'split': i + 1,
                        'error': str(e),
                        'status': 'failed'
                    })
            
            self.logger.info(f"Split sell completed: {len([o for o in orders if o.get('status') == 'success'])}/{splits} orders placed")
            KA.SendMessage(f"Split sell completed: {len([o for o in orders if o.get('status') == 'success'])}/{splits} orders placed")
            return orders
            
        except Exception as e:
            self.logger.error(f"Split sell failed: {e}")
            return []

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
        data_path = '/var/autobot/TR_Binance/binance_data.json'
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
        if BTC_weight == 1.0:
            if MA45signal == "Buy" and MA120signal == "Buy":
                position = {"position": "Hold state", "BTC_weight": 1.0, "BTC_target": BTC, "CASH_weight": 0.0, "Invest_quantity": 0.0}
            elif MA45signal == "Sell" and MA120signal == "Sell":
                position = {"position": "Sell full", "BTC_weight": 0.0, "BTC_target": 0.0, "CASH_weight": 1.0, "Invest_quantity": BTC}
            else:
                position = {"position": "Sell half", "BTC_weight": 0.5, "BTC_target": BTC * 0.5, "CASH_weight": 0.5, "Invest_quantity": BTC * 0.5}            
        elif BTC_weight == 0.5:
            if MA45signal == "Buy" and MA120signal == "Buy":
                position = {"position": "Buy full", "BTC_weight": 1.0, "BTC_target": BTC + ((USDT * 0.9995)/price), "CASH_weight": 0.0, "Invest_quantity": USDT}
            elif MA45signal == "Sell" and MA120signal == "Sell":
                position = {"position": "Sell full", "BTC_weight": 0.0, "BTC_target": 0.0, "CASH_weight": 1.0, "Invest_quantity": BTC}
            else:
                position = {"position": "Hold state", "BTC_weight": 0.5, "BTC_target": BTC, "CASH_weight": 0.5, "Invest_quantity": 0.0}
        elif BTC_weight == 0.0:
            if MA45signal == "Buy" and MA120signal == "Buy":
                position = {"position": "Buy full", "BTC_weight": 1.0, "BTC_target": ((USDT*0.9995)/price), "CASH_weight": 0.0, "Invest_quantity": USDT}
            elif MA45signal == "Sell" and MA120signal == "Sell":
                position = {"position": "Hold state", "BTC_weight": 0.0, "BTC_target": 0.0, "CASH_weight": 1.0, "Invest_quantity": 0.0}
            else:
                position = {"position": "Buy half", "BTC_weight": 0.5, "BTC_target": ((USDT*0.9995)/price) * 0.5, "CASH_weight": 0.5, "Invest_quantity": USDT * 0.5}

        return position, Last_day_Total_balance, Last_month_Total_balance, Last_year_Total_balance, Daily_return, Monthly_return, Yearly_return, BTC, USDT

# 시간확인 조건문 함수
def what_time():
    # 현재 시간 가져오기
    now = datetime.now()
    current_time = now.time()

    current_hour = current_time.hour
    current_minute = current_time.minute

    # 시간 비교 시 초 단위까지 정확히 매칭하기 어려우므로 시간 범위로 체크
    if current_hour == 23 and 41 <= current_minute <= 48:
        TR_time = ["0842", 0, "Redeem"]
    elif current_hour == 23 and 48 <= current_minute <= 50:
        TR_time = ["0849", 5, "Trading_1"]
    elif current_hour == 23 and 55 <= current_minute <= 57:
        TR_time = ["0856", 4, "Trading_2"]
    elif current_hour == 0 and 2 <= current_minute <= 4:
        TR_time = ["0903", 3, "Trading_3"]
    elif current_hour == 0 and 9 <= current_minute <= 11:
        TR_time = ["0910", 2, "Trading_4"] 
    elif current_hour == 0 and 16 <= current_minute <= 19 :
        TR_time = ["0917", 1, "Trading_5"]
    else:
        TR_time = ["Not_yet", None, "Nothing"]
    
    return now, TR_time

# # API 키 불러오기
# with open("C:/Users/ilpus/Desktop/NKL_invest/bnnkr.txt") as f:
#     API_KEY, API_SECRET = [line.strip() for line in f.readlines()]

# # 매니저 인스턴스 생성
# BinanceTrader = BinanceTrader(API_KEY, API_SECRET)
# shift+tab 내어쓰기

# 1. 잔고 조회
# print("=== 전체 잔고 조회 ===")
# total_balance = BinanceTrader.get_balance('total')
# print(f"BTC: {total_balance.get('BTC', {})}")
# print(f"USDT: {total_balance.get('USDT', {})}")

# print("\n=== Spot 잔고 조회 ===") # 트레이딩 시 기본으로 Spot잔고를 쓰는게 단순함
# spot_balance = BinanceTrader.get_balance('spot')
# print(f"BTC Free: {spot_balance.get('BTC_free', 0)}")
# print(f"USDT Free: {spot_balance.get('USDT_free', 0)}")
# print(f"BTC locked: {spot_balance.get('BTC_locked', 0)}")
# print(f"USDT locked: {spot_balance.get('USDT_locked', 0)}")
# print(f"BTC: {spot_balance.get('BTC', 0)}")
# print(f"USDT: {spot_balance.get('USDT', 0)}")

# # 2. 현재 가격 조회
# current_price = BinanceTrader.get_current_price()
# print(f"\n현재 BTC 가격: ${current_price}")

# # 3. 미체결 주문 조회
# print("\n=== 미체결 주문 조회 ===")
# open_orders = BinanceTrader.get_open_orders()
# print(f"미체결 주문 수: {len(open_orders)}")

# # 64. 모든 주문 취소
# print("\n=== 모든 주문 취소 ===")
# cancel_result = BinanceTrader.cancel_all_orders()
# print(f"주문 취소 결과: {cancel_result}")

# # 5. 분할매수: 5회 분할로 100 USDT 매수
# print("\n=== 분할 매도 주문 ===")
# buy_results = BinanceTrader.split_buy(splits=1, usdt_amount=13)
# print(buy_results)

# # 6. 분할매도: 3회 분할로 0.01 BTC 매도
# print("\n=== 분할 매도 주문 ===")
# sell_results = BinanceTrader.split_sell(splits=5, btc_amount=0.0016)
# print(sell_results)

# # 7. 현재시간, TR타임
# print(what_time())

# df = BinanceTrader.get_daily_ohlcv()
# print(df.tail(30))

# #이동평균선 수치, 첫번째: 분봉/일봉 정보, 두번째: 기간, 세번째: 기준 날짜
# result1 = BinanceTrader.moving_average(period=45, reference_day = -1, data_days = 365)
# result2 = BinanceTrader.moving_average(period=120, reference_day = -1, data_days = 365)
# print(result1)
# print(result2)

# # 8. 포지션 산출
# result = BinanceTrader.make_position()
# print(result)

