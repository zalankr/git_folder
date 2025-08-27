import pyupbit
import json
import time as time_module  # time 모듈을 별칭으로 import
import UP_signal_weight as SW

import pandas as pd # 삭제해도 이상 없을 시 삭제
from datetime import datetime

# Upbit 토큰 불러오기
with open("C:/Users/ilpus/Desktop/NKL_invest/upnkr.txt") as f: # Home경로
# with open("C:/Users/GSR/Desktop/Python_project/upnkr.txt") as f: # Company경로
    access_key, secret_key = [line.strip() for line in f.readlines()]

# 업비트 접속
upbit = pyupbit.Upbit(access_key, secret_key)

# 시간확인 조건문 8:55 > daily파일 불러와 Signal산출 후 매매 후 TR기록 json생성, 9:05/9:15/9:25> 트레이딩 후 TR기록 9:30 > 트레이딩 후 
now, current_time, TR_time = SW.what_time()
print(f"현재 시간: {now.strftime('%Y-%m-%d %H:%M:%S')}, TR_time: {TR_time}")

# If 8:58 Trading 5분할 (0회차) 시 TR_daily json읽기, Signal계산, 투자 금액 산출 (try로 감싸기) 후 주문 취소, 5분할 매매
if TR_time[1] == 5: # 5분할 매매로 5가 정답 0은 테스트 용
    # 기존 주문 모두 취소
    print(SW.CancelCoinOrder(upbit)) # 기존 모든 주문 취소 함수(모듈) 프린트 벗기기
    time_module.sleep(1) # 타임 슬립 1초

    # 잔고 확인
    ETH = upbit.get_balance("ETH")
    KRW = upbit.get_balance("KRW")

    # 포지션 확인 및 투자 수량 산출
    position = SW.make_position(ETH, KRW)

    # Upbit_data 만들고 저장하기
    Upbit_data = {
        "date": {
            "record day": now.strftime('%Y-%m-%d')
        },
        "position": {
            "position": position["position"],
            "ETH_weight": position["ETH_weight"],
            "ETH_target": position["ETH_target"],
            "CASH_weight": position["CASH_weight"],
            "Invest_Quantity": position["Invest_Quantity"],
            "ETH_balance": ETH,
            "KRW_balance": KRW
        }
    }

    with open('C:/Users/ilpus/Desktop/git_folder/Trading/CR_TR_Upbit/Upbit_data.json', 'w', encoding='utf-8') as f:
        json.dump(Upbit_data, f, ensure_ascii=False, indent=4)
    time_module.sleep(1)

# 당일의 Upbit_data.json 파일 불러오고 position 추출 try로 감싸기
with open('C:/Users/ilpus/Desktop/git_folder/Trading/CR_TR_Upbit/Upbit_data.json', 'r', encoding='utf-8') as f:
    Upbit_data = json.load(f)
position = Upbit_data["position"]

# 포지션별 주문하기> 완료 후 try로 감싸기
if position["position"] == "Hold state":
    print("Hold State - No Action")

elif position["position"] == "Sell full" and position["position"] == "Sell half":
    current_price = pyupbit.get_current_price("KRW-ETH")
    amount_per_times = round(position["Invest_Quantity"] / TR_time[1], 8) # 분할 매매 횟수당 ETH Quantity

    if amount_per_times * current_price < 5100: # ETH투자량을 KRW로 환산한 후 분할 매매당 금액이 5100원 미만일 때 pass
        pass
    else: # 분할 매매당 금액이 5100원 이상일 때만 매도 주문 실행
        SW.partial_selling(current_price, amount_per_times, TR_time, upbit)


elif position["position"] == "Buy full" and position["position"] == "Buy half":
    current_price = pyupbit.get_current_price("KRW-ETH")
    amount_per_times = round(position["Invest_Quantity"] / TR_time[1]) # 분할 매매 횟수당 ETH Quantity

    if amount_per_times < 5100: # KRW로 분할 매매당 금액이 5100원 미만일 때 pass
        pass
    else: # 분할 매매당 금액이 5100원 이상일 때만 매수 주문 실행
        SW.partial_buying(current_price, amount_per_times, TR_time, upbit)

time_module.sleep(1) # 타임 슬립1초

# 기록 시 체결 주문내역과 수익률 월, 일, 연 기록 try로 감싸기

        

# 마지막에 Upbit_Trading.json파일 생성, 카카오톡 보내기, 스프레드시트 기록하기


#### 마지막에 crontab에서 5분후 자동종료 되게 설정