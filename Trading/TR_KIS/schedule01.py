import schedule
import time

count = {"n": 0}  # 전역 변수 대신 딕셔너리로 카운트 관리

def job():
    count["n"] += 1
    print("Hello")
    if count["n"] >= 5:   # 5번째 출력 시
        return schedule.CancelJob  # 스케줄 job 해제

# 1초 간격 실행
schedule.every(1).seconds.do(job)

while True:
    schedule.run_pending()
    if count["n"] >= 5:   # 5번 출력되면 while 탈출
        break
    time.sleep(1)

print("while 루프 종료 후 코드 실행")

