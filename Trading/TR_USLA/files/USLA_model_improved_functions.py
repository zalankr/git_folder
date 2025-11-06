# USLA_model.py 개선 함수들
# 기존 USLA_model.py의 calculate_sell_summary와 calculate_buy_summary 함수를 교체

import time
import kakao_alert as KA

def calculate_sell_summary(self, Sell_order):
    """
    매도 체결 내역 조회 및 집계 - 개선버전
    
    Parameters:
    - Sell_order: 매도 주문 리스트 (success=True인 주문만 전달받음)
    
    Returns:
    - summary: 매도 체결 요약
        {
            'total_orders': 총 주문 수,
            'filled_orders': 체결된 주문 수,
            'partial_filled': 부분 체결 주문 수,
            'unfilled_orders': 미체결 주문 수,
            'total_quantity': 총 주문 수량,
            'filled_quantity': 총 체결 수량,
            'gross_amount': 총 매도 금액 (수수료 제외),
            'fee_amount': 총 수수료,
            'net_amount': 순 입금액 (수수료 차감),
            'details': 상세 체결 내역 리스트
        }
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
            
            # 체결 정보 추출 및 검증
            order_qty = order.get('quantity', 0)
            filled_qty = execution.get('filled_quantity', 0)
            avg_price = execution.get('average_price', 0.0)
            
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
    매수 체결 내역 조회 및 집계 - 개선버전
    
    Parameters:
    - Buy_order: 매수 주문 리스트 (success=True인 주문만 전달받음)
    
    Returns:
    - summary: 매수 체결 요약
        {
            'total_orders': 총 주문 수,
            'filled_orders': 체결된 주문 수,
            'partial_filled': 부분 체결 주문 수,
            'unfilled_orders': 미체결 주문 수,
            'total_quantity': 총 주문 수량,
            'filled_quantity': 총 체결 수량,
            'total_amount': 총 매수 금액 (수수료 포함),
            'details': 상세 체결 내역 리스트
        }
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
            
            # 체결 정보 추출 및 검증
            order_qty = order.get('quantity', 0)
            filled_qty = execution.get('filled_quantity', 0)
            avg_price = execution.get('average_price', 0.0)
            
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
                    KA.SendMessage(f"⚠️ 매수 체결 이상: {order['ticker']} (체결:{filled_qty} > 주문:{order_qty})")
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


# ============================================
# 사용 예시
# ============================================

"""
USLA_model.py 파일에서 기존 calculate_sell_summary와 calculate_buy_summary 함수를
위의 개선된 함수로 교체하세요.

사용 방법:
1. USLA_model.py 백업
2. 기존 함수 삭제
3. 위의 개선 함수 복사/붙여넣기
4. 테스트 실행

주요 개선 사항:
- 성공/실패/부분체결 상태를 명확히 구분
- 티커별 집계 기능 추가
- 상세한 로깅으로 디버깅 용이
- 예외 처리 강화
- 수수료 계산 명확화 (매도: 별도 계산, 매수: 체결가에 포함)
"""
