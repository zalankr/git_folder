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
        path = "/uapi/overseas-price/v1/quotations/price"
        url = f"{self.url_base}{path}"
        
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
    
    # 주식 시가 조회
    def get_US_open_price(self, ticker: str, exchange: Optional[str] = None) -> Union[float, str]:
        """
        미국 주식 시가 조회 (KIS API → yfinance 백업)
        
        Parameters:
        ticker (str): 주식 티커 심볼
        exchange (str): 거래소 코드 (None이면 자동 검색)
        
        Returns:
        float: 시가
        str: 에러 메시지
        """
        if not ticker:
            return "티커를 입력해주세요."
        
        ticker = ticker.upper()
        
        if exchange is None:
            exchange = self.get_US_exchange(ticker)
            if exchange is None:
                return self._get_open_price_from_yfinance(ticker)
        
        # KIS API 조회 시도
        open_price = self._get_open_price_from_kis(ticker, exchange)
        if isinstance(open_price, float):
            return open_price
        
        # yfinance 백업
        return self._get_open_price_from_yfinance(ticker)
    
    # KIS API로 시가 조회
    def _get_open_price_from_kis(self, ticker: str, exchange: str) -> Union[float, str]:
        """KIS API로 시가 조회 (기간별시세 API 사용)"""
        path = "/uapi/overseas-price/v1/quotations/dailyprice"
        url = f"{self.url_base}{path}"
        
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "HHDFS76240000"
        }
        
        params = {
            "AUTH": "",
            "EXCD": exchange,
            "SYMB": ticker,
            "GUBN": "0",  # 일봉
            "BYMD": "",   # 오늘 날짜
            "MODP": "0"   # 수정주가 미반영
        }
        
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get('rt_cd') == '0':
                output2 = data.get('output2', [])
                
                if output2 and len(output2) > 0:
                    latest = output2[0]
                    
                    # 시가(open) 확인
                    open_price = latest.get('open', '').strip()
                    if open_price and open_price != '0':
                        try:
                            price = float(open_price)
                            if price > 0:
                                return price
                        except (ValueError, TypeError):
                            pass
        except:
            pass
        
        return "KIS API 시가 조회 실패"
    
    # yfinance로 시가 조회
    def _get_open_price_from_yfinance(self, ticker: str) -> Union[float, str]:
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
    
    # 미국 주식 매수 주문
    def order_buy_US(self, ticker: str, quantity: int, price: float, 
                        exchange: Optional[str] = None, ord_dvsn: str = "00") -> Optional[requests.Response]:
        """미국 주식 매수 주문"""
        if exchange is None:
            exchange = self.get_US_exchange(ticker)
        
        if exchange is None:
            print(f"{ticker} 거래소를 찾을 수 없습니다.")
            return None
        
        path = "uapi/overseas-stock/v1/trading/order"
        url = f"{self.url_base}/{path}"

        data = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "OVRS_EXCG_CD": exchange,
            "PDNO": ticker,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(quantity),
            "OVRS_ORD_UNPR": str(price),
            "CTAC_TLNO": "",
            "MGCO_APTM_ODNO": "",
            "SLL_TYPE": "",
            "ORD_SVR_DVSN_CD": "0"
        }

        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "TTTT1002U",
            "custtype": "P",
            "hashkey": self.hashkey(data)
        }

        return requests.post(url, headers=headers, data=json.dumps(data))
    
    # 미국 주식 매도 주문
    def order_sell_US(self, ticker: str, quantity: int, price: float,
                        exchange: Optional[str] = None, ord_dvsn: str = "00") -> Optional[requests.Response]:
        """미국 주식 매도 주문 ord_dvsn "00"은 지정가 """
        if exchange is None:
            exchange = self.get_US_exchange(ticker)
        
        if exchange is None:
            print(f"{ticker} 거래소를 찾을 수 없습니다.")
            return None
        
        path = "uapi/overseas-stock/v1/trading/order"
        url = f"{self.url_base}/{path}"

        data = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "OVRS_EXCG_CD": exchange,
            "PDNO": ticker,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(quantity),
            "OVRS_ORD_UNPR": str(price),
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

        return requests.post(url, headers=headers, data=json.dumps(data))
    
    # 미국 주간거래 매수 주문 (Pre-market/After-hours)
    def order_daytime_buy_US(self, ticker: str, quantity: int, price: float,
                            exchange: Optional[str] = None) -> Optional[requests.Response]:
        """
        미국 주간거래 매수 주문 (Pre-market/After-hours)
        - 지정가 주문만 가능
        - 나스닥, NYSE, AMEX만 지원
        
        Parameters:
        ticker: 종목 코드
        quantity: 주문 수량
        price: 지정가
        exchange: 거래소 코드 (None이면 자동 검색)
        
        Returns:
        requests.Response 또는 None
        """
        if exchange is None:
            exchange = self.get_US_exchange(ticker)
        
        if exchange is None:
            print(f"{ticker} 거래소를 찾을 수 없습니다.")
            return None
        
        # 주간거래는 나스닥, NYSE, AMEX만 가능
        if exchange not in ["NAS", "NYS", "AMS"]:
            print(f"주간거래는 나스닥(NAS), 뉴욕(NYS), 아멕스(AMS)만 가능합니다. (현재: {exchange})")
            return None
        
        path = "uapi/overseas-stock/v1/trading/daytime-order"
        url = f"{self.url_base}/{path}"
        
        data = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "OVRS_EXCG_CD": exchange,
            "PDNO": ticker,
            "ORD_DVSN": "00",  # 주간거래는 지정가(00)만 가능
            "ORD_QTY": str(quantity),
            "OVRS_ORD_UNPR": str(price),
            "CTAC_TLNO": "",
            "MGCO_APTM_ODNO": "",
            "ORD_SVR_DVSN_CD": "0"
        }
        
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "TTTS6036U",  # 미국 주간거래 매수
            "custtype": "P",
            "hashkey": self.hashkey(data)
        }
        
        return requests.post(url, headers=headers, data=json.dumps(data))

    # 미국 주간거래 매도 주문 (Pre-market/After-hours)
    def order_daytime_sell_US(self, ticker: str, quantity: int, price: float,
                            exchange: Optional[str] = None) -> Optional[requests.Response]:
        """
        미국 주간거래 매도 주문 (Pre-market/After-hours)
        - 지정가 주문만 가능
        - 나스닥, NYSE, AMEX만 지원
        
        Parameters:
        ticker: 종목 코드
        quantity: 주문 수량
        price: 지정가
        exchange: 거래소 코드 (None이면 자동 검색)
        
        Returns:
        requests.Response 또는 None
        """
        if exchange is None:
            exchange = self.get_US_exchange(ticker)
        
        if exchange is None:
            print(f"{ticker} 거래소를 찾을 수 없습니다.")
            return None
        
        # 주간거래는 나스닥, NYSE, AMEX만 가능
        if exchange not in ["NAS", "NYS", "AMS"]:
            print(f"주간거래는 나스닥(NAS), 뉴욕(NYS), 아멕스(AMS)만 가능합니다. (현재: {exchange})")
            return None
        
        path = "uapi/overseas-stock/v1/trading/daytime-order"
        url = f"{self.url_base}/{path}"
        
        data = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "OVRS_EXCG_CD": exchange,
            "PDNO": ticker,
            "ORD_DVSN": "00",  # 주간거래는 지정가(00)만 가능
            "ORD_QTY": str(quantity),
            "OVRS_ORD_UNPR": str(price),
            "CTAC_TLNO": "",
            "MGCO_APTM_ODNO": "",
            "ORD_SVR_DVSN_CD": "0"
        }
        
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "TTTS6037U",  # 미국 주간거래 매도
            "custtype": "P",
            "hashkey": self.hashkey(data)
        }
        
        return requests.post(url, headers=headers, data=json.dumps(data))

    # 미국 주식 종목별 잔고
    def get_US_stock_balance(self) -> Optional[List[Dict]]:
        """미국 주식 종목별 잔고"""
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
            
            return stocks
        except:
            return None
    
    # 미국 달러 예수금
    def get_US_dollar_balance(self) -> Optional[Dict]:
        """미국 달러 예수금"""
        path = "uapi/overseas-stock/v1/trading/inquire-present-balance"
        url = f"{self.url_base}{path}"
        
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
        url = f"{self.url_base}{path}"
        
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
    def check_order_execution(self, order_number, ticker, wait_seconds=10, order_type="00"):
        """
        주문 체결 확인 함수
        
        Parameters:
        order_number (str): 주문번호 (ODNO)
        ticker (str): 종목코드
        wait_seconds (int): 대기 시간 (초)
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
        # 대기
        print(f"\n⏰ {wait_seconds}초 대기 중...")
        time.sleep(wait_seconds)
        
        # 오늘 날짜
        today = datetime.now().strftime('%Y%m%d')
        
        # 거래소 확인
        exchange = self.get_US_exchange(ticker)
        if not exchange:
            print(f"✗ {ticker}의 거래소를 찾을 수 없습니다.")
            return None
        
        # 체결 내역 조회
        print(f"\n🔍 주문번호 {order_number} 체결 내역 확인 중...")
        
        path = "/uapi/overseas-stock/v1/trading/inquire-ccnl"
        url = f"{self.url_base}{path}"
        
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

    # ==================== 추가된 메서드: 체결내역 조회 및 수수료 계산 ====================
    
    def get_order_executions_detailed(
        self,
        start_date: str = None,
        end_date: str = None,
        ticker: str = "",
        sll_buy_dvsn: str = "00",
        ccld_nccs_dvsn: str = "01",
        exchange: str = "NASD"
    ) -> pd.DataFrame:
        """
        주문 체결내역 상세 조회 (수수료 계산 포함)
        
        Parameters:
        start_date: 조회 시작일 (YYYYMMDD)
        end_date: 조회 종료일 (YYYYMMDD)
        ticker: 종목코드
        sll_buy_dvsn: 00:전체, 01:매도, 02:매수
        ccld_nccs_dvsn: 00:전체, 01:체결, 02:미체결
        exchange: 거래소코드
        
        Returns:
        pd.DataFrame: 체결내역 + 수수료 계산
        """
        # 날짜 기본값 설정
        if start_date is None:
            start_date = datetime.now().strftime('%Y%m%d')
        if end_date is None:
            end_date = datetime.now().strftime('%Y%m%d')
        
        path = "/uapi/overseas-stock/v1/trading/inquire-ccnl"
        url = f"{self.url_base}{path}"
        
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "TTTS3035R",
            "custtype": "P"
        }
        
        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "PDNO": ticker,
            "ORD_STRT_DT": start_date,
            "ORD_END_DT": end_date,
            "SLL_BUY_DVSN": sll_buy_dvsn,
            "CCLD_NCCS_DVSN": ccld_nccs_dvsn,
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
                if not orders:
                    return pd.DataFrame()
                
                df = pd.DataFrame(orders)
                
                # 수치형 변환
                df['ft_ccld_qty'] = pd.to_numeric(df['ft_ccld_qty'], errors='coerce')
                df['ft_ccld_unpr3'] = pd.to_numeric(df['ft_ccld_unpr3'], errors='coerce')
                df['ft_ccld_amt3'] = pd.to_numeric(df['ft_ccld_amt3'], errors='coerce')
                
                # 매도/매수 구분
                df['is_sell'] = df['sll_buy_dvsn_cd'] == '01'
                
                # 수수료 계산
                df['fee'] = 0.0
                df.loc[df['is_sell'], 'fee'] = df.loc[df['is_sell'], 'ft_ccld_amt3'] * self.SELL_FEE_RATE
                
                # 순 체결금액 (매도: 수수료 차감, 매수: 그대로)
                df['net_amount'] = df['ft_ccld_amt3'] - df['fee']
                
                # 예수금 변동액 (매도: +, 매수: -)
                df['deposit_change'] = df['net_amount']
                df.loc[~df['is_sell'], 'deposit_change'] = -df.loc[~df['is_sell'], 'ft_ccld_amt3']
                
                # 반올림
                df['fee'] = df['fee'].round(2)
                df['net_amount'] = df['net_amount'].round(2)
                df['deposit_change'] = df['deposit_change'].round(2)
                
                return df
            else:
                print(f"API 오류: {result.get('msg1')}")
                return pd.DataFrame()
                
        except Exception as e:
            print(f"체결내역 조회 오류: {e}")
            return pd.DataFrame()
    
    def get_usd_deposit_info(self) -> Dict:
        """
        USD 예수금 상세 정보 조회
        
        Returns:
        Dict: {
            'deposit': 예수금,
            'withdrawable': 출금가능금액,
            'exchange_rate': 환율,
            'krw_value': 원화환산금액
        }
        """
        return self.get_US_dollar_balance()
    
    def print_execution_summary(
        self, 
        executions_df: pd.DataFrame, 
        initial_balance: Dict = None
    ):
        """
        체결내역 요약 출력
        
        Parameters:
        executions_df: 체결내역 DataFrame
        initial_balance: 초기 잔고 정보
        """
        if executions_df.empty:
            print("체결내역이 없습니다.")
            return
        
        print("\n" + "="*120)
        print("미국주식 주문 체결내역 요약")
        print("="*120)
        
        if initial_balance:
            print(f"\n[초기 USD 예수금]")
            print(f"예수금: ${initial_balance['deposit']:,.2f}")
            print(f"출금가능: ${initial_balance['withdrawable']:,.2f}")
            print(f"환율: ₩{initial_balance['exchange_rate']:,.2f}")
        
        total_sell_amount = 0
        total_buy_amount = 0
        total_fees = 0
        
        print(f"\n{'주문번호':<15} {'종목':<8} {'구분':<6} {'수량':<6} {'단가':<10} "
              f"{'체결금액':<12} {'수수료':<10} {'입출금액':<12} {'상태':<10}")
        print("-"*120)
        
        for idx, row in executions_df.iterrows():
            is_sell = row['deposit_change'] > 0
            
            print(f"{row['odno']:<15} "
                  f"{row['pdno']:<8} "
                  f"{row['sll_buy_dvsn_cd_name']:<6} "
                  f"{int(row['ft_ccld_qty']):<6} "
                  f"${row['ft_ccld_unpr3']:<9,.2f} "
                  f"${row['ft_ccld_amt3']:<11,.2f} "
                  f"${row['fee']:<9,.2f} "
                  f"${row['deposit_change']:+11,.2f} "
                  f"{row['prcs_stat_name']:<10}")
            
            if is_sell:
                total_sell_amount += row['net_amount']
            else:
                total_buy_amount += abs(row['deposit_change'])
            
            total_fees += row['fee']
        
        print("="*120)
        print(f"\n[합계]")
        print(f"총 매도 입금액: ${total_sell_amount:,.2f}")
        print(f"총 매수 출금액: ${total_buy_amount:,.2f}")
        print(f"총 수수료: ${total_fees:,.2f}")
        print(f"순 예수금 변동: ${(total_sell_amount - total_buy_amount):+,.2f}")
        
        if initial_balance:
            final_balance = initial_balance['deposit'] + (total_sell_amount - total_buy_amount)
            print(f"\n예상 최종 예수금: ${final_balance:,.2f}")
            print(f"예수금 변동: ${(final_balance - initial_balance['deposit']):+,.2f}")
    
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
                    print("✅ 체결 확인 완료!")
                    return detail
            
            if attempt < max_attempts - 1:
                print(f"⏳ {wait_seconds}초 후 재시도...")
                time.sleep(wait_seconds)
        
        print("❌ 체결 확인 실패")
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
        key_file_path="C:/Users/ilpus/Desktop/NKL_invest/kis63721147nkr.txt",
        token_file_path="C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/kis63721147_token.json",
        cano="63721147",
        acnt_prdt_cd="01"
    )
    
    print("\n=== 미국주식 주문 체결내역 추적 시스템 ===\n")
    
    # 1. 초기 USD 예수금 조회
    print("[1] 초기 USD 예수금 조회")
    initial_balance = api.get_usd_deposit_info()
    if initial_balance:
        print(f"현재 예수금: ${initial_balance['deposit']:,.2f}")
        print(f"출금가능: ${initial_balance['withdrawable']:,.2f}")
        print(f"환율: ₩{initial_balance['exchange_rate']:,.2f}")
    
    # 2. 오늘의 체결내역 조회
    print("\n[2] 오늘의 체결내역 조회")
    today = datetime.now().strftime('%Y%m%d')
    executions_df = api.get_order_executions_detailed(
        start_date=today,
        end_date=today,
        ccld_nccs_dvsn="01"  # 체결만
    )
    
    # 3. 체결내역 출력
    if not executions_df.empty:
        print(f"\n총 {len(executions_df)}건의 체결내역 발견")
        api.print_execution_summary(executions_df, initial_balance)
        
        # 4. 최종 예수금 확인
        print("\n[4] 최종 USD 예수금 확인")
        final_balance = api.get_usd_deposit_info()
        if final_balance and initial_balance:
            print(f"최종 예수금: ${final_balance['deposit']:,.2f}")
            print(f"변동액: ${(final_balance['deposit'] - initial_balance['deposit']):+,.2f}")
    else:
        print("오늘 체결된 주문이 없습니다.")
    
    # 예제: 특정 주문번호 추적
    # execution_info = api.track_order_execution(
    #     order_number="0123456789",
    #     ticker="AAPL",
    #     wait_seconds=10,
    #     max_attempts=5
    # )
    # if execution_info:
    #     print(f"\n체결 상세:")
    #     print(f"종목: {execution_info['name']} ({execution_info['ticker']})")
    #     print(f"구분: {execution_info['order_type']}")
    #     print(f"수량: {execution_info['quantity']}")
    #     print(f"단가: ${execution_info['price']:,.2f}")
    #     print(f"체결금액: ${execution_info['amount_before_fee']:,.2f}")
    #     print(f"수수료: ${execution_info['fee']:,.2f}")
    #     print(f"입출금액: ${execution_info['deposit_change']:+,.2f}")


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