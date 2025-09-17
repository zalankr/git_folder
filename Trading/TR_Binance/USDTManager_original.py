import requests
import time
import hmac
import hashlib
from urllib.parse import urlencode
from typing import Dict, List, Optional, Union

class USDTM:
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
        Simple Earn의 USDT Flexible Products 잔액 조회
        
        Returns:
            Dict: {'balance': float, 'product_id': str, 'annual_rate': float} or {'error': str}
        """
        try:
            # Simple Earn 플렉서블 포지션 조회 (새로운 엔드포인트)
            endpoint = "/sapi/v1/simple-earn/flexible/position"
            positions = self._make_request('GET', endpoint)
            
            if 'error' in positions:
                return positions
            
            # positions가 dict이고 'rows' 키를 가지고 있는지 확인
            if isinstance(positions, dict) and 'rows' in positions:
                position_list = positions['rows']
            else:
                position_list = positions
            
            # USDT 포지션 찾기
            for position in position_list:
                if position.get('asset') == 'USDT':
                    return {
                        'balance': float(position.get('totalAmount', 0)),
                        'product_id': position.get('productId'),
                        'annual_rate': float(position.get('latestAnnualPercentageRate', 0)),
                        'free_amount': float(position.get('freeAmount', 0)),
                        'locked_amount': float(position.get('lockedAmount', 0)),
                        'today_purchased': float(position.get('todayPurchasedAmount', 0)),
                        'today_redeemed': float(position.get('todayRedeemedAmount', 0))
                    }
            
            return {'balance': 0.0, 'product_id': None, 'message': 'No USDT flexible position found'}
            
        except Exception as e:
            return {'error': f"Error getting USDT flexible balance: {str(e)}"}
    
    # 2. USDT Flexible Products Redeem (Fast)
    def redeem_usdt_flexible(self, amount: Union[float, str] = 'all', dest_account: str = 'SPOT') -> Dict:
        """
        USDT Flexible Products에서 일부/전체 Redeem (Simple Earn API 사용)
        
        Args:
            amount: 리딤할 수량 ('all' for 전체, float for 특정 수량)
            dest_account: 대상 계정 ('SPOT' 또는 'FUND', 기본값: 'SPOT')
        
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
            
            # 새로운 Simple Earn API 엔드포인트
            endpoint = "/sapi/v1/simple-earn/flexible/redeem"
            
            # 파라미터 구성
            if amount == 'all':
                # 전체 리딤
                params = {
                    'productId': product_id,
                    'redeemAll': 'true',
                    'destAccount': dest_account
                }
                redeem_amount = current_balance
            else:
                # 특정 수량 리딤
                redeem_amount = float(amount)
                if redeem_amount > current_balance:
                    return {'error': f'Insufficient balance. Available: {current_balance}, Requested: {redeem_amount}'}
                
                # 최소 금액 체크 (0.1 USDT)
                if redeem_amount < 0.1:
                    return {'error': f'Minimum redemption amount is 0.1 USDT. Requested: {redeem_amount}'}
                
                params = {
                    'productId': product_id,
                    'redeemAll': 'false',
                    'amount': str(redeem_amount),
                    'destAccount': dest_account
                }
            
            # 리딤 실행
            result = self._make_request('POST', endpoint, params)
            
            if 'error' in result:
                return result
            
            # 성공 응답 처리
            if result.get('success'):
                return {
                    'success': True,
                    'redeem_id': result.get('redeemId'),
                    'redeemed_amount': redeem_amount,
                    'dest_account': dest_account,
                    'remaining_balance': current_balance - redeem_amount if amount != 'all' else 0,
                    'result': result
                }
            else:
                return {'error': f'Redemption failed: {result}'}
            
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

    # 4. USDT Flexible Product ID 조회
    def get_usdt_flexible_product_id(self) -> str:
        """
        USDT Flexible Product ID 조회
        
        Returns:
            str: Product ID 또는 None
        """
        try:
            endpoint = "/sapi/v1/simple-earn/flexible/list"
            params = {
                'asset': 'USDT',
                'current': 1,
                'size': 10
            }
            
            products = self._make_request('GET', endpoint, params)
            
            if 'error' in products:
                return None
            
            # 응답이 dict이고 'rows' 키를 가지고 있는지 확인
            if isinstance(products, dict) and 'rows' in products:
                product_list = products['rows']
            else:
                product_list = products
            
            # USDT 상품 찾기
            for product in product_list:
                if (product.get('asset') == 'USDT' and 
                    product.get('canPurchase', False) and 
                    product.get('status') == 'PURCHASING'):
                    return product.get('productId')
            
            return None
            
        except Exception as e:
            print(f"Error getting USDT flexible product ID: {str(e)}")
            return None

    # 4. Funding Account USDT를 Flexible Savings에 Subscribe
    def subscribe_usdt_from_funding(self, amount: Union[float, str] = 'all') -> Dict:
        """
        Funding Account의 USDT를 Flexible Savings에 예치 (Simple Earn API 사용)
        
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
            
            # 최소 예치 금액 체크 (일반적으로 0.01 USDT)
            if subscribe_amount < 0.01:
                return {'error': f'Minimum subscription amount is 0.01 USDT. Requested: {subscribe_amount}'}
            
            # 3. USDT 플렉서블 상품 ID 조회
            product_id = self.get_usdt_flexible_product_id()
            if not product_id:
                return {'error': 'USDT flexible product not found or not available for purchase'}
            
            # 4. Funding에서 직접 Simple Earn에 예치 (새로운 API)
            endpoint = "/sapi/v1/simple-earn/flexible/subscribe"
            params = {
                'productId': product_id,
                'amount': f"{subscribe_amount:.8f}",
                'sourceAccount': 'FUND'  # FUND 계정에서 직접 예치
            }
            
            result = self._make_request('POST', endpoint, params)
            
            if 'error' in result:
                return {'error': f'Subscribe failed: {result["error"]}'}
            
            # 성공 응답 처리
            if result.get('success'):
                return {
                    'success': True,
                    'subscribed_amount': subscribe_amount,
                    'product_id': product_id,
                    'purchase_id': result.get('purchaseId'),
                    'remaining_funding_balance': available_amount - subscribe_amount,
                    'result': result
                }
            else:
                return {'error': f'Subscription failed: {result}'}
            
        except Exception as e:
            return {'error': f"Error subscribing USDT from funding: {str(e)}"}
    
    # 5. EARN - FUNDING - SPOT Account간 Transfer
    def transfer_accounts(self, asset: str, amount: Union[float, str], from_account: str, to_account: str) -> Dict:
        """
        계정 간 자산 이체 (Universal Transfer API 사용)
        
        Args:
            asset: 자산 심볼 (예: 'USDT')
            amount: 이체할 수량 ('all' for 해당 계정 전체, float for 특정 수량)
            from_account: 출금 계정 ('SPOT', 'FUNDING', 'MARGIN', 'UMFUTURE', 'CMFUTURE')
            to_account: 입금 계정 ('SPOT', 'FUNDING', 'MARGIN', 'UMFUTURE', 'CMFUTURE')
        
        Returns:
            Dict: 이체 결과 또는 에러 정보
        """
        try:
            # Transfer type 매핑 (Binance Universal Transfer API 기준)
            transfer_types = {
                ('SPOT', 'FUNDING'): 'MAIN_FUNDING',
                ('FUNDING', 'SPOT'): 'FUNDING_MAIN',
                ('SPOT', 'MARGIN'): 'MAIN_MARGIN',
                ('MARGIN', 'SPOT'): 'MARGIN_MAIN',
                ('SPOT', 'UMFUTURE'): 'MAIN_UMFUTURE',
                ('UMFUTURE', 'SPOT'): 'UMFUTURE_MAIN',
                ('SPOT', 'CMFUTURE'): 'MAIN_CMFUTURE',
                ('CMFUTURE', 'SPOT'): 'CMFUTURE_MAIN',
                ('FUNDING', 'UMFUTURE'): 'FUNDING_UMFUTURE',
                ('UMFUTURE', 'FUNDING'): 'UMFUTURE_FUNDING',
                ('FUNDING', 'MARGIN'): 'FUNDING_MARGIN',
                ('MARGIN', 'FUNDING'): 'MARGIN_FUNDING',
                ('FUNDING', 'CMFUTURE'): 'FUNDING_CMFUTURE',
                ('CMFUTURE', 'FUNDING'): 'CMFUTURE_FUNDING',
                ('MARGIN', 'UMFUTURE'): 'MARGIN_UMFUTURE',
                ('UMFUTURE', 'MARGIN'): 'UMFUTURE_MARGIN',
                ('MARGIN', 'CMFUTURE'): 'MARGIN_CMFUTURE',
                ('CMFUTURE', 'MARGIN'): 'CMFUTURE_MARGIN'
            }
            
            transfer_key = (from_account, to_account)
            
            if transfer_key not in transfer_types:
                return {'error': f'Transfer from {from_account} to {to_account} is not supported'}
            
            if from_account == to_account:
                return {'error': 'From and To accounts cannot be the same'}
            
            # 이체할 수량 결정
            if amount == 'all':
                if from_account == 'SPOT':
                    balance_info = self.get_spot_balance(asset)
                elif from_account == 'FUNDING':
                    balance_info = self.get_funding_usdt_balance() if asset == 'USDT' else {'error': 'Only USDT supported for funding'}
                elif from_account == 'EARN':
                    # EARN은 Universal Transfer에서 직접 지원되지 않으므로 별도 처리 필요
                    return {'error': 'EARN account transfers require special handling. Use redeem first.'}
                else:
                    return {'error': f'Balance check not implemented for {from_account} account'}
                
                if 'error' in balance_info:
                    return balance_info
                
                transfer_amount = balance_info.get('free', balance_info.get('balance', 0))
                if transfer_amount <= 0:
                    return {'error': f'No available {asset} in {from_account} account'}
            else:
                transfer_amount = float(amount)
            
            # 최소 이체 금액 체크
            if transfer_amount < 0.00000001:  # 8자리 소수점
                return {'error': f'Transfer amount too small: {transfer_amount}'}
            
            # 이체 실행
            endpoint = "/sapi/v1/asset/transfer"
            params = {
                'type': transfer_types[transfer_key],
                'asset': asset,
                'amount': f"{transfer_amount:.8f}"  # 8자리 소수점으로 포맷
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
                'transfer_type': transfer_types[transfer_key],
                'transfer_id': result.get('tranId'),
                'result': result
            }
            
        except Exception as e:
            return {'error': f"Error transferring between accounts: {str(e)}"}

    # 6. SPOT Account ticker별 잔액 확인
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
    
    # 7. 모든 계정의 종합 USDT 잔액 조회
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

# API 키 불러오기
# with open("C:/Users/ilpus/Desktop/NKL_invest/bnnkr.txt") as f:
#     API_KEY, API_SECRET = [line.strip() for line in f.readlines()]

# 매니저 인스턴스 생성
# USDTmanager = USDTManager(API_KEY, API_SECRET)

# # 1. 전체 USDT 현황 조회
# print("1. USDT 종합 현황:")
# summary = USDTmanager.get_usdt_summary()
# if 'error' not in summary:
#     print(f"   SPOT: {summary['spot']['total']:.2f} USDT")
#     print(f"   FUNDING: {summary['funding']['total']:.2f} USDT")
#     print(f"   EARN: {summary['earn']['total']:.2f} USDT (연 {summary['earn']['annual_rate']:.2f}%)")
#     print(f"   총합: {summary['grand_total']:.2f} USDT\n")
# else:
#     print(f"   에러: {summary['error']}\n")

# # 2. USDT Flexible 잔액 조회
# print("2. USDT Flexible 잔액:")
# earn_balance = USDTmanager.get_usdt_flexible_balance()
# if 'error' not in earn_balance: 
#     print(f"   잔액: {earn_balance['balance']:.2f} USDT")
#     print(f"   연 이율: {earn_balance['annual_rate']:.2f}%")
#     print(f"   자유 사용 가능: {earn_balance['free_amount']:.2f} USDT")
#     print(f"   잠긴 금액: {earn_balance['locked_amount']:.2f} USDT\n")
# else:
#     print(f"   에러: {earn_balance['error']}\n")

# # 3. flexible Product ID 조회 (USDT)
# print("3. flexible Product ID 조회:")
# earn_balance = USDTmanager.get_usdt_flexible_balance()
# if earn_balance:
#     print(f"   USDT Flexible Product ID: {earn_balance['product_id']}\n")
# else:   
#     print("   에러: USDT Flexible Product not found\n")

# # 4. USDT Flexible Products Redeem (Fast)
# print("4. USDT Flexible Products Redeem (Fast):")
# result = USDTmanager.redeem_usdt_flexible(amount='all', dest_account='SPOT')
# if 'error' not in result:
#     print(f"   성공적으로 인출되었습니다: {result['redeemed_amount']:.2f} USDT")
#     print(f"   Redeem ID: {result.get('redeem_id')}")
#     print(f"   남은 잔액: {result['remaining_balance']:.2f} USDT")
#     print(f"   대상 계정: {result['dest_account']}\n")
# else:
#     print(f"   에러: {result['error']}\n")

# 5. EARN - FUNDING - SPOT Account간 Transfer (먼저 잔고 확인)
# print("5. EARN - FUNDING - SPOT Account간 Transfer:")
# result = USDTmanager.transfer_accounts('USDT', 2.0, 'SPOT', 'FUNDING')
# if 'error' not in result:   
#     print(f"   성공적으로 이체되었습니다: {result['amount']:.2f} USDT")
#     print(f"   From: {result['from_account']} To: {result['to_account']}")
#     print(f"   Transfer ID: {result.get('transfer_id')}\n")
# else:
#     print(f"   에러: {result['error']}\n")

# # 6. Funding Account USDT를 Flexible Savings에 Subscribe
# print("6. Funding Account USDT를 Flexible Savings에 Subscribe:")    
# result = USDTmanager.subscribe_usdt_from_funding(amount='all')    
# if 'error' not in result:   
#     print(f"   성공적으로 예치되었습니다: {result['subscribed_amount']:.2f} USDT")
#     print(f"   Product ID: {result['product_id']}")
#     print(f"   Purchase ID: {result.get('purchase_id')}")
#     print(f"   남은 Funding 잔액: {result['remaining_funding_balance']:.2f} USDT\n")
# else:
#     print(f"   에러: {result['error']}\n")
#     # 특정 수량만 예치하는 경우
#     # result = USDTmanager.subscribe_usdt_from_funding(amount=10.0)