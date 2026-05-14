import requests
import json
from datetime import datetime, timedelta
import telegram_alert as TA
import sys
import os
from typing import Union, Optional, Dict, List, Tuple
import time

class KIS_API:
    """한국투자증권 API 클래스 (최종 정제 버전 + 체결내역 추적 기능)"""
    def __init__(self, key_file_path: str, token_file_path: str, cano: str, acnt_prdt_cd: str): #
        self.key_file_path = key_file_path
        self.token_file_path = token_file_path
        self.cano = cano
        self.acnt_prdt_cd = acnt_prdt_cd
        self.url_base = "https://openapi.koreainvestment.com:9443"
        
        self._load_api_keys()
        self.access_token = self.get_access_token()
        self.sell_fee_tax = 0.00214  # 매도 수수료 0.014% + 세금 0.2% KRQT계좌
        self.buy_fee_tax = 0.00014  # 매수 수수료 0.014% KRQT 계좌

        self.last_api_call = 0
        self.api_interval = 0.1 # 초당 ~10회 요청 인터벌

    # API 간격 제어
    def _rate_limit_sleep(self): #
        """API 호출 간격 제어 (Rate Limit 대응)"""
        elapsed = time.time() - self.last_api_call
        if elapsed < self.api_interval:
            time.sleep(self.api_interval - elapsed)
        self.last_api_call = time.time()

    # API-Key 로드 
    def _load_api_keys(self): #
        try:
            with open(self.key_file_path) as f:
                self.app_key, self.app_secret = [line.strip() for line in f.readlines()]
        except FileNotFoundError:
            TA.send_tele(f"API Key 파일을 찾을 수 없습니다: {self.key_file_path}")
            sys.exit(1)
        except Exception as e:
            TA.send_tele(f"API Key 로드 실패: {e}")
            sys.exit(1)
    
    # 토큰 로드
    def load_token(self) -> Optional[Dict]: #
        try:
            if os.path.exists(self.token_file_path):
                with open(self.token_file_path, 'r') as f:
                    return json.load(f)
            return None
        except Exception as e:
            TA.send_tele(f"KIS 토큰 로드 오류: {e}")
            return None
    
    # 토큰 저장
    def save_token(self, access_token: str, expires_in: int = 86400) -> bool: #
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
    
    # 토큰 유효성 확인
    def is_token_valid(self, token_data: Dict) -> bool: #
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
    
    # 토큰 발급
    def get_new_token(self) -> Optional[str]: #
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

    # 토큰 접속
    def get_access_token(self) -> Optional[str]: #
        token_data = self.load_token()
        
        if token_data and self.is_token_valid(token_data):
            return token_data['access_token']
        
        return self.get_new_token()
    
    # Hash-Key 생성
    def hashkey(self, datas: Dict) -> str: #
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
            raise RuntimeError(f"Hashkey 생성 실패: {e}")  # 빈 문자열 반환 시 주문이 진행되므로 예외로 차단
    
    # 국내 주식 현재가 조회
    def get_KR_current_price(self, ticker: str) -> Union[int, str]: #
        """
        국내 주식 현재가 조회
        Parameters:
            ticker (str): 종목코드 (예: "005930" 삼성전자)
        Returns:
            int: 현재가
            str: 에러 메시지
        """
        if not ticker:
            return "종목코드를 입력해주세요."

        path = "uapi/domestic-stock/v1/quotations/inquire-price"
        url = f"{self.url_base}/{path}"
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "FHKST01010100"
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",  # J: 주식/ETF/ETN
            "FID_INPUT_ISCD": ticker
        }

        try:
            res = requests.get(url, headers=headers, params=params, timeout=5)
            res.raise_for_status()
            data = res.json()

            if data.get("rt_cd") == "0":
                return int(data["output"]["stck_prpr"])  # 주식 현재가
            else:
                return f"현재가 조회 실패: {data.get('msg1', '알 수 없는 오류')}"

        except Exception as e:
            return f"현재가 조회 오류: {e}"

    # 한국 주식 계좌 잔고 조회
    def get_KR_stock_balance(self) -> Union[List[Dict], str]: #
        """한국 주식 종목별 잔고 조회"""
        path = "uapi/domestic-stock/v1/trading/inquire-balance"
        url = f"{self.url_base}/{path}"

        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "TTTC8434R",   # 실전투자 / 모의투자: VTTC8434R
            "custtype": "P"
        }

        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "00",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }

        try:
            stocks = []
            tr_cont_req = ""        # 첫 조회: 공백, 연속조회: "N"
            max_retry = 3
            page_count = 0
            MAX_PAGE = 30           # 안전장치 (20종목 × 30 = 600종목)

            while True:
                headers["tr_cont"] = tr_cont_req

                data = None
                resp_tr_cont = ""
                for attempt in range(max_retry):
                    try:
                        self._rate_limit_sleep()
                        response = requests.get(url, headers=headers, params=params, timeout=10)
                        response.raise_for_status()
                        data = response.json()
                        resp_tr_cont = response.headers.get("tr_cont", "").strip()
                        break
                    except (requests.exceptions.ConnectionError,
                            requests.exceptions.ChunkedEncodingError,
                            requests.exceptions.ReadTimeout) as conn_err:
                        if attempt == max_retry - 1:
                            return f"한국주식 잔고조회 연결 오류(최종): {conn_err}"
                        time.sleep(1.0 * (attempt + 1))

                if data is None:
                    return "한국주식 잔고조회 응답 없음"

                if data.get('rt_cd') != '0':
                    return f"한국주식 잔고조회 API 오류: {data.get('msg1')}"

                for stock in data.get('output1', []):
                    quantity = int(stock.get('hldg_qty', 0))
                    if quantity == 0:
                        continue
                    stocks.append({
                        "종목코드": stock.get('pdno', ''),
                        "종목명":   stock.get('prdt_name', ''),
                        "보유수량": quantity,
                        "매도가능수량": int(stock.get('ord_psbl_qty', 0)),
                        "매입단가": float(stock.get('pchs_avg_pric', 0)),
                        "매입금액": int(float(stock.get('pchs_amt', 0))),
                        "현재가":   int(stock.get('prpr', 0)),
                        "평가금액": int(float(stock.get('evlu_amt', 0))),
                        "평가손익": int(float(stock.get('evlu_pfls_amt', 0))),
                        "수익률":   float(stock.get('evlu_pfls_rt', 0))
                    })

                page_count += 1
                if page_count >= MAX_PAGE:
                    break

                # 연속조회 종료 판정: 응답 헤더 tr_cont 우선
                if resp_tr_cont in ("D", "E", "F"):
                    break

                FK100 = data.get('ctx_area_fk100', '').strip()
                NK100 = data.get('ctx_area_nk100', '').strip()
                if FK100 == '' or NK100 == '':
                    break
                params['CTX_AREA_FK100'] = FK100
                params['CTX_AREA_NK100'] = NK100
                tr_cont_req = "N"
                time.sleep(0.12)

            return stocks

        except Exception as e:
            return f"한국주식 잔고조회 오류: {e}"

    # 한국 주식 종목 잔고 조회
    def get_KR_stock_balance_by_ticker(self, ticker: str) -> Optional[Dict]:
        """한국 주식 특정 종목 잔고 조회"""
        stocks = self.get_KR_stock_balance()
        if not isinstance(stocks, list):
            return None

        for stock in stocks:
            if stock['종목코드'] == ticker:
                return stock

        return None  # 미보유 종목

    # 한국 주식 계좌 원화 평가금 요약        
    def get_KR_account_summary(self) -> Optional[Dict]: #
        """
        한국주식 계좌 원화 자산 요약
        Returns:
            {
                'stock_eval_amt':  한국주식 평가금액 합계 (원),
                'cash_balance':    D+2 정산 포함 주문가능현금 (원),
                'total_krw_asset': 계좌 전체 원화자산 = nass_amt (주식평가금 + D+2 현금)
            }

        ※ 필드 구조:
            - nass_amt      : 순자산금액 = 주식평가금 + D+2 정산현금 합계 → total_krw_asset ✅
            - stock_eval_amt: output1에서 직접 합산한 주식 평가금액
            - cash_balance  : nass_amt - stock_eval_amt (파생값, 표시용)

        ※ 이전 오류 패턴 (절대 반복 금지):
            - dnca_tot_amt를 cash로, stock_eval_amt와 합산 → D+0만 반영, 미정산분 누락 ❌
            - nass_amt를 cash로, stock_eval_amt와 합산 → 주식이 이중 계산됨 ❌
        """
        path = "uapi/domestic-stock/v1/trading/inquire-balance"
        url = f"{self.url_base}/{path}"

        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "TTTC8434R",   # 실전투자 / 모의투자: VTTC8434R
            "custtype": "P"
        }

        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "00",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }

        try:
            stock_eval_amt = 0.0
            total_krw_asset = 0.0  # nass_amt (순자산 = 주식 + D+2 현금 합계)
            tr_cont_req = ""        # 첫 조회: 공백, 연속조회: "N"
            max_retry = 3
            page_count = 0
            MAX_PAGE = 30           # 무한루프 안전장치 (20종목 × 30 = 600종목)

            while True:
                # 연속조회 헤더 세팅 (KIS 사양 필수)
                headers["tr_cont"] = tr_cont_req

                # 일시적 RemoteDisconnected / Timeout 재시도
                data = None
                resp_tr_cont = ""
                for attempt in range(max_retry):
                    try:
                        self._rate_limit_sleep()
                        response = requests.get(url, headers=headers, params=params, timeout=10)
                        response.raise_for_status()
                        data = response.json()
                        resp_tr_cont = response.headers.get("tr_cont", "").strip()
                        break
                    except (requests.exceptions.ConnectionError,
                            requests.exceptions.ChunkedEncodingError,
                            requests.exceptions.ReadTimeout) as conn_err:
                        if attempt == max_retry - 1:
                            TA.send_tele(f"계좌요약 연결 오류(최종): {conn_err}")
                            return None
                        time.sleep(1.0 * (attempt + 1))  # 1s → 2s 백오프

                if data is None:
                    return None

                if data.get('rt_cd') != '0':
                    TA.send_tele(f"계좌요약 API 오류: {data.get('msg1')}")
                    return None

                # output1: 종목별 평가금액 직접 합산 (페이지마다 누적)
                for stock in data.get('output1', []):
                    if int(stock.get('hldg_qty', 0)) == 0:
                        continue
                    stock_eval_amt += float(stock.get('evlu_amt', 0))

                # output2: nass_amt 는 마지막 페이지에서만 의미 있음 → 0이 아닐 때만 갱신
                output2 = data.get('output2', [{}])
                summary = output2[0] if output2 else {}
                nass_amt_page = float(summary.get('nass_amt', 0) or 0)
                if nass_amt_page > 0:
                    total_krw_asset = nass_amt_page

                # 연속조회 종료 판정: 응답 헤더 tr_cont 가 우선, 없으면 ctx 값으로 판단
                page_count += 1
                if page_count >= MAX_PAGE:
                    break
                if resp_tr_cont in ("D", "E", "F", ""):
                    # D/E/F = 마지막, 빈문자 = 더 이상 없음
                    if resp_tr_cont == "":
                        # 일부 환경은 헤더가 비어있으므로 ctx로 재확인
                        FK100 = data.get('ctx_area_fk100', '').strip()
                        NK100 = data.get('ctx_area_nk100', '').strip()
                        if FK100 == '' or NK100 == '':
                            break
                        params['CTX_AREA_FK100'] = FK100
                        params['CTX_AREA_NK100'] = NK100
                        tr_cont_req = "N"
                        time.sleep(0.12)
                        continue
                    break

                # M = 다음 페이지 있음 → 연속조회
                FK100 = data.get('ctx_area_fk100', '').strip()
                NK100 = data.get('ctx_area_nk100', '').strip()
                if FK100 == '' or NK100 == '':
                    break
                params['CTX_AREA_FK100'] = FK100
                params['CTX_AREA_NK100'] = NK100
                tr_cont_req = "N"
                time.sleep(0.12)

            cash_balance = total_krw_asset - stock_eval_amt  # D+2 정산 포함 현금 (파생값)

            return {
                'stock_eval_amt':  stock_eval_amt,
                'cash_balance':    cash_balance,
                'total_krw_asset': total_krw_asset
            }

        except Exception as e:
            TA.send_tele(f"계좌요약 조회 오류: {e}")
            return None
        
    # 한국 주식 매수 가능 원화 예수금 조회    
    def get_KR_orderable_cash(self) -> Optional[float]: #
        """
        한국주식 매수 가능 원화 예수금 조회 (D+2 정산 포함)
        TR: TTTC8908R (실전) / VTTC8908R (모의)
        Returns:
            float: 주문가능현금 (원) / None: 오류

        ※ 필드 선택 기준:
            - ord_psbl_cash  : D+0 주문가능현금 → 당일 매도 미정산분 제외, 실제보다 적음 ❌
            - nrcvb_buy_amt  : 미수없는 매수가능금액 = D+2 정산 포함 실제 주문가능금액 ✅
        """
        path = "uapi/domestic-stock/v1/trading/inquire-psbl-order"
        url = f"{self.url_base}/{path}"

        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "TTTC8908R",   # 실전투자 / 모의투자: VTTC8908R
            "custtype": "P"
        }

        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "PDNO": "005930",       # 조회용 더미 종목코드 (삼성전자) - API 필수값
            "ORD_UNPR": "0",        # 시장가 기준 (0 입력)
            "ORD_DVSN": "01",       # 01: 시장가
            "CMA_EVLU_AMT_ICLD_YN": "N",   # CMA 평가금액 포함여부
            "OVRS_ICLD_YN": "N"    # 해외 포함여부
        }

        try:
            self._rate_limit_sleep()
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get('rt_cd') != '0':
                TA.send_tele(f"매수가능조회 API 오류: {data.get('msg1')}")
                return None

            # ✅ nrcvb_buy_amt: 미수없는 매수가능금액 (D+2 정산대금 포함, 실제 주문가능금액)
            # ❌ ord_psbl_cash: D+0 현금만 반영 → 당일 매도 미정산분 누락으로 실제보다 적게 나옴
            return float(data['output'].get('nrcvb_buy_amt', 0))

        except Exception as e:
            TA.send_tele(f"매수가능현금 조회 오류: {e}")
            return None

    # 한국 주식 매수 주문
    def order_buy_KR(self, ticker: str, quantity: int, price: int = 0,
                     ord_dvsn: str = "00") -> Optional[Dict]: #
        """
        한국 주식 매수 주문

        Parameters:
            ticker   (str): 종목코드 (예: "005930")
            quantity (int): 주문 수량
            price    (int): 주문 단가 (시장가일 때는 0)
            ord_dvsn (str): 주문구분
                "00" 지정가 | "01" 시장가 | "02" 조건부지정가
                "03" 최유리지정가 | "04" 최우선지정가 | "05" 장전시간외
                "06" 장후시간외 | "07" 시간외단일가

        Returns:
            Tuple[Dict | None, List[str]]
            Dict keys:
                success      (bool)
                ticker       (str)
                quantity     (int)
                price        (int)
                order_number (str)  주문번호 (ODNO)
                order_time   (str)  주문시각
                org_number   (str)  원주문번호
                message      (str)
                response     (requests.Response)
        """
        if not ticker or quantity <= 0:
            return None

        path = "uapi/domestic-stock/v1/trading/order-cash"
        url  = f"{self.url_base}/{path}"

        data = {
            "CANO":         self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "PDNO":         ticker,
            "ORD_DVSN":     ord_dvsn,
            "ORD_QTY":      str(quantity),
            "ORD_UNPR":     str(price),   # 시장가는 "0"
        }

        headers = {
            "Content-Type":  "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey":        self.app_key,
            "appSecret":     self.app_secret,
            "tr_id":         "TTTC0802U",
            "custtype":      "P",
            "hashkey":       self.hashkey(data)
        }

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    time.sleep(1)

                self._rate_limit_sleep()
                response = requests.post(url, headers=headers, data=json.dumps(data), timeout=10)
                response.raise_for_status()
                result = response.json()

                if result.get("rt_cd") == "0":
                    output = result.get("output", {})
                    order_info = {
                        "success":      True,
                        "ticker":       ticker,
                        "quantity":     quantity,
                        "price":        price,
                        "order_number": output.get("ODNO", ""),
                        "order_time":   output.get("ORD_TMD", ""),
                        "org_number":   output.get("KRX_FWDG_ORD_ORGNO", ""),
                        "message":      result.get("msg1", ""),
                        "response":     response
                    }
                    return order_info
                else:
                    return {
                        "success":       False,
                        "ticker":        ticker,
                        "quantity":      quantity,
                        "price":         price,
                        "order_number":  "",
                        "error_code":    result.get("rt_cd"),
                        "error_message": result.get("msg1", ""),
                        "response":      response
                    }

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 500 and attempt < max_retries:
                    TA.send_tele("500 에러 발생, 재시도 중...")
                    continue
                try:
                    err_body = e.response.json()
                    return {
                        "success":       False,
                        "ticker":        ticker,
                        "quantity":      quantity,
                        "price":         price,
                        "order_number":  "",
                        "error_code":    str(e.response.status_code),
                        "error_message": err_body.get("msg1", str(e)),
                        "response":      e.response
                    }
                except Exception:
                    return None

            except Exception as e:
                if attempt < max_retries:
                    continue
                return None

        return None

    # 한국 주식 매도 주문
    def order_sell_KR(self, ticker: str, quantity: int, price: int = 0,
                      ord_dvsn: str = "00") -> Optional[Dict]: #
        """
        한국 주식 매도 주문

        Parameters:
            ticker   (str): 종목코드 (예: "005930")
            quantity (int): 주문 수량
            price    (int): 주문 단가 (시장가일 때는 0)
            ord_dvsn (str): 주문구분 (order_buy_KR 동일)

        Returns:
            Tuple[Dict | None, List[str]]
            Dict keys: success, ticker, quantity, price,
                       order_number, order_time, org_number, message, response
        """

        if not ticker or quantity <= 0:
            TA.send_tele("종목코드 또는 수량이 올바르지 않습니다.")
            return None

        path = "uapi/domestic-stock/v1/trading/order-cash"
        url  = f"{self.url_base}/{path}"

        data = {
            "CANO":         self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "PDNO":         ticker,
            "ORD_DVSN":     ord_dvsn,
            "ORD_QTY":      str(quantity),
            "ORD_UNPR":     str(price),
        }

        headers = {
            "Content-Type":  "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey":        self.app_key,
            "appSecret":     self.app_secret,
            "tr_id":         "TTTC0801U",
            "custtype":      "P",
            "hashkey":       self.hashkey(data)
        }

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    time.sleep(1)

                self._rate_limit_sleep()
                response = requests.post(url, headers=headers, data=json.dumps(data), timeout=10)
                response.raise_for_status()
                result = response.json()

                if result.get("rt_cd") == "0":
                    output = result.get("output", {})
                    order_info = {
                        "success":      True,
                        "ticker":       ticker,
                        "quantity":     quantity,
                        "price":        price,
                        "order_number": output.get("ODNO", ""),
                        "order_time":   output.get("ORD_TMD", ""),
                        "org_number":   output.get("KRX_FWDG_ORD_ORGNO", ""),
                        "message":      result.get("msg1", ""),
                        "response":     response
                    }
                    return order_info
                else:
                    return {
                        "success":       False,
                        "ticker":        ticker,
                        "quantity":      quantity,
                        "price":         price,
                        "order_number":  "",
                        "error_code":    result.get("rt_cd"),
                        "error_message": result.get("msg1", ""),
                        "response":      response
                    }

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 500 and attempt < max_retries:
                    TA.send_tele("500 에러 발생, 재시도 중...")
                    continue
                return None

            except Exception as e:
                if attempt < max_retries:
                    continue
                return None

        return None

    # 한국 주식 주문 체결 확인
    def check_KR_order_execution(self, order_number: str, ticker: str,
                                  order_type: str = "00") -> Optional[Dict]:
        """
        한국 주식 주문 체결 확인

        Parameters:
            order_number (str): 주문번호 (ODNO)
            ticker       (str): 종목코드
            order_type   (str): "00" 전체 | "01" 매도 | "02" 매수

        Returns:
            Dict | None
                success      (bool)
                order_number (str)
                name         (str)  종목명
                qty          (str)  체결수량
                price        (str)  체결단가
                amount       (str)  체결금액
                status       (str)  처리상태명
                order_type   (str)  매도/매수 구분
            None: 해당 주문번호를 찾지 못하거나 API 오류
        """
        today = datetime.now().strftime("%Y%m%d")

        path = "uapi/domestic-stock/v1/trading/inquire-daily-ccld"
        url  = f"{self.url_base}/{path}"

        headers = {
            "Content-Type":  "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey":        self.app_key,
            "appSecret":     self.app_secret,
            "tr_id":         "TTTC8001R",   # 실전: TTTC8001R / 모의: VTTC8001R
            "custtype":      "P"
        }

        params = {
            "CANO":          self.cano,
            "ACNT_PRDT_CD":  self.acnt_prdt_cd,
            "INQR_STRT_DT":  today,
            "INQR_END_DT":   today,
            "SLL_BUY_DVSN_CD": order_type,   # 00: 전체 / 01: 매도 / 02: 매수
            "INQR_DVSN":     "00",            # 00: 역순
            "PDNO":          ticker,
            "CCLD_DVSN":     "01",            # 01: 체결만
            "ORD_GNO_BRNO":  "",
            "ODNO":          order_number,
            "INQR_DVSN_3":   "00",
            "INQR_DVSN_1":   "",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }

        try:
            self._rate_limit_sleep()
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            result = response.json()

            if result.get("rt_cd") != "0":
                TA.send_tele(f"국내 체결확인 조회 실패: {result.get('msg1')}")
                return None

            orders = result.get("output1", [])
            for order in orders:
                if order.get("odno") == order_number:
                    return {
                        "success":      True,
                        "order_number": order_number,
                        "name":         order.get("prdt_name", ""),
                        "qty":          order.get("tot_ccld_qty", "0"),   # 총체결수량
                        "price":        order.get("avg_prvs", "0"),        # 평균체결가
                        "amount":       order.get("tot_ccld_amt", "0"),   # 총체결금액
                        "status":       order.get("ord_tmd", ""),          # 주문시각 (상태 대체)
                        "order_type":   order.get("sll_buy_dvsn_cd_name", "알 수 없음")
                    }

            TA.send_tele(f"체결확인: 주문번호 {order_number} 미체결 또는 조회 실패")
            return None

        except Exception as e:
            TA.send_tele(f"국내 체결 확인 오류: {e}")
            return None

    # 한국 주식 미체결 주문 조회
    def get_KR_unfilled_orders(self) -> List[Dict]: #
        """
        한국 주식 당일 미체결 주문 전체 조회

        Returns:
            List[Dict]: 미체결 주문 리스트
                order_number (str)  주문번호
                ticker       (str)  종목코드
                name         (str)  종목명
                order_type   (str)  매도/매수 구분명
                order_qty    (int)  주문수량
                filled_qty   (int)  체결수량
                unfilled_qty (int)  미체결수량
                order_price  (int)  주문단가
                ord_dvsn     (str)  주문구분명
        """
        path = "uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl"
        url  = f"{self.url_base}/{path}"

        headers = {
            "Content-Type":  "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey":        self.app_key,
            "appSecret":     self.app_secret,
            "tr_id":         "TTTC8036R",   # 실전: TTTC8036R / 모의: VTTC8036R
            "custtype":      "P"
        }

        params = {
            "CANO":          self.cano,
            "ACNT_PRDT_CD":  self.acnt_prdt_cd,
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
            "INQR_DVSN_1":   "0",   # 0: 조회순서 기본
            "INQR_DVSN_2":   "0"    # 0: 전체
        }

        try:
            unfilled: List[Dict] = []
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
                        self._rate_limit_sleep()
                        response = requests.get(url, headers=headers, params=params, timeout=10)
                        response.raise_for_status()
                        result = response.json()
                        resp_tr_cont = response.headers.get("tr_cont", "").strip()
                        break
                    except (requests.exceptions.ConnectionError,
                            requests.exceptions.ChunkedEncodingError,
                            requests.exceptions.ReadTimeout) as conn_err:
                        if attempt == max_retry - 1:
                            TA.send_tele(f"미체결 조회 연결 오류(최종): {conn_err}")
                            return []
                        time.sleep(1.0 * (attempt + 1))

                if result is None:
                    return []

                if result.get("rt_cd") != "0":
                    TA.send_tele(f"미체결 조회 실패: {result.get('msg1')}")
                    return []

                for order in result.get("output", []):
                    unfilled_qty = int(order.get("psbl_qty", 0))
                    if unfilled_qty == 0:
                        continue
                    unfilled.append({
                        "order_number": order.get("odno", ""),
                        "ticker":       order.get("pdno", ""),
                        "name":         order.get("prdt_name", ""),
                        "order_type":   order.get("sll_buy_dvsn_cd_name", ""),
                        "order_qty":    int(order.get("ord_qty", 0)),
                        "filled_qty":   int(order.get("tot_ccld_qty", 0)),
                        "unfilled_qty": unfilled_qty,
                        "order_price":  int(order.get("ord_unpr", 0)),
                        "ord_dvsn":     order.get("ord_dvsn_name", "")
                    })

                page_count += 1
                if page_count >= MAX_PAGE:
                    break

                if resp_tr_cont in ("D", "E", "F"):
                    break

                FK100 = result.get("ctx_area_fk100", "").strip()
                NK100 = result.get("ctx_area_nk100", "").strip()
                if not FK100 or not NK100:
                    break
                params["CTX_AREA_FK100"] = FK100
                params["CTX_AREA_NK100"] = NK100
                tr_cont_req = "N"
                time.sleep(0.12)

            return unfilled

        except Exception as e:
            TA.send_tele(f"미체결 조회 오류: {e}")
            return []

    # 한국 주식 개별 주문 취소
    def cancel_KR_order(self, order_number: str, ticker: str,
                         quantity: int) -> Optional[Dict]: #
        """
        한국 주식 개별 주문 취소

        Parameters:
            order_number (str): 취소할 주문번호 (ODNO)
            ticker       (str): 종목코드
            quantity     (int): 취소 수량 (전량 취소 시 원주문 수량 그대로)

        Returns:
            Dict | None
                success      (bool)
                ticker       (str)
                order_number (str)
                message      (str)
                response     (requests.Response)
        """
        path = "uapi/domestic-stock/v1/trading/order-rvsecncl"
        url  = f"{self.url_base}/{path}"

        data = {
            "CANO":             self.cano,
            "ACNT_PRDT_CD":     self.acnt_prdt_cd,
            "KRX_FWDG_ORD_ORGNO": "",
            "ORGN_ODNO":        order_number,
            "ORD_DVSN":         "00",       # 00: 지정가로 취소
            "RVSE_CNCL_DVSN_CD": "02",     # 02: 취소
            "ORD_QTY":          "0",    # QTY_ALL_ORD_YN=Y 시 반드시 "0"
            "ORD_UNPR":         "0",        # 취소는 0
            "QTY_ALL_ORD_YN":   "Y",        # Y: 잔량 전부 취소
            "PDNO":             ticker
        }

        headers = {
            "Content-Type":  "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey":        self.app_key,
            "appSecret":     self.app_secret,
            "tr_id":         "TTTC0803U",   # 실전: TTTC0803U / 모의: VTTC0803U
            "custtype":      "P",
            "hashkey":       self.hashkey(data)
        }

        try:
            self._rate_limit_sleep()
            response = requests.post(url, headers=headers, data=json.dumps(data), timeout=10)
            response.raise_for_status()
            result = response.json()

            if result.get("rt_cd") == "0":
                return {
                    "success":      True,
                    "ticker":       ticker,
                    "order_number": order_number,
                    "message":      result.get("msg1", ""),
                    "response":     response
                }
            else:
                return {
                    "success":       False,
                    "ticker":        ticker,
                    "order_number":  order_number,
                    "error_message": result.get("msg1", ""),
                    "response":      response
                }

        except Exception as e:
            TA.send_tele(f"주문 취소 오류: {e}")
            return None

    # 한국 주식 전체 주문 취소
    def cancel_all_KR_unfilled_orders(self, side: str = "all") -> Optional[Dict]: #
        if side not in ("buy", "sell", "all"):
            raise ValueError(f"side는 'buy', 'sell', 'all' 중 하나여야 합니다: {side}")

        unfilled_orders = self.get_KR_unfilled_orders()

        empty_summary = {
            "total": 0, "success": 0, "failed": 0,
            "success_list": [], "failed_list": []
        }
        if not unfilled_orders:
            return empty_summary

        # ✅ 실제 필드명 "order_type", 실제 값 "매수"/"매도" 기준으로 필터
        side_map = {"buy": "매수", "sell": "매도"}
        if side != "all":
            unfilled_orders = [o for o in unfilled_orders if o.get("order_type") == side_map[side]]

        if not unfilled_orders:
            return empty_summary

        success_list, failed_list = [], []

        for order in unfilled_orders:
            result = self.cancel_KR_order(
                order_number=order["order_number"],
                ticker=order["ticker"],
                quantity=order["unfilled_qty"]
            )
            entry = {
                "ticker":       order["ticker"],
                "name":         order["name"],
                "order_number": order["order_number"],
                "unfilled_qty": order["unfilled_qty"],
                "order_type":   order.get("order_type")
            }
            if result and result.get("success"):
                success_list.append(entry)
            else:
                entry["error"] = result.get("error_message") if result else "알 수 없는 오류"
                failed_list.append(entry)
            time.sleep(0.2)

        summary = {
            "total":        len(unfilled_orders),
            "success":      len(success_list),
            "failed":       len(failed_list),
            "success_list": success_list,
            "failed_list":  failed_list
        }

        return summary
    
    # 한국 주식 시장 거래일 여부
    def is_KR_trading_day(self, date: Optional[datetime] = None) -> bool: #
        """
        한국 주식시장 거래일 여부 확인 (KIS API 휴장일 조회 기반)

        Parameters:
            date (datetime, optional): 확인할 날짜. 기본값은 오늘.

        Returns:
            bool: 거래일이면 True, 휴장일(주말/공휴일)이면 False
        """
        target = date or datetime.now()

        # 주말 사전 필터 (API 호출 절약)
        if target.weekday() >= 5:  # 5=토, 6=일
            return False

        date_str = target.strftime("%Y%m%d")
        path = "uapi/domestic-stock/v1/quotations/chk-holiday"
        url  = f"{self.url_base}/{path}"

        headers = {
            "Content-Type":  "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey":        self.app_key,
            "appSecret":     self.app_secret,
            "tr_id":         "CTCA0903R",
            "custtype":      "P"
        }
        params = {
            "BASS_DT":   date_str,   # 기준일자 (YYYYMMDD)
            "CTX_AREA_NK": "",
            "CTX_AREA_FK": ""
        }

        for attempt in range(3):   # 최대 3회 재시도
            try:
                self._rate_limit_sleep()
                res = requests.get(url, headers=headers, params=params, timeout=10) # 10초로
                res.raise_for_status()
                data = res.json()

                if data.get("rt_cd") != "0":
                    TA.send_tele(f"거래일 조회 실패: {data.get('msg1')}")
                    return False

                for item in data.get("output", []):
                    if item.get("bass_dt") == date_str:
                        return item.get("opnd_yn") == "Y"

                return False  # 해당 날짜 정보 없으면 보수적으로 False

            except Exception as e:
                if attempt < 2:
                    time.sleep(3) # 3초로
                    continue
                TA.send_tele(f"거래일 조회 오류 (3회 실패): {e}")
                return False
            
    def round_to_tick(self, price: float, market: str = "KR") -> int: #
        """
        주문 가격을 시장별 호가 단위에 맞게 변환
        
        Args:
            price: 원본 가격 (float)
            market: "KR" (한국), "US" (미국), "JP" (일본)
        
        Returns:
            호가 단위에 맞춘 정수 가격
        """
        if market == "US":
            # 미국: 소수점 2자리 (센트 단위) → 정수 불필요, 반올림
            return round(price, 2)
        
        elif market == "JP":
            # 일본: 엔화 단위 (정수)
            return int(price)
        
        elif market == "KR":
            # 한국: 주가 구간별 호가 단위 (KRX 기준)
            if price < 1_000:
                tick = 1
            elif price < 5_000:
                tick = 5
            elif price < 10_000:
                tick = 10
            elif price < 50_000:
                tick = 50
            elif price < 100_000:
                tick = 100
            elif price < 500_000:
                tick = 500
            else:
                tick = 1_000
            
            return int((price // tick) * tick)
        
        else:
            raise ValueError(f"지원하지 않는 시장: {market}")