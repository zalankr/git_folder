#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
선물 자동매매용 TR-id 사전 검증 스크립트 (무거래 확인)
─────────────────────────────────────────────────────
목적
  - daily_snapshot.py에서 검증된 선물 잔고 TR-id 외에, 자동매매에 필요한
    주문/주문가능/체결/현재가 TR-id의 응답 구조를 실제 호출로 확인한다.
  - 매수/매도/청산 전(주문 송신 없이) 안전하게 응답 키와 필수 파라미터를
    출력해, 본 매매 코드 작성 시 오류 없이 그대로 사용할 수 있게 한다.

검증 범위 (전부 GET 또는 무위험 호출. 실제 주문 송신 0건)
  국내선물옵션(KRFT, acnt_prdt_cd="03")
    1) CTFO6118R   잔고                    (daily_snapshot 검증 완료, 재확인)
    2) FHMIF10000000 현재가                  → 단축종목코드 자동 조회
    3) TTTO5105R   주문가능조회              → 주문가능수량, 증거금 확인
    4) TTTO5201R   주문체결내역(체결+미체결)
  해외선물옵션(GBFT, acnt_prdt_cd="08")
    1) OTFM1412R   미결제잔고                (daily_snapshot 검증 완료)
    2) OTFM1411R   예수금                    (daily_snapshot 검증 완료)
    3) HHDFC55010000 현재가                  → SRS_CD로 조회
    4) OTFM3304R   주문가능조회              → 가능수량/증거금
    5) OTFM3120R   당일 미체결 주문
    6) OTFM3122R   당일 체결내역

선물 종목 자동 선정
  - 보유 포지션이 있으면 그 종목 사용 (현재 자동매매 운영 종목)
  - 없으면 안전한 기본값:
      KRFT: KOSPI200 미니선물 최근월물 (105 시리즈) — 1계약 ≈ 25만원
      GBFT: Micro E-mini S&P 500 (MES) 최근월물 — 1계약 ≈ $1,000
    실제 주문 송신은 절대 하지 않음. 가능 수량/증거금만 조회.

사용법
  python3 test_futures_api.py
  python3 test_futures_api.py --cano 64753341
  python3 test_futures_api.py --krft-only
  python3 test_futures_api.py --gbft-only
  python3 test_futures_api.py --krft-pdno 101W09  # 특정 종목 강제 지정
  python3 test_futures_api.py --gbft-pdno 6EU25
"""
import os
import sys
import json
import time
import argparse
from datetime import datetime, timedelta

import requests


# ══════════════════════════════════════════════════
#  설정 (daily_snapshot.py와 동일 경로/규칙)
# ══════════════════════════════════════════════════
BASE_URL    = "https://openapi.koreainvestment.com:9443"
KIS_KEY_DIR = "/var/autobot/KIS"
API_SLEEP   = 0.12
DEFAULT_CANO = "64753341"   # 선물옵션 계좌 (daily_snapshot.py 참조)


# ══════════════════════════════════════════════════
#  인증 (daily_snapshot.py와 동일한 패턴)
# ══════════════════════════════════════════════════
_token_cache = {}

def load_kis_keys(cano: str) -> tuple:
    path = f"{KIS_KEY_DIR}/kis{cano}nkr.txt"
    if cano == "43680827":
        path = f"{KIS_KEY_DIR}/kis{cano}lys.txt"
    with open(path) as f:
        lines = [l.strip() for l in f.readlines()]
    return lines[0], lines[1]


def get_kis_token(cano: str) -> tuple:
    if cano in _token_cache:
        c = _token_cache[cano]
        return c["token"], c["appkey"], c["secret"]
    app_key, app_secret = load_kis_keys(cano)
    token_file = f"{KIS_KEY_DIR}/kis{cano}_token.json"
    if os.path.exists(token_file):
        try:
            with open(token_file) as f:
                td = json.load(f)
            issued = datetime.fromisoformat(td["issued_at"])
            exp = issued + timedelta(seconds=td.get("expires_in", 86400))
            if datetime.now() < exp - timedelta(minutes=60):
                _token_cache[cano] = {"token": td["access_token"],
                                      "appkey": app_key, "secret": app_secret}
                return td["access_token"], app_key, app_secret
        except Exception:
            pass
    body = {"grant_type": "client_credentials",
            "appkey": app_key, "appsecret": app_secret}
    r = requests.post(f"{BASE_URL}/oauth2/tokenP",
                      headers={"content-type": "application/json"},
                      json=body, timeout=10)
    r.raise_for_status()
    data = r.json()
    td = {"access_token": data["access_token"],
          "issued_at": datetime.now().isoformat(),
          "expires_in": data.get("expires_in", 86400)}
    with open(token_file, "w") as f:
        json.dump(td, f, indent=2)
    _token_cache[cano] = {"token": td["access_token"],
                          "appkey": app_key, "secret": app_secret}
    return td["access_token"], app_key, app_secret


def kis_headers(cano: str, tr_id: str) -> dict:
    tok, ak, sc = get_kis_token(cano)
    return {
        "Content-Type": "application/json",
        "authorization": f"Bearer {tok}",
        "appKey": ak,
        "appSecret": sc,
        "tr_id": tr_id,
        "custtype": "P",
    }


# ══════════════════════════════════════════════════
#  공통 출력 도우미
# ══════════════════════════════════════════════════
def hr(title: str = "", char: str = "─", width: int = 70):
    if title:
        pad = (width - len(title) - 2) // 2
        print(f"\n{char*pad} {title} {char*pad}")
    else:
        print(char * width)


def pretty(d, max_keys: int = 0):
    """dict/list 정렬 출력. max_keys>0이면 key 수 제한."""
    if isinstance(d, dict):
        if max_keys and len(d) > max_keys:
            keys = list(d.keys())[:max_keys]
            d = {k: d[k] for k in keys}
            d["__truncated__"] = f"(+{len(d)} more keys)"
        print(json.dumps(d, ensure_ascii=False, indent=2))
    elif isinstance(d, list):
        if not d:
            print("[] (empty)")
        else:
            print(f"[list of {len(d)} items]")
            for i, x in enumerate(d[:3]):
                print(f"--- item[{i}] ---")
                pretty(x, max_keys)
            if len(d) > 3:
                print(f"... (+{len(d)-3} more)")
    else:
        print(repr(d))


def check_rt(resp_json: dict, label: str) -> bool:
    rt = resp_json.get("rt_cd", "?")
    msg_cd = resp_json.get("msg_cd", "")
    msg1 = (resp_json.get("msg1", "") or "").strip()
    if rt == "0":
        print(f"  [OK]   {label}  msg_cd={msg_cd}  {msg1}")
        return True
    else:
        print(f"  [FAIL] {label}  rt_cd={rt} msg_cd={msg_cd}  {msg1}")
        return False


# ══════════════════════════════════════════════════
#  국내선물(KRFT) 검증
# ══════════════════════════════════════════════════
def krft_inquire_balance(cano: str, acnt_prdt_cd: str = "03") -> dict:
    """잔고 조회 (CTFO6118R) — 보유종목 1개만 빨리 확보용 간단 버전"""
    url = f"{BASE_URL}/uapi/domestic-futureoption/v1/trading/inquire-balance"
    params = {
        "CANO": cano, "ACNT_PRDT_CD": acnt_prdt_cd,
        "MGNA_DVSN": "01", "EXCC_STAT_CD": "1",
        "CTX_AREA_FK200": "", "CTX_AREA_NK200": "",
    }
    h = kis_headers(cano, "CTFO6118R")
    time.sleep(API_SLEEP)
    r = requests.get(url, headers=h, params=params, timeout=10)
    return r.json() if r.status_code == 200 else {"rt_cd": "1", "msg1": f"HTTP {r.status_code}"}


def krft_inquire_price(shtn_pdno: str) -> dict:
    """현재가 (FHMIF10000000) — 인증 헤더만 필요, 계좌 불필요"""
    url = f"{BASE_URL}/uapi/domestic-futureoption/v1/quotations/inquire-price"
    # 헤더의 cano는 토큰용. tr_id가 시세계열이라 cano와 무관.
    h = kis_headers(DEFAULT_CANO, "FHMIF10000000")
    params = {
        "FID_COND_MRKT_DIV_CODE": "F",   # F=지수선물, O=지수옵션
        "FID_INPUT_ISCD": shtn_pdno,     # 예: 101W09
    }
    time.sleep(API_SLEEP)
    r = requests.get(url, headers=h, params=params, timeout=10)
    return r.json() if r.status_code == 200 else {"rt_cd": "1", "msg1": f"HTTP {r.status_code}"}


def krft_inquire_psbl_order(cano: str, acnt_prdt_cd: str, pdno: str,
                            sll_buy: str, unit_price: str,
                            ord_dvsn_cd: str = "01") -> dict:
    """
    주문가능조회 (TTTO5105R) — GET 메서드, 응답 output에 가능수량/증거금
    sll_buy: 01=매도, 02=매수
    unit_price: 지정가 (시장가는 0)
    ord_dvsn_cd: 01=지정가, 02=시장가
    """
    url = f"{BASE_URL}/uapi/domestic-futureoption/v1/trading/inquire-psbl-order"
    h = kis_headers(cano, "TTTO5105R")
    params = {
        "CANO": cano, "ACNT_PRDT_CD": acnt_prdt_cd,
        "PDNO": pdno,
        "SLL_BUY_DVSN_CD": sll_buy,
        "UNIT_PRICE": str(unit_price),
        "ORD_DVSN_CD": ord_dvsn_cd,
    }
    time.sleep(API_SLEEP)
    r = requests.get(url, headers=h, params=params, timeout=10)
    return r.json() if r.status_code == 200 else {"rt_cd": "1", "msg1": f"HTTP {r.status_code}"}


def krft_inquire_ccnl(cano: str, acnt_prdt_cd: str) -> dict:
    """오늘자 주문체결내역 (TTTO5201R) — 미체결+체결 모두"""
    url = f"{BASE_URL}/uapi/domestic-futureoption/v1/trading/inquire-ccnl"
    h = kis_headers(cano, "TTTO5201R")
    today = datetime.now().strftime("%Y%m%d")
    params = {
        "CANO": cano, "ACNT_PRDT_CD": acnt_prdt_cd,
        "STRT_ORD_DT": today, "END_ORD_DT": today,
        "SLL_BUY_DVSN_CD": "00",       # 00=전체
        "CCLD_NCCS_DVSN": "00",        # 00=전체
        "SORT_SQN": "DS",              # DS=정순, AS=역순
        "STRT_ODNO": "", "PDNO": "",
        "MKET_ID_CD": "",
        "CTX_AREA_FK200": "", "CTX_AREA_NK200": "",
    }
    time.sleep(API_SLEEP)
    r = requests.get(url, headers=h, params=params, timeout=10)
    return r.json() if r.status_code == 200 else {"rt_cd": "1", "msg1": f"HTTP {r.status_code}"}


def find_krft_default_pdno(cano: str, acnt_prdt_cd: str) -> str:
    """
    검증용 KRFT 단축종목코드 자동 선정.
    보유 포지션 있으면 그 종목, 없으면 KOSPI200 미니선물 시리즈 추정.
    KOSPI200 선물 코드 규칙: 101 + 월코드 + 종목구분
      예) 101W09 = KOSPI200 정규월물 (W는 2024.12 만기 등 시기별 변동)
    실거래 환경에서는 보유 포지션이 가장 안전한 검증 대상.
    """
    bal = krft_inquire_balance(cano, acnt_prdt_cd)
    if bal.get("rt_cd") == "0":
        for s in (bal.get("output1") or []):
            qty = float(s.get("cblc_qty", 0) or 0)
            if qty > 0:
                code = s.get("shtn_pdno") or s.get("pdno") or ""
                if code:
                    print(f"  → 보유 종목 자동 선정: {code} ({s.get('prdt_name','')})  잔고={qty}")
                    return code
    print("  → 보유 포지션 없음. 검증 종목을 명시적으로 지정해야 함 (--krft-pdno).")
    return ""


def run_krft_checks(cano: str, acnt_prdt_cd: str, forced_pdno: str = ""):
    hr("KRFT 국내선물옵션 검증", "═")

    # ── 1. 잔고 ──────────────────────────────────────
    hr("1) CTFO6118R  잔고조회", "─")
    bal = krft_inquire_balance(cano, acnt_prdt_cd)
    check_rt(bal, "CTFO6118R")
    out1 = bal.get("output1") or []
    out2 = bal.get("output2") or {}
    if isinstance(out2, list):
        out2 = out2[0] if out2 else {}
    print(f"  보유 포지션 건수: {len([s for s in out1 if float(s.get('cblc_qty',0) or 0) > 0])}")
    if out2:
        print(f"  예수금현금(dnca_cash):       {out2.get('dnca_cash','-')}")
        print(f"  주문가능현금(ord_psbl_cash): {out2.get('ord_psbl_cash','-')}")
        print(f"  추정예탁자산(prsm_dpast):    {out2.get('prsm_dpast','-')}")

    # ── 2. 검증할 단축종목코드 결정 ────────────────
    hr("2) 검증 종목 선정", "─")
    pdno = forced_pdno or find_krft_default_pdno(cano, acnt_prdt_cd)
    if not pdno:
        print("  ⚠ 종목 미지정. KRFT 시세/주문가능 검증 SKIP.")
        print("     → --krft-pdno 101W09 형태로 지정 후 재실행")
        return

    # ── 3. 현재가 ───────────────────────────────────
    hr(f"3) FHMIF10000000 현재가 ({pdno})", "─")
    px = krft_inquire_price(pdno)
    check_rt(px, "FHMIF10000000")
    o1 = px.get("output1") or {}
    o2 = px.get("output2") or {}
    if isinstance(o1, list): o1 = o1[0] if o1 else {}
    if isinstance(o2, list): o2 = o2[0] if o2 else {}
    cur_px = o1.get("futs_prpr") or o1.get("stck_prpr") or o2.get("futs_prpr")
    print(f"  현재가(futs_prpr): {cur_px}")
    print(f"  전일대비(prdy_vrss): {o1.get('prdy_vrss','-')}")
    print(f"  거래량(acml_vol):    {o1.get('acml_vol','-')}")
    if not cur_px or float(cur_px) == 0:
        print("  ⚠ 현재가 0/없음. 장 외 시간일 가능성. 검증은 진행.")

    # ── 4. 주문가능조회 (매수) ────────────────────
    hr(f"4) TTTO5105R 주문가능 (매수, {pdno})", "─")
    # 지정가가 0이면 거절될 수 있어 현재가의 0.5% 아래로 셋업 (실주문 아님, 단순 조회)
    try:
        unit_buy = max(0.05, float(cur_px or 0) * 0.995)
        unit_buy = round(unit_buy, 2)
    except Exception:
        unit_buy = 0
    psbl_buy = krft_inquire_psbl_order(cano, acnt_prdt_cd, pdno, "02", str(unit_buy), "01")
    check_rt(psbl_buy, "TTTO5105R (BUY)")
    o = psbl_buy.get("output") or {}
    if isinstance(o, list): o = o[0] if o else {}
    if o:
        print("  주요 응답 필드:")
        for k in ["ord_psbl_qty", "max_ord_psbl_qty", "max_buy_psbl_qty",
                  "max_sll_psbl_qty", "nrcvb_buy_amt", "ord_psbl_cash",
                  "tot_frcr_cltr_amt", "psbl_qty1", "psbl_qty"]:
            if k in o:
                print(f"    {k:<24}: {o[k]}")
        print("\n  [전체 output keys]")
        print(f"    {list(o.keys())}")

    # ── 5. 주문가능조회 (매도) ────────────────────
    hr(f"5) TTTO5105R 주문가능 (매도, {pdno})", "─")
    try:
        unit_sell = float(cur_px or 0) * 1.005
        unit_sell = round(unit_sell, 2)
    except Exception:
        unit_sell = 0
    psbl_sell = krft_inquire_psbl_order(cano, acnt_prdt_cd, pdno, "01", str(unit_sell), "01")
    check_rt(psbl_sell, "TTTO5105R (SELL)")
    o = psbl_sell.get("output") or {}
    if isinstance(o, list): o = o[0] if o else {}
    if o:
        for k in ["ord_psbl_qty", "max_sll_psbl_qty", "psbl_qty1"]:
            if k in o:
                print(f"    {k:<24}: {o[k]}")

    # ── 6. 체결내역 ────────────────────────────────
    hr("6) TTTO5201R 오늘자 체결/미체결", "─")
    ccnl = krft_inquire_ccnl(cano, acnt_prdt_cd)
    check_rt(ccnl, "TTTO5201R")
    out1 = ccnl.get("output1") or []
    out2 = ccnl.get("output2") or {}
    if isinstance(out2, list): out2 = out2[0] if out2 else {}
    print(f"  주문건수: {len(out1)}")
    if out1:
        print("  최근 주문 1건 keys:")
        print(f"    {list(out1[0].keys())}")
    if out2:
        print(f"  합계 output2 keys: {list(out2.keys())[:10]}...")


# ══════════════════════════════════════════════════
#  해외선물(GBFT) 검증
# ══════════════════════════════════════════════════
def gbft_inquire_unpd(cano: str, acnt_prdt_cd: str = "08") -> dict:
    """미결제잔고 (OTFM1412R)"""
    url = f"{BASE_URL}/uapi/overseas-futureoption/v1/trading/inquire-unpd"
    h = kis_headers(cano, "OTFM1412R")
    params = {
        "CANO": cano, "ACNT_PRDT_CD": acnt_prdt_cd,
        "FUOP_DVSN": "00",
        "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
    }
    time.sleep(API_SLEEP)
    r = requests.get(url, headers=h, params=params, timeout=10)
    return r.json() if r.status_code == 200 else {"rt_cd": "1", "msg1": f"HTTP {r.status_code}"}


def gbft_inquire_deposit(cano: str, acnt_prdt_cd: str, crcy: str = "USD") -> dict:
    """예수금 (OTFM1411R)"""
    url = f"{BASE_URL}/uapi/overseas-futureoption/v1/trading/inquire-deposit"
    h = kis_headers(cano, "OTFM1411R")
    params = {
        "CANO": cano, "ACNT_PRDT_CD": acnt_prdt_cd,
        "CRCY_CD": crcy,
        "INQR_DT": datetime.now().strftime("%Y%m%d"),
    }
    time.sleep(API_SLEEP)
    r = requests.get(url, headers=h, params=params, timeout=10)
    return r.json() if r.status_code == 200 else {"rt_cd": "1", "msg1": f"HTTP {r.status_code}"}


def gbft_inquire_price(srs_cd: str) -> dict:
    """현재가 (HHDFC55010000)"""
    url = f"{BASE_URL}/uapi/overseas-futureoption/v1/quotations/inquire-price"
    h = kis_headers(DEFAULT_CANO, "HHDFC55010000")
    params = {"SRS_CD": srs_cd}
    time.sleep(API_SLEEP)
    r = requests.get(url, headers=h, params=params, timeout=10)
    return r.json() if r.status_code == 200 else {"rt_cd": "1", "msg1": f"HTTP {r.status_code}"}


def gbft_inquire_psamount(cano: str, acnt_prdt_cd: str,
                          srs_cd: str, sll_buy: str,
                          fm_ord_pric: str = "") -> dict:
    """
    주문가능수량 (OTFM3304R)
    sll_buy: 01=매도, 02=매수
    fm_ord_pric: 빈문자열이면 시장가 기준
    """
    url = f"{BASE_URL}/uapi/overseas-futureoption/v1/trading/inquire-psamount"
    h = kis_headers(cano, "OTFM3304R")
    params = {
        "CANO": cano, "ACNT_PRDT_CD": acnt_prdt_cd,
        "OVRS_FUTR_FX_PDNO": srs_cd,
        "SLL_BUY_DVSN_CD": sll_buy,
        "FM_ORD_PRIC": fm_ord_pric,
        "ECIS_RSVN_ORD_YN": "N",
    }
    time.sleep(API_SLEEP)
    r = requests.get(url, headers=h, params=params, timeout=10)
    return r.json() if r.status_code == 200 else {"rt_cd": "1", "msg1": f"HTTP {r.status_code}"}


def gbft_inquire_daily_order(cano: str, acnt_prdt_cd: str) -> dict:
    """당일 미체결주문 (OTFM3120R)"""
    url = f"{BASE_URL}/uapi/overseas-futureoption/v1/trading/inquire-daily-order"
    h = kis_headers(cano, "OTFM3120R")
    today = datetime.now().strftime("%Y%m%d")
    params = {
        "CANO": cano, "ACNT_PRDT_CD": acnt_prdt_cd,
        "STRT_DT": today, "END_DT": today,
        "FM_PDGR_CD": "", "CCLD_NCCS_DVSN": "02",   # 02=미체결
        "SLL_BUY_DVSN_CD": "00",
        "FUOP_DVSN_CD": "00",
        "FM_KRX_FWRD_ORD_ORGN_NO": "",
        "FM_ODNO": "",
        "CTX_AREA_FK200": "", "CTX_AREA_NK200": "",
    }
    time.sleep(API_SLEEP)
    r = requests.get(url, headers=h, params=params, timeout=10)
    return r.json() if r.status_code == 200 else {"rt_cd": "1", "msg1": f"HTTP {r.status_code}"}


def gbft_inquire_daily_ccld(cano: str, acnt_prdt_cd: str) -> dict:
    """당일 체결내역 (OTFM3122R)"""
    url = f"{BASE_URL}/uapi/overseas-futureoption/v1/trading/inquire-daily-ccld"
    h = kis_headers(cano, "OTFM3122R")
    today = datetime.now().strftime("%Y%m%d")
    params = {
        "CANO": cano, "ACNT_PRDT_CD": acnt_prdt_cd,
        "STRT_DT": today, "END_DT": today,
        "FM_PDGR_CD": "", "CCLD_NCCS_DVSN": "01",   # 01=체결
        "SLL_BUY_DVSN_CD": "00",
        "FUOP_DVSN_CD": "00",
        "FM_KRX_FWRD_ORD_ORGN_NO": "",
        "FM_ODNO": "",
        "CTX_AREA_FK200": "", "CTX_AREA_NK200": "",
    }
    time.sleep(API_SLEEP)
    r = requests.get(url, headers=h, params=params, timeout=10)
    return r.json() if r.status_code == 200 else {"rt_cd": "1", "msg1": f"HTTP {r.status_code}"}


def find_gbft_default_pdno(cano: str, acnt_prdt_cd: str) -> str:
    """보유 포지션 있으면 그 종목, 없으면 빈문자열 반환."""
    bal = gbft_inquire_unpd(cano, acnt_prdt_cd)
    if bal.get("rt_cd") == "0":
        out = bal.get("output") or []
        if isinstance(out, dict):
            out = [out]
        for s in out:
            qty = float(s.get("cblc_qty", 0) or s.get("ccld_qty", 0) or 0)
            if qty > 0:
                code = s.get("ovrs_futr_fx_pdno", "") or s.get("pdno", "")
                if code:
                    print(f"  → 보유 종목 자동 선정: {code} ({s.get('prdt_name','')})  잔고={qty}")
                    return code
    print("  → 보유 포지션 없음. 검증 종목을 명시적으로 지정해야 함 (--gbft-pdno).")
    return ""


def run_gbft_checks(cano: str, acnt_prdt_cd: str, forced_pdno: str = ""):
    hr("GBFT 해외선물옵션 검증", "═")

    # ── 1. 미결제잔고 ───────────────────────────────
    hr("1) OTFM1412R 미결제잔고", "─")
    unpd = gbft_inquire_unpd(cano, acnt_prdt_cd)
    check_rt(unpd, "OTFM1412R")
    out = unpd.get("output") or []
    if isinstance(out, dict): out = [out]
    pos_cnt = sum(1 for s in out
                  if float(s.get("cblc_qty", 0) or s.get("ccld_qty", 0) or 0) > 0)
    print(f"  미결제 포지션 건수: {pos_cnt}")
    if out and pos_cnt > 0:
        print(f"  첫 포지션 keys: {list(out[0].keys())[:12]}...")

    # ── 2. 예수금 (USD/KRW/TUS) ─────────────────────
    hr("2) OTFM1411R 예수금 (USD/KRW/TUS)", "─")
    for crcy in ["USD", "KRW", "TUS"]:
        dep = gbft_inquire_deposit(cano, acnt_prdt_cd, crcy)
        ok = check_rt(dep, f"OTFM1411R [{crcy}]")
        if ok:
            o = dep.get("output") or {}
            if isinstance(o, list): o = o[0] if o else {}
            for k in ["fm_dnca_rmnd", "fm_ord_psbl_amt", "fm_tot_asst_evlu_amt",
                      "fm_drwg_psbl_amt", "fm_brkg_mgn_amt"]:
                if k in o:
                    print(f"    {crcy} {k:<24}: {o[k]}")

    # ── 3. 검증할 종목 결정 ────────────────────────
    hr("3) 검증 종목 선정", "─")
    srs = forced_pdno or find_gbft_default_pdno(cano, acnt_prdt_cd)
    if not srs:
        print("  ⚠ 종목 미지정. GBFT 시세/주문가능 검증 SKIP.")
        print("     → --gbft-pdno 6EU25 등으로 지정 후 재실행")
        print("     (예: 6EU25=Euro FX 2025-9월물, MESU25=Micro E-mini S&P 9월물)")
        return

    # ── 4. 현재가 ───────────────────────────────────
    hr(f"4) HHDFC55010000 현재가 ({srs})", "─")
    px = gbft_inquire_price(srs)
    check_rt(px, "HHDFC55010000")
    o1 = px.get("output1") or {}
    if isinstance(o1, list): o1 = o1[0] if o1 else {}
    cur_px = o1.get("last_pric") or o1.get("now_pric") or o1.get("stat_pric")
    print(f"  현재가(last_pric):  {cur_px}")
    print(f"  전일종가(prev_pric): {o1.get('prev_pric','-')}")
    print(f"  거래량(tot_vol):     {o1.get('tot_vol','-')}")
    print(f"  [keys] {list(o1.keys())[:15]}...")

    # ── 5. 주문가능조회 (매수) ───────────────────
    hr(f"5) OTFM3304R 주문가능 (매수, {srs})", "─")
    psbl_buy = gbft_inquire_psamount(cano, acnt_prdt_cd, srs, "02",
                                     fm_ord_pric=str(cur_px or ""))
    check_rt(psbl_buy, "OTFM3304R (BUY)")
    o = psbl_buy.get("output") or {}
    if isinstance(o, list): o = o[0] if o else {}
    if o:
        print("  주요 응답 필드:")
        for k in ["fm_new_ord_psbl_qty", "fm_lqd_ord_psbl_qty",
                  "fm_ord_psbl_qty", "fm_psbl_qty",
                  "fm_ord_psbl_amt", "fm_new_mgn_amt", "fm_mgn_amt"]:
            if k in o:
                print(f"    {k:<26}: {o[k]}")
        print(f"\n  [전체 output keys]")
        print(f"    {list(o.keys())}")

    # ── 6. 주문가능조회 (매도) ───────────────────
    hr(f"6) OTFM3304R 주문가능 (매도, {srs})", "─")
    psbl_sell = gbft_inquire_psamount(cano, acnt_prdt_cd, srs, "01",
                                      fm_ord_pric=str(cur_px or ""))
    check_rt(psbl_sell, "OTFM3304R (SELL)")
    o = psbl_sell.get("output") or {}
    if isinstance(o, list): o = o[0] if o else {}
    if o:
        for k in ["fm_new_ord_psbl_qty", "fm_lqd_ord_psbl_qty",
                  "fm_ord_psbl_qty", "fm_psbl_qty"]:
            if k in o:
                print(f"    {k:<26}: {o[k]}")

    # ── 7. 당일 미체결 ─────────────────────────────
    hr("7) OTFM3120R 당일 미체결주문", "─")
    nccs = gbft_inquire_daily_order(cano, acnt_prdt_cd)
    check_rt(nccs, "OTFM3120R")
    out = nccs.get("output1") or nccs.get("output") or []
    if isinstance(out, dict): out = [out]
    print(f"  미체결 건수: {len(out)}")
    if out:
        print(f"  첫 건 keys: {list(out[0].keys())[:12]}...")

    # ── 8. 당일 체결내역 ───────────────────────────
    hr("8) OTFM3122R 당일 체결내역", "─")
    ccld = gbft_inquire_daily_ccld(cano, acnt_prdt_cd)
    check_rt(ccld, "OTFM3122R")
    out = ccld.get("output1") or ccld.get("output") or []
    if isinstance(out, dict): out = [out]
    print(f"  체결 건수: {len(out)}")
    if out:
        print(f"  첫 건 keys: {list(out[0].keys())[:12]}...")


# ══════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser(description="선물 자동매매용 TR-id 사전 검증 (무거래)")
    ap.add_argument("--cano", default=DEFAULT_CANO, help=f"종합계좌번호 8자리 (기본 {DEFAULT_CANO})")
    ap.add_argument("--krft-only", action="store_true", help="국내선물만 검증")
    ap.add_argument("--gbft-only", action="store_true", help="해외선물만 검증")
    ap.add_argument("--krft-pdno", default="", help="국내선물 단축종목코드 강제 지정 (예: 101W09)")
    ap.add_argument("--gbft-pdno", default="", help="해외선물 종목코드 강제 지정 (예: 6EU25, MESU25)")
    args = ap.parse_args()

    hr(f"KIS 선물 API 검증  CANO={args.cano}  실거래 0건", "█")
    print(f"BASE_URL    : {BASE_URL}")
    print(f"실행 시각   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 토큰 확인
    try:
        tok, ak, _ = get_kis_token(args.cano)
        print(f"토큰 OK     : {tok[:20]}... (appKey={ak[:10]}...)")
    except Exception as e:
        print(f"\n[FATAL] 토큰/키 로드 실패: {e}")
        sys.exit(1)

    if not args.gbft_only:
        run_krft_checks(args.cano, "03", args.krft_pdno)

    if not args.krft_only:
        run_gbft_checks(args.cano, "08", args.gbft_pdno)

    hr("검증 완료", "█")
    print("""
[다음 단계 가이드]
  ✓ 잔고/예수금 조회 OK → daily_snapshot.py와 동일 키 사용 가능
  ✓ 현재가 OK            → 시세 기반 한도/지정가 산출 가능
  ✓ 주문가능 OK          → 가능수량 필드명 확정, 자동매매 코드의
                            "주문수량 = min(전략수량, 가능수량)" 처리 가능
  ✓ 미체결/체결 OK       → 분할매수 라운드 사이 진행상황 추적 가능

  실제 주문 검증이 필요하다면(가장 변동성 작은 1계약 권장):
    KRFT: 코스피200 미니선물(105 시리즈) 또는 옵션 1계약 (~10만원 증거금)
    GBFT: Micro E-mini S&P 500 (MES) 1계약 (~$1,000 증거금)
  이 스크립트는 의도적으로 주문 송신을 포함하지 않습니다.
  실주문 검증 코드는 본 검증 결과를 받고 별도로 만들어드립니다.
""")


if __name__ == "__main__":
    main()
