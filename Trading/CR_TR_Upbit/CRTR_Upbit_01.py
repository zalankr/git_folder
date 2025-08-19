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

# If 8:58 Trading 0회차 시 TR_daily json읽기, Signal계산, 투자 금액 산출 (try로 감싸기) 후 주문 취소, 필요 시 4분할 매매
if TR_time[1] == None:
    ETH_balance = upbit.get_balance("ETH")
    KRW_balance = upbit.get_balance("KRW")
    ETH20_signal, ETH40_signal = SW.generate_signal()
    ETH_Invest = SW.get_Invest(ETH20_signal, ETH40_signal, ETH_balance, KRW_balance) # 모델별 투자신호, 투자금액 산출

    print("ETH20_signal:", ETH20_signal, "ETH40_signal:", ETH40_signal) # 완성 후 삭제
    print("ETH_balance:", ETH_balance, "KRW_balance:", KRW_balance) # 완성 후 삭제
    print("ETH_Invest:", ETH_Invest) # 완성 후 삭제

    time_module.sleep(1) # 타임 슬립1초   
    SW.CancelCoinOrder(upbit, Ticker) # 기존 모든 주문 취소 함수(모듈)

    time_module.sleep(1) # 타임 슬립1초
    # 조건별 주문 하기 (모듈로)

    if ETH_Invest[0] == "Buy":
        amount_per_times = (ETH_Invest[1] / TR_time[1]) # 분할 매매 횟수당 KRW Quantity
        current_price = pyupbit.get_current_price("KRW-ETH") # 이더리움 가격
        # TR 분할 매매 가격 계산
        prices = [current_price * (1 - i) for i in range(4)]
        orders = []


    # TR json저장

# elif 시간 체크 > 기존 주문 확인 (체결 수도 확인) 후 남은 주문취소 > 해당 횟차 주문 분할(min 5000원 if로 상향시킬 것)
## 투자금액 분할 후 주문 > json기록 
else:
    pass


# 기존 주문 확인 후 있으면 일괄 취소
# TR json불러오기
# 타임에서 시간확인하고 분할 횟수 생성
## 분할에 맞춰 투자금액을 분할
## 공통 변수
amount_per_times = (ETH_Invest[1] / 5)

if ETH_Invest[0] == "Buy":

    amount_per_times = (ETH_Invest[1] / 5)
    current_price = pyupbit.get_current_price("ETH")
    prices = [current_price * (i + 1) for i in range(5)]
    orders = []
## 분할에 맞춰 틱사이즈에 맞는 가격 계산 (모듈)
## 주문 실행 + UUID 저장

elif ETH_Invest[0] == "Sell":
    pass

else:
    pass

orders = []
order_record = [TR_time[1], ETH_Invest, ETH_balance, KRW_balance, ETH20_signal, ETH40_signal, orders]

# 제일 마지막에 Upbit_Trading.json파일 생성
"""
def generate_Upbit_Trading_json(order_record):

    Upbit_Trading = {
        "TR_number": {"number": 0, "splits": 5},
        "signal": {"ETH20_signal": ETH20_signal, "ETH40_signal": ETH40_signal},
        "balance": {"ETH": ETH_balance, "KRW": KRW_balance},
        "trading": {"action": ETH_Invest[0], "amount": ETH_Invest[1], "ETH20" : ETH_Invest[2], "ETH40" : ETH_Invest[3]},
        "orders": {"UUID_0": None, "UUID_1": None, "UUID_2": None, "UUID_3": None, "UUID_4": None, "Fin_TR": 0}
    }
"""


#### 마지막에 try exception 구문과 crontab에서 5분후 자동종료 되게 설정
"""
# 8:55 TR_daily json읽기, Signal 계산, 투자 금액 산출, TRdata json저장
    # Upbit_TR data 만들기
    Upbit_TR = {
        "TR": {"times": 0, "TR_count": 5},
        "ETH20": {"position": ETH20_signal[0], "action": ETH20_signal[1], "UUID_0": None, "UUID_1": None, "UUID_2": None, "UUID_3": None, "UUID_4": None, "Fin_TR": 0},
        "ETH40": {"position": ETH40_signal[0], "action": ETH40_signal[1], "UUID_0": None, "UUID_1": None, "UUID_2": None, "UUID_3": None, "UUID_4": None, "Fin_TR": 0},
        "BTC45": {"position": BTC45_signal[0], "action": BTC45_signal[1], "UUID_0": None, "UUID_1": None, "UUID_2": None, "UUID_3": None, "UUID_4": None, "Fin_TR": 0},
    }

    # Upbit_TR JSON 파일 쓰기
    Upbit_TR_path = 'C:/Users/ilpus/Desktop/git_folder/Trading/CR_TR_Upbit/Upbit_TR.json'
    try:
        with open(Upbit_TR_path, 'w', encoding='utf-8') as f:
            json.dump(Upbit_TR, f, ensure_ascii=False, indent=4)

    except Exception as e:
        print("Exception File")

# Upbit_TR JSON 불러오기
Upbit_TR_path = 'C:/Users/ilpus/Desktop/git_folder/Trading/CR_TR_Upbit/Upbit_TR.json'
try:
    with open(Upbit_TR_path, 'r', encoding='utf-8') as f:
        Upbit_TR = json.load(f)
except Exception as e:
    print("Exception File")

print(Upbit_TR)

# Trading Action


# Balance 체크
## 전체금액
balances = upbit.get_balances()
## Ticker별 balance
ETH_balance = upbit.get_balance("ETH")
BTC_balance = upbit.get_balance("BTC")
KRW_balance = upbit.get_balance("KRW")
print("ETH_balance:", ETH_balance)
print("BTC_balance:", BTC_balance)
print("KRW_balance:", KRW_balance)

# Ticker별 Invest 금액 산정
Invest_Amount = IW.get_Invest(ETH20_signal, ETH40_signal, BTC45_signal, ETH_balance, BTC_balance, KRW_balance)

print("-" * 30)
print("ETH_Buying:", Invest_Amount[0]) # KRW Quantity
print("ETH_Selling:", Invest_Amount[1]) # ETH Quantity
print("BTC_Buying:", Invest_Amount[2]) # KRW Quantity
print("BTC_Selling:", Invest_Amount[3]) # BTC Quantity
print("KRW_balance:", Invest_Amount[4]) # KRW Quantity

## 체결내역 확인
# filled_orders = upbit.get_filled_orders()
# print("체결내역:", filled_orders)

# Cancel_Orders = []

# 

# # Ticker별 Trading Action 및 투자금 산정
# ## Ticker별 Balance 확인
# ETH_Remain = upbit.get_balance("ETH")
# BTC_Remain = upbit.get_balance("BTC")
# KRW_Remain = upbit.get_balance("KRW")
# Total_Balance = myUpbit.GetTotalRealMoney(balances)

# print("ETH_Remain:", ETH_Remain)
# print("BTC_Remain:", BTC_Remain)
# print("KRW_Remain:", KRW_Remain)
# print("Total_Balance:", Total_Balance)
"""

