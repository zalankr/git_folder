from datetime import datetime, timedelta
import json

"""
crontab 설정
1. 25년~26년 1년치 월 첫 거래일 USAA(USLA+HAA) Rebalancing
*/5 9-21 1 11 * python3 /TR_KIS/KIS_Trading.py 일반 시간대 UTC 21시 정규장 종료 > 장종류 time.sleep하고 난 후주문 취소 체결확인 기록 등 시행 
*/5 8-20 1 4 * python3 /TR_KIS/KIS_Trading.py 서머타임 시간대 UTC 20시 정규장 종료 > 장종류 time.sleep하고 난 후주문 취소 체결확인 기록 등 시행 
2. 25년~26년 1년치 월 마지막 거래일 USAA(USLA+HAA) 'BIL'매도 후 USD CASH로 전환(이자수익용 BIL)
30 20 31 10 * python3 /TR_KIS/KIS_Trading.py 일반 시간대 UTC 21시 정규장 종료 > 장종류 time.sleep하고 난 후주문 취소 체결확인 기록 등 시행 
30 19 31 3 * python3 /TR_KIS/KIS_Trading.py 서머타임 시간대 UTC 20시 정규장 종료 > 장종류 time.sleep하고 난 후주문 취소 체결확인 기록 등 시행 
"""

# 현재 일자시간 확인(실제 구문에서는 심플하게, 로컬에서는 utcnow로)
def get_current():
    '''현재 UTC 날짜와 시간 정보를 딕셔너리로 반환'''
    current = datetime.utcnow() # now = datetime.now()
    current_date = current.date()
    current_time = current.time()
    now = {
        'date': current_date,
        'time': current_time,
        'year': current_date.year,
        'month': current_date.month,
        'day': current_date.day,
        'hour': current_time.hour,
        'minute': current_time.minute
    }
    return now

def USAA_rebalancing_day_Making(USAA_summer, USAA_winter):
    """USAA 리밸런싱 날짜를 JSON 파일로 저장"""
    # 날짜 문자열을 date 객체로 변환
    USAA_summer_dates = []
    for d in USAA_summer:
        date_obj = datetime.strptime(d, "%Y-%m-%d").date()
        USAA_summer_dates.append(date_obj)

    USAA_winter_dates = []
    for d in USAA_winter:
        date_obj = datetime.strptime(d, "%Y-%m-%d").date()
        USAA_winter_dates.append(date_obj)

    # JSON 저장용 딕셔너리 (date를 다시 문자열로 변환)
    rebalancing_data = {
        "summer_dst": [d.strftime("%Y-%m-%d") for d in USAA_summer_dates],
        "winter_standard": [d.strftime("%Y-%m-%d") for d in USAA_winter_dates]
    }
    
    # JSON 파일로 저장
    file_path = "C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/USAA_rebalancing_day.json"
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(rebalancing_data, f, ensure_ascii=False, indent=4)
        
        print(f"USAA_rebalancing_day.json 파일 저장 완료: {file_path}")
        return rebalancing_data
        
    except Exception as e:
        print(f"JSON 파일 저장 오류: {e}")
        return None

def check_USAA_rebalancing(now):
    '''오늘이 USAA 리밸런싱일인지 확인'''
    USAA_rebalancing_day_path = 'C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/USAA_rebalancing_day.json'

    try:
        with open(USAA_rebalancing_day_path, 'r', encoding='utf-8') as f:
            USAA_rebalancing_day = json.load(f)
    except Exception as e:
        print(f"JSON 파일 오류: {e}")

    if str(now['date']) in USAA_rebalancing_day["summer_dst"] or now['date'] in USAA_rebalancing_day["summer_dst"]:
        print("today is summer_dst")
        return "USAA_summer_rebalancing"
    elif str(now['date']) in USAA_rebalancing_day["winter_standard"] or now['date'] in USAA_rebalancing_day["winter_standard"]:
        print("today is winter_standard")
        return "USAA_winter_rebalancing"
    else:
        print("today is not rebalancing day")
        return "USAA_not_rebalancing"
    

# 실행
if __name__ == "__main__":
    # USAA Rebalancing day list 기입하기
    USAA_summer = ["2026-04-01", "2026-05-01", "2026-06-01", "2026-07-01", "2026-08-03", "2026-09-01", "2026-10-01"]
    USAA_winter = ["2025-11-03", "2025-12-01", "2026-01-02", "2026-02-02", "2026-03-02"]

    result = USAA_rebalancing_day_Making(USAA_summer, USAA_winter)
    print(result)