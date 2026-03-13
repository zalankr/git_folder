import sys
import json
from datetime import datetime, timedelta as time_obj
import pandas as pd
from collections import defaultdict
import gspread_updater as GU
import KIS_KR

# KIS instance 생성
key_file_path = "/var/autobot/TR_KRQT/kis43018646nkr.txt"
token_file_path = "/var/autobot/TR_KRQT/kis43018646_token.json"
cano = "43018646"
acnt_prdt_cd = "01"
KIS = KIS_KR.KIS_API(key_file_path, token_file_path, cano, acnt_prdt_cd)

KRQT_daily_path = "/var/autobot/TR_KRQT/KRQT_daily.json" # json
KRQT_stock_path = "/var/autobot/TR_KRQT/KRQT_stock.csv" # csv

def save_json(data, path):
    """
    저장 실패 시에도 백업 파일 생성
    """
    result_msgs = []
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            result_msgs.append(f"{path} 저장 완료")
    except Exception as e:
        result_msgs.append(f"{path} 저장 실패: {e}")
        backup_path = f"/var/autobot/TR_KRQT/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            result_msgs.append(f"백업 파일 생성: {backup_path}")
        except Exception as backup_error:
            result_msgs.append(f"백업 실패: {backup_error}")
    return result_msgs   # 새 리스트 반환

try:
    with open(KRQT_stock_path, 'r', encoding='utf-8') as f:
        Target = pd.read_csv(f, dtype={
            "code": str,
            "name": str,
            "weight": float,
            "category": str
        })
except Exception as e:
    print(f"KRQT_stock.csv 파일 오류: {e}")
    sys.exit(1)

# 중복 종목 비중 합산
Target["code"] = Target["code"].str[1:]

grouped = Target.groupby("code").agg(
    name=("name", "first"),
    weight=("weight", "sum"),
    categories=("category", list)  # 전략 목록 보존
).reset_index()

target = {
    str(row["code"]): {
        "name":       str(row["name"]),
        "weight":     float(row["weight"]),
        "categories": [str(c) for c in row["categories"]],  # ['모멘텀'] or ['모멘텀', '피크']
    }
    for _, row in grouped.iterrows()
}

for k, v in target.items():
    print(f"{k} : {v}")
    
target_code = list(target.keys())

current_date = datetime.now()
current_month = current_date.month

plan = Target

plan_raw = defaultdict(list)
for _, row in plan.iterrows():
    if str(row["code"]) == "CASH":        # CASH는 결과 리포트 대상 아님
        continue
    if pd.isna(row["category"]):          # category 빈값 행 스킵
        continue
    plan_raw[str(row["category"])].append({
        "code": str(row["code"]),
        "name": str(row["name"]),
        "weight": float(row["weight"]),
    })

plan = dict(plan_raw)

# 보유 종목 잔고 불러오기
stocks = KIS.get_KR_stock_balance()
if not isinstance(stocks, list):
    print(f"KRQT: 잔고 조회 불가로 종료합니다. ({stocks})")
    sys.exit(1)

hold = {}
for stock in stocks:
    code = stock["종목코드"]
    hold[code] = {
        "name": stock["종목명"],
        "hold_balance": stock["평가금액"],
        "hold_qty": stock["보유수량"],
    }

hold_code = list(hold.keys())

result = {}
for category in plan.keys():
    result[category] = []       # 카테고리별 리스트로 초기화
    for stock in plan[category]:
        stock_code = stock['code']
        if stock_code not in hold_code:
            result[category].append({
                "code":    stock_code,
                "name":    stock['name'],
                "qty":     0,
                "balance": 0,
                "weight":  stock['weight'],
                "status":  "리밸런싱 매수실패"
            })
        else:
            total_w = target[stock_code]['weight']
            if total_w == 0:
                split_weight = 1.0   # 단일 전략 종목으로 처리
                print(f"경고: {stock_code} weight=0, split_weight=1.0으로 처리")
            else:
                split_weight = stock['weight'] / total_w
                
            result[category].append({
                "code":    stock_code,
                "name":    stock['name'],
                "qty":     hold[stock_code]['hold_qty'] * split_weight,  # stock_code 사용
                "balance": hold[stock_code]['hold_balance'] * split_weight,  # stock_code 사용
                "weight":  stock['weight'],
                "status":  "리밸런싱"
            })

remain_items = []
for code in hold_code:
    if code not in target_code:
        remain_items.append({
            "code":    code,
            "name":    hold[code]['name'],
            "qty":     hold[code]['hold_qty'],
            "balance": hold[code]['hold_balance'],
            "weight":  0,
            "status":  "리밸런싱 매도실패"
        })
if remain_items:                      # 항목이 있을 때만 result에 추가
    result["remain_last"] = remain_items

for category, stocks_list in result.items():
    for item in stocks_list:
        qty     = int(item['qty'])
        balance = f"{int(item['balance']):,}"
        print(f"종목명: {item['name']}, 잔고: {qty}주, 평가금: {balance}원, 상태: {item['status']}")

all_balance = KIS.get_KR_account_summary()
if not isinstance(all_balance, dict):
    print(f"KRQT: 전체 자산 조회 불가로 종료합니다. ({all_balance})")
    sys.exit(1)

orderable_cash = KIS.get_KR_orderable_cash()    # 주문가능현금 추가 조회
if not isinstance(orderable_cash, (int, float)):
    print(f"KRQT: 주문가능현금 조회 불가로 종료합니다. ({orderable_cash})")
    sys.exit(1)

daily_data = {
    "date": current_date.strftime("%Y%m%d"),
    "total_stocks":     all_balance['stock_eval_amt'],
    "total_cash":       float(orderable_cash),                          # ← 주문가능현금
    "total_asset":      all_balance['stock_eval_amt'] + float(orderable_cash),  # ← 재산출
    "total_asset_ret":  0.0
}

# category별 자산
for category, stocks_list in result.items():
    category_balance = sum(item['balance'] for item in stocks_list)
    daily_data[category]            = category_balance
    daily_data[f"{category}_ret"]   = 0.0
    
# KRQT_daily.json 저장
try:
    json_message = save_json(daily_data, KRQT_daily_path)
    print("\n".join(json_message))
except Exception as e:
    error_msg = f"KRQT_daily.json 저장 실패: {e}"
    print(error_msg)
    
# data 정제
daily = {
    "date": daily_data["date"],
    "total_stocks":     f"{int(daily_data['total_stocks'])}원",
    "total_cash":       f"{int(daily_data['total_cash'])}원",
    "total_asset":      f"{int(daily_data['total_asset'])}원",  
    "total_asset_ret":  f"{float(daily_data['total_asset_ret']*100):.2f}%"
}

for category, stocks_list in result.items():
    category_balance = sum(item['balance'] for item in stocks_list)
    daily[category]            = f"{int(category_balance)}원"
    daily[f"{category}_ret"]   = "0.00%"
    
print("\n".join(f"{k} : {v}" for k, v in daily.items()))

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
    print(error_msg)


sys.exit(0)