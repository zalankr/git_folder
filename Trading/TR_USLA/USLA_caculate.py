from datetime import date, datetime, timedelta
import kakao_alert as KA
import calendar
import time
import pandas as pd
import riskfolio as rp
import requests
import json
from KIS_US import KIS_API

etf_tickers = ['UPRO', 'TQQQ', 'EDC', 'TMF', 'TMV']
all_tickers = etf_tickers + ['CASH']

# KIS API 인스턴스 초기화 (전역 변수)
kis_api = None

# NYSE Arca ETF 거래소 매핑 (NYS 코드 사용)
ARCA_ETFS = {
    'UPRO': 'NYS',  # NYSE Arca
    'TMF': 'NYS',   # NYSE Arca
    'TMV': 'NYS',   # NYSE Arca
    'EDC': 'NYS',   # NYSE Arca
    'TQQQ': 'NAS',  # NASDAQ
    'AGG': 'NYS'    # NYSE Arca
}

def initialize_kis_api(key_file_path: str, token_file_path: str, cano: str, acnt_prdt_cd: str):
    """KIS API 초기화 함수 - 메인 코드에서 한 번만 호출"""
    global kis_api
    kis_api = KIS_API(
        key_file_path=key_file_path,
        token_file_path=token_file_path,
        cano=cano,
        acnt_prdt_cd=acnt_prdt_cd
    )
    # KIS_US.py의 EXCHANGE_MAP 업데이트
    kis_api.EXCHANGE_MAP.update(ARCA_ETFS)
    return kis_api

def get_month_end_date(year, month):
    """월말일 반환"""
    last_day = calendar.monthrange(year, month)[1]
    return f'{year}-{month:02d}-{last_day}'

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
    global kis_api
    
    if kis_api is None:
        raise ValueError("KIS API가 초기화되지 않았습니다. initialize_kis_api()를 먼저 호출하세요.")
    
    # 거래소 찾기 (수정된 매핑 사용)
    exchange = ARCA_ETFS.get(ticker) or kis_api.get_US_exchange(ticker)
    if exchange is None:
        raise ValueError(f"{ticker}의 거래소를 찾을 수 없습니다.")
    
    # 날짜 형식 변환 (YYYYMMDD)
    end_date_formatted = end_date.replace('-', '')
    
    # KIS API 호출
    url = f"{kis_api.url_base}/uapi/overseas-price/v1/quotations/dailyprice"
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {kis_api.access_token}",
        "appKey": kis_api.app_key,
        "appSecret": kis_api.app_secret,
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
                    raise ValueError(f"{ticker} 데이터가 비어있습니다.")
                
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
                raise ValueError(f"{ticker} API 응답 오류: {data.get('msg1', 'Unknown error')}")
        else:
            raise ValueError(f"{ticker} API 호출 실패: HTTP {response.status_code}")
            
    except Exception as e:
        raise ValueError(f"{ticker} 월간 가격 조회 오류: {e}")

def calculate_regime():
    """AGG 채권 ETF의 Regime 신호 계산 (KIS API 사용)"""
    global kis_api
    
    try:
        today = date.today()
        # 전월 계산
        target_month = today.month - 1
        target_year = today.year

        # 1월인 경우 전년 12월로 변경
        if target_month == 0:
            target_month = 12
            target_year = target_year - 1

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
        end_date = get_month_end_date(prev_year, prev_month)

        # KIS API로 AGG 월간 데이터 조회
        agg_data = get_monthly_prices_kis('AGG', start_date, end_date)
        time.sleep(0.3)

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

def calculate_momentum():
    """모멘텀 점수 계산 (KIS API 사용)"""
    global kis_api
    
    try:
        today = date.today()
        # 전월 계산
        target_month = today.month - 1
        target_year = today.year

        # 1월인 경우 전년 12월로 변경
        if target_month == 0:
            target_month = 12
            target_year = target_year - 1

        # 13개월 데이터 필요 (현재 + 12개월)
        start_year = target_year - 2
        prev_month = target_month - 1 if target_month > 1 else 12
        prev_year = target_year if target_month > 1 else target_year - 1
        
        start_date = f'{start_year}-{target_month:02d}-01'
        end_date = get_month_end_date(prev_year, prev_month)
        
        # 각 ETF의 월간 가격 데이터 수집
        price_data = {}
        
        for ticker in etf_tickers:
            try:
                # KIS API로 월간 데이터 조회
                prices = get_monthly_prices_kis(ticker, start_date, end_date)
                price_data[ticker] = prices
                time.sleep(0.3)  # API 호출 간격
                
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
        
        for ticker in etf_tickers:
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

def get_daily_prices_kis(tickers: list, days: int = 90) -> pd.DataFrame:
    """
    KIS API로 일간 가격 데이터 조회 (포트폴리오 최적화용)
    
    Parameters:
    tickers (list): 종목 코드 리스트
    days (int): 조회할 일수 (기본 90일)
    
    Returns:
    pd.DataFrame: 날짜를 인덱스로 하는 종가 데이터프레임
    """
    global kis_api
    
    if kis_api is None:
        raise ValueError("KIS API가 초기화되지 않았습니다.")
    
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    end_date_str = end_date.strftime('%Y%m%d')
    
    price_data = {}
    
    for ticker in tickers:
        try:
            # 거래소 찾기 (수정된 매핑 사용)
            exchange = ARCA_ETFS.get(ticker) or kis_api.get_US_exchange(ticker)
            if exchange is None:
                continue
            
            url = f"{kis_api.url_base}/uapi/overseas-price/v1/quotations/dailyprice"
            headers = {
                "Content-Type": "application/json",
                "authorization": f"Bearer {kis_api.access_token}",
                "appKey": kis_api.app_key,
                "appSecret": kis_api.app_secret,
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
            
            time.sleep(0.3)
            
        except Exception as e:
            KA.SendMessage(f"USLA {ticker} 일간 데이터 조회 오류: {e}")
            continue
    
    if not price_data:
        raise ValueError("일간 가격 데이터를 가져올 수 없습니다.")
    
    return pd.DataFrame(price_data).sort_index(ascending=True)

def calculate_portfolio_weights(top_tickers):
    """최소분산 포트폴리오 가중치 계산 (KIS API 사용)"""
    global kis_api
    
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
            'Weight': [0.2, 0.8],
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
            return {ticker: 1.0/len(top_tickers) for ticker in top_tickers}
        
        weight_dict = {}
        for i, ticker in enumerate(top_tickers):
            weight_dict[ticker] = float(weights.iloc[i, 0]) * 0.99
            
        return weight_dict
        
    except Exception as e:
        KA.SendMessage(f"USLA 포트폴리오 최적화 오류: {e}")
        # 동일가중으로 폴백
        equal_weight = 0.99 / len(top_tickers)
        return {ticker: equal_weight for ticker in top_tickers}

def get_prices():
    """현재 가격 조회 (KIS API 사용)"""
    global kis_api
    
    if kis_api is None:
        KA.SendMessage("USLA 경고: KIS API가 초기화되지 않았습니다.")
        return {ticker: 100.0 for ticker in all_tickers}
    
    try:
        prices = {}
        
        for ticker in etf_tickers:
            try:
                # 거래소 찾기 (수정된 매핑 사용)
                exchange = ARCA_ETFS.get(ticker)
                
                # KIS API로 현재가 조회
                price = kis_api.get_US_current_price(ticker, exchange)
                
                # 가격이 float 타입인지 확인
                if isinstance(price, float) and price > 0:
                    prices[ticker] = price
                else:
                    KA.SendMessage(f"USLA {ticker} 가격 조회 실패")
                    prices[ticker] = 100.0
                
                time.sleep(0.2)  # API 호출 간격
                
            except Exception as e:
                KA.SendMessage(f"USLA {ticker} 가격 조회 오류: {e}")
                prices[ticker] = 100.0
        
        prices['CASH'] = 1.0
        return prices
        
    except Exception as e:
        KA.SendMessage(f"USLA 가격 조회 전체 오류: {e}")
        return {ticker: 100.0 for ticker in all_tickers}

def run_strategy(regime, momentum_df):
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
        allocation = {ticker: 0.0 for ticker in etf_tickers}
        allocation['CASH'] = 1.0

    else:
        # 상위 2개 ETF 선택
        if len(momentum_df) < 2:
            KA.SendMessage(f"USLA 경고: 모멘텀 데이터가 2개 미만입니다. CASH로 대기합니다.")
            allocation = {ticker: 0.0 for ticker in etf_tickers}
            allocation['CASH'] = 1.0
        else:
            top_tickers = momentum_df.head(2)['ticker'].tolist()
            
            # 포트폴리오 가중치 계산
            weights = calculate_portfolio_weights(top_tickers)
            
            allocation = {ticker: 0.0 for ticker in etf_tickers}
            allocation.update(weights)
            allocation['CASH'] = 0.01  # 1% 현금 보유
    
    # 4. 현재 가격 조회
    current_prices = get_prices()
    
    # 4. 결과 출력
    message = []
    for ticker in all_tickers:
        if allocation.get(ticker, 0) > 0:
            message.append(f"USLA {ticker}: {allocation[ticker]:.1%} (현재가: ${current_prices[ticker]:.2f})")

    KA.SendMessage("\n".join(message))
    
    return {
        'regime': regime,
        'momentum': momentum_df,
        'allocation': allocation,
        'current_prices': current_prices
    }

def target_ticker_weight():
    """target 티커별 목표 비중 산출"""
    regime = calculate_regime()
    momentum_df = calculate_momentum()
    result = run_strategy(regime, momentum_df)
    
    if result is None:
        KA.SendMessage("USLA 경고: 전략 실행 실패, CASH로 대기합니다.")
        return {'CASH': 1.0}, 0
    
    target = {
        ticker: weight 
        for ticker, weight in result['allocation'].items() 
        if weight >= 0.01
    }
    regime_signal = result['regime']
    return target, regime_signal

# 메인 실행 부분
if __name__ == "__main__":
    # KIS API 초기화 (실제 경로로 수정 필요)
    initialize_kis_api(
        key_file_path="/var/autobot/TR_USLA/kis63721147nkr.txt",
        token_file_path="/var/autobot/TR_USLA/kis63721147_token.json",
        cano="63721147",
        acnt_prdt_cd="01"
    )
    
    result = calculate_regime()
    print(result)