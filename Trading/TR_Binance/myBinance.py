#-*-coding:utf-8 -*-
# Binance 서버 시간과 동기화  > 윈도우 우하단 일자 우클릭 후 날짜와 시간 설정창으로 들어가서 시간 지금 동기화

import ccxt
import time
import pandas as pd
import pprint
import numpy
from datetime import datetime
import time as time_module  # time 모듈을 별칭으로 import

#이동평균선 수치를 구해준다 첫번째: 분봉/일봉 정보, 두번째: 기간, 세번째: 기준 날짜
def GetMA(ohlcv,period,st):
    close = ohlcv["close"]
    ma = close.rolling(period).mean()
    return float(ma.iloc[st])

# 시간확인 조건문 함수: 8:55 > daily파일 불러와 Signal산출 후 매매 후 TR기록 json생성, 9:05/9:15/9:25> 트레이딩 후 TR기록 9:30 > 트레이딩 후 
def what_time():
    # 현재 시간 가져오기
    now = datetime.now()
    current_time = now.time()

    current_hour = current_time.hour
    current_minute = current_time.minute

    # 시간 비교 시 초 단위까지 정확히 매칭하기 어려우므로 시간 범위로 체크
    if current_hour == 23 and 57 < current_minute <= 59:  # 23:58
        TR_time = ["0858", 5] # 시간, 분할 횟수
    elif current_hour == 0 and 4 < current_minute <= 6:  # 00:05
        TR_time = ["0905", 4] # 시간, 분할 횟수
    elif current_hour == 0 and 11 < current_minute <= 13:  # 00:12
        TR_time = ["0912", 3] # 시간, 분할 횟수
    elif current_hour == 0 and 18 < current_minute <= 20:  # 00:19
        TR_time = ["0919", 2] # 시간, 분할 횟수
    elif current_hour == 0 and 25 < current_minute <= 30:  # 00:26
        TR_time = ["0926", 1]
    else:
        TR_time = [None, 0]
    
    return now, current_time, TR_time
