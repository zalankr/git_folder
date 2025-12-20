import KIS_US
import json
import pandas as pd
import kakao_alert as KA
import riskfolio as rp
import requests
import sys
import calendar
import time
from datetime import date, datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

class HAA(KIS_US.KIS_API): #상속
    def __init__(self, key_file_path, token_file_path, cano, acnt_prdt_cd):
        super().__init__(key_file_path, token_file_path, cano, acnt_prdt_cd)  # 부모 생성자 호출
        self.etf_tickers = ['TIP', 'SPY', 'IWM', 'VEA', 'VWO', 'PDBC', 'VNQ', 'TLT', 'IEF', 'BIL']
        self.all_tickers = self.etf_tickers + ['CASH']
        self.HAA_data_path = "/var/autobot/TR_HAA/HAA_data.json"
        self.HAA_TR_path = "/var/autobot/TR_HAA/HAA_TR.json"
        self.fee = self.SELL_FEE_RATE  # 수수료 0.25%
    
    def calculate_USD_value(self, hold): # USD 환산 잔고 계산 - 수수료 포함
        """USD 환산 잔고 계산"""
        hold_USD_value = 0
        for t in hold.keys():
            if t == "CASH":
                # USLA_CASH도 float로 변환
                hold_USD_value += (hold["CASH"])

            else:
                price = self.get_US_current_price(t)
                # hold[t]를 float로 변환
                qty = hold[t]
                value = price * qty * (1 - self.fee)  # 시장 평가액 (수수료 포함)
                hold_USD_value += value

        return hold_USD_value

    def calculate_target_qty(self, target_weight, target_usd_value): # 보유 $기준 잔고를 바탕으로 target 티커별 목표 quantity 산출 - 수수료 포함
        target_stock_value = 0
        target_qty = {}

        for ticker in target_weight.keys():
            if ticker != "CASH":
                try:
                    price = self.get_US_current_price(ticker)
                    
                    # 타입 체크 추가
                    if isinstance(price, (int, float)) and price > 0:
                        target_qty[ticker] = int(target_usd_value[ticker] / (price*(1 + self.fee))) # 수수료 포함
                        target_stock_value += target_qty[ticker] * price
                        
                    else:
                        KA.SendMessage(f"{ticker}: 가격 정보 없음 (price={price})")
                        target_qty[ticker] = 0
                        
                except Exception as e:
                    KA.SendMessage(f"{ticker}: 수량 계산 오류 - {e}")
                    target_qty[ticker] = 0

        # 남은 현금 = 전체 USD - 주식 매수 예정 금액
        target_qty["CASH"] = sum(target_usd_value.values()) - target_stock_value

        return target_qty

    def make_split_data(self, round): # 시장과 시간대별 티커별 분할횟수와 분할당 가격 산출
        if round in range(1, 12): # Pre-Market
            sell_splits = 4
            sell_price_adjust = [1.0075, 1.0150, 1.0225, 1.0300]
            buy_splits = 2
            buy_price_adjust = [0.9975, 0.9950]

        elif round in range(12, 25): # Regular
            sell_splits = 5
            sell_price_adjust = [1.002, 1.004, 1.006, 1.008, 1.01]
            buy_splits = 5
            buy_price_adjust = [0.998, 0.996, 0.994, 0.992, 0.99]

            if round == 12:
                pass
            elif round == 13:
                sell_price_adjust[0] = 0.99
            elif round == 14:
                sell_splits = 4
                sell_price_adjust = sell_price_adjust[:sell_splits]
                buy_price_adjust[0] = 1.01
            elif round == 15:
                sell_splits = 4
                sell_price_adjust = sell_price_adjust[:sell_splits]
                buy_splits = 4
                buy_price_adjust = buy_price_adjust[:buy_splits]
            elif round == 16:
                sell_splits = 4
                sell_price_adjust = sell_price_adjust[:sell_splits]
                sell_price_adjust[0] = 0.99
                buy_splits = 4
                buy_price_adjust = buy_price_adjust[:buy_splits]
            elif round == 17:
                sell_splits = 3
                sell_price_adjust = sell_price_adjust[:sell_splits]
                buy_splits = 4
                buy_price_adjust = buy_price_adjust[:buy_splits]
                buy_price_adjust[0] = 1.01
            elif round == 18:
                sell_splits = 3
                sell_price_adjust = sell_price_adjust[:sell_splits]
                buy_splits = 3
                buy_price_adjust = buy_price_adjust[:buy_splits]
            elif round == 19:
                sell_splits = 3
                sell_price_adjust = sell_price_adjust[:sell_splits]
                sell_price_adjust[0] = 0.99
                buy_splits = 3
                buy_price_adjust = buy_price_adjust[:buy_splits]
            elif round == 20:
                sell_splits = 2
                sell_price_adjust = sell_price_adjust[:sell_splits]
                buy_splits = 3
                buy_price_adjust = buy_price_adjust[:buy_splits]
                buy_price_adjust[0] = 1.01
            elif round == 21:
                sell_splits = 2
                sell_price_adjust = sell_price_adjust[:sell_splits]
                buy_splits = 2
                buy_price_adjust = buy_price_adjust[:buy_splits]
            elif round == 22:
                sell_splits = 2
                sell_price_adjust = sell_price_adjust[:sell_splits]
                sell_price_adjust[0] = 0.99
                buy_splits = 2
                buy_price_adjust = buy_price_adjust[:buy_splits]
            elif round == 23:
                sell_splits = 1
                sell_price_adjust = sell_price_adjust[:sell_splits]
                sell_price_adjust[0] = 0.99
                buy_splits = 2
                buy_price_adjust = buy_price_adjust[:buy_splits]
                buy_price_adjust[0] = 1.01
            elif round == 24:
                sell_splits = 1
                sell_price_adjust = [0.98]
                buy_splits = 1
                buy_price_adjust = [1.02]
            
        round_split = {
            "sell_splits": sell_splits, 
            "sell_price_adjust": sell_price_adjust, 
            "buy_splits": buy_splits, 
            "buy_price_adjust": buy_price_adjust
        }

        return round_split

    def load_HAA_data(self): # HAA data 불러오기
        """HAA data 불러오기"""   
        try:
            with open(self.HAA_data_path, 'r', encoding='utf-8') as f:
                HAA_data = json.load(f)
            return HAA_data

        except Exception as e:
            KA.SendMessage(f"HAA_data JSON 파일 오류: {e}")
            sys.exit(0)

    def load_HAA_TR(self): # Kis_TR data 불러오기
        """HAA_TR 불러오기"""   
        try:
            with open(self.HAA_TR_path, 'r', encoding='utf-8') as f:
                TR_data = json.load(f)
            return TR_data

        except Exception as e:
            KA.SendMessage(f"HAA_TR JSON 파일 오류: {e}")
            exit()

    def save_HAA_data_json(self, HAA_data):
        """HAA_data를 JSON 파일로 저장"""     
        try:
            with open(self.HAA_data_path, 'w', encoding='utf-8') as f:
                json.dump(HAA_data, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            KA.SendMessage(f"\n HAA_data JSON 파일 저장 오류: {e}")
            return False

    def save_HAA_TR_json(self, TR_data):
        """HAA_TR_data를 JSON 파일로 저장"""     
        try:
            with open(self.HAA_TR_path, 'w', encoding='utf-8') as f:
                json.dump(TR_data, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            KA.SendMessage(f"\n HAA_TR JSON 파일 저장 오류: {e}")
            return False
        
    def calculate_sell_summary(self, Sell_order):
        """
        매도 체결 내역 조회 및 집계 - 수정버전
        
        Parameters:
        - Sell_order: 매도 주문 리스트 (success=True인 주문만 전달받음)
        
        Returns:
        - summary: 매도 체결 요약
        """
        
        # 빈 주문 리스트 처리
        if not Sell_order or len(Sell_order) == 0:
            return {
                'total_orders': 0,
                'filled_orders': 0,
                'partial_filled': 0,
                'unfilled_orders': 0,
                'total_quantity': 0,
                'filled_quantity': 0,
                'gross_amount': 0.0,
                'fee_amount': 0.0,
                'net_amount': 0.0,
                'details': []
            }
        
        Sell_result = []
        
        # 집계 변수 초기화
        total_orders = len(Sell_order)
        filled_orders = 0
        partial_filled = 0
        unfilled_orders = 0
        total_order_qty = 0
        total_filled_qty = 0
        total_gross_amount = 0.0
        total_fee = 0.0
        
        # 각 주문의 체결 내역 조회
        message = []
        for order in Sell_order:
            try:
                # 주문 번호가 없는 경우 스킵 (주문 실패)
                if not order.get('order_number'):
                    message.append(f"매도 체결 확인 스킵: {order.get('ticker')} (주문번호 없음)")
                    continue
                
                # 체결 내역 조회
                execution = self.check_order_execution(
                    order_number=order['order_number'],
                    ticker=order['ticker'],
                    order_type="01"  # 매도
                )

                # execution이 None인 경우 처리 추가
                if execution is None:
                    message.append(f"매도 체결 확인 대기중: {order.get('ticker')} (주문번호: {order.get('order_number')})")
                    unfilled_orders += 1
                    order_qty = order.get('quantity', 0)
                    total_order_qty += order_qty
                    
                    # 미체결 내역 기록
                    detail = {
                        'ticker': order['ticker'],
                        'order_number': order['order_number'],
                        'order_qty': order_qty,
                        'filled_qty': 0,
                        'avg_price': 0.0,
                        'gross_amount': 0.0,
                        'fee': 0.0,
                        'net_amount': 0.0,
                        'status': 'unfilled'
                    }
                    Sell_result.append(detail)
                    continue
                
                # 체결 정보 추출 및 검증
                order_qty = order.get('quantity', 0)
                filled_qty = int(execution.get('qty', 0)) if execution.get('qty') else 0 #'qty'
                avg_price = float(execution.get('price', 0)) if execution.get('price') else 0.0 #'price'
                
                # 주문 수량 누적
                total_order_qty += order_qty
                
                # 체결 수량이 있는 경우
                if filled_qty > 0 and avg_price > 0:
                    # 매도 금액 계산 (수수료 제외)
                    gross_amount = filled_qty * avg_price
                    
                    # 수수료 계산 (매도 수수료 0.09%)
                    fee = gross_amount * self.SELL_FEE_RATE
                    
                    # 순 입금액 (수수료 차감)
                    net_amount = gross_amount - fee
                    
                    # 집계
                    total_filled_qty += filled_qty
                    total_gross_amount += gross_amount
                    total_fee += fee
                    
                    # 체결 상태 판단
                    if filled_qty == order_qty:
                        filled_orders += 1
                        status = 'filled'
                    elif filled_qty < order_qty:
                        partial_filled += 1
                        status = 'partial_filled'
                    else:
                        # 체결 수량 > 주문 수량 (이론적으로 불가능하지만 체크)
                        message.append(f"⚠️ 매도 체결 이상: {order['ticker']} (체결:{filled_qty} > 주문:{order_qty})")
                        filled_orders += 1
                        status = 'overfilled'
                    
                    # 상세 내역 저장
                    detail = {
                        'ticker': order['ticker'],
                        'order_number': order['order_number'],
                        'order_qty': order_qty,
                        'filled_qty': filled_qty,
                        'avg_price': avg_price,
                        'gross_amount': gross_amount,
                        'fee': fee,
                        'net_amount': net_amount,
                        'status': status
                    }
                    Sell_result.append(detail)
                    
                else:
                    # 미체결
                    unfilled_orders += 1
                    
                    # 미체결 내역도 기록
                    detail = {
                        'ticker': order['ticker'],
                        'order_number': order['order_number'],
                        'order_qty': order_qty,
                        'filled_qty': 0,
                        'avg_price': 0.0,
                        'gross_amount': 0.0,
                        'fee': 0.0,
                        'net_amount': 0.0,
                        'status': 'unfilled'
                    }
                    Sell_result.append(detail)
                
                # API 호출 간격
                time.sleep(0.1)
                
            except Exception as e:
                message.append(f"매도 체결 확인 오류 ({order.get('ticker', 'Unknown')}): {e}")
                unfilled_orders += 1
                continue
        
        # 요약 정보 생성
        summary = {
            'total_orders': total_orders,
            'filled_orders': filled_orders,
            'partial_filled': partial_filled,
            'unfilled_orders': unfilled_orders,
            'total_quantity': total_order_qty,
            'filled_quantity': total_filled_qty,
            'gross_amount': total_gross_amount,
            'fee_amount': total_fee,
            'net_amount': total_gross_amount - total_fee,
            'details': Sell_result
        }
        
        # 상세 로깅
        message.append(
            f"📤 매도 체결 요약:\n"
            f"주문: {total_orders}건 (완전체결:{filled_orders}, 부분:{partial_filled}, 미체결:{unfilled_orders})\n"
            f"수량: {total_filled_qty}/{total_order_qty}\n"
            f"매도금액: ${total_gross_amount:.2f}\n"
            f"수수료: ${total_fee:.2f} ({self.SELL_FEE_RATE*100:.2f}%)\n"
            f"순입금: ${summary['net_amount']:.2f}"
        )
        
        # 티커별 집계 (선택적)
        ticker_summary = {}
        for detail in Sell_result:
            ticker = detail['ticker']
            if ticker not in ticker_summary:
                ticker_summary[ticker] = {
                    'total_qty': 0,
                    'filled_qty': 0,
                    'net_amount': 0
                }
            ticker_summary[ticker]['total_qty'] += detail['order_qty']
            ticker_summary[ticker]['filled_qty'] += detail['filled_qty']
            ticker_summary[ticker]['net_amount'] += detail['net_amount']
        
        # 티커별 요약 로깅
        if ticker_summary:
            ticker_msg = "티커별 매도:\n"
            for ticker, data in ticker_summary.items():
                ticker_msg += f"{ticker}: {data['filled_qty']}/{data['total_qty']}주, ${data['net_amount']:.2f}\n"
            message.append(ticker_msg.strip())
        
        return summary, message

    def calculate_buy_summary(self, Buy_order):
        """
        매수 체결 내역 조회 및 집계 - 수정버전
        
        Parameters:
        - Buy_order: 매수 주문 리스트 (success=True인 주문만 전달받음)
        
        Returns:
        - summary: 매수 체결 요약
        """
        
        # 빈 주문 리스트 처리
        if not Buy_order or len(Buy_order) == 0:
            return {
                'total_orders': 0,
                'filled_orders': 0,
                'partial_filled': 0,
                'unfilled_orders': 0,
                'total_quantity': 0,
                'filled_quantity': 0,
                'total_amount': 0.0,
                'details': []
            }
        
        Buy_result = []
        
        # 집계 변수 초기화
        total_orders = len(Buy_order)
        filled_orders = 0
        partial_filled = 0
        unfilled_orders = 0
        total_order_qty = 0
        total_filled_qty = 0
        total_amount_sum = 0.0  # 총 USD 출금액 집계용
        total_fee_sum = 0.0  # 총 수수료 집계용
        
        # 각 주문의 체결 내역 조회
        message = []
        for order in Buy_order:
            try:
                # 주문 번호가 없는 경우 스킵 (주문 실패)
                if not order.get('order_number'):
                    message.append(f"매수 체결 확인 스킵: {order.get('ticker')} (주문번호 없음)")
                    continue
                
                # 체결 내역 조회
                execution = self.check_order_execution(
                    order_number=order['order_number'],
                    ticker=order['ticker'],
                    order_type="02"  # 매수
                )
                
                # execution이 None인 경우 처리 추가
                if execution is None:
                    message.append(f"매수 체결 확인 대기중: {order.get('ticker')} (주문번호: {order.get('order_number')})")
                    unfilled_orders += 1
                    order_qty = order.get('quantity', 0)
                    total_order_qty += order_qty
                    
                    # 미체결 내역 기록
                    detail = {
                        'ticker': order['ticker'],
                        'order_number': order['order_number'],
                        'order_qty': order_qty,
                        'filled_qty': 0,
                        'avg_price': 0.0,
                        'gross_amount': 0.0,  # ✅ 추가
                        'fee': 0.0,  # ✅ 추가
                        'total_amount': 0.0,
                        'status': 'unfilled'
                    }
                    Buy_result.append(detail)
                    continue

                # 체결 정보 추출 및 검증
                order_qty = order.get('quantity', 0)
                filled_qty = int(execution.get('qty', 0)) if execution.get('qty') else 0 # 'qty'
                avg_price = float(execution.get('price', 0)) if execution.get('price') else 0.0 # 'price'
                
                # 주문 수량 누적
                total_order_qty += order_qty
                
                # 체결 수량이 있는 경우
                if filled_qty > 0 and avg_price > 0:
                    # ✅ 매수 금액 계산 (수수료 포함)
                    gross_amount = filled_qty * avg_price  # 체결금액 (KIS API에서 받은 값)
                    fee = gross_amount * self.fee  # 매수 수수료 0.25%
                    total_amount_this = gross_amount + fee  # 실제 USD 출금액
                    
                    # 집계 - ✅ 변수명 수정
                    total_filled_qty += filled_qty
                    total_amount_sum += total_amount_this  # ✅ 수정
                    total_fee_sum += fee  # ✅ 추가
                    
                    # 체결 상태 판단
                    if filled_qty == order_qty:
                        filled_orders += 1
                        status = 'filled'
                    elif filled_qty < order_qty:
                        partial_filled += 1
                        status = 'partial_filled'
                    else:
                        # 체결 수량 > 주문 수량 (이론적으로 불가능하지만 체크)
                        message.append(f"매수 체결 이상: {order['ticker']} (체결:{filled_qty} > 주문:{order_qty})")
                        filled_orders += 1
                        status = 'overfilled'
                    
                    # 상세 내역 저장
                    detail = {
                        'ticker': order['ticker'],
                        'order_number': order['order_number'],
                        'order_qty': order_qty,
                        'filled_qty': filled_qty,
                        'avg_price': avg_price,
                        'gross_amount': gross_amount,  # ✅ 추가
                        'fee': fee,  # ✅ 추가
                        'total_amount': total_amount_this,  # ✅ 수정
                        'status': status
                    }
                    Buy_result.append(detail)
                    
                else:
                    # 미체결
                    unfilled_orders += 1
                    
                    # 미체결 내역도 기록
                    detail = {
                        'ticker': order['ticker'],
                        'order_number': order['order_number'],
                        'order_qty': order_qty,
                        'filled_qty': 0,
                        'avg_price': 0.0,
                        'gross_amount': 0.0,  # ✅ 추가
                        'fee': 0.0,  # ✅ 추가
                        'total_amount': 0.0,
                        'status': 'unfilled'
                    }
                    Buy_result.append(detail)
                
                # API 호출 간격
                time.sleep(0.1)
                
            except Exception as e:
                message.append(f"매수 체결 확인 오류 ({order.get('ticker', 'Unknown')}): {e}")
                unfilled_orders += 1
                continue
        
        # 요약 정보 생성
        summary = {
            'total_orders': total_orders,
            'filled_orders': filled_orders,
            'partial_filled': partial_filled,
            'unfilled_orders': unfilled_orders,
            'total_quantity': total_order_qty,
            'filled_quantity': total_filled_qty,
            'total_amount': total_amount_sum,  # ✅ 수정
            'total_fee': total_fee_sum,  # ✅ 추가
            'details': Buy_result
        }
        
        # 상세 로깅
        message.append(
            f"📥 매수 체결 요약:\n"
            f"주문: {total_orders}건 (완전체결:{filled_orders}, 부분:{partial_filled}, 미체결:{unfilled_orders})\n"
            f"수량: {total_filled_qty}/{total_order_qty}\n"
            f"체결금액: ${total_amount_sum - total_fee_sum:.2f}\n"  # ✅ 추가
            f"수수료: ${total_fee_sum:.2f}\n"  # ✅ 추가
            f"총 출금액: ${total_amount_sum:.2f}"  # ✅ 수정
        )
        
        # 티커별 집계 (선택적)
        ticker_summary = {}
        for detail in Buy_result:
            ticker = detail['ticker']
            if ticker not in ticker_summary:
                ticker_summary[ticker] = {
                    'total_qty': 0,
                    'filled_qty': 0,
                    'gross_amount': 0,  # ✅ 추가
                    'fee': 0,  # ✅ 추가
                    'total_amount': 0
                }
            ticker_summary[ticker]['total_qty'] += detail['order_qty']
            ticker_summary[ticker]['filled_qty'] += detail['filled_qty']
            ticker_summary[ticker]['gross_amount'] += detail['gross_amount']  # ✅ 추가
            ticker_summary[ticker]['fee'] += detail['fee']  # ✅ 추가
            ticker_summary[ticker]['total_amount'] += detail['total_amount']

        # 티커별 요약 로깅
        if ticker_summary:
            ticker_msg = "티커별 매수:\n"
            for ticker, data in ticker_summary.items():
                # ✅ 수정: 수수료 정보 추가
                ticker_msg += f"{ticker}: {data['filled_qty']}/{data['total_qty']}주, ${data['total_amount']:.2f} (수수료: ${data['fee']:.2f})\n"
            message.append(ticker_msg.strip())

        return summary, message

    def get_month_end_date(self, year, month):
        """월말일 반환"""
        last_day = calendar.monthrange(year, month)[1]
        return f'{year}-{month:02d}-{last_day}'

    def get_monthly_prices_kis(self, ticker: str, start_date: str, end_date: str) -> pd.Series:
        """
        KIS API로 월간 가격 데이터 조회
        
        Parameters:
        ticker (str): 종목 코드
        start_date (str): 시작일 (YYYY-MM-DD)
        end_date (str): 종료일 (YYYY-MM-DD)
        
        Returns:
        pd.Series: 날짜를 인덱스로 하는 종가 시리즈
        """
        
        # 거래소 찾기 (수정된 매핑 사용)
        exchange = self.get_exchange_by_ticker(ticker)
        if exchange == "거래소 조회 실패":
            return pd.Series()
        
        # 거래소 코드
        if exchange == "NASD": exchange = "NAS"
        if exchange == "AMEX": exchange = "AMS"
        if exchange == "NYSE": exchange = "NYS"
        
        # 날짜 형식 변환 (YYYYMMDD)
        end_date_formatted = end_date.replace('-', '')
        
        # KIS API 호출
        url = f"{self.url_base}/uapi/overseas-price/v1/quotations/dailyprice"
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
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

    def HAA_momentum(self):
        """HAA 모멘텀 점수 계산 (KIS API 사용)"""
        Aggresive_ETF = ['SPY', 'IWM', 'VEA', 'VWO', 'PDBC', 'VNQ', 'TLT', 'IEF']
        Defensive_ETF = ['IEF', 'BIL']
        Regime_ETF = 'TIP'
        
        # 결과값 초기화 실패 시'CASH' 100%로 대기
        result = {
            'target_weight': {'CASH': 1.0},
            'regime_score': -1
        }

        try:
            today = date.today()
            target_month = today.month
            target_year = today.year

            # 13개월 데이터 필요 (현재 + 12개월)
            start_year = target_year - 2
            prev_month = target_month - 1 if target_month > 1 else 12
            prev_year = target_year if target_month > 1 else target_year - 1
            
            start_date = f'{start_year}-{target_month:02d}-01'
            end_date = self.get_month_end_date(prev_year, prev_month)
            
            # 각 ETF의 월간 가격 데이터 수집
            price_data = {}
            
            for ticker in self.etf_tickers:
                try:
                    # KIS API로 월간 데이터 조회
                    prices = self.get_monthly_prices_kis(ticker, start_date, end_date)
                    price_data[ticker] = prices
                    time.sleep(0.1)  # API 호출 간격
                    
                except Exception as e:
                    KA.SendMessage(f"HAA {ticker} 월간 데이터 조회 오류: {e}")
                    continue
            
            if not price_data:
                KA.SendMessage("HAA 경고: 모멘텀 계산을 위한 데이터를 가져올 수 없습니다.")
                return result
            
            # DataFrame으로 변환
            price_df = pd.DataFrame(price_data)
            
            if len(price_df) < 13:
                KA.SendMessage("HAA 경고: 모멘텀 계산을 위한 데이터가 충분하지 않습니다.")
                return result
                
            momentum_scores = []
            messages = []
            
            for ticker in self.etf_tickers:
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
                return result
            
            # Regime구하기
            regime = momentum_scores['TIP']
            if regime is None:
                KA.SendMessage(f"HAA 경고: {Regime_ETF} 모멘텀 데이터를 찾을 수 없습니다.")
                return result
            else:
                messages.append(f"HAA: {Regime_ETF} 모멘텀 = {regime:.2f}")

            # 데이터프레임 만들기
            momentum_df = pd.DataFrame(momentum_scores)
            if momentum_df is None:
                KA.SendMessage(f"HAA 경고: momentum_df를 찾을 수 없습니다.")
                return result
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
                    return result
                else:
                    top_tickers = momentum_df.head(4)['ticker'].tolist()
                    
                    # 포트폴리오 ticker와 weights를 allocation dictionary에 기입
                    weights = 0.2425 # 97%의 25%씩 할당
                    target_weight = {ticker: weights for ticker in top_tickers}
                    target_weight['CASH'] = 0.03  # 3% 현금 보유

                    result = {
                        'target_weight': target_weight,
                        'regime_score': regime
                    }
                    for ticker, weight in target_weight.items():
                        messages.append(f"{ticker}: {weight:.2%}")

                    KA.SendMessage("\n".join(messages))
                    return result

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
                    return result
                else:
                    top_tickers = momentum_df.head(1)['ticker'].tolist()
                    
                    # 포트폴리오 ticker와 weights를 allocation dictionary에 기입
                    if top_tickers == ['IEF']:
                        target_weight['IEF'] = 0.97  # 97%
                        target_weight['CASH'] = 0.03  # 3% 현금 보유

                    elif top_tickers == ['BIL']:
                        target_weight['CASH'] = 1.0  # 100% 현금 보유

                    result = {
                        'target_weight': target_weight, 
                        'regime_score': regime
                    }

                    for ticker, weight in target_weight.items():
                        messages.append(f"{ticker}: {weight:.2%}")

                    KA.SendMessage("\n".join(messages))
                    return result

        except Exception as e:
            KA.SendMessage(f"HAA_momentum 전체 오류: {e}")
            return result
 
    def get_daily_prices_kis(self, tickers: list, days: int = 90) -> pd.DataFrame:
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
                exchange = self.get_exchange_by_ticker(ticker)
                
                url = f"{self.url_base}/uapi/overseas-price/v1/quotations/dailyprice"
                headers = {
                    "Content-Type": "application/json",
                    "authorization": f"Bearer {self.access_token}",
                    "appKey": self.app_key,
                    "appSecret": self.app_secret,
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
                
                time.sleep(0.1)
                
            except Exception as e:
                KA.SendMessage(f"USLA {ticker} 일간 데이터 조회 오류: {e}")
                continue
        
        if not price_data:
            raise ValueError("일간 가격 데이터를 가져올 수 없습니다.")
        
        return pd.DataFrame(price_data).sort_index(ascending=True)
    
    def get_prices(self):
        """현재 가격 조회 (KIS API 사용)"""
        try:
            prices = {}            
            for ticker in self.etf_tickers:
                try:   
                    # KIS API로 현재가 조회
                    price = self.get_US_current_price(ticker)
                    
                    # 가격이 float 타입인지 확인
                    if isinstance(price, float) and price > 0:
                        prices[ticker] = price
                    else:
                        KA.SendMessage(f"USLA {ticker} 가격 조회 실패")
                        prices[ticker] = 100.0
                    
                    time.sleep(0.1)  # API 호출 간격
                    
                except Exception as e:
                    KA.SendMessage(f"USLA {ticker} 가격 조회 오류: {e}")
                    prices[ticker] = 100.0
            
            prices['CASH'] = 1.0
            return prices
            
        except Exception as e:
            KA.SendMessage(f"USLA 가격 조회 전체 오류: {e}")
            return {ticker: 100.0 for ticker in self.all_tickers}
        
    def check_mode(self, HAA_data):
        exLev_mode = HAA_data['Lev_mode']
        exLev_month = HAA_data['Lev_month']
        exHAA_weight = HAA_data['HAA_weight']
        exSPXL_weight = HAA_data['SPXL_weight']
        exCASH_weight = HAA_data['CASH_weight']

        spy_analysis = self.get_spy_60month_analysis()

        ath_60to1months = spy_analysis['ath_60to1months'] # 60개월~1개월전 전고가
        high_1month = spy_analysis['high_1month'] # 최근 1개월 최고가
        current_price = spy_analysis['current_price'] # 현재가
        high_1month_percentage = spy_analysis['high_1month_percentage'] # 전고가 대비 1개월 최고가 비율(%)
        current_percentage = spy_analysis['current_percentage'] # 전고가 대비 현재가 비율(%)

###############################################################
        if exLev_mode == "HAA":
            if percentage_from_ath >= 75:
                return {
                    "Lev_mode": "HAA",
                    "Lev_month": "NA",
                    "exHAA_weight": exHAA_weight,
                    "exSPXL_weight": exSPXL_weight,
                    "exCASH_weight": exCASH_weight,
                    "HAA_weight": 0.980,
                    "SPXL_weight": 0.000,
                    "CASH_weight": 0.020
                }
            
            else:
                return {
                    "Lev_mode": "Lev_1",
                    "Lev_month": 1,
                    "exHAA_weight": exHAA_weight,
                    "exSPXL_weight": exSPXL_weight,
                    "exCASH_weight": exCASH_weight,
                    "HAA_weight": 0.939,
                    "SPXL_weight": 0.041,
                    "CASH_weight": 0.020
                }
        




