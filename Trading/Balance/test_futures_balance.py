#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
KIS 선물계좌 잔고/예수금 조회 테스트 스크립트
================================================================================

목적
  기존 daily_snapshot.py 의 국내·해외 선물 잔고 조회 코드를
  KIS 공식 GitHub(koreainvestment/open-trading-api) 의 최신 사양에 맞춰
  완전히 다시 작성하여 단독 실행 가능한 테스트 코드로 분리.

발견된 버그 요약 (기존 daily_snapshot.py 대비)
  ┌─────────────────────────────────────────────────────────────────────────┐
  │ [국내선물 CTFO6118R]                                                     │
  │   ✗ STTL_STTS_CD ("00") → 존재하지 않는 필드                             │
  │   ✗ EXCC_UNPR_DVSN ("01") → 존재하지 않는 필드                           │
  │   ✓ 정확한 필수: EXCC_STAT_CD = "1"(정산) 또는 "2"(본정산)              │
  │   → 에러 "정산상태코드은(는) 필수입력 항목입니다" 의 직접 원인           │
  ├─────────────────────────────────────────────────────────────────────────┤
  │ [해외선물 OTFM3118R / OTFM3114R - 기존 코드]                            │
  │   ✗ TR_ID와 URL이 서로 잘못 짝지어짐                                     │
  │   ✗ inquire-unpd-brkg-prft-amt → 존재하지 않는 엔드포인트               │
  │   ✓ 정확:                                                                │
  │       OTFM1412R → /inquire-unpd      (미결제잔고)                       │
  │       OTFM1411R → /inquire-deposit   (예수금현황, 외화별)               │
  │       OTFM3115R → /margin-detail     (증거금상세, 보조)                 │
  └─────────────────────────────────────────────────────────────────────────┘

사용법 (EC2 운영 디렉토리에 그대로 복사)
  $ python3 test_futures_balance.py            # 모든 테스트 실행
  $ python3 test_futures_balance.py KRFT       # 국내선물만
  $ python3 test_futures_balance.py GBFT       # 해외선물만
  $ python3 test_futures_balance.py raw        # 원시 응답 JSON 까지 출력

전제
  /var/autobot/KIS/kis64753341nkr.txt          (appkey/secret)
  /var/autobot/KIS/kis64753341_token.json      (access_token 캐시)
"""

from __future__ import annotations
import os, sys, json, time
from datetime import datetime, timedelta
from typing import Tuple
import requests


# ══════════════════════════════════════════════════
# 환경 / 상수
# ══════════════════════════════════════════════════
BASE_URL    = "https://openapi.koreainvestment.com:9443"
KIS_KEY_DIR = "/var/autobot/KIS"
API_SLEEP   = 0.12        # KIS rate-limit 회피 (~8/sec)
MAX_PAGE    = 30
HTTP_TIMEOUT= 10

# 선물계좌 (사용자 환경)
FUTURES_CANO       = "64753341"
KRFT_ACNT_PRDT_CD  = "03"     # 국내선물옵션
GBFT_ACNT_PRDT_CD  = "08"     # 해외선물옵션


# ══════════════════════════════════════════════════
# 인증 (daily_snapshot.py 와 동일 토큰 캐시 공유)
# ══════════════════════════════════════════════════
def load_kis_keys(cano: str) -> Tuple[str, str]:
    path = f"{KIS_KEY_DIR}/kis{cano}nkr.txt"
    with open(path) as f:
        lines = [l.strip() for l in f.readlines()]
    return lines[0], lines[1]


def get_kis_token(cano: str) -> Tuple[str, str, str]:
    app_key, app_secret = load_kis_keys(cano)
    token_file = f"{KIS_KEY_DIR}/kis{cano}_token.json"

    # 캐시 확인 (만료 60분 전까지 유효)
    if os.path.exists(token_file):
        try:
            with open(token_file) as f:
                td = json.load(f)
            issued = datetime.fromisoformat(td["issued_at"])
            exp = issued + timedelta(seconds=td.get("expires_in", 86400))
            if datetime.now() < exp - timedelta(minutes=60):
                return td["access_token"], app_key, app_secret
        except Exception:
            pass

    # 신규 발급
    body = {"grant_type": "client_credentials",
            "appkey": app_key, "appsecret": app_secret}
    r = requests.post(f"{BASE_URL}/oauth2/tokenP",
                      headers={"content-type": "application/json"},
                      json=body, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    td = {"access_token": data["access_token"],
          "issued_at": datetime.now().isoformat(),
          "expires_in": data.get("expires_in", 86400)}
    with open(token_file, "w") as f:
        json.dump(td, f, indent=2)
    return td["access_token"], app_key, app_secret


def kis_headers(cano: str, tr_id: str, tr_cont: str = "") -> dict:
    tok, ak, sc = get_kis_token(cano)
    h = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {tok}",
        "appKey": ak,
        "appSecret": sc,
        "tr_id": tr_id,
        "custtype": "P",
    }
    if tr_cont:
        h["tr_cont"] = tr_cont
    return h


# ══════════════════════════════════════════════════
# [1] 국내선물 잔고조회 — CTFO6118R
# ──────────────────────────────────────────────────
#   URL : /uapi/domestic-futureoption/v1/trading/inquire-balance
#   필수 파라미터 (KIS 공식):
#     CANO            : 종합계좌번호
#     ACNT_PRDT_CD    : 03
#     MGNA_DVSN       : 증거금 구분  ("01"=개시, "02"=유지)
#     EXCC_STAT_CD    : 정산상태코드 ("1"=정산, "2"=본정산)   ← 필수, 1자리
#     CTX_AREA_FK200, CTX_AREA_NK200 : 연속조회용
#
#   ※ 기존 코드의 STTL_STTS_CD / EXCC_UNPR_DVSN 은 모두 잘못된 필드명/값
#
#   응답 (output2 주요 필드 - 예수금/증거금/평가):
#     dnca_tot_amt        : 예수금총액
#     thdt_dnca           : 당일예수금
#     prsm_dpast          : 추정예탁자산금액
#     tot_evlu_amt        : 총평가금액
#     tot_pftrt           : 총수익률
#     ord_psbl_cash       : 주문가능현금
# ══════════════════════════════════════════════════
def fetch_krft_balance(cano: str, acnt_prdt_cd: str,
                        mgna_dvsn: str = "01",
                        excc_stat_cd: str = "1",
                        verbose: bool = False) -> dict:
    url = f"{BASE_URL}/uapi/domestic-futureoption/v1/trading/inquire-balance"
    params = {
        "CANO": cano,
        "ACNT_PRDT_CD": acnt_prdt_cd,
        "MGNA_DVSN":   mgna_dvsn,        # 01=개시증거금, 02=유지증거금
        "EXCC_STAT_CD": excc_stat_cd,    # 1=정산, 2=본정산  (필수, 1자리!)
        "CTX_AREA_FK200": "",
        "CTX_AREA_NK200": "",
    }

    stocks = []
    out2_acc = {}
    tr_cont_req = ""
    page = 0
    raw_responses = []

    while True:
        h = kis_headers(cano, "CTFO6118R", tr_cont_req)
        time.sleep(API_SLEEP)
        r = requests.get(url, headers=h, params=params, timeout=HTTP_TIMEOUT)

        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}: {r.text[:200]}"}

        data = r.json()
        raw_responses.append(data)
        if data.get("rt_cd") != "0":
            return {"error": f"{data.get('msg_cd','?')} - {data.get('msg1','국내선물 API 오류')}",
                    "raw": data}

        # output1: 미결제 포지션 리스트
        for s in data.get("output1", []) or []:
            qty = float(s.get("cblc_qty", 0) or 0)
            if qty == 0:
                continue
            stocks.append({
                "code":         s.get("pdno", "") or s.get("shtn_pdno", ""),
                "name":         s.get("prdt_name", ""),
                "qty":          qty,
                "side":         s.get("sll_buy_dvsn_cd", ""),  # 01=매도, 02=매수
                "avg_price":    float(s.get("pchs_avg_pric", 0) or 0),
                "cur_price":    float(s.get("idx_clpr", 0) or 0) or float(s.get("ccld_avg_unpr1", 0) or 0),
                "eval_amt":     float(s.get("evlu_amt", 0) or 0),
                "evlu_pfls":    float(s.get("evlu_pfls_amt", 0) or 0),
                "evlu_pfls_rt": float(s.get("evlu_pfls_rt", 0) or 0),
            })

        # output2: 계좌요약 (1건, 단일객체)
        out2 = data.get("output2") or []
        d2 = out2[0] if isinstance(out2, list) and out2 else (out2 if isinstance(out2, dict) else {})
        if d2:
            out2_acc.update(d2)   # 페이지 진행되더라도 마지막 값으로 갱신

        # 페이지 종료 판단
        page += 1
        resp_tr_cont = (r.headers.get("tr_cont", "") or "").strip()
        if page >= MAX_PAGE:
            break
        if resp_tr_cont in ("D", "E", "F", ""):    # 마지막 페이지
            break
        fk = (data.get("ctx_area_fk200") or "").strip()
        nk = (data.get("ctx_area_nk200") or "").strip()
        if not fk or not nk:
            break
        params["CTX_AREA_FK200"] = fk
        params["CTX_AREA_NK200"] = nk
        tr_cont_req = "N"

    # ── 핵심 금액 추출 (output2) ──
    # ※ 실 응답 raw로 확인된 KIS 국내선물(CTFO6118R) output2 필드:
    #   dnca_cash         : 예수금(현금)         ← 실제 예수금
    #   dnca_sbst         : 예수금(대용)
    #   tot_dncl_amt      : 총예탁금액(현금+대용 합계)
    #   nxdy_dnca         : 익일예수금
    #   nxdy_dncl_amt     : 익일예탁금액
    #   ord_psbl_cash     : 주문가능현금
    #   ord_psbl_tota     : 주문가능총액
    #   wdrw_psbl_tot_amt : 인출가능총액
    #   prsm_dpast        : 추정예탁자산 (= 총평가금액)
    #   prsm_dpast_amt    : 추정예탁자산금액 (보조)
    #   evlu_amt_smtl     : 평가금액합계 (미결제포지션 평가)
    #   evlu_pfls_amt_smtl: 평가손익합계
    #   futr_evlu_pfls_amt: 선물평가손익
    #   opt_evlu_pfls_amt : 옵션평가손익
    def _f(*keys):
        """주어진 키들을 순회하며 0이 아닌 첫 값을 반환."""
        for k in keys:
            v = out2_acc.get(k)
            if v is None or v == "":
                continue
            try:
                fv = float(v)
                if fv != 0:
                    return fv
            except (TypeError, ValueError):
                continue
        return 0.0

    deposit       = _f("dnca_cash", "tot_dncl_amt")            # 예수금(현금) 우선
    deposit_sbst  = _f("dnca_sbst")                             # 대용
    today_deposit = _f("nxdy_dnca", "nxdy_dncl_amt")            # 익일예수금
    total_eval    = _f("prsm_dpast", "prsm_dpast_amt")          # 추정예탁자산 = 총평가
    ord_psbl_cash = _f("ord_psbl_cash", "ord_psbl_tota")        # 주문가능현금
    wdrw_psbl     = _f("wdrw_psbl_tot_amt")                     # 인출가능총액
    pos_eval      = _f("evlu_amt_smtl")                         # 미결제포지션평가
    pos_pl        = _f("evlu_pfls_amt_smtl",
                       "futr_evlu_pfls_amt", "opt_evlu_pfls_amt")  # 평가손익

    stock_eval    = sum(s["eval_amt"] for s in stocks) or pos_eval

    # 안전 합계: 추정예탁자산이 비어있으면 (예수금+대용 + 포지션평가)
    total = total_eval if total_eval > 0 else (deposit + deposit_sbst + stock_eval)

    result = {
        "stocks":        stocks,
        "stock_eval":    stock_eval,
        "deposit":       deposit,         # 예수금현금 (= cash)
        "deposit_sbst":  deposit_sbst,    # 예수금대용
        "today_deposit": today_deposit,
        "ord_psbl_cash": ord_psbl_cash,   # 실제 주문가능 현금
        "wdrw_psbl":     wdrw_psbl,       # 인출가능총액
        "total_eval":    total_eval,      # 추정예탁자산
        "total":         total,
        "pos_pl":        pos_pl,
        "currency":      "KRW",
    }
    if verbose:
        result["_raw_pages"] = raw_responses
        result["_output2_keys"] = sorted(out2_acc.keys())
        # 모든 output2 값을 (필드: 값) 형태로 같이 보존 (디버그용)
        result["_output2_values"] = {k: out2_acc.get(k) for k in sorted(out2_acc.keys())}
    return result


# ══════════════════════════════════════════════════
# [2] 해외선물 미결제잔고 — OTFM1412R
# ──────────────────────────────────────────────────
#   URL : /uapi/overseas-futureoption/v1/trading/inquire-unpd
#   필수: CANO, ACNT_PRDT_CD, FUOP_DVSN(00=전체/01=선물/02=옵션),
#         CTX_AREA_FK100, CTX_AREA_NK100
# ══════════════════════════════════════════════════
def fetch_gbft_positions(cano: str, acnt_prdt_cd: str,
                          fuop_dvsn: str = "00",
                          verbose: bool = False) -> dict:
    url = f"{BASE_URL}/uapi/overseas-futureoption/v1/trading/inquire-unpd"
    params = {
        "CANO": cano,
        "ACNT_PRDT_CD": acnt_prdt_cd,
        "FUOP_DVSN": fuop_dvsn,
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": "",
    }

    stocks = []
    tr_cont_req = ""
    page = 0
    raw_responses = []

    while True:
        h = kis_headers(cano, "OTFM1412R", tr_cont_req)
        time.sleep(API_SLEEP)
        r = requests.get(url, headers=h, params=params, timeout=HTTP_TIMEOUT)

        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}: {r.text[:200]}",
                    "stocks": [], "stock_eval": 0.0}

        data = r.json()
        raw_responses.append(data)
        if data.get("rt_cd") != "0":
            return {"error": f"{data.get('msg_cd','?')} - {data.get('msg1','해외선물 미결제 API 오류')}",
                    "stocks": [], "stock_eval": 0.0, "raw": data}

        # output: 미결제 포지션 (배열 또는 단일객체로 반환될 수 있음)
        out = data.get("output", [])
        if isinstance(out, dict):
            out = [out]
        for s in out or []:
            qty = float(s.get("cblc_qty", 0) or s.get("ccld_qty", 0) or 0)
            if qty == 0:
                continue
            stocks.append({
                "code":          s.get("ovrs_futr_fx_pdno", "") or s.get("pdno", ""),
                "name":          s.get("prdt_name", ""),
                "qty":           qty,
                "side":          s.get("sll_buy_dvsn_cd", ""),       # 01=매도, 02=매수
                "avg_price":     float(s.get("pchs_avg_pric", 0) or 0),
                "cur_price":     float(s.get("now_pric", 0) or s.get("idx_clpr", 0) or 0),
                "eval_amt":      float(s.get("frcr_evlu_amt", 0) or s.get("evlu_amt", 0) or 0),
                "evlu_pfls_amt": float(s.get("evlu_pfls_amt", 0) or 0),
                "currency":      s.get("crcy_cd", "USD"),
            })

        page += 1
        resp_tr_cont = (r.headers.get("tr_cont", "") or "").strip()
        if page >= MAX_PAGE:
            break
        if resp_tr_cont in ("D", "E", "F", ""):
            break
        fk = (data.get("ctx_area_fk100") or "").strip()
        nk = (data.get("ctx_area_nk100") or "").strip()
        if not fk or not nk:
            break
        params["CTX_AREA_FK100"] = fk
        params["CTX_AREA_NK100"] = nk
        tr_cont_req = "N"

    stock_eval = sum(s["eval_amt"] for s in stocks)
    result = {"stocks": stocks, "stock_eval": stock_eval}
    if verbose:
        result["_raw_pages"] = raw_responses
    return result


# ══════════════════════════════════════════════════
# [3] 해외선물 예수금현황 — OTFM1411R
# ──────────────────────────────────────────────────
#   URL : /uapi/overseas-futureoption/v1/trading/inquire-deposit
#   필수: CANO, ACNT_PRDT_CD, CRCY_CD, INQR_DT
#     CRCY_CD : "TUS"=총USD, "TKR"=총KRW, "USD"/"EUR"/"HKD"/"CNY"/"JPY"/"VND" 등
#   응답 (output, 단일객체):
#     frcr_dncl_amt1     : 외화예수금
#     frcr_use_pasl_amt  : 외화사용가능 (=주문가능)
#     frcr_evlu_amt      : 외화평가금
#     frst_bltn_exrt     : 최초고시환율
#     frcr_pchs_amt      : 외화매입금액 등
# ══════════════════════════════════════════════════
def fetch_gbft_deposit(cano: str, acnt_prdt_cd: str,
                        crcy_cd: str = "USD",
                        inqr_dt: str = "",
                        verbose: bool = False) -> dict:
    if not inqr_dt:
        inqr_dt = datetime.now().strftime("%Y%m%d")

    url = f"{BASE_URL}/uapi/overseas-futureoption/v1/trading/inquire-deposit"
    params = {
        "CANO": cano,
        "ACNT_PRDT_CD": acnt_prdt_cd,
        "CRCY_CD": crcy_cd,
        "INQR_DT": inqr_dt,
    }
    h = kis_headers(cano, "OTFM1411R")
    time.sleep(API_SLEEP)
    r = requests.get(url, headers=h, params=params, timeout=HTTP_TIMEOUT)

    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}: {r.text[:200]}",
                "currency": crcy_cd, "deposit": 0.0}

    data = r.json()
    if data.get("rt_cd") != "0":
        return {"error": f"{data.get('msg_cd','?')} - {data.get('msg1','해외선물 예수금 API 오류')}",
                "currency": crcy_cd, "deposit": 0.0, "raw": data}

    out = data.get("output", {}) or {}
    if isinstance(out, list):
        out = out[0] if out else {}

    def _f(*keys):
        for k in keys:
            v = out.get(k)
            if v in (None, ""):
                continue
            try:
                fv = float(v)
                if fv != 0:
                    return fv
            except (TypeError, ValueError):
                continue
        return 0.0

    # ※ 실 응답 raw로 확인된 KIS 해외선물(OTFM1411R) output 필드 (모두 fm_ 접두사):
    #   fm_dnca_rmnd            : 예수금잔액           ← 실제 예수금
    #   fm_nxdy_dncl_amt        : 익일예수금잔액
    #   fm_drwg_psbl_amt        : 인출가능액
    #   fm_drwg_prar_amt        : 인출예정금액
    #   fm_ord_psbl_amt         : 주문가능액           ← 실제 주문가능
    #   fm_tot_asst_evlu_amt    : 총자산평가금액
    #   fm_fuop_evlu_pfls_amt   : 선물옵션평가손익
    #   fm_brkg_mgn_amt         : 위탁증거금
    #   fm_mntn_mgn_amt         : 유지증거금
    #   fm_add_mgn_amt          : 추가증거금
    #   fm_echm_rqrm_amt        : 교환요구금액
    #   fm_lqd_pfls_amt         : 청산손익금액
    #   fm_opt_evlu_amt         : 옵션평가금액
    #   fm_opt_icld_asst_evlu_amt: 옵션포함자산평가
    #   fm_crcy_sbst_amt        : 외화대용금액
    #   fm_risk_rt              : 위험도
    #   fm_fee, fm_opt_tr_chgs  : 수수료
    result = {
        "currency":      crcy_cd,
        "deposit":       _f("fm_dnca_rmnd"),                      # 예수금잔액
        "next_deposit":  _f("fm_nxdy_dncl_amt"),                  # 익일예수금
        "ord_avail":     _f("fm_ord_psbl_amt"),                   # 주문가능액
        "drwg_avail":    _f("fm_drwg_psbl_amt"),                  # 인출가능
        "tot_asst":      _f("fm_tot_asst_evlu_amt"),              # 총자산평가
        "fuop_pl":       _f("fm_fuop_evlu_pfls_amt"),             # 선물옵션평가손익
        "mgn_brkg":      _f("fm_brkg_mgn_amt"),                   # 위탁증거금
        "risk_rt":       _f("fm_risk_rt"),                        # 위험도
        "exrt":          0.0,                                      # 환율은 이 응답에 없음
        "inqr_dt":       inqr_dt,
        "raw_keys":      sorted(out.keys()) if verbose else None,
    }
    if verbose:
        result["_raw"] = data
        result["_raw_values"] = {k: out.get(k) for k in sorted(out.keys())}
    return result


# ══════════════════════════════════════════════════
# 출력 헬퍼
# ══════════════════════════════════════════════════
def _fmt_krw(v): return f"₩{v:,.0f}"
def _fmt_usd(v): return f"${v:,.2f}"


def print_krft_report(res: dict):
    print("─" * 72)
    print("【KRFT - 국내선물옵션】 CTFO6118R")
    print("─" * 72)
    if "error" in res:
        print(f"  ❌ ERROR: {res['error']}")
        return

    print(f"  예수금(현금)    : {_fmt_krw(res['deposit'])}")
    print(f"  예수금(대용)    : {_fmt_krw(res['deposit_sbst'])}")
    print(f"  익일예수금      : {_fmt_krw(res['today_deposit'])}")
    print(f"  주문가능현금    : {_fmt_krw(res['ord_psbl_cash'])}")
    print(f"  인출가능총액    : {_fmt_krw(res['wdrw_psbl'])}")
    print(f"  미결제 평가금   : {_fmt_krw(res['stock_eval'])}")
    print(f"  추정예탁자산    : {_fmt_krw(res['total_eval'])}")
    print(f"  선/옵 평가손익  : {_fmt_krw(res['pos_pl'])}")
    print(f"  ─ 합계(추정)    : {_fmt_krw(res['total'])}")

    if res["stocks"]:
        print(f"\n  미결제 포지션 ({len(res['stocks'])}건):")
        for s in res["stocks"]:
            side = {"01":"매도", "02":"매수"}.get(s["side"], s["side"] or "-")
            print(f"    {s['code']:>10} {s['name'][:14]:<14} {side} {s['qty']:>5.0f}계약 "
                  f"평균 {s['avg_price']:>10,.2f}  평가 {_fmt_krw(s['eval_amt'])}  "
                  f"({s['evlu_pfls_rt']:+.2f}%)")
    else:
        print("\n  미결제 포지션 없음")

    # raw verbose: 0이 아닌 모든 응답 값 출력
    if "_output2_values" in res:
        print("\n  [output2 0이 아닌 모든 응답값]")
        for k, v in res["_output2_values"].items():
            try:
                fv = float(v)
                if fv != 0:
                    print(f"    {k:24} = {v}")
            except (TypeError, ValueError):
                if v not in (None, "", "0"):
                    print(f"    {k:24} = {v}")


def print_gbft_report(pos: dict, deps: list):
    print("─" * 72)
    print("【GBFT - 해외선물옵션】 OTFM1412R(잔고) + OTFM1411R(예수금)")
    print("─" * 72)

    # 예수금
    print("  [통화별 예수금/주문가능]")
    print(f"    {'통화':<5} {'예수금':>14}  {'주문가능':>14}  {'총자산평가':>14}  {'위험도':>8}")
    for d in deps:
        if "error" in d:
            print(f"    {d.get('currency','?'):<5}: ❌ {d['error']}")
            continue
        print(f"    {d['currency']:<5} {d['deposit']:>14,.2f}  "
              f"{d['ord_avail']:>14,.2f}  "
              f"{d['tot_asst']:>14,.2f}  "
              f"{d['risk_rt']:>7,.2f}%")

    # 미결제 포지션
    if "error" in pos:
        print(f"\n  포지션 조회 ❌: {pos['error']}")
    elif pos["stocks"]:
        print(f"\n  미결제 포지션 ({len(pos['stocks'])}건):")
        for s in pos["stocks"]:
            side = {"01":"매도", "02":"매수"}.get(s["side"], s["side"] or "-")
            print(f"    {s['code']:>10} {s['name'][:18]:<18} {side} {s['qty']:>5.0f}계약 "
                  f"평균 {s['avg_price']:>10,.4f}  평가 {s['eval_amt']:>12,.2f} {s['currency']}")
    else:
        print("\n  미결제 포지션 없음")

    # raw verbose: 통화별로 0이 아닌 모든 응답 값 출력
    for d in deps:
        if "_raw_values" in d:
            nz = {k: v for k, v in d["_raw_values"].items()
                  if v not in (None, "", "0", "0.00")
                  and (k.startswith("fm_") or k in ("crcy_cd", "resp_dt"))}
            if nz:
                print(f"\n  [예수금({d['currency']}) 0이 아닌 모든 응답값]")
                for k, v in nz.items():
                    print(f"    {k:28} = {v}")


# ══════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════
def main():
    args = sys.argv[1:]
    target = "ALL"
    verbose = False
    for a in args:
        if a.upper() in ("KRFT", "GBFT", "ALL"):
            target = a.upper()
        elif a.lower() in ("raw", "verbose", "-v"):
            verbose = True

    print(f"\n{'='*72}")
    print(f"  KIS 선물계좌 잔고/예수금 테스트   계좌: {FUTURES_CANO}")
    print(f"  실행시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}   target={target}")
    print(f"{'='*72}\n")

    # ── 토큰 사전 발급 (오류 빨리 잡기용) ──
    try:
        get_kis_token(FUTURES_CANO)
    except Exception as e:
        print(f"❌ 토큰 발급 실패: {e}")
        sys.exit(1)

    # ── KRFT ──
    if target in ("ALL", "KRFT"):
        try:
            res = fetch_krft_balance(FUTURES_CANO, KRFT_ACNT_PRDT_CD,
                                      mgna_dvsn="01", excc_stat_cd="1",
                                      verbose=verbose)
            print_krft_report(res)
            if verbose and "_output2_keys" in res:
                print(f"\n  [output2 전체 응답 필드 목록]\n    {res['_output2_keys']}")
        except Exception as e:
            print(f"❌ KRFT 예외: {type(e).__name__}: {e}")
        print()

    # ── GBFT ──
    if target in ("ALL", "GBFT"):
        try:
            pos = fetch_gbft_positions(FUTURES_CANO, GBFT_ACNT_PRDT_CD,
                                        fuop_dvsn="00", verbose=verbose)
            # 통화별 예수금: TUS(총USD환산), USD, KRW 모두 시도
            deps = []
            for ccy in ("TUS", "USD", "KRW"):
                d = fetch_gbft_deposit(FUTURES_CANO, GBFT_ACNT_PRDT_CD,
                                        crcy_cd=ccy, verbose=verbose)
                deps.append(d)
            print_gbft_report(pos, deps)

            if verbose and pos.get("_raw_pages"):
                first = pos["_raw_pages"][0]
                if first.get("output"):
                    sample = first["output"][0] if isinstance(first["output"], list) else first["output"]
                    if sample:
                        print(f"\n  [GBFT 미결제 raw output 키 샘플]\n    {sorted(sample.keys())}")
        except Exception as e:
            print(f"❌ GBFT 예외: {type(e).__name__}: {e}")
        print()

    print("=" * 72)
    print("테스트 완료. 정상 출력되면 daily_snapshot.py 의 fetch_krft_balance /")
    print("fetch_gbft_balance 함수를 이 코드의 함수로 교체하면 됩니다.")
    print("=" * 72)


if __name__ == "__main__":
    main()
