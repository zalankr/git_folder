import pyupbit
import myUpbit
from datetime import datetime, time
import json

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

# Ticker별 매수매도 시그널 만들기
def create_signals():
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

    return ETH20_signal, ETH40_signal, BTC45_signal

# Ticker별 투자 Weight 산출 함수
def get_Invest(ETH20_signal, ETH40_signal, BTC45_signal, ETH_balance, BTC_balance, KRW_balance):
    ETH_Invest = ["None"]
    BTC_Invest = ["None"]
    if ETH20_signal[1] == "Buy" :
        if ETH40_signal[1] == "Buy":
            if BTC45_signal[1] == "Buy":
                ETH_Invest = ["Buy", KRW_balance * 0.66] # KRW-ETH
                BTC_Invest = ["Buy", KRW_balance * 0.33] # KRW-BTC
            elif BTC45_signal[1] == "Cash":
                ETH_Invest = ["Buy", KRW_balance * 0.66] # KRW-ETH
            elif BTC45_signal[1] == "Sell":
                ETH_Invest = ["Buy", KRW_balance * 0.99] # KRW-ETH
                BTC_Invest = ["Sell", BTC_balance] # BTC-KRW
            elif BTC45_signal[1] == "Hold":
                ETH_Invest = ["Buy", KRW_balance * 0.99] # KRW-ETH
        elif ETH40_signal[1] == "Cash":
            if BTC45_signal[1] == "Buy":
                ETH_Invest = ["Buy", KRW_balance * 0.33] # KRW-ETH
                BTC_Invest = ["Buy", KRW_balance * 0.33] # KRW-BTC
            elif BTC45_signal[1] == "Cash":
                ETH_Invest = ["Buy", KRW_balance * 0.33] # KRW-ETH
            elif BTC45_signal[1] == "Sell":
                ETH_Invest = ["Buy", KRW_balance * 0.495] # ETH-KRW
                BTC_Invest = ["Sell", BTC_balance] # BTC-KRW
            elif BTC45_signal[1] == "Hold":
                ETH_Invest = ["Buy", KRW_balance * 0.495] # ETH-KRW
        elif ETH40_signal[1] == "Sell":
            if BTC45_signal[1] == "Buy":
                BTC_Invest = ["Buy", KRW_balance * 0.495] # KRW-BTC
            elif BTC45_signal[1] == "Cash":
                pass
            elif BTC45_signal[1] == "Sell":
                BTC_Invest = ["Sell", BTC_balance] # BTC-KRW
            elif BTC45_signal[1] == "Hold":
                pass
        elif ETH40_signal[1] == "Hold":
            if BTC45_signal[1] == "Buy":
                ETH_Invest = ["Buy", KRW_balance * 0.495] # KRW-ETH
                BTC_Invest = ["Buy", KRW_balance * 0.495] # KRW-BTC
            elif BTC45_signal[1] == "Cash":
                ETH_Invest = ["Buy", KRW_balance * 0.495] # KRW-ETH
            elif BTC45_signal[1] == "Sell":
                ETH_Invest = ["Buy", KRW_balance * 0.99] # KRW-ETH
                BTC_Invest = ["Sell", BTC_balance] # BTC-KRW
            elif BTC45_signal[1] == "Hold":
                ETH_Invest = ["Buy", KRW_balance * 0.99] # KRW-ETH
#######################################################################################
    if ETH20_signal[1] == "Cash" :
        if ETH40_signal[1] == "Buy":
            if BTC30_signal[1] == "Buy":
                ETH_Buying = KRW_balance * 0.33
                BTC_Buying = KRW_balance * 0.33
            elif BTC30_signal[1] == "Cash":
                ETH_Buying = KRW_balance * 0.33
                BTC_Buying = 0
            elif BTC30_signal[1] == "Sell":
                ETH_Buying = KRW_balance * 0.495
                BTC_Selling = BTC_balance
            elif BTC30_signal[1] == "Hold":
                ETH_Buying = KRW_balance * 0.495
                BTC_Buying = 0
        elif ETH40_signal[1] == "Cash":
            if BTC30_signal[1] == "Buy":
                ETH_Buying = 0
                BTC_Buying = KRW_balance * 0.33
            elif BTC30_signal[1] == "Cash":
                ETH_Buying = 0
                BTC_Buying = 0
            elif BTC30_signal[1] == "Sell":
                ETH_Buying = 0
                BTC_Selling = BTC_balance
            elif BTC30_signal[1] == "Hold":
                ETH_Buying = 0
                BTC_Buying = 0
        elif ETH40_signal[1] == "Sell":
            if BTC30_signal[1] == "Buy":
                ETH_Selling = ETH_balance
                BTC_Buying = KRW_balance * 0.495
            elif BTC30_signal[1] == "Cash":
                ETH_Selling = ETH_balance
                BTC_Buying = 0
            elif BTC30_signal[1] == "Sell":
                ETH_Selling = ETH_balance
                BTC_Selling = BTC_balance
            elif BTC30_signal[1] == "Hold":
                ETH_Selling = ETH_balance
                BTC_Buying = 0
        elif ETH40_signal[1] == "Hold":
            if BTC30_signal[1] == "Buy":
                ETH_Buying = 0
                BTC_Buying = KRW_balance * 0.495
            elif BTC30_signal[1] == "Cash":
                ETH_Buying = 0
                BTC_Buying = 0
            elif BTC30_signal[1] == "Sell":
                ETH_Buying = 0
                BTC_Selling = BTC_balance
            elif BTC30_signal[1] == "Hold":
                ETH_Buying = 0
                BTC_Buying = 0

    if ETH20_signal[1] == "Sell" :
        if ETH40_signal[1] == "Buy":
            if BTC30_signal[1] == "Buy":
                ETH_Buying = 0
                BTC_Buying = KRW_balance * 0.495
            elif BTC30_signal[1] == "Cash":
                ETH_Buying = 0
                BTC_Buying = 0
            elif BTC30_signal[1] == "Sell":
                ETH_Buying = 0
                BTC_Selling = BTC_balance
            elif BTC30_signal[1] == "Hold":
                ETH_Buying = 0
                BTC_Buying = 0
        elif ETH40_signal[1] == "Cash":
            if BTC30_signal[1] == "Buy":
                ETH_Selling = ETH_balance
                BTC_Buying = KRW_balance * 0.495
            elif BTC30_signal[1] == "Cash":
                ETH_Selling = ETH_balance
                BTC_Buying = 0
            elif BTC30_signal[1] == "Sell":
                ETH_Selling = ETH_balance
                BTC_Selling = BTC_balance
            elif BTC30_signal[1] == "Hold":
                ETH_Selling = ETH_balance
                BTC_Buying = 0
        elif ETH40_signal[1] == "Sell":
            if BTC30_signal[1] == "Buy":
                ETH_Selling = ETH_balance
                BTC_Buying = KRW_balance * 0.99
            elif BTC30_signal[1] == "Cash":
                ETH_Selling = ETH_balance
                BTC_Buying = 0
            elif BTC30_signal[1] == "Sell":
                ETH_Selling = ETH_balance
                BTC_Selling = BTC_balance
            elif BTC30_signal[1] == "Hold":
                ETH_Selling = ETH_balance
                BTC_Buying = 0
        elif ETH40_signal[1] == "Hold":
            if BTC30_signal[1] == "Buy":
                ETH_Selling = ETH_balance*0.5
                BTC_Buying = KRW_balance * 0.99
            elif BTC30_signal[1] == "Cash":
                ETH_Selling = ETH_balance*0.5
                BTC_Buying = 0
            elif BTC30_signal[1] == "Sell":
                ETH_Selling = ETH_balance*0.5
                BTC_Selling = BTC_balance
            elif BTC30_signal[1] == "Hold":
                ETH_Selling = ETH_balance*0.5
                BTC_Buying = 0

    if ETH20_signal[1] == "Hold" :
        if ETH40_signal[1] == "Buy":
            if BTC30_signal[1] == "Buy":
                ETH_Buying = KRW_balance * 0.495
                BTC_Buying = KRW_balance * 0.495
            elif BTC30_signal[1] == "Cash":
                ETH_Buying = KRW_balance * 0.495
                BTC_Buying = 0
            elif BTC30_signal[1] == "Sell":
                ETH_Buying = KRW_balance * 0.99
                BTC_Selling = BTC_balance
            elif BTC30_signal[1] == "Hold":
                ETH_Buying = KRW_balance * 0.99
                BTC_Buying = 0
        elif ETH40_signal[1] == "Cash":
            if BTC30_signal[1] == "Buy":
                ETH_Buying = 0
                BTC_Buying = KRW_balance * 0.495
            elif BTC30_signal[1] == "Cash":
                ETH_Buying = 0
                BTC_Buying = 0
            elif BTC30_signal[1] == "Sell":
                ETH_Buying = 0
                BTC_Selling = BTC_balance
            elif BTC30_signal[1] == "Hold":
                ETH_Buying = 0
                BTC_Buying = 0
        elif ETH40_signal[1] == "Sell":
            if BTC30_signal[1] == "Buy":
                ETH_Selling = ETH_balance*0.5
                BTC_Buying = KRW_balance * 0.99
            elif BTC30_signal[1] == "Cash":
                ETH_Selling = ETH_balance*0.5
                BTC_Buying = 0
            elif BTC30_signal[1] == "Sell":
                ETH_Selling = ETH_balance*0.5
                BTC_Selling = BTC_balance
            elif BTC30_signal[1] == "Hold":
                ETH_Selling = ETH_balance
                BTC_Buying = 0
        elif ETH40_signal[1] == "Hold":
            if BTC30_signal[1] == "Buy":
                ETH_Buying = 0
                BTC_Buying = KRW_balance * 0.99
            elif BTC30_signal[1] == "Cash":
                ETH_Buying = 0
                BTC_Buying = 0
            elif BTC30_signal[1] == "Sell":
                ETH_Buying = 0
                BTC_Selling = BTC_balance
            elif BTC30_signal[1] == "Hold":
                ETH_Buying = 0
                BTC_Buying = 0

    return(ETH_Invest, BTC_Invest, KRW_balance) # Buy값은 KRW로 sell값은 ETH와 BTC 량으로

# Ticker별 Weight 산출 > json저장


ETH20_signal = ["ETH20", "Buy"]
ETH40_signal = ["ETH40", "Cash"]
BTC30_signal = ["BTC30", "Buy"]

ETH_balance = 0
BTC_balance = 0
KRW_balance = 100
ETH_Buying = 0
ETH_Selling = 0
BTC_Buying = 0
BTC_Selling = 0

list = get_Invest(ETH20_signal, ETH40_signal, BTC30_signal, ETH_balance, BTC_balance, KRW_balance)
print("ETH_Buying:", list[0], "ETH_Selling:", list[1], "BTC_Buying:", list[2], "BTC_Selling:", list[3], "KRW_balance:", list[4])

#######################완성 후 삭제할 부분

# 8:55 TR_daily json읽기, Signal 계산, 투자 금액 산출, TRdata json저장
if TR_time[1] == 0:
    # 


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

