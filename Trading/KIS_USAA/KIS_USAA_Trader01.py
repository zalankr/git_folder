import requests
import json
import keyring

# key 불러오기
app_key = keyring.get_password('kis63692011_key', 'nkr')
app_secret = keyring.get_password('kis63692011_secret', 'nkr')

## 토큰 발급받기
# base url
url_base = "https://openapi.koreainvestment.com:9443"

# information
headers = {"content-type": "application/json"}
path = "oauth2/tokenP"
body = {
    "grant_type": "client_credentials",
    "appkey": app_key,
    "appsecret": app_secret
}

url = f"{url_base}/{path}"

#토큰 발급요청
token = requests.post(url, headers=headers, data=json.dumps(body))
access_token = token.json()['access_token']

# 계좌 정보 (예시)
CANO = "63692011"  # 종합계좌번호 (8자리)
ACNT_PRDT_CD = "01"  # 계좌상품코드 (2자리)

# 주문 등에 쓰이는 hashkey 함수 만들기
def hashkey(datas):
    path = "uapi/hashkey"
    url = f"{url_base}/{path}"
    headers = {
        'content-Type': 'application/json',
        'appKey': app_key,
        'appSecret': app_secret,
    }
    res = requests.post(url, headers=headers, data=json.dumps(datas))
    hashkey = res.json()["HASH"]

    return hashkey

# 미국주식 현재가 조회
def current_price_US(ticker, exchange="NAS"):
    """
    미국 주식 현재가 조회
    
    Parameters:
    ticker (str): 종목코드 (예: AAPL, TSLA)
    exchange (str): 거래소 코드
        - NASD: 미국전체 유료시세
        - NAS: 나스닥 무료시세
        - NYS: 뉴욕
        - AMS: 아멕스
    
    Returns:
    requests.Response: API 응답 객체
    """
    path = "uapi/overseas-price/v1/quotations/price"
    url = f"{url_base}/{path}"

    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {access_token}",
        "appKey": app_key,
        "appSecret": app_secret,
        "tr_id": "HHDFS00000300"  # 해외주식 현재가 체결가 조회 tr_id
    }

    params = {
        "AUTH": "",
        "EXCD": exchange,  # 거래소 코드 NAS 나스닥 무료시세
        "SYMB": ticker     # 종목코드
    }

    search = requests.get(url, headers=headers, params=params)
    return search

def get_US_exchange(ticker): # 미국주식 종목코드로 거래소 코드 찾기
    """
    미국 주식 종목코드로 거래소 코드를 자동으로 찾아주는 함수
    
    Parameters:
    ticker (str): 종목코드 (예: AAPL, TSLA)
    
    Returns:
    str: 거래소 코드 (NASD, NYSE, AMEX) 또는 None
    """
    exchanges = ["NASD", "NYSE", "AMEX"]
    
    for exchange in exchanges:
        try:
            path = "uapi/overseas-price/v1/quotations/price"
            url = f"{url_base}/{path}"

            headers = {
                "Content-Type": "application/json",
                "authorization": f"Bearer {access_token}",
                "appKey": app_key,
                "appSecret": app_secret,
                "tr_id": "HHDFS00000300"
            }

            params = {
                "AUTH": "",
                "EXCD": exchange,
                "SYMB": ticker
            }

            response = requests.get(url, headers=headers, params=params)
            
            # 응답 성공 여부 확인
            if response.status_code == 200:
                data = response.json()
                # 정상 응답이고 데이터가 있으면 해당 거래소 반환
                if data.get('rt_cd') == '0' and data.get('output'):
                    print(f"✓ {ticker}는 {exchange}에서 거래됩니다.")
                    return exchange
                    
        except Exception as e:
            continue
    
    print(f"✗ {ticker}의 거래소를 찾을 수 없습니다.")
    return None


# TTTT1002U : 미국 매수 주문 "tr_id"

# 00 : 지정가
# 32 : LOO(장개시지정가)
# 34 : LOC(장마감지정가)
# 35 : TWAP (시간가중평균)
# 36 : VWAP (거래량가중평균)
# * TWAP, VWAP 주문은 분할시간 주문 입력 필수

# TTTT1006U : 미국 매도 주문 "tr_id"
# 00 : 지정가
# 31 : MOO(장개시시장가)
# 32 : LOO(장개시지정가)
# 33 : MOC(장마감시장가)
# 34 : LOC(장마감지정가)
# 35 : TWAP (시간가중평균)
# 36 : VWAP (거래량가중평균)
# * TWAP, VWAP 주문은 분할시간 주문 입력 필수

# 미국주식 # 지정가 # 매수 주문
def order_buy_US(ticker, quantity, price, exchange="NASD", ORD_DVSN="00"): # ORD_DVSN 주문구분 함수 넣기
    """
    미국 주식 지정가 매수 주문
    
    Parameters:
    ticker (str): 종목코드 (예: AAPL, TSLA)
    quantity (int): 주문수량
    price (float): 주문단가 (달러)
    exchange (str): 거래소 코드
   
    Returns:
    requests.Response: API 응답 객체
    """
    # 거래소 코드 찾기
    exchange = get_US_exchange(ticker)
    
    if exchange is None:
        print(f"{ticker}의 거래소를 찾을 수 없어 주문을 실행할 수 없습니다.")
        return None
    
    path = "uapi/overseas-stock/v1/trading/order"
    url = f"{url_base}/{path}"

    # 주문 데이터
    data = {
        "CANO": CANO,                    # 종합계좌번호 #
        "ACNT_PRDT_CD": ACNT_PRDT_CD,    # 계좌상품코드 #
        "OVRS_EXCG_CD": exchange,        # 해외거래소코드 #
        "PDNO": ticker,                  # 상품번호(종목코드) #
        "ORD_DVSN": ORD_DVSN,            # 주문구분 (00: 지정가)
        "ORD_QTY": str(quantity),        # 주문수량
        "OVRS_ORD_UNPR": str(price),     # 해외주문단가
        "ORD_SVR_DVSN_CD": "0"           # 주문서버구분코드 (0: 해외)
    }

    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {access_token}",
        "appKey": app_key,
        "appSecret": app_secret,
        "tr_id": "TTTT1002U",            # 해외주식 매수주문 (실전투자)
        "custtype": "P",                 # 고객타입 (P: 개인)
        "hashkey": hashkey(data)         # 해시키
    }

    res = requests.post(url, headers=headers, data=json.dumps(data))
    return res


# 미국주식 지정가 매도 주문
def order_sell_US(ticker, quantity, price, exchange="NASD", ORD_DVSN="00"): # ORD_DVSN 주문구분 함수 넣기):
    """
    미국 주식 지정가 매도 주문
    
    Parameters:
    ticker (str): 종목코드 (예: AAPL, TSLA)
    quantity (int): 주문수량
    price (float): 주문단가 (달러)
    exchange (str): 거래소 코드
    
    Returns:
    requests.Response: API 응답 객체
    """
    path = "uapi/overseas-stock/v1/trading/order"
    url = f"{url_base}/{path}"

    # 주문 데이터
    data = {
        "CANO": CANO,                    # 종합계좌번호
        "ACNT_PRDT_CD": ACNT_PRDT_CD,    # 계좌상품코드
        "OVRS_EXCG_CD": exchange,        # 해외거래소코드
        "PDNO": ticker,                  # 상품번호(종목코드)
        "ORD_DVSN": ORD_DVSN,            # 주문구분 (00: 지정가)
        "ORD_QTY": str(quantity),        # 주문수량
        "OVRS_ORD_UNPR": str(price),     # 해외주문단가
        "ORD_SVR_DVSN_CD": "0"           # 주문서버구분코드 (0: 해외)
    }

    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {access_token}",
        "appKey": app_key,
        "appSecret": app_secret,
        "tr_id": "TTTT1006U",            # 해외주식 매도주문 (실전투자)
        "custtype": "P",                 # 고객타입 (P: 개인)
        "hashkey": hashkey(data)         # 해시키
    }

    res = requests.post(url, headers=headers, data=json.dumps(data))
    return res


# 사용 예시
print("애플 현재가:", current_price_US("AAPL", "NAS").json()['output']['last'])

# 사용 예시
print("\n=== 거래소 찾기 테스트 ===")
aapl_exchange = get_US_exchange("AAPL")
print(f"AAPL 거래소: {aapl_exchange}\n")

tsla_exchange = get_US_exchange("TSLA")
print(f"TSLA 거래소: {tsla_exchange}\n")

koru_exchange = get_US_exchange("KORU")
print(f"KORU 거래소: {koru_exchange}\n")

# 주문 시 자동으로 거래소 찾아서 사용
ticker = "AAPL"
exchange = get_US_exchange(ticker)
if exchange:
    # result = order_buy_US(ticker, 1, 150.50, exchange)
    print(f"{ticker} 매수 주문 준비 완료 (거래소: {exchange})")

# 매수 주문 예시 (실제 주문 시 주석 해제)
# result = order_buy_US("AAPL", 1, 150.50, "NASD")
# print("매수 주문 결과:", result.json())

# 매도 주문 예시 (실제 주문 시 주석 해제)
# result = order_sell_US("AAPL", 1, 160.00, "NASD")
# print("매도 주문 결과:", result.json())