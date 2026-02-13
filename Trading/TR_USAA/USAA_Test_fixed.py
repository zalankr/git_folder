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
fee_rate = 0.0009 # 수수료 이벤트 계좌 0.09%
USAA_TR_path = "/var/autobot/TR_USAA/USAA_TR.json"
USAA_Message_path = "/var/autobot/TR_USAA/USAA_Message.json"

def health_check():
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

def get_balance():
    # 현재의 종합잔고를 USLA, HAA, CASH별로 산출 & 총잔고 계산
    USD_account = KIS.get_US_dollar_balance()
    if USD_account:
        USD = USD_account.get('withdrawable', 0)  # 키가 없을 경우 0 반환
    else:
        USD = 0  # API 호출 실패 시 처리
    time_module.sleep(0.1)

    USLA_balance = 0 # 해당 모델 현재 달러화 잔고
    USLA_qty = {} # 해당 티커 현재 보유량
    USLA_price  = {} # 해당 티커 현재 가격
    for ticker in USLA_ticker:
        balance = KIS.get_ticker_balance(ticker)
        if isinstance(balance, dict):  # 딕셔너리인 경우만 처리
            eval_amount = balance.get('eval_amount', 0)
            USLA_qty[ticker] = balance.get('holding_qty', 0)
            USLA_price[ticker] = balance.get('current_price', 0)
        else:
            eval_amount = 0  # 문자열(에러) 반환 시 처리
        USLA_balance += eval_amount
        time_module.sleep(0.1)

    HAA_balance = 0 # 해당 모델 현재 달러화 잔고
    HAA_qty = {} # 해당 티커 현재 보유량
    HAA_price  = {} # 해당 티커 현재 가격
    for ticker in HAA_ticker:
        if ticker == 'TIP':
            continue # TIP은 Regime signal 확인용으로 투자, 보유용이 아니라서 제외
        balance = KIS.get_ticker_balance(ticker)
        if isinstance(balance, dict):  # 딕셔너리인 경우만 처리
            eval_amount = balance.get('eval_amount', 0)
            HAA_qty[ticker] = balance.get('holding_qty', 0)
            HAA_price[ticker] = balance.get('current_price', 0)
        else:
            eval_amount = 0  # 문자열(에러) 반환 시 처리
        HAA_balance += eval_amount
        time_module.sleep(0.1)

    Total_balance = USLA_balance + HAA_balance + USD # 전체 잔고

    return USD, USLA_balance, USLA_qty, USLA_price, HAA_balance, HAA_qty, HAA_price, Total_balance

def Selling(USLA, HAA, sell_split_USLA, sell_split_HAA, order_time):
    """
    매도 주문 실행 함수 - 개선버전 (메시지 통합)
    
    Parameters:
    - USLA: USLA 모델 내 티커별 트레이딩 딕셔너리
    - HAA: HAA 모델 내 티커별 트레이딩 딕셔너리
    - sell_split_USLA: USLA 모델의 분할 정보 [분할횟수, [가격조정비율 리스트]]
    - sell_split_HAA: HAA 모델의 분할 정보 [분할횟수, [가격조정비율 리스트]]
    - order_time: 현재 주문 시간 정보 딕셔너리  # 추가
    
    Returns:
    - Sell_order: 주문 결과 리스트 (성공/실패 모두 포함)
    """  
    Sell_order = []
    order_messages = []
    
    # 수정: 함수 내부에서 호출하지 않고 매개변수로 받음
    round_info = f"{order_time['round']}/{order_time['total_round']}회 매도주문"
    order_messages.append(round_info)

    Sell_USLA = {}
    for ticker in USLA.keys():
        if USLA[ticker]['sell_qty'] > 0:
            Sell_USLA[ticker] = USLA[ticker]['sell_qty']

    Sell_HAA = {}
    for ticker in HAA.keys():
        if HAA[ticker]['sell_qty'] > 0:
            Sell_HAA[ticker] = HAA[ticker]['sell_qty']

    Sell = {**Sell_USLA, **Sell_HAA}

    if len(Sell.keys()) == 0:
        order_messages.append("매도할 종목이 없습니다.")
        return Sell_order, order_messages

    for ticker in Sell.keys():
        if Sell[ticker] == 0:
            continue
        
        # ✅ 핵심 수정: 티커별로 올바른 분할 설정 사용
        if ticker in USLA_ticker:
            split_count = sell_split_USLA[0]
            price_multipliers = sell_split_USLA[1]
        else:
            split_count = sell_split_HAA[0]
            price_multipliers = sell_split_HAA[1]
        
        qty_per_split = int(Sell[ticker] // split_count)

        if ticker in USLA_ticker:
            current_price = USLA[ticker].get("current_price", 0)
        else:
            current_price = HAA[ticker].get("current_price", 0)

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

        for i in range(split_count):
            if i == split_count - 1:
                quantity = Sell[ticker] - qty_per_split * (split_count - 1)
            else:
                quantity = qty_per_split
            
            if quantity == 0:
                continue

            price = round(current_price * price_multipliers[i], 2)
                
            try:
                order_info, order_sell_message = KIS.order_sell_US(ticker, quantity, price)
                order_messages.extend(order_sell_message)
                
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
                else:
                    error_msg = order_info.get('error_message', 'Unknown error') if order_info else 'API 호출 실패'
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
            
            # 같은 티커의 분할 주문 사이는 0.3초, 다른 티커로 넘어갈 때는 0.3초
            if i < split_count - 1:
                time_module.sleep(0.3)
            else:
                time_module.sleep(0.3)
    
    success_count = sum(1 for order in Sell_order if order['success'])
    total_count = len(Sell_order)
    order_messages.append(f"매도 주문: {success_count}/{total_count} 완료")
    
    return Sell_order, order_messages

def Buying(USLA, HAA, buy_split_USLA, buy_split_HAA, order_time):
    """
    매수 주문 실행 함수 - 버그 수정 버전
    
    Parameters:
    - USLA: USLA 모델 내 티커별 트레이딩 딕셔너리
    - HAA: HAA 모델 내 티커별 트레이딩 딕셔너리
    - buy_split_USLA: USLA 모델의 분할 정보 [분할횟수, [가격조정비율 리스트]]
    - buy_split_HAA: HAA 모델의 분할 정보 [분할횟수, [가격조정비율 리스트]]
    - order_time: 현재 주문 시간 정보 딕셔너리
    
    Returns:
    - Buy_order: 주문 결과 리스트 (성공/실패 모두 포함)
    """
    Buy_order = []
    order_messages = []

    round_info = f"{order_time['round']}/{order_time['total_round']}회 매수주문"
    order_messages.append(round_info)    
    
    Buy_USLA = {}
    for ticker in USLA.keys():
        if USLA[ticker]['buy_qty'] > 0:
            Buy_USLA[ticker] = USLA[ticker]['buy_qty']

    Buy_HAA = {}
    for ticker in HAA.keys():
        if HAA[ticker]['buy_qty'] > 0:
            Buy_HAA[ticker] = HAA[ticker]['buy_qty']

    Buy = {**Buy_USLA, **Buy_HAA}
    
    if len(Buy.keys()) == 0:
        order_messages.append("매수할 종목이 없습니다.")
        return Buy_order, order_messages
    
    for ticker in Buy.keys():
        if Buy[ticker] == 0:
            order_messages.append(f"{ticker} 매수 수량 0")
            continue
        
        # ✅ 핵심 수정: 티커별로 올바른 분할 설정 사용
        if ticker in USLA_ticker:
            split_count = buy_split_USLA[0]
            price_multipliers = buy_split_USLA[1]
        else:
            split_count = buy_split_HAA[0]
            price_multipliers = buy_split_HAA[1]
        
        qty_per_split = int(Buy[ticker] // split_count)

        if ticker in USLA_ticker:
            current_price = USLA[ticker].get("current_price", 0)
        else:
            current_price = HAA[ticker].get("current_price", 0)
        
        if not isinstance(current_price, (int, float)) or current_price <= 0:
            error_msg = f"{ticker} 가격 조회 실패 - 주문 스킵"
            order_messages.append(error_msg)
            Buy_order.append({
                'success': False,
                'ticker': ticker,
                'quantity': Buy[ticker],
                'price': 0,
                'order_number': '',
                'order_time': datetime.now().strftime('%H%M%S'),
                'error_message': error_msg,
                'split_index': -1
            })
            continue

        for i in range(split_count):
            if i == split_count - 1:
                quantity = Buy[ticker] - qty_per_split * (split_count - 1)
            else:
                quantity = qty_per_split
            
            if quantity == 0:
                continue

            price = round(current_price * price_multipliers[i], 2)
                
            try:
                order_info, order_buy_message = KIS.order_buy_US(ticker, quantity, price)
                order_messages.extend(order_buy_message)
                
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
                else:
                    error_msg = order_info.get('error_message', 'Unknown error') if order_info else 'API 호출 실패'
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

            # 같은 티커의 분할 주문 사이는 0.3초, 다른 티커로 넘어갈 때는 0.3초
            if i < split_count - 1:
                time_module.sleep(0.3)
            else:
                time_module.sleep(0.3)

    success_count = sum(1 for order in Buy_order if order['success'])
    total_count = len(Buy_order)
    order_messages.append(f"매수 주문: {success_count}/{total_count} 완료")

    return Buy_order, order_messages

def save_TR_data(order_time, Sell_order, Buy_order, USLA, HAA):
    """
    저장 실패 시에도 백업 파일 생성
    """
    TR_data = {} # 초기화
    message = []
    TR_data = {
        "round": order_time['round'],
        "timestamp": datetime.now().isoformat(),  # 타임스탬프 추가
        "Sell_order": Sell_order,
        "Buy_order": Buy_order,
        "USLA": USLA,
        "HAA": HAA
    }
    
    try:
        # 정상 
        with open(USAA_TR_path, 'w', encoding='utf-8') as f:
            json.dump(TR_data, f, ensure_ascii=False, indent=4)
        
        message.append(
            f"{order_time['date']}, {order_time['season']} 리밸런싱\n"
            f"{order_time['time']} {order_time['round']}/{order_time['total_round']}회차 거래저장완료\n"
        )
        
    except Exception as e:
        # 저장 실패 시 백업 파일 생성
        message.append(f"USAA_TR 데이터 저장 실패: {e}")
        
        backup_path = f"/var/autobot/TR_USAA/USAA_TR_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(TR_data, f, ensure_ascii=False, indent=4)
            message.append(f"USAA 백업 파일 생성: {backup_path}")
        except Exception as backup_error:
            message.append(f"USAA 백업 파일 생성도 실패: {backup_error}")
            # 최후의 수단: 카카오로 데이터 전송
            message.append(f"USAA TR_data: {json.dumps(TR_data, ensure_ascii=False)[:1000]}")

    return message

def get_prices(tickers):
    """현재 가격 조회 (KIS API 사용)"""
    try:
        prices = {}            
        for ticker in tickers:
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

def get_monthly_prices_kis(ticker: str, start_date: str, end_date: str) -> pd.Series:
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

def get_daily_prices_kis(tickers: list, days: int = 90) -> pd.DataFrame:
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

def AGG_regime():
    """AGG 채권 ETF의 Regime 신호 계산 (KIS API 사용)"""
    AGG_regime_message = []
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
            AGG_regime_message.append("USLA 경고: AGG 데이터가 충분하지 않습니다.")
            return 0, AGG_regime_message

        current_price = agg_data.iloc[-1]  # 최신 가격
        avg_price = agg_data.mean()  # 4개월 평균

        regime = current_price - avg_price

        return regime, AGG_regime_message
        
    except Exception as e:
        AGG_regime_message.append(f"USLA Regime 계산 오류: {e}")
        return 0, AGG_regime_message

def USLA_momentum():
    """모멘텀 점수 계산 (KIS API 사용)"""
    USLA_momentum_message = []
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
                USLA_momentum_message.append(f"USLA {ticker} 월간 데이터 조회 오류: {e}")
                continue
        
        if not price_data:
            USLA_momentum_message.append("USLA 경고: 모멘텀 계산을 위한 데이터를 가져올 수 없습니다.")
            return pd.DataFrame(), USLA_momentum_message
        
        # DataFrame으로 변환
        price_df = pd.DataFrame(price_data)
        
        if len(price_df) < 13:
            USLA_momentum_message.append("USLA 경고: 모멘텀 계산을 위한 데이터가 충분하지 않습니다.")
            return pd.DataFrame(), USLA_momentum_message
            
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
                USLA_momentum_message.append(f"USLA {ticker} 모멘텀 계산 오류: {e}")
                continue
        
        if not momentum_scores:
            return pd.DataFrame(), USLA_momentum_message
            
        momentum_df = pd.DataFrame(momentum_scores)
        momentum_df['rank'] = momentum_df['momentum'].rank(ascending=False)
        momentum_df = momentum_df.sort_values('rank').reset_index(drop=True)
        
        return momentum_df, USLA_momentum_message
        
    except Exception as e:
        USLA_momentum_message.append(f"USLA 모멘텀 점수 계산 오류: {e}")
        return pd.DataFrame(), USLA_momentum_message

def USLA_portfolio_weights(top_tickers):
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
        equal_weight = 1 / len(top_tickers) # 동일가중
        return {ticker: equal_weight for ticker in top_tickers}

def USLA_strategy(regime, momentum_df):
    """전략 실행"""
    USLA_strategy_message = []
    
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

    USLA_strategy_message.append("\n".join(lines))
        
    # 3. 투자 전략 결정
    if regime < 0:
        USLA_strategy_message.append(f"USLA Regime: {regime:.2f} < 0 → 100% CASH")
        
        allocation = {ticker: 0.0 for ticker in USLA_ticker}
        allocation['CASH'] = 1.0

    else:
        # 상위 2개 ETF 선택
        if len(momentum_df) < 2:
            USLA_strategy_message.append(f"USLA 경고: 모멘텀 데이터가 2개 미만입니다. CASH로 대기합니다.")
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
    current_prices = get_prices(USLA_ticker)
    
    # 4. 결과 출력
    for ticker in USLA_ticker:
        if allocation.get(ticker, 0) > 0:
            USLA_strategy_message.append(f"USLA {ticker}: {allocation[ticker]:.1%} (현재가: ${current_prices[ticker]:.2f})")

    result = {
        'regime': regime,
        'momentum': momentum_df,
        'allocation': allocation,
        'current_prices': current_prices
    }

    return result, USLA_strategy_message

def USLA_target_regime():
    """target 티커별 목표 비중 산출"""
    USLA_target_regime_message = []
    regime, AGG_regime_message = AGG_regime()
    USLA_target_regime_message.extend(AGG_regime_message)
    momentum_df, USLA_momentum_message = USLA_momentum()
    USLA_target_regime_message.extend(USLA_momentum_message)
    result, USLA_strategy_message = USLA_strategy(regime, momentum_df)
    USLA_target_regime_message.extend(USLA_strategy_message)
    USLA_regime = result['regime']

    if result is None:
        USLA_target_regime_message.append("USLA 경고: 전략 실행 실패, CASH로 대기")
        return {'CASH': 1.0}, USLA_regime, USLA_target_regime_message
    USLA_target = {
        ticker: weight 
        for ticker, weight in result['allocation'].items() 
        if weight >= 0.001
    }
    
    return USLA_target, USLA_regime, USLA_target_regime_message

def HAA_target_regime():
    """HAA 모멘텀 점수 계산 (KIS API 사용)"""
    HAA_target_regime_message = []
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
                HAA_target_regime_message.append(f"HAA {ticker} 월간 데이터 조회 오류: {e}")
                continue
        
        if not price_data:
            HAA_target_regime_message.append("HAA 경고: 모멘텀 계산을 위한 데이터를 가져올 수 없습니다.")
            return HAA_target, HAA_regime, HAA_target_regime_message
        
        # DataFrame으로 변환
        price_df = pd.DataFrame(price_data)
        
        if len(price_df) < 13:
            HAA_target_regime_message.append("HAA 경고: 모멘텀 계산을 위한 데이터가 충분하지 않습니다.")
            return HAA_target, HAA_regime, HAA_target_regime_message
            
        momentum_scores = []
        
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
                HAA_target_regime_message.append(f"HAA {ticker} 모멘텀 계산 오류: {e}")
                continue
        
        if not momentum_scores:
            HAA_target_regime_message.append("HAA 경고: 계산된 모멘텀 데이터를 찾을 수 없습니다.")
            return HAA_target, HAA_regime, HAA_target_regime_message
        
        # Regime구하기
        regime = None
        for score in momentum_scores:
            if score['ticker'] == 'TIP':
                regime = score['momentum']
                break

        if regime is None:
            HAA_target_regime_message.append(f"HAA 경고: {Regime_ETF} 모멘텀 데이터를 찾을 수 없습니다.")
            return HAA_target, HAA_regime, HAA_target_regime_message
        else:
            HAA_target_regime_message.append(f"HAA: {Regime_ETF} 모멘텀 = {regime:.2f}")

        # 데이터프레임 만들기
        momentum_df = pd.DataFrame(momentum_scores)
        if momentum_df is None:
            HAA_target_regime_message.append(f"HAA 경고: momentum_df를 찾을 수 없습니다.")
            return HAA_target, HAA_regime, HAA_target_regime_message
        else:
            HAA_target_regime_message.append(f"HAA: momentum_df 생성 성공")

        # regime 양수일 때 Aggresive ETF의 모멘텀 점수 구하기
        if regime >= 0:
            aggresive_df = momentum_df[momentum_df['ticker'].isin(Aggresive_ETF)].copy()
            aggresive_df['rank'] = aggresive_df['momentum'].rank(ascending=False)
            aggresive_df = aggresive_df.sort_values('rank').reset_index(drop=True)

            # 포트폴리오 ticker와 weights를 allocation dictionary에 기입
            if len(aggresive_df) < 4:
                HAA_target_regime_message.append(f"HAA 경고: Aggressive ETF {len(aggresive_df)}개만 있음")
                # 있는 만큼만 균등 배분
                top_tickers = aggresive_df['ticker'].tolist()
                weights = 1.0 / len(top_tickers)
            else:
                top_tickers = aggresive_df.head(4)['ticker'].tolist()
                weights = 0.25

            HAA_target = {ticker: weights for ticker in top_tickers}
            HAA_regime = regime

            for ticker, weight in HAA_target.items():
                HAA_target_regime_message.append(f"{ticker}: {weight:.2%}")

            return HAA_target, HAA_regime, HAA_target_regime_message

        # regime 음수일 때 defensive ETF의 모멘텀 점수 구하기    
        elif regime < 0:
            defensive_df = momentum_df[momentum_df['ticker'].isin(Defensive_ETF)].copy()
            defensive_df['rank'] = defensive_df['momentum'].rank(ascending=False)
            defensive_df = defensive_df.sort_values('rank').reset_index(drop=True)

            top_ticker = defensive_df.head(1)['ticker'].iloc[0]

            # 포트폴리오 ticker와 weights를 allocation dictionary에 기입
            if top_ticker == 'IEF':
                HAA_target = {'IEF': 1.0}

            elif top_ticker == 'BIL':
                HAA_target = {'CASH': 1.0} # 100% 현금 보유

            HAA_regime = regime
            HAA_target_regime_message.append(f"{top_ticker}: 100%")

            return HAA_target, HAA_regime, HAA_target_regime_message

    except Exception as e:
        HAA_target_regime_message.append(f"HAA_momentum 전체 오류: {e}")
        return HAA_target, HAA_regime, HAA_target_regime_message
    
def split_data(round):
    '''모델과 회차, 티커별 분할횟수와 분할당 가격 산출'''
    if round in range(1, 12): # Pre-Market
        sell_splits = 4
        sell_price_USLA = [1.015, 1.03, 1.045, 1.06]
        sell_price_HAA = [1.0075, 1.0150, 1.0225, 1.0300]
        buy_splits = 2
        buy_price_USLA = [0.995, 0.99]
        buy_price_HAA = [0.9975, 0.9950]

    elif round in range(12, 25): # Regular
        sell_splits = 5
        sell_price_USLA = [1.004, 1.008, 1.012, 1.016, 1.02]
        sell_price_HAA = [1.002, 1.004, 1.006, 1.008, 1.01]
        buy_splits = 5
        buy_price_USLA = [0.996, 0.992, 0.988, 0.984, 0.98]
        buy_price_HAA = [0.998, 0.996, 0.994, 0.992, 0.99]

        if round == 12:
            pass
        elif round == 13:
            sell_price_USLA[0] = 0.99
            sell_price_HAA[0] = 0.99
        elif round == 14:
            sell_splits = 4
            sell_price_USLA = sell_price_USLA[:sell_splits]
            sell_price_HAA = sell_price_HAA[:sell_splits]
            buy_price_USLA[0] = 1.01
            buy_price_HAA[0] = 1.01
        elif round == 15:
            sell_splits = 4
            sell_price_USLA = sell_price_USLA[:sell_splits]
            sell_price_HAA = sell_price_HAA[:sell_splits]
            buy_splits = 4
            buy_price_USLA = buy_price_USLA[:buy_splits]
            buy_price_HAA = buy_price_HAA[:buy_splits]
        elif round == 16:
            sell_splits = 4
            sell_price_USLA = sell_price_USLA[:sell_splits]
            sell_price_USLA[0] = 0.99
            sell_price_HAA = sell_price_HAA[:sell_splits]
            sell_price_HAA[0] = 0.99
            buy_splits = 4
            buy_price_USLA = buy_price_USLA[:buy_splits]
            buy_price_HAA = buy_price_HAA[:buy_splits]
        elif round == 17:
            sell_splits = 3
            sell_price_USLA = sell_price_USLA[:sell_splits]
            sell_price_HAA = sell_price_HAA[:sell_splits]
            buy_splits = 4
            buy_price_USLA = buy_price_USLA[:buy_splits]
            buy_price_HAA = buy_price_HAA[:buy_splits]
            buy_price_USLA[0] = 1.01
            buy_price_HAA[0] = 1.01
        elif round == 18:
            sell_splits = 3
            sell_price_USLA = sell_price_USLA[:sell_splits]
            sell_price_HAA = sell_price_HAA[:sell_splits]
            buy_splits = 3
            buy_price_USLA = buy_price_USLA[:buy_splits]
            buy_price_HAA = buy_price_HAA[:buy_splits]
        elif round == 19:
            sell_splits = 3
            sell_price_USLA = sell_price_USLA[:sell_splits]
            sell_price_HAA = sell_price_HAA[:sell_splits]    
            sell_price_USLA[0] = 0.99
            sell_price_HAA[0] = 0.99
            buy_splits = 3
            buy_price_USLA = buy_price_USLA[:buy_splits]
            buy_price_HAA = buy_price_HAA[:buy_splits]
        elif round == 20:
            sell_splits = 2
            sell_price_USLA = sell_price_USLA[:sell_splits]
            sell_price_HAA = sell_price_HAA[:sell_splits]
            buy_splits = 3
            buy_price_USLA = buy_price_USLA[:buy_splits]
            buy_price_HAA = buy_price_HAA[:buy_splits]
            buy_price_USLA[0] = 1.01
            buy_price_HAA[0] = 1.01
        elif round == 21:
            sell_splits = 2
            sell_price_USLA = sell_price_USLA[:sell_splits]
            sell_price_HAA = sell_price_HAA[:sell_splits]
            buy_splits = 2
            buy_price_USLA = buy_price_USLA[:buy_splits]
            buy_price_HAA = buy_price_HAA[:buy_splits]
        elif round == 22:
            sell_splits = 2
            sell_price_USLA = sell_price_USLA[:sell_splits]
            sell_price_HAA = sell_price_HAA[:sell_splits]
            sell_price_USLA[0] = 0.99
            sell_price_HAA[0] = 0.99
            buy_splits = 2
            buy_price_USLA = buy_price_USLA[:buy_splits]
            buy_price_HAA = buy_price_HAA[:buy_splits]
        elif round == 23:
            sell_splits = 1
            sell_price_USLA = sell_price_USLA[:sell_splits]
            sell_price_HAA = sell_price_HAA[:sell_splits]
            sell_price_USLA[0] = 0.98
            sell_price_HAA[0] = 0.98
            buy_splits = 2
            buy_price_USLA = buy_price_USLA[:buy_splits]
            buy_price_USLA[0] = 1.01
            buy_price_HAA = buy_price_HAA[:buy_splits]
            buy_price_HAA[0] = 1.01
        elif round == 24:
            sell_splits = 1
            sell_price_USLA = [0.98]
            sell_price_HAA = [0.98]
            buy_splits = 1
            buy_price_USLA = [1.02]
            buy_price_HAA = [1.02]
        
    round_split = {
        "sell_splits": sell_splits, 
        "sell_price_USLA": sell_price_USLA,
        "sell_price_HAA": sell_price_HAA,
        "buy_splits": buy_splits, 
        "buy_price_USLA": buy_price_USLA,
        "buy_price_HAA": buy_price_HAA
    }

    return round_split

def send_messages_in_chunks(message, max_length=900):
    current_chunk = []
    current_length = 0
    
    for msg in message:
        msg_length = len(msg) + 1  # \n 포함
        if current_length + msg_length > max_length:
            KA.SendMessage("\n".join(current_chunk))
            time_module.sleep(1)
            current_chunk = [msg]
            current_length = msg_length
        else:
            current_chunk.append(msg)
            current_length += msg_length
    
    if current_chunk:
        KA.SendMessage("\n".join(current_chunk))

# ============================================
# 메인 로직 # 연단위 모델간 리밸런싱
# ============================================

# 날짜 체크
order_time = USAA_Calender.check_order_time()
order_time['time'] = order_time['time'].replace(second=0, microsecond=0)

order_time['round'] = 1 ######################################################## 테스트 후 지울 것

if order_time['season'] == "USAA_not_rebalancing" or order_time['round'] == 0:
    KA.SendMessage(f"USAA 리밸런싱일이 아닙니다.\n{order_time['date']}가 USAA_day 리스트에 없습니다.")
    sys.exit(0)

# 메인로직 시작 전 시스템 상태 확인
health_check()
start_message = [] # 출력메세지 모으기
start_message.append(f"USAA {order_time['date']} 리밸런싱\n{order_time['time']}, {order_time['round']}/{order_time['total_round']}회차 거래시작")

if order_time['round'] == 1:
    '''round 1회에서 목표 Trading qty 구하기'''
    message = [] # 메세지 초기화
    message.extend(start_message)
    # USAA regime체크 및 거래 목표 데이터 만들기
    USLA_target, USLA_regime, USLA_message = USLA_target_regime()
    message.extend(USLA_message)
    
    # HAA regime체크 및 거래 목표 데이터 만들기
    HAA_target, HAA_regime, HAA_message = HAA_target_regime()
    message.extend(HAA_message)

    # 계좌잔고 조회
    USD, USLA_balance, USLA_qty, USLA_price, HAA_balance, HAA_qty, HAA_price, Total_balance = get_balance()

    ## 헷징 모드 확인 후 비중 조정: 빈 딕셔너리 체크 (값이 모두 0인지)
    USLA_has_position = any(qty > 0 for qty in USLA_qty.values())
    HAA_has_position = any(qty > 0 for qty in HAA_qty.values())

    if not USLA_has_position and not HAA_has_position:
        # 둘 다 보유 없음
        USLA_target_weight = 0.7
        USLA_target_balance = Total_balance * USLA_target_weight
        HAA_target_weight = 0.3
        HAA_target_balance = Total_balance * HAA_target_weight
        
    elif not USLA_has_position and HAA_has_position:
        # USLA만 없음
        USLA_target_balance = USD * (70/70.6)
        USLA_target_weight = (USD * (70/70.6)) / Total_balance
        HAA_target_balance = HAA_balance + (USD * (0.6/70.6))
        HAA_target_weight = (HAA_balance + (USD * (0.6/70.6))) / Total_balance
    elif USLA_has_position and not HAA_has_position:
        # HAA만 없음
        USLA_target_balance = USLA_balance + (USD * 1.4 / 31.4)
        USLA_target_weight = (USLA_balance + (USD * 1.4 / 31.4)) / Total_balance
        HAA_target_balance = USD * (30 / 31.4)
        HAA_target_weight = (USD * (30 / 31.4)) / Total_balance
    else:
        # 둘 다 보유
        USLA_target_balance = USLA_balance + (USD * 0.7)
        USLA_target_weight = (USLA_balance + (USD * 0.7)) / Total_balance
        HAA_target_balance = HAA_balance + (USD * 0.3)
        HAA_target_weight = (HAA_balance + (USD * 0.3)) / Total_balance

    ## 만약 1월에는 비중 리밸런싱
    order_time['month'] = 1 ######################################################## 최초 + 테스트 후 지울 것
    if order_time['month'] == 1:
        USLA_target_weight = 0.7
        USLA_target_balance = Total_balance * USLA_target_weight
        HAA_target_weight = 0.3
        HAA_target_balance = Total_balance * HAA_target_weight

    USLA = {}
    for ticker in USLA_ticker:
        USLA_price[ticker] = KIS.get_US_current_price(ticker)
        if ticker not in USLA_target:
            USLA[ticker] = {
                'hold_qty': USLA_qty.get(ticker, 0), # 현재 보유량
                'current_price': USLA_price[ticker] if ticker in USLA_price else KIS.get_US_current_price(ticker), # 해당 티커의 현재가
                'target_weight': 0, # 해당 티커의 목표비중 (2% 거래 안정성 마진 적용)
                'target_balance': 0, # 해당 티커의 목표투자금 (2% 거래 안정성 마진 적용)
                'target_qty': 0, # 해당 티커의 목표수량
                'buy_qty': 0, # 해당 티커의 매수 수량
                'sell_qty': USLA_qty.get(ticker, 0) # 해당 티커의 매도 수량
            }
        elif ticker in USLA_target:
            if USLA_price[ticker] <= 0:
                USLA_target_qty = 0
            else:
                USLA_target_qty = int((USLA_target[ticker] * USLA_target_balance * 0.98) / USLA_price[ticker])  # 2% 거래 안정성 마진 적용
            USLA[ticker] = {
                'hold_qty': USLA_qty.get(ticker, 0), # 현재 보유량
                'current_price': USLA_price[ticker] if ticker in USLA_price else KIS.get_US_current_price(ticker), # 해당 티커의 현재가
                'target_weight': USLA_target[ticker] * USLA_target_weight * 0.98, # 해당 티커의 목표비중 (2% 거래 안정성 마진 적용)
                'target_balance': USLA_target[ticker] * USLA_target_balance * 0.98, # 해당 티커의 목표투자금 (2% 거래 안정성 마진 적용)
                'target_qty': USLA_target_qty, # 해당 티커의 목표수량
                'buy_qty': USLA_target_qty - USLA_qty.get(ticker, 0) if USLA_target_qty > USLA_qty.get(ticker, 0) else 0, # 해당 티커의 매수 수량
                'sell_qty': USLA_qty.get(ticker, 0) - USLA_target_qty if USLA_target_qty < USLA_qty.get(ticker, 0) else 0 # 해당 티커의 매도 수량
            }

    HAA = {}
    for ticker in HAA_ticker:
        if ticker == 'TIP':
            continue
        HAA_price[ticker] = KIS.get_US_current_price(ticker)
        if ticker not in HAA_target:
            HAA[ticker] = {
                'hold_qty': HAA_qty.get(ticker, 0), # 현재 보유량
                'current_price': HAA_price[ticker] if ticker in HAA_price else KIS.get_US_current_price(ticker), # 해당 티커의 현재가
                'target_weight': 0, # 해당 티커의 목표비중 (2% 거래 안정성 마진 적용)
                'target_balance': 0, # 해당 티커의 목표투자금 (2% 거래 안정성 마진 적용)
                'target_qty': 0, # 해당 티커의 목표수량
                'buy_qty': 0, # 해당 티커의 매수 수량
                'sell_qty': HAA_qty.get(ticker, 0) # 해당 티커의 매도 수량                
            }
        elif ticker in HAA_target:
            if HAA_price[ticker] <= 0:
                HAA_target_qty = 0
            else:
                HAA_target_qty = int((HAA_target[ticker] * HAA_target_balance * 0.98) / HAA_price[ticker])  # 2% 거래 안정성 마진 적용
            HAA[ticker] = {
                'hold_qty': HAA_qty.get(ticker, 0), # 현재 보유량
                'current_price': HAA_price[ticker] if ticker in HAA_price else KIS.get_US_current_price(ticker), # 해당 티커의 현재가
                'target_weight': HAA_target[ticker] * HAA_target_weight * 0.98, # 해당 티커의 목표비중 (2% 거래 안정성 마진 적용)
                'target_balance': HAA_target[ticker] * HAA_target_balance * 0.98, # 해당 티커의 목표투자금 (2% 거래 안정성 마진 적용)
                'target_qty': HAA_target_qty, # 해당 티커의 목표수량
                'buy_qty': HAA_target_qty - HAA_qty.get(ticker, 0) if HAA_target_qty > HAA_qty.get(ticker, 0) else 0, # 해당 티커의 매수 수량
                'sell_qty': HAA_qty.get(ticker, 0) - HAA_target_qty if HAA_target_qty < HAA_qty.get(ticker, 0) else 0 # 해당 티커의 매도 수량                
            }

    # 목표비중 합계 검증
    total_weight = 0
    for ticker in USLA.keys():
        total_weight += USLA[ticker].get('target_weight', 0)
    for ticker in HAA.keys():
        total_weight += HAA[ticker].get('target_weight', 0)

    if total_weight > 1.01:
        error_msg = f"❌ 목표 비중 초과: {total_weight:.2%}"
        message.append(error_msg)
        KA.SendMessage("\n".join(message))
        sys.exit(1)
    elif total_weight < 0.90:
        message.append(f"⚠️ 목표 비중 부족: {total_weight:.2%}")
    else:
        message.append(f"✓ 목표 비중 합계: {total_weight:.2%}")

    # 회차별 분할 데이터 트레이딩
    round_split = split_data(order_time['round'])
    sell_split_USLA = [round_split["sell_splits"], round_split["sell_price_USLA"]]
    buy_split_USLA = [round_split["buy_splits"], round_split["buy_price_USLA"]]
    sell_split_HAA = [round_split["sell_splits"], round_split["sell_price_HAA"]]
    buy_split_HAA = [round_split["buy_splits"], round_split["buy_price_HAA"]]
    
    # 매도주문
    Sell_order, order_messages = Selling(USLA, HAA, sell_split_USLA, sell_split_HAA, order_time)
    message.extend(order_messages)
    order_messages = [] # 메세지 초기화
    
    # 예수금에 맞는 주문수량 구하기
    FULL_BUYUSD = 0
    price_error = False
    
    for ticker in USLA_ticker:
        if USLA[ticker]['current_price'] <= 0:
            message.append(f"⚠️ {ticker} 가격 조회 실패 - 매수 스킵")
            USLA[ticker]['buy_qty'] = 0
            price_error = True
            continue
        invest = USLA[ticker]['buy_qty'] * USLA[ticker]['current_price']
        FULL_BUYUSD += invest
        
    for ticker in HAA_ticker:
        if ticker == 'TIP':
            continue
        if HAA[ticker]['current_price'] <= 0:
            message.append(f"⚠️ {ticker} 가격 조회 실패 - 매수 스킵")
            HAA[ticker]['buy_qty'] = 0
            price_error = True
            continue
        invest = HAA[ticker]['buy_qty'] * HAA[ticker]['current_price']
        FULL_BUYUSD += invest
        
    if price_error:
        message.append("⚠️ 일부 종목 가격 조회 실패로 매수 수량 조정됨")   
        
    if FULL_BUYUSD > USD:
        ADJUST_RATE = USD / FULL_BUYUSD
        for ticker in USLA_ticker:
            USLA[ticker]['buy_qty'] = int(USLA[ticker]['buy_qty'] * ADJUST_RATE)
        for ticker in HAA_ticker:
            HAA[ticker]['buy_qty'] = int(HAA[ticker]['buy_qty'] * ADJUST_RATE)
    else:
        pass  # 예수금이 충분할 경우 조정 없음

    # 매수주문
    Buy_order, order_messages = Buying(USLA, HAA, buy_split_USLA, buy_split_HAA, order_time)
    message.extend(order_messages)

    # 다음 order time으로 넘길 Trading data json 데이터 저장
    saveTR_message = save_TR_data(order_time, Sell_order, Buy_order, USLA, HAA)
    message.extend(saveTR_message)
    send_messages_in_chunks(message, max_length=900)

    print("\n".join(message)) #################################################지울 것

    sys.exit(0)

elif order_time['round'] in range(2, 25):  # Round 2~24회차
    if order_time['round'] == 2:
        message = [] # 메세지 초기화
    else:
        with open(USAA_Message_path, 'r', encoding='utf-8') as f:
            message = json.load(f)
    print_time = [4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24]
    if order_time['round'] in print_time:
        send_messages_in_chunks(message, max_length=900)
        message = [] # 메세지 초기화
        
    message.extend(start_message)

    # ====================================
    # 1단계: 지난 라운드 TR_data 불러오기
    # ====================================
    try:
        with open(USAA_TR_path, 'r', encoding='utf-8') as f:
            TR_data = json.load(f)
    except Exception as e:
        message.append(f"USAA_TR JSON 파일 오류: {e}")
        sys.exit(0)

    # ============================================
    # 2단계: 미체결 주문 취소
    # ============================================
    try:
        cancel_summary, cancel_messages = KIS.cancel_all_unfilled_orders()
        message.extend(cancel_messages)
        if cancel_summary['total'] > 0:
            message.append(f"미체결 주문 취소: {cancel_summary['success']}/{cancel_summary['total']}")
    except Exception as e:
        message.append(f"USAA 주문 취소 오류: {e}")

    print("\n".join(message)) #################################################지울 것

#     # ============================================
#     # 3단계: 새로운 주문 준비 및 실행
#     # ============================================
#     # 계좌잔고 조회
#     USD, USLA_balance, USLA_qty, USLA_price, HAA_balance, HAA_qty, HAA_price, Total_balance = get_balance()

#     # 목표 비중 만들기
#     USLA = TR_data["USLA"]
#     for ticker in USLA_ticker:
#         USLA[ticker]['hold_qty'] = USLA_qty[ticker]  # 현재 보유량 업데이트
#         USLA[ticker]['current_price'] = USLA_price[ticker] if ticker in USLA_price else KIS.get_US_current_price(ticker), # 해당 티커의 현재가
#         if USLA_price[ticker] <= 0:
#             message.append(f"⚠️ {ticker} 가격 조회 실패 - 거래 스킵")
#             USLA[ticker]['target_qty'] = USLA_qty[ticker]  # ← 현재 수량 유지 (핵심!)
#             USLA[ticker]['target_balance'] = 0
#             USLA[ticker]['buy_qty'] = 0
#             USLA[ticker]['sell_qty'] = 0
#             continue

#         USLA_target_qty = int((USLA[ticker]['target_weight'] * Total_balance) / USLA[ticker]['current_price'])
#         USLA_target_balance = USLA[ticker]['target_weight'] * Total_balance
#         USLA[ticker]['target_balance'] = USLA_target_balance  # 목표투자금 업데이트
#         USLA[ticker]['target_qty'] = USLA_target_qty  # 목표수량 업데이트
#         USLA[ticker]['buy_qty'] = USLA_target_qty - USLA_qty[ticker] if USLA_target_qty > USLA_qty[ticker] else 0  # 매수 수량 업데이트
#         USLA[ticker]['sell_qty'] = USLA_qty[ticker] - USLA_target_qty if USLA_target_qty < USLA_qty[ticker] else 0  # 매도 수량 업데이트

#     HAA = TR_data["HAA"]
#     for ticker in HAA_ticker:
#         # TIP은 건너뛰기
#         if ticker == 'TIP':
#             continue
#         HAA[ticker]['hold_qty'] = HAA_qty[ticker]  # 현재 보유량 업데이트
#         HAA[ticker]['current_price'] = HAA_price[ticker] if ticker in HAA_price else KIS.get_US_current_price(ticker), # 해당 티커의 현재가
#         if HAA_price[ticker] <= 0:
#             HAA_target_qty = 0
#             message.append(f"⚠️ {ticker} 가격 조회 실패 - 거래 스킵")
#             HAA[ticker]['target_qty'] = HAA_qty[ticker]  # ← 현재 수량 유지 (핵심!)
#             HAA[ticker]['target_balance'] = 0
#             HAA[ticker]['buy_qty'] = 0
#             HAA[ticker]['sell_qty'] = 0
#             continue

#         HAA_target_qty = int((HAA[ticker]['target_weight'] * Total_balance) / HAA[ticker]['current_price'])
#         HAA_target_balance = HAA[ticker]['target_weight'] * Total_balance
#         HAA[ticker]['target_balance'] = HAA_target_balance  # 목표투자금 업데이트
#         HAA[ticker]['target_qty'] = HAA_target_qty  # 목표수량 업데이트
#         HAA[ticker]['buy_qty'] = HAA_target_qty - HAA_qty[ticker] if HAA_target_qty > HAA_qty[ticker] else 0  # 매수 수량 업데이트
#         HAA[ticker]['sell_qty'] = HAA_qty[ticker] - HAA_target_qty if HAA_target_qty < HAA_qty[ticker] else 0  # 매도 수량 업데이트

#     # 회차별 분할 데이터 트레이딩
#     round_split = split_data(order_time['round'])
#     sell_split_USLA = [round_split["sell_splits"], round_split["sell_price_USLA"]]
#     buy_split_USLA = [round_split["buy_splits"], round_split["buy_price_USLA"]]
#     sell_split_HAA = [round_split["sell_splits"], round_split["sell_price_HAA"]]
#     buy_split_HAA = [round_split["buy_splits"], round_split["buy_price_HAA"]]

#     # 주문
#     Sell_order, order_messages = Selling(USLA, HAA, sell_split_USLA, sell_split_HAA, order_time)
#     message.extend(order_messages)
    
#     order_messages = [] # 메세지 초기화
    
#     # 예수금에 맞는 주문수량 구하기
#     FULL_BUYUSD = 0
#     price_error = False
    
#     for ticker in USLA_ticker:
#         if USLA[ticker]['current_price'] <= 0:
#             message.append(f"⚠️ {ticker} 가격 조회 실패 - 매수 스킵")
#             USLA[ticker]['buy_qty'] = 0
#             price_error = True
#             continue
#         invest = USLA[ticker]['buy_qty'] * USLA[ticker]['current_price']
#         FULL_BUYUSD += invest
#     for ticker in HAA_ticker:
#         if ticker == 'TIP':
#             continue
#         if HAA[ticker]['current_price'] <= 0:
#             message.append(f"⚠️ {ticker} 가격 조회 실패 - 매수 스킵")
#             HAA[ticker]['buy_qty'] = 0
#             price_error = True
#             continue
#         invest = HAA[ticker]['buy_qty'] * HAA[ticker]['current_price']
#         FULL_BUYUSD += invest

#     if price_error:
#         message.append("⚠️ 일부 종목 가격 조회 실패로 매수 수량 조정됨")   
        
#     if FULL_BUYUSD > USD:
#         ADJUST_RATE = USD / FULL_BUYUSD
#         for ticker in USLA_ticker:
#             USLA[ticker]['buy_qty'] = int(USLA[ticker]['buy_qty'] * ADJUST_RATE)
#         for ticker in HAA_ticker:
#             HAA[ticker]['buy_qty'] = int(HAA[ticker]['buy_qty'] * ADJUST_RATE)
#     else:
#         pass  # 예수금이 충분할 경우 조정 없음
    
#     # 매수주문
#     Buy_order, buy_order_messages = Buying(USLA, HAA, buy_split_USLA, buy_split_HAA, order_time)
#     message.extend(buy_order_messages)

#     # 다음 order time으로 넘길 Trading data json 데이터 저장
#     saveTR_message = save_TR_data(order_time, Sell_order, Buy_order, USLA, HAA)
#     message.extend(saveTR_message)

#     # 메세지 파일 저장
#     try:
#         with open(USAA_Message_path, 'w', encoding='utf-8') as f:
#             json.dump(message, f, ensure_ascii=False, indent=4)

#     except Exception as e:
#         USAA_Message_backup = "/var/autobot/TR_USAA/USAA_Message.txt"
#         with open(USAA_Message_backup, 'w', encoding='utf-8') as f:
#             json.dump(message, f, ensure_ascii=False, indent=4)

#     sys.exit(0)

# elif order_time['round'] == 25:  # 최종기록
#     # ============================================
#     # 1단계: 지난 라운드 Message 불러오기
#     # ============================================
#     try:
#         with open(USAA_Message_path, 'r', encoding='utf-8') as f:
#             message = json.load(f)
#     except Exception as e:
#         message = []
#         message.append(f"USAA_Message JSON 파일 오류: {e}")
     
#     # ============================================
#     # 2단계: 최종 미체결 주문 취소 + 모여진 메세지 출력
#     # ============================================
#     try:
#         cancel_summary, cancel_messages = KIS.cancel_all_unfilled_orders()
#         message.extend(cancel_messages)
#         if cancel_summary['total'] > 0:
#             message.append(f"미체결 주문 취소: {cancel_summary['success']}/{cancel_summary['total']}")
#     except Exception as e:
#         message.append(f"USAA 주문 취소 오류: {e}")
        
#     send_messages_in_chunks(message, max_length=900)

#     # ============================================
#     # 3단계: 최종 데이터 출력
#     # ============================================
#     message = [] # 메세지 초기화
#     message.append(f"USAA {order_time['date']} 리밸런싱 종료")
    
#     # 계좌잔고 조회
#     USD, USLA_balance, USLA_qty, USLA_price, HAA_balance, HAA_qty, HAA_price, Total_balance = get_balance()

#     USLA_target, USLA_regime, USLA_message = USLA_target_regime()
#     message.append(f"USLA Regime: {USLA_regime}")
#     for i in USLA_target.keys():
#         balance = USLA_qty[i] * USLA_price[i]
#         weight = balance / Total_balance
#         message.append(f"USLA {i} - weight:{weight:.2%}, qty:{USLA_qty[i]}")
#     HAA_target, HAA_regime, HAA_message = HAA_target_regime()
#     message.append(f"HAA Regime: {HAA_regime}")
#     for i in HAA_target.keys():
#         balance = HAA_qty[i] * HAA_price[i]
#         weight = balance / Total_balance
#         message.append(f"HAA {i} - weight:{weight:.2%}, qty:{HAA_qty[i]}")
#     message.append(f"USLA 평가금: {USLA_balance:,.2f} USD")
#     message.append(f"HAA 평가금: {HAA_balance:,.2f} USD")
#     message.append(f"USD 평가금: {USD:,.2f} USD")
#     message.append(f"총 평가금: {Total_balance:,.2f} USD")

#     # 카톡 리밸 종료 결과 보내기
#     send_messages_in_chunks(message, max_length=900)
    
#     # 시스템 종료
#     sys.exit(0)