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
        self.sell_fee_tax = 0.00214  # 매도 수수료 0.014% + 세금 0.2% KRQT계좌
        self.buy_fee_tax = 0.00014  # 매수 수수료 0.014% KRQT 계좌

        self.last_api_call = 0
        self.api_interval = 0.07 # 초당 ~14회 요청 인터벌
    
    def _rate_limit_sleep(self):
        """API 호출 간격 제어 (Rate Limit 대응)"""
        elapsed = time.time() - self.last_api_call
        if elapsed < self.api_interval:
            time.sleep(self.api_interval - elapsed)
        self.last_api_call = time.time()

    # API-Key 로드 
    def _load_api_keys(self):
        try:
            with open(self.key_file_path) as f:
                self.app_key, self.app_secret = [line.strip() for line in f.readlines()]
        except FileNotFoundError:
            KA.SendMessage(f"API Key 파일을 찾을 수 없습니다: {self.key_file_path}")
            sys.exit(1)
        except Exception as e:
            KA.SendMessage(f"API Key 로드 실패: {e}")
            sys.exit(1)
    
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
            response = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
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
        try:
            res = requests.post(url, headers=headers, data=json.dumps(datas), timeout=5)
            res.raise_for_status()
            return res.json()["HASH"]
        except Exception as e:
            KA.SendMessage(f"Hashkey 생성 실패: {e}")
            return ""

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

        # 500 에러 재시도 로직
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    time.sleep(1)  # 재시도 전 1초 대기
                    order_sell_message.append(f"재시도 {attempt}/{max_retries}")
                
                response = requests.post(url, headers=headers, data=json.dumps(data), timeout=10)
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
                    
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 500 and attempt < max_retries:
                    order_sell_message.append(f"500 에러 발생, 재시도 중...")
                    continue
                else:
                    order_sell_message.append(f"정규매도 주문 오류: {e}")
                    order_info = None
                    return order_info, order_sell_message
                    
            except Exception as e:
                if attempt < max_retries:
                    order_sell_message.append(f"에러 발생, 재시도 중...")
                    continue
                else:
                    order_sell_message.append(f"정규매도 주문 오류: {e}")
                    order_info = None
                    return order_info, order_sell_message
        
        # 모든 재시도 실패
        order_sell_message.append(f"정규매도 주문 최종 실패: 모든 재시도 소진")
        return None, order_sell_message

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

        # 500 에러 재시도 로직
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    time.sleep(1)  # 재시도 전 1초 대기
                    order_buy_message.append(f"재시도 {attempt}/{max_retries}")
                
                response = requests.post(url, headers=headers, data=json.dumps(data), timeout=10)
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
                    }, order_buy_message
                    
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 500 and attempt < max_retries:
                    order_buy_message.append(f"500 에러 발생, 재시도 중...")
                    continue
                else:
                    order_buy_message.append(f"정규매수 주문 오류: {e}")
                    order_info = None
                    return order_info, order_buy_message
                    
            except Exception as e:
                if attempt < max_retries:
                    order_buy_message.append(f"에러 발생, 재시도 중...")
                    continue
                else:
                    order_buy_message.append(f"정규매수 주문 오류: {e}")
                    order_info = None
                    return order_info, order_buy_message
        
        # 모든 재시도 실패
        order_buy_message.append(f"정규매수 주문 최종 실패: 모든 재시도 소진")
        return None, order_buy_message
    
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

##########################################################################################################

    def get_KR_current_price(self, ticker: str) -> Union[float, str]: # 한국주식 현재가 조회 검증완료
        """
        국내 주식 현재가 조회
        Parameters:
            ticker (str): 종목코드 (예: "005930" 삼성전자)
        Returns:
            float: 현재가
            str: 에러 메시지
        """
        if not ticker:
            return "종목코드를 입력해주세요."

        path = "uapi/domestic-stock/v1/quotations/inquire-price"
        url = f"{self.url_base}/{path}"
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "FHKST01010100"
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",  # J: 주식/ETF/ETN
            "FID_INPUT_ISCD": ticker
        }

        try:
            res = requests.get(url, headers=headers, params=params, timeout=5)
            res.raise_for_status()
            data = res.json()

            if data.get("rt_cd") == "0":
                return float(data["output"]["stck_prpr"])  # 주식 현재가
            else:
                return f"현재가 조회 실패: {data.get('msg1', '알 수 없는 오류')}"

        except Exception as e:
            return f"현재가 조회 오류: {e}"
        
    def get_KR_stock_balance(self) -> Optional[List[Dict]]:
        """한국 주식 종목별 잔고 조회"""
        path = "uapi/domestic-stock/v1/trading/inquire-balance"
        url = f"{self.url_base}/{path}"

        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "TTTC8434R",   # 실전투자 / 모의투자: VTTC8434R
            "custtype": "P"          # 개인
        }

        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "AFHR_FLPR_YN": "N",        # 시간외단일가 여부
            "OFL_YN": "",               # 오프라인 여부 (미사용)
            "INQR_DVSN": "00",          # 00: 전체
            "UNPR_DVSN": "01",          # 단가구분 01: 기본값
            "FUND_STTL_ICLD_YN": "N",   # 펀드결제분 포함여부
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",          # 00: 전일매매포함
            "CTX_AREA_FK100": "",       # 연속조회 키 (최초조회 시 공란)
            "CTX_AREA_NK100": ""        # 연속조회 키 (최초조회 시 공란)
        }

        try:
            stocks = []

            while True:
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()

                if data.get('rt_cd') != '0':
                    KA.SendMessage(f"한국주식 잔고조회 API 오류: {data.get('msg1')}")
                    return None

                for stock in data.get('output1', []):
                    quantity = int(stock.get('hldg_qty', 0))
                    if quantity == 0:
                        continue

                    stocks.append({
                        'ticker': stock.get('pdno', ''),           # 종목코드 (6자리)
                        'name': stock.get('prdt_name', ''),        # 종목명
                        'quantity': quantity,                       # 보유수량
                        'avg_price': float(stock.get('pchs_avg_pric', 0)),   # 매입평균가
                        'current_price': float(stock.get('prpr', 0)),        # 현재가
                        'eval_amt': float(stock.get('evlu_amt', 0)),         # 평가금액
                        'profit_loss': float(stock.get('evlu_pfls_amt', 0)), # 평가손익
                        'profit_loss_rate': float(stock.get('evlu_pfls_rt', 0)) # 손익률
                    })

                # 연속조회 처리 (실전: 50종목, 모의: 20종목 초과 시)
                FK100 = data.get('ctx_area_fk100', '').strip()
                NK100 = data.get('ctx_area_nk100', '').strip()

                if FK100 == '' or NK100 == '':
                    break

                params['CTX_AREA_FK100'] = FK100
                params['CTX_AREA_NK100'] = NK100
                time.sleep(0.1)

            return stocks

        except Exception as e:
            KA.SendMessage(f"한국주식 잔고조회 오류: {e}")
            return None
        
    def get_KR_account_summary(self) -> Optional[Dict]:
        """
        한국주식 계좌 원화 자산 요약
        Returns:
            {
                'stock_eval_amt': 한국주식 평가금액 합계 (원),
                'cash_balance':   원화 예수금 잔고 (원),
                'total_krw_asset': 계좌 전체 원화자산 (주식평가금+예수금)
            }
        """
        path = "uapi/domestic-stock/v1/trading/inquire-balance"
        url = f"{self.url_base}/{path}"

        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "TTTC8434R",   # 실전투자 / 모의투자: VTTC8434R
            "custtype": "P"
        }

        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "00",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }

        try:
            self._rate_limit_sleep()
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get('rt_cd') != '0':
                KA.SendMessage(f"계좌요약 API 오류: {data.get('msg1')}")
                return None

            # output2는 연속조회 무관하게 첫 번째 응답에 계좌 전체 합산값 반환
            output2 = data.get('output2', [{}])
            summary = output2[0] if output2 else {}

            stock_eval_amt  = float(summary.get('scts_evlu_amt', 0))   # 주식 평가금액 합계
            cash_balance    = float(summary.get('dnca_tot_amt', 0))     # 예수금 총금액
            total_krw_asset = stock_eval_amt + cash_balance

            return {
                'stock_eval_amt':  stock_eval_amt,
                'cash_balance':    cash_balance,
                'total_krw_asset': total_krw_asset
            }

        except Exception as e:
            KA.SendMessage(f"계좌요약 조회 오류: {e}")
            return None
        
    def get_KR_orderable_cash(self) -> Optional[float]:
        """
        한국주식 매수 가능 원화 예수금 조회
        TR: TTTC8908R (실전) / VTTC8908R (모의)
        Returns:
            float: 주문가능현금 (원) / None: 오류
        """
        path = "uapi/domestic-stock/v1/trading/inquire-psbl-order"
        url = f"{self.url_base}/{path}"

        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "TTTC8908R",   # 실전투자 / 모의투자: VTTC8908R
            "custtype": "P"
        }

        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "PDNO": "005930",       # 조회용 더미 종목코드 (삼성전자) - API 필수값
            "ORD_UNPR": "0",        # 시장가 기준 (0 입력)
            "ORD_DVSN": "01",       # 01: 시장가
            "CMA_EVLU_AMT_ICLD_YN": "N",   # CMA 평가금액 포함여부
            "OVRS_ICLD_YN": "N"    # 해외 포함여부
        }

        try:
            self._rate_limit_sleep()
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get('rt_cd') != '0':
                KA.SendMessage(f"매수가능조회 API 오류: {data.get('msg1')}")
                return None

            return float(data['output'].get('ord_psbl_cash', 0))

        except Exception as e:
            KA.SendMessage(f"매수가능현금 조회 오류: {e}")
            return None