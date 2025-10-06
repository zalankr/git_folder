from datetime import datetime, timedelta

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
    utc_now = datetime.utcnow()
    
    # 미국 동부 시간 계산 (일단 EST 기준 UTC-5로 계산)
    us_eastern_time = utc_now - timedelta(hours=5)
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



# 서머타임(DST) 확인
is_dst = is_us_dst()
print("="*60)
print(is_dst)
print(f"현재 UTC 시간: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"서머타임(DST): {True if is_dst else False}")
