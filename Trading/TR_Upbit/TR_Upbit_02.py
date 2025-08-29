import pyupbit
import json
import time as time_module  # time 모듈을 별칭으로 import
import UP_signal_weight as UP
import kakao_alert as KA
import pandas as PD

# Upbit 토큰 불러오기
with open("C:/Users/ilpus/Desktop/NKL_invest/upnkr.txt") as f: # Home경로
# with open("C:/Users/GSR/Desktop/Python_project/upnkr.txt") as f: # Company경로
    access_key, secret_key = [line.strip() for line in f.readlines()]

# 업비트 접속
upbit = pyupbit.Upbit(access_key, secret_key)

# 시간확인 조건문
now, current_time, TR_time = UP.what_time()
print(f"현재 시간: {now.strftime('%Y-%m-%d %H:%M:%S')}, TR_time: {TR_time}")

# If 8:58 Trading 5분할 (0회차)때에만 전일 TR_data json읽고 Signal계산, 투자 금액 산출 후 저장
try:
    if TR_time[1] == 5: # 5분할 매매로 5인 경우만
        # 기존 주문 모두 취소
        print(UP.CancelCoinOrder(upbit)) # 기존 모든 주문 취소 함수(모듈) 프린트 벗기기
        time_module.sleep(1) # 타임 슬립 1초

        # 잔고 확인
        ETH = upbit.get_balance("ETH")
        KRW = upbit.get_balance("KRW")

        # 포지션 확인 및 투자 수량 산출
        position, Total_balance, last_month_Total_balance, last_year_Total_balance = UP.make_position(ETH, KRW)


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
                "Invest_quantity": position["Invest_quantity"]
            },
            "balance": {
                "Total_balance": Total_balance,
                "ETH": ETH,
                "KRW": KRW
            },
            "Historical_data": {
                "last_month_Total_balance": last_month_Total_balance,
                "last_year_Total_balance": last_year_Total_balance
            }
        }

        with open('C:/Users/ilpus/Desktop/git_folder/Trading/CR_TR_Upbit/Upbit_data.json', 'w', encoding='utf-8') as f:
            json.dump(Upbit_data, f, ensure_ascii=False, indent=4)
        time_module.sleep(1)

except Exception as e:
        print(f"8:55 당일 포지션/잔고 생성 시 예외의 오류: {e}")
        KA.SendMessage(f"8:55 포지션/잔고 생성 시 예외의 오류: {e}")


# 회차별 매매 주문하기 try로 감싸기
try:
    if TR_time[1] in [5, 4, 3, 2, 1]: # 5,4,3,2,1분할 매매로 5,4,3,2,1인 경우만
        # 당일의 Upbit_data.json 파일 불러오고 position 추출
        with open('C:/Users/ilpus/Desktop/git_folder/Trading/CR_TR_Upbit/Upbit_data.json', 'r', encoding='utf-8') as f:
            Upbit_data = json.load(f)
        position = Upbit_data["position"]

        # 포지션별 주문하기
        if position["position"] == "Hold state":
            print("Hold State - No Action")

        elif position["position"] == "Sell full" and position["position"] == "Sell half":
            current_price = pyupbit.get_current_price("KRW-ETH")
            amount_per_times = round(position["Invest_quantity"] / TR_time[1], 8) # 분할 매매 횟수당 ETH Quantity
            if amount_per_times * current_price < 5100: # ETH투자량을 KRW로 환산한 후 분할 매매당 금액이 5100원 미만일 때 pass
                pass
            else: # 분할 매매당 금액이 5100원 이상일 때만 매도 주문 실행
                UP.partial_selling(current_price, amount_per_times, TR_time, upbit)


        elif position["position"] == "Buy full" and position["position"] == "Buy half":
            current_price = pyupbit.get_current_price("KRW-ETH")
            amount_per_times = round(position["Invest_quantity"] / TR_time[1]) # 분할 매매 횟수당 ETH Quantity
            if amount_per_times < 5100: # KRW로 분할 매매당 금액이 5100원 미만일 때 pass
                pass
            else: # 분할 매매당 금액이 5100원 이상일 때만 매수 주문 실행
                UP.partial_buying(current_price, amount_per_times, TR_time, upbit)
    
    else:
         pass

except Exception as e:
        print(f"{TR_time[0]} 주문하기 중 예외의 오류: {e}")
        KA.SendMessage(f"{TR_time[0]} 주문하기 중 예외의 오류: {e}")

time_module.sleep(1) # 타임 슬립1초

# 수익률 계산하기 월, 일, 연 기록 try로 감싸기
if TR_time[1] == 1:
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
    daily_return = (position["ETH_balance"] - position["Invest_quantity"]) / position["Invest_quantity"] * 100
    montly_return = (position["ETH_balance"] - position["Invest_quantity"]) / position["Invest_quantity"] * 100
    yearly_return = (position["ETH_balance"] - position["Invest_quantity"]) / position["Invest_quantity"] * 100



# 기록 시 과 수익률 월, 일, 연 기록 try로 감싸기
# Upbit_data 만들기
Upbit_data = {
    "date": {
        "record day": now.strftime('%Y-%m-%d')
    },
    "position": {
        "position": position["position"],
        "ETH_weight": position["ETH_weight"],
        "ETH_target": position["ETH_target"],
        "CASH_weight": position["CASH_weight"],
        "Invest_quantity": position["Invest_quantity"],
        "Total_balance": 0,
        "ETH_balance": ETH,
        "KRW_balance": KRW
    },
    "return": {
         
    }
}
        

# 마지막에 Upbit_Trading.json파일 생성, 카카오톡 보내기, 스프레드시트 기록하기


#### 마지막에 crontab에서 5분 후 자동종료 되게 설정
exit()