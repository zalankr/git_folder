import yfinance as yf
import kakao_alert as KA
import KIS_US
import json
import sys
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
    
    def get_USLA_current_prices(self): # run_strategy함수에 종속되어 USLA model의 현재 가격 조회
        """현재 가격 조회"""
        try:
            prices = {}
            for ticker in self.etf_tickers:
                data = yf.download(ticker, period='1d', interval='1d', progress=False, multi_level_index=False)['Close']
                prices[ticker] = float(data.iloc[-1])
            prices['CASH'] = 1.0
            return prices
        except Exception as e:
            print(f"가격 조회 오류: {e}")
            return {ticker: 100.0 for ticker in self.all_tickers}  # 기본값
    
    def calculate_USD_value(self, hold): # make_trading_data함수에 종속되어 USD 환산 잔고 계산
        """USD 환산 잔고 계산"""
        hold_USD_value = 0
        for t in hold.keys():
            if t == "CASH":
                # USLA_CASH도 float로 변환
                hold_USD_value += float(hold["CASH"])
            else:
                price = self.get_US_current_price(ticker=t)
                # hold[t]를 float로 변환
                qty = float(hold[t])
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

    def make_split_data(self, market, round): # make_trading_data함수에 종속되어 시장과 시간대별 티커별 분할횟수와 분할당 가격 산출
        if market == "Pre-market":
            order_type = "order_daytime_US"
            sell_splits = 4
            sell_price_adjust = [1.015, 1.03, 1.045, 1.06]
            buy_splits = 2
            buy_price_adjust = [0.995, 0.99]

        elif market == "Regular":
            order_type = "order_US"
            sell_splits = 5
            sell_price_adjust = [1.0025, 1.005, 1.0075, 1.01, 1.0125]
            buy_splits = 5
            buy_price_adjust = [0.9975, 0.995, 0.9925, 0.99, 0.9875]

            if round == 1:
                pass
            elif round == 2:
                sell_price_adjust[0] = 0.99
            elif round == 3:
                sell_splits = 4
                sell_price_adjust = sell_price_adjust[:sell_splits]
                buy_price_adjust[0] = 1.01
            elif round == 4:
                sell_splits = 4
                sell_price_adjust = sell_price_adjust[:sell_splits]
                buy_splits = 4
                buy_price_adjust = buy_price_adjust[:buy_splits]
            elif round == 5:
                sell_splits = 4
                sell_price_adjust = sell_price_adjust[:sell_splits]
                sell_price_adjust[0] = 0.99
                buy_splits = 4
                buy_price_adjust = buy_price_adjust[:buy_splits]
            elif round == 6:
                sell_splits = 3
                sell_price_adjust = sell_price_adjust[:sell_splits]
                buy_splits = 4
                buy_price_adjust = buy_price_adjust[:buy_splits]
                buy_price_adjust[0] = 1.01
            elif round == 7:
                sell_splits = 3
                sell_price_adjust = sell_price_adjust[:sell_splits]
                buy_splits = 3
                buy_price_adjust = buy_price_adjust[:buy_splits]
            elif round == 8:
                sell_splits = 3
                sell_price_adjust = sell_price_adjust[:sell_splits]
                sell_price_adjust[0] = 0.99
                buy_splits = 3
                buy_price_adjust = buy_price_adjust[:buy_splits]
            elif round == 9:
                sell_splits = 2
                sell_price_adjust = sell_price_adjust[:sell_splits]
                buy_splits = 3
                buy_price_adjust = buy_price_adjust[:buy_splits]
                buy_price_adjust[0] = 1.01
            elif round == 10:
                sell_splits = 2
                sell_price_adjust = sell_price_adjust[:sell_splits]
                buy_splits = 2
                buy_price_adjust = buy_price_adjust[:buy_splits]
            elif round == 11:
                sell_splits = 2
                sell_price_adjust = sell_price_adjust[:sell_splits]
                sell_price_adjust[0] = 0.99
                buy_splits = 2
                buy_price_adjust = buy_price_adjust[:buy_splits]
            elif round == 12:
                sell_splits = 1
                sell_price_adjust = sell_price_adjust[:sell_splits]
                sell_price_adjust[0] = 0.97
                buy_splits = 2
                buy_price_adjust = buy_price_adjust[:buy_splits]
                buy_price_adjust[0] = 1.01
            elif round == 13:
                sell_splits = 1
                sell_price_adjust = [0.97]
                buy_splits = 1
                buy_price_adjust = [1.03]
            
        round_split = {
            "order_type": order_type,
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
        """SLA_TR 불러오기"""   
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
        """매도 체결 내역 조회 및 집계 (종목별 집계 포함)"""
        
        Sell_result = []
        
        for order in Sell_order:
            execution = self.check_order_execution(
                order_number=order['order_number'],
                ticker=order['ticker'],
                order_type="01"
            )
            Sell_result.append(execution)
        
        # 체결된 주문만 필터링
        filled = [r for r in Sell_result if r and r.get('success')]
        
        if not filled:
            return {
                'success': False,
                'count': 0,
                'total_quantity': 0,
                'total_amount': 0.0,
                'total_fee': 0.0,  # 추가
                'net_amount': 0.0,  # 추가 (실제 입금액)
                'avg_price': 0.0,
                'by_ticker': {},
                'details': []
            }
        
        # 전체 집계
        total_quantity = sum(int(r.get('qty', 0)) for r in filled)
        total_amount = sum(float(r.get('amount', 0)) for r in filled)
        
        # 수수료 계산
        total_fee = total_amount * self.SELL_FEE_RATE
        
        # 실제 입금액 (체결금액 - 수수료)
        net_amount = total_amount - total_fee
        
        avg_price = total_amount / total_quantity if total_quantity > 0 else 0
        
        # 종목별 집계
        from collections import defaultdict
        ticker_summary = defaultdict(lambda: {'qty': 0, 'amount': 0, 'orders': []})
        
        for r in filled:
            ticker = r.get('name', '알 수 없음')
            qty = int(r.get('qty', 0))
            amount = float(r.get('amount', 0))
            price = float(r.get('price', 0))
            
            ticker_summary[ticker]['qty'] += qty
            ticker_summary[ticker]['amount'] += amount
            ticker_summary[ticker]['orders'].append({
                'qty': qty,
                'price': price,
                'amount': amount
            })
        
        # 종목별 평균가 계산
        by_ticker = {}
        for ticker, data in ticker_summary.items():
            qty = data['qty']
            amount = data['amount']
            avg = amount / qty if qty > 0 else 0
            
            # 종목별 수수료 및 실제 입금액 계산
            fee = amount * self.SELL_FEE_RATE
            net = amount - fee
            
            by_ticker[ticker] = {
                'quantity': qty,
                'amount': amount,  # 체결금액
                'fee': fee,  # 수수료
                'net_amount': net,  # 실제 입금액
                'avg_price': avg,
                'order_count': len(data['orders']),
                'orders': data['orders']
            }
        
        return {
            'success': True,
            'count': len(filled),
            'total_quantity': total_quantity,
            'total_amount': total_amount,  # 체결금액
            'total_fee': total_fee,  # 전체 수수료
            'net_amount': net_amount,  # 실제 입금액 ← 이것이 예수금!
            'avg_price': avg_price,
            'by_ticker': by_ticker,
            'details': filled
        }

    def calculate_buy_summary(self, Buy_order):
        """매수 체결 내역 조회 및 집계 (종목별 집계 포함)"""
        
        Buy_result = []
        
        for order in Buy_order:
            execution = self.check_order_execution(
                order_number=order['order_number'],
                ticker=order['ticker'],
                order_type="02"  # 매수는 "02"
            )
            Buy_result.append(execution)
        
        # 체결된 주문만 필터링
        filled = [r for r in Buy_result if r and r.get('success')]
        
        if not filled:
            return {
                'success': False,
                'count': 0,
                'total_quantity': 0,
                'total_amount': 0.0,
                'avg_price': 0.0,
                'by_ticker': {},
                'details': []
            }
        
        # 전체 집계
        total_quantity = sum(int(r.get('qty', 0)) for r in filled)
        total_amount = sum(float(r.get('amount', 0)) for r in filled)
        
        # 실제 사용 금액 (체결금액 + 수수료)
        avg_price = total_amount / total_quantity if total_quantity > 0 else 0
        
        # 종목별 집계
        from collections import defaultdict
        ticker_summary = defaultdict(lambda: {'qty': 0, 'amount': 0, 'orders': []})
        
        for r in filled:
            ticker = r.get('name', '알 수 없음')
            qty = int(r.get('qty', 0))
            amount = float(r.get('amount', 0))
            price = float(r.get('price', 0))
            
            ticker_summary[ticker]['qty'] += qty
            ticker_summary[ticker]['amount'] += amount
            ticker_summary[ticker]['orders'].append({
                'qty': qty,
                'price': price,
                'amount': amount
            })
        
        # 종목별 평균가 계산
        by_ticker = {}
        for ticker, data in ticker_summary.items():
            qty = data['qty']
            amount = data['amount']
            avg = amount / qty if qty > 0 else 0
            
            by_ticker[ticker] = {
                'quantity': qty,
                'amount': amount,  # 체결금액
                'avg_price': avg,
                'order_count': len(data['orders']),
                'orders': data['orders']
            }
        
        return {
            'success': True,
            'count': len(filled),
            'total_quantity': total_quantity,
            'total_amount': total_amount,
            'avg_price': avg_price,
            'by_ticker': by_ticker,
            'details': filled
        }
