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

# 매니저 인스턴스 생성, JSON data 경로 설정
BinanceT = BinanceTrader.BinanceT(API_KEY, API_SECRET)
USDTM = USDTManager.USDTM(API_KEY, API_SECRET)
data_path = '/var/autobot/TR_Binance/binance_data.json'

# 시간확인
now, TR_time = BinanceTrader.what_time()

# Reddem실행 함수
def Redeem():
     # signal 확인
    position = BinanceT.make_position()[0]

    # Redeem(Buy일때만, 전액/반액 나누지 말기, 트레이딩 오류최소화)
    if position["position"] in ["Buy full", "Buy half"]:
        # 기존 주문 모두 취소
        result = BinanceT.cancel_all_orders() # 기존 모든 주문 취소 함수(모듈)
        time_module.sleep(1)

        result = USDTM.redeem_usdt_flexible(amount = 'all', dest_account = 'SPOT')
        message = f" Buy position, {result}"
    else:
        message = f" Not Buy position, Redeem 불필요"
    return message

# If 8:42 Signal확인 후 Redeem 3회
try:
    if TR_time[1] == 0: # 8:42 Redeem 2분간격 3회
        for num in range(3):
            message = Redeem()
            KA.SendMessage(f"Binance Redeem: {now.strftime('%Y-%m-%d %H:%M:%S')} \n{message}")
            time_module.sleep(119) # 타임 슬립 119초 = 약 2분

except Exception as e:
        print(f"Binance {TR_time[0]} \nRedeem 예외 오류: {e}")
        KA.SendMessage(f"Binance {TR_time[0]} \nRedeem 예외 오류: {e}")

# If 8:49 Signal확인 후 json파일로 만들기
try:
    if TR_time[1] == 5:
        result = BinanceT.cancel_all_orders() # 기존 모든 주문 취소 함수(모듈)
        KA.SendMessage(f"Binance {now.strftime('%Y-%m-%d %H:%M:%S')} \n1회차 Posion확인 \n주문 취소 목록: {result}")
        time_module.sleep(1) # 타임 슬립 1초

        # 포지션 확인 및 투자 수량 산출
        position, Last_day_Total_balance, Last_month_Total_balance, Last_year_Total_balance, Daily_return, Monthly_return, Yearly_return, BTC, USDT = BinanceT.make_position()

        # Binance data 만들고 저장하기
        binance_data = {
            "Date": now.strftime('%Y-%m-%d'),
            "Position": position["position"],
            "BTC_weight": position["BTC_weight"],
            "BTC_target": position["BTC_target"],
            "CASH_weight": position["CASH_weight"],
            "Invest_quantity": position["Invest_quantity"],
            "Total_balance": USDT + (BTC * BinanceT.get_current_price()),
            "BTC": BTC,
            "USDT": USDT,
            "Last_day_Total_balance": Last_day_Total_balance,
            "Last_month_Total_balance": Last_month_Total_balance,
            "Last_year_Total_balance": Last_year_Total_balance,
            "Daily_return": Daily_return,
            "Monthly_return": Monthly_return,
            "Yearly_return": Yearly_return
        }
        
        # Binance_data.json파일 생성 후 알림
        with open(data_path, 'w', encoding='utf-8') as f:
            json.dump(binance_data, f, ensure_ascii=False, indent=4)
        KA.SendMessage(f"Binance Trading, {TR_time[0]} \nPosition: {position['position']} \nBTC_target: {position['BTC_target']} \nInvest_quantity: {position['Invest_quantity']}")

except Exception as e:
        print(f"Binance {TR_time[0]} \n포지션 생성 예외 오류: {e}")
        KA.SendMessage(f"Binance {TR_time[0]} \n포지션 생성 예외 오류: {e}")
time_module.sleep(1) # 타임슬립 1초

# 회차별매매 주문하기
try:
    if TR_time[1] in [5, 4, 3, 2, 1]: # 5,4,3,2,1 분할매매 주문 실행
        # 기존 주문 취소
        result = BinanceT.cancel_all_orders() # 기존 모든 주문 취소 함수(모듈)
        KA.SendMessage(f"Binance {now.strftime('%Y-%m-%d %H:%M:%S')} \nTR_time[{TR_time[1]}]분할매매 \n주문 취소 목록: {result}")
        time_module.sleep(1) # 타임 슬립 1초

        # 당일의 Upbit_data.json 파일 불러오고 position 추출
        with open(data_path, 'r', encoding='utf-8') as f:
            binance_data = json.load(f)

        Position = binance_data["Position"] 
        Invest_quantity = binance_data["Invest_quantity"]

        # 포지션별 주문하기
        if Position == "Sell full":
            splits = TR_time[1]
            BTC = USDTM.get_spot_balance("BTC")['free']
            
            orders = BinanceT.split_sell(splits=splits, btc_amount=BTC)
            for i in range(len(orders)):
                split = orders[i]['split']
                order_id = orders[i]['order_id']
                price = orders[i]['price']
                amount = orders[i]['amount']
                status = orders[i]['status']
                KA.SendMessage(f"Binance Sell Split: {split} \nOrder ID: {order_id} \nPrice: {price} \nAmount: {amount} \nStatus: {status}")

        elif Position == "Sell half":
            splits = TR_time[1]
            BTC = USDTM.get_spot_balance("BTC")['free']
            Remain_BTC = BTC - Invest_quantity
            
            orders = BinanceT.split_sell(splits=splits, btc_amount=Remain_BTC)
            for i in range(len(orders)):
                split = orders[i]['split']
                order_id = orders[i]['order_id']
                price = orders[i]['price']
                amount = orders[i]['amount']
                status = orders[i]['status']
                KA.SendMessage(f"Binance Sell Split: {split} \nOrder ID: {order_id} \nPrice: {price} \nAmount: {amount} \nStatus: {status}")

        elif Position == "Buy full":
            splits = TR_time[1]
            USDT = USDTM.get_spot_balance("USDT")['free']

            orders = BinanceT.split_buy(splits=splits, usdt_amount=USDT)
            for i in range(len(orders)):
                split = orders[i]['split']
                order_id = orders[i]['order_id']
                price = orders[i]['price']
                amount = orders[i]['amount']
                status = orders[i]['status']
                KA.SendMessage(f"Binance Buy Split: {split} \nOrder ID: {order_id} \nPrice: {price} \nAmount: {amount} \nStatus: {status}")

        elif Position == "Buy half":
            splits = TR_time[1]
            USDT = USDTM.get_spot_balance("USDT")['free']
            Remain_USDT = USDT - Invest_quantity

            orders = BinanceT.split_buy(splits=splits, usdt_amount=Remain_USDT)
            for i in range(len(orders)):
                split = orders[i]['split']
                order_id = orders[i]['order_id']
                price = orders[i]['price']
                amount = orders[i]['amount']
                status = orders[i]['status']
                KA.SendMessage(f"Binance Buy Split: {split} \nOrder ID: {order_id} \nPrice: {price} \nAmount: {amount} \nStatus: {status}")

    else:
         pass

except Exception as e:
        print(f"Binance {TR_time[0]} \n주문하기 중 예외 오류: {e}")
        KA.SendMessage(f"Binance {TR_time[0]} \n주문하기 중 예외 오류: {e}")

time_module.sleep(1) # 타임슬립 1초

# 마지막 주문 후 수익률 계산하기(년, 월, 일) JSON 기록 카톡 알림, gspread sheet 기록 try로 감싸기
try:
    if TR_time[1] == 1: #######test 후 1로
        time_module.sleep(10) # 거래완료 까지 시간 두기 타임슬립 10초

        # 혹시 남은 기존 주문 취소
        result = BinanceT.cancel_all_orders() # 기존 모든 주문 취소 함수(모듈)
        KA.SendMessage(f"Binance {now.strftime('%Y-%m-%d %H:%M:%S')} \nTR_time[{TR_time[1]}]분할매매 \n주문 취소 목록: {result}")
        time_module.sleep(2) # 타임 슬립 2초

        # 당일 SPOT계좌에 남은 USDT잔고 확인
        spotUSDT = USDTM.get_spot_balance("USDT")
        spotUSDTfree = spotUSDT['free']

        # 당일 SPOT계좌에 남은 USDT 1이상 펀딩계좌로 이체 후 Earn flexible Product에 Subscribe
        if spotUSDTfree > 1: # minimum 0.1USDT 바이낸스
            # Funding 계좌로 이체
            transfer = USDTM.transfer_accounts(asset = 'USDT', amount = 'all', from_account = 'SPOT', to_account = 'FUNDING')
            transfer_amount = transfer['amount']
            transfer_to = transfer['to_account']
            transfer_asset = transfer['asset']
            print(f'{transfer_asset}, {transfer_amount}, {transfer_to}')
            KA.SendMessage(f'{transfer_asset}, {transfer_amount}, {transfer_to}')

            # Funding Account USDT를 Flexible Savings에 Subscribe
            time_module.sleep(5) # 타임 슬립 5초
            result = USDTM.subscribe_usdt_from_funding(amount='all')
            time_module.sleep(5) # 타임 슬립 5초
            result = result['subscribed_amount']

            print(f"Binance 성공적으로 예치되었습니다: {result:.2f} USDT")
            KA.SendMessage(f"Binance 성공적으로 예치되었습니다: {result:.2f} USDT")
        else:
            pass

        # 당일의 Binance_data.json 파일 불러오고 position, 어제종료 원화환산 토탈잔고, KRW잔고, ETH잔고 추출
        with open(data_path, 'r', encoding='utf-8') as f:
            binance_data = json.load(f)

        # 전일 잔고, 전월말, 전년말 원화환산 잔고
        Last_day_Total_balance = binance_data["Last_day_Total_balance"]
        Last_month_Total_balance = binance_data["Last_month_Total_balance"]
        Last_year_Total_balance = binance_data["Last_year_Total_balance"]

        # 당일종료 원화환산 토탈잔고, BTC잔고, USDT잔고
        BTC = USDTM.get_spot_balance("BTC")['balance']
        USDT = USDTM.get_usdt_summary()['grand_total']
        Total_balance = (BTC*BinanceT.get_current_price()) + USDT

        # 일, 월, 연 수익률
        Daily_return = (Total_balance - Last_day_Total_balance) / Last_day_Total_balance * 100
        Monthly_return = (Total_balance - Last_month_Total_balance) / Last_month_Total_balance * 100
        Yearly_return = (Total_balance - Last_year_Total_balance) / Last_year_Total_balance * 100

        time_module.sleep(0.5) # 타임슬립 0.5초

        # 월초, 연초 전월말, 전년말 잔고 업데이트
        if now.day == 1: # 월초 전월 잔고 데이터 변경
            Last_month_Total_balance = Last_day_Total_balance
            print(f"Binance 월초, 전월 잔고를 {Last_month_Total_balance}원으로 업데이트했습니다.")
        else:
            pass

        if now.month == 1 and now.day == 1: # 연초 전년 잔고 데이터 변경
            Last_year_Total_balance = Last_day_Total_balance
            print(f"Binance 연초, 전년 잔고를 {Last_year_Total_balance}원으로 업데이트했습니다.")
        else:
            pass

        # binance_data 만들기
        binance_data = {
            "Date": now.strftime('%Y-%m-%d'),
            "Position": binance_data["Position"],
            "BTC_weight": binance_data["BTC_weight"],
            "BTC_target": binance_data["BTC_target"],
            "CASH_weight": binance_data["CASH_weight"],
            "Invest_quantity": binance_data["Invest_quantity"],
            "Total_balance": Total_balance,
            "BTC": BTC,
            "USDT": USDT,
            "Last_day_Total_balance": Last_day_Total_balance,
            "Last_month_Total_balance": Last_month_Total_balance,
            "Last_year_Total_balance": Last_year_Total_balance,
            "Daily_return": Daily_return,
            "Monthly_return": Monthly_return,
            "Yearly_return": Yearly_return
        }

        # Binance_data.json파일 생성
        with open(data_path, 'w', encoding='utf-8') as f:
            json.dump(binance_data, f, ensure_ascii=False, indent=4)
        time_module.sleep(0.5)

        # KakaoTalk 메시지 보내기
        KA.SendMessage(f"Binance {now.strftime('%Y-%m-%d %H:%M:%S')} \n당일 트레이딩 완료")
        KA.SendMessage(f"Binance 일수익률: {Daily_return:.2f}% \n월수익률: {Monthly_return:.2f}% \n연수익률: {Yearly_return:.2f}% \n환산잔고: {Total_balance:.2f}$ \nBTC: {BTC:.8f} \nUSDT: {USDT:.2f}$")
        KA.SendMessage(f"Binance Position: {binance_data['Position']} \nBTC_weight: {binance_data['BTC_weight']} \nBTC_target: {binance_data['BTC_target']} \nCASH_weight: {binance_data['CASH_weight']}")

        # Google Spreadsheet에 데이터 추가
        
        # 설정값 (실제 값으로 변경 필요)
        credentials_file = "/var/autobot/gspread/service_account.json" # 구글 서비스 계정 JSON 파일 경로
        spreadsheet_name = "2025_TR_Binance" # 스프레드시트 이름
        
        # 구글 스프레드시트 연결
        spreadsheet = GU.connect_google_sheets(credentials_file, spreadsheet_name)
        
        # 현재 월 계산
        current_month = now.month
        
        # 데이터 저장
        GU.save_to_sheets(spreadsheet, binance_data, current_month)
    else:
        pass

except Exception as e:
    print(f"Binance {TR_time[0]} 당일 data 기록 중 예외 오류: {e}")
    KA.SendMessage(f"Binance {TR_time[0]} 당일 data 기록 중 예외 오류: {e}")

if TR_time[1] == None:
    KA.SendMessage(f"Binance {now.strftime('%Y-%m-%d')} 트레이딩 프로그램 운용시간이 아닙니다. 프로그램을 종료합니다.")

exit()
#### 검증 > 마지막에 crontab에서 5분 후 자동종료 되게 설정
