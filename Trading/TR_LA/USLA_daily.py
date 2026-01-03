import USLA_model
import kakao_alert as KA
from datetime import datetime
import gspread_updater as GU
import time

# USLA모델 instance 생성
key_file_path = "/var/autobot/TR_USLA/kis63721147nkr.txt"
token_file_path = "/var/autobot/TR_USLA/kis63721147_token.json"
cano = "63721147"  # 종합계좌번호 (8자리)
acnt_prdt_cd = "01"  # 계좌상품코드 (2자리)
USLA_ticker = ["UPRO", "TQQQ", "EDC", "TMF", "TMV"]
USLA = USLA_model.USLA_Model(key_file_path, token_file_path, cano, acnt_prdt_cd)

try:
    # 지난 USLA data 불러오기
    USLA_data = USLA.load_USLA_data()
    USD_adjust = 0.0 # 입출금 변동액 직접기입 기본 0$

    # date 업데이트
    current = datetime.now()
    current_date = current.date()

    # 전일, 월초, 연초 전월말, 전년말 잔고 업데이트
    last_day_balance = float("{:.2f}".format(USLA_data['balance'])) # USLA_data['balance']
    last_day_balance_KRW = int(USLA_data['balance_KRW'])

    if current.day == 1: # 월초 전월 잔고 데이터 변경
        last_month_balance = last_day_balance
        last_month_balance_KRW = last_day_balance_KRW
        KA.SendMessage(f"월초, 전월 잔고를 {last_month_balance}원으로 업데이트했습니다.")
    else:
        last_month_balance = USLA_data['last_month_balance']
        last_month_balance_KRW = USLA_data['last_month_balance_KRW']

    if current.month == 1 and current.day == 1: # 연초 전년 잔고 데이터 변경
        last_year_balance = last_day_balance
        last_year_balance_KRW = last_day_balance_KRW
        KA.SendMessage(f"연초, 전년 잔고를 {last_year_balance}원으로 업데이트했습니다.")
    else:
        last_year_balance = USLA_data['last_year_balance']
        last_year_balance_KRW = USLA_data['last_year_balance_KRW']

    # 당일 평가잔고 산출
    result = USLA.get_US_stock_balance()
    Hold_tickers = {}
    if len(result) > 0:
        for i in range(len(result)):
            ticker = result[i]['ticker']
            qty = result[i]['quantity']
            Hold_tickers[ticker] = qty
    else:
        pass

    result = USLA.get_US_dollar_balance()
    exchange_rate = result['exchange_rate']

    UPRO = Hold_tickers.get('UPRO', 0)
    TQQQ = Hold_tickers.get('TQQQ', 0)
    EDC = Hold_tickers.get('EDC', 0)
    TMF = Hold_tickers.get('TMF', 0)
    TMV = Hold_tickers.get('TMV', 0)
    CASH = USLA_data['CASH'] + USD_adjust
    time.sleep(0.2)

    # 당일 티커별 평가금 산출
    UPRO_eval = UPRO * (USLA.get_US_current_price('UPRO') * (1-USLA.fee))
    TQQQ_eval = TQQQ * (USLA.get_US_current_price('TQQQ') * (1-USLA.fee))
    EDC_eval = EDC * (USLA.get_US_current_price('EDC') * (1-USLA.fee))
    TMF_eval = TMF * (USLA.get_US_current_price('TMF') * (1-USLA.fee))
    TMV_eval = TMV * (USLA.get_US_current_price('TMV') * (1-USLA.fee))
    # 데이터 조정
    today_eval = UPRO_eval + TQQQ_eval + EDC_eval + TMF_eval + TMV_eval + CASH
    today_eval_KRW = int(today_eval * exchange_rate)
    today_eval = float("{:.2f}".format(today_eval))
    

    # 일, 월, 연 수익률 #
    daily_return = (today_eval - last_day_balance) / last_day_balance * 100
    daily_return = float("{:.2f}".format(daily_return))
    monthly_return = (today_eval - last_month_balance) / last_month_balance * 100
    monthly_return = float("{:.2f}".format(monthly_return))
    yearly_return = (today_eval - last_year_balance) / last_year_balance * 100
    yearly_return = float("{:.2f}".format(yearly_return))

    daily_return_KRW = (today_eval_KRW - last_day_balance_KRW) / last_day_balance_KRW * 100
    daily_return_KRW = float("{:.2f}".format(daily_return_KRW))
    monthly_return_KRW = (today_eval_KRW - last_month_balance_KRW) / last_month_balance_KRW * 100
    monthly_return_KRW = float("{:.2f}".format(monthly_return_KRW))
    yearly_return_KRW = (today_eval_KRW - last_year_balance_KRW) / last_year_balance_KRW * 100
    yearly_return_KRW = float("{:.2f}".format(yearly_return_KRW))

    regime_signal = USLA_data['regime_signal']
    regime_signal = float("{:.2f}".format(regime_signal))
    target_weight1 = USLA_data['target_weight1']
    target_weight1 = float("{:.2f}".format(target_weight1))
    target_weight2 = USLA_data['target_weight2']    
    target_weight2 = float("{:.2f}".format(target_weight2))
    
    # USLA data
    USLA_data = {
        'date': str(current_date),
        'regime_signal': regime_signal,
        'target_ticker1': USLA_data['target_ticker1'],
        'target_weight1': target_weight1,
        'target_ticker1_qty': USLA_data['target_ticker1_qty'],
        'target_ticker2': USLA_data['target_ticker2'],
        'target_weight2': target_weight2,
        'target_ticker2_qty': USLA_data['target_ticker2_qty'],
        'UPRO': UPRO,
        'TQQQ': TQQQ,
        'EDC': EDC,
        'TMF': TMF,
        'TMV': TMV,
        'CASH': CASH,
        'balance': today_eval,
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

    USLA.save_USLA_data_json(USLA_data)

    # KaKaoTalk 알림
    Kamessage = []
    for key, value in USLA_data.items():
        Kamessage.append(f"{key}: {value}")
    KA.SendMessage("\n".join(Kamessage))

    # google sheet 업로드
    # 설정값 (실제 값으로 변경 필요)
    credentials_file = "/var/autobot/gspread/service_account.json" # 구글 서비스 계정 JSON 파일 경로
    spreadsheet_name = "2026_TR_USLA" # 스프레드시트 이름

    # 구글 스프레드시트 연결
    spreadsheet = GU.connect_google_sheets(credentials_file, spreadsheet_name)

    # 현재 월 계산 
    current_month = current_date.month

    # 데이터 저장
    GU.save_to_sheets(spreadsheet, USLA_data, current_month)
    
except Exception as e:
    KA.SendMessage(f"USLA_daily.py 에러 발생: {e}")