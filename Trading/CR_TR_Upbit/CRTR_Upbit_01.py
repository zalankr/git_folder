import pyupbit
import myUpbit
from datetime import datetime, time
import json
import Investweight as IW

# ohlcv와 MA를 가져오는 함수
def get_data(ticker, interval, period):
    data = pyupbit.get_ohlcv(ticker=ticker, interval=interval)
    MA = myUpbit.GetMA(data, period, -1)
    return data, MA

# Signal 체크 함수
def check_signal(position, data, MA):
    if position == True:
        if data["close"].iloc[-1] >= MA:
            return [True, "Hold"]
        else:
            return [False, "Sell"]

    else:
        if data["close"].iloc[-1] >= MA:
            return [True, "Buy"]
        else:
            return [False, "Cash"]

# 시간확인 조건문 8:55 > daily파일 불러와 Signal산출 후 매매 후 TR기록 json생성, 9:05/9:15/9:25> 트레이딩 후 TR기록 9:30 > 트레이딩 후 
# 현재 시간 불러오기(AWS엔 UTC +0로 산출됨, 그에 맞게 시간 체크)
def what_time():
    # 현재 시간 가져오기
    now = datetime.now()
    current_time = now.time()

    # if time(23, 55) <= current_time <= time(23, 59, 59): # 23:55 ~ 24:00 사이인지 확인 
    if time(0, 55) <= current_time <= time(23, 59, 59): # 23:55 ~ 24:00 사이인지 확인
        TR_time = ["0855", 0]
    elif time(0, 5) <= current_time <= time(0, 9, 59):  # 00:05 ~ 00:10 사이인지 확인
        TR_time = ["0905", 1]
    elif time(0, 15) <= current_time <= time(0, 19, 59):  # 00:15 ~ 00:20 사이인지 확인
        TR_time = ["0915", 2]
    elif time(0, 25) <= current_time <= time(0, 29, 59):  # 00:25 ~ 00:30 사이인지 확인
        TR_time = ["0925", 3]
    elif time(0, 30) <= current_time <= time(23, 34, 59):  # 00:30 ~ 00:35 사이인지 확인
        TR_time = ["0930", 4]
    
    return now, current_time, TR_time 
    
now, current_time, TR_time = what_time() 
print(f"현재 시간: {now.strftime('%Y-%m-%d %H:%M:%S')}, TR_time: {TR_time}")

# Upbit 토큰 불러오기
with open("C:/Users/ilpus/Desktop/NKL_invest/upnkr.txt") as f:
# with open("C:/Users/GSR/Desktop/Python_project/upnkr.txt") as f:
    access_key, secret_key = [line.strip() for line in f.readlines()]

# 업비트 접속
upbit = pyupbit.Upbit(access_key, secret_key)

# 8:55 TR_daily json읽기, Signal 계산, 투자 금액 산출, TRdata json저장
if TR_time[1] == 0:
    # daily record JSON 파일에서 읽기
    Upbit_daily_path = 'C:/Users/ilpus/Desktop/git_folder/Trading/CR_TR_Upbit/Upbit_daily.json'
    try:
        with open(Upbit_daily_path, 'r', encoding='utf-8') as f:
            Upbit_daily = json.load(f)
    except Exception as e:
        print("Exception File")

    print(Upbit_daily)

    # Ticker별 현재가와 MA 비교 8:55
    ## ETH 20MA
    position = Upbit_daily["ETH20"]["position"]
    data, MA = get_data(ticker = "KRW-ETH", interval = "day", period=20)
    ETH20_signal = check_signal(position, data, MA)

    ## ETH 40MA
    position = Upbit_daily["ETH40"]["position"]
    data, MA = get_data(ticker = "KRW-ETH", interval = "day", period=40)
    ETH40_signal = check_signal(position, data, MA)

    ## BTC 45MA
    position = Upbit_daily["BTC45"]["position"]
    data, MA = get_data(ticker = "KRW-BTC", interval = "day", period=45)
    BTC45_signal = check_signal(position, data, MA)

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


