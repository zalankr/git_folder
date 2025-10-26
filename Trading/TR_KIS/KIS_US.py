import requests
import json
from datetime import datetime, timedelta
import os
from typing import Union, Optional, Dict, List
import time
import pandas as pd

class KIS_API:
    """한국투자증권 API 클래스 (최종 정제 버전 + 체결내역 추적 기능)"""
    
    EXCHANGE_MAP = {
        # 나스닥
        "AAPL": "NAS", "MSFT": "NAS", "GOOGL": "NAS", "GOOG": "NAS",
        "AMZN": "NAS", "TSLA": "NAS", "META": "NAS", "NVDA": "NAS",
        "NFLX": "NAS", "AMD": "NAS", "INTC": "NAS", "CSCO": "NAS",
        "ADBE": "NAS", "PYPL": "NAS", "QCOM": "NAS", "AVGO": "NAS",
        "TQQQ": "NAS", "UPRO": "NAS", "TMF": "NAS", "TMV": "NAS",
        "EDC": "NAS", "BIL": "NYS",
        
        # 뉴욕증권거래소
        "BRK.B": "NYS", "JPM": "NYS", "JNJ": "NYS", "V": "NYS",
        "WMT": "NYS", "PG": "NYS", "MA": "NYS", "DIS": "NYS",
        "BAC": "NYS", "XOM": "NYS", "KO": "NYS", "PFE": "NYS",
        "T": "NYS", "VZ": "NYS", "CVX": "NYS", "NKE": "NYS",
    }
    
    # 수수료율
    SELL_FEE_RATE = 0.0009  # 매도 수수료 0.09%
    BUY_FEE_RATE = 0.0  # 매수 수수료는 체결단가에 포함

    def __init__(self, key_file_path: str, token_file_path: str, cano: str, acnt_prdt_cd: str):
        self.key_file_path = key_file_path
        self.token_file_path = token_file_path
        self.cano = cano
        self.acnt_prdt_cd = acnt_prdt_cd
        self.url_base = "https://openapi.koreainvestment.com:9443"
        
        self._load_api_keys()
        self.access_token = self.get_access_token()
    
    # API-Key 로드
    def _load_api_keys(self):
        with open(self.key_file_path) as f:
            self.app_key, self.app_secret = [line.strip() for line in f.readlines()]
    
    # 토큰 로드
    def load_token(self) -> Optional[Dict]:
        try:
            if os.path.exists(self.token_file_path):
                with open(self.token_file_path, 'r') as f:
                    return json.load(f)
            return None
        except Exception as e:
            print(f"토큰 로드 오류: {e}")
            return None
    
    # 토큰 저장
    def save_token(self, access_token: str, expires_in: int = 86400) -> bool:
        try:
            token_data = {
                "access_token": access_token,
                "issued_at": datetime.now().isoformat(),
                "expires_in": expires_in
            }
            with open(self.token_file_path, 'w') as f:
                json.dump(token_data, f, indent=2)
            return True
        except Exception as e:
            print(f"토큰 저장 오류: {e}")
            return False
    
    # 토큰 유효성 확인
    def is_token_valid(self, token_data: Dict) -> bool:
        if not token_data or 'access_token' not in token_data:
            return False
        
        try:
            issued_at = datetime.fromisoformat(token_data['issued_at'])
            expires_in = token_data.get('expires_in', 86400)
            now = datetime.now()
            expiry_time = issued_at + timedelta(seconds=expires_in)
            safe_expiry_time = expiry_time - timedelta(minutes=800)
            
            return now < safe_expiry_time
        except:
            return False
    
    # 토큰 발급
    def get_new_token(self) -> Optional[str]:
        headers = {"content-type": "application/json"}
        path = "oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        
        url = f"{self.url_base}/{path}"
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(body))
            response.raise_for_status()
            
            token_response = response.json()
            access_token = token_response['access_token']
            expires_in = token_response.get('expires_in', 86400)
            
            self.save_token(access_token, expires_in)
            return access_token
        except Exception as e:
            print(f"토큰 발급 실패: {e}")
            return None

    # 토큰 접속
    def get_access_token(self) -> Optional[str]:
        token_data = self.load_token()
        
        if token_data and self.is_token_valid(token_data):
            return token_data['access_token']
        
        return self.get_new_token()
    
    # Hash-Key 생성
    def hashkey(self, datas: Dict) -> str:
        path = "uapi/hashkey"
        url = f"{self.url_base}/{path}"
        headers = {
            'content-Type': 'application/json',
            'appKey': self.app_key,
            'appSecret': self.app_secret,
        }
        res = requests.post(url, headers=headers, data=json.dumps(datas))
        return res.json()["HASH"]
    
    # 티커별 거래소 찾기
    def get_US_exchange(self, ticker: str) -> Optional[str]:
        if not ticker:
            return None
        
        ticker = ticker.upper()
        
        if ticker in self.EXCHANGE_MAP:
            return self.EXCHANGE_MAP[ticker]
        
        exchanges = ["NAS", "NYS", "AMS"]
        path = "uapi/overseas-price/v1/quotations/price"
        url = f"{self.url_base}/{path}"
        
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "HHDFS00000300"
        }
        
        for exchange in exchanges:
            params = {
                "AUTH": "",
                "EXCD": exchange,
                "SYMB": ticker
            }
            
            try:
                response = requests.get(url, headers=headers, params=params)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('rt_cd') == '0':
                        output = data.get('output', {})
                        if any(output.get(field, '').strip() for field in ['rsym', 'base', 'last']):
                            return exchange
            except:
                continue
        
        return None
    
    # 주식 현재가 조회
    def get_US_current_price(self, ticker: str, exchange: Optional[str] = None) -> Union[float, str]:
        """
        미국 주식 현재가 조회 (KIS API → yfinance 백업)
        
        Parameters:
        ticker (str): 주식 티커 심볼
        exchange (str): 거래소 코드 (None이면 자동 검색)
        
        Returns:
        float: 현재가
        str: 에러 메시지
        """
        if not ticker:
            return "티커를 입력해주세요."
        
        ticker = ticker.upper()
        
        if exchange is None:
            exchange = self.get_US_exchange(ticker)
            if exchange is None:
                return self._get_price_from_yfinance(ticker)
        
        # KIS API 조회 시도
        price = self._get_price_from_kis(ticker, exchange)
        if isinstance(price, float):
            return price
        
        # yfinance 백업
        return self._get_price_from_yfinance(ticker)


        """yfinance로 시가 조회"""
        try:
            import yfinance as yf
            
            stock = yf.Ticker(ticker)
            
            # 최근 1일 데이터 조회
            hist = stock.history(period='1d')
            
            if not hist.empty and 'Open' in hist.columns:
                open_price = float(hist['Open'].iloc[-1])
                if open_price > 0:
                    return open_price
            
            # 실패시 2일 데이터로 재시도
            hist = stock.history(period='2d')
            if not hist.empty and 'Open' in hist.columns:
                open_price = float(hist['Open'].iloc[-1])
                if open_price > 0:
                    return open_price
            
            return "yfinance 시가 조회 실패"
        
        except ImportError:
            return "yfinance 미설치 (pip install yfinance)"
        except Exception as e:
            return f"yfinance 오류: {str(e)}"

    # KIS API로 현재가 조회
    def _get_price_from_kis(self, ticker: str, exchange: str) -> Union[float, str]:
        """KIS API로 현재가 조회 (3단계)"""
        
        # 1단계: 현재체결가 API
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "HHDFS00000300"
        }
        
        params = {
            "AUTH": "",
            "EXCD": exchange,
            "SYMB": ticker
        }
        
        try:
            # 1단계: 현재체결가
            response = requests.get(f"{self.url_base}/uapi/overseas-price/v1/quotations/price", 
                                   headers=headers, params=params)
            if response.status_code == 200:
                data = response.json()
                if data.get('rt_cd') == '0':
                    output = data.get('output', {})
                    for field in ['last', 'base', 'open', 'high', 'low']:
                        value = output.get(field, '').strip()
                        if value and value != '0':
                            try:
                                price = float(value)
                                if price > 0:
                                    return price
                            except:
                                continue
            
            # 2단계: 현재가상세
            headers['tr_id'] = "HHDFS76200200"
            response = requests.get(f"{self.url_base}/uapi/overseas-price/v1/quotations/price-detail",
                                   headers=headers, params=params)
            if response.status_code == 200:
                data = response.json()
                if data.get('rt_cd') == '0':
                    output = data.get('output', {})
                    for field in ['last', 'open', 'high', 'low', 'base', 't_xprc', 'p_xprc']:
                        value = output.get(field, '').strip()
                        if value and value != '0':
                            try:
                                price = float(value)
                                if price > 0:
                                    return price
                            except:
                                continue
            
            # 3단계: 기간별시세
            headers['tr_id'] = "HHDFS76240000"
            params_daily = {
                "AUTH": "",
                "EXCD": exchange,
                "SYMB": ticker,
                "GUBN": "0",
                "BYMD": "",
                "MODP": "0"
            }
            response = requests.get(f"{self.url_base}/uapi/overseas-price/v1/quotations/dailyprice",
                                   headers=headers, params=params_daily)
            if response.status_code == 200:
                data = response.json()
                if data.get('rt_cd') == '0':
                    output = data.get('output2', [])
                    if output and len(output) > 0:
                        clos = output[0].get('clos', '').strip()
                        if clos and clos != '0':
                            try:
                                price = float(clos)
                                if price > 0:
                                    return price
                            except:
                                pass
        except:
            pass
        
        return "KIS API 조회 실패"
    
    # yfinance로 현재가 조회
    def _get_price_from_yfinance(self, ticker: str) -> Union[float, str]:
        """yfinance로 현재가 조회 (백업)"""
        try:
            import yfinance as yf
            
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # 현재가 조회
            for field in ['currentPrice', 'regularMarketPrice', 'previousClose']:
                if field in info and info[field]:
                    price = info[field]
                    if price > 0:
                        return float(price)
            
            # 종가 조회
            hist = stock.history(period='1d')
            if not hist.empty and 'Close' in hist.columns:
                price = float(hist['Close'].iloc[-1])
                if price > 0:
                    return price
            
            return "yfinance 조회 실패"
            
        except ImportError:
            return "yfinance 미설치 (pip install yfinance)"
        except Exception as e:
            return f"yfinance 오류: {str(e)}"
    
    # 미국 정규시장 주식 매도 주문
    def order_sell_US(self, ticker: str, quantity: int, price: float,
                        exchange: Optional[str] = None, ord_dvsn: str = "00") -> Optional[Dict]:
        """
        미국 주식 매도 주문 (Regular Market)
        
        Parameters:
        ticker: 종목 코드
        quantity: 주문 수량
        price: 지정가
        exchange: 거래소 코드 (None이면 자동 검색)
        ord_dvsn: 주문구분 ("00": 지정가, "31": MOO, "32": LOO, "33": MOC, "34": LOC)
        
        Returns:
        Dict 또는 None - 주문 정보 딕셔너리
        {
            'success': bool,
            'ticker': str,
            'quantity': int,
            'price': float,
            'order_number': str,  # 주문번호 (ODNO)
            'order_time': str,    # 주문시각
            'response': requests.Response
        }
        """
        if exchange is None:
            exchange = self.get_US_exchange(ticker)
        
        if exchange is None:
            print(f"{ticker} 거래소를 찾을 수 없습니다.")
            return None
        
        # 가격을 소수점 2자리로 반올림
        price = round(price, 2)
        
        path = "uapi/overseas-stock/v1/trading/order"
        url = f"{self.url_base}/{path}"

        data = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "OVRS_EXCG_CD": exchange,
            "PDNO": ticker,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(quantity),
            "OVRS_ORD_UNPR": f"{price:.2f}",  # 소수점 2자리 문자열
            "CTAC_TLNO": "",
            "MGCO_APTM_ODNO": "",
            "SLL_TYPE": "00",
            "ORD_SVR_DVSN_CD": "0"
        }

        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "TTTT1006U",
            "custtype": "P",
            "hashkey": self.hashkey(data)
        }

        try:
            response = requests.post(url, headers=headers, data=json.dumps(data))
            response.raise_for_status()
            
            result = response.json()
            
            # 응답 성공 여부 확인
            if result.get('rt_cd') == '0':
                output = result.get('output', {})
                
                order_info = {
                    'success': True,
                    'ticker': ticker,
                    'quantity': quantity,
                    'price': price,
                    'order_number': output.get('ODNO', ''),      # 주문번호
                    'order_time': output.get('ORD_TMD', ''),     # 주문시각
                    'org_number': output.get('KRX_FWDG_ORD_ORGNO', ''),
                    'message': result.get('msg1', ''),
                    'response': response
                }
                
                print(f" 매도 주문 성공: {ticker} {quantity}주 @ ${price:.2f}")
                print(f" 주문번호: {order_info['order_number']}")
                
                return order_info
            else:
                print(f" 매도 주문 실패: {result.get('msg1', '알 수 없는 오류')}")
                return {
                    'success': False,
                    'ticker': ticker,
                    'quantity': quantity,
                    'price': price,
                    'order_number': '',
                    'error_code': result.get('rt_cd'),
                    'error_message': result.get('msg1', ''),
                    'response': response
                }
                
        except Exception as e:
            print(f" 매도 주문 오류: {e}")
            return None

    # 미국 정규시장 주식 매수 주문
    def order_buy_US(self, ticker: str, quantity: int, price: float, 
                        exchange: Optional[str] = None, ord_dvsn: str = "00") -> Optional[Dict]:
        """
        미국 주식 매수 주문 (Regular Market)
        
        Parameters:
        ticker: 종목 코드
        quantity: 주문 수량
        price: 지정가
        exchange: 거래소 코드 (None이면 자동 검색)
        ord_dvsn: 주문구분 ("00": 지정가, "32": LOO, "34": LOC)
        
        Returns:
        Dict 또는 None - 주문 정보 딕셔너리
        """
        if exchange is None:
            exchange = self.get_US_exchange(ticker)
        
        if exchange is None:
            print(f"{ticker} 거래소를 찾을 수 없습니다.")
            return None
        
        # 가격을 소수점 2자리로 반올림
        price = round(price, 2)
        
        path = "uapi/overseas-stock/v1/trading/order"
        url = f"{self.url_base}/{path}"

        data = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "OVRS_EXCG_CD": exchange,
            "PDNO": ticker,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(quantity),
            "OVRS_ORD_UNPR": f"{price:.2f}",
            "CTAC_TLNO": "",
            "MGCO_APTM_ODNO": "",
            "SLL_TYPE": "",  # 매수는 공란
            "ORD_SVR_DVSN_CD": "0"
        }

        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "TTTT1002U",  # 매수는 TTTT1002U
            "custtype": "P",
            "hashkey": self.hashkey(data)
        }

        try:
            response = requests.post(url, headers=headers, data=json.dumps(data))
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('rt_cd') == '0':
                output = result.get('output', {})
                
                order_info = {
                    'success': True,
                    'ticker': ticker,
                    'quantity': quantity,
                    'price': price,
                    'order_number': output.get('ODNO', ''),
                    'order_time': output.get('ORD_TMD', ''),
                    'org_number': output.get('KRX_FWDG_ORD_ORGNO', ''),
                    'message': result.get('msg1', ''),
                    'response': response
                }
                
                print(f" 매수 주문 성공: {ticker} {quantity}주 @ ${price:.2f}")
                print(f" 주문번호: {order_info['order_number']}")
                
                return order_info
            else:
                print(f" 매수 주문 실패: {result.get('msg1', '알 수 없는 오류')}")
                return {
                    'success': False,
                    'ticker': ticker,
                    'quantity': quantity,
                    'price': price,
                    'order_number': '',
                    'error_code': result.get('rt_cd'),
                    'error_message': result.get('msg1', ''),
                    'response': response
                }
                
        except Exception as e:
            print(f" 매수 주문 오류: {e}")
            return None
    
    # 미국 주간거래 매수 주문 (Pre-market/After-hours)
    def order_daytime_buy_US(self, ticker: str, quantity: int, price: float,
                            exchange: Optional[str] = None) -> Optional[Dict]:
        """
        미국 주간거래 매수 주문 (Pre-market/After-hours)
        
        Returns:
        Dict 또는 None - 주문 정보 딕셔너리
        {
            'success': bool,
            'ticker': str,
            'quantity': int,
            'price': float,
            'order_number': str,  # 주문번호 (ODNO)
            'order_time': str,    # 주문시각
            'response': requests.Response
        }
        """
        if exchange is None:
            exchange = self.get_US_exchange(ticker)
        
        if exchange is None:
            print(f"{ticker} 거래소를 찾을 수 없습니다.")
            return None
        
        if exchange not in ["NAS", "NYS", "AMS"]:
            print(f"주간거래는 나스닥(NAS), 뉴욕(NYS), 아멕스(AMS)만 가능합니다. (현재: {exchange})")
            return None
        
        # 가격을 소수점 2자리로 반올림
        price = round(price, 2)
        
        path = "uapi/overseas-stock/v1/trading/daytime-order"
        url = f"{self.url_base}/{path}"
        
        data = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "OVRS_EXCG_CD": exchange,
            "PDNO": ticker,
            "ORD_DVSN": "00",
            "ORD_QTY": str(quantity),
            "OVRS_ORD_UNPR": f"{price:.2f}",  # 소수점 2자리 문자열
            "CTAC_TLNO": "",
            "MGCO_APTM_ODNO": "",
            "ORD_SVR_DVSN_CD": "0"
        }
        
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "TTTS6036U",
            "custtype": "P",
            "hashkey": self.hashkey(data)
        }
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(data))
            response.raise_for_status()
            
            result = response.json()
            
            # 응답 성공 여부 확인
            if result.get('rt_cd') == '0':
                output = result.get('output', {})
                
                order_info = {
                    'success': True,
                    'ticker': ticker,
                    'quantity': quantity,
                    'price': price,
                    'order_number': output.get('ODNO', ''),      # 주문번호 (체결/취소 시 사용)
                    'order_time': output.get('ORD_TMD', ''),     # 주문시각
                    'org_number': output.get('KRX_FWDG_ORD_ORGNO', ''),  # 한국거래소 주문조직번호
                    'message': result.get('msg1', ''),
                    'response': response
                }
                
                print(f"주문 성공: {ticker} {quantity}주 @ ${price:.2f}")
                print(f"주문번호: {order_info['order_number']}")
                
                return order_info
            else:
                print(f"주문 실패: {result.get('msg1', '알 수 없는 오류')}")
                return {
                    'success': False,
                    'ticker': ticker,
                    'quantity': quantity,
                    'price': price,
                    'order_number': '',
                    'error_code': result.get('rt_cd'),
                    'error_message': result.get('msg1', ''),
                    'response': response
                }
                
        except Exception as e:
            print(f"주문 오류: {e}")
            return None

    # 미국 주간거래 매도 주문 (Pre-market/After-hours)
    def order_daytime_sell_US(self, ticker: str, quantity: int, price: float,
                            exchange: Optional[str] = None) -> Optional[Dict]:
        """
        미국 주간거래 매도 주문 (Pre-market/After-hours)
        
        Returns:
        Dict 또는 None - 주문 정보 딕셔너리
        {
            'success': bool,
            'ticker': str,
            'quantity': int,
            'price': float,
            'order_number': str,  # 주문번호 (ODNO)
            'order_time': str,    # 주문시각
            'response': requests.Response
        }
        """
        if exchange is None:
            exchange = self.get_US_exchange(ticker)
        
        if exchange is None:
            print(f"{ticker} 거래소를 찾을 수 없습니다.")
            return None
        
        if exchange not in ["NAS", "NYS", "AMS"]:
            print(f"주간거래는 나스닥(NAS), 뉴욕(NYS), 아멕스(AMS)만 가능합니다. (현재: {exchange})")
            return None
        
        # 가격을 소수점 2자리로 반올림
        price = round(price, 2)
        
        path = "uapi/overseas-stock/v1/trading/daytime-order"
        url = f"{self.url_base}/{path}"
        
        data = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "OVRS_EXCG_CD": exchange,
            "PDNO": ticker,
            "ORD_DVSN": "00",
            "ORD_QTY": str(quantity),
            "OVRS_ORD_UNPR": f"{price:.2f}",  # 소수점 2자리 문자열
            "CTAC_TLNO": "",
            "MGCO_APTM_ODNO": "",
            "ORD_SVR_DVSN_CD": "0"
        }
        
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "TTTS6037U",
            "custtype": "P",
            "hashkey": self.hashkey(data)
        }
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(data))
            response.raise_for_status()
            
            result = response.json()
            
            # 응답 성공 여부 확인
            if result.get('rt_cd') == '0':
                output = result.get('output', {})
                
                order_info = {
                    'success': True,
                    'ticker': ticker,
                    'quantity': quantity,
                    'price': price,
                    'order_number': output.get('ODNO', ''),      # 주문번호 (체결/취소 시 사용)
                    'order_time': output.get('ORD_TMD', ''),     # 주문시각
                    'org_number': output.get('KRX_FWDG_ORD_ORGNO', ''),  # 한국거래소 주문조직번호
                    'message': result.get('msg1', ''),
                    'response': response
                }
                
                print(f"주문 성공: {ticker} {quantity}주 @ ${price:.2f}")
                print(f"주문번호: {order_info['order_number']}")
                
                return order_info
            else:
                print(f"주문 실패: {result.get('msg1', '알 수 없는 오류')}")
                return {
                    'success': False,
                    'ticker': ticker,
                    'quantity': quantity,
                    'price': price,
                    'order_number': '',
                    'error_code': result.get('rt_cd'),
                    'error_message': result.get('msg1', ''),
                    'response': response
                }
                
        except Exception as e:
            print(f"주문 오류: {e}")
            return None

    # 미국 주식 종목별 잔고
    def get_US_stock_balance(self) -> Optional[List[Dict]]:
        """미국 주식 종목별 잔고 (체결기준 현재잔고)"""
        path = "uapi/overseas-stock/v1/trading/inquire-present-balance"
        url = f"{self.url_base}/{path}"
        
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "CTRP6504R"
        }
        
        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "WCRC_FRCR_DVSN_CD": "02",  # 02: 외화
            "NATN_CD": "840",  # 840: 미국
            "TR_MKET_CD": "00",  # 00: 전체
            "INQR_DVSN_CD": "00"  # 00: 전체
        }
        
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get('rt_cd') != '0':
                print(f"API 오류: {data.get('msg1')}")
                return None
            
            output1 = data.get('output1', [])
            stocks = []
            
            for stock in output1:
                # 핵심 수정: ccld_qty_smtl1 (체결수량합계) 사용
                quantity = int(float(stock.get('ccld_qty_smtl1', 0)))
                
                # 수량이 0인 종목은 제외 (옵션)
                if quantity == 0:
                    continue
                
                stock_info = {
                    'ticker': stock.get('pdno', ''),
                    'name': stock.get('prdt_name', ''),
                    'quantity': quantity,  # 체결수량합계 = 전일잔고 + 당일매수 - 당일매도
                    'avg_price': float(stock.get('avg_unpr3', 0)),
                    'current_price': float(stock.get('ovrs_now_pric1', 0)),
                    'eval_amt': float(stock.get('frcr_evlu_amt2', 0)),
                    'profit_loss': float(stock.get('evlu_pfls_amt2', 0)),
                    'profit_loss_rate': float(stock.get('evlu_pfls_rt1', 0)),
                    'exchange': stock.get('ovrs_excg_cd', ''),
                    # 추가 정보 (선택)
                    'thdt_buy_qty': int(float(stock.get('thdt_buy_ccld_qty1', 0))),  # 당일 매수량
                    'thdt_sell_qty': int(float(stock.get('thdt_sll_ccld_qty1', 0)))  # 당일 매도량
                }
                stocks.append(stock_info)
            
            return stocks
            
        except Exception as e:
            print(f"잔고 조회 오류: {e}")
            import traceback
            traceback.print_exc()
            return None

    # 미국 달러 예수금 # 오류 클로드 정상화 이후 확인 에러 # 삭제예정
    def get_US_dollar_balance(self) -> Optional[Dict]:
        """미국 달러 예수금"""
        path = "uapi/overseas-stock/v1/trading/inquire-present-balance"
        url = f"{self.url_base}/{path}"
        
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "CTRP6504R"
        }
        
        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "WCRC_FRCR_DVSN_CD": "02",
            "NATN_CD": "840",
            "TR_MKET_CD": "00",
            "INQR_DVSN_CD": "00"
        }
        
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get('rt_cd') != '0':
                return None
            
            output2 = data.get('output2', [])
            if not output2:
                return None
            
            usd_info = output2[0]
            
            return {
                'currency': usd_info.get('crcy_cd', 'USD'),
                'deposit': float(usd_info.get('frcr_dncl_amt_2', 0)),
                'withdrawable': float(usd_info.get('frcr_drwg_psbl_amt_1', 0)),
                'exchange_rate': float(usd_info.get('frst_bltn_exrt', 0)),
                'krw_value': float(usd_info.get('frcr_evlu_amt2', 0))
            }
        except:
            return None
    
    # 전체 계좌 잔고
    def get_total_balance(self) -> Optional[Dict]:
        """전체 계좌 잔고"""
        path = "uapi/overseas-stock/v1/trading/inquire-present-balance"
        url = f"{self.url_base}/{path}"
        
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "CTRP6504R"
        }
        
        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "WCRC_FRCR_DVSN_CD": "02",
            "NATN_CD": "840",
            "TR_MKET_CD": "00",
            "INQR_DVSN_CD": "00"
        }
        
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get('rt_cd') != '0':
                return None
            
            output1 = data.get('output1', [])
            stocks = []
            for stock in output1:
                stock_info = {
                    'ticker': stock.get('pdno', ''),
                    'name': stock.get('prdt_name', ''),
                    'quantity': int(float(stock.get('cblc_qty13', 0))),
                    'avg_price': float(stock.get('avg_unpr3', 0)),
                    'current_price': float(stock.get('ovrs_now_pric1', 0)),
                    'eval_amt': float(stock.get('frcr_evlu_amt2', 0)),
                    'profit_loss': float(stock.get('evlu_pfls_amt2', 0)),
                    'profit_loss_rate': float(stock.get('evlu_pfls_rt1', 0)),
                    'exchange': stock.get('tr_mket_name', '')
                }
                stocks.append(stock_info)
            
            output2 = data.get('output2', [])
            usd_deposit = 0
            exchange_rate = 0
            if output2:
                usd_info = output2[0]
                usd_deposit = float(usd_info.get('frcr_dncl_amt_2', 0))
                exchange_rate = float(usd_info.get('frst_bltn_exrt', 0))
            
            output3 = data.get('output3', {})
            stock_eval_usd = float(output3.get('evlu_amt_smtl', 0))
            stock_eval_krw = float(output3.get('evlu_amt_smtl_amt', 0))
            total_usd = stock_eval_usd + usd_deposit
            total_krw = float(output3.get('tot_asst_amt', 0))
            total_profit_loss_usd = float(output3.get('evlu_pfls_amt_smtl', 0))
            total_profit_loss_krw = float(output3.get('tot_evlu_pfls_amt', 0))
            profit_rate = float(output3.get('evlu_erng_rt1', 0))
            
            return {
                'stocks': stocks,
                'stock_count': len(stocks),
                'stock_eval_usd': stock_eval_usd,
                'stock_eval_krw': stock_eval_krw,
                'usd_deposit': usd_deposit,
                'usd_deposit_krw': usd_deposit * exchange_rate if exchange_rate > 0 else 0,
                'total_usd': total_usd,
                'total_krw': total_krw,
                'total_profit_loss_usd': total_profit_loss_usd,
                'total_profit_loss_krw': total_profit_loss_krw,
                'profit_rate': profit_rate,
                'exchange_rate': exchange_rate
            }
        except:
            return None

    # 체결내역 확인
    def check_order_execution(self, order_number, ticker, order_type="00"):       

        """
        주문 체결 확인 함수
        
        Parameters:
        order_number (str): 주문번호 (ODNO)
        ticker (str): 종목코드

        order_type (str): 주문 유형 ("00": 전체, "01": 매도, "02": 매수)
        
        Returns:
        dict: 체결 정보 또는 None
            - success (bool): 체결 성공 여부
            - name (str): 종목명
            - qty (str): 체결수량
            - price (str): 체결단가
            - amount (str): 체결금액
            - status (str): 처리상태
            - order_type (str): 주문유형 (매도/매수)
        """
        
        # 오늘 날짜
        today = datetime.now().strftime('%Y%m%d')
        
        # 거래소 확인
        exchange = self.get_US_exchange(ticker)
        if not exchange:
            print(f"{ticker}의 거래소를 찾을 수 없습니다.")
            return None
        
        # 체결 내역 조회
        print(f"\n주문번호 {order_number} 체결 내역 확인 중...")
        
        path = "uapi/overseas-stock/v1/trading/inquire-ccnl"
        url = f"{self.url_base}/{path}"
        
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "TTTS3035R"
        }
        
        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "PDNO": ticker,
            "ORD_STRT_DT": today,
            "ORD_END_DT": today,
            "SLL_BUY_DVSN": order_type,   # "00": 전체, "01": 매도, "02": 매수
            "CCLD_NCCS_DVSN": "01",       # 체결만
            "OVRS_EXCG_CD": exchange,
            "SORT_SQN": "DS",
            "ORD_DT": "",
            "ORD_GNO_BRNO": "",
            "ODNO": "",
            "CTX_AREA_NK200": "",
            "CTX_AREA_FK200": ""
        }
        
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('rt_cd') == '0':
                orders = result.get('output', [])
                
                # 해당 주문 찾기
                for order in orders:
                    if order.get('odno') == order_number:
                        return {
                            'success': True,
                            'name': order.get('prdt_name'),
                            'qty': order.get('ft_ccld_qty'),
                            'price': order.get('ft_ccld_unpr3'),
                            'amount': order.get('ft_ccld_amt3'),
                            'status': order.get('prcs_stat_name'),
                            'order_type': order.get('sll_buy_dvsn_cd_name', '알 수 없음')
                        }
                
                print(f"주문번호 {order_number}를 찾을 수 없습니다.")
                return None
            else:
                print(f"조회 실패: {result.get('msg1')}")
                return None
                
        except Exception as e:
            print(f"체결 확인 중 오류: {e}")
            return None

    # 주문 체결내역 추적
    def track_order_execution(
        self,
        order_number: str,
        ticker: str,
        wait_seconds: int = 10,
        max_attempts: int = 5
    ) -> Optional[Dict]:
        """
        특정 주문번호의 체결 추적
        
        Parameters:
        order_number: 추적할 주문번호
        ticker: 종목코드
        wait_seconds: 재시도 대기 시간
        max_attempts: 최대 시도 횟수
        
        Returns:
        Dict: 체결 정보 또는 None
        """
        today = datetime.now().strftime('%Y%m%d')
        
        for attempt in range(max_attempts):
            print(f"\n[{attempt + 1}/{max_attempts}] 체결 확인 중... (주문번호: {order_number})")
            
            executions = self.get_order_executions_detailed(
                start_date=today,
                end_date=today,
                ticker=ticker,
                ccld_nccs_dvsn="01"  # 체결만
            )
            
            if not executions.empty:
                # 해당 주문번호 찾기
                order = executions[executions['odno'] == order_number]
                if not order.empty:
                    row = order.iloc[0]
                    detail = {
                        'order_number': row['odno'],
                        'ticker': row['pdno'],
                        'name': row['prdt_name'],
                        'order_type': row['sll_buy_dvsn_cd_name'],
                        'quantity': int(row['ft_ccld_qty']),
                        'price': float(row['ft_ccld_unpr3']),
                        'amount_before_fee': float(row['ft_ccld_amt3']),
                        'fee': float(row['fee']),
                        'net_amount': float(row['net_amount']),
                        'deposit_change': float(row['deposit_change']),
                        'status': row['prcs_stat_name']
                    }
                    print(" 체결 확인 완료!")
                    return detail
            
            if attempt < max_attempts - 1:
                print(f"⏳ {wait_seconds}초 후 재시도...")
                time.sleep(wait_seconds)
        
        print("체결 확인 실패")
        return None

    # 서머타임(DST) 확인
    def is_us_dst(self):
        """
        미국 동부 시간 기준 현재 서머타임(DST) 여부 확인
        
        미국 서머타임 규칙:
        - 시작: 3월 두 번째 일요일 02:00
        - 종료: 11월 첫 번째 일요일 02:00
        
        Returns:
        bool: 서머타임이면 True, 아니면 False
        """
        # 현재 UTC 시간 가져오기 (timezone-naive)
        utc_now = datetime.utcnow()
        
        # 미국 동부 시간 계산 (일단 EST 기준 UTC-5로 계산)
        us_eastern_time = utc_now - timedelta(hours=5)
        year = us_eastern_time.year
        
        # 3월 두 번째 일요일 찾기
        march_first = datetime(year, 3, 1)
        days_to_sunday = (6 - march_first.weekday()) % 7
        first_sunday_march = march_first + timedelta(days=days_to_sunday)
        second_sunday_march = first_sunday_march + timedelta(days=7)
        dst_start = second_sunday_march.replace(hour=2, minute=0, second=0, microsecond=0)
        
        # 11월 첫 번째 일요일 찾기
        november_first = datetime(year, 11, 1)
        days_to_sunday = (6 - november_first.weekday()) % 7
        first_sunday_november = november_first + timedelta(days=days_to_sunday)
        dst_end = first_sunday_november.replace(hour=2, minute=0, second=0, microsecond=0)
        
        # 서머타임 기간 확인
        return dst_start <= us_eastern_time < dst_end

# 사용 예시
if __name__ == "__main__":
    # 계좌 정보 설정
    api = KIS_API(
        key_file_path = "C:/Users/ilpus/Desktop/NKL_invest/kis63721147nkr.txt",
        token_file_path = "C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/kis63721147_token.json",
        cano="63721147",
        acnt_prdt_cd="01"
    )
    get_US_stock_balance = api.get_US_stock_balance()
    get_total_balance = api.get_total_balance()
    get_US_dollar_balance = api.get_US_dollar_balance()
    print("\n=== 미국주식 주문 체결내역 추적 시스템 ===\n")
    print(get_US_stock_balance)
    print(get_US_dollar_balance)
    print(get_total_balance)

"""
[Header tr_id TTTT1002U(미국 매수 주문)]
00 : 지정가
32 : LOO(장개시지정가)
34 : LOC(장마감지정가)
35 : TWAP (시간가중평균)
36 : VWAP (거래량가중평균)
* TWAP, VWAP 주문은 분할시간 주문 입력 필수

[Header tr_id TTTT1006U(미국 매도 주문)]
00 : 지정가
31 : MOO(장개시시장가)
32 : LOO(장개시지정가)
33 : MOC(장마감시장가)
34 : LOC(장마감지정가)
35 : TWAP (시간가중평균)
36 : VWAP (거래량가중평균)
* TWAP, VWAP 주문은 분할시간 주문 입력 필수

[Header tr_id TTTS1001U(홍콩 매도 주문)]
00 : 지정가
50 : 단주지정가

※ TWAP, VWAP 주문은 정정 불가
"""