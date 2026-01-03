# KIS_US.py 수정 사항
# order_sell_US와 order_buy_US 함수의 메시지 발송 부분을 수정하세요

def order_sell_US(self, ticker: str, quantity: int, price: float,
                    exchange: Optional[str] = None, ord_dvsn: str = "00") -> Optional[Dict]:
    """
    미국 주식 매도 주문 (Regular Market)
    """
    if exchange is None:
        exchange = self.get_exchange_by_ticker(ticker)
        if exchange == "NAS" or exchange == "BAQ":
            exchange = "NASD"
        elif exchange == "AMS" or exchange == "BAA":
            exchange = "AMEX"
        elif exchange == "NYS" or exchange == "BAY":
            exchange = "NYSE"
        else:
            exchange = None
    
    if exchange is None:
        KA.SendMessage(f"{ticker} 거래소를 찾을 수 없습니다.")
        return None
    
    # 가격을 소수점 2자리로 반올림
    price = round(price, 2)
    
    path = "uapi/overseas-stock/v1/trading/order"
    url = f"{self.url_base}/{path}"

    data = {
        "CANO": self.cano,
        "ACNT_PRDT_CD": self.acnt_prdt_cd,
        "OVRS_EXCG_CD": exchange,
        "PDNO": ticker,
        "ORD_DVSN": ord_dvsn,
        "ORD_QTY": str(quantity),
        "OVRS_ORD_UNPR": f"{price:.2f}",
        "CTAC_TLNO": "",
        "MGCO_APTM_ODNO": "",
        "SLL_TYPE": "00",
        "ORD_SVR_DVSN_CD": "0"
    }

    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {self.access_token}",
        "appKey": self.app_key,
        "appSecret": self.app_secret,
        "tr_id": "TTTT1006U",
        "custtype": "P",
        "hashkey": self.hashkey(data)
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        response.raise_for_status()
        
        result = response.json()
        
        # 응답 성공 여부 확인
        if result.get('rt_cd') == '0':
            output = result.get('output', {})
            
            order_info = {
                'success': True,
                'ticker': ticker,
                'quantity': quantity,
                'price': price,
                'order_number': output.get('ODNO', ''),
                'order_time': output.get('ORD_TMD', ''),
                'org_number': output.get('KRX_FWDG_ORD_ORGNO', ''),
                'message': result.get('msg1', ''),
                'response': response
            }
            
            # ⭐⭐⭐ 핵심 수정: 성공 메시지 제거 ⭐⭐⭐
            # 성공 메시지는 Selling 함수에서 통합 발송
            # KA.SendMessage(f"정규매도 주문: {ticker} {quantity}주 @ ${price:.2f} \n주문번호: {order_info['order_number']}")  # ← 이 줄 삭제 또는 주석 처리
            
            return order_info
        else:
            # ⭐ 실패 메시지는 즉시 발송 (유지)
            KA.SendMessage(f"정규매도 주문실패: {result.get('msg1', '알 수 없는 오류')}")
            return {
                'success': False,
                'ticker': ticker,
                'quantity': quantity,
                'price': price,
                'order_number': '',
                'error_code': result.get('rt_cd'),
                'error_message': result.get('msg1', ''),
                'response': response
            }
            
    except Exception as e:
        # ⭐ 예외 메시지는 즉시 발송 (유지)
        KA.SendMessage(f"정규매도 주문 오류: {e}")
        return None


def order_buy_US(self, ticker: str, quantity: int, price: float,
                   exchange: Optional[str] = None, ord_dvsn: str = "00") -> Optional[Dict]:
    """
    미국 주식 매수 주문 (Regular Market)
    """
    if exchange is None:
        exchange = self.get_exchange_by_ticker(ticker)
        if exchange == "NAS" or exchange == "BAQ":
            exchange = "NASD"
        elif exchange == "AMS" or exchange == "BAA":
            exchange = "AMEX"
        elif exchange == "NYS" or exchange == "BAY":
            exchange = "NYSE"
        else:
            exchange = None
    
    if exchange is None:
        KA.SendMessage(f"{ticker} 거래소를 찾을 수 없습니다.")
        return None
    
    # 가격을 소수점 2자리로 반올림
    price = round(price, 2)
    
    path = "uapi/overseas-stock/v1/trading/order"
    url = f"{self.url_base}/{path}"

    data = {
        "CANO": self.cano,
        "ACNT_PRDT_CD": self.acnt_prdt_cd,
        "OVRS_EXCG_CD": exchange,
        "PDNO": ticker,
        "ORD_DVSN": ord_dvsn,
        "ORD_QTY": str(quantity),
        "OVRS_ORD_UNPR": f"{price:.2f}",
        "CTAC_TLNO": "",
        "MGCO_APTM_ODNO": "",
        "ORD_SVR_DVSN_CD": "0"
    }

    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {self.access_token}",
        "appKey": self.app_key,
        "appSecret": self.app_secret,
        "tr_id": "TTTT1002U",  # 매수는 TTTT1002U
        "custtype": "P",
        "hashkey": self.hashkey(data)
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        response.raise_for_status()
        
        result = response.json()
        
        # 응답 성공 여부 확인
        if result.get('rt_cd') == '0':
            output = result.get('output', {})
            
            order_info = {
                'success': True,
                'ticker': ticker,
                'quantity': quantity,
                'price': price,
                'order_number': output.get('ODNO', ''),
                'order_time': output.get('ORD_TMD', ''),
                'org_number': output.get('KRX_FWDG_ORD_ORGNO', ''),
                'message': result.get('msg1', ''),
                'response': response
            }
            
            # ⭐⭐⭐ 핵심 수정: 성공 메시지 제거 ⭐⭐⭐
            # 성공 메시지는 Buying 함수에서 통합 발송
            # KA.SendMessage(f"정규매수 주문: {ticker} {quantity}주 @ ${price:.2f} \n주문번호: {order_info['order_number']}")  # ← 이 줄 삭제 또는 주석 처리
            
            return order_info
        else:
            # ⭐ 실패 메시지는 즉시 발송 (유지)
            KA.SendMessage(f"정규매수 주문실패: {result.get('msg1', '알 수 없는 오류')}")
            return {
                'success': False,
                'ticker': ticker,
                'quantity': quantity,
                'price': price,
                'order_number': '',
                'error_code': result.get('rt_cd'),
                'error_message': result.get('msg1', ''),
                'response': response
            }
            
    except Exception as e:
        # ⭐ 예외 메시지는 즉시 발송 (유지)
        KA.SendMessage(f"정규매수 주문 오류: {e}")
        return None


# ⭐⭐⭐ 핵심 수정 요약 ⭐⭐⭐
# 
# 수정 전:
# - 성공: "정규매도 주문: TQQQ 3주 @ $111.96" 발송
# - 실패: "정규매도 주문실패: ..." 발송
#
# 수정 후:
# - 성공: 메시지 발송 안 함 (Selling 함수에서 통합 발송)
# - 실패: 즉시 메시지 발송 (유지)
#
# 이유:
# 1. 성공 메시지는 Selling/Buying에서 모아서 한 번에 보냄
# 2. 실패 메시지는 즉시 알아야 하므로 개별 발송
# 3. 결과적으로 메시지 수 대폭 감소!
