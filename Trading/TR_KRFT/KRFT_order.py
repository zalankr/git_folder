# -*- coding: utf-8 -*-
"""
KRFT_order.py
=============
KIS 국내 선물 API 래퍼.

TR-id 매핑:
  - 잔고:     CTFO6118R   (dnca_cash, 보유 포지션 목록)
  - 주문가능: TTTO5105R   (ord_psbl_qty, tot_psbl_qty, lqd_psbl_qty1, bass_idx)
  - 현재가:  FHMIF10000000 (futs_prpr, futs_mxpr/llam, hts_otst_stpl_qty)
  - 호가:    FHMIF10010000 (futs_bidp1, futs_askp1, ...)
  - 주문:    TTTO1101U     (정규)  /  STTN1101U (야간)
  - 정정/취소: TTTO1103U
  - 미체결:  TTTO5301R
  - 체결내역: TTTO5201R

주의:
  - 모든 가격/수량 필드는 문자열로 전송
  - SHTN_PDNO = 단축코드 (A01612 등)
  - 단일 KIS 토큰 인스턴스 재사용 → KIS_KR.py의 KIS_API 인스턴스를 그대로 받아 사용
"""

from __future__ import annotations
import time
import requests
from typing import Optional


# ------------------------------------------------------------------
# 주문 구분 코드 (KIS 선물 공식)
# ------------------------------------------------------------------
ORD_DVSN_LIMIT  = "01"    # 지정가
ORD_DVSN_MARKET = "02"    # 시장가

NMPR_TYPE_LIMIT  = "01"   # 지정가
NMPR_TYPE_MARKET = "02"   # 시장가

# 매수/매도 구분 (sll_buy_dvsn_cd)
SIDE_SELL = "01"
SIDE_BUY  = "02"

# 신규/청산 구분 (cls_cd)
CLS_OPEN  = "01"   # 신규
CLS_CLOSE = "02"   # 청산


# ------------------------------------------------------------------
# 헤더 빌더
# ------------------------------------------------------------------
def _headers(kis, tr_id: str, post: bool = False) -> dict:
    """KIS API 공통 헤더"""
    h = {
        "authorization": f"Bearer {kis.access_token}",
        "appkey":        kis.app_key,
        "appsecret":     kis.app_secret,
        "tr_id":         tr_id,
        "custtype":      "P",
    }
    if post:
        h["content-type"] = "application/json; charset=utf-8"
    return h


def _retry_request(method: str, url: str, headers: dict, **kw) -> Optional[dict]:
    """API 호출 재시도 (network/EGW 오류 대응)"""
    for attempt in range(3):
        try:
            if method == "GET":
                r = requests.get(url, headers=headers, timeout=10, **kw)
            else:
                r = requests.post(url, headers=headers, timeout=10, **kw)
            if r.status_code == 200:
                return r.json()
            # EGW00201 등 일시 오류는 재시도
            time.sleep(0.5 * (attempt + 1))
        except requests.RequestException:
            time.sleep(0.5 * (attempt + 1))
    return None


# ------------------------------------------------------------------
# 현재가 (FHMIF10000000)
# ------------------------------------------------------------------
def get_futures_price(kis, shtn_code: str) -> Optional[dict]:
    """
    선물 현재가 조회.

    Returns:
      {
        "price":    int,    # 현재가 (지수 포인트 * 100, KIS는 소수점 2자리를 정수로 안 줌; 실수 그대로)
        "upper":    float,  # 상한가
        "lower":    float,  # 하한가
        "volume":   int,    # 누적거래량
        "open_int": int,    # 미결제 약정 (hts_otst_stpl_qty)
      }
      None on error.
    """
    kis._rate_limit_sleep()
    url = f"{kis.url_base}/uapi/domestic-futureoption/v1/quotations/inquire-price"
    headers = _headers(kis, "FHMIF10000000")
    params = {
        "FID_COND_MRKT_DIV_CODE": "F",
        "FID_INPUT_ISCD":         shtn_code,
    }
    res = _retry_request("GET", url, headers, params=params)
    if not res or res.get("rt_cd") != "0":
        return None
    out = res.get("output1") or res.get("output") or {}
    try:
        return {
            "price":    float(out.get("futs_prpr", 0) or 0),
            "upper":    float(out.get("futs_mxpr", 0) or 0),
            "lower":    float(out.get("futs_llam", 0) or 0),
            "volume":   int(float(out.get("acml_vol", 0) or 0)),
            "open_int": int(float(out.get("hts_otst_stpl_qty", 0) or 0)),
        }
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------
# 호가 (FHMIF10010000)
# ------------------------------------------------------------------
def get_futures_orderbook(kis, shtn_code: str) -> Optional[dict]:
    """
    선물 호가 조회.

    Returns:
      {
        "bid1": float,    # 매수 1호가
        "ask1": float,    # 매도 1호가
        "bid1_qty": int,  # 매수 1호가 잔량
        "ask1_qty": int,
      }
    """
    kis._rate_limit_sleep()
    url = f"{kis.url_base}/uapi/domestic-futureoption/v1/quotations/inquire-asking-price"
    headers = _headers(kis, "FHMIF10010000")
    params = {
        "FID_COND_MRKT_DIV_CODE": "F",
        "FID_INPUT_ISCD":         shtn_code,
    }
    res = _retry_request("GET", url, headers, params=params)
    if not res or res.get("rt_cd") != "0":
        return None
    # 호가는 output2 에 있음 (KIS 실측 확인)
    out = res.get("output2") or res.get("output1") or res.get("output") or {}
    try:
        return {
            "bid1":     float(out.get("futs_bidp1", 0) or 0),
            "ask1":     float(out.get("futs_askp1", 0) or 0),
            "bid1_qty": int(float(out.get("bidp_rsqn1", 0) or 0)),
            "ask1_qty": int(float(out.get("askp_rsqn1", 0) or 0)),
        }
    except (TypeError, ValueError):
        return None


def get_futures_orderbook_full(kis, shtn_code: str) -> Optional[dict]:
    """5단 호가 전체 반환 (확장용)"""
    kis._rate_limit_sleep()
    url = f"{kis.url_base}/uapi/domestic-futureoption/v1/quotations/inquire-asking-price"
    headers = _headers(kis, "FHMIF10010000")
    params = {
        "FID_COND_MRKT_DIV_CODE": "F",
        "FID_INPUT_ISCD":         shtn_code,
    }
    res = _retry_request("GET", url, headers, params=params)
    if not res or res.get("rt_cd") != "0":
        return None
    out = res.get("output2") or {}
    try:
        bids = [(float(out.get(f"futs_bidp{i}", 0) or 0),
                 int(float(out.get(f"bidp_rsqn{i}", 0) or 0))) for i in range(1, 6)]
        asks = [(float(out.get(f"futs_askp{i}", 0) or 0),
                 int(float(out.get(f"askp_rsqn{i}", 0) or 0))) for i in range(1, 6)]
        return {
            "bids":            bids,           # [(price, qty), ...] 5단
            "asks":            asks,
            "total_bid_qty":   int(float(out.get("total_bidp_rsqn", 0) or 0)),
            "total_ask_qty":   int(float(out.get("total_askp_rsqn", 0) or 0)),
        }
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------
# 잔고 (CTFO6118R)
# ------------------------------------------------------------------
def get_futures_balance(kis) -> Optional[dict]:
    """
    선물옵션 잔고 + 예수금 조회.

    Returns:
      {
        "dnca_cash":     float,    # 예수금 (현금)
        "nass_amt":      float,    # 순자산금액
        "ord_psbl_cash": float,    # 주문가능현금 (있으면)
        "positions":     [
          {
            "symbol":     str,   # SHTN_PDNO
            "name":       str,   # 종목명
            "side":       str,   # "long" or "short"
            "qty":        int,   # 보유 수량
            "avg_price":  float, # 평균 진입가
            "eval_pnl":   float, # 평가손익
          }, ...
        ]
      }
    """
    kis._rate_limit_sleep()
    url = f"{kis.url_base}/uapi/domestic-futureoption/v1/trading/inquire-balance"
    headers = _headers(kis, "CTFO6118R")
    params = {
        "CANO":              kis.cano,
        "ACNT_PRDT_CD":      kis.acnt_prdt_cd,
        "MGNA_DVSN":         "01",   # 01:개시증거금, 02:유지증거금
        "EXCC_STAT_CD":      "1",    # 1:정산, 2:본정산
        "CTX_AREA_FK200":    "",
        "CTX_AREA_NK200":    "",
    }
    res = _retry_request("GET", url, headers, params=params)
    if not res or res.get("rt_cd") != "0":
        return None

    out2 = res.get("output2") or {}
    out1 = res.get("output1") or []

    positions = []
    for p in out1:
        # 수량: cblc_qty(잔고) 우선, 0이면 lqd_psbl_qty(청산가능) 사용.
        # KIS 선물 잔고는 당일 체결분이 cblc_qty 또는 lqd_psbl_qty 에 잡힘.
        cblc = int(float(p.get("cblc_qty", 0) or 0))
        lqd  = int(float(p.get("lqd_psbl_qty", 0) or 0))
        # 두 값 중 절대값이 큰 쪽 채택 (당일 체결 반영)
        if abs(cblc) >= abs(lqd):
            raw_qty = cblc
        else:
            raw_qty = lqd
        if raw_qty == 0:
            continue

        # side 판정: 명시적 구분코드가 없으므로 부호로 판정.
        # 양수=매수보유(long), 음수=매도보유(short).
        side = "long" if raw_qty > 0 else "short"
        qty = abs(raw_qty)

        # 평균단가: pchs_avg_pric 우선, 없으면 ccld_avg_unpr1, excc_unpr 순.
        avg_price = (float(p.get("pchs_avg_pric", 0) or 0)
                     or float(p.get("ccld_avg_unpr1", 0) or 0)
                     or float(p.get("excc_unpr", 0) or 0))

        positions.append({
            "symbol":    str(p.get("shtn_pdno", "") or "").strip(),  # 단축코드
            "std_code":  str(p.get("pdno", "") or "").strip(),       # 표준코드
            "name":      str(p.get("prdt_name", "") or "").strip(),
            "side":      side,
            "qty":       qty,
            "raw_qty":   raw_qty,   # 부호 보존값
            "avg_price": avg_price,
            "eval_pnl":  float(p.get("evlu_pfls_amt", 0) or 0),
        })

    return {
        "dnca_cash":       float(out2.get("dnca_cash", 0) or 0),
        "prsm_dpast_amt":  float(out2.get("prsm_dpast_amt", 0) or 0),   # 추정예탁자산
        "ord_psbl_cash":   float(out2.get("ord_psbl_cash", 0) or 0),
        "wdrw_psbl":       float(out2.get("wdrw_psbl_tot_amt", 0) or 0), # 출금가능
        "evlu_amt_smtl":   float(out2.get("evlu_amt_smtl", 0) or 0),    # 포지션 평가금합계
        "pchs_amt_smtl":   float(out2.get("pchs_amt_smtl", 0) or 0),    # 매입금액합계
        "evlu_pfls_smtl":  float(out2.get("evlu_pfls_amt_smtl", 0) or 0),
        "mgna_tota":       float(out2.get("mgna_tota", 0) or 0),         # 증거금총액
        "positions":       positions,
        "_raw_output1":    out1,   # 진단용 원본
    }


# ------------------------------------------------------------------
# 주문가능 (TTTO5105R) — ★자동매매 진입 시 ord_psbl_qty 사용★
# ------------------------------------------------------------------
def get_futures_orderable(kis, shtn_code: str, price: float,
                          side: str = SIDE_BUY,
                          cls: str = CLS_OPEN) -> Optional[dict]:
    """
    주문가능수량 조회.

    Args:
      shtn_code: 단축코드 (예: A01612)
      price:     주문 예상가격 (지정가 기준)
      side:      "02"=매수, "01"=매도
      cls:       "01"=신규, "02"=청산

    Returns:
      {
        "ord_psbl_qty":   int,   # 신규주문 가능수량 (★자동매매 진입★)
        "tot_psbl_qty":   int,   # 총 가능수량 (신규+청산)
        "lqd_psbl_qty1":  int,   # 청산가능수량
        "bass_idx":       float, # 기준지수
      }
    """
    kis._rate_limit_sleep()
    url = f"{kis.url_base}/uapi/domestic-futureoption/v1/trading/inquire-psbl-order"
    headers = _headers(kis, "TTTO5105R")
    params = {
        "CANO":              kis.cano,
        "ACNT_PRDT_CD":      kis.acnt_prdt_cd,
        "PDNO":              shtn_code,
        "SLL_BUY_DVSN_CD":   side,
        "UNIT_PRICE":        f"{price:.2f}",
        "ORD_DVSN_CD":       ORD_DVSN_LIMIT,
    }
    res = _retry_request("GET", url, headers, params=params)
    if not res or res.get("rt_cd") != "0":
        return None
    out = res.get("output") or {}
    try:
        return {
            "ord_psbl_qty":  int(float(out.get("ord_psbl_qty", 0) or 0)),
            "tot_psbl_qty":  int(float(out.get("tot_psbl_qty", 0) or 0)),
            "lqd_psbl_qty1": int(float(out.get("lqd_psbl_qty1", 0) or 0)),
            "bass_idx":      float(out.get("bass_idx", 0) or 0),
        }
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------
# 주문 (TTTO1101U)
# ------------------------------------------------------------------
def order_futures(kis, shtn_code: str, qty: int, price: float,
                  side: str, cls: str,
                  market_order: bool = False) -> Optional[dict]:
    """
    선물 주문 (정규장).

    Args:
      shtn_code:    단축코드 (예: A01612)
      qty:          주문수량
      price:        지정가 (시장가일 때도 형식상 전송, 0 가능)
      side:         "02"=매수, "01"=매도
      cls:          "01"=신규, "02"=청산
      market_order: True면 시장가

    Returns:
      {
        "ok":        bool,
        "order_no":  str,    # ODNO
        "org_orgno": str,    # KRX_FWDG_ORD_ORGNO
        "msg":       str,
      }
    """
    kis._rate_limit_sleep()
    url = f"{kis.url_base}/uapi/domestic-futureoption/v1/trading/order"
    headers = _headers(kis, "TTTO1101U", post=True)

    body = {
        "ORD_PRCS_DVSN_CD":  "02",                       # 02 = 전송
        "CANO":              kis.cano,
        "ACNT_PRDT_CD":      kis.acnt_prdt_cd,
        "SLL_BUY_DVSN_CD":   side,
        "SHTN_PDNO":         shtn_code,
        "ORD_QTY":           str(int(qty)),
        "UNIT_PRICE":        f"{price:.2f}" if not market_order else "0",
        "NMPR_TYPE_CD":      NMPR_TYPE_MARKET if market_order else NMPR_TYPE_LIMIT,
        "KRX_NMPR_CNDT_CD":  "0",                         # 0=없음
        "CTAC_TLNO":         "",
        "FUOP_ITEM_DVSN_CD": "",
        "ORD_DVSN_CD":       ORD_DVSN_MARKET if market_order else ORD_DVSN_LIMIT,
    }
    res = _retry_request("POST", url, headers, json=body)
    if not res:
        return {"ok": False, "order_no": "", "org_orgno": "", "msg": "request_failed"}
    if res.get("rt_cd") != "0":
        return {"ok": False, "order_no": "", "org_orgno": "",
                "msg": f"{res.get('msg_cd','')}/{res.get('msg1','')}"}
    out = res.get("output") or {}
    return {
        "ok":         True,
        "order_no":   str(out.get("ODNO", "") or ""),
        "org_orgno":  str(out.get("KRX_FWDG_ORD_ORGNO", "") or ""),
        "msg":        str(res.get("msg1", "") or ""),
    }


# ------------------------------------------------------------------
# 미체결 조회 (TTTO5201R, CCLD_NCCS_DVSN='02')
# ------------------------------------------------------------------
def get_unfilled(kis) -> list:
    """미체결 주문 리스트"""
    kis._rate_limit_sleep()
    url = f"{kis.url_base}/uapi/domestic-futureoption/v1/trading/inquire-ccnl"
    headers = _headers(kis, "TTTO5201R")
    params = {
        "CANO":              kis.cano,
        "ACNT_PRDT_CD":      kis.acnt_prdt_cd,
        "STRT_ORD_DT":       "",
        "END_ORD_DT":        "",
        "SLL_BUY_DVSN_CD":   "00",   # 00=전체
        "CCLD_NCCS_DVSN":    "02",   # 02=미체결
        "SORT_SQN":          "DS",
        "STRT_ODNO":         "",
        "PDNO":              "",
        "MKET_ID_CD":        "",
        "CTX_AREA_FK200":    "",
        "CTX_AREA_NK200":    "",
    }
    res = _retry_request("GET", url, headers, params=params)
    if not res or res.get("rt_cd") != "0":
        return []
    rows = res.get("output1") or []
    out = []
    for r in rows:
        rem = int(float(r.get("nccs_qty", 0) or 0))
        if rem <= 0:
            continue
        out.append({
            "order_no":  str(r.get("odno", "") or ""),
            "org_orgno": str(r.get("ord_gno_brno", "") or ""),
            "symbol":    str(r.get("pdno", "") or ""),
            "side":      str(r.get("sll_buy_dvsn_cd", "") or ""),
            "qty":       int(float(r.get("ord_qty", 0) or 0)),
            "rem_qty":   rem,
            "price":     float(r.get("ord_unpr", 0) or 0),
        })
    return out


# ------------------------------------------------------------------
# 체결내역 조회 (TTTO5201R, CCLD_NCCS_DVSN='01')
# ------------------------------------------------------------------
def get_filled(kis, order_no: str = "") -> list:
    """
    당일 체결내역 조회.

    Args:
      order_no: 특정 주문번호로 필터 (빈 문자열이면 전체)

    Returns: [{order_no, symbol, side, ord_qty, ccld_qty, ccld_price}, ...]
    """
    kis._rate_limit_sleep()
    url = f"{kis.url_base}/uapi/domestic-futureoption/v1/trading/inquire-ccnl"
    headers = _headers(kis, "TTTO5201R")
    params = {
        "CANO":              kis.cano,
        "ACNT_PRDT_CD":      kis.acnt_prdt_cd,
        "STRT_ORD_DT":       "",
        "END_ORD_DT":        "",
        "SLL_BUY_DVSN_CD":   "00",   # 00=전체
        "CCLD_NCCS_DVSN":    "01",   # 01=체결
        "SORT_SQN":          "DS",
        "STRT_ODNO":         "",
        "PDNO":              "",
        "MKET_ID_CD":        "",
        "CTX_AREA_FK200":    "",
        "CTX_AREA_NK200":    "",
    }
    res = _retry_request("GET", url, headers, params=params)
    if not res or res.get("rt_cd") != "0":
        return []
    rows = res.get("output1") or []
    out = []
    for r in rows:
        odno = str(r.get("odno", "") or "")
        if order_no and odno != order_no:
            continue
        ccld = int(float(r.get("tot_ccld_qty", 0) or r.get("ccld_qty", 0) or 0))
        out.append({
            "order_no":   odno,
            "symbol":     str(r.get("shtn_pdno", "") or r.get("pdno", "") or ""),
            "side":       str(r.get("sll_buy_dvsn_cd", "") or ""),
            "ord_qty":    int(float(r.get("ord_qty", 0) or 0)),
            "ccld_qty":   ccld,
            "ccld_price": float(r.get("avg_idx", 0) or r.get("ccld_unpr", 0) or 0),
        })
    return out


# ------------------------------------------------------------------
# 주문취소 (TTTO1103U)
# ------------------------------------------------------------------
def cancel_order(kis, org_orgno: str, order_no: str, qty: int = 0) -> Optional[dict]:
    """
    주문 취소 (TTTO1103U).

    Args:
      org_orgno: (KIS 선물옵션 TR은 사용 안 함, 호환성 위해 남김)
      order_no:  원주문번호 (ORGN_ODNO)
      qty:       0이면 전량 취소
    """
    kis._rate_limit_sleep()
    url = f"{kis.url_base}/uapi/domestic-futureoption/v1/trading/order-rvsecncl"
    headers = _headers(kis, "TTTO1103U", post=True)

    body = {
        "ORD_PRCS_DVSN_CD":     "02",          # 02 = 전송
        "CANO":                 kis.cano,
        "ACNT_PRDT_CD":         kis.acnt_prdt_cd,
        "RVSE_CNCL_DVSN_CD":    "02",          # 02 = 취소 (01 = 정정)
        "ORGN_ODNO":            order_no,
        "ORD_QTY":              str(int(qty)),
        "UNIT_PRICE":           "0",
        "NMPR_TYPE_CD":         "01",
        "KRX_NMPR_CNDT_CD":     "0",
        "RMN_QTY_YN":           "Y" if qty == 0 else "N",  # Y=잔량전부, N=수량지정
        "ORD_DVSN_CD":          "01",
        "FUOP_ITEM_DVSN_CD":    "",
    }
    res = _retry_request("POST", url, headers, json=body)
    if not res:
        return {"ok": False, "msg": "request_failed"}
    return {
        "ok":  res.get("rt_cd") == "0",
        "msg": f"{res.get('msg_cd','')}/{res.get('msg1','')}",
    }


def cancel_all_unfilled(kis, log_fn=print) -> int:
    """미체결 전부 취소. Returns: 취소한 주문 수"""
    unfilled = get_unfilled(kis)
    cnt = 0
    for u in unfilled:
        r = cancel_order(kis, u["org_orgno"], u["order_no"], qty=0)
        if r and r.get("ok"):
            cnt += 1
            log_fn(f"  취소: {u['symbol']} {u['order_no']} (잔량 {u['rem_qty']})")
        else:
            log_fn(f"  취소실패: {u['order_no']} {r.get('msg') if r else 'no-response'}")
        time.sleep(0.2)
    return cnt
