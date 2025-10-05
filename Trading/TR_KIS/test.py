import requests
import json
from datetime import datetime, timedelta
import os
from typing import Union, Optional

class BIL_OpenPrice:
    """BIL 시가 조회 클래스 (KIS API + yfinance 백업)"""
    
    def __init__(self, key_file_path: str, token_file_path: str):
        self.key_file_path = key_file_path
        self.token_file_path = token_file_path
        self.url_base = "https://openapi.koreainvestment.com:9443"
        
        self._load_api_keys()
        self.access_token = self.get_access_token()
    
    def _load_api_keys(self):
        with open(self.key_file_path) as f:
            self.app_key, self.app_secret = [line.strip() for line in f.readlines()]
    
    def load_token(self):
        try:
            if os.path.exists(self.token_file_path):
                with open(self.token_file_path, 'r') as f:
                    return json.load(f)
            return None
        except:
            return None
    
    def save_token(self, access_token: str, expires_in: int = 86400):
        try:
            token_data = {
                "access_token": access_token,
                "issued_at": datetime.now().isoformat(),
                "expires_in": expires_in
            }
            with open(self.token_file_path, 'w') as f:
                json.dump(token_data, f, indent=2)
            return True
        except:
            return False
    
    def is_token_valid(self, token_data):
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
    
    def get_new_token(self):
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
    
    def get_access_token(self):
        token_data = self.load_token()
        
        if token_data and self.is_token_valid(token_data):
            return token_data['access_token']
        
        return self.get_new_token()
    
    def get_open_price_from_kis(self, ticker: str, exchange: str = "NYS") -> Union[float, str]:
        """
        KIS API로 시가 조회 (기간별시세 API 사용)
        
        Parameters:
        ticker (str): 종목 코드 (예: BIL)
        exchange (str): 거래소 코드 (NYS: 뉴욕, NAS: 나스닥)
        
        Returns:
        float: 시가
        str: 에러 메시지
        """
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
            "GUBN": "0",  # 0: 일봉, 1: 주봉, 2: 월봉
            "BYMD": "",   # 공란: 오늘 날짜
            "MODP": "0"   # 0: 수정주가 미반영
        }
        
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get('rt_cd') == '0':
                output2 = data.get('output2', [])
                
                if output2 and len(output2) > 0:
                    latest = output2[0]  # 최근 데이터
                    
                    # 시가(open) 확인
                    open_price = latest.get('open', '').strip()
                    if open_price and open_price != '0':
                        try:
                            price = float(open_price)
                            if price > 0:
                                print(f"✓ {ticker} 시가: ${price} (KIS API)")
                                return price
                        except (ValueError, TypeError):
                            pass
            
            return "KIS API에서 시가를 찾을 수 없습니다."
        
        except Exception as e:
            return f"KIS API 오류: {str(e)}"
    
    def get_open_price_from_yfinance(self, ticker: str) -> Union[float, str]:
        """
        yfinance로 시가 조회
        
        Parameters:
        ticker (str): 종목 코드 (예: BIL)
        
        Returns:
        float: 시가
        str: 에러 메시지
        """
        try:
            import yfinance as yf
            
            stock = yf.Ticker(ticker)
            
            # 최근 1일 데이터 조회
            hist = stock.history(period='1d')
            
            if not hist.empty and 'Open' in hist.columns:
                open_price = float(hist['Open'].iloc[-1])
                if open_price > 0:
                    print(f"✓ {ticker} 시가: ${open_price:.2f} (yfinance)")
                    return open_price
            
            # 실패시 2일 데이터로 재시도
            hist = stock.history(period='2d')
            if not hist.empty and 'Open' in hist.columns:
                open_price = float(hist['Open'].iloc[-1])
                if open_price > 0:
                    print(f"✓ {ticker} 시가: ${open_price:.2f} (yfinance)")
                    return open_price
            
            return "yfinance에서 시가를 찾을 수 없습니다."
        
        except ImportError:
            return "yfinance 미설치 (pip install yfinance)"
        except Exception as e:
            return f"yfinance 오류: {str(e)}"
    
    def get_open_price(self, ticker: str, exchange: str = "NYS") -> Union[float, str]:
        """
        시가 조회 (KIS API → yfinance 자동 백업)
        
        Parameters:
        ticker (str): 종목 코드 (예: BIL)
        exchange (str): 거래소 코드 (NYS: 뉴욕, NAS: 나스닥)
        
        Returns:
        float: 시가
        str: 에러 메시지
        """
        # 1단계: KIS API 시도
        print(f"\n[{ticker}] 시가 조회 중...")
        result = self.get_open_price_from_kis(ticker, exchange)
        
        if isinstance(result, float):
            return result
        
        # 2단계: yfinance 백업
        print(f"KIS API 실패, yfinance로 재시도...")
        result = self.get_open_price_from_yfinance(ticker)
        
        if isinstance(result, float):
            return result
        
        print(f"✗ {ticker} 시가 조회 실패: {result}")
        return result


# 사용 예시
if __name__ == "__main__":
    # API 인스턴스 생성
    api = BIL_OpenPrice(
        key_file_path="C:/Users/ilpus/Desktop/NKL_invest/kis63721147nkr.txt",
        token_file_path="C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/kis63721147_token.json"
    )
    
    # BIL 시가 조회
    print("="*60)
    open_price = api.get_open_price("BIL", exchange="NYS")
    
    if isinstance(open_price, float):
        print(f"\n최종 결과: BIL 시가 = ${open_price:.2f}")
    else:
        print(f"\n최종 결과: {open_price}")
    
    print("="*60)
    
    # 다른 종목들도 테스트
    print("\n\n=== 추가 테스트 ===")
    test_tickers = [
        ("AAPL", "NAS"),
        ("TSLA", "NAS"),
        ("UPRO", "NAS"),
    ]
    
    for ticker, exch in test_tickers:
        open_price = api.get_open_price(ticker, exchange=exch)
        if isinstance(open_price, float):
            print(f"{ticker}: ${open_price:.2f}")