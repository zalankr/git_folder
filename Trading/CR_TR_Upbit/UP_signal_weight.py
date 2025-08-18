import pyupbit
import pandas as pd
import numpy
from datetime import datetime, time
import json

#이동평균선 수치, 첫번째: 분봉/일봉 정보, 두번째: 기간, 세번째: 기준 날짜
def getMA(ohlcv,period,st):
    close = ohlcv["close"]
    ma = close.rolling(period).mean()
    return float(ma.iloc[st])

# 어제 포지션을 오늘 포지션으로 변경 함수
def remake_position(data, period, position):
    MA = getMA(data, period, -1)
    if position == "ETH": # ETH or CASH
        if data["close"].iloc[-1] >= MA:
            signal = "Hold"
            return signal
        else:
            signal = "Sell"
            return signal
    else:
        if data["close"].iloc[-1] >= MA:
            signal = "Buy"
            return signal
        else:
            signal = "Cash"
            return signal

# 매수매도 시그널 생성 함수
def generate_signal():
    # 어제의 포지션, 밸런스 json값 불러오기
    # Upbit_daily_path = 'C:/Users/ilpus/Desktop/git_folder/Trading/CR_TR_Upbit/Upbit_daily.json' # Home경로
    Upbit_daily_path = 'C:/Users/GSR/Desktop/Python_project/git_folder/Trading/CR_TR_Upbit/Upbit_daily.json' # Company경로
    try:
        with open(Upbit_daily_path, 'r', encoding='utf-8') as f:
            Upbit_daily = json.load(f)
    except Exception as e:
        print("Exception File")

    # ETH 가격자료 불러오기
    data = pyupbit.get_ohlcv(ticker="KRW-ETH", interval="day")

    ## ETH 20MA
    position = Upbit_daily["ETH20"]["position"]
    ETH20_signal = remake_position(data, 20, position)

    ## ETH 40MA
    position = Upbit_daily["ETH40"]["position"]
    ETH40_signal = remake_position(data, 40, position)

    return ETH20_signal, ETH40_signal

# Ticker별 투자 Weight 산출 함수
def get_Invest(ETH20_signal, ETH40_signal, ETH_balance, KRW_balance):
    ETH20_signal, ETH40_signal = generate_signal()
    ETH_Invest = list()
    if ETH20_signal == "Buy" :
        if ETH40_signal == "Buy":
            ETH_Invest = ["Buy", KRW_balance * 0.99, "ETH", "ETH"] #2 ETH20, 3 ETH40
        elif ETH40_signal == "Cash":
            ETH_Invest = ["Buy", KRW_balance * 0.495, "ETH", "Cash"] #2 ETH20, 3 ETH40
        elif ETH40_signal == "Sell":
            ETH_Invest = ["None", 0, "ETH", "Cash"] #2 ETH20, 3 ETH40
        elif ETH40_signal == "Hold":
            ETH_Invest = ["Buy", KRW_balance * 0.99, "ETH", "ETH"] #2 ETH20, 3 ETH40
    if ETH20_signal == "Cash" :
        if ETH40_signal == "Buy":
            ETH_Invest = ["Buy", KRW_balance * 0.495, "Cash", "ETH"] #2 ETH20, 3 ETH40
        elif ETH40_signal == "Cash":
            ETH_Invest = ["None", 0, "Cash", "Cash"] #2 ETH20, 3 ETH40
        elif ETH40_signal == "Sell":
            ETH_Invest = ["Sell", ETH_balance, "Cash", "Cash"] #2 ETH20, 3 ETH40
        elif ETH40_signal == "Hold":
            ETH_Invest = ["None", 0, "Cash", "ETH"] #2 ETH20, 3 ETH40
    if ETH20_signal == "Sell" :
        if ETH40_signal == "Buy":
            ETH_Invest = ["None", 0, "Cash", "ETH"] #2 ETH20, 3 ETH40
        elif ETH40_signal == "Cash":
            ETH_Invest = ["Sell", ETH_balance, "Cash", "Cash"] #2 ETH20, 3 ETH40
        elif ETH40_signal == "Sell":
            ETH_Invest = ["Sell", ETH_balance, "Cash", "Cash"] #2 ETH20, 3 ETH40
        elif ETH40_signal == "Hold":
            ETH_Invest = ["Sell", ETH_balance*0.5, "Cash", "ETH"] #2 ETH20, 3 ETH40
    if ETH20_signal == "Hold" :
        if ETH40_signal == "Buy":
            ETH_Invest = ["Buy", KRW_balance * 0.99, "ETH", "ETH"] #2 ETH20, 3 ETH40
        elif ETH40_signal == "Cash":
            ETH_Invest = ["None", 0, "ETH", "Cash"] #2 ETH20, 3 ETH40
        elif ETH40_signal == "Sell":
            ETH_Invest = ["Sell", ETH_balance*0.5, "ETH", "Cash"] #2 ETH20, 3 ETH40
        elif ETH40_signal == "Hold":
            ETH_Invest = ["None", 0, "ETH", "ETH"] #2 ETH20, 3 ETH40

    return ETH_Invest # Buy값은 KRW로 sell값은 ETH량으로 sample["Buy", KRW_balance * 0.99, "ETH", "ETH"]

# 시간확인 조건문 함수: 8:55 > daily파일 불러와 Signal산출 후 매매 후 TR기록 json생성, 9:05/9:15/9:25> 트레이딩 후 TR기록 9:30 > 트레이딩 후 
def what_time():
    # 현재 시간 가져오기
    now = datetime.now()
    current_time = now.time()

    # if time(23, 55) <= current_time <= time(23, 59, 59): # 23:55 ~ 24:00 사이인지 확인 정식버전으로 바꿀때는 이코드로 
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
    