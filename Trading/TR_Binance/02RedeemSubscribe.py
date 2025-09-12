import ccxt
import requests
import hmac
import hashlib
import time
from typing import Dict, List, Optional

class BinanceManager:
    def __init__(self, api_key: str, api_secret: str, sandbox: bool = False):
        """
        Binance API 관리 클래스
        
        Args:
            api_key: Binance API 키
            api_secret: Binance API 시크릿
            sandbox: 테스트넷 사용 여부
        """
        self.api_key = api_key
        self.api_secret = api_secret
        
        # CCXT 거래소 인스턴스 생성
        self.exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'sandbox': sandbox,
            'enableRateLimit': True,
        })
        
        # Binance API 기본 URL
        self.base_url = 'https://api.binance.com' if not sandbox else 'https://testnet.binance.vision'
    
    def _create_signature(self, query_string: str) -> str:
        """API 서명 생성"""
        return hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    def _make_request(self, endpoint: str, params: Dict = None, method: str = 'GET') -> Dict:
        """Binance API 요청"""
        if params is None:
            params = {}
        
        params['timestamp'] = int(time.time() * 1000)
        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        signature = self._create_signature(query_string)
        
        headers = {
            'X-MBX-APIKEY': self.api_key
        }
        
        url = f"{self.base_url}{endpoint}?{query_string}&signature={signature}"
        
        if method == 'GET':
            response = requests.get(url, headers=headers)
        elif method == 'POST':
            response = requests.post(url, headers=headers)
        elif method == 'DELETE':
            response = requests.delete(url, headers=headers)
        
        return response.json()

    def get_total_usdt_balance(self) -> Dict[str, float]:
        """
        1. 전체 계좌의 USDT 잔고조회 (Funding, Earn, Spot Account USDT)
        
        Returns:
            Dict: 각 계좌별 USDT 잔고
        """
        try:
            # Spot Account USDT
            spot_balance = self.exchange.fetch_balance()
            spot_usdt = spot_balance.get('USDT', {}).get('free', 0)
            
            # Funding Account USDT
            funding_response = self._make_request('/sapi/v1/asset/get-funding-asset', {'asset': 'USDT'})
            funding_usdt = float(funding_response[0]['free']) if funding_response else 0
            
            # Earn Account USDT (Simple Earn)
            earn_response = self._make_request('/sapi/v1/simple-earn/account')
            earn_usdt = 0
            for position in earn_response.get('positionAmountVos', []):
                if position['asset'] == 'USDT':
                    earn_usdt += float(position['amount'])
            
            total_usdt = spot_usdt + funding_usdt + earn_usdt
            
            return {
                'spot_usdt': spot_usdt,
                'funding_usdt': funding_usdt,
                'earn_usdt': earn_usdt,
                'total_usdt': total_usdt
            }
            
        except Exception as e:
            print(f"USDT 잔고 조회 오류: {e}")
            return {}

    def get_spot_btc_balance(self) -> float:
        """
        2. SPOT계좌의 BTC 잔고조회
        
        Returns:
            float: BTC 잔고
        """
        try:
            balance = self.exchange.fetch_balance()
            btc_balance = balance.get('BTC', {}).get('free', 0)
            return btc_balance
        except Exception as e:
            print(f"BTC 잔고 조회 오류: {e}")
            return 0

    def get_flexible_usdt_amount(self) -> float:
        """
        3. Earn Account USDT Flexible Products 수량 확인
        
        Returns:
            float: Flexible Products USDT 수량
        """
        try:
            response = self._make_request('/sapi/v1/simple-earn/flexible/position', {'asset': 'USDT'})
            total_amount = 0
            
            for position in response.get('rows', []):
                if position['asset'] == 'USDT':
                    total_amount += float(position['totalAmount'])
            
            return total_amount
        except Exception as e:
            print(f"Flexible Products 조회 오류: {e}")
            return 0

    def redeem_flexible_usdt(self, amount: float, product_id: str = None) -> Dict:
        """
        4. USDT Flexible Products Redeem (Fast)
        
        Args:
            amount: 상환할 USDT 수량
            product_id: 상품 ID (선택사항)
            
        Returns:
            Dict: 상환 결과
        """
        try:
            params = {
                'asset': 'USDT',
                'amount': str(amount),
                'type': 'FAST'  # Fast redemption
            }
            
            if product_id:
                params['productId'] = product_id
            
            response = self._make_request('/sapi/v1/simple-earn/flexible/redeem', params, 'POST')
            return response
        except Exception as e:
            print(f"Flexible Products 상환 오류: {e}")
            return {}

    def subscribe_flexible_savings(self, amount: float, product_id: str = None) -> Dict:
        """
        5. Funding Account USDT를 Flexible Savings에 Subscribe
        
        Args:
            amount: 투자할 USDT 수량
            product_id: 상품 ID (선택사항)
            
        Returns:
            Dict: 구독 결과
        """
        try:
            # 먼저 Funding에서 Earn으로 이체 (필요시)
            # self.transfer_between_accounts('FUNDING', 'EARN', 'USDT', amount)
            
            params = {
                'asset': 'USDT',
                'amount': str(amount)
            }
            
            if product_id:
                params['productId'] = product_id
            
            response = self._make_request('/sapi/v1/simple-earn/flexible/subscribe', params, 'POST')
            return response
        except Exception as e:
            print(f"Flexible Savings 구독 오류: {e}")
            return {}

    def transfer_between_accounts(self, from_account: str, to_account: str, asset: str, amount: float) -> Dict:
        """
        6. EARN - FUNDING - SPOT Account간 Transfer
        
        Args:
            from_account: 출금 계좌 ('SPOT', 'FUNDING', 'EARN')
            to_account: 입금 계좌 ('SPOT', 'FUNDING', 'EARN')
            asset: 자산 심볼 (예: 'USDT', 'BTC')
            amount: 이체할 수량
            
        Returns:
            Dict: 이체 결과
        """
        try:
            # 계좌 타입 매핑
            account_mapping = {
                'SPOT': 'MAIN',
                'FUNDING': 'FUNDING',
                'EARN': 'EARN'
            }
            
            params = {
                'asset': asset,
                'amount': str(amount),
                'fromAccountType': account_mapping[from_account],
                'toAccountType': account_mapping[to_account]
            }
            
            response = self._make_request('/sapi/v1/asset/transfer', params, 'POST')
            return response
        except Exception as e:
            print(f"계좌 간 이체 오류: {e}")
            return {}

    def get_spot_asset_balance(self, asset: str) -> Dict[str, float]:
        """
        7. SPOT 계정 특정 자산 잔액 조회
        
        Args:
            asset: 자산 심볼 (예: 'BTC', 'ETH', 'USDT')
            
        Returns:
            Dict: 자산 잔액 정보 (free, used, total)
        """
        try:
            balance = self.exchange.fetch_balance()
            asset_balance = balance.get(asset, {})
            
            return {
                'free': asset_balance.get('free', 0),
                'used': asset_balance.get('used', 0),
                'total': asset_balance.get('total', 0)
            }
        except Exception as e:
            print(f"{asset} 잔액 조회 오류: {e}")
            return {'free': 0, 'used': 0, 'total': 0}

    def get_flexible_product_ids(self) -> List[Dict]:
        """
        8. USDT 플렉서블 상품 ID 조회
        
        Returns:
            List[Dict]: USDT 플렉서블 상품 정보 리스트
        """
        try:
            response = self._make_request('/sapi/v1/simple-earn/flexible/list', {'asset': 'USDT'})
            
            products = []
            for product in response.get('rows', []):
                if product['asset'] == 'USDT':
                    products.append({
                        'productId': product['productId'],
                        'productName': product['productName'],
                        'asset': product['asset'],
                        'avgAnnualPercentageRate': product.get('avgAnnualPercentageRate', ''),
                        'canPurchase': product.get('canPurchase', False),
                        'canRedeem': product.get('canRedeem', False)
                    })
            
            return products
        except Exception as e:
            print(f"플렉서블 상품 조회 오류: {e}")
            return []

# 사용 예제
def main():
    # API 키와 시크릿을 입력하세요
    API_KEY = "your_api_key_here"
    API_SECRET = "your_api_secret_here"
    
    # BinanceManager 인스턴스 생성
    binance = BinanceManager(API_KEY, API_SECRET, sandbox=False)
    
    # 1. 전체 USDT 잔고 조회
    print("=== 전체 USDT 잔고 ===")
    usdt_balances = binance.get_total_usdt_balance()
    print(usdt_balances)
    
    # 2. SPOT BTC 잔고 조회
    print("\n=== SPOT BTC 잔고 ===")
    btc_balance = binance.get_spot_btc_balance()
    print(f"BTC 잔고: {btc_balance}")
    
    # 3. Flexible USDT 수량 확인
    print("\n=== Flexible USDT 수량 ===")
    flexible_amount = binance.get_flexible_usdt_amount()
    print(f"Flexible USDT: {flexible_amount}")
    
    # 4. USDT 플렉서블 상품 ID 조회
    print("\n=== USDT 플렉서블 상품 ===")
    products = binance.get_flexible_product_ids()
    for product in products:
        print(product)
    
    # 5. 특정 자산 잔액 조회 (예: USDT)
    print("\n=== SPOT USDT 상세 잔액 ===")
    usdt_detail = binance.get_spot_asset_balance('USDT')
    print(usdt_detail)

if __name__ == "__main__":
    main()