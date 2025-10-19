import pyupbit
import time as time_module  # time 모듈을 별칭으로 import

# Upbit 토큰 불러오기
with open("/var/autobot/TR_Upbit/upnkr.txt") as f:
    access_key, secret_key = [line.strip() for line in f.readlines()]

# 업비트 접속, JSON data 경로 설정
upbit = pyupbit.Upbit(access_key, secret_key)

# 직전 회차 체결 주문 확인 함수
def check_filled_orders(upbit, ticker):
    """
    Args:
        upbit: Upbit 객체
        ticker: "KRW-ETH" 또는 "KRW-BTC"
    
    Returns:
        tuple: (사용된 총 KRW, 체결된 총 수량)
    """
    
    total_krw_used = 0.0
    total_volume_filled = 0.0
    
    try:
        # 체결 완료된 주문 조회
        filled_orders = upbit.get_order(ticker, state='done')
        for filled_order in filled_orders:
            executed_volume = float(filled_order.get('executed_volume', 0))
            avg_price = float(filled_order.get('avg_price', 0))
                
            # 매수 주문인 경우
            if filled_order['side'] == 'bid':
                paid_fee = float(filled_order.get('paid_fee', 0))
                krw_used = (executed_volume * avg_price) + paid_fee
                total_krw_used += krw_used
                total_volume_filled += executed_volume
        
        print(f"{ticker} 직전 회차 체결 요약: 사용 KRW {total_krw_used:.0f}원, "
              f"체결량 {total_volume_filled:.8f}개")
        
        return total_krw_used, total_volume_filled
    
    except Exception as e:
        print(f"{ticker} 체결 확인 중 오류: {e}")
        return 0.0, 0.0

# 양쪽 티커의 체결 확인을 한번에 처리하는 래퍼 함수
def check_all_filled_orders(upbit):
    """
    ETH와 BTC 모두의 체결된 주문을 확인
    
    Args: upbit: Upbit 객체
    
    Returns:
        dict: {
            'ETH_krw_used': float,
            'ETH_volume_filled': float,
            'BTC_krw_used': float,
            'BTC_volume_filled': float,
            'total_krw_used': float
        }
    """
    # ETH 체결 확인
    eth_krw, eth_volume = check_filled_orders(upbit, "KRW-ETH")
    
    # BTC 체결 확인
    btc_krw, btc_volume = check_filled_orders(upbit, "KRW-BTC")
    
    result = {
        'ETH_krw_used': eth_krw,
        'ETH_volume_filled': eth_volume,
        'BTC_krw_used': btc_krw,
        'BTC_volume_filled': btc_volume,
        'total_krw_used': eth_krw + btc_krw
    }
    
    return result

result = check_all_filled_orders(upbit)
print(result)