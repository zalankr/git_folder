import time as time_module  # time 모듈을 별칭으로 import
from datetime import timedelta
from datetime import datetime
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

# Reddem실행 함수
def Redeem():
    # Redeem(Buy일때만, 전액/반액 나누지 말기, 트레이딩 오류최소화)
    if position["position"] in ["Buy full", "Buy half"]:
        result = USDTM.redeem_usdt_flexible(amount = 'all', dest_account = 'SPOT')
        message = f" Buy position, {result}"
    else:
        message = f" Not Buy position, Redeem 불필요"
    return message

# 당일 최초 기존 주문 취소
result = BinanceT.cancel_all_orders()
now = datetime.now() # 당일 시작시간 확인
KA.SendMessage(f"Binance Start: {now.strftime('%Y-%m-%d %H:%M:%S')} \n당일 트레이딩 시작 \n주문 취소 목록: {result}")
time_module.sleep(1)

# 당일 포지션 불러오기
now = datetime.now() # 현재시간 확인
try:
    # 포지션 확인 및 투자 수량 산출
    position, Last_day_Total_balance, Last_month_Total_balance, Last_year_Total_balance, Daily_return, Monthly_return, Yearly_return, BTC, USDT = BinanceT.make_position()  
    Invest_quantity = float(position['Invest_quantity'])
    KA.SendMessage(f"Binance Position: {now.strftime('%Y-%m-%d %H:%M:%S')} \nPosition: {position['position']} \nBTC_target: {position['BTC_target']:.2f} \nInvest_quantity: {Invest_quantity:.2f}")

except Exception as e:
    KA.SendMessage(f"Binance Position: {now.strftime('%Y-%m-%d %H:%M:%S')} \n포지션 생성 예외 오류: {e}")

time_module.sleep(1) # 타임슬립 1초

# 당일 Redeem 3회
if position["position"] in ["Buy full", "Buy half"]:
    try:
        for num in range(3):
            message = Redeem()
            now = datetime.now() # 현재시간 확인
            KA.SendMessage(f"Binance Redeem: {now.strftime('%Y-%m-%d %H:%M:%S')} \n{message}")
            time_module.sleep(119) # 타임 슬립 119초

    except Exception as e:
        now = datetime.now() # 현재시간 확인
        KA.SendMessage(f"Binance Redeem: {now.strftime('%Y-%m-%d %H:%M:%S')} \nRedeem 예외 오류: {e}")
else:
    time_module.sleep(357) # 타임 슬립 357초

time_module.sleep(87) # 타임 슬립 87초

# 회당 투자량 계산
now = datetime.now() # 현재시간 확인

if position["position"] == "Buy full":
    try:
        USDT = USDTM.get_spot_balance('USDT')['free']
        USDT_per_splits = (float(USDT) * 0.99) / 10
        KA.SendMessage(f"Binance caculate: {now.strftime('%Y-%m-%d %H:%M:%S')} \nUSDT 회당 투자량: {USDT_per_splits}")
    except Exception as e:
        USDT_per_splits = float(Invest_quantity)
        KA.SendMessage(f"USDT 산출 예외 오류로 Json데이터 사용: {e}")

elif position["position"] == "Buy half":
    try:
        USDT = USDTM.get_spot_balance('USDT')['free']
        USDT_per_splits = (float(USDT) * 0.5 * 0.99) / 10
        KA.SendMessage(f"Binance caculate: {now.strftime('%Y-%m-%d %H:%M:%S')} \nUSDT 회당 투자량: {USDT_per_splits}")
    except Exception as e:
        USDT_per_splits = float(Invest_quantity)
        KA.SendMessage(f"USDT 산출 예외 오류로 Json데이터 사용: {e}")

elif position["position"] == "Sell full":
    try:
        BTC = USDTM.get_spot_balance('BTC')['free']
        BTC_per_splits = (float(BTC) * 0.99) / 10
        KA.SendMessage(f"Binance caculate: {now.strftime('%Y-%m-%d %H:%M:%S')} \nBTC 회당 투자량: {BTC_per_splits}")
    except Exception as e:
        BTC_per_splits = float(Invest_quantity)
        KA.SendMessage(f"BTC 산출 예외 오류로 Json데이터 사용: {e}")

elif position["position"] == "Sell half":
    try:
        BTC = USDTM.get_spot_balance('BTC')['free']
        BTC_per_splits = (float(BTC) * 0.5 * 0.99) / 10
        KA.SendMessage(f"Binance caculate: {now.strftime('%Y-%m-%d %H:%M:%S')} \nBTC 회당 투자량: {BTC_per_splits}")
    except Exception as e:
        BTC_per_splits = float(Invest_quantity)
        KA.SendMessage(f"BTC 산출 예외 오류로 Json데이터 사용: {e}")

time_module.sleep(0.5) # 타임슬립

# 시분할 10회 주문하기 > 18회로 증회
try:
    no = 18 # 10회로 변경 가능
    for num in range(no):
        num = num + 1
        now = datetime.now() # 현재시간 확인

        # 포지션별 주문하기
        if position["position"] == "Buy full":
            try:
                order = BinanceT.market_buy(usdt_amount = USDT_per_splits)
                KA.SendMessage(f"Binance Market Buy Order : {now.strftime('%Y-%m-%d %H:%M:%S')} \n{num}/{no} 회차 분할 매매")
            except Exception as e:
                KA.SendMessage(f"Binance Market Buy Order : {now.strftime('%Y-%m-%d %H:%M:%S')} \n{num}/{no} 회차 매매 예외 오류: {e}")

        elif position["position"] == "Buy half":
            try:
                order = BinanceT.market_buy(usdt_amount = USDT_per_splits)
                KA.SendMessage(f"Binance Market Buy Order : {now.strftime('%Y-%m-%d %H:%M:%S')} \n{num}/{no} 회차 분할 매매")
            except Exception as e:    
                KA.SendMessage(f"Binance Market Buy Order : {now.strftime('%Y-%m-%d %H:%M:%S')} \n{num}/{no} 회차 매매 예외 오류: {e}")

        elif position["position"] == "Sell full":
            try:
                order = BinanceT.market_sell(btc_amount = BTC_per_splits)
                KA.SendMessage(f"Binance Market Sell Order : {now.strftime('%Y-%m-%d %H:%M:%S')} \n{num}/{no} 회차 분할 매매")
            except Exception as e:
                KA.SendMessage(f"Binance Market Sell Order : {now.strftime('%Y-%m-%d %H:%M:%S')} \n{num}/{no} 회차 매매 예외 오류: {e}")

        elif position["position"] == "Sell half":
            try:
                order = BinanceT.market_sell(btc_amount = BTC_per_splits)
                KA.SendMessage(f"Binance Market Sell Order : {now.strftime('%Y-%m-%d %H:%M:%S')} \n{num}/{no} 회차 분할 매매")
            except Exception as e:
                KA.SendMessage(f"Binance Market Sell Order : {now.strftime('%Y-%m-%d %H:%M:%S')} \n{num}/{no} 회차 매매 예외 오류: {e}")

        else:
            pass

        time_module.sleep(210) # 타임 슬립 210초

except Exception as e:
    now = datetime.now() # 현재시간 확인
    KA.SendMessage(f"Binance Order: {now.strftime('%Y-%m-%d %H:%M:%S')} \n주문 생성 예외 오류: {e}")

# 마지막 주문 후 수익률 계산하기(년, 월, 일) JSON 기록 카톡 알림, gspread sheet 기록 try로 감싸기
try:
    # 혹시 남은 기존 주문 취소
    result = BinanceT.cancel_all_orders() # 기존 모든 주문 취소
    now = datetime.now() # 현재시간 확인
    KA.SendMessage(f"Binance cancle {now.strftime('%Y-%m-%d %H:%M:%S')} \n종료전 주문 취소 목록: {result}")
    time_module.sleep(1) # 타임 슬립

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
        KA.SendMessage(f'{transfer_asset}, {transfer_amount}, {transfer_to}')

        # Funding Account USDT를 Flexible Savings에 Subscribe
        time_module.sleep(5) # 타임 슬립 5초
        result = USDTM.subscribe_usdt_from_funding(amount='all')
        time_module.sleep(5) # 타임 슬립 5초
        result = result['subscribed_amount']

        print(f"Binance saving 성공적으로 예치되었습니다: {result:.2f} USDT")
        KA.SendMessage(f"Binance saving 성공적으로 예치되었습니다: {result:.2f} USDT")
    else:
        pass

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
    now = datetime.now() # 현재시간 확인

    binance_data = {
        "Date": now.strftime('%Y-%m-%d'),
        "Position": position["position"],
        "BTC_weight": position["BTC_weight"],
        "BTC_target": position["BTC_target"],
        "CASH_weight": position["CASH_weight"],
        "Invest_quantity": position["Invest_quantity"],
        "Total_balance": Total_balance,
        "BTC": float(BTC),
        "USDT": float(USDT),
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
    KA.SendMessage(f"Binance finish: {now.strftime('%Y-%m-%d %H:%M:%S')} \n당일 트레이딩 완료")
    KA.SendMessage(f"Binance 일수익률: {Daily_return:.2f}% \n월수익률: {Monthly_return:.2f}% \n연수익률: {Yearly_return:.2f}% \n환산잔고: {Total_balance:.2f}$ \nBTC: {BTC:.8f} \nUSDT: {USDT:.2f}$")
    KA.SendMessage(f"Binance Position: {binance_data['Position']} \nBTC_weight: {binance_data['BTC_weight']} \nBTC_target: {binance_data['BTC_target']:.2f} \nCASH_weight: {binance_data['CASH_weight']}")

    # Google Spreadsheet에 데이터 추가   
    # 설정값
    credentials_file = "/var/autobot/gspread/service_account.json" # 구글 서비스 계정 JSON 파일 경로
    spreadsheet_name = "2025_TR_Binance" # 스프레드시트 이름
        
    # 구글 스프레드시트 연결
    spreadsheet = GU.connect_google_sheets(credentials_file, spreadsheet_name)
        
    # 현재 월 계산
    current_month = now.month
        
    # 데이터 저장
    GU.save_to_sheets(spreadsheet, binance_data, current_month)

except Exception as e:
    print(f"Binance 기록 {now.strftime('%Y-%m-%d %H:%M:%S')} \n 당일 data 기록 중 예외 오류: {e}")
    KA.SendMessage(f"Binance 기록 {now.strftime('%Y-%m-%d %H:%M:%S')} 당일 data 기록 중 예외 오류: {e}")

exit()