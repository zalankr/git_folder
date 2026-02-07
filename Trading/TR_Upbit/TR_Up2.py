import pyupbit
import json
import sys
import time as time_module  # time 모듈을 별칭으로 import
import Up2_model as UP
import kakao_alert as KA
import gspread_updater as GU
from tendo import singleton
me = singleton.SingleInstance()

# 필요한 라이브러리 설치: pip install gspread google-auth

# Upbit 토큰 불러오기
with open("/var/autobot/TR_Upbit/upnkr.txt") as f:
    access_key, secret_key = [line.strip() for line in f.readlines()]

# 업비트 접속, JSON data 경로 설정
upbit = pyupbit.Upbit(access_key, secret_key)
TR_data_path = '/var/autobot/TR_Upbit/TR_data2.json'

# 시간확인 조건문
now, current_time, TR_time = UP.what_time()
message = []

# If 8:58 Trading 8분할(첫 번째)에만 전일 Upbit_data json읽고 Signal계산, 투자 금액 산출 후 다시 저장
try:
    if TR_time[1] == 8: # 8:58 8분할 매매시에만 실행
        # 포지션 확인 및 투자 수량 산출 ####
        try:
            with open(TR_data_path, 'r', encoding='utf-8') as f:
                TR_data = json.load(f)
        except FileNotFoundError:
            TR_data = {}  # 파일이 없으면 빈 딕셔너리 생성

        # Upbit 당일 전략 데이터 만들기
        TR_data, UPmessage = UP.make_position(upbit)
        message.extend(UPmessage)
        UPmessage = []  # 메시지 초기화
        
        # Upbit_data.json파일 생성 후 알림
        with open(TR_data_path, 'w', encoding='utf-8') as f:
            json.dump(TR_data, f, ensure_ascii=False, indent=4)
        message.append(f"Upbit Trading, {TR_time[0]} Upbit trade 당일 전략 data 생성완료")
    else:
        pass

except Exception as e:
    message.append(f"Upbit {TR_time[0]} \nUpbit trade 당일 전략 생성 시 예외 오류: {e}")

time_module.sleep(1) # 타임슬립 1초

# 회차별매매 주문하기
try:
    if TR_time[1] in range(1, 9): # 8분할매매 주문 실행(0은 제외)
        # 기존 주문 모두 취소
        result = UP.Cancel_Order(upbit) # 기존 모든 주문 취소 함수(모듈)
        if result:  # 리스트가 비어있지 않으면 True
            uuids = "\n".join([r.get("uuid", "uuid 없음") for r in result])
            message.append(f"Upbit {TR_time[0]}, \n{TR_time[1]}회차 분할매매, \n주문 취소 목록:\n{uuids}")
        else:
            message.append(f"Upbit {TR_time[0]}, \n{TR_time[1]}회차 분할매매, \n취소할 주문이 없습니다.")
        time_module.sleep(1) # 타임 슬립 1초

        # 당일의 TR_data2.json 파일 불러오기     
        try:
            with open(TR_data_path, 'r', encoding='utf-8') as f:
                TR_data = json.load(f)
        except Exception as e:
            message.append(f"Upbit {TR_time[0]} JSON 파일 오류: {e}")
            sys.exit(1) # 오류와 함께 종료

        # 변수지정
        ETH_Position = TR_data.get("ETH_Position", "Hold_state")
        BTC_Position = TR_data.get("BTC_Position", "Hold_state")
        Last_ETH_weight = TR_data.get("Last_ETH_weight", 0.0)
        Last_BTC_weight = TR_data.get("Last_BTC_weight", 0.0)
        ETH_weight = TR_data.get("ETH_weight", 0.0)
        BTC_weight = TR_data.get("BTC_weight", 0.0)
        ETH_price = pyupbit.get_current_price("KRW-ETH") 
        BTC_price = pyupbit.get_current_price("KRW-BTC")
        ETH_result = None
        BTC_result = None

        # ETH 포지션별 주문하기 ticker인수 넣기              
        if ETH_Position == "Sell_full":
            ETH = upbit.get_balance_t("ETH")
            if ETH > 0:  # 매도할 물량이 있을 때만
                amount_per_times = ETH / TR_time[1] # 분할 매매 횟수당 ETH Quantity
                ticker = "KRW-ETH"
                ETH_result, Upmessage = UP.partial_selling(ticker, ETH_price, amount_per_times, TR_time, upbit) 
                message.extend(Upmessage)
                Upmessage = []  # 메시지 초기화
            else:
                message.append(f"Upbit {TR_time[0]} ETH Sell_full: 보유량 0")

        elif ETH_Position == "Sell_half":
            ETH = upbit.get_balance_t("ETH")
            ETH_target = TR_data["ETH_target"]
            SellETH = max(0, ETH - ETH_target)

            if SellETH > 0:  # 매도할 물량이 있을 때만
                amount_per_times = SellETH / TR_time[1] # 분할 매매 횟수당 ETH Quantity
                ticker = "KRW-ETH"
                ETH_result, Upmessage = UP.partial_selling(ticker, ETH_price, amount_per_times, TR_time, upbit)
                message.extend(Upmessage)
                Upmessage = []  # 메시지 초기화
            else:
                message.append(f"Upbit {TR_time[0]} ETH Sell_half: 매도할 수량 없음 (보유: {ETH:.8f}, 목표: {ETH_target:.8f})")
        
        elif ETH_Position == "Buy_full" or ETH_Position == "Buy_half":
            KRWETH_buy = TR_data["KRWETH_buy"]
            result, Upmessage = UP.check_all_filled_orders_last_hour(upbit)
            message.extend(Upmessage)
            Upmessage = [] # 메시지 초기화
            KRWETH_used = result["KRWETH_used"]
            Remain_buy = max(0, KRWETH_buy - KRWETH_used)

            if Remain_buy > 5500: # 5500원 이상만 매매
                krw_per_times = (Remain_buy * 0.99) / TR_time[1] # 분할 매매 횟수당 ETH Quantity, 안정성 있게 현금의 99%만 매매
                ticker = "KRW-ETH"
                ETH_result, Upmessage = UP.partial_buying(ticker, ETH_price, krw_per_times, TR_time, upbit) # amount가 ETH로 교체
                message.extend(Upmessage)
                Upmessage = []  # 메시지 초기화
            else:
                message.append(f"Upbit {TR_time[0]} ETH Buy: 매수 가능 금액 부족 (남은 금액: {Remain_buy:.0f}원)")

        elif ETH_Position == "Hold_state":
            message.append(f"Upbit {TR_time[0]} ETH Hold_state: 주문 없음")

        else:
            message.append(f"Upbit {TR_time[0]} 예상치 못한 ETH_Position: {ETH_Position}")
    
        # BTC 포지션별 주문하기 ticker인수 넣기             
        if BTC_Position == "Sell_full":
            BTC = upbit.get_balance_t("BTC")
            if BTC > 0:
                amount_per_times = BTC / TR_time[1] # 분할 매매 횟수당 BTC Quantity
                ticker = "KRW-BTC"
                BTC_result, Upmessage = UP.partial_selling(ticker, BTC_price, amount_per_times, TR_time, upbit)
                message.extend(Upmessage)
                Upmessage = []  # 메시지 초기화
            else:
                message.append(f"Upbit {TR_time[0]} BTC Sell_full: 매도할 BTC 없음 (보유: {BTC:.8f})")

        elif BTC_Position == "Sell_half":
            BTC = upbit.get_balance_t("BTC")
            BTC_target = TR_data["BTC_target"]
            SellBTC = max(0, BTC - BTC_target)

            if SellBTC > 0:  # 매도할 물량이 있을 때만
                amount_per_times = SellBTC / TR_time[1] # 분할 매매 횟수당 BTC Quantity
                ticker = "KRW-BTC"
                BTC_result, Upmessage = UP.partial_selling(ticker, BTC_price, amount_per_times, TR_time, upbit)
                message.extend(Upmessage)
                Upmessage = []  # 메시지 초기화
            else:
                message.append(f"Upbit {TR_time[0]} BTC Sell_half: 매도할 수량 없음 (보유: {BTC:.8f}, 목표: {BTC_target:.8f})")
        
        elif BTC_Position == "Buy_full" or BTC_Position == "Buy_half":
            KRWBTC_buy = TR_data["KRWBTC_buy"]
            result, Upmessage = UP.check_all_filled_orders_last_hour(upbit)
            message.extend(Upmessage)
            Upmessage = [] # 메시지 초기화
            KRWBTC_used = result["KRWBTC_used"]
            Remain_buy = max(0, KRWBTC_buy - KRWBTC_used)

            if Remain_buy > 5500: # 5500원 이상만 매매
                krw_per_times = (Remain_buy * 0.99) / TR_time[1] # 분할 매매 횟수당 BTC Quantity, 안정성 있게 현금의 99%만 매매
                ticker = "KRW-BTC"
                BTC_result, Upmessage = UP.partial_buying(ticker, BTC_price, krw_per_times, TR_time, upbit) # amount가 BTC로 교체
                message.extend(Upmessage)
                Upmessage = []  # 메시지 초기화
            else:
                message.append(f"Upbit {TR_time[0]} BTC Buy: 매수 가능 금액 부족 (남은 금액: {Remain_buy:.0f}원)")

        elif BTC_Position == "Hold_state":
            message.append(f"Upbit {TR_time[0]} BTC Hold_state: 주문 없음")

        else:
            message.append(f"Upbit {TR_time[0]} 예상치 못한 BTC_Position: {BTC_Position}")

except Exception as e:
        message.append(f"Upbit {TR_time[0]} \n주문하기 중 예외 오류: {e}")

time_module.sleep(1) # 타임슬립 1초

# 마지막 주문 후 수익률 계산하기(년, 월, 일) JSON 기록 카톡 알림, gspread sheet 기록 try로 감싸기
try:
    if TR_time[1] == 1:
        message = []  # 메시지 초기화
        time_module.sleep(10) # 타임슬립 10초

        result = UP.Cancel_Order(upbit) # 기존 모든 주문 취소 함수(모듈)
        if result:  # 리스트가 비어있지 않으면 True
            uuids = "\n".join([r.get("uuid", "uuid 없음") for r in result])
            message.append(f"Upbit {TR_time[0]}, \n트레이딩 종료 취소주문, \n주문 취소 목록:\n{uuids}")
        else:
            message.append(f"Upbit {TR_time[0]}, \n트레이딩 종료 취소주문, \n취소할 주문이 없습니다.")
        time_module.sleep(1) # 타임 슬립 1초

        # 당일종료 원화환산 토탈잔고, KRW잔고, ETH잔고
        KRW, ETH, BTC, Total = UP.Total_balance(upbit)

        # 전일 ETH/KRW/원화환산 잔고, 전월말, 전년말 원화환산 잔고
        Last_day_balance = TR_data["Last_day_balance"]
        Last_month_balance = TR_data["Last_month_balance"]
        Last_year_balance = TR_data["Last_year_balance"]

        # 일, 월, 연 수익률 #
        Daily_return = (Total - Last_day_balance) / Last_day_balance * 100
        Daily_return = float("{:.2f}".format(Daily_return))
        Monthly_return = (Total - Last_month_balance) / Last_month_balance * 100
        Monthly_return = float("{:.2f}".format(Monthly_return))
        Yearly_return = (Total - Last_year_balance) / Last_year_balance * 100
        Yearly_return = float("{:.2f}".format(Yearly_return))

        # 월초, 연초 전월말, 전년말 잔고 업데이트
        if now.day == 1: # 월초 전월 잔고 데이터 변경
            Last_month_balance = Last_day_balance
            message.append(f"월초, 전월 잔고를 {Last_month_balance}원으로 업데이트했습니다.")
        else:
            pass

        if now.month == 1 and now.day == 1: # 연초 전년 잔고 데이터 변경
            Last_year_balance = Last_day_balance
            message.append(f"연초, 전년 잔고를 {Last_year_balance}원으로 업데이트했습니다.")
        else:
            pass
        
        Last_day_balance = Total

        # Upbit_data 만들기
        TR_data_today = {
            "Date": str(now.date()),
            "ETH": ETH,
            "BTC": BTC,
            "KRW": KRW,
            "ETH_Position": ETH_Position,
            "BTC_Position": BTC_Position,
            "Last_ETH_weight": Last_ETH_weight,
            "Last_BTC_weight": Last_BTC_weight,
            "ETH_weight": ETH_weight,
            "BTC_weight": BTC_weight,
            "ETH_target": TR_data["ETH_target"],
            "BTC_target": TR_data["BTC_target"],
            "ETHKRW_sell": TR_data["ETHKRW_sell"],
            "BTCKRW_sell": TR_data["BTCKRW_sell"],
            "KRWETH_buy": TR_data["KRWETH_buy"],
            "KRWBTC_buy": TR_data["KRWBTC_buy"],
            "ETHKRW_balance": ETH * ETH_price * 0.9995,
            "BTCKRW_balance": BTC * BTC_price * 0.9995,
            "KRW_balance": KRW,
            "Total_balance": Total,
            "Last_day_balance": Last_day_balance,
            "Last_month_balance": Last_month_balance,
            "Last_year_balance": Last_year_balance,
            "Daily_return": Daily_return,
            "Monthly_return": Monthly_return,
            "Yearly_return": Yearly_return
        }

        # TR_data2.json파일 생성
        TR_data = TR_data_today
        with open(TR_data_path, 'w', encoding='utf-8') as f:
            json.dump(TR_data, f, ensure_ascii=False, indent=4)

        # KakaoTalk 메시지 보내기
        ETH_target = TR_data["ETH_target"]
        BTC_target = TR_data["BTC_target"]
        message.append(f"Upbit {now.strftime('%Y-%m-%d %H:%M:%S')} \n당일 트레이딩 완료")
        message.append(f"Upbit 일수익률: {Daily_return}% \n월수익률: {Monthly_return}% \n연수익률: {Yearly_return}% \n환산잔고: {round(Total):,}원 \nETH: {ETH:,}, BTC: {BTC:,} \nKRW: {(round(KRW)):,}원")
        message.append(f"Upbit ETH Position: {ETH_Position} \nETH weight: {ETH_weight} \nETH target: {ETH_target}")
        message.append(f"Upbit BTC Position: {BTC_Position} \nBTC_weight: {BTC_weight} \nBTC_target: {BTC_target}")

        # Google Spreadsheet에 데이터 추가
        # 설정값 (실제 값으로 변경 필요)
        credentials_file = "/var/autobot/gspread/service_account.json" # 구글 서비스 계정 JSON 파일 경로
        spreadsheet_name = "2026_TR_Upbit" # 스프레드시트 이름
        
        # 구글 스프레드시트 연결
        spreadsheet = GU.connect_google_sheets(credentials_file, spreadsheet_name)
        
        # 현재 월 계산
        current_month = now.month
        
        # 데이터 저장
        GU.save_to_sheets(spreadsheet,TR_data, current_month)
    else:
        pass

except Exception as e:
    message.append(f"Upbit {TR_time[0]} 당일 data 기록 중 예외 오류: {e}")

#### 검증 > 마지막에 crontab에서 5분 후 자동종료 되게 설정
if TR_time[1] == 0:
    print(f"Upbit {now.strftime('%Y-%m-%d')} 트레이딩 프로그램 운용시간이 아닙니다. 프로그램을 종료합니다.")
    message.append(f"Upbit {now.strftime('%Y-%m-%d')} 트레이딩 프로그램 운용시간이 아닙니다. 프로그램을 종료합니다.")

KA.SendMessage("\n".join(message))
message = []  # 메시지 초기화
sys.exit()