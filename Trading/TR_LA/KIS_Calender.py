from datetime import datetime, timedelta, time as time_obj
import json

# 현재 일자시간 확인(실제 구문에서는 심플하게, 로컬에서는 utcnow로)
def get_current():
    '''현재 UTC 날짜와 시간 정보를 딕셔너리로 반환'''
    current = datetime.now()
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

def check_USLA_rebalancing(current_date):
    '''오늘이 USLA 리밸런싱일인지 확인'''
    USLA_rebalancing_day_path = '/var/autobot/TR_USLA/USLA_rebalancing_day.json'
    
    try:
        with open(USLA_rebalancing_day_path, 'r', encoding='utf-8') as f:
            USLA_rebalancing_day = json.load(f)
    except Exception as e:
        print(f"JSON 파일 오류: {e}")
        # ✅ 추가: 안전하게 종료
        try:
            import kakao_alert as KA
            KA.SendMessage(f"USLA_rebalancing_day.json 로드 실패: {e}")
        except:
            pass
        return "USLA_not_rebalancing"

    if str(current_date) in USLA_rebalancing_day["summer_dst"]:
        return "USLA_summer"
    elif str(current_date) in USLA_rebalancing_day["winter_standard"]:
        return "USLA_winter"
    else:
        return "USLA_not_rebalancing"

def check_order_time():
    """USLA 리밸런싱일인지, 써머타임 시간대인지 그리고 장전, 장중거래 시간대인지, 거래회차는 몇회차인지 확인""" 
    # 현재 날짜와 시간 확인 UTC시간대
    now = datetime.now()
    current_date = now.date()
    current_time = now.time()

    # USLA 리밸런싱일 확인
    check_USLA = check_USLA_rebalancing(current_date)
    
    # ✅ 수정: 모든 키를 미리 초기화
    order_time = {
        'season': check_USLA,
        'date': current_date,
        'time': current_time,
        'round': 0,         # ✅ 기본값
        'total_round': 0    # ✅ 기본값
    }

    if check_USLA == "USLA_winter":
        current = time_obj(current_time.hour, current_time.minute)
        start = time_obj(9, 0)   # 09:00
        end = time_obj(21, 5)    # 21:05
        
        if start <= current < end:
            order_time['round'] = 1 + (current.hour - 9) * 2 + (current.minute // 30)
            order_time['total_round'] = 25

    elif check_USLA == "USLA_summer":
        current = time_obj(current_time.hour, current_time.minute)
        start = time_obj(8, 0)   # 08:00
        end = time_obj(20, 5)    # 20:05

        if start <= current < end:
            order_time['round'] = 1 + (current.hour - 8) * 2 + (current.minute // 30)
            order_time['total_round'] = 25

    # ✅ else 블록 제거 (이미 초기화됨)

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
