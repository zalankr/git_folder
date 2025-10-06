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
    exit()

# Json데이터에서 holding ticker와 quantity 구하기
holding = dict(zip(USLA_data['ticker'], USLA_data['quantity']))
tickers = list(holding.keys())

# 'BIL'종목 보유 확인 후 시가 매도
if 'BIL' not in tickers:
    print("BIL 종목이 없습니다. 프로그램 종료.")
    exit()

# Account연결 data
key_file_path = "C:/Users/ilpus/Desktop/NKL_invest/kis63721147nkr.txt"
token_file_path = "C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/kis63721147_token.json"
cano = "63721147"
acnt_prdt_cd = "01"

# Instance 생성
kis = KIS_US.KIS_API(key_file_path, token_file_path, cano, acnt_prdt_cd)

# BIL 매도 주문
response = kis.order_sell_US(
    ticker='BIL', 
    quantity=int(holding['BIL']), 
    price=0, 
    exchange=None, 
    ord_dvsn="33"
)

# 응답 처리
ORNO = None  # 초기화

if response.status_code == 200:
    result = response.json()
    
    if result.get('rt_cd') == '0':  # 성공
        ORNO = result['output']['ODNO']
        print(f"주문번호: {ORNO}")
        print(f"주문시각: {result['output']['ORD_TMD']}")
    else:
        print(f"주문 실패: {result.get('msg1')}")
        exit()
else:
    print(f"API 호출 실패: {response.status_code}")
    exit()

# 주문 실패 시 종료 확인
if ORNO is None:
    print("주문번호를 받지 못했습니다. 프로그램 종료.")
    exit()

# 21:10까지 대기 (개선된 로직)
now = datetime.datetime.now()
target_time = now.replace(hour=21, minute=10, second=0, microsecond=0)

# 이미 21:10 이후면 다음날 21:10 설정
if now >= target_time:
    target_time += datetime.timedelta(days=1)

print(f"{target_time.strftime('%Y-%m-%d %H:%M:%S')}까지 대기 중...")

while True:
    now = datetime.datetime.now()
    if now >= target_time:
        break
    
    remaining = (target_time - now).total_seconds()
    
    # 남은 시간이 5분 이하면 1분마다, 그 외엔 5분마다 체크
    sleep_time = min(60 if remaining <= 300 else 300, remaining)
    time.sleep(sleep_time)

print("대기 완료. 체결 확인 시작...")

# 체결 확인  
execution = kis.check_order_execution(
    order_number=ORNO, 
    ticker='BIL', 
    wait_seconds=1
)

if execution and execution['success']:
    print(f"종목: {execution['name']}, 수량: {execution['qty']}")
    print(f"단가: ${execution['price']}, 유형: {execution['order_type']}")
    print(f"체결금액: ${execution['amount']}, 체결상태: {execution['status']}")
    
    # 문자열을 float으로 변환 (타입 안전)
    try:
        amount = float(execution['amount'])
    except (ValueError, TypeError):
        print(f"체결금액 변환 실패: {execution['amount']}")
        exit()
    
    now = datetime.datetime.now()
    
    # JSON 파일 다시 읽기
    try:
        with open(USLA_data_path, 'r', encoding='utf-8') as f:
            USLA_data = json.load(f)
    except Exception as e:
        print(f"JSON 파일 읽기 오류: {e}")
        exit()
    
    # 날짜 업데이트
    USLA_data["date"] = now.strftime('%Y-%m-%d')
    
    # BIL과 USLA_CASH 인덱스 찾기
    try:
        idxBIL = USLA_data["ticker"].index("BIL")
        idxCASH = USLA_data["ticker"].index("USLA_CASH")
    except ValueError as e:
        print(f"종목 인덱스 찾기 실패: {e}")
        exit()
    
    # USLA_CASH 잔액 계산 (타입 안전)
    try:
        current_cash = float(USLA_data["quantity"][idxCASH])
        balance = amount + current_cash
    except (ValueError, TypeError) as e:
        print(f"잔액 계산 오류: {e}")
        exit()
    
    # BIL 삭제
    USLA_data["ticker"].pop(idxBIL)
    USLA_data["quantity"].pop(idxBIL)
    
    # USLA_CASH 업데이트 (idxCASH가 BIL보다 뒤에 있으면 인덱스 조정)
    if idxCASH > idxBIL:
        idxCASH -= 1  # BIL 삭제로 인덱스가 하나 앞당겨짐
    
    USLA_data["quantity"][idxCASH] = balance
    
    print(f"\nUSLA_CASH 업데이트: ${current_cash:.2f} → ${balance:.2f}")
    
    # JSON 파일 저장
    try:
        with open(USLA_data_path, 'w', encoding='utf-8') as f:
            json.dump(USLA_data, f, ensure_ascii=False, indent=4)
        print(f"JSON 파일 저장 완료: {USLA_data_path}")
    except Exception as e:
        print(f"JSON 파일 저장 오류: {e}")
        exit()
        
else:
    print("체결 확인 실패")
    exit()

print("\n모든 작업 완료!")
