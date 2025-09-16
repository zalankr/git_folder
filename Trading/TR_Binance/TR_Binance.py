# import ccxt
# import myBinance
import time as time_module  # time 모듈을 별칭으로 import
import BinanceTrader
import USDTManager
import json
import kakao_alert as KA
import gspread_updater as GU
from tendo import singleton
me = singleton.SingleInstance()

# API 키 불러오기
with open("/var/autobot/TR_Binance/bnnkr.txt") as f:
    API_KEY, API_SECRET = [line.strip() for line in f.readlines()]

# 매니저 인스턴스 생성
BinanceT = BinanceTrader.BinanceT(API_KEY, API_SECRET)
USDTM = USDTManager.USDTM(API_KEY, API_SECRET)

# 시간확인
now, TR_time = BinanceTrader.what_time()

# If 8:38 Signal확인 후 Redeem / 8:48 Signal확인> Redeem Trading> 5분할(첫 번째)전회 Binance_data json읽고 Signal계산, 투자 금액 산출 후 다시 저장
try:
    if TR_time[1] in [0, 5, None]: # 8:38, 8:48 매매시에만 실행
        # 기존 주문 모두 취소
        result = BinanceT.cancel_all_orders() # 기존 모든 주문 취소 함수(모듈)
        if TR_time[1] == 0: # 0회차 Redeem
            KA.SendMessage(f"Binance {now.strftime('%Y-%m-%d %H:%M:%S')} \n0회차 Redeem \n주문 취소 목록: {result}")
        elif TR_time[1] == 5: # 1회차 Redeem 후 5분할 Trading
            KA.SendMessage(f"Binance {now.strftime('%Y-%m-%d %H:%M:%S')} \n1회차 Redeem & 5분할매매 \n주문 취소 목록: {result}")
        elif TR_time[1] == None: # 완성 후 삭제
            KA.SendMessage(f"Binance {now.strftime('%Y-%m-%d %H:%M:%S')} \n1회차 Redeem & 5분할매매 \n주문 취소 목록: {result}")
        else:
            KA.SendMessage(f"Upbit {now.strftime('%Y-%m-%d %H:%M:%S')} \n오류 \n취소할 주문이 없습니다.")

        time_module.sleep(1) # 타임 슬립 1초

        # 먼저 Signal확인 후 USDT SPOT / 플렉셔블 잔고 확인 후 USDT Redeeem처리
        # 38분이면 300초 쉬었다가 SPOT / 플렉셔블 잔고 확인 SPOT 계좌로 잘 이체되었는 지 확인 성공여부 메세지
        # 48분이면 플렉셔블 없을 시 트레이딩 / 레딤 시엔 60초 쉬었다가 SPOT / 플렉셔블 잔고 확인 SPOT 계좌로 잘 이체되었는 지 확인 성공여부 메세지
        
        # signal 확인
        

        
        # 잔고 확인
        print("=== 전체 잔고 조회 ===")
        total_balance = BinanceT.get_balance('total')
        print(f"BTC: {total_balance.get('BTC', {})}") # 완성 후 삭제
        print(f"USDT: {total_balance.get('USDT', {})}") # 완성 후 삭제
        # KRW, ETH, Total_balance = UP.get_balance()

        # # 포지션 확인 및 투자 수량 산출
        # position, Last_day_Total_balance, Last_month_Total_balance, Last_year_Total_balance, Daily_return, Monthly_return, Yearly_return = UP.make_position(ETH, KRW)

        # # Upbit_data 만들고 저장하기
        # Upbit_data = {
        #     "Date": now.strftime('%Y-%m-%d'),
        #     "Position": position["position"],
        #     "ETH_weight": position["ETH_weight"],
        #     "ETH_target": position["ETH_target"],
        #     "CASH_weight": position["CASH_weight"],
        #     "Invest_quantity": position["Invest_quantity"],
        #     "Total_balance": Total_balance,
        #     "ETH": ETH,
        #     "KRW": KRW,
        #     "Last_day_Total_balance": Last_day_Total_balance,
        #     "Last_month_Total_balance": Last_month_Total_balance,
        #     "Last_year_Total_balance": Last_year_Total_balance,
        #     "Daily_return": Daily_return,
        #     "Monthly_return": Monthly_return,
        #     "Yearly_return": Yearly_return
        # }
        
        # # Upbit_data.json파일 생성 후 알림
        # with open(Upbit_data_path, 'w', encoding='utf-8') as f:
        #     json.dump(Upbit_data, f, ensure_ascii=False, indent=4)
        # KA.SendMessage(f"Upbit Trading, {TR_time[0]} \nPosition: {position['position']} \nETH_target: {position['ETH_target']} \nInvest_quantity: {position['Invest_quantity']}")

except Exception as e:
        print(f"Upbit {TR_time[0]} \n포지션 생성 시 예외 오류: {e}")
        KA.SendMessage(f"Upbit {TR_time[0]} \n포지션 생성 시 예외 오류: {e}")
time_module.sleep(1) # 타임슬립 1초







