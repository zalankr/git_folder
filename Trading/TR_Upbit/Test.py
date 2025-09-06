import pyupbit
import json
import time as time_module  # time 모듈을 별칭으로 import
import UP_signal_weight as UP
import kakao_alert as KA
import gspread_updater as GU


################## 마지막 주문 후 수익률 계산하기(년, 월, 일) JSON 기록 카톡 알림, gspread sheet 기록 try로 감싸기
# Upbit 토큰 불러오기
with open("/var/autobot/TR_Upbit/upnkr.txt") as f:
    access_key, secret_key = [line.strip() for line in f.readlines()]

# 업비트 접속, JSON data 경로 설정
upbit = pyupbit.Upbit(access_key, secret_key)
Upbit_data_path = '/var/autobot/TR_Upbit/Upbit_data.json'

now, current_time, TR_time = UP.what_time()
print(f"현재 시간: {now.strftime('%Y-%m-%d %H:%M:%S')}, TR_time: {TR_time}")

# For test
TR_time = 1
try:
    if TR_time == 1:
        # 당일의 Upbit_data.json 파일 불러오고 position, 어제종료 원화환산 토탈잔고, KRW잔고, ETH잔고 추출
        with open(Upbit_data_path, 'r', encoding='utf-8') as f:
            Upbit_data = json.load(f)

        # 전일 ETH/KRW/원화환산 잔고, 전월말, 전년말 원화환산 잔고
        Last_day_Total_balance = Upbit_data["Last_day_Total_balance"]
        Last_month_Total_balance = Upbit_data["Last_month_Total_balance"]
        Last_year_Total_balance = Upbit_data["Last_year_Total_balance"]

        # 당일종료 원화환산 토탈잔고, KRW잔고, ETH잔고
        KRW, ETH, Total_balance = UP.Total_balance(upbit)

        # 일, 월, 연 수익률
        Daily_return = (Total_balance - Last_day_Total_balance) / Last_day_Total_balance * 100
        Monthly_return = (Total_balance - Last_month_Total_balance) / Last_month_Total_balance * 100
        Yearly_return = (Total_balance - Last_year_Total_balance) / Last_year_Total_balance * 100

        time_module.sleep(0.5) # 타임슬립 0.5초

        # 월초, 연초 전월말, 전년말 잔고 업데이트
        if now.day == 1: # 월초 전월 잔고 데이터 변경
            Last_month_Total_balance = Last_day_Total_balance
            print(f"월초, 전월 잔고를 {Last_month_Total_balance}원으로 업데이트했습니다.")
        else:
            pass

        if now.month == 1 and now.day == 1: # 연초 전년 잔고 데이터 변경
            Last_year_Total_balance = Last_day_Total_balance
            print(f"연초, 전년 잔고를 {Last_year_Total_balance}원으로 업데이트했습니다.")
        else:
            pass

        # Upbit_data 만들기
        Upbit_data = {
            "Date": now.strftime('%Y-%m-%d'),
            "Position": Upbit_data["Position"],
            "ETH_weight": Upbit_data["ETH_weight"],
            "ETH_target": Upbit_data["ETH_target"],
            "CASH_weight": Upbit_data["CASH_weight"],
            "Invest_quantity": Upbit_data["Invest_quantity"],
            "Total_balance": Total_balance,
            "ETH": ETH,
            "KRW": KRW,
            "Last_day_Total_balance": Last_day_Total_balance,
            "Last_month_Total_balance": Last_month_Total_balance,
            "Last_year_Total_balance": Last_year_Total_balance,
            "Daily_return": Daily_return,
            "Monthly_return": Monthly_return,
            "Yearly_return": Yearly_return
        }

        # Upbit_data.json파일 생성
        with open(Upbit_data_path, 'w', encoding='utf-8') as f:
            json.dump(Upbit_data, f, ensure_ascii=False, indent=4)
        time_module.sleep(0.5)

        # KakaoTalk 메시지 보내기
        KA.SendMessage(f"{now.strftime('%Y-%m-%d')} {str(TR_time)[0]} 당일 트레이딩 완료")
        KA.SendMessage(f"일간 수익률: {Daily_return:.2f}% \n월간 수익률: {Monthly_return:.2f}% \n연간 수익률: {Yearly_return:.2f}%")
        KA.SendMessage(f"원화환산 잔고: {Total_balance:,}원 \nETH: {ETH:,} \nKRW: {KRW:,}원")
        KA.SendMessage(f"Position: {Upbit_data['Position']} \nETH_weight: {Upbit_data['ETH_weight']} \nETH_target: {Upbit_data['ETH_target']} \nCASH_weight: {Upbit_data['CASH_weight']}")

        # Google Spreadsheet에 데이터 추가
        
        # 설정값 (실제 값으로 변경 필요)
        credentials_file = "/var/autobot/gspread/service_account.json"  # 구글 서비스 계정 JSON 파일 경로
        spreadsheet_name = "2025_TR_Upbit"  # 스프레드시트 이름
        
        # 구글 스프레드시트 연결
        spreadsheet = GU.connect_google_sheets(credentials_file, spreadsheet_name)
        
        # 현재 월 계산
        current_month = now.month
        
        # 데이터 저장
        GU.save_to_sheets(spreadsheet, Upbit_data, current_month)
    else:
        pass

except Exception as e:
    print(f"{TR_time[0]} 당일주문 data 기록 중 예외의 오류: {e}")
    KA.SendMessage(f"{TR_time[0]} 당일주문 data 기록 중 예외의 오류: {e}")

#### 검증 > 마지막에 crontab에서 5분 후 자동종료 되게 설정
exit()
