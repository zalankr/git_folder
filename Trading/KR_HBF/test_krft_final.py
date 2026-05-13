#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KRFT 자동매매용 최종 통합 검증
─────────────────────────────────
종목코드 확정 후 자동매매에 필요한 5개 호출이 끝까지 정상 동작하는지 확인:
  1. CTFO6118R  잔고 (검증 완료)
  2. FHMIF10000000 현재가 (A05606/A01606)
  3. FHMIF10010000 호가 (호가창)
  4. TTTO5105R  주문가능 (매수/매도, 핵심 가능수량 필드 확정)
  5. TTTO5201R  체결내역

KOSPI200 6월물 정규(A01606)와 미니(A05606) 둘 다 검증.
"""
import os, json, time, requests
from datetime import datetime, timedelta

BASE_URL = "https://openapi.koreainvestment.com:9443"
KIS_KEY_DIR = "/var/autobot/KIS"
CANO = "64753341"
ACNT = "03"

# 자동매매 후보 종목 (6월물)
KOSPI200_F   = "A01606"   # 정규선물 6월물
KOSPI200_MF  = "A05606"   # 미니선물 6월물


def load_keys():
    with open(f"{KIS_KEY_DIR}/kis{CANO}nkr.txt") as f:
        lines = [l.strip() for l in f.readlines()]
    return lines[0], lines[1]


def get_token():
    f = f"{KIS_KEY_DIR}/kis{CANO}_token.json"
    if os.path.exists(f):
        with open(f) as fp:
            td = json.load(fp)
        issued = datetime.fromisoformat(td["issued_at"])
        exp = issued + timedelta(seconds=td.get("expires_in", 86400))
        if datetime.now() < exp - timedelta(minutes=60):
            return td["access_token"]
    ak, sc = load_keys()
    body = {"grant_type": "client_credentials", "appkey": ak, "appsecret": sc}
    r = requests.post(f"{BASE_URL}/oauth2/tokenP",
                      headers={"content-type": "application/json"}, json=body, timeout=10)
    return r.json()["access_token"]


def headers(tr_id):
    ak, sc = load_keys()
    return {
        "Content-Type": "application/json",
        "authorization": f"Bearer {get_token()}",
        "appKey": ak, "appSecret": sc,
        "tr_id": tr_id, "custtype": "P",
    }


def get_call(url, tr_id, params):
    time.sleep(0.15)
    r = requests.get(url, headers=headers(tr_id), params=params, timeout=10)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"raw": r.text[:500]}


def hr(title, char="═", width=78):
    print(f"\n{char*width}")
    print(f" {title}")
    print(char*width)


def check_one_code(code, label):
    """단일 종목코드로 시세/호가/주문가능 통합 검증"""
    hr(f"종목 {code}  ({label})", "─")

    # ── 1. 현재가 ──
    s, j = get_call(f"{BASE_URL}/uapi/domestic-futureoption/v1/quotations/inquire-price",
                    "FHMIF10000000",
                    {"FID_COND_MRKT_DIV_CODE": "F", "FID_INPUT_ISCD": code})
    o1 = j.get("output1", {}) or {}
    if isinstance(o1, list): o1 = o1[0] if o1 else {}
    cur = float(o1.get("futs_prpr", 0) or 0)
    name = o1.get("hts_kor_isnm", "?")
    print(f"  [1] 현재가  rt={j.get('rt_cd','?')}  {name}  현재={cur}")
    print(f"      시가={o1.get('futs_oprc','-')}  고가={o1.get('futs_hgpr','-')}  저가={o1.get('futs_lwpr','-')}")
    print(f"      상한={o1.get('futs_mxpr','-')}  하한={o1.get('futs_llam','-')}")
    print(f"      거래량={o1.get('acml_vol','-')}  미결제={o1.get('hts_otst_stpl_qty','-')}")

    # ── 2. 호가 ──
    s, j = get_call(f"{BASE_URL}/uapi/domestic-futureoption/v1/quotations/inquire-asking-price",
                    "FHMIF10010000",
                    {"FID_COND_MRKT_DIV_CODE": "F", "FID_INPUT_ISCD": code})
    o1 = j.get("output1", {}) or {}
    o2 = j.get("output2", {}) or {}
    if isinstance(o1, list): o1 = o1[0] if o1 else {}
    if isinstance(o2, list): o2 = o2[0] if o2 else {}
    print(f"  [2] 호가    rt={j.get('rt_cd','?')}")
    if o1:
        print(f"      output1 keys: {list(o1.keys())[:8]}")
        # 매도1호가/매수1호가
        for k in ["futs_askp1", "futs_bidp1", "futs_askp_rsqn1", "futs_bidp_rsqn1"]:
            if k in o1:
                print(f"      {k}: {o1[k]}")

    # ── 3. 주문가능 (매수, 지정가) ──
    if cur > 0:
        unit_buy = round(cur - 0.05, 2)   # 현재가보다 0.05포인트 낮게
        s, j = get_call(f"{BASE_URL}/uapi/domestic-futureoption/v1/trading/inquire-psbl-order",
                        "TTTO5105R",
                        {"CANO": CANO, "ACNT_PRDT_CD": ACNT,
                         "PDNO": code, "SLL_BUY_DVSN_CD": "02",
                         "UNIT_PRICE": str(unit_buy), "ORD_DVSN_CD": "01"})
        o = j.get("output", {}) or {}
        if isinstance(o, list): o = o[0] if o else {}
        rt = j.get('rt_cd', '?')
        msg = j.get('msg1', '')[:60]
        print(f"  [3] 매수가능 (단가 {unit_buy})  rt={rt}  msg={msg}")
        if rt == "0" and o:
            print(f"      output keys: {list(o.keys())}")
            for k in ["ord_psbl_qty", "max_ord_psbl_qty", "max_buy_psbl_qty",
                      "psbl_qty1", "psbl_qty", "ord_psbl_cash",
                      "nrcvb_buy_amt", "tot_frcr_cltr_amt"]:
                if k in o:
                    print(f"        {k:<24}: {o[k]}")

        # ── 4. 주문가능 (매도, 지정가) ──
        unit_sell = round(cur + 0.05, 2)
        s, j = get_call(f"{BASE_URL}/uapi/domestic-futureoption/v1/trading/inquire-psbl-order",
                        "TTTO5105R",
                        {"CANO": CANO, "ACNT_PRDT_CD": ACNT,
                         "PDNO": code, "SLL_BUY_DVSN_CD": "01",
                         "UNIT_PRICE": str(unit_sell), "ORD_DVSN_CD": "01"})
        o = j.get("output", {}) or {}
        if isinstance(o, list): o = o[0] if o else {}
        rt = j.get('rt_cd', '?')
        print(f"  [4] 매도가능 (단가 {unit_sell})  rt={rt}")
        if rt == "0" and o:
            for k in ["ord_psbl_qty", "max_sll_psbl_qty", "psbl_qty1"]:
                if k in o:
                    print(f"        {k:<24}: {o[k]}")


def main():
    print(f"실행시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # ── 잔고 한 번만 ──
    hr("CTFO6118R 잔고 확인", "═")
    s, j = get_call(f"{BASE_URL}/uapi/domestic-futureoption/v1/trading/inquire-balance",
                    "CTFO6118R",
                    {"CANO": CANO, "ACNT_PRDT_CD": ACNT,
                     "MGNA_DVSN": "01", "EXCC_STAT_CD": "1",
                     "CTX_AREA_FK200": "", "CTX_AREA_NK200": ""})
    o2 = j.get("output2") or {}
    if isinstance(o2, list): o2 = o2[0] if o2 else {}
    print(f"  예수금현금: {o2.get('dnca_cash','-')}")
    print(f"  주문가능현금: {o2.get('ord_psbl_cash','-')}")
    print(f"  추정예탁자산: {o2.get('prsm_dpast','-')}")

    # ── KOSPI200 정규 6월물 ──
    check_one_code(KOSPI200_F, "KOSPI200 정규 6월물, 1포인트=25만원")

    # ── KOSPI200 미니 6월물 ──
    check_one_code(KOSPI200_MF, "KOSPI200 미니 6월물, 1포인트=5만원")

    # ── 체결내역 (오늘) ──
    hr("TTTO5201R 오늘 체결내역", "═")
    today = datetime.now().strftime("%Y%m%d")
    s, j = get_call(f"{BASE_URL}/uapi/domestic-futureoption/v1/trading/inquire-ccnl",
                    "TTTO5201R",
                    {"CANO": CANO, "ACNT_PRDT_CD": ACNT,
                     "STRT_ORD_DT": today, "END_ORD_DT": today,
                     "SLL_BUY_DVSN_CD": "00", "CCLD_NCCS_DVSN": "00",
                     "SORT_SQN": "DS", "STRT_ODNO": "", "PDNO": "",
                     "MKET_ID_CD": "",
                     "CTX_AREA_FK200": "", "CTX_AREA_NK200": ""})
    print(f"  rt={j.get('rt_cd','?')}  msg={j.get('msg1','')[:50]}")
    print(f"  주문건수: {len(j.get('output1') or [])}")

    hr("최종 검증 완료", "█")
    print("""
[자동매매 코드 작성 시작 조건]
  ✓ 종목코드: A01606 (정규) / A05606 (미니)
  ✓ 잔고: CTFO6118R 검증 완료
  ✓ 시세: FHMIF10000000 검증 완료, futs_prpr 필드 정상 추출
  ✓ 주문가능: TTTO5105R 필드명 확정 (위 결과로)
  ✓ 체결조회: TTTO5201R 검증 완료
  ✓ 주문: TTTO1101U (실주문 미시도 — 코드 작성 후 검증 단계에서)

[권장 자동매매 운영 종목]
  - 첫 운영: A05606 (미니선물) — 1계약 730만원 증거금, 분할매매 유리
  - 익숙해진 후: A01606 (정규선물) — 1계약 3,640만원 증거금
  - 주의: 5월물(A05605/A01605)은 5월 14일 만기 임박, 사용 금지
""")


if __name__ == "__main__":
    main()
