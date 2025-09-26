
import requests
import json
import time
from datetime import datetime, timedelta
import pandas as pd
from typing import Dict, List, Optional
import logging

class KISMultiStrategyTrader:
    def __init__(self, app_key: str, app_secret: str, account_no: str):
        self.app_key = app_key
        self.app_secret = app_secret
        self.account_no = account_no
        self.base_url = "https://openapi.koreainvestment.com:9443"
        self.access_token = None
        
        # 전략별 설정
        self.strategies = {
            'domestic_small_cap': {
                'name': '국내소형주퀀트',
                'allocation': 0.4,  # 40% 할당
                'max_positions': 20,
                'rebalance_freq': 'monthly',
                'holdings': {},
                'cash': 0
            },
            'us_etf_allocation': {
                'name': '미국ETF자산배분',
                'allocation': 0.3,  # 30% 할당
                'max_positions': 10,
                'rebalance_freq': 'monthly',
                'holdings': {},
                'cash': 0
            },
            'domestic_trading': {
                'name': '국내일봉트레이딩',
                'allocation': 0.15,  # 15% 할당
                'max_positions': 5,
                'rebalance_freq': 'daily',
                'holdings': {},
                'cash': 0
            },
            'us_trading': {
                'name': '미국일봉트레이딩',
                'allocation': 0.15,  # 15% 할당
                'max_positions': 5,
                'rebalance_freq': 'daily',
                'holdings': {},
                'cash': 0
            }
        }
        
        self.total_balance = 0
        self.setup_logging()
    
    def setup_logging(self):
        """로깅 설정"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('trading_log.txt'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def get_access_token(self):
        """액세스 토큰 발급"""
        url = f"{self.base_url}/oauth2/tokenP"
        headers = {"content-type": "application/json"}
        data = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(data))
            if response.status_code == 200:
                self.access_token = response.json()["access_token"]
                self.logger.info("액세스 토큰 발급 성공")
                return True
            else:
                self.logger.error(f"토큰 발급 실패: {response.text}")
                return False
        except Exception as e:
            self.logger.error(f"토큰 발급 중 오류: {e}")
            return False
    
    def get_balance(self):
        """계좌 잔고 조회"""
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        headers = {
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "TTTC8434R"
        }
        params = {
            "CANO": self.account_no.split('-')[0],
            "ACNT_PRDT_CD": self.account_no.split('-')[1],
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }
        
        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                data = response.json()
                self.total_balance = float(data['output2'][0]['tot_evlu_amt'])
                self.update_strategy_allocation()
                return data
            else:
                self.logger.error(f"잔고 조회 실패: {response.text}")
                return None
        except Exception as e:
            self.logger.error(f"잔고 조회 중 오류: {e}")
            return None
    
    def update_strategy_allocation(self):
        """전략별 할당 자본 업데이트"""
        for strategy_name, strategy in self.strategies.items():
            allocated_amount = self.total_balance * strategy['allocation']
            strategy['cash'] = allocated_amount
            self.logger.info(f"{strategy['name']} 할당 자본: {allocated_amount:,.0f}원")
    
    def domestic_stock_order(self, symbol: str, quantity: int, price: int, 
                           order_type: str, strategy_name: str):
        """국내 주식 주문"""
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-cash"
        headers = {
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "TTTC0802U" if order_type == "buy" else "TTTC0801U"
        }
        
        data = {
            "CANO": self.account_no.split('-')[0],
            "ACNT_PRDT_CD": self.account_no.split('-')[1],
            "PDNO": symbol,
            "ORD_DVSN": "01",  # 시장가
            "ORD_QTY": str(quantity),
            "ORD_UNPR": str(price) if price > 0 else "0"
        }
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(data))
            if response.status_code == 200:
                result = response.json()
                # 전략별 주문 기록
                order_key = f"{strategy_name}_{symbol}"
                self.log_order(strategy_name, symbol, quantity, price, order_type, result)
                return result
            else:
                self.logger.error(f"국내 주식 주문 실패: {response.text}")
                return None
        except Exception as e:
            self.logger.error(f"국내 주식 주문 중 오류: {e}")
            return None
    
    def us_stock_order(self, symbol: str, quantity: int, order_type: str, strategy_name: str):
        """미국 주식 주문"""
        url = f"{self.base_url}/uapi/overseas-stock/v1/trading/order"
        headers = {
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "JTTT1002U" if order_type == "buy" else "JTTT1006U"
        }
        
        data = {
            "CANO": self.account_no.split('-')[0],
            "ACNT_PRDT_CD": self.account_no.split('-')[1],
            "OVRS_EXCG_CD": "NASD",  # 나스닥
            "PDNO": symbol,
            "ORD_QTY": str(quantity),
            "OVRS_ORD_UNPR": "0",  # 시장가
            "ORD_SVR_DVSN_CD": "0"
        }
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(data))
            if response.status_code == 200:
                result = response.json()
                order_key = f"{strategy_name}_{symbol}"
                self.log_order(strategy_name, symbol, quantity, 0, order_type, result)
                return result
            else:
                self.logger.error(f"미국 주식 주문 실패: {response.text}")
                return None
        except Exception as e:
            self.logger.error(f"미국 주식 주문 중 오류: {e}")
            return None
    
    def log_order(self, strategy_name: str, symbol: str, quantity: int, 
                  price: int, order_type: str, result: dict):
        """주문 로그 기록"""
        log_entry = {
            'timestamp': datetime.now(),
            'strategy': strategy_name,
            'symbol': symbol,
            'quantity': quantity,
            'price': price,
            'order_type': order_type,
            'result': result
        }
        
        self.logger.info(f"[{strategy_name}] {order_type.upper()} {symbol} {quantity}주 @ {price}")
        
        # 전략별 포지션 업데이트
        if result.get('rt_cd') == '0':  # 성공
            holdings_key = f"{symbol}"
            if order_type == "buy":
                if holdings_key in self.strategies[strategy_name]['holdings']:
                    self.strategies[strategy_name]['holdings'][holdings_key] += quantity
                else:
                    self.strategies[strategy_name]['holdings'][holdings_key] = quantity
            elif order_type == "sell":
                if holdings_key in self.strategies[strategy_name]['holdings']:
                    self.strategies[strategy_name]['holdings'][holdings_key] -= quantity
                    if self.strategies[strategy_name]['holdings'][holdings_key] <= 0:
                        del self.strategies[strategy_name]['holdings'][holdings_key]
    
    def execute_domestic_small_cap_strategy(self):
        """국내 소형주 퀀트 전략 실행"""
        self.logger.info("국내 소형주 퀀트 전략 실행 시작")
        
        # 예시: 소형주 선별 로직 (실제로는 더 복합적인 퀀트 모델 적용)
        target_stocks = ['066570', '035720', '000660']  # 예시 종목코드
        
        strategy = self.strategies['domestic_small_cap']
        available_cash = strategy['cash']
        position_size = available_cash / strategy['max_positions']
        
        for stock in target_stocks:
            # 현재 가격 조회 (실제로는 get_current_price 함수 구현 필요)
            current_price = 10000  # 예시 가격
            quantity = int(position_size / current_price)
            
            if quantity > 0:
                self.domestic_stock_order(stock, quantity, 0, "buy", "domestic_small_cap")
                time.sleep(0.1)  # API 호출 간격
    
    def execute_us_etf_strategy(self):
        """미국 ETF 자산배분 전략 실행"""
        self.logger.info("미국 ETF 자산배분 전략 실행 시작")
        
        # 예시: ETF 포트폴리오 구성
        etf_allocation = {
            'SPY': 0.4,   # S&P 500
            'QQQ': 0.3,   # 나스닥
            'IWM': 0.2,   # 소형주
            'TLT': 0.1    # 장기채권
        }
        
        strategy = self.strategies['us_etf_allocation']
        available_cash = strategy['cash']
        
        for etf, weight in etf_allocation.items():
            allocation_amount = available_cash * weight
            # 실제로는 ETF 현재가 조회 필요
            etf_price = 100  # 예시 가격 (USD)
            quantity = int(allocation_amount / (etf_price * 1300))  # USD/KRW 환율 가정
            
            if quantity > 0:
                self.us_stock_order(etf, quantity, "buy", "us_etf_allocation")
                time.sleep(0.1)
    
    def execute_daily_trading_strategies(self):
        """일봉 기준 트레이딩 전략들 실행"""
        self.logger.info("일봉 트레이딩 전략들 실행 시작")
        
        # 국내 트레이딩 전략
        domestic_signals = self.get_domestic_trading_signals()
        for signal in domestic_signals:
            if signal['action'] == 'buy':
                self.domestic_stock_order(signal['symbol'], signal['quantity'], 
                                        0, "buy", "domestic_trading")
            elif signal['action'] == 'sell':
                self.domestic_stock_order(signal['symbol'], signal['quantity'], 
                                        0, "sell", "domestic_trading")
            time.sleep(0.1)
        
        # 미국 트레이딩 전략
        us_signals = self.get_us_trading_signals()
        for signal in us_signals:
            if signal['action'] == 'buy':
                self.us_stock_order(signal['symbol'], signal['quantity'], 
                                  "buy", "us_trading")
            elif signal['action'] == 'sell':
                self.us_stock_order(signal['symbol'], signal['quantity'], 
                                  "sell", "us_trading")
            time.sleep(0.1)
    
    def get_domestic_trading_signals(self):
        """국내 일봉 트레이딩 시그널 생성"""
        # 실제로는 기술적 분석이나 퀀트 모델 구현
        signals = [
            {'symbol': '005930', 'action': 'buy', 'quantity': 10},
            {'symbol': '000660', 'action': 'sell', 'quantity': 5}
        ]
        return signals
    
    def get_us_trading_signals(self):
        """미국 일봉 트레이딩 시그널 생성"""
        # 실제로는 기술적 분석이나 퀀트 모델 구현
        signals = [
            {'symbol': 'AAPL', 'action': 'buy', 'quantity': 5},
            {'symbol': 'TSLA', 'action': 'sell', 'quantity': 3}
        ]
        return signals
    
    def get_strategy_performance(self):
        """전략별 수익률 조회"""
        performance = {}
        
        for strategy_name, strategy in self.strategies.items():
            # 실제로는 각 전략의 현재 평가금액과 초기 투자금액을 비교
            initial_amount = self.total_balance * strategy['allocation']
            current_value = initial_amount  # 예시 (실제로는 현재 보유 포지션 평가금액 계산)
            
            performance[strategy_name] = {
                'name': strategy['name'],
                'initial_amount': initial_amount,
                'current_value': current_value,
                'return_pct': ((current_value - initial_amount) / initial_amount) * 100,
                'holdings': strategy['holdings']
            }
        
        return performance
    
    def run_daily_routine(self):
        """일일 정기 실행 루틴"""
        self.logger.info("=== 일일 트레이딩 루틴 시작 ===")
        
        # 1. 액세스 토큰 갱신
        if not self.get_access_token():
            return False
        
        # 2. 계좌 잔고 및 할당 업데이트
        if not self.get_balance():
            return False
        
        # 3. 일봉 기준 트레이딩 전략 실행
        self.execute_daily_trading_strategies()
        
        # 4. 월별 리밸런싱 체크 (월초인 경우)
        if datetime.now().day == 1:
            self.execute_domestic_small_cap_strategy()
            self.execute_us_etf_strategy()
        
        # 5. 성과 리포트
        performance = self.get_strategy_performance()
        for strategy_name, perf in performance.items():
            self.logger.info(f"{perf['name']} 수익률: {perf['return_pct']:.2f}%")
        
        self.logger.info("=== 일일 트레이딩 루틴 완료 ===")
        return True

# 사용 예시
if __name__ == "__main__":
    # KIS API 인증 정보 (실제 값으로 교체 필요)
    APP_KEY = "your_app_key"
    APP_SECRET = "your_app_secret" 
    ACCOUNT_NO = "12345678-01"
    
    # 멀티 전략 트레이더 인스턴스 생성
    trader = KISMultiStrategyTrader(APP_KEY, APP_SECRET, ACCOUNT_NO)
    
    # 일일 루틴 실행
    trader.run_daily_routine()