import json
import UP_signal_weight as UP
import time as time_module
import pyupbit

# Upbit 토큰 불러오기
with open("C:/Users/ilpus/Desktop/NKL_invest/upnkr.txt") as f: # Home경로
# with open("C:/Users/GSR/Desktop/Python_project/upnkr.txt") as f: # Company경로
    access_key, secret_key = [line.strip() for line in f.readlines()]

# 업비트 접속
upbit = pyupbit.Upbit(access_key, secret_key)

with open('C:/Users/ilpus/Desktop/git_folder/Trading/TR_Upbit/Upbit_data.json', 'r', encoding='utf-8') as f:
    Upbit_data = json.load(f)
position = Upbit_data["position"]

now, current_time, TR_time = UP.what_time()

# 어제종료 원화환산 토탈잔고, KRW잔고, ETH잔고
balance = Upbit_data["balance"]
last_Total_balance = balance["Total_balance"]
last_KRW = balance["KRW"]
last_ETH = balance["ETH"]

# 전월말, 전년말 원화환산 토탈 잔고
Historical_data = Upbit_data["Historical_data"]
last_month_Total_balance = Historical_data["last_month_Total_balance"]
last_year_Total_balance = Historical_data["last_year_Total_balance"]

# 당일종료 원화환산 토탈잔고, KRW잔고, ETH잔고
KRW, ETH, Total_balance = UP.Total_balance(upbit)

# 일, 월, 연 수익률
daily_return = (ETH - last_ETH) / last_ETH * 100
montly_return = (Total_balance - last_month_Total_balance) / last_month_Total_balance * 100
yearly_return = (Total_balance - last_year_Total_balance) / last_year_Total_balance * 100

time_module.sleep(0.5) # 타임슬립 0.5초
print()
print(f"{now.strftime('%Y-%m-%d')} {TR_time[0]} 당일 트레이딩 완료")
print()
print(f"일간 수익률: {daily_return:.2f}% \n월간 수익률: {montly_return:.2f}% \n연간 수익률: {yearly_return:.2f}%")
print()
print(f"원화환산 잔고: {Total_balance:,}원 \nETH: {ETH:,}원 \nKRW: {KRW:,}원")
print()
print(f"position: {position['position']} \nTH_weight: {position['ETH_weight']} \nETH_target: {position['ETH_target']} \nCASH_weight: {position['CASH_weight']}")
print()