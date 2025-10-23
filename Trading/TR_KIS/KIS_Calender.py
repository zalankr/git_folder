from datetime import datetime, timedelta, time as time_obj
import json

"""
crontab 설정
1. 25년~26년 1년치 월 첫 거래일 USAA(USLA+HAA) Rebalancing
*/5 9-21 1 11 * python3 /TR_KIS/KIS_Trading.py 일반 시간대 UTC 21시 정규장 종료 > 장종류 time.sleep하고 난 후주문 취소 체결확인 기록 등 시행 
*/5 8-20 1 4 * python3 /TR_KIS/KIS_Trading.py 서머타임 시간대 UTC 20시 정규장 종료 > 장종류 time.sleep하고 난 후주문 취소 체결확인 기록 등 시행 
2. 25년~26년 1년치 월 마지막 거래일 USAA(USLA+HAA) 'BIL'매도 후 USD CASH로 전환(이자수익용 BIL)
30 20 31 10 * python3 /TR_KIS/KIS_Trading.py 일반 시간대 UTC 21시 정규장 종료 > 장종류 time.sleep하고 난 후주문 취소 체결확인 기록 등 시행 
30 19 31 3 * python3 /TR_KIS/KIS_Trading.py 서머타임 시간대 UTC 20시 정규장 종료 > 장종류 time.sleep하고 난 후주문 취소 체결확인 기록 등 시행 
"""

# 현재 일자시간 확인(실제 구문에서는 심플하게, 로컬에서는 utcnow로)
def get_current():
    '''현재 UTC 날짜와 시간 정보를 딕셔너리로 반환'''
    current = datetime.utcnow() # now = datetime.now()
    current_date = current.date()
    current_time = current.time()
    now = {
        'date': current_date,
        'time': current_time,
        'year': current_date.year,
        'month': current_date.month,
        'day': current_date.day,
        'hour': current_time.hour,
        'minute': current_time.minute
    }
    return now

def check_USAA_rebalancing(current_date):
    '''오늘이 USAA 리밸런싱일인지 확인'''
    USAA_rebalancing_day_path = 'C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/USAA_rebalancing_day.json'

    try:
        with open(USAA_rebalancing_day_path, 'r', encoding='utf-8') as f:
            USAA_rebalancing_day = json.load(f)
    except Exception as e:
        print(f"JSON 파일 오류: {e}")

    if str(current_date) in USAA_rebalancing_day["summer_dst"] or str(current_date) in USAA_rebalancing_day["summer_dst"]:
        return "USAA_summer"
    elif str(current_date) in USAA_rebalancing_day["winter_standard"] or str(current_date) in USAA_rebalancing_day["winter_standard"]:
        return "USAA_winter"
    else:
        return "USAA_not_rebalancing"

def check_order_time():
    """USAA 리밸런싱일인지, 써머타임 시간대인지 그리고 장전, 장중거래 시간대인지, 거래회차는 몇회차인지 확인""" 
    # 현재 날짜와 시간 확인 ## AWS EC2 UTC시간대 사용
    # now = datetime.now()
    # current_date = now.date()
    # current_time = now.time()

    # test #
    current_date = datetime.strptime("2025-11-03", "%Y-%m-%d").date()
    current_time = datetime.strptime("09:01:00", "%H:%M:%S").time()
    # test #

    # USAA 리밸런싱일 확인
    check_USAA = check_USAA_rebalancing(current_date)
    # order_time 딕셔너리 생성: season, date, time, market, round, total_round, USAA리밸런싱일 확인
    order_time = dict()
    order_time['season'] = check_USAA
    order_time['date'] = current_date
    order_time['time'] = current_time

    if check_USAA == "USAA_winter":
        current = time_obj(current_time.hour, current_time.minute) # current_time
        Pre_market_start = time_obj(9, 0)   # 09:00
        Pre_market_end = time_obj(14, 30)   # 14:29
        Regular_start = time_obj(14, 30)   # 14:30
        Regular_end = time_obj(21, 5)      # 21:01
        
        if Pre_market_start <= current < Pre_market_end:
            order_time['market'] = "Pre-market"            
            order_time['round'] = 1 + (current.hour - 9) * 12 + (current.minute // 5)
            order_time['total_round'] = 66  # Pre-market 총 회차
            
        elif Regular_start <= current_time < Regular_end:
            order_time['market'] = "Regular"
            order_time['round'] = 1 + (current.hour - 14) * 12 + (current.minute // 5) - 6
            order_time['total_round'] = 79  # Regular 총 회차

    elif check_USAA == "USAA_summer":
        current = time_obj(current_time.hour, current_time.minute) # current_time
        Pre_market_start = time_obj(8, 0)   # 08:00
        Pre_market_end = time_obj(13, 30)   # 13:29
        Regular_start = time_obj(13, 30)   # 13:30
        Regular_end = time_obj(20, 5)      # 20:01

        if Pre_market_start <= current < Pre_market_end:
            order_time['market'] = "Pre-market"            
            order_time['round'] = 1 + (current.hour - 8) * 12 + (current.minute // 5)
            order_time['total_round'] = 66  # Pre-market 총 회차
            
        elif Regular_start <= current_time < Regular_end:
            order_time['market'] = "Regular"
            order_time['round'] = 1 + (current.hour - 13) * 12 + (current.minute // 5) - 6
            order_time['total_round'] = 79  # Regular 총 회차

    else:
        order_time['market'] = "No_trading"
        order_time['round'] = 0
        order_time['total_round'] = 0

    return order_time
    
# 서머타임(DST) 확인
def is_us_dst():
    """
    미국 동부 시간 기준 현재 서머타임(DST) 여부 확인
    
    미국 서머타임 규칙:
    - 시작: 3월 두 번째 일요일 02:00
    - 종료: 11월 첫 번째 일요일 02:00
    
    Returns:
    bool: 서머타임이면 True, 아니면 False
    """
    # 현재 UTC 시간 가져오기 (timezone-naive)
    now = datetime.now()
    
    # 미국 동부 시간 계산 (일단 EST 기준 UTC-5로 계산)
    us_eastern_time = now - timedelta(hours=5)
    year = us_eastern_time.year
    
    # 3월 두 번째 일요일 찾기
    march_first = datetime(year, 3, 1)
    days_to_sunday = (6 - march_first.weekday()) % 7
    first_sunday_march = march_first + timedelta(days=days_to_sunday)
    second_sunday_march = first_sunday_march + timedelta(days=7)
    dst_start = second_sunday_march.replace(hour=2, minute=0, second=0, microsecond=0)
    
    # 11월 첫 번째 일요일 찾기
    november_first = datetime(year, 11, 1)
    days_to_sunday = (6 - november_first.weekday()) % 7
    first_sunday_november = november_first + timedelta(days=days_to_sunday)
    dst_end = first_sunday_november.replace(hour=2, minute=0, second=0, microsecond=0)
    
    # 서머타임 기간 확인
    return dst_start <= us_eastern_time < dst_end
