import json
import datetime
import time
import KIS_US

# 매월 마지막거래일 crontab 설정시간 19시에 예약 실행
# USLA data 불러오기
USLA_data_path = "C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/USLA_data.json"    
try:
    with open(USLA_data_path, 'r', encoding='utf-8') as f:
        USLA_data = json.load(f)
except Exception as e:
    print(f"JSON 파일 오류: {e}")
    # KA.SendMessage(f"{} JSON 파일 오류: {e}")
    exit()

# Json데이터에서 holding ticker와 quantity 구하기
holding = dict(zip(USLA_data['ticker'], USLA_data['quantity']))
tickers = list(holding.keys())

# 'BIL'종목 보유 확인 후 시가 매도
if 'BIL' in tickers:
    # Account연결 data
    key_file_path = "C:/Users/ilpus/Desktop/NKL_invest/kis63721147nkr.txt"
    token_file_path = "C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/kis63721147_token.json"
    cano = "63721147" # 종합계좌번호 (8자리)
    acnt_prdt_cd = "01"  # 계좌상품코드 (2자리)

    # Instance 생성
    kis = KIS_US.KIS_API(key_file_path, token_file_path, cano, acnt_prdt_cd)

    response = kis.order_sell_US(ticker ='BIL', quantity = int(holding['BIL']), price = 0, exchange = None, ord_dvsn = "33")
    # 응답 처리
    if response.status_code == 200:
        result = response.json()        
        if result.get('rt_cd') == '0':  # 성공
            ORNO = result['output']['ODNO']
            print(f"주문번호: {ORNO}")
            print(f"주문시각: {result['output']['ORD_TMD']}")
        else:  # API 호출 성공했지만 주문 실패
            print(f"주문 실패: {result.get('msg1')}")
    else:
        print(f"API 호출 실패: {response.status_code}")

    now = datetime.datetime.now()
    target_time = now.replace(hour=21, minute=10, second=0, microsecond=0)

    while True:
        now = datetime.datetime.now()
        if now >= target_time:
            break
        time.sleep(300)  # 5분마다 현재 시간 체크

    # 체결확인  
    execution = kis.check_order_execution(order_number = ORNO, ticker ='BIL', wait_seconds=1)
    if execution and execution['success']:
        print(f"종목: {execution['name']} \n수량: {execution['qty']} \n단가: ${execution['price']} \n유형: {execution['order_type']}")
        print(f"체결금액: ${execution['amount']} \n체결상태: {execution['status']}")
        amount = execution['amount']
        now = datetime.datetime.now()

        try:
            with open(USLA_data_path, 'r', encoding='utf-8') as f:
                USLA_data = json.load(f)
        except Exception as e:
            print(f"JSON 파일 오류: {e}")

        USLA_data["date"] = now.strftime('%Y-%m-%d')

        # 1"BIL"의 인덱스 찾기
        idxBIL = USLA_data["ticker"].index("BIL")
        idxCASH = USLA_data["ticker"].index("CASH")

        balance = amount + USLA_data["quantity"][idxCASH]

        # 2️해당 인덱스를 ticker와 quantity에서 동시에 삭제
        USLA_data["ticker"].pop(idxBIL)
        USLA_data["quantity"].pop(idxBIL)

        # Upbit_data.json파일 생성
        try:
            with open(USLA_data_path, 'w', encoding='utf-8') as f:
                json.dump(USLA_data, f, ensure_ascii=False, indent=4)

        except Exception as e:
            print(f"JSON 파일 오류: {e}")

else:
    exit()
