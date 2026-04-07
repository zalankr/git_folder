import requests
import json
from datetime import datetime, timedelta
import telegram_alert as TA
import sys
import os
from typing import Union, Optional, Dict, List, Tuple
import time

class KIS_API:
    """한국투자증권 API 클래스 (일본주식 전용 - KIS_US.py 구조 동일)"""
    
    def __init__(self, key_file_path: str, token_file_path: str, cano: str, acnt_prdt_cd: str):
        self.key_file_path = key_file_path
        self.token_file_path = token_file_path
        self.cano = cano
        self.acnt_prdt_cd = acnt_prdt_cd
        self.url_base = "https://openapi.koreainvestment.com:9443"
        
        self._load_api_keys()
        self.access_token = self.get_access_token()
        self.SELL_FEE_RATE = 0.0012  # 매도 수수료 0.12% 이벤트 계좌
        self.BUY_FEE_RATE = 0.0012  # 매수 수수료 0.12% 이벤트 계좌

        # 일본 시장 고정값
        self.EXCHANGE_CODE = "TSE"    # 현재가 조회용 (HHDFS00000300 EXCD)
        self.EXCHANGE_ORDER = "TKSE"  # 주문/잔고 조회용 (OVRS_EXCG_CD)
        self.NATN_CD = "392"          # 일본 국가코드
        self.CURRENCY = "JPY"
    
    # ============================================
    # API-Key 로드
    # ============================================
    def _load_api_keys(self):
        try:
            with open(self.key_file_path) as f:
                self.app_key, self.app_secret = [line.strip() for line in f.readlines()]
        except FileNotFoundError:
            TA.send_tele(f"API Key 파일을 찾을 수 없습니다: {self.key_file_path}")
            sys.exit(1)
        except Exception as e:
            TA.send_tele(f"API Key 로드 실패: {e}")
            sys.exit(1)
    
    # ============================================
    # 토큰 관리
    # ============================================
    def load_token(self) -> Optional[Dict]:
        try:
            if os.path.exists(self.token_file_path):
                with open(self.token_file_path, 'r') as f:
                    return json.load(f)
            return None
        except Exception as e:
            TA.send_tele(f"KIS 토큰 로드 오류: {e}")
            return None
    
    def save_token(self, access_token: str, expires_in: int = 86400) -> bool:
        try:
            token_data = {
                "access_token": access_token,
                "issued_at": datetime.now().isoformat(),
                "expires_in": expires_in
            }
            with open(self.token_file_path, 'w') as f:
                json.dump(token_data, f, indent=2)
            return True
        except Exception as e:
            TA.send_tele(f"KIS 토큰 저장 오류: {e}")
            return False
    
    def is_token_valid(self, token_data: Dict) -> bool:
        if not token_data or 'access_token' not in token_data:
            return False
        try:
            issued_at = datetime.fromisoformat(token_data['issued_at'])
            expires_in = token_data.get('expires_in', 86400)
            now = datetime.now()
            expiry_time = issued_at + timedelta(seconds=expires_in)
            safe_expiry_time = expiry_time - timedelta(minutes=60)
            return now < safe_expiry_time
        except:
            return False
    
    def get_new_token(self) -> Optional[str]:
        headers = {"content-type": "application/json"}
        path = "oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        url = f"{self.url_base}/{path}"
        try:
            response = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
            response.raise_for_status()
            token_response = response.json()
            access_token = token_response['access_token']
            expires_in = token_response.get('expires_in', 86400)
            self.save_token(access_token, expires_in)
            return access_token
        except Exception as e:
            TA.send_tele(f"KIS 토큰 발급 실패: {e}")
            sys.exit(1)

    def get_access_token(self) -> Optional[str]:
        token_data = self.load_token()
        if token_data and self.is_token_valid(token_data):
            return token_data['access_token']
        return self.get_new_token()
    
    # ============================================
    # Hash-Key 생성
    # ============================================
    def hashkey(self, datas: Dict) -> str:
        path = "uapi/hashkey"
        url = f"{self.url_base}/{path}"
        headers = {
            'content-Type': 'application/json',
            'appKey': self.app_key,
            'appSecret': self.app_secret,
        }
        try:
            res = requests.post(url, headers=headers, data=json.dumps(datas), timeout=5)
            res.raise_for_status()
            return res.json()["HASH"]
        except Exception as e:
            TA.send_tele(f"Hashkey 생성 실패: {e}")
            return ""

    # ============================================
    # 일본 주식 현재가 조회
    # ============================================
    def get_JP_current_price(self, ticker: str) -> Union[float, str]:
        """
        일본 주식 현재가 조회 (TSE)
        
        Parameters:
            ticker (str): 일본 종목코드 (4자리 숫자, 예: "9980")
        Returns:
            float: 현재가 (엔화, 정수)
            str: 에러 메시지
        """
        if not ticker:
            return "종목코드를 입력해주세요."
        
        ticker = ticker.strip()
        price = self.get_price_from_kis(ticker, self.EXCHANGE_CODE)
        if isinstance(price, float):
            return price
        
        return "현재가 조회 실패"

    def get_price_from_kis(self, ticker: str, exchange: str) -> Union[float, str]:
        """KIS API로 일본 주식 현재가 조회 (3단계 fallback)"""
        
        # 1단계: 현재체결가 API (HHDFS00000300)
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "HHDFS00000300"
        }
        params = {
            "AUTH": "",
            "EXCD": exchange,
            "SYMB": ticker
        }
        
        try:
            response = requests.get(f"{self.url_base}/uapi/overseas-price/v1/quotations/price",
                                   headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('rt_cd') == '0':
                    output = data.get('output', {})
                    for field in ['last', 'base', 'open', 'high', 'low']:
                        value = output.get(field, '').strip()
                        if value and value != '0':
                            try:
                                price = float(value)
                                if price > 0:
                                    return price
                            except:
                                continue
            
            # 2단계: 현재가상세 (HHDFS76200200)
            headers['tr_id'] = "HHDFS76200200"
            response = requests.get(f"{self.url_base}/uapi/overseas-price/v1/quotations/price-detail",
                                   headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('rt_cd') == '0':
                    output = data.get('output', {})
                    for field in ['last', 'open', 'high', 'low', 'base', 't_xprc', 'p_xprc']:
                        value = output.get(field, '').strip()
                        if value and value != '0':
                            try:
                                price = float(value)
                                if price > 0:
                                    return price
                            except:
                                continue
            
            # 3단계: 기간별시세 (HHDFS76240000)
            headers['tr_id'] = "HHDFS76240000"
            params_daily = {
                "AUTH": "",
                "EXCD": exchange,
                "SYMB": ticker,
                "GUBN": "0",
                "BYMD": "",
                "MODP": "0"
            }
            response = requests.get(f"{self.url_base}/uapi/overseas-price/v1/quotations/dailyprice",
                                   headers=headers, params=params_daily, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('rt_cd') == '0':
                    output = data.get('output2', [])
                    if output and len(output) > 0:
                        clos = output[0].get('clos', '').strip()
                        if clos and clos != '0':
                            try:
                                price = float(clos)
                                if price > 0:
                                    return price
                            except:
                                pass
        except:
            pass
        
        return "KIS API 조회 실패"

    # ============================================
    # 일본 주식 매도 주문
    # ============================================
    def order_sell_JP(self, ticker: str, quantity: int, price: float,
                      ord_dvsn: str = "00") -> Tuple[Optional[Dict], List[str]]:
        """
        일본 주식 매도 주문 (TSE 정규장)
        
        Parameters:
            ticker: 종목코드 (4자리 숫자)
            quantity: 주문 수량
            price: 지정가 (엔화, 정수)
            ord_dvsn: 주문구분 ("00": 지정가)
        Returns:
            Tuple[Dict, List[str]]: (주문결과, 메시지리스트)
        """
        order_sell_message = []
        
        # 일본 주식 가격은 정수 (엔화)
        price = int(round(price, 0))
        
        path = "uapi/overseas-stock/v1/trading/order"
        url = f"{self.url_base}/{path}"

        data = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "OVRS_EXCG_CD": self.EXCHANGE_ORDER,  # "TKSE"
            "PDNO": ticker,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(quantity),
            "OVRS_ORD_UNPR": str(price),  # 일본 정수가격
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
            "tr_id": "TTTS0307U",  # ★ 일본 매도 TR_ID
            "custtype": "P",
            "hashkey": self.hashkey(data)
        }

        # 500 에러 재시도 로직
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    time.sleep(1)
                    order_sell_message.append(f"재시도 {attempt}/{max_retries}")
                
                response = requests.post(url, headers=headers, data=json.dumps(data), timeout=10)
                response.raise_for_status()
                result = response.json()
                
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
                        'message': result.get('msg1', '')
                    }
                    order_sell_message.append(
                        f"정규매도 주문: {ticker} {quantity}주 @ ¥{price:,} "
                        f"\n주문번호: {order_info['order_number']}"
                    )
                    return order_info, order_sell_message
                else:
                    order_sell_message.append(f"정규매도 주문실패: {result.get('msg1', '알 수 없는 오류')}")
                    order_info = {
                        'success': False,
                        'ticker': ticker,
                        'quantity': quantity,
                        'price': price,
                        'order_number': '',
                        'error_code': result.get('rt_cd'),
                        'error_message': result.get('msg1', '')
                    }
                    return order_info, order_sell_message
                    
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 500 and attempt < max_retries:
                    order_sell_message.append(f"500 에러 발생, 재시도 중...")
                    continue
                else:
                    order_sell_message.append(f"정규매도 주문 오류: {e}")
                    return None, order_sell_message
            except Exception as e:
                if attempt < max_retries:
                    order_sell_message.append(f"에러 발생, 재시도 중...")
                    continue
                else:
                    order_sell_message.append(f"정규매도 주문 오류: {e}")
                    return None, order_sell_message
        
        order_sell_message.append(f"정규매도 주문 최종 실패: 모든 재시도 소진")
        return None, order_sell_message

    # ============================================
    # 일본 주식 매수 주문
    # ============================================
    def order_buy_JP(self, ticker: str, quantity: int, price: float,
                     ord_dvsn: str = "00") -> Tuple[Optional[Dict], List[str]]:
        """
        일본 주식 매수 주문 (TSE 정규장)
        
        Parameters:
            ticker: 종목코드 (4자리 숫자)
            quantity: 주문 수량
            price: 지정가 (엔화, 정수)
            ord_dvsn: 주문구분 ("00": 지정가)
        Returns:
            Tuple[Dict, List[str]]: (주문결과, 메시지리스트)
        """
        order_buy_message = []
        
        # 일본 주식 가격은 정수 (엔화)
        price = int(round(price, 0))
        
        path = "uapi/overseas-stock/v1/trading/order"
        url = f"{self.url_base}/{path}"

        data = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "OVRS_EXCG_CD": self.EXCHANGE_ORDER,  # "TKSE"
            "PDNO": ticker,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(quantity),
            "OVRS_ORD_UNPR": str(price),
            "CTAC_TLNO": "",
            "MGCO_APTM_ODNO": "",
            "SLL_TYPE": "",  # 매수는 공란
            "ORD_SVR_DVSN_CD": "0"
        }

        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "TTTS0308U",  # ★ 일본 매수 TR_ID
            "custtype": "P",
            "hashkey": self.hashkey(data)
        }

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    time.sleep(1)
                    order_buy_message.append(f"재시도 {attempt}/{max_retries}")
                
                response = requests.post(url, headers=headers, data=json.dumps(data), timeout=10)
                response.raise_for_status()
                result = response.json()
                
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
                        'message': result.get('msg1', '')
                    }
                    order_buy_message.append(
                        f"정규매수 주문: {ticker} {quantity}주 @ ¥{price:,} "
                        f"\n주문번호: {order_info['order_number']}"
                    )
                    return order_info, order_buy_message
                else:
                    order_buy_message.append(f"정규매수 주문실패: {result.get('msg1', '알 수 없는 오류')}")
                    return {
                        'success': False,
                        'ticker': ticker,
                        'quantity': quantity,
                        'price': price,
                        'order_number': '',
                        'error_code': result.get('rt_cd'),
                        'error_message': result.get('msg1', '')
                    }, order_buy_message
                    
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 500 and attempt < max_retries:
                    order_buy_message.append(f"500 에러 발생, 재시도 중...")
                    continue
                else:
                    order_buy_message.append(f"정규매수 주문 오류: {e}")
                    return None, order_buy_message
            except Exception as e:
                if attempt < max_retries:
                    order_buy_message.append(f"에러 발생, 재시도 중...")
                    continue
                else:
                    order_buy_message.append(f"정규매수 주문 오류: {e}")
                    return None, order_buy_message
        
        order_buy_message.append(f"정규매수 주문 최종 실패: 모든 재시도 소진")
        return None, order_buy_message

    # ============================================
    # 일본 주식 종목별 잔고 (체결기준 현재잔고)
    # ============================================
    def get_JP_stock_balance(self) -> Optional[List[Dict]]:
        """일본 주식 종목별 잔고 (체결기준 현재잔고, 연속조회 대응)"""
        path = "uapi/overseas-stock/v1/trading/inquire-present-balance"
        url = f"{self.url_base}/{path}"

        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "CTRP6504R"
        }

        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "WCRC_FRCR_DVSN_CD": "02",
            "NATN_CD": self.NATN_CD,
            "TR_MKET_CD": "00",
            "INQR_DVSN_CD": "00",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": ""
        }

        try:
            stocks: List[Dict] = []
            tr_cont_req = ""
            max_retry = 3
            page_count = 0
            MAX_PAGE = 30

            while True:
                headers["tr_cont"] = tr_cont_req

                data = None
                resp_tr_cont = ""
                for attempt in range(max_retry):
                    try:
                        response = requests.get(url, headers=headers, params=params, timeout=10)
                        response.raise_for_status()
                        data = response.json()
                        resp_tr_cont = response.headers.get("tr_cont", "").strip()
                        break
                    except (requests.exceptions.ConnectionError,
                            requests.exceptions.ChunkedEncodingError,
                            requests.exceptions.ReadTimeout) as conn_err:
                        if attempt == max_retry - 1:
                            TA.send_tele(f"JP잔고 연결 오류(최종): {conn_err}")
                            return None
                        time.sleep(1.0 * (attempt + 1))

                if data is None:
                    return None
                if data.get('rt_cd') != '0':
                    TA.send_tele(f"JP잔고 API 오류: {data.get('msg1')}")
                    return None

                for stock in data.get('output1', []):
                    quantity = int(float(stock.get('ccld_qty_smtl1', 0)))
                    if quantity == 0:
                        continue
                    stocks.append({
                        'ticker': stock.get('pdno', ''),
                        'name': stock.get('prdt_name', ''),
                        'quantity': quantity,
                        'avg_price': float(stock.get('avg_unpr3', 0)),
                        'current_price': float(stock.get('ovrs_now_pric1', 0)),
                        'eval_amt': float(stock.get('frcr_evlu_amt2', 0)),
                        'profit_loss': float(stock.get('evlu_pfls_amt2', 0)),
                        'profit_loss_rate': float(stock.get('evlu_pfls_rt1', 0)),
                        'exchange': stock.get('ovrs_excg_cd', ''),
                        'thdt_buy_qty': int(float(stock.get('thdt_buy_ccld_qty1', 0))),
                        'thdt_sell_qty': int(float(stock.get('thdt_sll_ccld_qty1', 0)))
                    })

                page_count += 1
                if page_count >= MAX_PAGE:
                    break
                if resp_tr_cont in ("D", "E", "F"):
                    break

                FK200 = data.get('ctx_area_fk200', '').strip()
                NK200 = data.get('ctx_area_nk200', '').strip()
                if not FK200 or not NK200:
                    break
                params['CTX_AREA_FK200'] = FK200
                params['CTX_AREA_NK200'] = NK200
                tr_cont_req = "N"
                time.sleep(0.12)

            return stocks

        except Exception as e:
            TA.send_tele(f"JP잔고 조회 오류: {e}")
            return None

    # ============================================
    # 일본 엔화 실제주문가능금액 (TTTS3007R)
    # ============================================
    def get_JP_order_available(self) -> Optional[float]:
        """
        해외주식 매수가능금액 조회 (TTTS3007R)
        MTS 주문화면 '주문가능금액'과 동일한 값 반환 (엔화 기준)
        일본 대표 종목 7203(도요타) / 1000엔 고정 조회
        """
        path = 'uapi/overseas-stock/v1/trading/inquire-psamount'
        url = f'{self.url_base}/{path}'
        headers = {
            'Content-Type': 'application/json',
            'authorization': f'Bearer {self.access_token}',
            'appKey': self.app_key,
            'appSecret': self.app_secret,
            'tr_id': 'TTTS3007R'
        }
        params = {
            'CANO': self.cano,
            'ACNT_PRDT_CD': self.acnt_prdt_cd,
            'OVRS_EXCG_CD': self.EXCHANGE_ORDER,  # "TKSE"
            'ITEM_CD': '7203',     # 도요타 고정 (대표 종목)
            'OVRS_ORD_UNPR': '1000'  # 주문단가 고정 (금액 계산에 무관)
        }
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            if data.get('rt_cd') != '0':
                TA.send_tele(f"TTTS3007R(JP) 오류: {data.get('msg1','')}")
                return None
            output = data.get('output', {})
            JPY = float(output.get('ovrs_ord_psbl_amt', 0))
            return JPY # 0도 유효한 잔고 (None은 API 에러 시에만)
        except Exception as e:
            TA.send_tele(f'JP 매수가능금액 조회 오류: {e}')
            return None

    # ============================================
    # 일본 엔화 예수금 정보 (참조용)
    # ============================================
    def get_JP_yen_balance(self) -> Optional[Dict]:
        """일본 엔화 예수금 (연속조회 마지막 페이지 + JPY 필터)"""
        path = "uapi/overseas-stock/v1/trading/inquire-present-balance"
        url = f"{self.url_base}/{path}"

        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "CTRP6504R"
        }

        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "WCRC_FRCR_DVSN_CD": "02",
            "NATN_CD": self.NATN_CD,  # 392
            "TR_MKET_CD": "00",
            "INQR_DVSN_CD": "00",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": ""
        }

        try:
            last_jpy_info: Optional[Dict] = None
            tr_cont_req = ""
            max_retry = 3
            page_count = 0
            MAX_PAGE = 30

            while True:
                headers["tr_cont"] = tr_cont_req

                data = None
                resp_tr_cont = ""
                for attempt in range(max_retry):
                    try:
                        response = requests.get(url, headers=headers, params=params, timeout=10)
                        response.raise_for_status()
                        data = response.json()
                        resp_tr_cont = response.headers.get("tr_cont", "").strip()
                        break
                    except (requests.exceptions.ConnectionError,
                            requests.exceptions.ChunkedEncodingError,
                            requests.exceptions.ReadTimeout):
                        if attempt == max_retry - 1:
                            return None
                        time.sleep(1.0 * (attempt + 1))

                if data is None or data.get('rt_cd') != '0':
                    return None

                output2 = data.get('output2', [])
                if output2:
                    # JPY 레코드만 선택 (다통화 계좌 대비)
                    for row in output2:
                        if row.get('crcy_cd', '').upper() == 'JPY':
                            last_jpy_info = row
                            break
                    else:
                        last_jpy_info = output2[0]

                page_count += 1
                if page_count >= MAX_PAGE:
                    break
                if resp_tr_cont in ("D", "E", "F"):
                    break

                FK200 = data.get('ctx_area_fk200', '').strip()
                NK200 = data.get('ctx_area_nk200', '').strip()
                if not FK200 or not NK200:
                    break
                params['CTX_AREA_FK200'] = FK200
                params['CTX_AREA_NK200'] = NK200
                tr_cont_req = "N"
                time.sleep(0.12)

            if not last_jpy_info:
                return None

            return {
                'currency': last_jpy_info.get('crcy_cd', 'JPY'),
                'deposit': float(last_jpy_info.get('frcr_dncl_amt_2', 0)),
                'withdrawable': float(last_jpy_info.get('frcr_drwg_psbl_amt_1', 0)),
                'sll_amt_smtl': float(last_jpy_info.get('frcr_sll_amt_smtl', 0)),
                'exchange_rate': float(last_jpy_info.get('frst_bltn_exrt', 0)),
                'krw_value': float(last_jpy_info.get('frcr_evlu_amt2', 0))
            }
        except Exception:
            return None

    # ============================================
    # 미체결 주문 조회
    # ============================================
    def get_unfilled_orders(self, start_date: Optional[str] = None,
                            end_date: Optional[str] = None) -> List[Dict]:
        """일본 미체결 주문 조회 (연속조회 대응)"""
        if start_date is None or end_date is None:
            today = datetime.now().strftime('%Y%m%d')
            start_date = end_date = today

        path = "uapi/overseas-stock/v1/trading/inquire-nccs"
        url = f"{self.url_base}/{path}"

        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "TTTS3018R"
        }

        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "PDNO": "",
            "ORD_STRT_DT": start_date,
            "ORD_END_DT": end_date,
            "SLL_BUY_DVSN": "00",
            "CCLD_NCCS_DVSN": "02",
            "OVRS_EXCG_CD": self.EXCHANGE_ORDER,
            "SORT_SQN": "DS",
            "ORD_DT": "",
            "ORD_GNO_BRNO": "",
            "ODNO": "",
            "CTX_AREA_NK200": "",
            "CTX_AREA_FK200": ""
        }

        try:
            unfilled_orders: List[Dict] = []
            tr_cont_req = ""
            max_retry = 3
            page_count = 0
            MAX_PAGE = 30

            while True:
                headers["tr_cont"] = tr_cont_req

                result = None
                resp_tr_cont = ""
                for attempt in range(max_retry):
                    try:
                        response = requests.get(url, headers=headers, params=params, timeout=10)
                        response.raise_for_status()
                        result = response.json()
                        resp_tr_cont = response.headers.get("tr_cont", "").strip()
                        break
                    except (requests.exceptions.ConnectionError,
                            requests.exceptions.ChunkedEncodingError,
                            requests.exceptions.ReadTimeout) as conn_err:
                        if attempt == max_retry - 1:
                            TA.send_tele(f"JP 미체결 연결 오류(최종): {conn_err}")
                            return []
                        time.sleep(1.0 * (attempt + 1))

                if result is None:
                    return []
                if result.get('rt_cd') != '0':
                    return []

                for order in result.get('output', []):
                    unfilled_orders.append({
                        'order_number': order.get('odno', ''),
                        'ticker': order.get('pdno', ''),
                        'name': order.get('prdt_name', ''),
                        'order_type': order.get('sll_buy_dvsn_cd_name', ''),
                        'order_qty': int(order.get('ft_ord_qty', 0)),
                        'filled_qty': int(order.get('ft_ccld_qty', 0)),
                        'unfilled_qty': int(order.get('nccs_qty', 0)),
                        'order_price': float(order.get('ft_ord_unpr3', 0)),
                        'exchange': order.get('ovrs_excg_cd', ''),
                        'status': order.get('prcs_stat_name', '')
                    })

                page_count += 1
                if page_count >= MAX_PAGE:
                    break
                if resp_tr_cont in ("D", "E", "F"):
                    break

                FK200 = result.get('ctx_area_fk200', '').strip()
                NK200 = result.get('ctx_area_nk200', '').strip()
                if not FK200 or not NK200:
                    break
                params['CTX_AREA_FK200'] = FK200
                params['CTX_AREA_NK200'] = NK200
                tr_cont_req = "N"
                time.sleep(0.12)

            return unfilled_orders

        except Exception as e:
            TA.send_tele(f"JP 미체결 조회 오류: {e}")
            return []

    # ============================================
    # 일본 주식 주문 취소
    # ============================================
    def cancel_JP_order(self, order_number: str, ticker: str,
                        quantity: int) -> Optional[Dict]:
        """일본 주식 주문 취소"""
        
        # 정규장 정정/취소 TR_ID
        tr_id = "TTTS0309U"  # 일본 정정취소
        path = "uapi/overseas-stock/v1/trading/order-rvsecncl"
        url = f"{self.url_base}/{path}"
        
        data = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "OVRS_EXCG_CD": self.EXCHANGE_ORDER,  # "TKSE"
            "PDNO": ticker,
            "ORGN_ODNO": order_number,
            "ORD_DVSN": "00",
            "RVSE_CNCL_DVSN_CD": "02",  # 02: 취소
            "ORD_QTY": "0",             # 취소는 0
            "OVRS_ORD_UNPR": "0",       # 취소는 0
            "CTAC_TLNO": "",
            "MGCO_APTM_ODNO": "",
            "ORD_SVR_DVSN_CD": "0"
        }
        
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
            "hashkey": self.hashkey(data)
        }
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(data))
            response.raise_for_status()
            result = response.json()
            
            if result.get('rt_cd') == '0':
                return {
                    'success': True,
                    'ticker': ticker,
                    'order_number': order_number,
                    'message': result.get('msg1', '')
                }
            else:
                return {
                    'success': False,
                    'ticker': ticker,
                    'order_number': order_number,
                    'error_message': result.get('msg1', '')
                }
        except Exception as e:
            TA.send_tele(f"JP 주문 취소 오류: {e}")
            return None

    # ============================================
    # 모든 미체결 주문 일괄 취소
    # ============================================
    def cancel_all_unfilled_orders(self, start_date: Optional[str] = None,
                                   end_date: Optional[str] = None
                                   ) -> Tuple[Dict, List[str]]:
        """모든 미체결 주문 일괄 취소 (일본 TSE)"""
        unfilled_orders = self.get_unfilled_orders(start_date, end_date)
        
        if not unfilled_orders:
            summary = {
                'total': 0, 'success': 0, 'failed': 0,
                'success_list': [], 'failed_list': []
            }
            message = ["미체결 주문 없음"]
            return summary, message

        success_list = []
        failed_list = []
        
        for i, order in enumerate(unfilled_orders, 1):
            result = self.cancel_JP_order(
                order_number=order['order_number'],
                ticker=order['ticker'],
                quantity=order['order_qty']
            )
            
            if result and result.get('success'):
                success_list.append({
                    'ticker': order['ticker'],
                    'name': order['name'],
                    'order_number': order['order_number'],
                    'unfilled_qty': order['unfilled_qty']
                })
            else:
                failed_list.append({
                    'ticker': order['ticker'],
                    'name': order['name'],
                    'order_number': order['order_number'],
                    'unfilled_qty': order['unfilled_qty'],
                    'error': result.get('error_message') if result else '알 수 없는 오류'
                })
            
            time.sleep(0.2)
        
        summary = {
            'total': len(unfilled_orders),
            'success': len(success_list),
            'failed': len(failed_list),
            'success_list': success_list,
            'failed_list': failed_list
        }
        
        message = []
        message.append(f"전체 미체결: {summary['total']}건")
        message.append(f"취소 성공: {summary['success']}건")
        message.append(f"취소 실패: {summary['failed']}건")
        return summary, message


"""
[일본 주식 주문 TR_ID 정리]

매수: TTTS0308U (실전) / VTTS0308U (모의)
매도: TTTS0307U (실전) / VTTS0307U (모의)
정정/취소: TTTS0309U (실전) / VTTS0309U (모의)

[거래소 코드]
현재가 조회 (EXCD): TSE
주문/잔고 (OVRS_EXCG_CD): TKSE
국가코드 (NATN_CD): 392

[일본 거래시간 - KST 기준]
오전: 09:00 ~ 11:30
오후: 12:30 ~ 15:00

[UTC 기준 (EC2)]
오전: 00:00 ~ 02:30
오후: 03:30 ~ 06:00

[주문가격]
일본주식은 엔화 정수 단위로 주문 (소수점 없음)
ord_dvsn: "00" = 지정가

[수수료]
매수: 수수료 체결가에 포함 (별도 차감 없음)
매도: 0.09% 명시적 차감 필요 (이벤트 계좌)
"""
