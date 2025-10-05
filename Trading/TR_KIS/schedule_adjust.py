import datetime
import schedule
import time

def calculate_remaining_time(target_hour, target_minute):
    """목표 시간까지 남은 시간을 계산"""
    now = datetime.datetime.now()
    target_time = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    
    # 목표 시간이 이미 지났다면 다음 날로 설정
    if target_time <= now:
        target_time += datetime.timedelta(days=1)
    
    remaining = target_time - now
    hours, remainder = divmod(remaining.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    print(f"현재 시간: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"목표 시간: {target_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"남은 시간: {hours}시간 {minutes}분 {seconds}초")
    
    return remaining

def main_task():
    """정해진 시간에 실행될 작업"""
    print("\n=== 예약된 작업 실행 ===")
    print(f"실행 시간: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 여기에 실행하고 싶은 코드를 작성하세요
    print("작업 1: 데이터 처리 중...")
    print("작업 2: 파일 저장 중...")
    print("작업 3: 완료!")
    print("======================\n")

# 목표 시간 설정 (22:30)
TARGET_HOUR = 22
TARGET_MINUTE = 30

# 현재 시간과 남은 시간 계산
calculate_remaining_time(TARGET_HOUR, TARGET_MINUTE)

# 매일 22:30에 실행되도록 스케줄 설정
schedule.every().day.at(f"{TARGET_HOUR:02d}:{TARGET_MINUTE:02d}").do(main_task)

print(f"\n스케줄러가 시작되었습니다. 매일 {TARGET_HOUR:02d}:{TARGET_MINUTE:02d}에 작업이 실행됩니다.")
print("프로그램을 종료하려면 Ctrl+C를 누르세요.\n")

# 스케줄러 실행
try:
    while True:
        schedule.run_pending()
        time.sleep(1)
except KeyboardInterrupt:
    print("\n프로그램이 종료되었습니다.")

