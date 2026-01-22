import sys
import json
import kakao_alert as KA
from datetime import date, datetime, timedelta
import pandas as pd
import riskfolio as rp
import requests
import calendar
import time as time_module
from tendo import singleton
import KIS_US
import USAA_Calender

try:
    me = singleton.SingleInstance()
except singleton.SingleInstanceException:
    KA.SendMessage("USAA: 이미 실행 중입니다.")
    sys.exit(0)

# KIS instance 생성
key_file_path = "/var/autobot/TR_USAA/kis63604155nkr.txt"
token_file_path = "/var/autobot/TR_USAA/kis63604155_token.json"
cano = "63604155"
acnt_prdt_cd = "01"
KIS = KIS_US.KIS_API(key_file_path, token_file_path, cano, acnt_prdt_cd)

USLA_ticker = ['UPRO', 'TQQQ', 'EDC', 'TMV', 'TMF']
HAA_ticker = ['TIP', 'SPY', 'IWM', 'VEA', 'VWO', 'PDBC', 'VNQ', 'TLT', 'IEF', 'BIL']
Aggresive_ETF = ['SPY', 'IWM', 'VEA', 'VWO', 'PDBC', 'VNQ', 'TLT', 'IEF']
Defensive_ETF = ['IEF', 'BIL']
Regime_ETF = 'TIP'
all_ticker = USLA_ticker + HAA_ticker
all_ticker_with_cash = all_ticker + ['CASH']
fee_rate = 0.0009 # 수수료 이벤트 계좌 0.09%
USAA_data_path = "/var/autobot/TR_USAA/USAA_data.json"
USAA_TR_path = "/var/autobot/TR_USAA/USAA_TR.json"

def health_check(): # Edit완료
    """시스템 상태 확인"""
    checks = []
    
    # 1. API 토큰 유효성
    if not KIS.access_token:
        checks.append("USAA 체크: API 토큰 없음")
    
    # 2. JSON 파일 존재
    import os
    files = [
        "/var/autobot/TR_USAA/USAA_day.json",
        "/var/autobot/TR_USAA/USAA_data.json",
        "/var/autobot/TR_USAA/USAA_TR.json"
    ]
    for f in files:
        if not os.path.exists(f):
            checks.append(f"USAA 체크: json 파일 없음: {f}")
    
    # 3. 네트워크 연결
    try:
        import socket
        socket.create_connection(("openapi.koreainvestment.com", 9443), timeout=5)
    except:
        checks.append("USAA 체크: KIS API 서버 접속 불가")
    
    if checks:
        KA.SendMessage("\n".join(checks))
        sys.exit(1)

def real_Hold(): # Edit완료
    """실제 잔고 확인 함수, Hold 반환"""
    real_balance = KIS.get_US_stock_balance()
    Hold = {
        "SPY": 0,
        "IWM": 0,
        "VEA": 0,
        "VWO": 0,
        "PDBC": 0,
        "VNQ": 0,
        "TLT": 0,
        "IEF": 0,
        "SPXL": 0,
        "UPRO": 0,
        "TQQQ": 0,
        "EDC": 0,
        "TMV": 0,
        "TMF": 0
    }
    for i in range(len(real_balance)):
        ticker = real_balance[i]['ticker']
        if real_balance[i]['ticker'] in all_ticker:
            Hold[ticker] = real_balance[i]['quantity']
    usd = KIS.get_US_dollar_balance()  # withdrawabl_usd
    if usd:
        Hold['CASH'] = usd.get('withdrawable', 0) # 키가 없을 경우 0 반환
    else:
        Hold['CASH'] = 0 # API 호출 실패 시 처리
    return Hold

def make_target_data(Hold, target_weight): #수수료 포함
    """target qty, target usd 만들기"""
    # 현재 USD환산 HAA 잔고
    hold_usd_value = HAA.calculate_USD_value(Hold)
    # HAA USD 잔고 X 티커별 비중 = target qty
    target_usd_value = {ticker: target_weight[ticker] * hold_usd_value for ticker in target_weight.keys()}
    target_qty = HAA.calculate_target_qty(target_weight, target_usd_value)
    target_usd = target_qty["CASH"]

    return target_qty, target_usd

def make_Buy_Sell(target_weight, target_qty, Hold):
    """target qty, hold qty 비교 조정 후 Buy와 Sell dict 만들고 반환하는 함수"""
    Buy = dict()
    Sell = dict()
    # target에 있는 종목 처리
    for ticker in target_weight.keys():
        if ticker == "CASH":
            continue
        hold_qty = Hold.get(ticker, 0)
        target = target_qty[ticker]

        if target > hold_qty:
            Buy[ticker] = target - hold_qty
        elif target < hold_qty:
            Sell[ticker] = hold_qty - target

    # Hold에만 있고 target에 없는 종목 처리 (전량 매도)
    for ticker in Hold.keys():
        if ticker == "CASH":
            continue
        if ticker not in target_weight.keys():
            if Hold[ticker] > 0:
                Sell[ticker] = Hold[ticker]
    return Buy, Sell

def Selling(Sell, sell_split, order_time):  # order_time 매개변수 추가
    """
    매도 주문 실행 함수 - 개선버전 (메시지 통합)
    
    Parameters:
    - Sell: 매도할 종목과 수량 딕셔너리 {ticker: quantity}
    - sell_split: [분할횟수, [가격조정비율 리스트]]
    - order_time: 현재 주문 시간 정보 딕셔너리  # 추가
    
    Returns:
    - Sell_order: 주문 결과 리스트 (성공/실패 모두 포함)
    """
    Sell_order = []
    order_messages = []
    
    if len(Sell.keys()) == 0:
        KA.SendMessage("매도할 종목이 없습니다.")
        return Sell_order
    
    # 수정: 함수 내부에서 호출하지 않고 매개변수로 받음
    round_info = f"{order_time['round']}/{order_time['total_round']}회 매도주문"
    order_messages.append(round_info)
    
    for ticker in Sell.keys():
        if Sell[ticker] == 0:
            order_messages.append(f"{ticker} 매도 수량 0")
            continue

        qty_per_split = int(Sell[ticker] // sell_split[0])
        current_price = HAA.get_US_current_price(ticker)

        if not isinstance(current_price, (int, float)) or current_price <= 0:
            error_msg = f"{ticker} 가격 조회 실패 - 매도 주문 스킵"
            order_messages.append(error_msg)
            Sell_order.append({
                'success': False,
                'ticker': ticker,
                'quantity': Sell[ticker],
                'price': 0,
                'order_number': '',
                'order_time': datetime.now().strftime('%H%M%S'),
                'error_message': error_msg,
                'split_index': -1
            })
            continue
        
        for i in range(sell_split[0]):
            if i == sell_split[0] - 1:
                quantity = Sell[ticker] - qty_per_split * (sell_split[0] - 1)
            else:
                quantity = qty_per_split
            
            if quantity == 0:
                continue
            
            price = round(current_price * sell_split[1][i], 2)
            
            try:
                order_info, order_sell_message = HAA.order_sell_US(ticker, quantity, price)
                
                if order_info and order_info.get('success') == True:
                    order_info = {
                        'success': True,
                        'ticker': ticker,
                        'quantity': quantity,
                        'price': price,
                        'order_number': order_info.get('order_number', ''),
                        'order_time': order_info.get('order_time', ''),
                        'org_number': order_info.get('org_number', ''),
                        'message': order_info.get('message', ''),
                        'split_index': i
                    }
                    Sell_order.append(order_info)
                    
                    # 수정: 변수명 변경 (i → j) 또는 extend 사용
                    if order_sell_message and len(order_sell_message) > 0:
                        order_messages.extend(order_sell_message)  # extend 사용
                    order_messages.append(f"✅ {ticker} {quantity}주 @${price} (분할{i+1})")
                else:
                    error_msg = order_info.get('error_message', 'Unknown error') if order_info else 'API 호출 실패'
                    if order_sell_message and len(order_sell_message) > 0:
                        order_messages.extend(order_sell_message)  # extend 사용
                    order_messages.append(f"❌ {ticker} {quantity}주 @${price} - {error_msg}")
                    Sell_order.append({
                        'success': False,
                        'ticker': ticker,
                        'quantity': quantity,
                        'price': price,
                        'order_number': '',
                        'order_time': datetime.now().strftime('%H%M%S'),
                        'error_message': error_msg,
                        'split_index': i
                    })
            except Exception as e:
                error_msg = f"Exception: {str(e)}"
                order_messages.append(f"❌ {ticker} {quantity}주 @${price} - {error_msg}")
                Sell_order.append({
                    'success': False,
                    'ticker': ticker,
                    'quantity': quantity,
                    'price': price,
                    'order_number': '',
                    'order_time': datetime.now().strftime('%H%M%S'),
                    'error_message': error_msg,
                    'split_index': i
                })
            
            time_module.sleep(0.2)
    
    success_count = sum(1 for order in Sell_order if order['success'])
    total_count = len(Sell_order)
    order_messages.append(f"매도 주문: {success_count}/{total_count} 완료")
    
    KA.SendMessage("\n".join(order_messages))
    
    return Sell_order

def calculate_Buy_qty(Buy, Hold, target_usd):
    """USD현재보유량과 목표보유량 비교 매수 수량과 매수 비중 매수 금액 산출"""
    Buy_value = {}
    total_Buy_value = 0
    ticker_prices = {}
    order_messages = []  # 주문 메시지를 모을 리스트

    for ticker in Buy.keys():
        price = HAA.get_US_current_price(ticker)

        if isinstance(price, (int, float)) and price > 0:
            ticker_prices[ticker] = price
            Buy_value[ticker] = Buy[ticker] * (price * (1 + HAA.fee))
            total_Buy_value += Buy_value[ticker]
        else:
            order_messages.append(f"❌ {ticker} 가격 조회 실패")
            Buy_value[ticker] = 0
            ticker_prices[ticker] = 0

        time_module.sleep(0.1)

    TR_usd = Hold['CASH'] - target_usd
    if TR_usd < 0:
        TR_usd = 0
        order_messages.append(f"⚠️ 매수 가능 USD 부족: ${Hold['CASH']:.2f} (목표: ${target_usd:.2f})")

    Buy_qty = dict()

    if total_Buy_value == 0:
        order_messages.append("매수 가능한 종목이 없습니다.")
        return Buy_qty, TR_usd

    for ticker in Buy_value.keys():
        Buy_weight = Buy_value[ticker] / total_Buy_value
        Buy_usd = TR_usd * Buy_weight
        
        price = ticker_prices[ticker]
        
        if price > 0:
            Buy_qty[ticker] = int(Buy_usd / (price * (1 + HAA.fee)))  # 수수료 포함
        else:
            Buy_qty[ticker] = 0
        
        time_module.sleep(0.1)
    
    # 한 번에 전송
    KA.SendMessage("\n".join(order_messages))
    return Buy_qty, TR_usd

def Buying(Buy_qty, buy_split, TR_usd, order_time):  # order_time 매개변수 추가
    """
    매수 주문 실행 함수 - 개선버전 (메시지 통합)
    
    Parameters:
    - Buy_qty: 매수할 종목과 수량 딕셔너리 {ticker: quantity}
    - buy_split: [분할횟수, [가격조정비율 리스트]]
    - TR_usd: 매수가능 금액
    - order_time: 현재 주문 시간 정보 딕셔너리  # 추가
    
    Returns:
    - Buy_order: 주문 결과 리스트 (성공/실패 모두 포함)
    """
    Buy_order = []
    order_messages = []
    
    if TR_usd < 0:
        TR_usd = 0
        order_messages.append("매수 가능 USD 부족")
    
    if len(Buy_qty.keys()) == 0:
        KA.SendMessage("매수할 종목이 없습니다.")
        return Buy_order
    
    # 수정: 함수 내부에서 호출하지 않고 매개변수로 받음
    round_info = f"{order_time['round']}/{order_time['total_round']}회 매수주문"
    order_messages.append(round_info)
    
    for ticker in Buy_qty.keys():
        if Buy_qty[ticker] == 0:
            order_messages.append(f"{ticker} 매수 수량 0")
            continue
        
        qty_per_split = int(Buy_qty[ticker] // buy_split[0])
        current_price = HAA.get_US_current_price(ticker)
        
        if not isinstance(current_price, (int, float)) or current_price <= 0:
            error_msg = f"{ticker} 가격 조회 실패 - 주문 스킵"
            order_messages.append(error_msg)
            Buy_order.append({
                'success': False,
                'ticker': ticker,
                'quantity': Buy_qty[ticker],
                'price': 0,
                'order_number': '',
                'order_time': datetime.now().strftime('%H%M%S'),
                'error_message': error_msg,
                'split_index': -1
            })
            continue
        
        for i in range(buy_split[0]):
            if i == buy_split[0] - 1:
                quantity = Buy_qty[ticker] - qty_per_split * (buy_split[0] - 1)
            else:
                quantity = qty_per_split
            
            if quantity == 0:
                continue
            
            price = round(current_price * buy_split[1][i], 2)
            
            try:
                order_info, order_buy_message = HAA.order_buy_US(ticker, quantity, price)
                
                if order_info and order_info.get('success') == True:
                    order_info = {
                        'success': True,
                        'ticker': ticker,
                        'quantity': quantity,
                        'price': price,
                        'order_number': order_info.get('order_number', ''),
                        'order_time': order_info.get('order_time', ''),
                        'org_number': order_info.get('org_number', ''),
                        'message': order_info.get('message', ''),
                        'split_index': i
                    }
                    Buy_order.append(order_info)

                    # 수정: 변수명 변경 (i → j) 또는 extend 사용
                    if order_buy_message and len(order_buy_message) > 0:
                        order_messages.extend(order_buy_message)  # extend 사용
                    order_messages.append(f"✅ {ticker} {quantity}주 @${price} (분할{i+1})")
                else:
                    error_msg = order_info.get('error_message', 'Unknown error') if order_info else 'API 호출 실패'
                    if order_buy_message and len(order_buy_message) > 0:
                        order_messages.extend(order_buy_message)  # extend 사용
                    order_messages.append(f"❌ {ticker} {quantity}주 @${price} - {error_msg}")
                    Buy_order.append({
                        'success': False,
                        'ticker': ticker,
                        'quantity': quantity,
                        'price': price,
                        'order_number': '',
                        'order_time': datetime.now().strftime('%H%M%S'),
                        'error_message': error_msg,
                        'split_index': i
                    })
            except Exception as e:
                error_msg = f"Exception: {str(e)}"
                order_messages.append(f"❌ {ticker} {quantity}주 @${price} - {error_msg}")
                Buy_order.append({
                    'success': False,
                    'ticker': ticker,
                    'quantity': quantity,
                    'price': price,
                    'order_number': '',
                    'order_time': datetime.now().strftime('%H%M%S'),
                    'error_message': error_msg,
                    'split_index': i
                })
            
            time_module.sleep(0.2)
    
    success_count = sum(1 for order in Buy_order if order['success'])
    total_count = len(Buy_order)
    order_messages.append(f"매수 주문: {success_count}/{total_count} 완료")
    
    KA.SendMessage("\n".join(order_messages))
    
    return Buy_order

def save_TR_data(order_time, Sell_order, Buy_order, Hold_usd, target_weight, target_qty):
    """
    저장 실패 시에도 백업 파일 생성
    """
    TR_data = {
        "round": order_time['round'],
        "timestamp": datetime.now().isoformat(),  # 타임스탬프 추가
        "Sell_order": Sell_order,
        "Buy_order": Buy_order,
        "CASH": Hold_usd,
        "target_weight": target_weight,
        "target_qty": target_qty
    }
    
    try:
        # 정상 저장
        save_result = HAA.save_HAA_TR_json(TR_data)
        
        if not save_result:
            raise Exception("save_HAA_TR_json returned False")
        
        KA.SendMessage(
            f"{order_time['date']}, {order_time['season']} 리밸런싱\n"
            f"{order_time['time']} {order_time['round']}/{order_time['total_round']}회차 거래저장완료\n"
        )
        
    except Exception as e:
        # 저장 실패 시 백업 파일 생성
        error_msg = f"TR 데이터 저장 실패: {e}"
        KA.SendMessage(error_msg)
        
        backup_path = f"/var/autobot/TR_HAA/HAA_TR_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(TR_data, f, ensure_ascii=False, indent=4)
            KA.SendMessage(f"백업 파일 생성: {backup_path}")
        except Exception as backup_error:
            KA.SendMessage(f"백업 파일 생성도 실패: {backup_error}")
            # 최후의 수단: 카카오로 데이터 전송
            KA.SendMessage(f"TR_data: {json.dumps(TR_data, ensure_ascii=False)[:1000]}")
    
    return TR_data

def load_USAA_data(): # Edit완료
    """USAA data 불러오기"""   
    try:
        with open(USAA_data_path, 'r', encoding='utf-8') as f:
            USAA_data = json.load(f)
        return USAA_data

    except Exception as e:
        KA.SendMessage(f"USAA_data JSON 파일 오류: {e}")
        sys.exit(0)

def get_prices(): # Edit완료
    """현재 가격 조회 (KIS API 사용)"""
    try:
        prices = {}            
        for ticker in all_ticker:
            try:   
                # KIS API로 현재가 조회
                price = KIS.get_US_current_price(ticker)
                
                # 가격이 float 타입인지 확인
                if isinstance(price, float) and price > 0:
                    prices[ticker] = price
                else:
                    KA.SendMessage(f"USAA {ticker} 가격 조회 실패")
                    prices[ticker] = 100.0
                
                time_module.sleep(0.1)  # API 호출 간격
                
            except Exception as e:
                KA.SendMessage(f"USAA {ticker} 가격 조회 오류: {e}")
                prices[ticker] = 100.0
        
        prices['CASH'] = 1.0
        return prices
        
    except Exception as e:
        KA.SendMessage(f"USAA 가격 조회 전체 오류: {e}")
        return {ticker: 100.0 for ticker in all_ticker}

def get_monthly_prices_kis(ticker: str, start_date: str, end_date: str) -> pd.Series: # Edit완료
    """
    KIS API로 월간 가격 데이터 조회
    
    Parameters:
    ticker (str): 종목 코드
    start_date (str): 시작일 (YYYY-MM-DD)
    end_date (str): 종료일 (YYYY-MM-DD)
    
    Returns:
    pd.Series: 날짜를 인덱스로 하는 종가 시리즈
    """
    
    # 거래소 찾기
    exchange = KIS.get_exchange_by_ticker(ticker)
    if exchange == "거래소 조회 실패":
        return pd.Series()
    
    # 거래소 코드
    if exchange == "NASD": exchange = "NAS"
    if exchange == "AMEX": exchange = "AMS"
    if exchange == "NYSE": exchange = "NYS"
    
    # 날짜 형식 변환 (YYYYMMDD)
    end_date_formatted = end_date.replace('-', '')
    
    # KIS API 호출
    url = f"{KIS.url_base}/uapi/overseas-price/v1/quotations/dailyprice"
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {KIS.access_token}",
        "appKey": KIS.app_key,
        "appSecret": KIS.app_secret,
        "tr_id": "HHDFS76240000"
    }
    
    params = {
        "AUTH": "",
        "EXCD": exchange,
        "SYMB": ticker,
        "GUBN": "2",  # 0: 일, 1: 주, 2: 월
        "BYMD": end_date_formatted,
        "MODP": "1"   # 수정주가 반영
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('rt_cd') == '0' and 'output2' in data:
                output2 = data['output2']
                
                if not output2:
                    KA.SendMessage(f"{ticker} 데이터가 비어있습니다.")
                
                # DataFrame 생성
                df = pd.DataFrame(output2)
                
                # 날짜와 종가 추출
                df['date'] = pd.to_datetime(df['xymd'], format='%Y%m%d')
                df['close'] = pd.to_numeric(df['clos'], errors='coerce')
                
                # 날짜 필터링
                start_dt = pd.to_datetime(start_date)
                end_dt = pd.to_datetime(end_date)
                df = df[(df['date'] >= start_dt) & (df['date'] <= end_dt)]
                
                # 시리즈로 변환 (날짜 인덱스)
                df = df.set_index('date')
                price_series = df['close'].sort_index()
                
                return price_series
            else:
                KA.SendMessage(f"{ticker} API 응답 오류: {data.get('msg1', 'Unknown error')}")
        else:
            KA.SendMessage(f"{ticker} API 호출 실패: HTTP {response.status_code}")
            
    except Exception as e:
        KA.SendMessage(f"{ticker} 월간 가격 조회 오류: {e}")

def get_daily_prices_kis(self, tickers: list, days: int = 90) -> pd.DataFrame: # Edit완료
    """
    KIS API로 일간 가격 데이터 조회 (포트폴리오 최적화용)
    
    Parameters:
    tickers (list): 종목 코드 리스트
    days (int): 조회할 일수 (기본 90일)
    
    Returns:
    pd.DataFrame: 날짜를 인덱스로 하는 종가 데이터프레임
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    end_date_str = end_date.strftime('%Y%m%d')
    
    price_data = {}
    
    for ticker in tickers:
        try:
            # 거래소 찾기 (수정된 매핑 사용)
            exchange = KIS.get_exchange_by_ticker(ticker)
            
            url = f"{KIS.url_base}/uapi/overseas-price/v1/quotations/dailyprice"
            headers = {
                "Content-Type": "application/json",
                "authorization": f"Bearer {KIS.access_token}",
                "appKey": KIS.app_key,
                "appSecret": KIS.app_secret,
                "tr_id": "HHDFS76240000"
            }
            
            params = {
                "AUTH": "",
                "EXCD": exchange,
                "SYMB": ticker,
                "GUBN": "0",  # 0: 일, 1: 주, 2: 월
                "BYMD": end_date_str,
                "MODP": "1"   # 수정주가 반영
            }
            
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('rt_cd') == '0' and 'output2' in data:
                    output2 = data['output2']
                    
                    if output2:
                        df = pd.DataFrame(output2)
                        df['date'] = pd.to_datetime(df['xymd'], format='%Y%m%d')
                        df['close'] = pd.to_numeric(df['clos'], errors='coerce')
                        
                        # 날짜 필터링
                        df = df[df['date'] >= pd.to_datetime(start_date)]
                        df = df.set_index('date')
                        
                        price_data[ticker] = df['close']
            
            time_module.sleep(0.1)
            
        except Exception as e:
            KA.SendMessage(f"USLA {ticker} 일간 데이터 조회 오류: {e}")
            continue
    
    if not price_data:
        raise ValueError("일간 가격 데이터를 가져올 수 없습니다.")
    
    return pd.DataFrame(price_data).sort_index(ascending=True)

def AGG_regime(): # Edit완료
    """AGG 채권 ETF의 Regime 신호 계산 (KIS API 사용)"""
    try:
        today = date.today()
        target_month = today.month
        target_year = today.year

        # 4개월 전 시작일 계산
        start_month = target_month - 4
        start_year = target_year

        if start_month <= 0:
            start_month = 12 + start_month
            start_year = target_year - 1
            
        # 전월 말일 계산    
        prev_month = target_month - 1 if target_month > 1 else 12
        prev_year = target_year if target_month > 1 else target_year - 1

        start_date = f'{start_year}-{start_month:02d}-01'
        last_day = calendar.monthrange(prev_year, prev_month)[1] # 월말일 반환
        end_date = f'{prev_year}-{prev_month:02d}-{last_day}'

        # KIS API로 AGG 월간 데이터 조회
        agg_data = get_monthly_prices_kis('AGG', start_date, end_date)
        time_module.sleep(0.1) # API 호출 간격

        if len(agg_data) < 4:
            KA.SendMessage("USLA 경고: AGG 데이터가 충분하지 않습니다.")
            return 0    

        current_price = agg_data.iloc[-1]  # 최신 가격
        avg_price = agg_data.mean()  # 4개월 평균

        regime = current_price - avg_price

        return regime
        
    except Exception as e:
        KA.SendMessage(f"USLA Regime 계산 오류: {e}")
        return 0

def USLA_momentum(): # Edit완료
    """모멘텀 점수 계산 (KIS API 사용)"""
    try:
        today = date.today()
        target_month = today.month
        target_year = today.year

        # 13개월 데이터 필요 (현재 + 12개월)
        start_year = target_year - 2
        prev_month = target_month - 1 if target_month > 1 else 12
        prev_year = target_year if target_month > 1 else target_year - 1
        
        start_date = f'{start_year}-{target_month:02d}-01'
        last_day = calendar.monthrange(prev_year, prev_month)[1] # 월말일 반환
        end_date = f'{prev_year}-{prev_month:02d}-{last_day}'
        
        # 각 ETF의 월간 가격 데이터 수집
        price_data = {}        
        for ticker in USLA_ticker:
            try:
                # KIS API로 월간 데이터 조회
                prices = get_monthly_prices_kis(ticker, start_date, end_date)
                price_data[ticker] = prices
                time_module.sleep(0.1)  # API 호출 간격
                
            except Exception as e:
                KA.SendMessage(f"USLA {ticker} 월간 데이터 조회 오류: {e}")
                continue
        
        if not price_data:
            KA.SendMessage("USLA 경고: 모멘텀 계산을 위한 데이터를 가져올 수 없습니다.")
            return pd.DataFrame()
        
        # DataFrame으로 변환
        price_df = pd.DataFrame(price_data)
        
        if len(price_df) < 13:
            KA.SendMessage("USLA 경고: 모멘텀 계산을 위한 데이터가 충분하지 않습니다.")
            return pd.DataFrame()
            
        momentum_scores = []
        
        for ticker in USLA_ticker:
            try:
                if ticker not in price_df.columns:
                    continue
                    
                prices = price_df[ticker].dropna()
                
                if len(prices) < 13:
                    continue
                    
                # 현재가 기준 수익률 계산
                current = prices.iloc[-1]
                returns = {
                    '1m': (current / prices.iloc[-2] - 1) if len(prices) >= 2 else 0,
                    '3m': (current / prices.iloc[-4] - 1) if len(prices) >= 4 else 0,
                    '6m': (current / prices.iloc[-7] - 1) if len(prices) >= 7 else 0,
                    '9m': (current / prices.iloc[-10] - 1) if len(prices) >= 10 else 0,
                    '12m': (current / prices.iloc[-13] - 1) if len(prices) >= 13 else 0
                }
                
                # 모멘텀 점수 계산 (가중평균)
                score = (returns['1m'] * 30 + returns['3m'] * 25 + 
                        returns['6m'] * 20 + returns['9m'] * 15 + 
                        returns['12m'] * 10)
                
                momentum_scores.append({
                    'ticker': ticker,
                    'momentum': score,
                    '1m_return': returns['1m'],
                    '3m_return': returns['3m'],
                    '12m_return': returns['12m']
                })
                
            except Exception as e:
                KA.SendMessage(f"USLA {ticker} 모멘텀 계산 오류: {e}")
                continue
        
        if not momentum_scores:
            return pd.DataFrame()
            
        momentum_df = pd.DataFrame(momentum_scores)
        momentum_df['rank'] = momentum_df['momentum'].rank(ascending=False)
        momentum_df = momentum_df.sort_values('rank').reset_index(drop=True)
        
        return momentum_df
        
    except Exception as e:
        KA.SendMessage(f"USLA 모멘텀 점수 계산 오류: {e}")
        return pd.DataFrame()

def USLA_portfolio_weights(top_tickers): # Edit완료
    """최소분산 포트폴리오 가중치 계산 (KIS API 사용)"""
    try:
        # KIS API로 최근 90일 일간 데이터 조회
        Hist = get_daily_prices_kis(top_tickers, days=90)

        
        # 최근 45일만 사용
        Hist = Hist.tail(45)
        Hist.sort_index(axis=0, ascending=False, inplace=True)
        
        Ret = Hist.pct_change(-1).dropna()
        Ret = Ret.round(4)

        port = rp.Portfolio(returns=Ret)
        method_mu = 'hist'
        method_cov = 'hist'
        port.assets_stats(method_mu=method_mu, method_cov=method_cov)

        model = 'Classic'
        rm = 'MV'
        obj = 'MinRisk'
        hist = True
        rf = 0
        l = 0

        # 유니버스 데이터베이스
        ticker_class = []
        for i in top_tickers:
            if i == 'UPRO' or i == 'TQQQ' or i == 'EDC':
                ticker_class.append('stock')
            else:
                ticker_class.append('bond')

        asset_classes = {
            'Asset': [top_tickers[0], top_tickers[1]],
            'Class': [ticker_class[0], ticker_class[1]]
        }

        asset_classes = pd.DataFrame(asset_classes)

        # 제약조건 설정 데이터베이스
        constraints = {
            'Disabled': [False, False],
            'Type': ['All Assets', 'All Assets'],
            'Set': ['', ''],
            'Position': ['', ''],
            'Sign': ['>=', '<='],
            'Weight': [0.16, 0.84],
            'Type Relative': ['', ''],
            'Relative Set': ['', ''],
            'Relative': ['', ''],
            'Factor': ['', '']
        }

        constraints = pd.DataFrame(constraints)

        # 제약조건 적용 MVP모델 Weight 해찾기
        A, B = rp.assets_constraints(constraints, asset_classes)

        port.ainequality = A
        port.binequality = B

        weights = port.optimization(model=model, rm=rm, obj=obj, rf=rf, l=l, hist=hist)
        
        if weights is None or weights.empty:
            KA.SendMessage(f"USLA 최적화 실패: 동일가중으로 설정")
            return {ticker: 1 / len(top_tickers) for ticker in top_tickers} # 100%내 50%씩 동일가중
        
        weight_dict = {}
        for i, ticker in enumerate(top_tickers):
            weight_dict[ticker] = float(weights.iloc[i, 0]) # 최소분산 비중 할당
            
        return weight_dict
        
    except Exception as e:
        KA.SendMessage(f"USLA 포트폴리오 최적화 오류: {e}")
        # 동일가중으로 폴백
        equal_weight = 0.97 / len(top_tickers) # 98% 동일가중
        return {ticker: equal_weight for ticker in top_tickers}

def USLA_strategy(regime, momentum_df): # Edit완료
    """전략 실행"""
    if momentum_df.empty:
        KA.SendMessage("USLA 경고: 모멘텀 데이터가 비어 계산할 수 없습니다.")
        return None
    
    # 모멘텀 상위 종목 출력 (최대 5개 또는 실제 데이터 개수)
    num_tickers = min(5, len(momentum_df))
    momentum = momentum_df.head(num_tickers)
    
    lines = [f"USLA Regime: {regime:.2f}", "모멘텀 순위:"]
    for i in range(num_tickers):
        ticker = momentum.iloc[i]['ticker']
        score = momentum.iloc[i]['momentum']
        lines.append(f"{i+1}위: {ticker} ({score:.4f})")

    KA.SendMessage("\n".join(lines))
        
    # 3. 투자 전략 결정
    if regime < 0:
        KA.SendMessage(f"USLA Regime: {regime:.2f} < 0 → 100% CASH")
        
        allocation = {ticker: 0.0 for ticker in USLA_ticker}
        allocation['CASH'] = 1.0

    else:
        # 상위 2개 ETF 선택
        if len(momentum_df) < 2:
            KA.SendMessage(f"USLA 경고: 모멘텀 데이터가 2개 미만입니다. CASH로 대기합니다.")
            allocation = {ticker: 0.0 for ticker in USLA_ticker}
            allocation['CASH'] = 1.0
        else:
            top_tickers = momentum_df.head(2)['ticker'].tolist()
            
            # 포트폴리오 가중치 계산
            weights = USLA_portfolio_weights(top_tickers)
            
            allocation = {ticker: 0.0 for ticker in USLA_ticker}
            allocation.update(weights)
            allocation['CASH'] = 0.0  # 여유 현금은 최종 합산 단계에서 현금 보유 비중 결정
    
    # 4. 현재 가격 조회
    current_prices = get_prices()
    
    # 4. 결과 출력
    message = []
    for ticker in USLA_ticker:
        if allocation.get(ticker, 0) > 0:
            message.append(f"USLA {ticker}: {allocation[ticker]:.1%} (현재가: ${current_prices[ticker]:.2f})")

    KA.SendMessage("\n".join(message))
    
    return {
        'regime': regime,
        'momentum': momentum_df,
        'allocation': allocation,
        'current_prices': current_prices
    }

def USLA_target_regime(): # Edit완료
    """target 티커별 목표 비중 산출"""
    regime = AGG_regime()
    momentum_df = USLA_momentum()
    result = USLA_strategy(regime, momentum_df)
    
    if result is None:
        KA.SendMessage("USLA 경고: 전략 실행 실패, CASH로 대기합니다.")
        return {'CASH': 1.0}, 0
    
    USLA_target = {
        ticker: weight 
        for ticker, weight in result['allocation'].items() 
        if weight >= 0.001
    }
    USLA_regime = result['regime']
    return USLA_target, USLA_regime

def HAA_target_regime(): # Edit완료
    """HAA 모멘텀 점수 계산 (KIS API 사용)"""
    
    # 결과값 초기화 실패 시'CASH' 100%로 대기
    HAA_target = {'CASH': 1.0}
    HAA_regime = -1

    try:
        today = date.today()
        target_month = today.month
        target_year = today.year

        # 13개월 데이터 필요 (현재 + 12개월)
        start_year = target_year - 2
        prev_month = target_month - 1 if target_month > 1 else 12
        prev_year = target_year if target_month > 1 else target_year - 1
        
        start_date = f'{start_year}-{target_month:02d}-01'
        last_day = calendar.monthrange(prev_year, prev_month)[1] # 월말일 반환
        end_date = f'{prev_year}-{prev_month:02d}-{last_day}'
        
        # 각 ETF의 월간 가격 데이터 수집
        price_data = {}
        
        for ticker in HAA_ticker:
            try:
                # KIS API로 월간 데이터 조회
                prices = get_monthly_prices_kis(ticker, start_date, end_date)
                price_data[ticker] = prices
                time_module.sleep(0.1)  # API 호출 간격
                
            except Exception as e:
                KA.SendMessage(f"HAA {ticker} 월간 데이터 조회 오류: {e}")
                continue
        
        if not price_data:
            KA.SendMessage("HAA 경고: 모멘텀 계산을 위한 데이터를 가져올 수 없습니다.")
            return HAA_target, HAA_regime
        
        # DataFrame으로 변환
        price_df = pd.DataFrame(price_data)
        
        if len(price_df) < 13:
            KA.SendMessage("HAA 경고: 모멘텀 계산을 위한 데이터가 충분하지 않습니다.")
            return HAA_target, HAA_regime
            
        momentum_scores = []
        messages = []
        
        for ticker in HAA_ticker:
            try:
                if ticker not in price_df.columns:
                    continue
                    
                prices = price_df[ticker].dropna()
                
                if len(prices) < 13:
                    continue
                    
                # 현재가 기준 수익률 계산
                current = prices.iloc[-1]
                returns = {
                    '1m': (current / prices.iloc[-2] - 1) if len(prices) >= 2 else 0,
                    '3m': (current / prices.iloc[-4] - 1) if len(prices) >= 4 else 0,
                    '6m': (current / prices.iloc[-7] - 1) if len(prices) >= 7 else 0,
                    '12m': (current / prices.iloc[-13] - 1) if len(prices) >= 13 else 0
                }
                # 모멘텀 점수 계산 (가중평균)
                score = (returns['1m']+returns['3m']+returns['6m']+returns['12m'])*100
                
                momentum_scores.append({
                    'ticker': ticker,
                    'momentum': score
                })
            
            except Exception as e:
                messages.append(f"HAA {ticker} 모멘텀 계산 오류: {e}")
                continue
        
        if not momentum_scores:
            KA.SendMessage("HAA 경고: 계산된 모멘텀 데이터를 찾을 수 없습니다.")
            return HAA_target, HAA_regime
        
        # Regime구하기
        regime = momentum_scores['TIP']
        if regime is None:
            KA.SendMessage(f"HAA 경고: {Regime_ETF} 모멘텀 데이터를 찾을 수 없습니다.")
            return HAA_target, HAA_regime
        else:
            messages.append(f"HAA: {Regime_ETF} 모멘텀 = {regime:.2f}")

        # 데이터프레임 만들기
        momentum_df = pd.DataFrame(momentum_scores)
        if momentum_df is None:
            KA.SendMessage(f"HAA 경고: momentum_df를 찾을 수 없습니다.")
            return HAA_target, HAA_regime
        else:
            messages.append(f"HAA: momentum_df 생성 성공")

        # regime 양수일 때 Aggresive ETF의 모멘텀 점수 구하기
        if regime >= 0:
            aggresive_df = momentum_df[momentum_df['ticker'].isin(Aggresive_ETF)]
            aggresive_df['rank'] = aggresive_df['momentum'].rank(ascending=False)
            aggresive_df = aggresive_df.sort_values('rank').reset_index(drop=True)

            # 모멘텀 상위 종목 출력 (최대 8개 또는 실제 데이터 개수 중 적은 것)
            num_tickers = min(8, len(momentum_df))
            momentum = momentum_df.head(num_tickers)

            messages.append(f"HAA Regime: {regime:.2f}", "모멘텀 순위:")
            for i in range(num_tickers):
                ticker = momentum.iloc[i]['ticker']
                score = momentum.iloc[i]['momentum']
                messages.append(f"{i+1}위: {ticker} ({score:.4f})")

            # 상위 4개 ETF 선택
            if len(momentum_df) < 4:
                KA.SendMessage(f"HAA 경고: 모멘텀 데이터가 4개 미만입니다. CASH로 대기합니다.")
                return HAA_target, HAA_regime
            else:
                top_tickers = momentum_df.head(4)['ticker'].tolist()
                
                # 포트폴리오 ticker와 weights를 allocation dictionary에 기입
                weights = 0.25 # 25%씩 할당
                HAA_target = {ticker: weights for ticker in top_tickers}
                HAA_regime = regime

                for ticker, weight in HAA_target.items():
                    messages.append(f"{ticker}: {weight:.2%}")

                KA.SendMessage("\n".join(messages))
                return HAA_target, HAA_regime

        # regime 음수일 때 defensive ETF의 모멘텀 점수 구하기    
        elif regime < 0:
            defensive_df = momentum_df[momentum_df['ticker'].isin(Defensive_ETF)]
            defensive_df['rank'] = defensive_df['momentum'].rank(ascending=False)
            defensive_df = defensive_df.sort_values('rank').reset_index(drop=True)

            # 모멘텀 상위 종목 출력 (최대 2개 또는 실제 데이터 개수 중 적은 것)
            num_tickers = min(2, len(momentum_df))
            momentum = momentum_df.head(num_tickers)

            messages.append(f"HAA Regime: {regime:.2f}", "모멘텀 순위:")
            for i in range(num_tickers):
                ticker = momentum.iloc[i]['ticker']
                score = momentum.iloc[i]['momentum']
                messages.append(f"{i+1}위: {ticker} ({score:.4f})")

            # 상위 1개 ETF 선택
            if len(momentum_df) < 1:
                KA.SendMessage(f"HAA 경고: 모멘텀 데이터가 1개 미만입니다. CASH로 대기합니다.")
                return HAA_target, HAA_regime
            else:
                top_tickers = momentum_df.head(1)['ticker'].tolist()
                
                # 포트폴리오 ticker와 weights를 allocation dictionary에 기입
                if top_tickers == ['IEF']:
                    HAA_target = {'IEF': 1.0}
                    # HAA_target['IEF'] = 1.0

                elif top_tickers == ['BIL']:
                    HAA_target = {'CASH': 1.0}
                    # HAA_target['CASH'] = 1.0  # 100% 현금 보유
                
                HAA_regime = regime

                for ticker, weight in HAA_target.items():
                    messages.append(f"{ticker}: {weight:.2%}")

                KA.SendMessage("\n".join(messages))
                return HAA_target, HAA_regime

    except Exception as e:
        KA.SendMessage(f"HAA_momentum 전체 오류: {e}")
        return result

# ============================================
# 메인 로직 # 연단위 모델간 리밸런싱
# ============================================

# 날짜 체크
order_time = USAA_Calender.check_order_time()
order_time['time'] = order_time['time'].replace(second=0, microsecond=0)

if order_time['season'] == "USAA_not_rebalancing" or order_time['round'] == 0:
    KA.SendMessage(f"USAA 리밸런싱일이 아닙니다.\n{order_time['date']}가 USAA_day 리스트에 없습니다.")
    sys.exit(0)

# 메인로직 시작 전 시스템 상태 확인
health_check()
KA.SendMessage(f"USAA {order_time['date']} 리밸런싱\n{order_time['time']}, {order_time['round']}/{order_time['total_round']}회차 거래시작")

if order_time['round'] == 1:  # round 1회에서 목표 Trading qty 구하기   
    # USAA regime체크 및 거래 목표 데이터 만들기
    USLA_target, USLA_regime = USLA_target_regime()
    USLA_target_ticker = list(USLA_target.keys())
    
    # HAA regime체크 및 거래 목표 데이터 만들기
    HAA_target, HAA_regime = HAA_target_regime()   
    HAA_target_ticker = list(HAA_target.keys())
    
    # 현재의 종합잔고를 USLA, HAA, CASH별로 산출 & 총잔고 계산
    USD_account = KIS.get_US_dollar_balance()
    if USD_account:
        USD = USD_account.get('withdrawable', 0)  # 키가 없을 경우 0 반환
    else:
        USD = 0  # API 호출 실패 시 처리
    time_module.sleep(0.1)

    USLA_balance = 0
    USLA_qty = []
    for ticker in USLA_ticker:
        balance = KIS.get_ticker_balance(ticker)
        if balance:
            eval_amount = balance.get('eval_amount', 0)
            USLA_qty.append(balance.get('holding_qty', 0))
        else:
            eval_amount = 0  # API 호출 실패 시 처리
        USLA_balance += eval_amount
        time_module.sleep(0.05)
    
    HAA_balance = 0
    HAA_qty = []
    for ticker in HAA_ticker:
        if ticker == 'TIP':
            continue
        balance = KIS.get_ticker_balance(ticker)
        if balance:
            eval_amount = balance.get('eval_amount', 0)
        else:
            eval_amount = 0  # API 호출 실패 시 처리
        HAA_balance += eval_amount
        time_module.sleep(0.05)

    Total_balance = USLA_balance + HAA_balance + USD
    
    # 월별 모델별 비중 계산
    ## 헷징 모드 확인 후 USD 재조정
    if USLA_qty == [] and HAA_qty == []: # USLA와 HAA 모두에 ETF 잔고 없음 (전액 현금 헷징)
        USLA_qty = Total_balance * 0.67 # USLA모델에 USD 예수금의 67% 할당
        HAA_qty = Total_balance * 0.33       # HAA모델에 USD 예수금의 33% 할당
    elif USLA_qty == [] and HAA_qty != []: # USLA에만 ETF 잔고 없음 (USLA모델 현금 헷징)
        USLA_qty = USD * 67 / 68
        HAA_qty = HAA_balance + USD / 68
    elif USLA_qty != [] and HAA_qty == []: # HAA에만 ETF 잔고 없음 (HAA모델 현금 헷징)
        USLA_qty = USLA_balance + USD * 2 / 35
        HAA_qty = USD * 33 / 35
    else: # 두 모델 모두에 ETF 잔고 있음 (정상 운용)
        USLA_balance = USLA_balance + (USD * 0.67)  # 달러의 67%는 USLA모델에 할당
        HAA_balance = HAA_balance + (USD * 0.33)  # 달러의 33%는 HAA모델에 할당

    ## 만약 1월에는 비중 리밸런싱
    if order_time['month'] == 1:
        USAA_balance = Total_balance * 0.67
        HAA_balance = Total_balance * 0.33

    #################################################################################
    # 수량구하기

    
    

    target_qty, target_usd = make_target_data(Hold, target_weight)
    Buy, Sell = make_Buy_Sell(target_weight, target_qty, Hold)

    round_split = HAA.make_split_data(order_time['round'])
    sell_split = [round_split["sell_splits"], round_split["sell_price_adjust"]]
    buy_split = [round_split["buy_splits"], round_split["buy_price_adjust"]]
    
    # 당일 티커별 평가금 산출 - 수수료 포함
    SPY_eval = Hold['SPY'] * (HAA.get_US_current_price('SPY') * (1-HAA.fee))
    IWM_eval = Hold['IWM'] * (HAA.get_US_current_price('IWM') * (1-HAA.fee))
    VEA_eval = Hold['VEA'] * (HAA.get_US_current_price('VEA') * (1-HAA.fee))
    VWO_eval = Hold['VWO'] * (HAA.get_US_current_price('VWO') * (1-HAA.fee))
    PDBC_eval = Hold['PDBC'] * (HAA.get_US_current_price('PDBC') * (1-HAA.fee))
    VNQ_eval = Hold['VNQ'] * (HAA.get_US_current_price('VNQ') * (1-HAA.fee))
    TLT_eval = Hold['TLT'] * (HAA.get_US_current_price('TLT') * (1-HAA.fee))
    IEF_eval = Hold['IEF'] * (HAA.get_US_current_price('IEF') * (1-HAA.fee))

    result = HAA.get_US_dollar_balance()
    exchange_rate = result['exchange_rate']
    time_module.sleep(0.2)

    # 데이터 조정
    today_eval = SPY_eval + IWM_eval + VEA_eval + VWO_eval + PDBC_eval + VNQ_eval + TLT_eval + IEF_eval + Hold['CASH']
    today_eval_KRW = int(today_eval * exchange_rate)
    today_eval = float("{:.2f}".format(today_eval))

    HAA_data = {
        'date': str(order_time['date']),
        'regime_score': regime_score,
        'SPY_hold': Hold['SPY'],
        'SPY_weight': target_weight.get('SPY', 0),
        'SPY_target_qty': target_qty.get('SPY', 0),
        'IWM_hold': Hold['IWM'],
        'IWM_weight': target_weight.get('IWM', 0),
        'IWM_target_qty': target_qty.get('IWM', 0),
        'VEA_hold': Hold['VEA'],
        'VEA_weight': target_weight.get('VEA', 0),
        'VEA_target_qty': target_qty.get('VEA', 0),
        'VWO_hold': Hold['VWO'],
        'VWO_weight': target_weight.get('VWO', 0),
        'VWO_target_qty': target_qty.get('VWO', 0),
        'PDBC_hold': Hold['PDBC'],
        'PDBC_weight': target_weight.get('PDBC', 0),
        'PDBC_target_qty': target_qty.get('PDBC', 0),
        'VNQ_hold': Hold['VNQ'],
        'VNQ_weight': target_weight.get('VNQ', 0),
        'VNQ_target_qty': target_qty.get('VNQ', 0),
        'TLT_hold': Hold['TLT'],
        'TLT_weight': target_weight.get('TLT', 0),
        'TLT_target_qty': target_qty.get('TLT', 0),
        'IEF_hold': Hold['IEF'],
        'IEF_weight': target_weight.get('IEF', 0),
        'IEF_target_qty': target_qty.get('IEF', 0),
        'CASH_hold': Hold['CASH'],
        'CASH_weight': target_weight.get('CASH', 0),
        'CASH_target_qty': target_qty.get('CASH', 0),
        'balance': today_eval,
        'last_day_balance': HAA_data['last_day_balance'],
        'last_month_balance': HAA_data['last_month_balance'],
        'last_year_balance': HAA_data['last_year_balance'],
        'daily_return': HAA_data['daily_return'],
        'monthly_return': HAA_data['monthly_return'],
        'yearly_return': HAA_data['yearly_return'],
        'exchange_rate': HAA_data['exchange_rate'],
        'balance_KRW': today_eval_KRW,
        'last_day_balance_KRW': HAA_data['last_day_balance_KRW'],
        'last_month_balance_KRW': HAA_data['last_month_balance_KRW'],
        'last_year_balance_KRW': HAA_data['last_year_balance_KRW'],
        'daily_return_KRW': HAA_data['daily_return_KRW'],
        'monthly_return_KRW': HAA_data['monthly_return_KRW'],
        'yearly_return_KRW': HAA_data['yearly_return_KRW']
    }

    HAA.save_HAA_data_json(HAA_data)

    # Sell주문
    Sell_order = Selling(Sell, sell_split, order_time) 
    # Buy 수량 계산
    Buy_qty, TR_usd = calculate_Buy_qty(Buy, Hold, target_usd)
    # Buy주문
    Buy_order = Buying(Buy_qty, buy_split, TR_usd, order_time)

    # 데이터 저장
    save_TR_data(order_time, Sell_order, Buy_order, Hold_usd, target_weight, target_qty)
    sys.exit(0)

elif order_time['round'] in range(2, 25):  # Round 2~24회차
    # ====================================
    # 1단계: 지난 라운드 TR_data 불러오기
    # ====================================
    try:
        TR_data =HAA.load_HAA_TR()
        Sell_order = TR_data['Sell_order']
        Buy_order = TR_data['Buy_order']
        Hold_usd = TR_data['CASH']
        target_weight = TR_data['target_weight']
        target_qty = TR_data['target_qty']
        target_usd = target_qty['CASH']
        # 이전 라운드 USD 저장 (검증용)
        prev_round_usd = Hold_usd
    
    except Exception as e:
        KA.SendMessage(f"HAA_TR JSON 파일 오류: {e}")
        sys.exit(0)

    # ============================================
    # 2단계: 체결 내역 확인 (주문 취소 전!)
    # ============================================
    # 성공한 주문만 필터링하여 체결 확인
    successful_sell_orders = [o for o in Sell_order if o.get('success', False)]
    successful_buy_orders = [o for o in Buy_order if o.get('success', False)]

    report_message = [] # 출력메세지 모으기

    # 매도 체결결과 반영
    if len(successful_sell_orders) > 0:
        sell_summary, message = HAA.calculate_sell_summary(successful_sell_orders)
        Hold_usd += sell_summary['net_amount']
        for i in message:
            report_message.append(i)
        report_message.append(f"매도 체결: ${sell_summary['net_amount']:.2f} (수수료 차감 후)")
    
    # 매수 체결결과 반영
    if len(successful_buy_orders) > 0:
        buy_summary, message = HAA.calculate_buy_summary(successful_buy_orders)
        Hold_usd -= buy_summary['total_amount']
        for i in message:
            report_message.append(i)
        report_message.append(f"매수 체결: ${buy_summary['total_amount']:.2f} (수수료 포함)")

    # USD 잔고 변화 로깅
    usd_change = Hold_usd - prev_round_usd
    report_message.append(f"USD 변화: ${usd_change:+.2f} (이전: ${prev_round_usd:.2f} → 현재: ${Hold_usd:.2f})")
    
    # ============================================
    # 3단계: 미체결 주문 취소 (체결 확인 후!)
    # ============================================
    try:
        cancel_result, cancel_messages = HAA.cancel_all_unfilled_orders()
        report_message.extend(cancel_messages)
        if cancel_result['total'] > 0:
            report_message.append(f"미체결 주문 취소: {cancel_result['success']}/{cancel_result['total']}")
    except Exception as e:
        report_message.append(f"USLA 주문 취소 오류: {e}")
        
    # 출력
    KA.SendMessage("\n".join(report_message))

    # ============================================
    # 4단계: 새로운 주문 준비 및 실행
    # ============================================
    # 목표 비중 만들기
    Hold = real_Hold() #실제보유
    
    Buy = dict()
    Sell = dict()
    # target에 있는 종목 처리
    for ticker in target_qty.keys():
        hold_qty = Hold.get(ticker, 0)
        target = target_qty[ticker]
        if ticker == "CASH":
            continue
        if target > hold_qty:
            Buy[ticker] = target - hold_qty
        elif target < hold_qty:
            Sell[ticker] = hold_qty - target
    # Hold에만 있고 target에 없는 종목 처리 (전량 매도)
    for ticker in Hold.keys():
        if ticker == "CASH":
            continue
        if ticker not in target_qty.keys():
            if Hold[ticker] > 0:
                Sell[ticker] = Hold[ticker]
    
    # Buy USD환산총액이 현재 Hold['CASH']보다 클 경우 매수수량 조정
    TR_usd = Hold_usd - target_usd  # 매수가능 USD
    needs_usd = 0
    for ticker in Buy.keys(): # Buy USD환산총액 계산
        price = HAA.get_US_current_price(ticker)
        if isinstance(price, (int, float)) and price > 0:
            needs_usd += Buy[ticker] * (price * (1 + HAA.fee))
        else:
            needs_usd += 0
        time_module.sleep(0.1)
    Buy_qty = dict()
    ratio = TR_usd / needs_usd if needs_usd > 0 else 0
    if ratio < 1.0:
        for ticker in Buy.keys():
            original_qty = Buy[ticker]
            adjusted_qty = int(original_qty * ratio)
            Buy_qty[ticker] = adjusted_qty
    else:
        Buy_qty = Buy
    
    # split 데이터 만들기      
    round_split = HAA.make_split_data(order_time['round'])
    sell_split = [round_split["sell_splits"], round_split["sell_price_adjust"]]
    buy_split = [round_split["buy_splits"], round_split["buy_price_adjust"]]
    
    # Sell 주문
    Sell_order = Selling(Sell, sell_split, order_time)
    
    # Buy 주문
    Buy_order = Buying(Buy_qty, buy_split, TR_usd, order_time)

    # 데이터 저장
    save_TR_data(order_time, Sell_order, Buy_order, Hold_usd, target_weight, target_qty)

    sys.exit(0)

elif order_time['round'] == 25:  # 25회차 최종기록
    # ============================================
    # 1단계: 지난 라운드 TR_data 불러오기
    # ============================================
    try:
        TR_data = HAA.load_HAA_TR()
        Sell_order = TR_data['Sell_order']
        Buy_order = TR_data['Buy_order']
        Hold_usd = TR_data['CASH']
        target_weight = TR_data['target_weight']
        target_qty = TR_data['target_qty']
        target_usd = target_qty['CASH']
        # 이전 라운드 USD 저장 (검증용)
        prev_round_usd = Hold_usd
    
    except Exception as e:
        KA.SendMessage(f"HAA_TR JSON 파일 오류: {e}")
        sys.exit(0)    

    # ============================================
    # 2단계: 최종 체결 내역 확인 (주문 취소 전!)
    # ============================================
    # 성공한 주문만 필터링
    successful_sell_orders = [o for o in Sell_order if o.get('success', False)]
    successful_buy_orders = [o for o in Buy_order if o.get('success', False)]

    report_message = [] # 출력메세지 모으기

    # 매도 체결결과 반영
    if len(successful_sell_orders) > 0:
        sell_summary, message = HAA.calculate_sell_summary(successful_sell_orders)
        Hold_usd += sell_summary['net_amount']
        for i in message:
            report_message.append(i)
        report_message.append(f"매도 체결: ${sell_summary['net_amount']:.2f} (수수료 차감 후)")
    
    # 매수 체결결과 반영
    if len(successful_buy_orders) > 0:
        buy_summary, message = HAA.calculate_buy_summary(successful_buy_orders)
        Hold_usd -= buy_summary['total_amount']
        for i in message:
            report_message.append(i)
        report_message.append(f"매수 체결: ${buy_summary['total_amount']:.2f} (수수료 포함)")

    # USD 잔고 변화 로깅
    usd_change = Hold_usd - prev_round_usd
    report_message.append(f"USD 변화: ${usd_change:+.2f} (이전: ${prev_round_usd:.2f} → 현재: ${Hold_usd:.2f})")

    # ============================================
    # 3단계: 최종 미체결 주문 취소 (체결 확인 후!)
    # ============================================
    try:
        cancel_result, cancel_messages = HAA.cancel_all_unfilled_orders()
        report_message.extend(cancel_messages)
        if cancel_result['total'] > 0:
            report_message.append(f"미체결 주문 취소: {cancel_result['success']}/{cancel_result['total']}")
    except Exception as e:
        report_message.append(f"USLA 주문 취소 오류: {e}")
        
    # 출력
    KA.SendMessage("\n".join(report_message))    

    # ============================================
    # 4단계: 최종 데이터 저장 (USLA_data.json)
    # ============================================
    HAA_data = HAA.load_HAA_data()
    
    Hold = real_Hold()

    SPY = Hold.get('SPY', 0)    
    IWM = Hold.get('IWM', 0)
    VEA = Hold.get('VEA', 0)
    VWO = Hold.get('VWO', 0)
    PDBC = Hold.get('PDBC', 0)
    VNQ = Hold.get('VNQ', 0)
    TLT = Hold.get('TLT', 0)
    IEF = Hold.get('IEF', 0)
    CASH = Hold_usd

    # 당일 티커별 평가금 산출 - 수수료 포함
    SPY_eval = SPY * (HAA.get_US_current_price('SPY') * (1-HAA.fee))
    IWM_eval = IWM * (HAA.get_US_current_price('IWM') * (1-HAA.fee))
    VEA_eval = VEA * (HAA.get_US_current_price('VEA') * (1-HAA.fee))
    VWO_eval = VWO * (HAA.get_US_current_price('VWO') * (1-HAA.fee))
    PDBC_eval = PDBC * (HAA.get_US_current_price('PDBC') * (1-HAA.fee))
    VNQ_eval = VNQ * (HAA.get_US_current_price('VNQ') * (1-HAA.fee))
    TLT_eval = TLT * (HAA.get_US_current_price('TLT') * (1-HAA.fee))
    IEF_eval = IEF * (HAA.get_US_current_price('IEF') * (1-HAA.fee))
    stocks_eval_usd = SPY_eval + IWM_eval + VEA_eval + VWO_eval + PDBC_eval + VNQ_eval + TLT_eval + IEF_eval
    balance = stocks_eval_usd + CASH
    balanceKRW = int(balance * HAA.get_US_dollar_balance()['exchange_rate'])
   
    #data 조정
    HAA_data = {
        'date': str(order_time['date']),
        'regime_score': HAA_data['regime_signal'],
        'SPY_hold': SPY,
        'SPY_weight': HAA_data['SPY_weight'],
        'SPY_target_qty': HAA_data['SPY_target_qty'],
        'IWM_hold': IWM,
        'IWM_weight': HAA_data['IWM_weight'],
        'IWM_target_qty': HAA_data['IWM_target_qty'],
        'VEA_hold': VEA,
        'VEA_weight': HAA_data['VEA_weight'],
        'VEA_target_qty': HAA_data['VEA_target_qty'],
        'VWO_hold': VWO,
        'VWO_weight': HAA_data['VWO_weight'],
        'VWO_target_qty': HAA_data['VWO_target_qty'],
        'PDBC_hold': PDBC,
        'PDBC_weight': HAA_data['PDBC_weight'],
        'PDBC_target_qty': HAA_data['PDBC_target_qty'],
        'VNQ_hold': VNQ,
        'VNQ_weight': HAA_data['VNQ_weight'],
        'VNQ_target_qty': HAA_data['VNQ_target_qty'],
        'TLT_hold': TLT,
        'TLT_weight': HAA_data['TLT_weight'],
        'TLT_target_qty': HAA_data['TLT_target_qty'],
        'IEF_hold': IEF,
        'IEF_weight': HAA_data['IEF_weight'],
        'IEF_target_qty': HAA_data['IEF_target_qty'],
        'CASH_hold': CASH,
        'CASH_weight': HAA_data['CASH_weight'],
        'CASH_target_qty': HAA_data['CASH_target_qty'],
        'balance': balance,
        'last_day_balance': HAA_data['last_day_balance'],
        'last_month_balance': HAA_data['last_month_balance'],
        'last_year_balance': HAA_data['last_year_balance'],
        'daily_return': HAA_data['daily_return'],
        'monthly_return': HAA_data['monthly_return'],
        'yearly_return': HAA_data['yearly_return'],
        'exchange_rate': HAA_data['exchange_rate'],
        'balance_KRW': balanceKRW,
        'last_day_balance_KRW': HAA_data['last_day_balance_KRW'],
        'last_month_balance_KRW': HAA_data['last_month_balance_KRW'],
        'last_year_balance_KRW': HAA_data['last_year_balance_KRW'],
        'daily_return_KRW': HAA_data['daily_return_KRW'],
        'monthly_return_KRW': HAA_data['monthly_return_KRW'],
        'yearly_return_KRW': HAA_data['yearly_return_KRW']
    }

    HAA.save_HAA_data_json(HAA_data)

# 카톡 리밸 종료 결과 보내기
KA.SendMessage(f"KIS HAA {order_time['date']}\n당월 리벨런싱 완료")
KA.SendMessage(
    f"KIS HAA regime_signal: {HAA_data['regime_signal']}\n"
    f"SPY: {SPY}, weight: {HAA_data['SPY_weight']}\n"
    f"IWM: {IWM}, weight: {HAA_data['IWM_weight']}\n"
    f"VEA: {VEA}, weight: {HAA_data['VEA_weight']}\n"
    f"VWO: {VWO}, weight: {HAA_data['VWO_weight']}\n"
    f"PDBC: {PDBC}, weight: {HAA_data['PDBC_weight']}\n"
    f"VNQ: {VNQ}, weight: {HAA_data['VNQ_weight']}\n"
    f"TLT: {TLT}, weight: {HAA_data['TLT_weight']}\n"
    f"IEF: {IEF}, weight: {HAA_data['IEF_weight']}\n"
    f"CASH: {CASH}, weight: {HAA_data['CASH_weight']}\n"
    f"KIS HAA balance: {balance}\n"
    f"CASH: ${Hold_usd:.2f}, Risk regime인 경우 USD RP 월말일까지 투자"
)
