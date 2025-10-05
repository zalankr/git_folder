import json
import datetime
import time
import KIS_US

# 매월 마지막거래일 crontab 설정시간 19시에 예약 실행
# Account연결 data
key_file_path = "C:/Users/ilpus/Desktop/NKL_invest/kis63721147nkr.txt"
token_file_path = "C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/kis63721147_token.json"
USLA_data_path = "C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/USLA_data.json"
cano = "63721147" # 종합계좌번호 (8자리)
acnt_prdt_cd = "01"  # 계좌상품코드 (2자리)

# Instance 생성
kis = KIS_US.KIS_API(key_file_path, token_file_path, cano, acnt_prdt_cd)

# 현재 시간에서 목표시간까지의 시간차 계산
def calculate_remaining_time(target_hour, target_minute):
    """목표 시간까지 남은 시간을 계산"""
    now = datetime.datetime.now()
    target_time = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    
    # 목표 시간이 이미 지났다면 다음 날로 설정
    if target_time <= now:
        target_time += datetime.timedelta(days=1)
    
    remaining = target_time - now
    hours, remainder = divmod(remaining.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    print(f"현재 시간: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"목표 시간: {target_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"남은 시간: {hours}시간 {minutes}분 {seconds}초")
    
    return remaining

# USLA data 불러오기    
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

# 현재 시간에서 목표시간까지의 시간차 계산
target_time = datetime.datetime.now().replace(hour=21, minute=10, second=0, microsecond=0)
if target_time < datetime.datetime.now():
    target_time += datetime.timedelta(days=1)

print(f"{target_time.strftime('%Y-%m-%d %H:%M:%S')}까지 대기 중...")

while datetime.datetime.now() < target_time:
    time.sleep(240)  # 4분 = 300초 간격으로 체크
print(f"{target_time.strftime('%Y-%m-%d %H:%M:%S')} 코드 실행을 시작합니다.")

# 체결확인








# BIL이 0으로 CASH가 +A 적용한 걸로 json 파일에 업데이트 저장