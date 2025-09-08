import ccxt
import json

# API 키 불러오기
with open("C:/Users/ilpus/Desktop/NKL_invest/bnnkr.txt") as f:
    access, secret = [line.strip() for line in f.readlines()]

# Binance 현물거래 객체 생성
BinanceX = ccxt.binance({
    "apiKey": access,
    "secret": secret,
    "enableRateLimit": True,
    "options": {"defaultType": "spot"}
})

def get_earn_account_usdt():
    total_earn_usdt = 0
    
    try:
        # 1. Flexible Savings (Simple Earn Flexible) USDT 조회
        try:
            flexible_position = BinanceX.sapi_get_simple_earn_flexible_position({
                'asset': 'USDT'
            })
            flexible_usdt = 0
            for position in flexible_position.get('rows', []):
                if position['asset'] == 'USDT':
                    flexible_usdt += float(position['totalAmount'])
            
            print(f"Simple Earn Flexible USDT: {flexible_usdt}")
            total_earn_usdt += flexible_usdt
            
        except Exception as e:
            print(f"Flexible Savings 조회 실패: {e}")
        
        # 2. Locked Savings (Simple Earn Locked) USDT 조회
        try:
            locked_position = BinanceX.sapi_get_simple_earn_locked_position({
                'asset': 'USDT'
            })
            locked_usdt = 0
            for position in locked_position.get('rows', []):
                if position['asset'] == 'USDT':
                    locked_usdt += float(position['amount'])
            
            print(f"Simple Earn Locked USDT: {locked_usdt}")
            total_earn_usdt += locked_usdt
            
        except Exception as e:
            print(f"Locked Savings 조회 실패: {e}")
        
        # 3. DeFi Staking USDT 조회
        try:
            defi_position = BinanceX.sapi_get_staking_position({
                'product': 'STAKING',
                'asset': 'USDT'
            })
            defi_usdt = 0
            for position in defi_position:
                if position['asset'] == 'USDT':
                    defi_usdt += float(position['amount'])
            
            print(f"DeFi Staking USDT: {defi_usdt}")
            total_earn_usdt += defi_usdt
            
        except Exception as e:
            print(f"DeFi Staking 조회 실패: {e}")
        
        # 4. ETH 2.0 Staking USDT 조회 (참고용)
        try:
            eth_staking = BinanceX.sapi_get_staking_position({
                'product': 'ETH_STAKING'
            })
            print(f"ETH 2.0 Staking 정보: {len(eth_staking)} 항목")
            
        except Exception as e:
            print(f"ETH Staking 조회 실패: {e}")
        
        # 5. Auto-Invest 조회
        try:
            auto_invest = BinanceX.sapi_get_lending_auto_invest_target_asset_list({})
            print(f"Auto-Invest 정보 조회 완료")
            
        except Exception as e:
            print(f"Auto-Invest 조회 실패: {e}")
        
        # 6. 전체 Earn 계정 요약 (가능한 경우)
        try:
            # 모든 Earn 상품의 위치 조회
            all_positions = BinanceX.sapi_get_asset_getfundingasset({})
            funding_earn_usdt = 0
            
            for asset in all_positions:
                if asset['asset'] == 'USDT':
                    funding_earn_usdt = float(asset['free']) + float(asset['freeze'])
                    break
            
            print(f"Funding Account USDT: {funding_earn_usdt}")
            
        except Exception as e:
            print(f"Funding Account 조회 실패: {e}")
        
        return total_earn_usdt
        
    except Exception as e:
        print(f"전체 조회 중 오류 발생: {e}")
        return 0

# 실행
if __name__ == "__main__":
    print("=== Binance Earn Account USDT 조회 ===\n")
    
    # 기본 계정 정보
    try:
        account_info = BinanceX.fetch_balance()
        spot_usdt = account_info['total'].get('USDT', 0)
        print(f"Spot Account USDT: {spot_usdt}")
        print("-" * 40)
    except Exception as e:
        print(f"Spot 계정 조회 실패: {e}")
    
    # Earn Account 조회
    total_earn = get_earn_account_usdt()
    
    print("-" * 40)
    print(f"총 Earn Account USDT: {total_earn}")
    print(f"전체 USDT (Spot + Earn): {spot_usdt + total_earn}")