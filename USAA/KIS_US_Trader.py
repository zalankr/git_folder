import requests
import json

class KISAutoTrading:
    def __init__(self):
        self.base_url = "https://openapi.koreainvestment.com:9443"
        self.api_key = None
        self.api_secret = None
        self.access_token = None
    
    def load_keys(self, file_path="api_keys.txt"):
        """API key와 secret 불러오기"""
        try:
            with open(file_path, 'r') as f:
                lines = f.readlines()
                if len(lines) < 2:
                    raise ValueError("파일에 API key와 secret이 모두 필요합니다")
                self.api_key = lines[0].strip()
                self.api_secret = lines[1].strip()
            print("API 키 불러오기 완료")
        except FileNotFoundError:
            print(f"파일을 찾을 수 없습니다: {file_path}")
            raise
        except Exception as e:
            print(f"API 키 불러오기 실패: {e}")
            raise
    
    def get_token(self):
        """접근 토큰 발급"""
        try:
            url = f"{self.base_url}/oauth2/tokenP"
            
            data = {
                "grant_type": "client_credentials",
                "appkey": self.api_key,
                "appsecret": self.api_secret
            }
            
            response = requests.post(url, json=data)
            response.raise_for_status()  # HTTP 오류 발생시 예외 처리
            
            result = response.json()
            
            if "access_token" not in result:
                raise ValueError("응답에 access_token이 없습니다")
            
            self.access_token = result["access_token"]
            print("토큰 발급 완료")
            
        except requests.exceptions.RequestException as e:
            print(f"토큰 발급 요청 실패: {e}")
            raise
        except ValueError as e:
            print(f"토큰 발급 응답 오류: {e}")
            raise
        except Exception as e:
            print(f"토큰 발급 중 예상치 못한 오류: {e}")
            raise
    
    def get_us_balance(self, account_no, account_code="01"):
        """미국주식 잔고 조회"""
        try:
            if not self.access_token:
                raise ValueError("접근 토큰이 없습니다. get_token()을 먼저 실행하세요")
                
            url = f"{self.base_url}/uapi/overseas-stock/v1/trading/inquire-balance"
            
            headers = {
                "content-type": "application/json",
                "authorization": f"Bearer {self.access_token}",
                "appkey": self.api_key,
                "appsecret": self.api_secret,
                "tr_id": "TTTS3012R",
                "custtype": "P"
            }
            
            params = {
                "CANO": account_no,           # 계좌번호
                "ACNT_PRDT_CD": account_code, # 계좌상품코드
                "OVRS_EXCG_CD": "NASD",      # 해외거래소코드 (NASD: 나스닥)
                "TR_CRCY_CD": "USD",         # 거래통화코드
                "CTX_AREA_FK200": "",        # 연속조회검색조건200
                "CTX_AREA_NK200": ""         # 연속조회키200
            }
            
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()  # HTTP 오류 발생시 예외 처리
            
            result = response.json()
            
            if result["rt_cd"] != "0":
                raise ValueError(f"API 오류: {result.get('msg1', '알 수 없는 오류')}")
            
            # 달러 잔고
            dollar_balance = 0
            if result.get("output2"):
                for item in result["output2"]:
                    if item.get("crcy_cd") == "USD":
                        dollar_balance = float(item.get("frcr_dncl_amt_2", 0))
            
            # 보유 주식 리스트
            stocks = []
            if result.get("output1"):
                for stock in result["output1"]:
                    stock_info = {
                        "종목코드": stock.get("ovrs_pdno", ""),
                        "종목명": stock.get("ovrs_item_name", ""),
                        "보유수량": int(stock.get("ovrs_cblc_qty", 0)),
                        "평균단가": float(stock.get("pchs_avg_pric", 0)),
                        "현재가": float(stock.get("now_pric2", 0)),
                        "평가금액": float(stock.get("ovrs_stck_evlu_amt", 0)),
                        "손익금액": float(stock.get("evlu_pfls_amt", 0)),
                        "손익률": float(stock.get("evlu_pfls_rt", 0))
                    }
                    stocks.append(stock_info)
            
            return {
                "달러잔고": dollar_balance,
                "보유주식": stocks
            }
            
        except requests.exceptions.RequestException as e:
            print(f"잔고 조회 요청 실패: {e}")
            return None
        except ValueError as e:
            print(f"잔고 조회 오류: {e}")
            return None
        except KeyError as e:
            print(f"응답 데이터 파싱 오류: {e}")
            return None
        except Exception as e:
            print(f"잔고 조회 중 예상치 못한 오류: {e}")
            return None


# 사용 예시
if __name__ == "__main__":
    try:
        # 1. 인스턴스 생성 및 키 불러오기
        trader = KISAutoTrading()
        file_path = "api_keys.txt"
        trader.load_keys(file_path="api_keys.txt")
        
        # 2. 토큰 발급
        trader.get_token()
        
        # 3. 미국주식 잔고 조회 (계좌번호 입력 필요)
        account_number = "12345678-01"  # 실제 계좌번호로 변경하세요
        
        balance = trader.get_us_balance(account_number)
        if balance:
            print(f"\n달러 잔고: ${balance['달러잔고']:,.2f}")
            print("\n보유 미국 주식:")
            print("-" * 80)
            for stock in balance['보유주식']:
                print(f"종목: {stock['종목명']} ({stock['종목코드']})")
                print(f"보유량: {stock['보유수량']}주, 평균단가: ${stock['평균단가']:.2f}")
                print(f"현재가: ${stock['현재가']:.2f}, 평가금액: ${stock['평가금액']:,.2f}")
                print(f"손익: ${stock['손익금액']:,.2f} ({stock['손익률']:.2f}%)")
                print("-" * 80)
        else:
            print("잔고 조회에 실패했습니다.")
            
    except Exception as e:
        print(f"프로그램 실행 중 오류 발생: {e}")