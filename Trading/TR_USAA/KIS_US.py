import requests
import json
from datetime import datetime, timedelta
import kakao_alert as KA
import sys
import os
from typing import Union, Optional, Dict, List, Tuple
import time

class KIS_API:
    """한국투자증권 API 클래스 (최종 정제 버전 + 체결내역 추적 기능)"""
    
    def __init__(self, key_file_path: str, token_file_path: str, cano: str, acnt_prdt_cd: str):
        self.key_file_path = key_file_path
        self.token_file_path = token_file_path
        self.cano = cano
        self.acnt_prdt_cd = acnt_prdt_cd
        self.url_base = "https://openapi.koreainvestment.com:9443"
        
        self._load_api_keys()
        self.access_token = self.get_access_token()
        self.SELL_FEE_RATE = 0.0009  # 매도 수수료 0.09% 이벤트 계좌
        self.BUY_FEE_RATE = 0.0009  # 매수 수수료 0.09% 이벤트 계좌
    
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
            KA.SendMessage(f"KIS 토큰 로드 오류: {e}")
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
            KA.SendMessage(f"KIS 토큰 저장 오류: {e}")
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
            safe_expiry_time = expiry_time - timedelta(minutes=60)
            
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
            KA.SendMessage(f"KIS 토큰 발급 실패: {e}")
            sys.exit(0)
            # return None

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

    # Ticker로 거래소명 조회
    def get_exchange_by_ticker(self, ticker: str) -> str:
        """
        미국 주식 거래소 조회       
        Parameters:
        ticker (str): 주식 티커 심볼        
        Returns:
        str: 거래소명
        str: 에러 메시지
        """
        if not ticker:
            return "error:티커를 입력해주세요."
        
        ticker = ticker.upper()
        
        exchanges = ["NAS", "AMS", "NYS", "BAY", "BAQ", "BAA"]

        for exchange in exchanges:
            price = self.get_price_from_kis(ticker, exchange)
            if isinstance(price, float):
                return exchange
            time.sleep(0.1)

        return "error: 거래소 조회 실패"

    # 주식 현재가 조회
    def get_US_current_price(self, ticker: str) -> Union[float, str]:
        """
        미국 주식 현재가 조회       
        Parameters:
        ticker (str): 주식 티커 심볼        
        Returns:
        float: 현재가
        str: 에러 메시지
        """
        if not ticker:
            return "티커를 입력해주세요."
        
        ticker = ticker.upper()

        # 거래소 목록 정의
        exchanges = ["NAS", "AMS", "NYS", "BAY", "BAQ", "BAA"]
        
        for exchange in exchanges:
            price = self.get_price_from_kis(ticker, exchange)
            if isinstance(price, float):
                return price
            time.sleep(0.1)

        return "현재가 조회 실패"

    # KIS API로 현재가 조회
    def get_price_from_kis(self, ticker: str, exchange: str) -> Union[float, str]:
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
    
    # 미국 정규시장 주식 매도 주문
    def order_sell_US(self, ticker: str, quantity: int, price: float,
                        exchange: Optional[str] = None, ord_dvsn: str = "00") -> Optional[Dict]:
        """
        미국 주식 매도 주문 (Regular Market)
        
        Parameters:
        ticker: 종목 코드
        quantity: 주문 수량
        price: 지정가
        exchange: 거래소 코드 ("NASD" > "NYSE" > "AMEX" > "BAT" > "ARC"순서)
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
        order_sell_message = []

        if exchange is None:
            exchange = self.get_exchange_by_ticker(ticker)
            if exchange == "NAS" or exchange == "BAQ":
                exchange = "NASD"
            elif exchange == "AMS" or exchange == "BAA":
                exchange = "AMEX"
            elif exchange == "NYS" or exchange == "BAY":
                exchange = "NYSE"
            else:
                exchange = None
        
        if exchange is None:
            order_sell_message.append(f"{ticker} 거래소를 찾을 수 없습니다.")
            order_info = None
            return order_info, order_sell_message
        
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
                
                order_sell_message.append(f"정규매도 주문: {ticker} {quantity}주 @ ${price:.2f} \n주문번호: {order_info['order_number']}")                
                return order_info, order_sell_message
            else:
                order_sell_message.append(f"정규매도 주문실패: {result.get('msg1', '알 수 없는 오류')}")
                order_info = {
                    'success': False,
                    'ticker': ticker,
                    'quantity': quantity,
                    'price': price,
                    'order_number': '',
                    'error_code': result.get('rt_cd'),
                    'error_message': result.get('msg1', ''),
                    'response': response
                }
                return order_info, order_sell_message
                
        except requests.exceptions.RequestException as e:
            order_sell_message.append(f"정규매도 주문 오류: {e}")
            order_info = None
            return order_info, order_sell_message
                
        except Exception as e:
            order_sell_message.append(f"정규매도 주문 오류: {e}")
            order_info = None
            return order_info, order_sell_message

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

        order_buy_message = []

        if exchange is None:
            exchange = self.get_exchange_by_ticker(ticker)
            if exchange == "NAS" or exchange == "BAQ":
                exchange = "NASD"
            elif exchange == "AMS" or exchange == "BAA":
                exchange = "AMEX"
            elif exchange == "NYS" or exchange == "BAY":
                exchange = "NYSE"
            else:
                exchange = None
        
        if exchange is None:
            order_buy_message.append(f"{ticker} 거래소를 찾을 수 없습니다.")
            order_info = None
            return order_info, order_buy_message
        
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
                
                order_buy_message.append(f"정규매수 주문: {ticker} {quantity}주 @ ${price:.2f} \n주문번호: {order_info['order_number']}")
                return order_info, order_buy_message
            else:
                order_buy_message.append(f"정규매수 주문실패: {result.get('msg1', '알 수 없는 오류')}")
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
            order_buy_message.append(f"정규매수 주문 오류: {e}")
            order_info = None
            return order_info, order_buy_message
    
    # 미국 주간거래 매수 주문 (국내 증권사지원 주간거래)
    def order_daytime_buy_US(self, ticker: str, quantity: int, price: float,
                            exchange: Optional[str] = None) -> Optional[Dict]:
        """
        미국 국내 증권사지원 주간거래 매수주문
        
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
            exchange = self.get_exchange_by_ticker(ticker)
            if exchange == "NAS" or exchange == "BAQ":
                exchange = "NASD"
            elif exchange == "AMS" or exchange == "BAA":
                exchange = "AMEX"
            elif exchange == "NYS" or exchange == "BAY":
                exchange = "NYSE"
            else:
                exchange = None
        
        if exchange is None:
            KA.SendMessage(f"{ticker} 거래소를 찾을 수 없습니다.")
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
                
                KA.SendMessage(f"주간매수 주문: {ticker} {quantity}주 @ ${price:.2f} \n주문번호: {order_info['order_number']}")
                return order_info
            else:
                KA.SendMessage(f"주간매수 주문실패: {result.get('msg1', '알 수 없는 오류')}")
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
            KA.SendMessage(f"주간매수 주문 오류: {e}")
            return None

    # 미국 주간거래 매도 주문 (국내 증권사지원 주간거래)
    def order_daytime_sell_US(self, ticker: str, quantity: int, price: float,
                            exchange: Optional[str] = None) -> Optional[Dict]:
        """
        미국 국내 증권사지원 주간거래 매도주문
        
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
            exchange = self.get_exchange_by_ticker(ticker)
            if exchange == "NAS" or exchange == "BAQ":
                exchange = "NASD"
            elif exchange == "AMS" or exchange == "BAA":
                exchange = "AMEX"
            elif exchange == "NYS" or exchange == "BAY":
                exchange = "NYSE"
            else:
                exchange = None
        
        if exchange is None:
            KA.SendMessage(f"{ticker} 거래소를 찾을 수 없습니다.")
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
                
                KA.SendMessage(f"주간매도 주문: {ticker} {quantity}주 @ ${price:.2f} \n주문번호: {order_info['order_number']}")
                return order_info
            else:
                KA.SendMessage(f"주간매도 주문실패: {result.get('msg1', '알 수 없는 오류')}")
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
            KA.SendMessage(f"주간매도 주문오류: {e}")
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
                KA.SendMessage(f"API 오류: {data.get('msg1')}")
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
            KA.SendMessage(f"잔고 조회 오류: {e}")
            return None

    # 미국 달러 예수금
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
                'withdrawable': float(usd_info.get('frcr_drwg_psbl_amt_1', 0)), # 출금가능액, 정확한 거래가능금액
                'exchange_rate': float(usd_info.get('frst_bltn_exrt', 0)),
                'krw_value': float(usd_info.get('frcr_evlu_amt2', 0))
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
        exchange = self.get_exchange_by_ticker(ticker)
        if exchange == "NAS" or exchange == "BAQ":
            exchange = "NASD"
        elif exchange == "AMS" or exchange == "BAA":
            exchange = "AMEX"
        elif exchange == "NYS" or exchange == "BAY":
            exchange = "NYSE"
        else:
            exchange = None
        
        if exchange is None:
            print(f"{ticker} 거래소를 찾을 수 없습니다.")
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

    # 미국 주식 주문 취소
    def cancel_US_order(self, order_number: str, ticker: str, 
                        quantity: int, exchange: Optional[str] = None,
                        ) -> Optional[Dict]:
        """
        미국 주식 주문 취소
        
        Parameters:
        order_number (str): 취소할 주문번호 (ODNO)
        ticker (str): 종목코드
        quantity (int): 취소 수량 (전량 취소시 원주문 수량)
        exchange (str): 거래소 코드 (None이면 자동 검색)
        
        Returns:
        Dict 또는 None - 취소 결과
        """
        message = []
        # 거래소 확인
        exchange = self.get_exchange_by_ticker(ticker)
        if exchange == "NAS" or exchange == "BAQ":
            exchange = "NASD"
        elif exchange == "AMS" or exchange == "BAA":
            exchange = "AMEX"
        elif exchange == "NYS" or exchange == "BAY":
            exchange = "NYSE"
        else:
            exchange = None
        
        if exchange is None:
            print(f"{ticker} 거래소를 찾을 수 없습니다.")
            return None
        
        # 정규장 TR_ID
        tr_id = "TTTT1004U"
        path = "uapi/overseas-stock/v1/trading/order-rvsecncl"
        url = f"{self.url_base}/{path}"
        
        data = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "OVRS_EXCG_CD": exchange,
            "PDNO": ticker,
            "ORGN_ODNO": order_number,
            "ORD_DVSN": "00",
            "RVSE_CNCL_DVSN_CD": "02",  # 02: 취소
            "ORD_QTY": "0",  # 취소는 0
            "OVRS_ORD_UNPR": "0",  # 취소는 0
            "CTAC_TLNO": "",
            "MGCO_APTM_ODNO": "",
            "ORD_SVR_DVSN_CD": "0"
        }
        
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
            "hashkey": self.hashkey(data)
        }
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(data))
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('rt_cd') == '0':
                # print(f"주문 취소 성공: {ticker} (주문번호: {order_number})")
                return {
                    'success': True,
                    'ticker': ticker,
                    'order_number': order_number,
                    'message': result.get('msg1', ''),
                    'response': response
                }
            else:
                # print(f"주문 취소 실패: {result.get('msg1', '알 수 없는 오류')}")
                return {
                    'success': False,
                    'ticker': ticker,
                    'order_number': order_number,
                    'error_message': result.get('msg1', ''),
                    'response': response
                }
                
        except Exception as e:
            print(f"주문 취소 오류: {e}")
            return None

    # 미체결 주문 조회
    def get_unfilled_orders(self, start_date: Optional[str] = None, 
                        end_date: Optional[str] = None) -> List[Dict]:
        """
        미체결 주문 조회
        
        Parameters:
        start_date (str): 시작일 (YYYYMMDD) - None이면 오늘
        end_date (str): 종료일 (YYYYMMDD) - None이면 오늘
        
        Returns:
        List[Dict]: 미체결 주문 리스트
        """
        if start_date is None or end_date is None:
            today = datetime.now().strftime('%Y%m%d')
            start_date = end_date = today
        
        path = "uapi/overseas-stock/v1/trading/inquire-nccs"
        url = f"{self.url_base}/{path}"
        
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "TTTS3018R"
        }
        
        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "PDNO": "",
            "ORD_STRT_DT": start_date,
            "ORD_END_DT": end_date,
            "SLL_BUY_DVSN": "00",  # 00: 전체
            "CCLD_NCCS_DVSN": "02",  # 02: 미체결만
            "OVRS_EXCG_CD": "",  # 전체
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
                
                unfilled_orders = []
                for order in orders:
                    unfilled_orders.append({
                        'order_number': order.get('odno', ''),
                        'ticker': order.get('pdno', ''),
                        'name': order.get('prdt_name', ''),
                        'order_type': order.get('sll_buy_dvsn_cd_name', ''),
                        'order_qty': int(order.get('ft_ord_qty', 0)),
                        'filled_qty': int(order.get('ft_ccld_qty', 0)),
                        'unfilled_qty': int(order.get('nccs_qty', 0)),
                        'order_price': float(order.get('ft_ord_unpr3', 0)),
                        'exchange': order.get('ovrs_excg_cd', ''),
                        'status': order.get('prcs_stat_name', '')
                    })
                
                return unfilled_orders
            else:
                print(f"미체결 조회 실패: {result.get('msg1')}")
                return []
                
        except Exception as e:
            print(f"미체결 조회 오류: {e}")
            return []

    # 모든 미체결 주문 취소 >>> 오류수정
    def cancel_all_unfilled_orders(self, start_date: Optional[str] = None,
                                end_date: Optional[str] = None
                                ) -> Tuple[Dict, List[str]]:
        """
        모든 미체결 주문 일괄 취소
        
        Parameters:
        start_date (str): 시작일 (YYYYMMDD) - None이면 오늘
        end_date (str): 종료일 (YYYYMMDD) - None이면 오늘
        
        Returns:
        Dict: 취소 결과 요약
        {
            'total': int,           # 전체 미체결 주문 수
            'success': int,         # 취소 성공 수
            'failed': int,          # 취소 실패 수
            'success_list': List,   # 성공한 주문 리스트
            'failed_list': List     # 실패한 주문 리스트
        }
        """
        # 1. 미체결 주문 조회
        unfilled_orders = self.get_unfilled_orders(start_date, end_date)
        
        if not unfilled_orders:
            summary = {
                'total': 0,
                'success': 0,
                'failed': 0,
                'success_list': [],
                'failed_list': []
            }
            message = ["미체결 주문 없음"]
            return summary, message

        # 2. 각 주문 취소
        success_list = []
        failed_list = []
        
        for i, order in enumerate(unfilled_orders, 1):
            result = self.cancel_US_order(
                order_number=order['order_number'],
                ticker=order['ticker'],
                quantity=order['order_qty'],
                exchange=order['exchange']
            )
            
            # 결과 처리
            if result and result.get('success'):
                success_list.append({
                    'ticker': order['ticker'],
                    'name': order['name'],
                    'order_number': order['order_number'],
                    'unfilled_qty': order['unfilled_qty']
                })
            else:
                failed_list.append({
                    'ticker': order['ticker'],
                    'name': order['name'],
                    'order_number': order['order_number'],
                    'unfilled_qty': order['unfilled_qty'],
                    'error': result.get('error_message') if result else '알 수 없는 오류'
                })
            
            # API 호출 간격 (0.2초)
            time.sleep(0.2)
        
        # 3. 결과 요약
        summary = {
            'total': len(unfilled_orders),
            'success': len(success_list),
            'failed': len(failed_list),
            'success_list': success_list,
            'failed_list': failed_list
        }
        
        # 4. 결과 출력
        message = []
        message.append(f"전체 미체결: {summary['total']}건")
        message.append(f"취소 성공: {summary['success']}건")
        message.append(f"취소 실패: {summary['failed']}건")
        return summary, message

    # SPY ETF 60개월 전고가 분석 (수정 버전)
    def get_spy_60month_analysis(self, ticker: str = "SPY") -> Union[Dict, str]:
        """
        SPY ETF 분석:
        1. 60개월전~1개월전까지의 일별 종가 전고가
        2. 최근 1개월간의 일별 종가 최고가
        3. 현재가
        4. 전고가 대비 1개월 최고가 비율
        5. 전고가 대비 현재가 비율
        
        Parameters:
        ticker (str): 주식 티커 심볼 (기본값: SPY)
        
        Returns:
        Dict: {
            'ath_60to1months': float,           # 60개월~1개월전 전고가
            'high_1month': float,               # 최근 1개월 최고가
            'current_price': float,             # 현재가
            'high_1month_percentage': float,    # 전고가 대비 1개월 최고가 비율(%)
            'current_percentage': float         # 전고가 대비 현재가 비율(%)
        }
        str: 에러 메시지
        """
        if not ticker:
            return "티커를 입력해주세요."
        
        ticker = ticker.upper()
        
        # 1. 거래소 조회
        exchange = self.get_exchange_by_ticker(ticker)
        if not isinstance(exchange, str) or exchange == "거래소 조회 실패":
            return f"{ticker} 거래소 조회 실패"
        
        # 2. 날짜 계산
        today = datetime.now()
        date_60months_ago = today - timedelta(days=60*31)  # 60개월 전
        date_1month_ago = today - timedelta(days=1*31)     # 1개월 전
        
        # 3. API 헤더 설정
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "HHDFS76240000"
        }
        
        try:
            # 4. 60개월전~1개월전 데이터 조회 (전고가 계산용)
            closing_prices_60to1 = []
            
            # 한국투자증권 API는 한 번에 100개 데이터만 조회되므로 여러 번 호출 필요
            current_date = date_1month_ago
            while current_date >= date_60months_ago:
                params = {
                    "AUTH": "",
                    "EXCD": exchange,
                    "SYMB": ticker,
                    "GUBN": "0",  # 0: 일봉
                    "BYMD": current_date.strftime('%Y%m%d'),
                    "MODP": "1"
                }
                
                path = "uapi/overseas-price/v1/quotations/dailyprice"
                url = f"{self.url_base}/{path}"
                
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()
                
                result = response.json()
                
                if result.get('rt_cd') == '0':
                    output2 = result.get('output2', [])
                    
                    for data in output2:
                        # 날짜 필터링: 60개월전 ~ 1개월전
                        data_date_str = data.get('xymd', '')
                        if data_date_str:
                            try:
                                data_date = datetime.strptime(data_date_str, '%Y%m%d')
                                if date_60months_ago <= data_date <= date_1month_ago:
                                    close_price = data.get('clos', '')
                                    if close_price and close_price != '0':
                                        closing_prices_60to1.append(float(close_price))
                            except:
                                continue
                    
                    # 더 이상 데이터가 없으면 중단
                    if len(output2) < 100:
                        break
                    
                    # 다음 조회를 위한 날짜 업데이트 (100일 이전)
                    if output2:
                        last_date_str = output2[-1].get('xymd', '')
                        if last_date_str:
                            current_date = datetime.strptime(last_date_str, '%Y%m%d') - timedelta(days=1)
                        else:
                            break
                else:
                    break
                
                # API 호출 제한을 위한 대기
                time.sleep(0.2)
            
            if not closing_prices_60to1:
                return f"{ticker} 60개월~1개월전 데이터 조회 실패"
            
            # 5. 60개월~1개월전 전고가 계산
            ath_60to1months = max(closing_prices_60to1)
            
            # 6. 최근 1개월 데이터 조회 (최고가 계산용)
            closing_prices_1month = []
            
            params = {
                "AUTH": "",
                "EXCD": exchange,
                "SYMB": ticker,
                "GUBN": "0",  # 0: 일봉
                "BYMD": date_1month_ago.strftime('%Y%m%d'),
                "MODP": "1"
            }
            
            path = "uapi/overseas-price/v1/quotations/dailyprice"
            url = f"{self.url_base}/{path}"
            
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('rt_cd') == '0':
                output2 = result.get('output2', [])
                
                for data in output2:
                    # 날짜 필터링: 최근 1개월
                    data_date_str = data.get('xymd', '')
                    if data_date_str:
                        try:
                            data_date = datetime.strptime(data_date_str, '%Y%m%d')
                            if data_date >= date_1month_ago:
                                close_price = data.get('clos', '')
                                if close_price and close_price != '0':
                                    closing_prices_1month.append(float(close_price))
                        except:
                            continue
            
            if not closing_prices_1month:
                return f"{ticker} 최근 1개월 데이터 조회 실패"
            
            # 7. 최근 1개월 최고가 계산
            high_1month = max(closing_prices_1month)
            
            # 8. 현재가 조회
            current_price = self.get_US_current_price(ticker)
            if not isinstance(current_price, float):
                return f"{ticker} 현재가 조회 실패"
            
            # 9. 비율 계산
            high_1month_percentage = (high_1month / ath_60to1months) * 100
            current_percentage = (current_price / ath_60to1months) * 100
            
            return {
                'ath_60to1months': ath_60to1months,
                'high_1month': high_1month,
                'current_price': current_price,
                'high_1month_percentage': round(high_1month_percentage, 2),
                'current_percentage': round(current_percentage, 2)
            }
            
        except Exception as e:
            return f"{ticker} 분석 중 오류 발생: {str(e)}"

    # 특정 ticker의 보유 잔고 조회
    def get_ticker_balance(self, ticker: str) -> Union[Dict, str]:
        """
        특정 ticker의 계좌 내 보유 잔고 조회
        
        Parameters:
        ticker (str): 주식 티커 심볼
        
        Returns:
        Dict: {
            'ticker': str,              # 티커 심볼
            'holding_qty': float,       # 보유 수량
            'avg_price': float,         # 매입 평균가
            'current_price': float,     # 현재가
            'eval_amount': float,       # 평가금액
            'profit_loss': float,       # 평가손익금액
            'profit_rate': float,       # 평가손익율(%)
            'currency': str,            # 거래통화코드
            'exchange': str             # 거래소코드
        }
        str: 에러 메시지 또는 "보유 잔고 없음"
        """
        if not ticker:
            return "error: 티커를 입력해주세요."
        
        ticker = ticker.upper()
        
        # 1. 거래소 조회
        exchange = self.get_exchange_by_ticker(ticker)
        if not isinstance(exchange, str) or exchange == "거래소 조회 실패":
            return f"error: {ticker} 거래소 조회 실패"
        
        # 2. 거래소 코드에 따른 통화 코드 설정
        currency_map = {
            "NAS": "USD", "NASD": "USD", "NYS": "USD", "NYSE": "USD", 
            "AMS": "USD", "AMEX": "USD", "BAY": "USD", "BAQ": "USD", "BAA": "USD",
            "SEHK": "HKD",
            "SHAA": "CNY", "SZAA": "CNY",
            "TKSE": "JPY",
            "HASE": "VND", "VNSE": "VND"
        }
        
        tr_crcy_cd = currency_map.get(exchange, "USD")
        
        # 3. 해외주식 잔고 조회 API 호출
        path = "uapi/overseas-stock/v1/trading/inquire-balance"
        url = f"{self.url_base}/{path}"
        
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "TTTS3012R"
        }
        
        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "OVRS_EXCG_CD": exchange,
            "TR_CRCY_CD": tr_crcy_cd,
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": ""
        }
        
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('rt_cd') != '0':
                return f"{ticker} 잔고 조회 실패: {result.get('msg1', '알 수 없는 오류')}"
            
            # output2에서 해당 ticker 찾기
            output2 = result.get('output2', [])
            
            for item in output2:
                # ovrs_pdno는 ticker를 의미
                if item.get('ovrs_pdno', '').upper() == ticker:
                    holding_qty = float(item.get('ovrs_cblc_qty', '0'))
                    
                    # return holding_qty                    
                    return {
                        'ticker': ticker, # 종목코드
                        'holding_qty': holding_qty, # 보유수량
                        'avg_price': float(item.get('pchs_avg_pric', '0')), # 매입평균가격
                        'current_price': float(item.get('now_pric2', '0')), # 현재가격
                        'eval_amount': float(item.get('ovrs_stck_evlu_amt', '0')), # 해외주식평가금액
                        'profit_loss': float(item.get('frcr_evlu_pfls_amt', '0')), # 외화평가손익금액
                        'profit_rate': float(item.get('evlu_pfls_rt', '0')), # 평가손익율 (%)
                        'currency': item.get('tr_crcy_cd', tr_crcy_cd), # 거래통화코드 (USD, JPY 등)
                        'exchange': item.get('ovrs_excg_cd', exchange) # 해외거래소코드 (NASDAQ, NYSE 등)
                    }
            
            return "보유 잔고 없음"
            
        except Exception as e:
            return f"{ticker} 잔고 조회 중 오류 발생: {str(e)}"
        
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