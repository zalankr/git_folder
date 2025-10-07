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

# TR Model 구분
now = KIS_Calender.get_current()
'''
1. USAA 리밸런싱 모델 구분
- 정해진 리밸런싱일에 미국증시 시간대로 crontab 실행되었는 지 확인. 이후 해당일 8-20(summer), 9-21(winter) 5분마다 실행
'''
# 밑에 부분 테스트용으로 삭제 #
now = {
    'date': datetime.strptime("2025-11-03", "%Y-%m-%d").date(),
    'time': datetime.strptime("09:00:00", "%H:%M:%S").time(),
    'year': 2025, 
    'month': 11, 
    'day': 3, 
    'hour': 9, 
    'minute': 0
    }
# 위에 부분 테스트용으로 삭제 #

# USAA 리밸런싱일 확인 후 trading
check_USAA = KIS_Calender.check_USAA_rebalancing(now)

if check_USAA == "USAA_winter_rebalancing":
    print("USAA winter 리밸런싱 모델 구동")

    # 공통 USLA모델 객체 생성
    key_file_path = "C:/Users/ilpus/Desktop/NKL_invest/kis63721147nkr.txt"
    token_file_path = "C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/kis63721147_token.json"
    cano = "63721147"  # 종합계좌번호 (8자리)
    acnt_prdt_cd = "01"  # 계좌상품코드 (2자리)
    USLA = USLA_model.USLA_Model(key_file_path, token_file_path, cano, acnt_prdt_cd)

    # USLA 리밸런싱일 최초 장전거래시간 확인 및 코드(8시59분~9시2분 사이에 구동)
    if  now['hour'] == 9 and now['minute'] <= 2 or now['hour'] == 8 and now['minute'] >= 59:
        # USLA 데이터 json파일 불러오고 > 당일 target 비중, ticker별 trading 수량 산출
        USLA_data = USLA.get_USLA_data()
        trading_data = USLA.make_trading_data(USLA_data)
        print("*"*60)
        print(trading_data['sell_ticker'])
        print(trading_data['buy_ticker'])
        print(trading_data['keep_ticker'])
        print(trading_data['hold'])
        print(trading_data['target_quantity'])

        # 최초 미국 Pre-market 주간거래 매도, 매수 주문하기
        ## Pre-market 5 split 수량 계산
        split_5_qty = dict()
        for ticker in trading_data['sell_ticker'].keys():
            split_5_qty[ticker] = int(trading_data['sell_ticker'][ticker] // 5)  # 5로 정수 나누기(나머지는 버리기)
        
        print("*"*60)
        print(split_5_qty)

        ## 매매 시 USD 변동 가치 기입


        # split_quantity = trading_data['target_quantity'] // 5  # 5로 정수 나누기(나머지는 버리기)

        ## Pre-market split 주문가격 계산

        # for ticker in trading_data['sell_ticker']:
        #     USLA.order_daytime_sell_US(ticker, split_quantity, trading_data['current_price'], exchange="NAS")

        # USLA.order_daytime_sell_US(ticker: str, quantity: int, price: float, exchange: Optional[str] = None) -> Optional[requests.Response]:


        # target_quantity, target_stock_value = USLA.calculate_target_quantity(USLA_data)

        # target비중에 맞춰 USD환산금액을 곱하고 현재가로 나누기 > ticker별 수량 반환+USD금액 반환
        
        # sell_ticker, buy_ticker, keep_ticker = USLA.trading_ticker(holding, USLA_data)








# if check_USAA == "USAA_summer_rebalancing":
#     print("USAA summer 리밸런싱 모델 구동")

#     # 공통 USLA모델 객체 생성
#     key_file_path = "C:/Users/ilpus/Desktop/NKL_invest/kis63721147nkr.txt"
#     token_file_path = "C:/Users/ilpus/Desktop/git_folder/Trading/TR_KIS/kis63721147_token.json"
#     cano = "63721147"  # 종합계좌번호 (8자리)
#     acnt_prdt_cd = "01"  # 계좌상품코드 (2자리)

#     USLA = USLA_model.USLA_Model(key_file_path, token_file_path, cano, acnt_prdt_cd)



#     # USLA 데이터 불러오기
#     USLA_data = USLA.get_USLA_data()
#     print(USLA_data)




# else:
#     pass    



