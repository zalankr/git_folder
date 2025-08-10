from datetime import datetime, time

# 현재 시간 체크(AWS엔 UTC 0로 산출됨, 그에 맞게 시간 체크)
now = datetime.now()
current_time = now.time()

print(f"현재 시간: {now.strftime('%Y-%m-%d %H:%M:%S')}")


# start_time = time(23, 55)  # 23:55
# end_time = time(23, 59, 59)  # 23:59:59




####################################################################

# from datetime import datetime, time

# now = datetime.now()
# current_time = now.time()
# start_time = time(23, 55)  # 23:55
# end_time = time(23, 59, 59)  # 23:59:59

# is_in_range = start_time <= current_time <= end_time

#################################################################3

# from datetime import datetime

# # 현재 시간 구하기
# now = datetime.now()
# print(f"현재 시간: {now.strftime('%Y-%m-%d %H:%M:%S')}")

# # 현재 시간이 23:55 ~ 24:00(자정) 사이인지 확인
# current_hour = now.hour
# current_minute = now.minute

# # 23시 55분에서 24시(자정) 사이인지 확인
# is_in_range = current_hour == 23 and current_minute >= 55

# if is_in_range:
#     print("현재 시간이 23:55 ~ 24:00 사이입니다.")
# else:
#     print("현재 시간이 23:55 ~ 24:00 사이가 아닙니다.")

# # 더 구체적인 정보 출력
# print(f"현재 시각: {current_hour:02d}:{current_minute:02d}")
# print(f"조건 확인 결과: {is_in_range}")

# # 함수로 만든 버전
# def is_late_night():
#     """현재 시간이 23:55 ~ 24:00 사이인지 확인하는 함수"""
#     now = datetime.now()
#     return now.hour == 23 and now.minute >= 55

# # 함수 사용 예제
# if is_late_night():
#     print("늦은 밤 시간대입니다!")
# else:
#     print("늦은 밤 시간대가 아닙니다.")