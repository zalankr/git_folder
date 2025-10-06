import json
from datetime import datetime
import USLA
import KIS_US

# 매월 첫거래일 crontab 설정시간에 예약 실행
# Account연결 data
key_file_path = "C:/Users/ilpus/Desktop/NKL_invest/kis63721147nkr.txt"
token_file_path = "C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/kis63721147_token.json"
cano = "63721147"  # 종합계좌번호 (8자리)
acnt_prdt_cd = "01"  # 계좌상품코드 (2자리)

# Instance 생성
kis = KIS_US.KIS_API(key_file_path, token_file_path, cano, acnt_prdt_cd)
usla = USLA.USLAS()

# USLA data 불러오기
def get_USLA_data():
    USLA_data_path = "C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/USLA_data.json"    
    try:
        with open(USLA_data_path, 'r', encoding='utf-8') as f:
            USLA_data = json.load(f)
        return USLA_data

    except Exception as e:
        print(f"JSON 파일 오류: {e}")
        exit()

# USD 환산 잔고 계산
def calculate_USD_value(holding):
    holding_USD_value = 0
    for t in holding.keys():
        if t == "USLA_CASH":
            holding_USD_value += holding[t]
        else:
            price = kis.get_US_current_price(t)
            value = price * holding[t] * (1 - usla.tax_rate)
            holding_USD_value += value

    return holding_USD_value

# USLA 모델 실행, target ticker와 weight 구하기
def invest_target():
    invest = usla.run_strategy()
    target = {
        ticker: weight 
        for ticker, weight in invest['allocation'].items() 
        if weight > 0
    }

    return target

# target비중에 맞춰 보유 $환산금액을 곱해서 현재가로 나누기 > ticker별 수량 반환+USD금액 반환
def calculate_target_quantity(target, target_usd_value):
    target_quantity = {}
    target_stock_value = 0
    for ticker in target.keys():
        if ticker != "USLA_CASH":
            try:
                price = kis.get_US_current_price(ticker)
                if price and price > 0:
                    target_quantity[ticker] = int(target_usd_value[ticker] / price)
                    target_stock_value += target_quantity[ticker] * price * (1 + usla.tax_rate)
                else:
                    print(f"{ticker}: 가격 정보 없음")
                    target_quantity[ticker] = 0
            except Exception as e:
                print(f"{ticker}: 수량 계산 오류 - {e}")
                target_quantity[ticker] = 0

    target_quantity["USLA_CASH"] = sum(target_usd_value.values()) - target_stock_value

    return target_quantity, target_stock_value

# trading할 ticker별 매수매도량 구하기
def trading_ticker(holding_ticker, holding, target_ticker, target_quantity):
    sell_ticker = {}
    buy_ticker = {}
    keep_ticker = {}

    for hold in holding_ticker:
        if hold not in target_ticker:
            sell_ticker[hold] = holding[hold]
        else:
            edited_quantity = target_quantity[hold] - holding[hold]
            if edited_quantity > 0:
                buy_ticker[hold] = edited_quantity
            elif edited_quantity < 0:
                sell_ticker[hold] = -edited_quantity
            elif edited_quantity == 0:
                keep_ticker[hold] = holding[hold]

    for target in target_ticker:
        if target not in holding_ticker:
            buy_ticker[target] = target_quantity[target]

    return sell_ticker, buy_ticker, keep_ticker

# Kis_TR_data JSON 생성 및 저장
def create_kis_tr_data(holding, target_quantity, sell_ticker, buy_ticker):
    """
    거래 데이터를 JSON 형식으로 생성
    
    Parameters:
    holding: 현재 보유 수량
    target_quantity: 목표 수량
    sell_ticker: 매도할 티커와 수량
    buy_ticker: 매수할 티커와 수량
    """
    kis_tr_data = []
    
    # 모든 관련 티커 수집 (CASH 제외)
    all_tickers = set(holding.keys()) | set(target_quantity.keys())
    all_tickers.discard("USLA_CASH")
    
    for ticker in sorted(all_tickers):
        # 포지션 결정
        if ticker in buy_ticker:
            position = "Buy"
        elif ticker in sell_ticker:
            position = "Sell"
        else:
            position = "Hold"
        
        # 수량 정보
        hold_amount = holding.get(ticker, 0)
        target_amount = target_quantity.get(ticker, 0)
        tr_quantity = target_amount - hold_amount
        
        ticker_data = {
            "ticker": ticker,
            "position": position,
            "target_amount": target_amount,
            "hold_amount": hold_amount,
            "TR_quantity": tr_quantity,
            "order_quantity": 0,
            "filled_quantity": 0,
            "unfilled_quantity": 0,
            "pending_order": 0
        }
        
        kis_tr_data.append(ticker_data)
    
    # CASH 정보 추가
    USLA_cash_data = {
        "ticker": "USLA_CASH",
        "position": "USLA_Cash",
        "target_amount": round(target_quantity.get("USLA_CASH", 0), 2),
        "hold_amount": round(holding.get("USLA_CASH", 0), 2),
        "TR_quantity": "",
        "order_quantity": "",
        "filled_quantity": "",
        "unfilled_quantity": "",
        "pending_order": ""
    }
    kis_tr_data.append(USLA_cash_data)
    
    return kis_tr_data

# Kis_TR_data JSON 파일로 저장
def save_kis_tr_json(kis_tr_data):
    """Kis_TR_data를 JSON 파일로 저장"""
    file_path = "C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/Kis_TR_data.json"
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(kis_tr_data, f, ensure_ascii=False, indent=4)
        print(f"\n✓ Kis_TR_data.json 파일 저장 완료: {file_path}")
        return True
    except Exception as e:
        print(f"\n✗ JSON 파일 저장 오류: {e}")
        return False

# Kis_TR_data를 표 형식으로 출력
def print_tr_table(kis_tr_data):
    """거래 데이터를 표 형식으로 출력"""
    print("\n" + "="*120)
    print("Kis Trading Data Table")
    print("="*120)
    
    # 헤더
    header = f"{'ticker':<8} {'position':<10} {'target':<8} {'hold':<8} {'TR qty':<8} {'order':<8} {'filled':<8} {'unfilled':<8} {'pending':<8}"
    print(header)
    print("-"*120)
    
    # 데이터
    for data in kis_tr_data:
        row = (f"{data['ticker']:<8} "
               f"{data['position']:<10} "
               f"{str(data['target_amount']):<8} "
               f"{str(data['hold_amount']):<8} "
               f"{str(data['TR_quantity']):<8} "
               f"{str(data['order_quantity']):<8} "
               f"{str(data['filled_quantity']):<8} "
               f"{str(data['unfilled_quantity']):<8} "
               f"{str(data['pending_order']):<8}")
        print(row)
    
    print("="*120)


# 메인 실행
if __name__ == "__main__":
    print("\n" + "="*60)
    print("USLA 리밸런싱")
    print(f"실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    # 최초 1회만 target비중 계산, Json데이터에서 holding ticker와 quantity 구하기 
    target = invest_target()
    target_ticker = list(target.keys())

    USLA_data = get_USLA_data()
    holding = dict(zip(USLA_data['ticker'], USLA_data['quantity']))
    holding_ticker = list(holding.keys())

    # USD 환산 잔고금액 계산
    holding_USD_value = calculate_USD_value(holding)

    # 보유 $기준 잔고를 바탕으로 목표 비중에 맞춰 ticker별 quantity 계산
    target_usd_value = {ticker: target[ticker] * holding_USD_value for ticker in target.keys()}

    # target비중에 맞춰 환산금액을 곱하고 현재가로 나누기 > ticker별 수량 반환+USD금액 반환
    target_quantity, target_stock_value = calculate_target_quantity(target, target_usd_value)
    sell_ticker, buy_ticker, keep_ticker = trading_ticker(holding_ticker, holding, target_ticker, target_quantity)

    print("\n[매도 종목]")
    print(sell_ticker)
    print("\n[매수 종목]")
    print(buy_ticker)
    print("\n[유지 종목]")
    print(keep_ticker)

    # Kis_TR_data 생성
    print("\n" + "="*60)
    print("거래 데이터 생성 중...")
    print("="*60)
    
    kis_tr_data = create_kis_tr_data(holding, target_quantity, sell_ticker, buy_ticker)
    
    # 표 형식으로 출력
    print_tr_table(kis_tr_data)
    
    # JSON 파일로 저장
    save_kis_tr_json(kis_tr_data)
#######################################################################################
    # 서머타임(DST) 확인
    is_dst = kis.is_us_dst()
    print(f"서머타임(DST): {"써머타임" if is_dst else "윈터타임"}")

    # 장전 거래 시간 확인    