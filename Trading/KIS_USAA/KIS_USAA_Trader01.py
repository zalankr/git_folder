import requests
import json
import keyring
from datetime import datetime, timedelta
import os
import pandas as pd
import numpy as np

# API 키 불러오기
with open("C:/Users/ilpus/Desktop/git_folder/Trading/kis63692011nkr.txt") as f:
# with open("C:/Users/GSR/Desktop/Code/kis63692011nkr.txt") as f:
    app_key, app_secret = [line.strip() for line in f.readlines()]

# 토큰 저장 파일 경로
TOKEN_FILE = "C:/Users/ilpus/Desktop/git_folder/Trading/KIS_USAA/kis63692011_token.json"
# TOKEN_FILE = "C:/Users/GSR/Desktop/Code/git_folder/Trading/KIS_USAA/kis63692011_token.json"

# base url
url_base = "https://openapi.koreainvestment.com:9443"

def load_token():
    """저장된 토큰 파일 불러오기"""
    try:
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'r') as f:
                token_data = json.load(f)
                print("✓ 저장된 토큰 파일을 찾았습니다.")
                return token_data
        else:
            print("✗ 저장된 토큰 파일이 없습니다.")
            return None
    except Exception as e:
        print(f"✗ 토큰 파일 로드 중 오류: {e}")
        return None

def save_token(access_token, expires_in=86400):
    """토큰을 JSON 파일로 저장 (기본 유효시간: 24시간 = 86400초)"""
    try:
        token_data = {
            "access_token": access_token,
            "issued_at": datetime.now().isoformat(),
            "expires_in": expires_in
        }
        with open(TOKEN_FILE, 'w') as f:
            json.dump(token_data, f, indent=2)
        print("✓ 토큰이 파일로 저장되었습니다.")
        return True
    except Exception as e:
        print(f"✗ 토큰 저장 중 오류: {e}")
        return False

def is_token_valid(token_data):
    """토큰 유효성 확인 (스케줄 실행 고려하여 800분 안전 마진 적용)"""
    if not token_data or 'access_token' not in token_data:
        return False
    
    try:
        issued_at = datetime.fromisoformat(token_data['issued_at'])
        expires_in = token_data.get('expires_in', 86400)
        
        # 현재 시간과 발급 시간 비교
        now = datetime.now()
        expiry_time = issued_at + timedelta(seconds=expires_in)
        
        # 만료 800분 전까지를 유효한 것으로 간주 (12시간 스케줄 실행 대비)
        safe_expiry_time = expiry_time - timedelta(minutes=800)
        
        is_valid = now < safe_expiry_time
        
        if is_valid:
            remaining = safe_expiry_time - now
            # total_seconds()를 사용하여 전체 시간 계산 (일 포함)
            total_seconds = int(remaining.total_seconds())
            
            # total_seconds가 음수인 경우 처리
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

def get_new_token():
    """새로운 토큰 발급받기"""
    print("→ 새로운 토큰을 발급받는 중...")
    
    headers = {"content-type": "application/json"}
    path = "oauth2/tokenP"
    body = {
        "grant_type": "client_credentials",
        "appkey": app_key,
        "appsecret": app_secret
    }
    
    url = f"{url_base}/{path}"
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(body))
        response.raise_for_status()
        
        token_response = response.json()
        access_token = token_response['access_token']
        expires_in = token_response.get('expires_in', 86400)
        
        print("✓ 새로운 토큰 발급 완료!")
        
        # 토큰 저장
        save_token(access_token, expires_in)
        
        return access_token
    except Exception as e:
        print(f"✗ 토큰 발급 실패: {e}")
        return None

def get_access_token():
    """
    토큰 가져오기 (자동으로 저장/로드/갱신 처리)
    1. 저장된 토큰 확인
    2. 유효성 검사
    3. 필요시 새로 발급
    """
    print("\n=== 토큰 확인 중 ===")
    
    # 1. 저장된 토큰 로드
    token_data = load_token()
    
    # 2. 토큰 유효성 확인
    if token_data and is_token_valid(token_data):
        print("✓ 기존 토큰을 사용합니다.\n")
        return token_data['access_token']
    
    # 3. 유효하지 않으면 새로 발급
    print("→ 토큰을 새로 발급받습니다.")
    access_token = get_new_token()
    print()
    return access_token

## 토큰 발급/로드
access_token = get_access_token()

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

# 미국 주식 종목별 잔고 조회
def get_US_stock_balance():
    """
    미국 주식 종목별 잔고 조회
    
    Returns:
    dict: {
        'stocks': [종목별 보유 내역],
        'total_eval': 총 평가금액(원화),
        'total_eval_usd': 총 평가금액(달러)
    }
    """
    path = "uapi/overseas-stock/v1/trading/inquire-balance"
    url = f"{url_base}/{path}"
    
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {access_token}",
        "appKey": app_key,
        "appSecret": app_secret,
        "tr_id": "TTTS3012R"  # 해외주식 잔고조회 (실전투자)
    }
    
    params = {
        "CANO": CANO,
        "ACNT_PRDT_CD": ACNT_PRDT_CD,
        "OVRS_EXCG_CD": "NASD",  # 미국 전체 조회
        "TR_CRCY_CD": "USD",      # 거래통화코드 (USD)
        "CTX_AREA_FK200": "",
        "CTX_AREA_NK200": ""
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('rt_cd') != '0':
            print(f"✗ 잔고 조회 실패: {data.get('msg1', '알 수 없는 오류')}")
            return None
        
        stocks = data.get('output1', [])
        summary = data.get('output2', {})
        
        result = {
            'stocks': [],
            'total_eval': float(summary.get('tot_evlu_pfls_amt', 0)),  # 총 평가손익금액(원화)
            'total_eval_usd': float(summary.get('ovrs_tot_pfls', 0))   # 해외 총 손익(달러)
        }
        
        for stock in stocks:
            stock_info = {
                'ticker': stock.get('ovrs_pdno', ''),           # 종목코드
                'name': stock.get('ovrs_item_name', ''),        # 종목명
                'quantity': int(stock.get('ovrs_cblc_qty', 0)), # 보유수량
                'avg_price': float(stock.get('pchs_avg_pric', 0)),   # 매입평균가격
                'current_price': float(stock.get('now_pric2', 0)),   # 현재가
                'eval_amt': float(stock.get('ovrs_stck_evlu_amt', 0)),  # 평가금액(달러)
                'profit_loss': float(stock.get('frcr_evlu_pfls_amt', 0)),  # 평가손익(달러)
                'profit_loss_rate': float(stock.get('evlu_pfls_rt', 0))    # 평가손익율(%)
            }
            result['stocks'].append(stock_info)
        
        return result
        
    except Exception as e:
        print(f"✗ 잔고 조회 중 오류: {e}")
        return None

# 미국 달러화 예수금 잔고 조회
def get_US_dollar_balance():
    """
    미국 달러화 예수금 잔고 조회
    
    Returns:
    dict: {
        'available_usd': 출금가능 달러,
        'deposit_usd': 예수금 총액,
        'order_possible_usd': 주문가능 금액
    }
    
    Note: 
    - 해외주식 예수금/주문가능금액 조회 (CTRP6504R) 사용
    """
    path = "uapi/overseas-stock/v1/trading/inquire-present-balance"
    url = f"{url_base}/{path}"
    
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {access_token}",
        "appKey": app_key,
        "appSecret": app_secret,
        "tr_id": "CTRP6504R"  # 해외주식 예수금/주문가능금액 조회
    }
    
    params = {
        "CANO": CANO,
        "ACNT_PRDT_CD": ACNT_PRDT_CD,
        "WCRC_FRCR_DVSN_CD": "02",  # 외화구분코드 (01: 원화, 02: 외화)
        "NATN_CD": "840",           # 국가코드 (840: 미국)
        "TR_MKET_CD": "00",         # 거래시장코드 (00: 전체)
        "INQR_DVSN_CD": "00"        # 조회구분코드 (00: 전체)
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        
        data = response.json()
        
        # 디버깅: 전체 응답 출력
        print("\n=== 달러 예수금 조회 API 응답 ===")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        
        if data.get('rt_cd') != '0':
            print(f"✗ 예수금 조회 실패: {data.get('msg1', '알 수 없는 오류')}")
            print(f"  응답 코드: {data.get('rt_cd')}")
            print(f"  메시지: {data.get('msg_cd')}")
            return None
        
        output = data.get('output', {})
        
        # 디버깅: output 키 확인
        if output:
            print("\n[Output 사용 가능한 필드]")
            for key, value in output.items():
                print(f"  {key}: {value}")
        
        # 주요 필드 매핑
        result = {
            'available_usd': float(output.get('frcr_dncl_amt_2', 0) or 0),     # 외화예수금
            'deposit_usd': float(output.get('frcr_use_psbl_amt', 0) or 0),     # 외화사용가능금액  
            'order_possible_usd': float(output.get('max_buy_amt', 0) or 0),    # 최대매수금액
            # 추가 정보
            'withdrawable_usd': float(output.get('frcr_drwg_psbl_amt', 0) or 0)  # 외화출금가능금액
        }
        
        return result
        
    except requests.exceptions.RequestException as e:
        print(f"✗ API 요청 오류: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"  응답 내용: {e.response.text}")
        return None
    except Exception as e:
        print(f"✗ 예수금 조회 중 오류: {e}")
        import traceback
        traceback.print_exc()
        return None

# 미국 주식과 예수금 총 잔고
def get_total_balance():
    """
    미국주식 총 잔고 (평가금액 + 달러 예수금)
    
    Returns:
    dict: {
        'stocks': 종목별 보유내역,
        'stock_eval_usd': 주식 평가금액(달러),
        'cash_usd': 달러 예수금,
        'total_usd': 총 자산(달러),
        'total_krw': 총 자산(원화 환산)
    }
    """
    print("\n=== 미국 주식 잔고 조회 ===")
    
    # 1. 주식 잔고 조회
    stock_balance = get_US_stock_balance()
    if stock_balance is None:
        return None
    
    # 2. 달러 예수금 조회
    dollar_balance = get_US_dollar_balance()
    if dollar_balance is None:
        return None
    
    # 3. 종목별 상세 출력
    if stock_balance['stocks']:
        print("\n[보유 종목]")
        for stock in stock_balance['stocks']:
            print(f"  • {stock['name']} ({stock['ticker']})")
            print(f"    - 보유수량: {stock['quantity']:,}주")
            print(f"    - 평균단가: ${stock['avg_price']:.2f}")
            print(f"    - 현재가: ${stock['current_price']:.2f}")
            print(f"    - 평가금액: ${stock['eval_amt']:,.2f}")
            print(f"    - 손익: ${stock['profit_loss']:,.2f} ({stock['profit_loss_rate']:.2f}%)")
    else:
        print("\n[보유 종목] 없음")
    
    # 4. 총 평가금액 계산
    stock_eval_usd = sum(stock['eval_amt'] for stock in stock_balance['stocks'])
    cash_usd = dollar_balance['available_usd']
    total_usd = stock_eval_usd + cash_usd
    
    # 5. 환율 정보 (대략적인 환산, 실제로는 API에서 받아온 원화 금액 사용)
    # 원화 총액은 API output2의 tot_evlu_pfls_amt 활용 가능
    
    print(f"\n[달러 예수금]")
    print(f"  • 출금가능금액: ${cash_usd:,.2f}")
    print(f"  • 주문가능금액: ${dollar_balance['order_possible_usd']:,.2f}")
    
    print(f"\n[총 자산 현황]")
    print(f"  • 주식 평가금액: ${stock_eval_usd:,.2f}")
    print(f"  • 달러 예수금: ${cash_usd:,.2f}")
    print(f"  • 총 자산(USD): ${total_usd:,.2f}")
    
    result = {
        'stocks': stock_balance['stocks'],
        'stock_eval_usd': stock_eval_usd,
        'cash_usd': cash_usd,
        'total_usd': total_usd,
        'available_cash_usd': dollar_balance['available_usd'],
        'order_possible_usd': dollar_balance['order_possible_usd']
    }
    
    return result

# 사용 예시
# print("\n=== 미국 주식 잔고 조회 테스트 ===")
# result = get_US_stock_balance()
# for i in range(len(result['stocks'])):
#     print(f"{i+1}. {result['stocks'][i]['name']} ({result['stocks'][i]['ticker']})")
#     print(f"  - 보유수량: {result['stocks'][i]['quantity']:,}주")
#     print(f"  - 평균단가: ${result['stocks'][i]['avg_price']:.2f}")
#     print(f"  - 현재가: ${result['stocks'][i]['current_price']:.2f}")
#     print(f"  - 평가금액: ${result['stocks'][i]['eval_amt']:,.2f}")
#     print(f"  - 손익: ${result['stocks'][i]['profit_loss']:,.2f} ({result['stocks'][i]['profit_loss_rate']:.2f}%)")


# 2. 달러 예수금 조회
print("\n=== 미국 달러화 예수금 잔고 조회 테스트 ===")

dollar_balance = get_US_dollar_balance()
print(dollar_balance)
#output2에 달러가 있음. 내일 클로드에게 문의할 것
#   "output2": [
#     {
#       "crcy_cd": "USD",
#       "crcy_cd_name": "미국 달러",
#       "frcr_buy_amt_smtl": "0.000000",
#       "frcr_sll_amt_smtl": "0.000000",
#       "frcr_dncl_amt_2": "233.240000",
#       "frst_bltn_exrt": "1402.20000000",
#       "frcr_buy_mgn_amt": "0.00000000",
#       "frcr_etc_mgna": "0.00000000",
#       "frcr_drwg_psbl_amt_1": "233.240000",
#       "frcr_evlu_amt2": "327049.000000",
#       "acpl_cstd_crcy_yn": "N",
#       "nxdy_frcr_drwg_psbl_amt": "233.240000"
#     }

# 사용 예시
# print("애플 현재가:", current_price_US("AAPL", "NAS").json()['output']['last'])
# print("\n=== 거래소 찾기 테스트 ===")
# tsla_exchange = get_US_exchange("TSLA")
# print(f"TSLA 거래소: {tsla_exchange}\n")

# 주문 시 자동으로 거래소 찾아서 사용
# ticker = "AAPL"
# exchange = get_US_exchange(ticker)
# if exchange:
#     # result = order_buy_US(ticker, 1, 150.50, exchange)
#     print(f"{ticker} 매수 주문 준비 완료 (거래소: {exchange})")

# 매수 주문 예시 (실제 주문 시 주석 해제)
# result = order_buy_US("AAPL", 1, 150.50, "NASD")
# print("매수 주문 결과:", result.json())

# 매도 주문 예시 (실제 주문 시 주석 해제)
# result = order_sell_US("AAPL", 1, 160.00, "NASD")
# print("매도 주문 결과:", result.json())