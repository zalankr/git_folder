import requests
import time
import hmac
import hashlib
from urllib.parse import urlencode

class BinanceEarnAPI:
    def __init__(self, api_key, secret_key):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = "https://api.binance.com"
    
    def _generate_signature(self, params):
        """API 서명 생성"""
        query_string = urlencode(params)
        return hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    def _make_request(self, method, endpoint, params=None):
        """API 요청 실행"""
        if params is None:
            params = {}
        
        # 타임스탬프 추가
        params['timestamp'] = int(time.time() * 1000)
        
        # 서명 생성 및 추가
        params['signature'] = self._generate_signature(params)
        
        # 헤더 설정
        headers = {
            'X-MBX-APIKEY': self.api_key,
            'Content-Type': 'application/json'
        }
        
        url = f"{self.base_url}{endpoint}"
        
        if method == 'GET':
            response = requests.get(url, params=params, headers=headers)
        elif method == 'POST':
            response = requests.post(url, params=params, headers=headers)
        
        return response.json()
    
    def get_flexible_products(self):
        """플렉서블 상품 목록 조회"""
        endpoint = "/sapi/v1/lending/daily/product/list"
        params = {
            'status': 'SUBSCRIBABLE'  # 구독 가능한 상품만
        }
        return self._make_request('GET', endpoint, params)
    
    def get_flexible_positions(self):
        """현재 플렉서블 포지션 조회"""
        endpoint = "/sapi/v1/lending/daily/token/position"
        return self._make_request('GET', endpoint)
    
    def redeem_flexible_product(self, product_id, amount, redeem_type='FAST'):
        """
        플렉서블 상품에서 리딤(인출)
        
        Args:
            product_id (str): 상품 ID
            amount (float): 리딤할 수량
            redeem_type (str): 'FAST' (즉시-당일이자X) 또는 'NORMAL' (일반-인출다음날)
        Notes:
        일일 할당량: FAST 인출은 일일 제한이 있어서 대량 인출이 안될 수 있음
        인출 금지 시간: 매일 23:50-00:10 UTC 시간에는 인출 불가 > 8:40 KST 시그널 확인 후 인출 결정 8:56 Account transfer
        9:00부터 트레이딩 > 종료 후 다시 저장
        이자 계산: 구독 다음날부터 이자 발생 시작
        """
        endpoint = "/sapi/v1/lending/daily/redeem"
        params = {
            'productId': product_id,
            'amount': str(amount),
            'type': redeem_type
        }
        return self._make_request('POST', endpoint, params)

def main():
    # API 키 설정 (실제 키로 교체 필요)
    API_KEY = "your_api_key_here"
    SECRET_KEY = "your_secret_key_here"
    
    # Binance API 클래스 인스턴스 생성
    binance = BinanceEarnAPI(API_KEY, SECRET_KEY)
    
    try:
        # 1. 현재 플렉서블 포지션 조회
        print("1. 현재 플렉서블 포지션 조회 중...")
        positions = binance.get_flexible_positions()
        
        if 'code' in positions and positions['code'] != 200:
            print(f"에러: {positions}")
            return
        
        # USDT 포지션 찾기
        usdt_position = None
        for position in positions:
            if position['asset'] == 'USDT':
                usdt_position = position
                break
        
        if not usdt_position:
            print("USDT 플렉서블 포지션을 찾을 수 없습니다.")
            return
        
        print(f"USDT 잔액: {usdt_position['totalAmount']}")
        print(f"상품 ID: {usdt_position['productId']}")
        print(f"연 수익률: {usdt_position['annualPercentageRate']}%\n")
        
        # 2. 리딤할 수량 입력
        available_amount = float(usdt_position['totalAmount'])
        
        print(f"리딤 가능한 USDT: {available_amount}")
        redeem_amount = float(input("리딤할 USDT 수량을 입력하세요: "))
        
        if redeem_amount > available_amount:
            print("리딤 수량이 보유 수량을 초과합니다.")
            return
        
        # 3. 리딤 타입 선택
        print("\n리딤 타입을 선택하세요:")
        print("1. FAST (즉시 리딤)")
        print("2. NORMAL (일반 리딤)")
        
        redeem_type_choice = input("선택 (1 또는 2): ").strip()
        redeem_type = 'FAST' if redeem_type_choice == '1' else 'NORMAL'
        
        # 4. 리딤 실행
        print(f"\n{redeem_amount} USDT를 {redeem_type} 방식으로 리딤 중...")
        
        result = binance.redeem_flexible_product(
            product_id=usdt_position['productId'],
            amount=redeem_amount,
            redeem_type=redeem_type
        )
        
        if 'code' in result and result['code'] != 200:
            print(f"리딤 실패: {result}")
        else:
            print("✅ 리딤이 성공적으로 요청되었습니다!")
            print(f"결과: {result}")
        
    except Exception as e:
        print(f"오류 발생: {str(e)}")

# 개별 함수들 (필요시 사용)
def redeem_usdt_simple(api_key, secret_key, amount, redeem_type='FAST'):
    """
    간단한 USDT 리딤 함수
    """
    binance = BinanceEarnAPI(api_key, secret_key)
    
    # 현재 포지션 조회
    positions = binance.get_flexible_positions()
    
    # USDT 포지션 찾기
    usdt_position = None
    for position in positions:
        if position['asset'] == 'USDT':
            usdt_position = position
            break
    
    if not usdt_position:
        return {"error": "USDT 포지션을 찾을 수 없습니다."}
    
    # 리딤 실행
    return binance.redeem_flexible_product(
        product_id=usdt_position['productId'],
        amount=amount,
        redeem_type=redeem_type
    )

if __name__ == "__main__":
    main()