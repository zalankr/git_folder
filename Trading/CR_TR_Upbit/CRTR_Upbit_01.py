import pyupbit
import json
import time as time_module  # time 모듈을 별칭으로 import
import UP_signal_weight as SW

import pandas as pd # 삭제해도 이상 없을 시 삭제
import myUpbit # 삭제해도 이상 없을 시 삭제
from datetime import datetime

# Upbit 토큰 불러오기
with open("C:/Users/ilpus/Desktop/NKL_invest/upnkr.txt") as f: # Home경로
# with open("C:/Users/GSR/Desktop/Python_project/upnkr.txt") as f: # Company경로
    access_key, secret_key = [line.strip() for line in f.readlines()]

# 업비트 접속
upbit = pyupbit.Upbit(access_key, secret_key)

# 거래 Ticker
Ticker = "KRW-ETH"

# 시간확인 조건문 8:55 > daily파일 불러와 Signal산출 후 매매 후 TR기록 json생성, 9:05/9:15/9:25> 트레이딩 후 TR기록 9:30 > 트레이딩 후 
now, current_time, TR_time = SW.what_time()
print(f"현재 시간: {now.strftime('%Y-%m-%d %H:%M:%S')}, TR_time: {TR_time}")

# If 8:58 Trading 5분할 (0회차) 시 TR_daily json읽기, Signal계산, 투자 금액 산출 (try로 감싸기) 후 주문 취소, 5분할 매매
if TR_time[1] == 5:
    ETH_balance = upbit.get_balance("ETH")
    KRW_balance = upbit.get_balance("KRW")
    ETH20_signal, ETH40_signal = SW.generate_signal()
    ETH_Invest = SW.get_Invest(ETH20_signal, ETH40_signal, ETH_balance, KRW_balance) # 모델별 투자신호, 투자금액 산출

    time_module.sleep(1) # 타임 슬립1초   
    SW.CancelCoinOrder(upbit, Ticker) # 기존 모든 주문 취소 함수(모듈)

    # 조건별 주문 하기 (모듈로)
    if ETH_Invest[0] == "Buy": # 매수 신호
        amount_per_times = (ETH_Invest[1] / TR_time[1]) # 분할 매매 횟수당 KRW Quantity
        print("분할 매매 횟수:", TR_time[1], "분할 매매 금액:", amount_per_times) # 완성 후 삭제
        current_price = pyupbit.get_current_price("KRW-ETH") # 이더리움 가격
        # TR 분할 매매 가격 계산 & tick size에 맞춰 가격 조정
        prices = []
        for i in range(TR_time[1]):
            price = (current_price * (1 - (i * 0.002))) # 가격을 0.2%씩 낮추는 분할 매매 가격 계산
            prices.append(SW.get_tick_size(price = price,  method="floor"))
        ## if문으로 TR_time[1]이 3미만이면 주문을 +2%(유사 시장가)주문으로 대체
        if TR_time[1] < 3:
            prices[0] = [SW.get_tick_size(price = current_price*1.02,  method="floor")]




    time_module.sleep(1) # 타임 슬립1초

        









# 제일 마지막에 Upbit_Trading.json파일 생성


#### 마지막에 try exception 구문과 crontab에서 5분후 자동종료 되게 설정