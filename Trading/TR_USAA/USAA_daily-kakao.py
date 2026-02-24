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
USLA_ticker = ['UPRO', 'TQQQ', 'EDC', 'TMV', 'TMF']
HAA_ticker = ['TIP', 'SPY', 'IWM', 'VEA', 'VWO', 'PDBC', 'VNQ', 'TLT', 'IEF', 'BIL']

def send_messages_in_chunks(message, max_length=1000):
    """메시지를 최대 길이로 나누어 전송"""
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

def get_balance(): # 신규 생성 사용
    # 현재의 종합잔고를 USLA, HAA, CASH별로 산출 & 총잔고 계산
    USD_account = KIS.get_US_dollar_balance()
    if USD_account:
        USD = USD_account.get('withdrawable', 0)  # 키가 없을 경우 0 반환
    else:
        USD = 0  # API 호출 실패 시 처리
    time.sleep(0.1)

    USLA_balance = 0 # 해당 모델 현재 달러화 잔고
    USLA_qty = {} # 해당 티커 현재 보유량
    USLA_price  = {} # 해당 티커 현재 가격
    for ticker in USLA_ticker:
        balance = KIS.get_ticker_balance(ticker)
        if isinstance(balance, dict):  # 딕셔너리인 경우만 처리
            eval_amount = balance.get('eval_amount', 0)
            USLA_qty[ticker] = balance.get('holding_qty', 0)
            USLA_price[ticker] = balance.get('current_price', 0)
        else:
            eval_amount = 0  # 문자열(에러) 반환 시 처리
        USLA_balance += eval_amount
        time.sleep(0.1)

    HAA_balance = 0 # 해당 모델 현재 달러화 잔고
    HAA_qty = {} # 해당 티커 현재 보유량
    HAA_price  = {} # 해당 티커 현재 가격
    for ticker in HAA_ticker:
        if ticker == 'TIP':
            continue # TIP은 Regime signal 확인용으로 투자, 보유용이 아니라서 제외
        balance = KIS.get_ticker_balance(ticker)
        if isinstance(balance, dict):  # 딕셔너리인 경우만 처리
            eval_amount = balance.get('eval_amount', 0)
            HAA_qty[ticker] = balance.get('holding_qty', 0)
            HAA_price[ticker] = balance.get('current_price', 0)
        else:
            eval_amount = 0  # 문자열(에러) 반환 시 처리
        HAA_balance += eval_amount
        time.sleep(0.05)

    Total_balance = USLA_balance + HAA_balance + USD # 전체 잔고

    return USD, USLA_balance, USLA_qty, USLA_price, HAA_balance, HAA_qty, HAA_price, Total_balance

message = []
try:
    # 지난 USAA data 불러오기
    with open(USAA_data_path, 'r', encoding='utf-8') as f:
        previous_USAA_data = json.load(f)  # 변수명 변경하여 덮어쓰기 방지

    # 현재 날짜 업데이트
    current = datetime.now()
    current_date = current.date()

    # USAA 계좌잔고 조회
    try:
        USD, USLA_balance, USLA_qty, USLA_price, HAA_balance, HAA_qty, HAA_price, Total_balance = get_balance()

    except Exception as e:
        error_msg = f"계좌 잔고 조회 실패: {e}"
        print(error_msg)
        KA.SendMessage(error_msg)
        raise
    
    ## 헷징 모드 확인 후 비중 조정: 빈 딕셔너리 체크 (값이 모두 0인지)
    USLA_has_position = any(qty > 0 for qty in USLA_qty.values())
    HAA_has_position = any(qty > 0 for qty in HAA_qty.values())

    if not USLA_has_position and not HAA_has_position:
        # 둘 다 보유 없음
        USLA_balance = USD * 0.7
        HAA_balance = USD * 0.3

    elif not USLA_has_position and HAA_has_position:
        # USLA만 없음
        USLA_balance = USD * (70/70.6)
        HAA_balance = HAA_balance + (USD * (0.6/70.6))

    elif USLA_has_position and not HAA_has_position:
        # HAA만 없음
        USLA_balance = USLA_balance + (USD * (1.4/31.4))
        HAA_balance = USD * (30/31.4)

    else:
        # 둘 다 보유
        USLA_balance = USLA_balance + (USD * 0.7)
        HAA_balance = HAA_balance + (USD * 0.3)

    # 당일 평가금 산출
    balance = float("{:.2f}".format(Total_balance))
    USLA_balance = float("{:.2f}".format(USLA_balance))
    HAA_balance = float("{:.2f}".format(HAA_balance))

    # 전일, 월초, 연초 전월말, 전년말 잔고 업데이트
    last_day_balance = float("{:.2f}".format(previous_USAA_data.get('balance', balance)))
    last_day_balance_KRW = int(previous_USAA_data.get('balance_KRW', 0))
    USLA_last_day_balance = float("{:.2f}".format(previous_USAA_data.get('USLA_balance', USLA_balance)))
    USLA_last_day_balance_KRW = int(previous_USAA_data.get('USLA_balance_KRW', 0))
    HAA_last_day_balance = float("{:.2f}".format(previous_USAA_data.get('HAA_balance', HAA_balance)))
    HAA_last_day_balance_KRW = int(previous_USAA_data.get('HAA_balance_KRW', 0))

    if current.day == 1:  # 월초 전월 잔고 데이터 변경
        last_month_balance = last_day_balance
        USLA_last_month_balance = USLA_last_day_balance
        HAA_last_month_balance = HAA_last_day_balance
        last_month_balance_KRW = last_day_balance_KRW
        USLA_last_month_balance_KRW = USLA_last_day_balance_KRW
        HAA_last_month_balance_KRW = HAA_last_day_balance_KRW
        message.append(f"월초, 전월 전체잔고를 {last_month_balance}원으로 업데이트했습니다.")
    else:
        last_month_balance = previous_USAA_data.get('last_month_balance', balance)
        USLA_last_month_balance = previous_USAA_data.get('USLA_last_month_balance', USLA_balance)
        HAA_last_month_balance = previous_USAA_data.get('HAA_last_month_balance', HAA_balance)
        last_month_balance_KRW = previous_USAA_data.get('last_month_balance_KRW', 0)
        USLA_last_month_balance_KRW = previous_USAA_data.get('USLA_last_month_balance_KRW', 0)
        HAA_last_month_balance_KRW = previous_USAA_data.get('HAA_last_month_balance_KRW', 0)

    if current.month == 1 and current.day == 1:  # 연초 전년 잔고 데이터 변경
        last_year_balance = last_day_balance
        USLA_last_year_balance = USLA_last_day_balance
        HAA_last_year_balance = HAA_last_day_balance
        last_year_balance_KRW = last_day_balance_KRW
        USLA_last_year_balance_KRW = USLA_last_day_balance_KRW
        HAA_last_year_balance_KRW = HAA_last_day_balance_KRW
        message.append(f"연초, 전년 전체잔고를 {last_year_balance}원으로 업데이트했습니다.")
    else:
        last_year_balance = previous_USAA_data.get('last_year_balance', balance)
        USLA_last_year_balance = previous_USAA_data.get('USLA_last_year_balance', USLA_balance)
        HAA_last_year_balance = previous_USAA_data.get('HAA_last_year_balance', HAA_balance)
        last_year_balance_KRW = previous_USAA_data.get('last_year_balance_KRW', 0)
        USLA_last_year_balance_KRW = previous_USAA_data.get('USLA_last_year_balance_KRW', 0)
        HAA_last_year_balance_KRW = previous_USAA_data.get('HAA_last_year_balance_KRW', 0)

    # 환율 조회
    try:
        USD_balance = KIS.get_US_dollar_balance()
        exchange_rate = USD_balance['exchange_rate']
    except Exception as e:
        error_msg = f"환율 조회 실패: {e}"
        print(error_msg)
        KA.SendMessage(error_msg)
        # 이전 환율 사용
        exchange_rate = previous_USAA_data.get('exchange_rate', 1400)  # 기본값 1400

    # 평가금 KRW 환산
    today_eval_KRW = int(balance * exchange_rate)
    USLA_today_eval_KRW = int(USLA_balance * exchange_rate)
    HAA_today_eval_KRW = int(HAA_balance * exchange_rate)
    
    #월, 연 수익률 계산
    monthly_return = ((Total_balance - last_month_balance) / last_month_balance * 100) if last_month_balance > 0 else 0
    monthly_return = float("{:.2f}".format(monthly_return))
    USLA_monthly_return = ((USLA_balance - USLA_last_month_balance) / USLA_last_month_balance * 100) if USLA_last_month_balance > 0 else 0
    USLA_monthly_return = float("{:.2f}".format(USLA_monthly_return))
    HAA_monthly_return = ((HAA_balance - HAA_last_month_balance) / HAA_last_month_balance * 100) if HAA_last_month_balance > 0 else 0
    HAA_monthly_return = float("{:.2f}".format(HAA_monthly_return))
    
    yearly_return = ((Total_balance - last_year_balance) / last_year_balance * 100) if last_year_balance > 0 else 0
    yearly_return = float("{:.2f}".format(yearly_return))
    USLA_yearly_return = ((USLA_balance - USLA_last_year_balance) / USLA_last_year_balance * 100) if USLA_last_year_balance > 0 else 0
    USLA_yearly_return = float("{:.2f}".format(USLA_yearly_return))
    HAA_yearly_return = ((HAA_balance - HAA_last_year_balance) / HAA_last_year_balance * 100) if HAA_last_year_balance > 0 else 0
    HAA_yearly_return = float("{:.2f}".format(HAA_yearly_return))

    monthly_return_KRW = ((today_eval_KRW - last_month_balance_KRW) / last_month_balance_KRW * 100) if last_month_balance_KRW > 0 else 0
    monthly_return_KRW = float("{:.2f}".format(monthly_return_KRW))
    USLA_monthly_return_KRW = ((USLA_today_eval_KRW - USLA_last_month_balance_KRW) / USLA_last_month_balance_KRW * 100) if USLA_last_month_balance_KRW > 0 else 0
    USLA_monthly_return_KRW = float("{:.2f}".format(USLA_monthly_return_KRW))
    HAA_monthly_return_KRW = ((HAA_today_eval_KRW - HAA_last_month_balance_KRW) / HAA_last_month_balance_KRW * 100) if HAA_last_month_balance_KRW > 0 else 0
    HAA_monthly_return_KRW = float("{:.2f}".format(HAA_monthly_return_KRW))
    
    yearly_return_KRW = ((today_eval_KRW - last_year_balance_KRW) / last_year_balance_KRW * 100) if last_year_balance_KRW > 0 else 0
    yearly_return_KRW = float("{:.2f}".format(yearly_return_KRW))
    USLA_yearly_return_KRW = ((USLA_today_eval_KRW - USLA_last_year_balance_KRW) / USLA_last_year_balance_KRW * 100) if USLA_last_year_balance_KRW > 0 else 0
    USLA_yearly_return_KRW = float("{:.2f}".format(USLA_yearly_return_KRW))
    HAA_yearly_return_KRW = ((HAA_today_eval_KRW - HAA_last_year_balance_KRW) / HAA_last_year_balance_KRW * 100) if HAA_last_year_balance_KRW > 0 else 0
    HAA_yearly_return_KRW = float("{:.2f}".format(HAA_yearly_return_KRW))

    # 새로운 USAA data 생성
    new_USAA_data = {
        'date': str(current_date),
        'exchange_rate': exchange_rate,
        'Total': balance,
        'last_day': last_day_balance,
        'last_mon': last_month_balance,
        'last_year': last_year_balance,
        'mon_ret': monthly_return,
        'year_ret': yearly_return,
        'Total_W': today_eval_KRW,
        'last_day_W': last_day_balance_KRW,
        'last_mon_W': last_month_balance_KRW,
        'last_year_W': last_year_balance_KRW,
        'mon_ret_W': monthly_return_KRW,
        'year_ret_W': yearly_return_KRW,
        'USLA': USLA_balance,
        'USLA_last_day': USLA_last_day_balance,
        'USLA_last_mon': USLA_last_month_balance,
        'USLA_last_year': USLA_last_year_balance,
        'USLA_mon_ret': USLA_monthly_return,
        'USLA_year_ret': USLA_yearly_return,
        'USLA_W': USLA_today_eval_KRW,
        'USLA_last_day_W': USLA_last_day_balance_KRW,
        'USLA_last_mon_W': USLA_last_month_balance_KRW,
        'USLA_last_year_W': USLA_last_year_balance_KRW,
        'USLA_mon_ret_W': USLA_monthly_return_KRW,
        'USLA_year_ret_W': USLA_yearly_return_KRW,
        'HAA': HAA_balance,
        'HAA_last_day': HAA_last_day_balance,
        'HAA_last_mon': HAA_last_month_balance,
        'HAA_last_year': HAA_last_year_balance,
        'HAA_mon_ret': HAA_monthly_return,
        'HAA_year_ret': HAA_yearly_return,
        'HAA_W': HAA_today_eval_KRW,
        'HAA_last_day_W': HAA_last_day_balance_KRW,
        'HAA_last_mon_W': HAA_last_month_balance_KRW,
        'HAA_last_year_W': HAA_last_year_balance_KRW,
        'HAA_mon_ret_W': HAA_monthly_return_KRW,
        'HAA_year_ret_W': HAA_yearly_return_KRW
    }

    # USAA data 저장
    with open(USAA_data_path, 'w', encoding='utf-8') as f:
        json.dump(new_USAA_data, f, indent=4, ensure_ascii=False)

    # KakaoTalk 알림
    for key, value in new_USAA_data.items():
        message.append(f"{key}: {value}")
    send_messages_in_chunks(message, max_length=1200)

    # Google Sheet 업로드
    try:
        credentials_file = "/var/autobot/gspread/service_account.json"
        spreadsheet_name = "2026_TR_USAA"

        # Google 스프레드시트 연결
        spreadsheet = GU.connect_google_sheets(credentials_file, spreadsheet_name)

        # 현재 월 계산
        current_month = current_date.month

        # 데이터 저장
        GU.save_to_sheets(spreadsheet, new_USAA_data, current_month)
    except Exception as e:
        error_msg = f"Google Sheet 업로드 실패: {e}"
        print(error_msg)
        KA.SendMessage(error_msg)
        # Google Sheet 업로드 실패는 전체 프로세스를 중단하지 않음
    
except Exception as e:
    error_msg = f"USAA_daily.py 에러 발생: {e}"
    KA.SendMessage(error_msg)
    raise  # 에러를 다시 발생시켜 스택 트레이스 확인 가능

sys.exit(0)