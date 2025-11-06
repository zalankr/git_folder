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

class USLA_Model(KIS_US.KIS_API): #상속
    def __init__(self, key_file_path, token_file_path, cano, acnt_prdt_cd):
        super().__init__(key_file_path, token_file_path, cano, acnt_prdt_cd)  # 부모 생성자 호출
        self.etf_tickers = ['UPRO', 'TQQQ', 'EDC', 'TMF', 'TMV']
        self.all_tickers = self.etf_tickers + ['CASH']
        self.USLA_data_path = "/var/autobot/TR_USLA/USLA_data.json"
        self.USLA_TR_path = "/var/autobot/TR_USLA/USLA_TR.json"
        self.fee = self.SELL_FEE_RATE  # 매도 수수료 0.09%
    
    def calculate_USD_value(self, hold): # make_trading_data함수에 종속되어 USD 환산 잔고 계산
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
                value = price * qty  # 시장 평가액 (수수료 제외)
                hold_USD_value += value

        return hold_USD_value

    def calculate_target_qty(self, target, target_usd_value): # make_trading_data함수에 종속되어 target 티커별 목표 quantity 산출
        # 보유 $기준 잔고를 바탕으로 목표 비중에 맞춰 ticker별 quantity 계산
        target_qty = {}
        target_stock_value = 0
        for ticker in target.keys():
            if ticker != "CASH":
                try:
                    price = self.get_US_current_price(ticker)
                    
                    # 타입 체크 추가
                    if isinstance(price, (int, float)) and price > 0:
                        target_qty[ticker] = int(target_usd_value[ticker] / price)  
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

    def make_split_data(self, round): # make_trading_data함수에 종속되어 시장과 시간대별 티커별 분할횟수와 분할당 가격 산출
        if round in range(1, 12): # Pre-Market
            sell_splits = 4
            sell_price_adjust = [1.015, 1.03, 1.045, 1.06]
            buy_splits = 2
            buy_price_adjust = [0.995, 0.99]

        elif round in range(12, 25): # Regular
            sell_splits = 5
            sell_price_adjust = [1.0025, 1.005, 1.0075, 1.01, 1.0125]
            buy_splits = 5
            buy_price_adjust = [0.9975, 0.995, 0.9925, 0.99, 0.9875]

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
                sell_price_adjust[0] = 0.98
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

    def load_USLA_data(self): # make_trading_data함수에 종속되어 USLA data 불러오기
        """USLA data 불러오기"""   
        try:
            with open(self.USLA_data_path, 'r', encoding='utf-8') as f:
                USLA_data = json.load(f)
            return USLA_data

        except Exception as e:
            KA.SendMessage(f"USLA_data JSON 파일 오류: {e}")
            sys.exit(0)

    def load_USLA_TR(self): # Kis_TR data 불러오기
        """USLA_TR 불러오기"""   
        try:
            with open(self.USLA_TR_path, 'r', encoding='utf-8') as f:
                TR_data = json.load(f)
            return TR_data

        except Exception as e:
            KA.SendMessage(f"USLA_TR JSON 파일 오류: {e}")
            exit()

    def save_USLA_data_json(self, USLA_data):
        """Kis_TR_data를 JSON 파일로 저장"""     
        try:
            with open(self.USLA_data_path, 'w', encoding='utf-8') as f:
                json.dump(USLA_data, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            KA.SendMessage(f"\n USLA_data JSON 파일 저장 오류: {e}")
            return False

    def save_USLA_TR_json(self, TR_data):
        """USLA_TR_data를 JSON 파일로 저장"""     
        try:
            with open(self.USLA_TR_path, 'w', encoding='utf-8') as f:
                json.dump(TR_data, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            KA.SendMessage(f"\n USLA_TR JSON 파일 저장 오류: {e}")
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
        for order in Sell_order:
            try:
                # 주문 번호가 없는 경우 스킵 (주문 실패)
                if not order.get('order_number'):
                    KA.SendMessage(f"매도 체결 확인 스킵: {order.get('ticker')} (주문번호 없음)")
                    continue
                
                # 체결 내역 조회
                execution = self.check_order_execution(
                    order_number=order['order_number'],
                    ticker=order['ticker'],
                    order_type="01"  # 매도
                )
                
                # ⭐ execution이 None인 경우 처리
                if execution is None:
                    KA.SendMessage(f"매도 체결 확인 실패: {order.get('ticker')} (주문번호: {order.get('order_number')})")
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
                
                # ⭐ 키 이름 수정: execution 딕셔너리의 실제 키 사용
                order_qty = order.get('quantity', 0)
                filled_qty = int(execution.get('qty', 0)) if execution.get('qty') else 0  # 'qty' 사용
                avg_price = float(execution.get('price', 0)) if execution.get('price') else 0.0  # 'price' 사용
                
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
                        KA.SendMessage(f"⚠️ 매도 체결 이상: {order['ticker']} (체결:{filled_qty} > 주문:{order_qty})")
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
                KA.SendMessage(f"매도 체결 확인 오류 ({order.get('ticker', 'Unknown')}): {e}")
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
        KA.SendMessage(
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
            KA.SendMessage(ticker_msg.strip())
        
        return summary

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
        total_amount = 0.0  # 매수는 체결가에 이미 수수료 포함됨
        
        # 각 주문의 체결 내역 조회
        for order in Buy_order:
            try:
                # 주문 번호가 없는 경우 스킵 (주문 실패)
                if not order.get('order_number'):
                    KA.SendMessage(f"매수 체결 확인 스킵: {order.get('ticker')} (주문번호 없음)")
                    continue
                
                # 체결 내역 조회
                execution = self.check_order_execution(
                    order_number=order['order_number'],
                    ticker=order['ticker'],
                    order_type="02"  # 매수
                )
                
                # ⭐ execution이 None인 경우 처리
                if execution is None:
                    KA.SendMessage(f"매수 체결 확인 실패: {order.get('ticker')} (주문번호: {order.get('order_number')})")
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
                        'total_amount': 0.0,
                        'status': 'unfilled'
                    }
                    Buy_result.append(detail)
                    continue
                
                # ⭐ 키 이름 수정: execution 딕셔너리의 실제 키 사용
                order_qty = order.get('quantity', 0)
                filled_qty = int(execution.get('qty', 0)) if execution.get('qty') else 0  # 'qty' 사용
                avg_price = float(execution.get('price', 0)) if execution.get('price') else 0.0  # 'price' 사용
                
                # 주문 수량 누적
                total_order_qty += order_qty
                
                # 체결 수량이 있는 경우
                if filled_qty > 0 and avg_price > 0:
                    # 매수 금액 계산
                    # ⭐ 중요: KIS API는 매수 체결가에 이미 수수료가 포함되어 있음
                    # 따라서 별도 수수료 계산 불필요
                    amount = filled_qty * avg_price
                    
                    # 집계
                    total_filled_qty += filled_qty
                    total_amount += amount
                    
                    # 체결 상태 판단
                    if filled_qty == order_qty:
                        filled_orders += 1
                        status = 'filled'
                    elif filled_qty < order_qty:
                        partial_filled += 1
                        status = 'partial_filled'
                    else:
                        # 체결 수량 > 주문 수량 (이론적으로 불가능하지만 체크)
                        KA.SendMessage(f"매수 체결 이상: {order['ticker']} (체결:{filled_qty} > 주문:{order_qty})")
                        filled_orders += 1
                        status = 'overfilled'
                    
                    # 상세 내역 저장
                    detail = {
                        'ticker': order['ticker'],
                        'order_number': order['order_number'],
                        'order_qty': order_qty,
                        'filled_qty': filled_qty,
                        'avg_price': avg_price,
                        'total_amount': amount,
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
                        'total_amount': 0.0,
                        'status': 'unfilled'
                    }
                    Buy_result.append(detail)
                
                # API 호출 간격
                time.sleep(0.1)
                
            except Exception as e:
                KA.SendMessage(f"매수 체결 확인 오류 ({order.get('ticker', 'Unknown')}): {e}")
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
            'total_amount': total_amount,
            'details': Buy_result
        }
        
        # 상세 로깅
        KA.SendMessage(
            f"📥 매수 체결 요약:\n"
            f"주문: {total_orders}건 (완전체결:{filled_orders}, 부분:{partial_filled}, 미체결:{unfilled_orders})\n"
            f"수량: {total_filled_qty}/{total_order_qty}\n"
            f"매수금액: ${total_amount:.2f} (수수료 포함)"
        )
        
        # 티커별 집계 (선택적)
        ticker_summary = {}
        for detail in Buy_result:
            ticker = detail['ticker']
            if ticker not in ticker_summary:
                ticker_summary[ticker] = {
                    'total_qty': 0,
                    'filled_qty': 0,
                    'total_amount': 0
                }
            ticker_summary[ticker]['total_qty'] += detail['order_qty']
            ticker_summary[ticker]['filled_qty'] += detail['filled_qty']
            ticker_summary[ticker]['total_amount'] += detail['total_amount']
        
        # 티커별 요약 로깅
        if ticker_summary:
            ticker_msg = "티커별 매수:\n"
            for ticker, data in ticker_summary.items():
                ticker_msg += f"{ticker}: {data['filled_qty']}/{data['total_qty']}주, ${data['total_amount']:.2f}\n"
            KA.SendMessage(ticker_msg.strip())
        
        return summary

    # 여기서부터는 나머지 함수들... (target_ticker_weight 등)
    # 파일이 너무 길어서 생략하지만 나머지는 그대로 유지
