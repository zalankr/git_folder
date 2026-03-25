import sys
import json
import telegram_alert as TA
from datetime import datetime
import time as time_module
from tendo import singleton
import KIS_IRP

try:
    me = singleton.SingleInstance()
except singleton.SingleInstanceException:
    TA.send_tele("IRP: 이미 실행 중입니다.")
    sys.exit(0)

# KIS instance 생성
key_file_path = "/var/autobot/TR_IRP/kis43685950nkr.txt"
token_file_path = "/var/autobot/TR_IRP/kis43685950_token.json"
cano = "43685950"
acnt_prdt_cd = "29" # IRP계좌
KIS = KIS_IRP.KIS_API(key_file_path, token_file_path, cano, acnt_prdt_cd)

IRP_result_path = "/var/autobot/TR_IRP/IRP_result.json" # json
IRP_target_path = "/var/autobot/TR_IRP/IRP_target.json" # json

# 포트폴리오 목표비중
target = {
    "441800": {
        "name": "TIME Korea플러스배당액티브",
        "weight": 0.20
    },
    "0113D0": {
        "name": "TIME 글로벌탑픽액티브",
        "weight": 0.20
    },
    "456600": {
        "name": "TIME 글로벌AI인공지능액티브",
        "weight": 0.20
    },
    "490490": {
        "name": "SOL 미국배당미국채혼합50",
        "weight": 0.40
    }
}

def order_time():
    """거래회차 확인 1~12회차""" 
    # 현재 날짜와 시간 확인 UTC시간대
    now = datetime.now()
    current_date = now.date()
    current_time = now.time()

    # 수정: 모든 키를 미리 초기화
    result = {
        'date': current_date,
        'time': current_time.strftime("%H:%M:%S"),
        'round': 0,        # 기본값
        'total_round': 12  # 기본값
    }
    
    # UTC 기준: 1회차=00:03, 12회차=05:33, 30분 간격
    current_total_min = current_time.hour * 60 + current_time.minute
    start_min = 0 * 60    # UTC 00:00 (KST 09:00) 시작시간 crontab 조정 시 유연하게
    end_min   = 5 * 60 + 50   # UTC 05:50 (KST 14:50) 종료시간 crontab 조정 시 유연하게

    if start_min <= current_total_min <= end_min:
        result['round'] = ((current_total_min - start_min) // 30) + 1
        result['round'] = min(result['round'], 12)   # 최대 12회차 cap
    else:
        result['round'] = 0

    return result

def health_check():
    """시스템 상태 확인"""
    checks = []
    
    # 1. API 토큰 유효성
    if not KIS.access_token:
        checks.append("IRP체크: API 토큰 없음")
    
    # 2. 네트워크 연결
    try:
        import socket
        socket.create_connection(("openapi.koreainvestment.com", 9443), timeout=5)
    except:
        checks.append("IRP체크: KIS API 서버 접속 불가")
        
    # 3. 거래가능일 체크
    checkday = KIS.is_KR_trading_day()
    if checkday == False:
        checks.append("IRP체크: 거래일이 아닙니다.")
    
    if checks:
        TA.send_tele(checks)
        sys.exit(0)
    
def save_json(data, path, order):
    """
    저장 실패 시에도 백업 파일 생성
    """
    result_msgs = []
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        result_msgs.append(f"{order['date']} {order['round']}/{order['total_round']}회차 저장 완료: {path}")
    except Exception as e:
        result_msgs.append(f"{path} 저장 실패: {e}")
        backup_path = f"/var/autobot/TR_IRP/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            result_msgs.append(f"백업 파일 생성: {backup_path}")
        except Exception as backup_error:
            result_msgs.append(f"백업 실패: {backup_error}")
    return result_msgs   # 새 리스트 반환
    
def split_data(round):
    '''회차별 분할횟수와 분할당 가격산출'''
    if round == 1:
        sell_splits = 5
        sell_price = [1.025, 1.020, 1.015, 1.010, 1.005]
        buy_splits = 6
        buy_price = [0.970, 0.975, 0.980, 0.985, 0.990, 1.000]
    elif round == 2:
        sell_splits = 5
        sell_price = [1.025, 1.020, 1.015, 1.010, 1.000]
        buy_splits = 5
        buy_price = [0.975, 0.980, 0.985, 0.990, 0.995]
    elif round == 3:
        sell_splits = 4
        sell_price = [1.020, 1.015, 1.010, 1.005]
        buy_splits = 5
        buy_price = [0.975, 0.980, 0.985, 0.990, 1.000]
    elif round == 4:
        sell_splits = 4
        sell_price = [1.020, 1.015, 1.010, 1.000]
        buy_splits = 4
        buy_price = [0.980, 0.985, 0.990, 0.995]
    elif round == 5:
        sell_splits = 3
        sell_price = [1.015, 1.010, 1.005]
        buy_splits = 4
        buy_price = [0.980, 0.985, 0.990, 1.000]
    elif round == 6:
        sell_splits = 3
        sell_price = [1.015, 1.010, 1.000]
        buy_splits = 3
        buy_price = [0.985, 0.990, 0.995]
    elif round == 7:
        sell_splits = 2
        sell_price = [1.010, 1.005]
        buy_splits = 3
        buy_price = [0.985, 0.990, 1.000]
    elif round == 8:
        sell_splits = 2
        sell_price = [1.010, 1.000]
        buy_splits = 2
        buy_price = [0.990, 0.995]
    elif round == 9:
        sell_splits = 1
        sell_price = [1.005]
        buy_splits = 2
        buy_price = [0.990, 1.000]
    elif round == 10:
        sell_splits = 1
        sell_price = [1.000]
        buy_splits = 1
        buy_price = [0.995]
    elif round == 11:
        sell_splits = 1
        sell_price = [0.980]
        buy_splits = 1
        buy_price = [1.000]
    elif round == 12:
        sell_splits = 0 # 12회차은 매도 주문은 없음
        sell_price = []
        buy_splits = 1
        buy_price = [1.020]
    else:
        # 유효하지 않은 회차
        raise ValueError(f"유효하지 않은 회차: {round}")
        
    round_split = {
        "sell_splits": sell_splits, 
        "sell_price": sell_price,
        "buy_splits": buy_splits, 
        "buy_price": buy_price
    }

    return round_split

def cancel_orders(side: str="all"):
    """모든 주문 취소"""
    summary = KIS.cancel_all_KR_unfilled_orders(side)
    if isinstance(summary, dict):
        cancel_message = f"IRP: {summary['success']}/{summary['total']} 주문 취소 성공"
    else:
        cancel_message = f"IRP: 주문 취소 에러발생"
    return cancel_message

def target_invest(target: dict, this_krw_asset: float):
    # 종목별 목표 투자금액 및 수량 산출
    # ✅ 각 종목의 weight는 전체 자산 대비 비중 (CASH 포함 합계 = 100%)
    #    → target_invest = this_krw_asset × weight  (직접 곱)
    # ❌ total_invest(= this_krw_asset × stock_weight)를 경유하면 이중 축소됨
    #    예) CASH=50%, 종목 각 5% → total_invest×5% = 총자산×2.5% (의도의 절반)
    target_code = list(target.keys())
    total_weight = sum(v['weight'] for v in target.values())
    if abs(total_weight - 1.0) > 0.01:   # 1% 오차 허용
        TA.send_tele(f"IRP경고: weight 합계 = {total_weight:.3f} (1.0 아님). 계속 진행합니다.")

    for i in target_code:
        if i == "CASH":                                   # CASH는 주식 아님 → 스킵
            target[i]['target_invest'] = int(target[i]['weight'] * this_krw_asset)
            target[i]['target_qty'] = 0
            continue
        price = KIS.get_KR_current_price(i)
        if price == 0 or not isinstance(price, int):
            TA.send_tele(f"IRP: 현재가 조회 불가로 종료합니다. ({price})")
            sys.exit(1)
        target[i]['target_invest'] = int(target[i]['weight'] * this_krw_asset)  # 투자 금액(현금+주식) 기준
        target[i]['target_qty'] = target[i]['target_invest'] // price
        time_module.sleep(0.1)   
    return target, target_code

def hold_invest():
    # 보유 종목 잔고 불러오기
    stocks = KIS.get_KR_stock_balance()
    if not isinstance(stocks, list):
        TA.send_tele(f"IRP: 잔고 조회 불가로 종료합니다. ({stocks})")
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
    return hold, hold_code

# ==========================
# 메인 로직 # 리밸런싱
# ==========================
message = [] # 출력메시지 LIST 생성
health_check() # 시스템 상태 확인

# 일자와 회차 시간데이터 불러오기
order = order_time() 
if order['round'] == 0:
    TA.send_tele(f"IRP: 매매시간이 아닙니다.")
    sys.exit(0)
message.append(f"IRP: {order['date']}, {order['time']}, {order['round']}/{order['total_round']}회차 매매 시작")

# 전회 주문 취소
cancel_message = cancel_orders(side='all')
message.append(cancel_message)

# 1회차 투자 목표 매매 수량 파악
if order['round'] == 1:
    # 총 원화 평가금액 불러오기
    account = KIS.get_KR_account_summary()
    if not isinstance(account, dict):
        TA.send_tele(f"IRP: 총 원화평가금 조회 불가로 종료합니다. ({account})")
        sys.exit(1)
    total_krw_asset = account['total_krw_asset']  # nass_amt (주식평가금 + D+2 현금 합계)
    message.append(f"IRP총자산: {int(total_krw_asset):,}원 (주식:{int(account['stock_eval_amt']):,} + 현금:{int(account['cash_balance']):,})")

    # 당일 target 투자금액 및 목표 산출 및 저장하기
    this_krw_asset = total_krw_asset
    message.append(f"IRP이번 투자기준금: {int(this_krw_asset):,}원")

    target, target_code = target_invest(target, this_krw_asset)

    # 당일 target 저장하기
    json_message = save_json(target, IRP_target_path, order)
    message.extend(json_message)

    # message 타겟 산출 메세지 전송
    TA.send_tele(message)
    time_module.sleep(1.0)
    message = []

# 2회~12회차 투자 목표 매매 수량 불러오기
elif order['round'] > 1:
    TA.send_tele(message)
    time_module.sleep(1.0)
    message = []
    try:
        with open(IRP_target_path, 'r', encoding='utf-8') as f:
            target = json.load(f)
        target_code = list(target.keys())
        for code in target_code:
            if "target_qty" in target[code]:
                target[code]["target_qty"] = int(target[code]["target_qty"])
    except Exception as e:
        TA.send_tele(f"IRP_target.json 파일 오류: {e}")
        sys.exit(1)

# 현재 잔고 수량 불러오기
hold, hold_code = hold_invest()

# 투자수량과 잔고수량 비교해서 매수매도수량 산출하기
buy = {}
sell = {}
for code in hold_code:
    if code in target_code:
        if code == "CASH":                 # CASH는 매매 대상 아님
            continue
        if target[code]["target_qty"] > hold[code]["hold_qty"]:
            buy[code] = target[code]["target_qty"] - hold[code]["hold_qty"]
        elif target[code]["target_qty"] < hold[code]["hold_qty"]:
            sell[code] = hold[code]["hold_qty"] - target[code]["target_qty"]
    else:
        sell[code] = hold[code]["hold_qty"]

for code in target_code:
    if code == "CASH":                     # CASH는 매매 대상 아님
        continue
    if code not in hold_code:
        if target[code]["target_qty"] > 0:   # ← 0주 방어
            buy[code] = target[code]["target_qty"]

# 분할 주문 수량 구하기
try:
    round_split = split_data(order['round'])
except ValueError as e:
    TA.send_tele(f"IRP: {e}")
    sys.exit(1)
sell_split = [round_split["sell_splits"], round_split["sell_price"]]
buy_split = [round_split["buy_splits"], round_split["buy_price"]]   

# 매도주문
sell_code = list(sell.keys())

if len(sell_code) == 0:
    message.append("IRP:매도 종목 없음")

elif sell_split[0] > 0:
    message.append(f"IRP: {order['round']}회차 - 매도 주문")
    for code, qty in sell.items():
        local_split_count = sell_split[0]
        local_split_price = sell_split[1][:]
        split_qty = int(qty // local_split_count)
        remainder = int(qty - split_qty * local_split_count)

        if split_qty < 1:
            local_split_count = 1
            local_split_price = [0.99]
            split_qty = int(qty)
            remainder = 0

        price = KIS.get_KR_current_price(code)
        if price == 0 or not isinstance(price, int):
            TA.send_tele(f"IRP: 현재가 조회 불가로 종료합니다. ({price})")
            sys.exit(1)

        for i in range(local_split_count):
            this_qty = split_qty + (remainder if i == local_split_count - 1 else 0)
            if this_qty < 1:
                continue
            split_price = float(price * local_split_price[i])
            order_price = KIS.round_to_tick(price=split_price, market="KR")
            order_info = KIS.order_sell_KR(code, this_qty, order_price, "00")
            if order_info is None:
                message.append(f"IRP 매도 오류: {code} API 응답 없음")
            elif order_info.get("success"):
                message.append(f"매도 {code} {this_qty}주 {order_price:,}원 주문번호:{order_info.get('order_number','')}")
            else:
                message.append(f"매도 실패 {code}: {order_info.get('error_message','')}")
            time_module.sleep(0.125)

else:
    # sell_code가 있지만 이 회차는 매도 주문 안 함 (12회차 등)
    message.append(f"IRP: {order['round']}회차 - 매도 주문 없음 (분할횟수 0)")

# 회차별 매도 메세지 telegram 출력
TA.send_tele(message)
message = []

# 매도 매수 시간딜레이
time_module.sleep(600)
# 매수구간 전환
# 주문가능 금액 조회 및 주문수량 구하기
# ✅ get_KR_orderable_cash()는 nrcvb_buy_amt (미수없는 매수가능금액) 반환
#    → D+2 정산대금 포함, 당일 매도 체결분도 반영 → 수동 보정 불필요
KRW = KIS.get_KR_orderable_cash()
if not isinstance(KRW, (int, float)):
    TA.send_tele(f"IRP: 주문가능현금 조회 불가로 종료합니다. ({KRW})")
    sys.exit(1)

orderable_KRW = float(KRW)   # nrcvb_buy_amt: 미수없는 매수가능금액 (D+2 정산 포함)
target_KRW = 0
buy_prices = {}                                              # 현재가 저장
buy_price_rate = buy_split[1][-1] if buy_split[1] else 1.0  # 최대 배율 기준

for code, qty in buy.items():
    price = KIS.get_KR_current_price(code)
    if not isinstance(price, int) or price == 0:
        TA.send_tele(f"IRP: 현재가 조회 불가로 종료합니다. ({price})")
        sys.exit(1)
    buy_prices[code] = price                                 # 저장
    ticker_invest = price * buy_price_rate * qty             # 최대 배율 반영
    target_KRW += ticker_invest
    time_module.sleep(0.125)

# ── 디버그: 매수 가능금액 vs 목표 매수금 비교 로그 ──────────────────────────
message.append(
    f"IRP매수가능: {int(orderable_KRW):,}원 | 목표매수금: {int(target_KRW):,}원"
    + (f" | 조정비율: {orderable_KRW/target_KRW:.4f}" if target_KRW > 0 else "")
)
# ────────────────────────────────────────────────────────────────────────────

if target_KRW > orderable_KRW:
    adjust_rate = orderable_KRW / target_KRW
    for ticker, ticker_qty in buy.items():
        adjusted = int(ticker_qty * adjust_rate)
        buy[ticker] = adjusted

    buy = {ticker: qty for ticker, qty in buy.items() if qty > 0}   # 0주 제거
    buy_code = list(buy.keys())
    message.append(f"IRP 매수수량 조정 완료 (adjust_rate={adjust_rate:.4f})")
else:
    message.append("IRP 매수가능금 충분 → 수량 조정 없음")

# 매수주문
buy = {code: qty for code, qty in buy.items() if qty > 0}  # 방어적 0주 제거
buy_code = list(buy.keys())

if len(buy_code) == 0:
    message.append("IRP:매수 종목 없음")

elif len(buy_code) > 0 and buy_split[0] > 0:
    message.append(f"IRP: {order['round']}회차 - 매수 주문")
    for code, qty in buy.items():
        local_split_count = buy_split[0]
        local_split_price = buy_split[1][:]
        split_qty = int(qty // local_split_count)
        remainder = int(qty - split_qty * local_split_count)

        if split_qty < 1:
            if qty < 1:
                message.append(f"IRP매수 스킵: {code} 수량 0주 (조정후 제거대상)")
                continue
            local_split_count = 1
            local_split_price = [1.01]
            split_qty = int(qty)
            remainder = 0

        price = buy_prices.get(code)
        if not isinstance(price, int) or price == 0:
            TA.send_tele(f"IRP: 현재가 없음으로 종료합니다. ({code})")
            sys.exit(1)

        for i in range(local_split_count):
            this_qty = split_qty + (remainder if i == local_split_count - 1 else 0)
            if this_qty < 1:
                continue
            split_price = float(price * local_split_price[i])
            order_price = KIS.round_to_tick(price=split_price, market="KR")
            order_info = KIS.order_buy_KR(code, this_qty, order_price, "00")
            if order_info is None:
                time_module.sleep(2)
                order_info = KIS.order_buy_KR(code, this_qty, order_price, "00")
            if order_info is None:
                message.append(f"IRP매수 오류: {code} {this_qty}주 {order_price:,}원 API 응답 없음")
            elif order_info.get("success"):
                message.append(f"매수 {code} {this_qty}주 {order_price:,}원 주문번호:{order_info.get('order_number','')}")
            else:
                message.append(f"매수 실패 {code} {this_qty}주 {order_price:,}원: {order_info.get('error_message','')}")
            time_module.sleep(0.125)

# 회차별 매수 메세지 telegram 출력
TA.send_tele(message)
message = []

# 최종 매매 데이터 telegram 출력 및 Google sheet 전략별 잔고 - 종목별 매입량 매입가 기록
if order['round'] == 12:
    time_module.sleep(300)
    # 전회 주문 취소
    cancel_message = cancel_orders(side='all')
    message.append(cancel_message)
    message.append(f"IRP {order['date']} 리밸런싱 종료")

    # 보유 종목 잔고 불러오기
    stocks = KIS.get_KR_stock_balance()
    if not isinstance(stocks, list):
        TA.send_tele(f"IRP: 잔고 조회 불가로 종료합니다. ({stocks})")
        sys.exit(1)
    if len(stocks) < 7:
        TA.send_tele(f"IRP: 잔고 종목 수가 target 종목수 7개보다 작음. ({len(stocks)})")

    account = KIS.get_KR_account_summary()
    if not isinstance(account, dict):
        TA.send_tele(f"IRP: 총 원화평가금 조회 불가로 종료합니다. ({account})")
        sys.exit(1)
    total_asset = account["total_krw_asset"]
    cash_balance = account["cash_balance"]
    stock_eval_amt = account["stock_eval_amt"]
    result = {}
    result["total"] = {
        "date": str(order['date']),
        "total_balance": total_asset,
        "cash_balance": cash_balance,
        "stock_eval_amt": stock_eval_amt
    }
    result["stocks"] = {}
    target_code = list(target.keys())
    for stock in stocks:
        code = stock["종목코드"]
        if code not in target_code:
            message.append(f"IRP: {stock['종목명']}는 target 리스트에 없는 이상 종목임.({stock['종목코드']})")
            continue
        target_weight = target[code]['weight']
        hold_weight = float(stock["평가금액"] / total_asset)
        result["stocks"][code] = {
            "name": stock["종목명"],
            "hold_balance": stock["평가금액"],
            "hold_qty": stock["보유수량"],
            "target_weight": target_weight,
            "hold_weight": round(hold_weight, 4)
        }

    # 전략결과 저장
    try:
        json_message = save_json(result, IRP_result_path, order)
        message.extend(json_message)
    except Exception as e:
        error_msg = f"IRP_result.json 저장 실패: {e}"
        TA.send_tele(error_msg)
    time_module.sleep(1.0)
        
    # data 정제
    tele_data = {
        "total": {
            "date": result["total"]["date"],
            "total_balance": f"{int(total_asset)}원",
            "cash_balance": f"{int(cash_balance)}원",
            "stock_eval_amt": f"{int(stock_eval_amt)}원"
        }
    }
    tele_data["stocks"] = {}
    for stock in stocks:
        code = stock["종목코드"]
        if code not in target_code:
            continue
        target_weight = target[code]['weight']
        hold_weight = float(stock["평가금액"] / total_asset)
        tele_data["stocks"][code] = {
            "name": stock["종목명"],
            "hold_balance": f"{int(stock['평가금액'])}원",
            "hold_qty": int(stock["보유수량"]),
            "target_weight": f"{target_weight*100:.1f}%",
            "hold_weight":   f"{hold_weight*100:.1f}%"
        } 

    # telegram message
    message.append(
        f"📊 IRP최종잔고 {tele_data['total']['date']}\n"
        f"총자산: {tele_data['total']['total_balance']} | "
        f"주식: {tele_data['total']['stock_eval_amt']} | "
        f"현금: {tele_data['total']['cash_balance']}"
    )
    # 종목별 출력
    for code, info in tele_data["stocks"].items():
        message.append(
            f"{info['name']}({code}): "
            f"{info['hold_qty']}주 {info['hold_balance']} "
            f"[목표:{info['target_weight']} 실제:{info['hold_weight']}]"
        )

    TA.send_tele(message)

sys.exit(0)