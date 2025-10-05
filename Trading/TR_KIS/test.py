import requests
import json
from datetime import datetime, timedelta
import os
import pandas as pd
import numpy as np
from typing import Union

class KIS_API:
    """한국투자증권 API 클래스"""
    
    # 주요 종목별 거래소 매핑
    EXCHANGE_MAP = {
        # 나스닥
        "AAPL": "NAS", "MSFT": "NAS", "GOOGL": "NAS", "GOOG": "NAS",
        "AMZN": "NAS", "TSLA": "NAS", "META": "NAS", "NVDA": "NAS",
        "NFLX": "NAS", "AMD": "NAS", "INTC": "NAS", "CSCO": "NAS",
        "ADBE": "NAS", "PYPL": "NAS", "QCOM": "NAS", "AVGO": "NAS",
        
        # 뉴욕증권거래소
        "BRK.B": "NYS", "JPM": "NYS", "JNJ": "NYS", "V": "NYS",
        "WMT": "NYS", "PG": "NYS", "MA": "NYS", "DIS": "NYS",
        "BAC": "NYS", "XOM": "NYS", "KO": "NYS", "PFE": "NYS",
        "T": "NYS", "VZ": "NYS", "CVX": "NYS", "NKE": "NYS",
    }
    
    def __init__(self, key_file_path, token_file_path, cano, acnt_prdt_cd):
        """
        Parameters:
        key_file_path (str): API 키 파일 경로
        token_file_path (str): 토큰 저장 파일 경로
        cano (str): 종합계좌번호 (8자리)
        acnt_prdt_cd (str): 계좌상품코드 (2자리)
        """
        self.key_file_path = key_file_path
        self.token_file_path = token_file_path
        self.cano = cano
        self.acnt_prdt_cd = acnt_prdt_cd
        self.url_base = "https://openapi.koreainvestment.com:9443"
        
        # API 키 로드
        self._load_api_keys()
        
        # 토큰 발급/로드
        self.access_token = self.get_access_token()
    
    def _load_api_keys(self):
        """API 키 불러오기"""
        with open(self.key_file_path) as f:
            self.app_key, self.app_secret = [line.strip() for line in f.readlines()]
    
    def load_token(self):
        """저장된 토큰 파일 불러오기"""
        try:
            if os.path.exists(self.token_file_path):
                with open(self.token_file_path, 'r') as f:
                    token_data = json.load(f)
                    return token_data
            else:
                print("✗ 저장된 토큰 파일이 없습니다.")
                return None
        except Exception as e:
            print(f"✗ 토큰 파일 로드 중 오류: {e}")
            return None
    
    def save_token(self, access_token, expires_in=86400):
        """토큰을 JSON 파일로 저장 (기본 유효시간: 24시간 = 86400초)"""
        try:
            token_data = {
                "access_token": access_token,
                "issued_at": datetime.now().isoformat(),
                "expires_in": expires_in
            }
            with open(self.token_file_path, 'w') as f:
                json.dump(token_data, f, indent=2)
            print("✓ 토큰이 파일로 저장되었습니다.")
            return True
        except Exception as e:
            print(f"✗ 토큰 저장 중 오류: {e}")
            return False
    
    def is_token_valid(self, token_data):
        """토큰 유효성 확인 (스케줄 실행 고려하여 800분 안전 마진 적용)"""
        if not token_data or 'access_token' not in token_data:
            return False
        
        try:
            issued_at = datetime.fromisoformat(token_data['issued_at'])
            expires_in = token_data.get('expires_in', 86400)
            
            now = datetime.now()
            expiry_time = issued_at + timedelta(seconds=expires_in)
            safe_expiry_time = expiry_time - timedelta(minutes=800)
            
            is_valid = now < safe_expiry_time
            
            if is_valid:
                remaining = safe_expiry_time - now
                total_seconds = int(remaining.total_seconds())
                
                if total_seconds < 0:
                    print("✗ 토큰이 만료되었습니다.")
                    return False
                    
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                print(f"✓ 토큰이 유효합니다. (남은 시간: {hours}시간 {minutes}분)")
            else:
                print("✗ 토큰이 만료되었습니다.")
            
            return is_valid
        except Exception as e:
            print(f"✗ 토큰 유효성 확인 중 오류: {e}")
            return False
    
    def get_new_token(self):
        """새로운 토큰 발급받기"""
        print("→ 새로운 토큰을 발급받는 중...")
        
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
            
            print("✓ 새로운 토큰 발급 완료!")
            self.save_token(access_token, expires_in)
            
            return access_token
        except Exception as e:
            print(f"✗ 토큰 발급 실패: {e}")
            return None
    
    def get_access_token(self):
        """
        토큰 가져오기 (자동으로 저장/로드/갱신 처리)
        1. 저장된 토큰 확인
        2. 유효성 검사
        3. 필요시 새로 발급
        """
        print("\n=== 토큰 확인 중 ===")
        
        token_data = self.load_token()
        
        if token_data and self.is_token_valid(token_data):
            print("✓ 기존 토큰을 사용합니다.\n")
            return token_data['access_token']
        
        print("→ 토큰을 새로 발급받습니다.")
        access_token = self.get_new_token()
        print()
        return access_token
    
    def hashkey(self, datas):
        """주문 등에 쓰이는 hashkey 생성"""
        path = "uapi/hashkey"
        url = f"{self.url_base}/{path}"
        headers = {
            'content-Type': 'application/json',
            'appKey': self.app_key,
            'appSecret': self.app_secret,
        }
        res = requests.post(url, headers=headers, data=json.dumps(datas))
        hashkey = res.json()["HASH"]
        return hashkey
    
    def get_US_exchange(self, ticker: str) -> Union[str, None]:
        """
        미국 주식 티커의 거래소 코드를 자동으로 찾습니다.
        
        Parameters:
        ticker (str): 주식 티커 심볼 (예: AAPL, TSLA)
        
        Returns:
        str: 거래소 코드 ("NAS", "NYS", "AMS") 또는 None
        
        Example:
        >>> exchange = api.get_US_exchange("AAPL")
        >>> print(exchange)  # "NAS"
        """
        if not ticker:
            return None
        
        ticker = ticker.upper()
        
        # 1. 사전에 매핑된 종목인지 확인
        if ticker in self.EXCHANGE_MAP:
            return self.EXCHANGE_MAP[ticker]
        
        # 2. 나스닥에서 시도
        path = "/uapi/overseas-price/v1/quotations/price"
        url = f"{self.url_base}{path}"
        
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "HHDFS00000300"
        }
        
        params = {
            "AUTH": "",
            "EXCD": "NAS",
            "SYMB": ticker
        }
        
        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                data = response.json()
                if data.get('rt_cd') == '0':
                    return "NAS"
        except:
            pass
        
        # 3. 뉴욕증권거래소에서 시도
        params["EXCD"] = "NYS"
        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                data = response.json()
                if data.get('rt_cd') == '0':
                    return "NYS"
        except:
            pass
        
        # 4. 아멕스에서 시도
        params["EXCD"] = "AMS"
        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                data = response.json()
                if data.get('rt_cd') == '0':
                    return "AMS"
        except:
            pass
        
        return None
    
    def get_US_current_price(self, ticker: str) -> Union[float, str]:
        """
        미국 주식의 현재가를 조회합니다.
        
        Parameters:
        ticker (str): 주식 티커 심볼 (예: AAPL, TSLA)
        
        Returns:
        float: 현재가 (성공 시)
        str: 에러 메시지 (실패 시)
        
        Example:
        >>> price = api.get_US_current_price("AAPL")
        >>> if isinstance(price, float):
        >>>     print(f"현재가: ${price}")
        >>> else:
        >>>     print(f"오류: {price}")
        """
        if not ticker:
            return "티커를 입력해주세요."
        
        ticker = ticker.upper()
        
        # 거래소 자동 검색
        exchange = self.get_US_exchange(ticker)
        if exchange is None:
            return f"{ticker}의 거래소를 찾을 수 없습니다."
        
        path = "/uapi/overseas-price/v1/quotations/price"
        url = f"{self.url_base}{path}"
        
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
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('rt_cd') != '0':
                return f"조회 실패: {data.get('msg1', '알 수 없는 오류')}"
            
            output = data.get('output')
            if output and 'last' in output:
                return float(output['last'])
            else:
                return "현재가 데이터가 없습니다."
                
        except Exception as e:
            return f"오류 발생: {str(e)}"
    
    def order_buy_US(self, ticker, quantity, price, exchange=None, ord_dvsn="00"):
        """
        미국 주식 지정가 매수 주문
        
        Parameters:
        ticker (str): 종목코드 (예: AAPL, TSLA)
        quantity (int): 주문수량
        price (float): 주문단가 (달러)
        exchange (str): 거래소 코드 (None이면 자동 검색)
        ord_dvsn (str): 주문구분
            - 00: 지정가
            - 32: LOO(장개시지정가)
            - 34: LOC(장마감지정가)
            - 35: TWAP (시간가중평균)
            - 36: VWAP (거래량가중평균)
        
        Returns:
        requests.Response: API 응답 객체
        """
        if exchange is None:
            exchange = self.get_US_exchange(ticker)
        
        if exchange is None:
            print(f"{ticker}의 거래소를 찾을 수 없어 주문을 실행할 수 없습니다.")
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

        res = requests.post(url, headers=headers, data=json.dumps(data))
        return res
    
    def order_sell_US(self, ticker, quantity, price, exchange=None, ord_dvsn="00"):
        """
        미국 주식 지정가 매도 주문
        
        Parameters:
        ticker (str): 종목코드 (예: AAPL, TSLA)
        quantity (int): 주문수량
        price (float): 주문단가 (달러)
        exchange (str): 거래소 코드 (None이면 자동 검색)
        ord_dvsn (str): 주문구분
            - 00: 지정가
            - 31: MOO(장개시시장가)
            - 32: LOO(장개시지정가)
            - 33: MOC(장마감시장가)
            - 34: LOC(장마감지정가)
            - 35: TWAP (시간가중평균)
            - 36: VWAP (거래량가중평균)
        
        Returns:
        requests.Response: API 응답 객체
        """
        if exchange is None:
            exchange = self.get_US_exchange(ticker)
        
        if exchange is None:
            print(f"{ticker}의 거래소를 찾을 수 없어 주문을 실행할 수 없습니다.")
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

        res = requests.post(url, headers=headers, data=json.dumps(data))
        return res
    
    def get_US_stock_balance(self):
        """
        미국 주식 종목별 잔고만 조회
        
        Returns:
        list: 종목별 보유 내역 리스트
        """
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
                print(f"✗ 종목 잔고 조회 실패: {data.get('msg1', '알 수 없는 오류')}")
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
            
        except Exception as e:
            print(f"✗ 종목 잔고 조회 중 오류: {e}")
            return None
    
    def get_US_dollar_balance(self):
        """
        미국 달러 예수금만 조회
        
        Returns:
        dict: USD 잔고 정보
        """
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
                print(f"✗ USD 잔고 조회 실패: {data.get('msg1', '알 수 없는 오류')}")
                return None
            
            output2 = data.get('output2', [])
            if not output2:
                print("✗ USD 정보를 찾을 수 없습니다.")
                return None
            
            usd_info = output2[0]
            
            result = {
                'currency': usd_info.get('crcy_cd', 'USD'),
                'deposit': float(usd_info.get('frcr_dncl_amt_2', 0)),
                'withdrawable': float(usd_info.get('frcr_drwg_psbl_amt_1', 0)),
                'exchange_rate': float(usd_info.get('frst_bltn_exrt', 0)),
                'krw_value': float(usd_info.get('frcr_evlu_amt2', 0))
            }
            
            return result
            
        except Exception as e:
            print(f"✗ USD 잔고 조회 중 오류: {e}")
            return None
    
    def get_total_balance(self):
        """
        전체 계좌 잔고 조회 (주식 + USD 예수금)
        달러 표시와 원화 환산 모두 제공
        
        Returns:
        dict: 전체 계좌 정보
        """
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
                print(f"✗ 전체 잔고 조회 실패: {data.get('msg1', '알 수 없는 오류')}")
                return None
            
            # 종목 정보 (output1)
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
            
            # USD 정보 (output2)
            output2 = data.get('output2', [])
            usd_deposit = 0
            exchange_rate = 0
            if output2:
                usd_info = output2[0]
                usd_deposit = float(usd_info.get('frcr_dncl_amt_2', 0))
                exchange_rate = float(usd_info.get('frst_bltn_exrt', 0))
            
            # 계좌 전체 정보 (output3)
            output3 = data.get('output3', {})
            
            stock_eval_usd = float(output3.get('evlu_amt_smtl', 0))
            stock_eval_krw = float(output3.get('evlu_amt_smtl_amt', 0))
            
            total_usd = stock_eval_usd + usd_deposit
            total_krw = float(output3.get('tot_asst_amt', 0))
            
            total_profit_loss_usd = float(output3.get('evlu_pfls_amt_smtl', 0))
            total_profit_loss_krw = float(output3.get('tot_evlu_pfls_amt', 0))
            profit_rate = float(output3.get('evlu_erng_rt1', 0))
            
            result = {
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
            
            return result
            
        except Exception as e:
            print(f"✗ 전체 잔고 조회 중 오류: {e}")
            return None


# 사용 예시
if __name__ == "__main__":
    # API 인스턴스 생성
    api = KIS_API(
        key_file_path="C:/Users/ilpus/Desktop/NKL_invest/kis63721147nkr.txt",
        token_file_path="C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/kis63721147_token.json",
        cano="63721147",
        acnt_prdt_cd="01"
    )
    
    # 1. 거래소 조회 테스트
    print("\n=== 거래소 조회 테스트 ===")
    tickers = ["AAPL", "TSLA", "JPM", "NVDA", "KO"]
    for ticker in tickers:
        exchange = api.get_US_exchange(ticker)
        print(f"{ticker}: {exchange}")
    
    # 2. 현재가 조회 테스트
    print("\n=== 현재가 조회 테스트 ===")
    for ticker in tickers:
        price = api.get_US_current_price(ticker)
        if isinstance(price, float):
            print(f"{ticker}: ${price:,.2f}")
        else:
            print(f"{ticker}: {price}")