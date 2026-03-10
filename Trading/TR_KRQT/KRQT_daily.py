import sys
import json
import telegram_alert as TA
from datetime import datetime
import gspread_updater as GU
import time as time_module
from tendo import singleton
import KIS_KR

try:
    me = singleton.SingleInstance()
except singleton.SingleInstanceException:
    TA.send_tele("KRQT: 이미 실행 중입니다.")
    sys.exit(0)

# KIS instance 생성
key_file_path = "/var/autobot/TR_KRQT/kis43018646nkr.txt"
token_file_path = "/var/autobot/TR_KRQT/kis43018646_token.json"
cano = "43018646"
acnt_prdt_cd = "01"
KIS = KIS_KR.KIS_API(key_file_path, token_file_path, cano, acnt_prdt_cd)

KRQT_result_path = "/var/autobot/TR_KRQT/KRQT_result.json" # json
KRQT_daily_path = "/var/autobot/TR_KRQT/KRQT_rdaily.json" # json
message = []

# 현재 일자 산출
current_date = datetime.now()
current_month = current_date.month
message.append(f"{str(current_date)}일 KRQT_daily 산출 시작")

# 전일 daily_data 불러오기
try:
    with open(KRQT_daily_path, "r") as f:  
        last_daily = json.load(f)
except Exception as e:
    TA.send_tele(f"KRQT daily_data 파일 오류: {e}")
    sys.exit(1)

# 시즌 매매 결과 불러오기
try:
    with open(KRQT_result_path, 'r', encoding='utf-8') as f:
        result = json.load(f)
except Exception as e:
    TA.send_tele(f"KRQT_result.json 파일 오류: {e}")
    sys.exit(1)
    
# 잔고 조회
balance = KIS.get_KR_account_summary()
if not isinstance(balance, dict):
    TA.send_tele(f"KRQT: 전체 자산 조회 불가로 종료합니다. ({balance})")
    sys.exit(1)

orderable_cash = KIS.get_KR_orderable_cash()    # 주문가능현금 추가 조회
if not isinstance(orderable_cash, (int, float)):
    TA.send_tele(f"KRQT: 주문가능현금 조회 불가로 종료합니다. ({orderable_cash})")
    sys.exit(1)

# 전체 자산 data 정리
total_asset = float(balance['stock_eval_amt'] + orderable_cash)
daily_data = {
    "date": str(current_date),
    "total_stocks":     float(balance['stock_eval_amt']),
    "total_cash":       float(orderable_cash),                        # ← 주문가능현금
    "total_asset":      total_asset,  # ← 재산출
    "total_asset_ret":  float(total_asset / last_daily['total_asset'] - 1)
}

# category별 자산
for category, stocks_list in result.items():
    category_balance = 0.0
    for i in stocks_list:
        price = KIS.get_KR_current_price(stocks_list[i]['code'])
        stock_balance = stocks_list[i]['qty'] * price
        category_balance += stock_balance
        time_module.sleep(0.125)
    daily_data[category]            = float(category_balance)  # category_balance
    daily_data[f"{category}_ret"]   = float(category_balance / last_daily[category] - 1)

# KRQT_daily.json 저장
try:
    with open(KRQT_daily_path, "w", encoding="utf-8") as f:
        json.dump(daily_data, f, indent=4, ensure_ascii=False)
    message.append(f"{str(current_date)}일 KRQT_daily.json 저장 완료")
except Exception as e:
    error_msg = f"KRQT_daily.json 저장 실패: {e}"
    TA.send_tele(error_msg)

# data 정제
daily = {
    "date": daily_data["date"],
    "total_stocks":     f"{int(daily_data['total_stocks'])}원",
    "total_cash":       f"{int(daily_data['total_cash'])}원",
    "total_asset":      f"{int(daily_data['total_asset'])}원",  
    "total_asset_ret":  f"{float(daily_data['total_asset_ret']*100):.2f}%"
}

for category, stocks_list in result.items():
    category_balance = 0.0
    for i in stocks_list:
        price = KIS.get_KR_current_price(stocks_list[i]['code'])
        stock_balance = stocks_list[i]['qty'] * price
        category_balance += stock_balance
        time_module.sleep(0.125)
    daily[category]            = f"{int(category_balance)}원"  # category_balance
    daily[f"{category}_ret"]   = f"{float(daily_data[f'{category}_ret']*100):.2f}%"  # float(category_balance / last_daily[category] - 1)

# daily balance google sheet 저장
try:
    credentials_file = "/var/autobot/gspread/service_account.json"
    spreadsheet_name = "2026_KRQT_daily"

    # Google 스프레드시트 연결
    spreadsheet = GU.connect_google_sheets(credentials_file, spreadsheet_name)

    # 데이터 저장
    GU.save_to_sheets(spreadsheet, daily, current_month)
except Exception as e:
    error_msg = f"Google Sheet 업로드 실패: {e}"
    TA.send_tele(error_msg)
    # Google Sheet 업로드 실패는 전체 프로세스를 중단하지 않음

# telegram message
for k, v in daily.items():
    message.append(f"{k} : {v}")

TA.send_tele(message)
message=[]

sys.exit(0)