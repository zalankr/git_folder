from datetime import datetime
import time as time_module  # time 모듈을 별칭으로 import
import pyupbit

# 현재 시간 가져오기
now = datetime.now()
print(f"현재 시간: {now.strftime('%Y-%m-%d %H:%M:%S')}")

current_time = now.time()
print(f"현재 시간 (time 객체): {current_time}")

# 시간 비교 시 초 단위까지 정확히 매칭하기 어려우므로 시간 범위로 체크
current_hour = current_time.hour
current_minute = current_time.minute

if current_hour == 23 and current_minute == 58:  # 23:58
    TR_time = ["0858", 0]
elif current_hour == 0 and current_minute == 5:  # 00:05
    TR_time = ["0905", 1]
elif current_hour == 0 and current_minute == 12:  # 00:12
    TR_time = ["0912", 2]
elif current_hour == 0 and current_minute == 19:  # 00:19
    TR_time = ["0919", 3]
elif current_hour == 17 and 0 <= current_minute <= 59: 
    TR_time = ["anytime", 4]
else:
    TR_time = [None, None]

print("sleep(1)")
time_module.sleep(1)
print(TR_time)
print(pyupbit.get_current_price("KRW-ETH"))