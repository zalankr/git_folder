import KIS_US
import telegram_alert as TA
from datetime import datetime
import gspread_updater as GU
import time
import sys
import json

# KIS instance 생성
key_file_path = "/var/autobot/TR_USAA/kis63721147nkr.txt"
token_file_path = "/var/autobot/TR_USAA/kis63721147_token.json"
cano = "63721147"
acnt_prdt_cd = "01"
KIS = KIS_US.KIS_API(key_file_path, token_file_path, cano, acnt_prdt_cd)

USAA_data_path = "/var/autobot/TR_USAA/USAA_data.json"
USAA_TR_path = "/var/autobot/TR_USAA/USAA_TR.json"
USLA_ticker = ['UPRO', 'TQQQ', 'EDC', 'TMV', 'TMF']
HAA_ticker = ['SPY', 'IWM', 'VEA', 'VWO', 'PDBC', 'VNQ', 'TLT', 'IEF', 'BIL']

def get_balance():
    # 현재의 종합잔고를 USLA, HAA, CASH별로 산출 & 총잔고 계산
    USD = KIS.get_US_order_available()
    if USD == None:
        TA.send_tele("USAA: USD잔고 확인 오류")
        sys.exit(1)
    try:
        with open(USAA_TR_path, 'r') as f:
            TR = json.load(f)
    except Exception as e:
        TA.send_tele(f"USAA_TR JSON 파일 오류: {e}")
        sys.exit(1)
    USD_USLA_weight = TR["USD_USLA"] / TR["USD_total"]
    USD_HAA_weight = TR["USD_HAA"] / TR["USD_total"]
    USD_USLA = USD * USD_USLA_weight
    USD_HAA = USD * USD_HAA_weight
    time.sleep(0.1)

    USLA_stocks = 0 # 해당 모델 현재 달러화 잔고
    for ticker in USLA_ticker:
        balance = KIS.get_ticker_balance(ticker)
        if isinstance(balance, dict):  # 딕셔너리인 경우만 처리
            eval_amount = balance.get('eval_amount', 0)
        else:
            eval_amount = 0  # 문자열(에러) 반환 시 처리
        USLA_stocks += eval_amount
        time.sleep(0.1)

    HAA_stocks = 0 # 해당 모델 현재 달러화 잔고
    for ticker in HAA_ticker:
        balance = KIS.get_ticker_balance(ticker)
        if isinstance(balance, dict):  # 딕셔너리인 경우만 처리
            eval_amount = balance.get('eval_amount', 0)
        else:
            eval_amount = 0  # 문자열(에러) 반환 시 처리
        HAA_stocks += eval_amount
        time.sleep(0.1)

    Total_balance = USLA_stocks + HAA_stocks + USD # 전체 잔고
    
    balance = {
        "USD": USD,
        "USLA_stocks": USLA_stocks,
        "USLA_USD": USD_USLA,
        "HAA_stocks": HAA_stocks,
        "HAA_USD": USD_HAA,
        "Total_balance": Total_balance
    }
    return balance

message = []
try:
    # 지난 USAA data 불러오기
    with open(USAA_data_path, 'r', encoding='utf-8') as f:
        pre_data = json.load(f)  # 변수명 변경하여 덮어쓰기 방지

    # 현재 날짜 업데이트
    current = datetime.now()
    current_date = current.date()

    # USAA 계좌잔고 조회
    balance = get_balance()
    USLA_stocks = balance["USLA_stocks"]
    HAA_stocks = balance["HAA_stocks"]
    USLA_USD = balance["USLA_USD"]
    HAA_USD = balance["HAA_USD"]
    USD = balance["USD"]
    USLA_balance = float("{:.2f}".format(USLA_stocks + USLA_USD))
    HAA_balance = float("{:.2f}".format(HAA_stocks + HAA_USD))
    Total_balance = float("{:.2f}".format(balance["Total_balance"]))

    # 계산오류 확인
    if Total_balance == USLA_balance + HAA_balance:
        pass
    else:
        TA.send_tele("USAA daily 잔고 계산 오류")
        sys.exit(1)

    # 전일, 월초, 연초 전월말, 전년말 잔고 업데이트
    last_day_balance = float("{:.2f}".format(pre_data.get('Total', 0.0)))
    USLA_last_day = float("{:.2f}".format(pre_data.get('USLA', USLA_balance)))
    HAA_last_day = float("{:.2f}".format(pre_data.get('HAA', HAA_balance)))

    if current.day == 1:  # 월초 전월 잔고 데이터 변경
        last_month_balance = last_day_balance
        USLA_last_month = USLA_last_day
        HAA_last_month = HAA_last_day
        message.append(f"USAA: 월초, 전월 전체잔고를 {last_month_balance:,.2f}$로 업데이트했습니다.")
    else:
        last_month_balance = pre_data.get('last_month_balance', Total_balance)
        USLA_last_month = pre_data.get('USLA_last_month', USLA_balance)
        HAA_last_month = pre_data.get('HAA_last_month', HAA_balance)

    if current.month == 1 and current.day == 1:  # 연초 전년 잔고 데이터 변경
        last_year_balance = last_day_balance
        USLA_last_year = USLA_last_day
        HAA_last_year = HAA_last_day
        message.append(f"USAA: 연초, 전년 전체잔고를 {last_year_balance:,.2f}$로 업데이트했습니다.")
    else:
        last_year_balance = pre_data.get('last_year_balance', Total_balance)
        USLA_last_year = pre_data.get('USLA_last_year', USLA_balance)
        HAA_last_year = pre_data.get('HAA_last_year', HAA_balance)
        
    # 환율 조회
    try:
        result = KIS.get_US_dollar_balance()
        exchange_rate = result['exchange_rate']
    except Exception as e:
        error_msg = f"USAA: 환율 조회 실패: {e}"
        TA.send_tele(error_msg)
        # 이전 환율 사용
        exchange_rate = pre_data.get('exchange_rate', 1400)  # 기본값 1400
    time.sleep(0.5)
    
    # 평가금 KRW 환산
    Total_KRW = int(Total_balance * exchange_rate)
    USLA_KRW = int(USLA_balance * exchange_rate)
    HAA_KRW = int(HAA_balance * exchange_rate)
    
    #월, 연 수익률 계산
    month_ret = (Total_balance - last_month_balance) / last_month_balance * 100 if last_month_balance > 0 else 0
    month_ret = float("{:.2f}".format(month_ret))
    USLA_month_ret = (USLA_balance - USLA_last_month) / USLA_last_month * 100 if USLA_last_month > 0 else 0
    USLA_month_ret = float("{:.2f}".format(USLA_month_ret))
    HAA_month_ret = (HAA_balance - HAA_last_month) / HAA_last_month * 100 if HAA_last_month > 0 else 0
    HAA_month_ret = float("{:.2f}".format(HAA_month_ret))
    
    year_ret = (Total_balance - last_year_balance) / last_year_balance * 100 if last_year_balance > 0 else 0
    year_ret = float("{:.2f}".format(year_ret))
    USLA_year_ret = (USLA_balance - USLA_last_year) / USLA_last_year * 100 if USLA_last_year > 0 else 0
    USLA_year_ret = float("{:.2f}".format(USLA_year_ret))
    HAA_year_ret = (HAA_balance - HAA_last_year) / HAA_last_year * 100 if HAA_last_year > 0 else 0
    HAA_year_ret = float("{:.2f}".format(HAA_year_ret))

    # 새로운 USAA data 생성
    str_USAA_data = {
        'date': str(current_date),
        'exchange_rate': str("{:,.2f}".format(exchange_rate)),
        'Total': str("{:,.2f}".format(Total_balance)),
        'last_day_balance': str("{:,.2f}".format(last_day_balance)),
        'last_month_balance': str("{:,.2f}".format(last_month_balance)),
        'last_year_balance': str("{:,.2f}".format(last_year_balance)),
        'month_ret': f"{month_ret:.2f}%",
        'year_ret': f"{year_ret:.2f}%",
        'Total_KRW': str("{:,.0f}".format(Total_KRW)),
        'USLA': str("{:,.2f}".format(USLA_balance)),
        'USLA_last_day': str("{:,.2f}".format(USLA_last_day)),
        'USLA_last_month': str("{:,.2f}".format(USLA_last_month)),
        'USLA_last_year': str("{:,.2f}".format(USLA_last_year)),
        'USLA_month_ret': f"{USLA_month_ret:.2f}%",
        'USLA_year_ret': f"{USLA_year_ret:.2f}%",
        'USLA_KRW': str("{:,.0f}".format(USLA_KRW)),
        'HAA': str("{:,.2f}".format(HAA_balance)),
        'HAA_last_day': str("{:,.2f}".format(HAA_last_day)),
        'HAA_last_month': str("{:,.2f}".format(HAA_last_month)),
        'HAA_last_year': str("{:,.2f}".format(HAA_last_year)),
        'HAA_month_ret': f"{HAA_month_ret:.2f}%",
        'HAA_year_ret': f"{HAA_year_ret:.2f}%",
        'HAA_KRW': str("{:,.0f}".format(HAA_KRW))
    }

    new_USAA_data = {
        'date': str(current_date),
        'exchange_rate': exchange_rate,
        'Total': Total_balance,
        'last_day_balance': last_day_balance,
        'last_month_balance': last_month_balance,
        'last_year_balance': last_year_balance,
        'month_ret': month_ret,
        'year_ret': year_ret,
        'Total_KRW': Total_KRW,
        'USLA': USLA_balance,
        'USLA_last_day': USLA_last_day,
        'USLA_last_month': USLA_last_month,
        'USLA_last_year': USLA_last_year,
        'USLA_month_ret': USLA_month_ret,
        'USLA_year_ret': USLA_year_ret,
        'USLA_KRW': USLA_KRW,
        'HAA': HAA_balance,
        'HAA_last_day': HAA_last_day,
        'HAA_last_month': HAA_last_month,
        'HAA_last_year': HAA_last_year,
        'HAA_month_ret': HAA_month_ret,
        'HAA_year_ret': HAA_year_ret,
        'HAA_KRW': HAA_KRW
    }

    # USAA data 저장
    with open(USAA_data_path, 'w', encoding='utf-8') as f:
        json.dump(new_USAA_data, f, indent=4, ensure_ascii=False)

    # Telegram 알림
    for key, value in str_USAA_data.items():
        message.append(f"{key}: {value}")
    TA.send_tele(message)

    for i in message: # 직접 실행 시 테스트
        print(i)

    # Google Sheet 업로드
    try:
        credentials_file = "/var/autobot/gspread/service_account.json"
        spreadsheet_name = "2026_TR_USAA"

        # Google 스프레드시트 연결
        spreadsheet = GU.connect_google_sheets(credentials_file, spreadsheet_name)

        # 현재 월 계산
        current_month = current_date.month

        # 데이터 저장
        GU.save_to_sheets(spreadsheet, str_USAA_data, current_month)
    except Exception as e:
        error_msg = f"Google Sheet 업로드 실패: {e}"
        TA.send_tele(error_msg)
        # Google Sheet 업로드 실패는 전체 프로세스를 중단하지 않음
    
except Exception as e:
    error_msg = f"USAA_daily.py 에러 발생: {e}"
    TA.send_tele(error_msg)
    sys.exit(1)

sys.exit(0)