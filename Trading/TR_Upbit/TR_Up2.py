import pyupbit
import json
import time as time_module  # time 모듈을 별칭으로 import
import Up2_model as UP
import kakao_alert as KA
import gspread_updater as GU
from tendo import singleton
me = singleton.SingleInstance()

# 필요한 라이브러리 설치: pip install gspread google-auth
# crontab 수정 추가 3회

# Upbit 토큰 불러오기
with open("/var/autobot/TR_Upbit/upnkr.txt") as f:
    access_key, secret_key = [line.strip() for line in f.readlines()]

# 업비트 접속, JSON data 경로 설정
upbit = pyupbit.Upbit(access_key, secret_key)
Upbit_data_path = '/var/autobot/TR_Upbit/Upbit2_data.json'

# 시간확인 조건문
now, current_time, TR_time = UP.what_time()
TR_time = ["0858", 8] ## test

# If 8:58 Trading 8분할(첫 번째)에만 전일 Upbit_data json읽고 Signal계산, 투자 금액 산출 후 다시 저장
try:
    if TR_time[1] == 8: # 8:58 8분할 매매시에만 실행
        # 잔고 확인
        KRW, ETH, BTC, Total_balance = UP.Total_balance(upbit)
        # 포지션 확인 및 투자 수량 산출
        ETH, BTC, Account = UP.make_position(ETH, BTC, KRW)

        # Upbit_data 만들고 저장하기
        Upbit2_data = {
             "Date": now.strftime("%Y-%m-%d"),
             "ETH": ETH,
             "BTC": BTC,
             "Account": Account
        }

        # Upbit_data.json파일 생성 후 알림
        with open(Upbit_data_path, 'w', encoding='utf-8') as f:
            json.dump(Upbit2_data, f, ensure_ascii=False, indent=4)
        KA.SendMessage(f"Upbit Trading, {TR_time[0]}\n \nETH: {ETH} \n \nBTC: {BTC}")

except Exception as e:
        print(f"Upbit {TR_time[0]} \n포지션 생성 시 예외 오류: {e}")
        KA.SendMessage(f"Upbit {TR_time[0]} \n포지션 생성 시 예외 오류: {e}")
time_module.sleep(1) # 타임슬립 1초

# 회차별매매 주문하기
try:
    if TR_time[1] in [8, 7, 6, 5, 4, 3, 2, 1]: # 8,7,6,5,4,3,2,1 분할매매 주문 실행(0은 제외)
        # 기존 주문 모두 취소
        result = UP.Cancel_Order(upbit) # 기존 모든 주문 취소 함수(모듈)
        if result:  # 리스트가 비어있지 않으면 True
            uuids = "\n".join([r.get("uuid", "uuid 없음") for r in result])
            KA.SendMessage(f"Upbit {TR_time[0]}, \n{TR_time[1]}회차 분할매매, \n주문 취소 목록:\n{uuids}")
        else:
            KA.SendMessage(f"Upbit {TR_time[0]}, \n{TR_time[1]}회차 분할매매, \n취소할 주문이 없습니다.")
        time_module.sleep(1) # 타임 슬립 1초

        # 당일의 Upbit_data.json 파일 불러오고 position 추출       
        try:
            with open(Upbit_data_path, 'r', encoding='utf-8') as f:
                Upbit2_data = json.load(f)

            ETH = Upbit2_data["ETH"]
            BTC = Upbit2_data["BTC"]

            ETH_Position = ETH["Position"]
            BTC_Position = BTC["Position"]
            ETH_sell_qty= ETH["ETH_sell_qty"]
            ETH_KRW_buy_qty= ETH["KRW_buy_qty"]
            BTC_sell_qty= BTC["BTC_sell_qty"]
            BTC_KRW_buy_qty= BTC["KRW_buy_qty"]
            
        except Exception as e:
            print(f"JSON 파일 오류: {e}")
            KA.SendMessage(f"Upbit {TR_time[0]} JSON 파일 오류: {e}")
            exit()
          
        # 포지션별 주문하기##############################################################################################################
        if ETH_Position == "Sell_full":
            current_price = pyupbit.get_current_price("KRW-ETH")
            ETH = upbit.get_balance_t("ETH")
            amount_per_times = ETH / TR_time[1] # 분할 매매 횟수당 ETH Quantity

            if amount_per_times * current_price < 6000: # ETH투자량을 KRW로 환산한 후 분할 매매당 금액이 6000원 미만일 때 pass
                pass
            else: # 분할 매매당 금액이 6000원 이상일 때만 매도 주문
                UP.partial_selling(current_price, amount_per_times, TR_time, upbit) 

#         elif Position == "Sell half":
#             current_price = pyupbit.get_current_price("KRW-ETH")    
#             ETH = upbit.get_balance_t("ETH")
#             Remain_ETH = max(0, ETH - Invest_quantity)
#             amount_per_times = Remain_ETH / TR_time[1] # 분할 매매 횟수당 ETH Quantity
            
#             if amount_per_times * current_price < 6000: # ETH투자량을 KRW로 환산한 후 분할 매매당 금액이 6000원 미만일 때 pass
#                 pass
#             else: # 분할 매매당 금액이 6000원 이상일 때만 매도 주문
#                 UP.partial_selling(current_price, amount_per_times, TR_time, upbit)
        
#         elif Position == "Buy full":
#             current_price = pyupbit.get_current_price("KRW-ETH")
#             KRW = upbit.get_balance_t("KRW")
#             amount_per_times = KRW / TR_time[1] # 분할 매매 횟수당 KRW Quantity

#             if amount_per_times < 6000: # KRW로 분할 매매당 금액이 6000원 미만일 때 pass
#                 pass
#             else: # 분할 매매당 금액이 6000원 이상일 때만 매수 주문
#                 UP.partial_buying(current_price, amount_per_times, TR_time, upbit)

#         elif Position == "Buy half":
#             current_price = pyupbit.get_current_price("KRW-ETH")
#             KRW = upbit.get_balance_t("KRW")
#             Remain_KRW = max(0, KRW - Invest_quantity)

#             amount_per_times = Remain_KRW / TR_time[1] # 분할 매매 횟수당 KRW Quantity

#             if amount_per_times < 6000: # KRW로 분할 매매당 금액이 6000원 미만일 때 pass
#                 pass
#             else: # 분할 매매당 금액이 6000원 이상일 때만 매수 주문
#                 UP.partial_buying(current_price, amount_per_times, TR_time, upbit)
    
#     else:
#          pass

except Exception as e:
        print(f"Upbit {TR_time[0]} \n주문하기 중 예외 오류: {e}")
        KA.SendMessage(f"Upbit {TR_time[0]} \n주문하기 중 예외 오류: {e}")
time_module.sleep(1) # 타임슬립 1초

# # 마지막 주문 후 수익률 계산하기(년, 월, 일) JSON 기록 카톡 알림, gspread sheet 기록 try로 감싸기
# try:
#     if TR_time[1] == 1:
#         result = UP.Cancel_ETH_Order(upbit) # 기존 모든 주문 취소 함수(모듈)
#         if result:  # 리스트가 비어있지 않으면 True
#             uuids = "\n".join([r.get("uuid", "uuid 없음") for r in result])
#             KA.SendMessage(f"Upbit {TR_time[0]}, \n트레이딩 종료 취소주문, \n주문 취소 목록:\n{uuids}")
#         else:
#             KA.SendMessage(f"Upbit {TR_time[0]}, \n트레이딩 종료 취소주문, \n취소할 주문이 없습니다.")
#         time_module.sleep(1) # 타임 슬립 1초

#         # 당일의 Upbit_data.json 파일 불러오고 position, 어제종료 원화환산 토탈잔고, KRW잔고, ETH잔고 추출
#         with open(Upbit_data_path, 'r', encoding='utf-8') as f:
#             Upbit_data = json.load(f)

#         # 전일 ETH/KRW/원화환산 잔고, 전월말, 전년말 원화환산 잔고
#         Last_day_Total_balance = Upbit_data["Last_day_Total_balance"]
#         Last_month_Total_balance = Upbit_data["Last_month_Total_balance"]
#         Last_year_Total_balance = Upbit_data["Last_year_Total_balance"]

#         # 당일종료 원화환산 토탈잔고, KRW잔고, ETH잔고
#         KRW, ETH, Total_balance = UP.Total_balance(upbit)

#         # 일, 월, 연 수익률
#         Daily_return = (Total_balance - Last_day_Total_balance) / Last_day_Total_balance * 100
#         Monthly_return = (Total_balance - Last_month_Total_balance) / Last_month_Total_balance * 100
#         Yearly_return = (Total_balance - Last_year_Total_balance) / Last_year_Total_balance * 100

#         time_module.sleep(0.5) # 타임슬립 0.5초

#         # 월초, 연초 전월말, 전년말 잔고 업데이트
#         if now.day == 1: # 월초 전월 잔고 데이터 변경
#             Last_month_Total_balance = Last_day_Total_balance
#             print(f"월초, 전월 잔고를 {Last_month_Total_balance}원으로 업데이트했습니다.")
#         else:
#             pass

#         if now.month == 1 and now.day == 1: # 연초 전년 잔고 데이터 변경
#             Last_year_Total_balance = Last_day_Total_balance
#             print(f"연초, 전년 잔고를 {Last_year_Total_balance}원으로 업데이트했습니다.")
#         else:
#             pass

#         # Upbit_data 만들기
#         Upbit_data = {
#             "Date": now.strftime('%Y-%m-%d'),
#             "Position": Upbit_data["Position"],
#             "ETH_weight": Upbit_data["ETH_weight"],
#             "ETH_target": Upbit_data["ETH_target"],
#             "CASH_weight": Upbit_data["CASH_weight"],
#             "Invest_quantity": Upbit_data["Invest_quantity"],
#             "Total_balance": Total_balance,
#             "ETH": ETH,
#             "KRW": KRW,
#             "Last_day_Total_balance": Last_day_Total_balance,
#             "Last_month_Total_balance": Last_month_Total_balance,
#             "Last_year_Total_balance": Last_year_Total_balance,
#             "Daily_return": Daily_return,
#             "Monthly_return": Monthly_return,
#             "Yearly_return": Yearly_return
#         }

#         # Upbit_data.json파일 생성
#         with open(Upbit_data_path, 'w', encoding='utf-8') as f:
#             json.dump(Upbit_data, f, ensure_ascii=False, indent=4)
#         time_module.sleep(0.5)

#         # KakaoTalk 메시지 보내기
#         KA.SendMessage(f"Upbit {now.strftime('%Y-%m-%d %H:%M:%S')} \n당일 트레이딩 완료")
#         KA.SendMessage(f"Upbit 일수익률: {Daily_return:.2f}% \n월수익률: {Monthly_return:.2f}% \n연수익률: {Yearly_return:.2f}% \n환산잔고: {round(Total_balance):,}원 \nETH: {ETH:,} \nKRW: {(round(KRW)):,}원")
#         KA.SendMessage(f"Upbit Position: {Upbit_data['Position']} \nETH_weight: {Upbit_data['ETH_weight']} \nETH_target: {Upbit_data['ETH_target']} \nCASH_weight: {Upbit_data['CASH_weight']}")

#         # Google Spreadsheet에 데이터 추가
        
#         # 설정값 (실제 값으로 변경 필요)
#         credentials_file = "/var/autobot/gspread/service_account.json" # 구글 서비스 계정 JSON 파일 경로
#         spreadsheet_name = "2025_TR_Upbit" # 스프레드시트 이름
        
#         # 구글 스프레드시트 연결
#         spreadsheet = GU.connect_google_sheets(credentials_file, spreadsheet_name)
        
#         # 현재 월 계산
#         current_month = now.month
        
#         # 데이터 저장
#         GU.save_to_sheets(spreadsheet, Upbit_data, current_month)
#     else:
#         pass

# except Exception as e:
#     print(f"Upbit {TR_time[0]} 당일 data 기록 중 예외 오류: {e}")
#     KA.SendMessage(f"Upbit {TR_time[0]} 당일 data 기록 중 예외 오류: {e}")

# #### 검증 > 마지막에 crontab에서 5분 후 자동종료 되게 설정
# if TR_time[1] == 0:
#     print(f"Upbit {now.strftime('%Y-%m-%d')} 트레이딩 프로그램 운용시간이 아닙니다. 프로그램을 종료합니다.")
#     KA.SendMessage(f"Upbit {now.strftime('%Y-%m-%d')} 트레이딩 프로그램 운용시간이 아닙니다. 프로그램을 종료합니다.")

exit()