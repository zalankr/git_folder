import requests
import time
import hmac
import hashlib
from urllib.parse import urlencode
from typing import Dict, List, Optional, Union

class BinanceUSDTManager:
    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = "https://api.binance.com"
    
    def _generate_signature(self, params: Dict) -> str:
        """API 서명 생성"""
        query_string = urlencode(params)
        return hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None) -> Dict:
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
        
        try:
            if method == 'GET':
                response = requests.get(url, params=params, headers=headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, params=params, headers=headers, timeout=30)
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            return {"error": f"Request failed: {str(e)}"}
    
    # 1. Earn Account USDT Flexible Products 수량 확인
    def get_usdt_flexible_balance(self) -> Dict:
        """
        Earn Account의 USDT Flexible Products 잔액 조회
        
        Returns:
            Dict: {'balance': float, 'product_id': str, 'annual_rate': float} or {'error': str}
        """
        try:
            # 현재 플렉서블 포지션 조회
            endpoint = "/sapi/v1/lending/daily/token/position"
            positions = self._make_request('GET', endpoint)
            
            if 'error' in positions:
                return positions
            
            # USDT 포지션 찾기
            for position in positions:
                if position.get('asset') == 'USDT':
                    return {
                        'balance': float(position.get('totalAmount', 0)),
                        'product_id': position.get('productId'),
                        'annual_rate': float(position.get('annualPercentageRate', 0)),
                        'free_amount': float(position.get('freeAmount', 0)),
                        'locked_amount': float(position.get('lockedAmount', 0))
                    }
            
            return {'balance': 0.0, 'product_id': None, 'message': 'No USDT flexible position found'}
            
        except Exception as e:
            return {'error': f"Error getting USDT flexible balance: {str(e)}"}
    
    # 2. USDT Flexible Products Redeem (Fast)
    def redeem_usdt_flexible(self, amount: Union[float, str] = 'all', redeem_type: str = 'FAST') -> Dict:
        """
        USDT Flexible Products에서 일부/전체 Redeem
        
        Args:
            amount: 리딤할 수량 ('all' for 전체, float for 특정 수량)
            redeem_type: 'FAST' 또는 'NORMAL'
        
        Returns:
            Dict: 리딤 결과 또는 에러 정보
        """
        try:
            # 현재 잔액 확인
            balance_info = self.get_usdt_flexible_balance()
            if 'error' in balance_info:
                return balance_info
            
            current_balance = balance_info['balance']
            product_id = balance_info['product_id']
            
            if current_balance <= 0:
                return {'error': 'No USDT balance in flexible products'}
            
            if not product_id:
                return {'error': 'USDT flexible product ID not found'}
            
            # 리딤 수량 결정
            if amount == 'all':
                redeem_amount = current_balance
            else:
                redeem_amount = float(amount)
                if redeem_amount > current_balance:
                    return {'error': f'Insufficient balance. Available: {current_balance}, Requested: {redeem_amount}'}
            
            # 최소 금액 체크 (0.1 USDT)
            if redeem_amount < 0.1:
                return {'error': f'Minimum redemption amount is 0.1 USDT. Requested: {redeem_amount}'}
            
            # 리딤 실행
            endpoint = "/sapi/v1/lending/daily/redeem"
            params = {
                'productId': product_id,
                'amount': str(redeem_amount),
                'type': redeem_type
            }
            
            result = self._make_request('POST', endpoint, params)
            
            if 'error' in result:
                return result
            
            return {
                'success': True,
                'redeemed_amount': redeem_amount,
                'type': redeem_type,
                'remaining_balance': current_balance - redeem_amount,
                'result': result
            }
            
        except Exception as e:
            return {'error': f"Error redeeming USDT flexible: {str(e)}"}
    
    # 3. Funding Account USDT 잔액 확인
    def get_funding_usdt_balance(self) -> Dict:
        """
        Funding Account의 USDT 잔액 조회
        
        Returns:
            Dict: {'balance': float, 'free': float, 'locked': float} or {'error': str}
        """
        try:
            endpoint = "/sapi/v1/asset/get-funding-asset"
            params = {
                'asset': 'USDT',
                'needBtcValuation': 'false'
            }
            
            result = self._make_request('POST', endpoint, params)
            
            if 'error' in result:
                return result
            
            # USDT 찾기
            for asset in result:
                if asset.get('asset') == 'USDT':
                    free_amount = float(asset.get('free', 0))
                    locked_amount = float(asset.get('locked', 0))
                    return {
                        'balance': free_amount + locked_amount,
                        'free': free_amount,
                        'locked': locked_amount
                    }
            
            return {'balance': 0.0, 'free': 0.0, 'locked': 0.0}
            
        except Exception as e:
            return {'error': f"Error getting funding USDT balance: {str(e)}"}
    
    # 4. Funding Account USDT를 Flexible Savings에 Subscribe
    def subscribe_usdt_from_funding(self, amount: Union[float, str] = 'all') -> Dict:
        """
        Funding Account의 USDT를 Flexible Savings에 예치
        
        Args:
            amount: 예치할 수량 ('all' for 전체, float for 특정 수량)
        
        Returns:
            Dict: 예치 결과 또는 에러 정보
        """
        try:
            # 1. Funding 잔액 확인
            funding_balance = self.get_funding_usdt_balance()
            if 'error' in funding_balance:
                return funding_balance
            
            available_amount = funding_balance['free']
            if available_amount <= 0:
                return {'error': 'No available USDT in funding account'}
            
            # 2. 예치할 수량 결정
            if amount == 'all':
                subscribe_amount = available_amount
            else:
                subscribe_amount = float(amount)
                if subscribe_amount > available_amount:
                    return {'error': f'Insufficient balance. Available: {available_amount}, Requested: {subscribe_amount}'}
            
            # 3. USDT 플렉서블 상품 ID 조회
            product_id = self._get_usdt_flexible_product_id()
            if not product_id:
                return {'error': 'USDT flexible product not found'}
            
            # 4. Funding → Earn 이체
            transfer_result = self.transfer_accounts('USDT', subscribe_amount, 'FUNDING', 'EARN')
            if 'error' in transfer_result:
                return {'error': f'Transfer failed: {transfer_result["error"]}'}
            
            # 5. Flexible Savings에 예치
            endpoint = "/sapi/v1/lending/daily/purchase"
            params = {
                'productId': product_id,
                'amount': str(subscribe_amount)
            }
            
            result = self._make_request('POST', endpoint, params)
            
            if 'error' in result:
                # 이체는 성공했지만 예치 실패시 롤백 정보 제공
                return {
                    'error': f'Subscribe failed: {result["error"]}',
                    'note': f'USDT {subscribe_amount} transferred to EARN account but not subscribed to flexible savings'
                }
            
            return {
                'success': True,
                'subscribed_amount': subscribe_amount,
                'transfer_id': transfer_result.get('transfer_id'),
                'remaining_funding_balance': available_amount - subscribe_amount,
                'result': result
            }
            
        except Exception as e:
            return {'error': f"Error subscribing USDT from funding: {str(e)}"}
    
    # 5. EARN - FUNDING - SPOT Account간 Transfer
    def transfer_accounts(self, asset: str, amount: Union[float, str], from_account: str, to_account: str) -> Dict:
        """
        계정 간 자산 이체
        
        Args:
            asset: 자산 심볼 (예: 'USDT')
            amount: 이체할 수량 ('all' for 해당 계정 전체, float for 특정 수량)
            from_account: 출금 계정 ('SPOT', 'FUNDING', 'EARN')
            to_account: 입금 계정 ('SPOT', 'FUNDING', 'EARN')
        
        Returns:
            Dict: 이체 결과 또는 에러 정보
        """
        try:
            # 계정 타입 매핑
            account_mapping = {
                'SPOT': 'MAIN',
                'FUNDING': 'FUNDING', 
                'EARN': 'EARN'
            }
            
            if from_account not in account_mapping or to_account not in account_mapping:
                return {'error': 'Invalid account type. Use SPOT, FUNDING, or EARN'}
            
            if from_account == to_account:
                return {'error': 'From and To accounts cannot be the same'}
            
            # 이체할 수량 결정
            if amount == 'all':
                if from_account == 'SPOT':
                    balance_info = self.get_spot_balance(asset)
                elif from_account == 'FUNDING':
                    balance_info = self.get_funding_usdt_balance() if asset == 'USDT' else {'error': 'Only USDT supported for funding'}
                elif from_account == 'EARN':
                    balance_info = self.get_usdt_flexible_balance() if asset == 'USDT' else {'error': 'Only USDT supported for earn'}
                
                if 'error' in balance_info:
                    return balance_info
                
                transfer_amount = balance_info.get('free', balance_info.get('balance', 0))
                if transfer_amount <= 0:
                    return {'error': f'No available {asset} in {from_account} account'}
            else:
                transfer_amount = float(amount)
            
            # 이체 실행
            endpoint = "/sapi/v1/asset/transfer"
            params = {
                'type': f"{account_mapping[from_account]}_to_{account_mapping[to_account]}",
                'asset': asset,
                'amount': str(transfer_amount)
            }
            
            result = self._make_request('POST', endpoint, params)
            
            if 'error' in result:
                return result
            
            return {
                'success': True,
                'asset': asset,
                'amount': transfer_amount,
                'from_account': from_account,
                'to_account': to_account,
                'transfer_id': result.get('tranId'),
                'result': result
            }
            
        except Exception as e:
            return {'error': f"Error transferring between accounts: {str(e)}"}
    
    # 보조 함수들
    def _get_usdt_flexible_product_id(self) -> Optional[str]:
        """USDT 플렉서블 상품 ID 조회"""
        try:
            endpoint = "/sapi/v1/lending/daily/product/list"
            params = {'status': 'SUBSCRIBABLE'}
            products = self._make_request('GET', endpoint, params)
            
            if 'error' in products or not isinstance(products, list):
                return None
            
            for product in products:
                if product.get('asset') == 'USDT' and product.get('status') == 'SUBSCRIBABLE':
                    return product.get('productId')
            
            return None
            
        except Exception:
            return None
    
    def get_spot_balance(self, asset: str) -> Dict:
        """SPOT 계정 특정 자산 잔액 조회"""
        try:
            endpoint = "/api/v3/account"
            result = self._make_request('GET', endpoint)
            
            if 'error' in result:
                return result
            
            for balance in result.get('balances', []):
                if balance.get('asset') == asset:
                    free_amount = float(balance.get('free', 0))
                    locked_amount = float(balance.get('locked', 0))
                    return {
                        'balance': free_amount + locked_amount,
                        'free': free_amount,
                        'locked': locked_amount
                    }
            
            return {'balance': 0.0, 'free': 0.0, 'locked': 0.0}
            
        except Exception as e:
            return {'error': f"Error getting spot balance: {str(e)}"}
    
    # 종합 상태 조회
    def get_usdt_summary(self) -> Dict:
        """모든 계정의 USDT 잔액 종합 조회"""
        try:
            spot_balance = self.get_spot_balance('USDT')
            funding_balance = self.get_funding_usdt_balance() 
            earn_balance = self.get_usdt_flexible_balance()
            
            return {
                'spot': {
                    'total': spot_balance.get('balance', 0),
                    'free': spot_balance.get('free', 0),
                    'locked': spot_balance.get('locked', 0)
                },
                'funding': {
                    'total': funding_balance.get('balance', 0),
                    'free': funding_balance.get('free', 0),
                    'locked': funding_balance.get('locked', 0)
                },
                'earn': {
                    'total': earn_balance.get('balance', 0),
                    'annual_rate': earn_balance.get('annual_rate', 0)
                },
                'grand_total': (
                    spot_balance.get('balance', 0) + 
                    funding_balance.get('balance', 0) + 
                    earn_balance.get('balance', 0)
                )
            }
            
        except Exception as e:
            return {'error': f"Error getting USDT summary: {str(e)}"}
        
# 사용 예시 함수들
def main_example_trading():
    """사용 예시"""
    # API 키 설정
    API_KEY = "your_api_key_here"
    SECRET_KEY = "your_secret_key_here"
    
    # 매니저 인스턴스 생성
    manager = BinanceUSDTManager(API_KEY, SECRET_KEY)
    
    print("=== Binance USDT Manager ===\n")
    
    # 1. 전체 USDT 현황 조회
    print("1. USDT 종합 현황:")
    summary = manager.get_usdt_summary()
    if 'error' not in summary:
        print(f"   SPOT: {summary['spot']['total']:.2f} USDT")
        print(f"   FUNDING: {summary['funding']['total']:.2f} USDT")
        print(f"   EARN: {summary['earn']['total']:.2f} USDT (연 {summary['earn']['annual_rate']:.2f}%)")
        print(f"   총합: {summary['grand_total']:.2f} USDT\n")
    else:
        print(f"   에러: {summary['error']}\n")
    
    # 2. BTC/USDT 현재가 조회
    print("2. BTC/USDT 현재가:")
    btc_price = manager.get_btc_usdt_current_price()
    if 'error' not in btc_price:
        print(f"   현재가: ${btc_price['price']:,.2f}\n")
    else:
        print(f"   에러: {btc_price['error']}\n")
    
    # 3. BTC/USDT 미체결 주문 조회
    print("3. BTC/USDT 미체결 주문:")
    open_orders = manager.get_btc_usdt_open_orders()
    if 'error' not in open_orders:
        print(f"   미체결 주문 수: {open_orders['count']}개\n")
    else:
        print(f"   에러: {open_orders['error']}\n")
    
    # 4. 예시 작업들 (실제 실행시 주의!)
    print("4. 사용 가능한 작업들:")
    print("   === 계정 관리 ===")
    print("   - manager.redeem_usdt_flexible('all')  # 전체 인출")
    print("   - manager.subscribe_usdt_from_funding('all')  # Funding 전체를 Earn으로")
    print("   - manager.transfer_accounts('USDT', 100, 'SPOT', 'FUNDING')  # SPOT → FUNDING")
    print("   ")
    print("   === BTC/USDT 거래 ===")
    print("   - manager.cancel_all_btc_usdt_orders()  # 모든 미체결 주문 취소")
    print("   - manager.split_buy_btc_usdt(5, 1000)  # 1000 USDT를 5회 분할 매수")
    print("   - manager.split_sell_btc_usdt(3, 0.1)  # 0.1 BTC를 3회 분할 매도")
    print("   ")
    print("   === 분할 매매 가격 예시 ===")
    if 'error' not in btc_price:
        current = btc_price['price']
        print(f"   현재가: ${current:,.2f}")
        print("   분할 매수 가격 (5회):")
        for i in range(5):
            discount = 0.05 + (i * 0.05)
            buy_price = current * (1 - discount / 100)
            print(f"     {i+1}차: ${buy_price:,.2f} (-{discount:.2f}%)")
        print("   ")
        print("   분할 매도 가격 (3회):")
        for i in range(3):
            markup = 0.05 + (i * 0.05)
            sell_price = current * (1 + markup / 100)
            print(f"     {i+1}차: ${sell_price:,.2f} (+{markup:.2f}%)")

def trading_example():
    """거래 예시 (주의: 실제 거래 실행됨!)"""
    API_KEY = "your_api_key_here"
    SECRET_KEY = "your_secret_key_here"
    
    manager = BinanceUSDTManager(API_KEY, SECRET_KEY)
    
    print("=== BTC/USDT 거래 예시 ===\n")
    
    # 1. 모든 미체결 주문 취소
    print("1. 모든 미체결 주문 취소:")
    cancel_result = manager.cancel_all_btc_usdt_orders()
    print(f"   결과: {cancel_result}\n")
    
    # 2. 분할 매수 예시 (1000 USDT를 5회 분할)
    print("2. 분할 매수 (1000 USDT, 5회 분할):")
    buy_result = manager.split_buy_btc_usdt(5, 1000)
    if 'error' not in buy_result:
        print(f"   성공 주문: {buy_result['successful_orders']}개")
        print(f"   실패 주문: {buy_result['failed_orders']}개")
        print(f"   회당 금액: {buy_result['usdt_per_order']:.2f} USDT")
    else:
        print(f"   에러: {buy_result['error']}")
    print()
    
    # 3. 분할 매도 예시 (0.1 BTC를 3회 분할)  
    print("3. 분할 매도 (0.1 BTC, 3회 분할):")
    sell_result = manager.split_sell_btc_usdt(3, 0.1)
    if 'error' not in sell_result:
        print(f"   성공 주문: {sell_result['successful_orders']}개")
        print(f"   실패 주문: {sell_result['failed_orders']}개")
        print(f"   회당 수량: {sell_result['btc_per_order']:.8f} BTC")
    else:
        print(f"   에러: {sell_result['error']}")

if __name__ == "__main__":
    # 기본 예시 (거래 실행 안됨)
    main_example_trading()
    
    # 거래 예시 (실제 거래 실행됨 - 주석 해제시 주의!)
    # trading_example()

# 사용 예시 함수들
def main_example_saving():
    """사용 예시"""
    # API 키 설정
    API_KEY = "your_api_key_here"
    SECRET_KEY = "your_secret_key_here"
    
    # 매니저 인스턴스 생성
    manager = BinanceUSDTManager(API_KEY, SECRET_KEY)
    
    print("=== Binance USDT Manager ===\n")
    
    # 1. 전체 USDT 현황 조회
    print("1. USDT 종합 현황:")
    summary = manager.get_usdt_summary()
    if 'error' not in summary:
        print(f"   SPOT: {summary['spot']['total']:.2f} USDT")
        print(f"   FUNDING: {summary['funding']['total']:.2f} USDT")
        print(f"   EARN: {summary['earn']['total']:.2f} USDT (연 {summary['earn']['annual_rate']:.2f}%)")
        print(f"   총합: {summary['grand_total']:.2f} USDT\n")
    else:
        print(f"   에러: {summary['error']}\n")
    
    # 2. Earn Account의 USDT Flexible 잔액 확인
    print("2. Earn Account USDT Flexible 잔액:")
    earn_balance = manager.get_usdt_flexible_balance()
    if 'error' not in earn_balance:
        print(f"   잔액: {earn_balance['balance']:.2f} USDT")
        print(f"   연 수익률: {earn_balance['annual_rate']:.2f}%\n")
    else:
        print(f"   에러: {earn_balance['error']}\n")
    
    # 3. 예시 작업들 (실제 실행시 주의!)
    print("3. 사용 가능한 작업들:")
    print("   - manager.redeem_usdt_flexible('all')  # 전체 인출")
    print("   - manager.redeem_usdt_flexible(100.0)  # 100 USDT 인출")
    print("   - manager.subscribe_usdt_from_funding('all')  # Funding 전체를 Earn으로")
    print("   - manager.transfer_accounts('USDT', 100, 'SPOT', 'FUNDING')  # SPOT → FUNDING")

if __name__ == "__main__":
    main_example_saving()