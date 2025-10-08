# KIS_US.py에 추가할 메서드들
# 기존 KIS_API 클래스에 아래 메서드들을 추가하세요

import pandas as pd
from typing import Dict, List, Optional
import time

class KIS_API_Extended:
    """KIS_API 클래스에 추가할 메서드들"""
    
    # 클래스 변수로 수수료율 추가
    SELL_FEE_RATE = 0.0009  # 매도 수수료 0.09%
    
    def get_order_executions_detailed(
        self,
        start_date: str = None,
        end_date: str = None,
        ticker: str = "",
        sll_buy_dvsn: str = "00",
        ccld_nccs_dvsn: str = "01",
        exchange: str = "NASD"
    ) -> pd.DataFrame:
        """
        주문 체결내역 상세 조회 (수수료 계산 포함)
        
        Parameters:
        start_date: 조회 시작일 (YYYYMMDD)
        end_date: 조회 종료일 (YYYYMMDD)
        ticker: 종목코드
        sll_buy_dvsn: 00:전체, 01:매도, 02:매수
        ccld_nccs_dvsn: 00:전체, 01:체결, 02:미체결
        exchange: 거래소코드
        
        Returns:
        pd.DataFrame: 체결내역 + 수수료 계산
        """
        from datetime import datetime
        
        # 날짜 기본값 설정
        if start_date is None:
            start_date = datetime.now().strftime('%Y%m%d')
        if end_date is None:
            end_date = datetime.now().strftime('%Y%m%d')
        
        path = "/uapi/overseas-stock/v1/trading/inquire-ccnl"
        url = f"{self.url_base}{path}"
        
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "TTTS3035R",
            "custtype": "P"
        }
        
        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "PDNO": ticker,
            "ORD_STRT_DT": start_date,
            "ORD_END_DT": end_date,
            "SLL_BUY_DVSN": sll_buy_dvsn,
            "CCLD_NCCS_DVSN": ccld_nccs_dvsn,
            "OVRS_EXCG_CD": exchange,
            "SORT_SQN": "DS",
            "ORD_DT": "",
            "ORD_GNO_BRNO": "",
            "ODNO": "",
            "CTX_AREA_NK200": "",
            "CTX_AREA_FK200": ""
        }
        
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            result = response.json()
            
            if result.get('rt_cd') == '0':
                orders = result.get('output', [])
                if not orders:
                    return pd.DataFrame()
                
                df = pd.DataFrame(orders)
                
                # 수치형 변환
                df['ft_ccld_qty'] = pd.to_numeric(df['ft_ccld_qty'], errors='coerce')
                df['ft_ccld_unpr3'] = pd.to_numeric(df['ft_ccld_unpr3'], errors='coerce')
                df['ft_ccld_amt3'] = pd.to_numeric(df['ft_ccld_amt3'], errors='coerce')
                
                # 매도/매수 구분
                df['is_sell'] = df['sll_buy_dvsn_cd'] == '01'
                
                # 수수료 계산
                df['fee'] = 0.0
                df.loc[df['is_sell'], 'fee'] = df.loc[df['is_sell'], 'ft_ccld_amt3'] * self.SELL_FEE_RATE
                
                # 순 체결금액 (매도: 수수료 차감, 매수: 그대로)
                df['net_amount'] = df['ft_ccld_amt3'] - df['fee']
                
                # 예수금 변동액 (매도: +, 매수: -)
                df['deposit_change'] = df['net_amount']
                df.loc[~df['is_sell'], 'deposit_change'] = -df.loc[~df['is_sell'], 'ft_ccld_amt3']
                
                # 반올림
                df['fee'] = df['fee'].round(2)
                df['net_amount'] = df['net_amount'].round(2)
                df['deposit_change'] = df['deposit_change'].round(2)
                
                return df
            else:
                print(f"API 오류: {result.get('msg1')}")
                return pd.DataFrame()
                
        except Exception as e:
            print(f"체결내역 조회 오류: {e}")
            return pd.DataFrame()
    
    def get_usd_deposit_info(self) -> Dict:
        """
        USD 예수금 상세 정보 조회
        
        Returns:
        Dict: {
            'deposit': 예수금,
            'withdrawable': 출금가능금액,
            'exchange_rate': 환율,
            'krw_value': 원화환산금액
        }
        """
        path = "/uapi/overseas-stock/v1/trading/inquire-present-balance"
        url = f"{self.url_base}{path}"
        
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "CTRP6504R",
            "custtype": "P"
        }
        
        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "WCRC_FRCR_DVSN_CD": "02",  # 외화
            "NATN_CD": "840",  # 미국
            "TR_MKET_CD": "00",
            "INQR_DVSN_CD": "00"
        }
        
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            result = response.json()
            
            if result.get('rt_cd') == '0':
                output2 = result.get('output2', [])
                if output2:
                    info = output2[0]
                    deposit = float(info.get('frcr_dncl_amt_2', 0))
                    exchange_rate = float(info.get('frst_bltn