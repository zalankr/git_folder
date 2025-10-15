from datetime import datetime, timedelta
import json
import KIS_Calender
import USLA_model
import KIS_US

"""
crontab 설정
1. 25년~26년 1년치 월 첫 거래일 USAA(USLA+HAA) Rebalancing
*/5 9-21 1 11 * python3 /TR_KIS/KIS_Trading.py 일반 시간대 UTC 21시 정규장 종료 > 장종류 time.sleep하고 난 후주문 취소 체결확인 기록 등 시행 
*/5 8-20 1 4 * python3 /TR_KIS/KIS_Trading.py 서머타임 시간대 UTC 20시 정규장 종료 > 장종류 time.sleep하고 난 후주문 취소 체결확인 기록 등 시행 
2. 25년~26년 1년치 월 마지막 거래일 USAA(USLA+HAA) 'BIL'매도 후 USD CASH로 전환(이자수익용 BIL)
30 20 31 10 * python3 /TR_KIS/KIS_Trading.py 일반 시간대 UTC 21시 정규장 종료 > 장종류 time.sleep하고 난 후주문 취소 체결확인 기록 등 시행 
30 19 31 3 * python3 /TR_KIS/KIS_Trading.py 서머타임 시간대 UTC 20시 정규장 종료 > 장종류 time.sleep하고 난 후주문 취소 체결확인 기록 등 시행 
"""

# USLA모델 instance 생성
key_file_path = "C:/Users/ilpus/Desktop/NKL_invest/kis63721147nkr.txt"
token_file_path = "C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/kis63721147_token.json"
cano = "63721147"  # 종합계좌번호 (8자리)
acnt_prdt_cd = "01"  # 계좌상품코드 (2자리)
USLA = USLA_model.USLA_Model(key_file_path, token_file_path, cano, acnt_prdt_cd)

# 날짜를 받아 USAA 리밸런싱일이 맞는 지, summer or winter time 시간대인지 확인
# 리밸런싱일인 경우 시간을 받아 장전, 장중거래 시간대인지, 거래회차는 몇회차인지 확인
# 밑에 부분 테스트용, 정식버전은 KIS_Calender해당 메써드의 current_date, current_time 수정
order_time = KIS_Calender.check_order_time()
print(f"USLA {order_time['market']} 리밸런싱 {order_time['round']}/{order_time['total_round']}회차")
print(f"{order_time['date']}, {order_time['season']} 리밸런싱 {order_time['market']} \n{order_time['time']} {order_time['round']}/{order_time['total_round']}회차 거래입니다.")

# USAA 리밸런싱일인 경우
if order_time['season'] in ["USAA_summer", "USAA_winter"]:
    # Rebalancing 1회차에만 Trading data 만들기
    if order_time['market'] == "Pre-market" and order_time['round'] == 1:
        TR_data = USLA.USLA_trading_data(order_time)

        TR_data_meta = TR_data.pop('meta_data')
        TR_data_ticker = TR_data
        
        print("USLA Model Trading Data")
        print(TR_data_meta['date'])
        print(TR_data_meta['time'])
        print(TR_data_meta['model'])
        print(TR_data_meta['season'])
        print(TR_data_meta['market'])
        print(TR_data_meta['round'])
        print(TR_data_meta['total_round'])


        for ticker in TR_data_ticker:
            print(ticker, TR_data_ticker[ticker])

    




else:
    exit()    



