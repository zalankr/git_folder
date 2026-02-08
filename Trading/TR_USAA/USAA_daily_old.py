import USAA_Trading as USAA
import KIS_US
import kakao_alert as KA
from datetime import datetime
import gspread_updater as GU
import time
from tendo import singleton
import sys
import json

try:
    me = singleton.SingleInstance()
except singleton.SingleInstanceException:
    sys.exit(0)

# KIS instance 생성
key_file_path = "/var/autobot/TR_USAA/kis63604155nkr.txt"
token_file_path = "/var/autobot/TR_USAA/kis63604155_token.json"
cano = "63604155"
acnt_prdt_cd = "01"
KIS = KIS_US.KIS_API(key_file_path, token_file_path, cano, acnt_prdt_cd)
USAA_data_path = "/var/autobot/TR_USAA/USAA_data.json"

def send_messages_in_chunks(message, max_length=900):
    current_chunk = []
    current_length = 0
    
    for msg in message:
        msg_length = len(msg) + 1  # \n 포함
        if current_length + msg_length > max_length:
            KA.SendMessage("\n".join(current_chunk))
            time.sleep(1)
            current_chunk = [msg]
            current_length = msg_length
        else:
            current_chunk.append(msg)
            current_length += msg_length
    
    if current_chunk:
        KA.SendMessage("\n".join(current_chunk))

message = []
try:
    # 지난 USLA data 불러오기
    with open(USAA_data_path, 'r', encoding='utf-8') as f:
        USLA_data = json.load(f)

    # date 업데이트
    current = datetime.now()
    current_date = current.date()

    # USAA 계좌잔고 조회
    USD, USLA_balance, USLA_qty, USLA_price, HAA_balance, HAA_qty, HAA_price, Total_balance = USAA.get_balance()
    time.sleep(0.2) # API 호출 간격 조절
    
    # USLA, HAA 타겟 및 레짐 산출
    USLA_target, USLA_regime, USLA_message = USAA.USLA_target_regime()
    HAA_target, HAA_regime, HAA_message = USAA.HAA_target_regime()
    time.sleep(0.2) # API 호출 간격 조절

    # 당일 평가금 산출
    balance = float("{:.2f}".format(Total_balance))
    CASH = float("{:.2f}".format(USD))

    # 전일, 월초, 연초 전월말, 전년말 잔고 업데이트
    last_day_balance = float("{:.2f}".format(USLA_data['balance'])) # USLA_data['balance']
    last_day_balance_KRW = int(USLA_data['balance_KRW'])

    if current.day == 1: # 월초 전월 잔고 데이터 변경
        last_month_balance = last_day_balance
        last_month_balance_KRW = last_day_balance_KRW
        message.append(f"월초, 전월 잔고를 {last_month_balance}원으로 업데이트했습니다.")
    else:
        last_month_balance = USLA_data['last_month_balance']
        last_month_balance_KRW = USLA_data['last_month_balance_KRW']

    if current.month == 1 and current.day == 1: # 연초 전년 잔고 데이터 변경
        last_year_balance = last_day_balance
        last_year_balance_KRW = last_day_balance_KRW
        message.append(f"연초, 전년 잔고를 {last_year_balance}원으로 업데이트했습니다.")
    else:
        last_year_balance = USLA_data['last_year_balance']
        last_year_balance_KRW = USLA_data['last_year_balance_KRW']

    # 환율 조회
    try:
        USD_balance = KIS.get_US_dollar_balance()
        exchange_rate = USD_balance['exchange_rate']
    except Exception as e:
        error_msg = f"환율 조회 실패: {e}"
        print(error_msg)
        KA.SendMessage(error_msg)
        # 이전 환율 사용
        exchange_rate = USAA_data.get('exchange_rate', 1400)  # 기본값 1400

    # 평가금 KRW 환산
    today_eval_KRW = int(balance * exchange_rate)
    
    # 일, 월, 연 수익률 #
    daily_return = (Total_balance - last_day_balance) / last_day_balance * 100
    daily_return = float("{:.2f}".format(daily_return))
    monthly_return = (Total_balance - last_month_balance) / last_month_balance * 100
    monthly_return = float("{:.2f}".format(monthly_return))
    yearly_return = (Total_balance - last_year_balance) / last_year_balance * 100
    yearly_return = float("{:.2f}".format(yearly_return))

    daily_return_KRW = (today_eval_KRW - last_day_balance_KRW) / last_day_balance_KRW * 100
    daily_return_KRW = float("{:.2f}".format(daily_return_KRW))
    monthly_return_KRW = (today_eval_KRW - last_month_balance_KRW) / last_month_balance_KRW * 100
    monthly_return_KRW = float("{:.2f}".format(monthly_return_KRW))
    yearly_return_KRW = (today_eval_KRW - last_year_balance_KRW) / last_year_balance_KRW * 100
    yearly_return_KRW = float("{:.2f}".format(yearly_return_KRW))

    # USLA data
    USLA_data = {
        'date': str(current_date),
        'USLA_regime': USLA_regime,
        'UPRO': USLA_qty.get("UPRO", 0),
        'TQQQ': USLA_qty.get("TQQQ", 0),
        'EDC': USLA_qty.get("EDC", 0),
        'TMF': USLA_qty.get("TMF", 0),
        'TMV': USLA_qty.get("TMV", 0),
        'HAA_regime': HAA_regime,
        'SPY': HAA_qty.get("SPY", 0),
        'IWM': HAA_qty.get("IWM", 0),
        'VEA': HAA_qty.get("VEA", 0),
        'VWO': HAA_qty.get("VWO", 0),
        'PDBC': HAA_qty.get("PDBC", 0),
        'VNQ': HAA_qty.get("VNQ", 0),
        'TLT': HAA_qty.get("TLT", 0),
        'IEF': HAA_qty.get("IEF", 0),
        'CASH': CASH,
        'balance': balance,
        'last_day_balance': last_day_balance,
        'last_month_balance': last_month_balance,
        'last_year_balance': last_year_balance,
        'daily_return': daily_return,
        'monthly_return': monthly_return,
        'yearly_return': yearly_return,
        'exchange_rate': exchange_rate,
        'balance_KRW': today_eval_KRW,
        'last_day_balance_KRW': last_day_balance_KRW,
        'last_month_balance_KRW': last_month_balance_KRW,
        'last_year_balance_KRW': last_year_balance_KRW,
        'daily_return_KRW': daily_return_KRW,
        'monthly_return_KRW': monthly_return_KRW,
        'yearly_return_KRW': yearly_return_KRW
    }

    # USLA data 저장
    with open(USAA_data_path, 'w', encoding='utf-8') as f:
        json.dump(USLA_data, f, indent=4, ensure_ascii=False)


    # KaKaoTalk 알림
    for key, value in USLA_data.items():
        message.append(f"{key}: {value}")
    send_messages_in_chunks(message, max_length=900)

    # google sheet 업로드
    credentials_file = "/var/autobot/gspread/service_account.json" # 구글 서비스 계정 JSON 파일 경로
    spreadsheet_name = "2026_TR_USAA" # 스프레드시트 이름

    # 구글 스프레드시트 연결
    spreadsheet = GU.connect_google_sheets(credentials_file, spreadsheet_name)

    # 현재 월 계산 
    current_month = current_date.month

    # 데이터 저장
    GU.save_to_sheets(spreadsheet, USLA_data, current_month)
    
except Exception as e:
    KA.SendMessage(f"USAA_daily.py 에러 발생: {e}")