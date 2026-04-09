"""
Balance_63604155.py  (FIXED)
============================
63604155 계좌 4통화 일별 잔고 스냅샷

수정사항 (vs 원본):
  1) get_krw_balance: nass_amt가 마지막 페이지에서만 의미 있음 → 0이 아닐 때만 갱신
  2) get_overseas_balance: CTRP6504R 페이지네이션 추가
     (CTX_AREA_FK200/NK200 + tr_cont 헤더, KIS_JP.py 검증 패턴)
  3) get_overseas_balance: output3.tot_asst_amt 도 마지막 페이지에서만 갱신
  4) 종목수 무제한 안전 (MAX_PAGE=30 → 600종목까지)

KRW  → KRQT (한국주식)
USD  → USAA (USLA + HAA)
JPY  → JPQT (일본주식)
HKD  → HKQT (홍콩주식)

스케줄 (crontab, UTC):
  0 23 * * 1-5  → KST 08:00 평일: USD 잔고
  0  8 * * 1-5  → KST 17:00 평일: KRW / JPY / HKD 잔고

사용:
  python3 Balance_63604155.py US
  python3 Balance_63604155.py ASIA
"""

import sys
import os
import json
import time
import requests
from datetime import datetime, timedelta

sys.path.insert(0, "/var/autobot")
import telegram_alert as TA

# ══════════════════════════════════════════════════
#  설정
# ══════════════════════════════════════════════════

CANO = "63604155"
ACNT_PRDT_CD = "01"
KEY_FILE   = "/var/autobot/KIS/kis63604155nkr.txt"
TOKEN_FILE = "/var/autobot/KIS/kis63604155_token.json"
BASE_URL   = "https://openapi.koreainvestment.com:9443"

USAA_TR_PATH  = "/var/autobot/TR_USAA/USAA_TR.json"
SNAPSHOT_DIR  = "/var/autobot/Balance"
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

MAX_PAGE = 30   # 페이지네이션 안전장치 (해외 50종목/페이지 × 30 = 1500종목)

# ══════════════════════════════════════════════════
#  인증
# ══════════════════════════════════════════════════

def load_keys():
    with open(KEY_FILE) as f:
        return [l.strip() for l in f.readlines()]

APP_KEY, APP_SECRET = load_keys()


def get_token() -> str:
    """토큰 캐시 로드 또는 재발급"""
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            td = json.load(f)
        issued = datetime.fromisoformat(td["issued_at"])
        exp = issued + timedelta(seconds=td.get("expires_in", 86400))
        if datetime.now() < exp - timedelta(minutes=60):
            return td["access_token"]

    body = {"grant_type": "client_credentials",
            "appkey": APP_KEY, "appsecret": APP_SECRET}
    r = requests.post(f"{BASE_URL}/oauth2/tokenP",
                      headers={"content-type": "application/json"},
                      json=body, timeout=10)
    r.raise_for_status()
    data = r.json()
    td = {"access_token": data["access_token"],
          "issued_at": datetime.now().isoformat(),
          "expires_in": data.get("expires_in", 86400)}
    with open(TOKEN_FILE, "w") as f:
        json.dump(td, f, indent=2)
    return td["access_token"]

ACCESS_TOKEN = get_token()


def headers(tr_id: str) -> dict:
    return {
        "Content-Type": "application/json",
        "authorization": f"Bearer {ACCESS_TOKEN}",
        "appKey": APP_KEY,
        "appSecret": APP_SECRET,
        "tr_id": tr_id,
        "custtype": "P"
    }


# ══════════════════════════════════════════════════
#  KRW 잔고 (TTTC8434R - 국내주식 잔고)
# ══════════════════════════════════════════════════

def get_krw_balance() -> dict:
    """
    한국주식 잔고 조회 (페이지네이션 + nass_amt 마지막 페이지 보존)

    필드:
      - nass_amt   : 순자산금액 = 주식평가금 + D+2 정산현금 (마지막 페이지에서만 유효)
      - evlu_amt   : 종목별 평가금액 (output1, 모든 페이지 누적)
      - cash       : nass_amt - stock_eval (D+2 정산 포함 현금, 파생값)
    """
    url = f"{BASE_URL}/uapi/domestic-stock/v1/trading/inquire-balance"
    h = headers("TTTC8434R")
    params = {
        "CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD,
        "AFHR_FLPR_YN": "N", "OFL_YN": "", "INQR_DVSN": "00",
        "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N",
        "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00",
        "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""
    }

    stock_eval = 0.0
    total = 0.0       # nass_amt (마지막 페이지에서만 갱신)
    stocks = []
    tr_cont_req = ""
    page_count = 0

    try:
        while True:
            h["tr_cont"] = tr_cont_req
            time.sleep(0.12)
            r = requests.get(url, headers=h, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            resp_tr_cont = r.headers.get("tr_cont", "").strip()

            if data.get("rt_cd") != "0":
                return {"error": data.get("msg1", "API 오류")}

            # output1: 종목별 평가금 누적 (모든 페이지)
            for s in data.get("output1", []):
                qty = int(s.get("hldg_qty", 0))
                if qty == 0:
                    continue
                evl = float(s.get("evlu_amt", 0) or 0)
                stock_eval += evl
                stocks.append({
                    "code": s.get("pdno", ""),
                    "name": s.get("prdt_name", ""),
                    "qty": qty,
                    "eval_amt": evl,
                    "price": int(float(s.get("prpr", 0) or 0)),
                    "profit_rate": float(s.get("evlu_pfls_rt", 0) or 0)
                })

            # output2: nass_amt 는 마지막 페이지에서만 의미 있음 → 0이 아닐 때만 갱신
            out2 = data.get("output2", [{}])
            summary = out2[0] if out2 else {}
            nass_page = float(summary.get("nass_amt", 0) or 0)
            if nass_page > 0:
                total = nass_page

            page_count += 1
            if page_count >= MAX_PAGE:
                break
            # 연속조회 종료 판정 (D/E/F = 마지막)
            if resp_tr_cont in ("D", "E", "F"):
                break

            FK = data.get("ctx_area_fk100", "").strip()
            NK = data.get("ctx_area_nk100", "").strip()
            if not FK or not NK:
                break
            params["CTX_AREA_FK100"] = FK
            params["CTX_AREA_NK100"] = NK
            tr_cont_req = "N"

    except Exception as e:
        return {"error": f"KRW 조회 예외: {e}"}

    cash = total - stock_eval

    # 참고용: 미수없는 매수가능금액(TTTC8908R) 도 함께 조회 → cross-check
    nrcvb = get_krw_orderable()

    return {
        "currency": "KRW",
        "label": "KRQT",
        "stock_eval": stock_eval,
        "cash": cash,                   # nass_amt - 주식평가금 (D+2 정산 포함 순현금)
        "nrcvb_buy_amt": nrcvb,         # 미수없는 매수가능금액 (참조용)
        "total": total,                 # nass_amt (순자산)
        "stocks": stocks
    }


def get_krw_orderable() -> float:
    """국내 미수없는 매수가능금액 (TTTC8908R) — 참조용"""
    try:
        url = f"{BASE_URL}/uapi/domestic-stock/v1/trading/inquire-psbl-order"
        h = headers("TTTC8908R")
        params = {
            "CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD,
            "PDNO": "005930", "ORD_UNPR": "0",
            "ORD_DVSN": "01",            # 시장가
            "CMA_EVLU_AMT_ICLD_YN": "N",
            "OVRS_ICLD_YN": "N"
        }
        time.sleep(0.12)
        r = requests.get(url, headers=h, params=params, timeout=10)
        r.raise_for_status()
        d = r.json()
        if d.get("rt_cd") == "0":
            return float(d.get("output", {}).get("nrcvb_buy_amt", 0) or 0)
    except Exception:
        pass
    return 0.0


# ══════════════════════════════════════════════════
#  해외 잔고 (CTRP6504R + 페이지네이션) + TTTS3007R
# ══════════════════════════════════════════════════

def get_overseas_balance(natn_cd: str, currency: str,
                         excg_order: str, item_cd: str,
                         price: str = "100") -> dict:
    """
    해외 주식 잔고 (체결기준현재잔고 CTRP6504R, 페이지네이션 적용)
    + 주문가능금액 (TTTS3007R, ovrs_ord_psbl_amt)

    natn_cd:    840=미국, 392=일본, 344=홍콩
    excg_order: NASD(미국), TKSE(일본), SEHK(홍콩) — TTTS3007R용
    item_cd:    대표종목 (조회용, 금액은 종목 무관)

    필드 검증:
      - ccld_qty_smtl1   : 체결수량합계 (당일 체결 포함, 당일 매수/매도 정확)
      - frcr_evlu_amt2   : 외화 평가금액 (해당 통화 기준)
      - ovrs_ord_psbl_amt: 해외 주문가능금액 (T+2 매도 재사용 + 당일 매수 차감 반영) ✅
      - tot_asst_amt     : 원화 총자산 (output3, 마지막 페이지에서만 정확)
    """
    # ── 종목 잔고 (CTRP6504R, 페이지네이션) ──
    url = f"{BASE_URL}/uapi/overseas-stock/v1/trading/inquire-present-balance"
    h = headers("CTRP6504R")
    params = {
        "CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD,
        "WCRC_FRCR_DVSN_CD": "02", "NATN_CD": natn_cd,
        "TR_MKET_CD": "00", "INQR_DVSN_CD": "00",
        "CTX_AREA_FK200": "", "CTX_AREA_NK200": ""
    }

    stocks = []
    stock_eval = 0.0
    mts_krw_total = 0.0      # output3.tot_asst_amt (마지막 페이지에서만 갱신)
    tr_cont_req = ""
    page_count = 0

    try:
        while True:
            h["tr_cont"] = tr_cont_req
            time.sleep(0.12)
            r = requests.get(url, headers=h, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            resp_tr_cont = r.headers.get("tr_cont", "").strip()

            if data.get("rt_cd") != "0":
                return {"error": data.get("msg1", "API 오류"), "currency": currency}

            # output1: 종목별 누적
            for s in data.get("output1", []):
                qty = int(float(s.get("ccld_qty_smtl1", 0) or 0))
                if qty == 0:
                    continue
                evl = float(s.get("frcr_evlu_amt2", 0) or 0)
                stock_eval += evl
                stocks.append({
                    "code": s.get("pdno", ""),
                    "name": s.get("prdt_name", ""),
                    "qty": qty,
                    "eval_amt": evl,
                    "price": float(s.get("ovrs_now_pric1", 0) or 0),
                    "avg_price": float(s.get("avg_unpr3", 0) or 0),
                    "profit_rate": float(s.get("evlu_pfls_rt1", 0) or 0),
                    "exchange": s.get("ovrs_excg_cd", "")
                })

            # output3: 마지막 페이지에서만 정확
            out3 = data.get("output3", {})
            if isinstance(out3, list):
                out3 = out3[0] if out3 else {}
            tot_page = float(out3.get("tot_asst_amt", 0) or 0)
            if tot_page > 0:
                mts_krw_total = tot_page

            page_count += 1
            if page_count >= MAX_PAGE:
                break
            if resp_tr_cont in ("D", "E", "F"):
                break

            FK = data.get("ctx_area_fk200", "").strip()
            NK = data.get("ctx_area_nk200", "").strip()
            if not FK or not NK:
                break
            params["CTX_AREA_FK200"] = FK
            params["CTX_AREA_NK200"] = NK
            tr_cont_req = "N"

    except Exception as e:
        return {"error": f"{currency} 잔고 예외: {e}", "currency": currency}

    # ── 주문가능금액 (TTTS3007R) ──
    cash = 0.0
    exrt = 0.0
    try:
        time.sleep(0.12)
        url2 = f"{BASE_URL}/uapi/overseas-stock/v1/trading/inquire-psamount"
        h2 = headers("TTTS3007R")
        params2 = {
            "CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD,
            "OVRS_EXCG_CD": excg_order, "ITEM_CD": item_cd,
            "OVRS_ORD_UNPR": price
        }
        r2 = requests.get(url2, headers=h2, params=params2, timeout=10)
        r2.raise_for_status()
        d2 = r2.json()
        if d2.get("rt_cd") == "0":
            output = d2.get("output", {})
            cash = float(output.get("ovrs_ord_psbl_amt", 0) or 0)  # ✅ 검증된 필드
            exrt = float(output.get("exrt", 0) or 0)
    except Exception as e:
        TA.send_tele(f"{currency} TTTS3007R 오류: {e}")

    return {
        "currency": currency,
        "stock_eval": stock_eval,
        "cash": cash,
        "total": stock_eval + cash,
        "exchange_rate": exrt,
        "mts_krw_total": mts_krw_total,
        "stocks": stocks
    }


# ══════════════════════════════════════════════════
#  USD 전략 분리 (USLA / HAA)
# ══════════════════════════════════════════════════

USLA_TICKERS = {"UPRO", "TQQQ", "EDC", "TMV", "TMF"}
HAA_TICKERS  = {"SPY", "IWM", "VEA", "VWO", "PDBC", "VNQ", "TLT", "IEF", "BIL"}


def split_usaa(usd_balance: dict) -> dict:
    """USD 잔고를 USLA / HAA로 분리"""
    usaa_tr = {}
    try:
        if os.path.exists(USAA_TR_PATH):
            with open(USAA_TR_PATH, "r", encoding="utf-8") as f:
                usaa_tr = json.load(f)
    except Exception as e:
        TA.send_tele(f"USAA_TR.json 로드 실패: {e}")

    usla_usd_from_json = float(usaa_tr.get("USD_USLA", 0))
    haa_usd_from_json  = float(usaa_tr.get("USD_HAA", 0))
    usaa_timestamp     = usaa_tr.get("timestamp", "")
    usla_mode          = usaa_tr.get("USLA_Mode", "알수없음")
    haa_mode           = usaa_tr.get("HAA_Mode", "알수없음")

    usla_stocks, usla_eval = [], 0.0
    haa_stocks,  haa_eval  = [], 0.0

    for s in usd_balance.get("stocks", []):
        ticker = s["code"]
        if ticker in USLA_TICKERS:
            usla_stocks.append(s); usla_eval += s["eval_amt"]
        else:
            haa_stocks.append(s);  haa_eval  += s["eval_amt"]

    total_cash = usd_balance.get("cash", 0)

    if usla_mode == "헷징모드" or usla_eval == 0:
        usla_cash = min(usla_usd_from_json, total_cash)
        haa_cash = total_cash - usla_cash
    else:
        json_total = usla_usd_from_json + haa_usd_from_json
        usla_ratio = usla_usd_from_json / json_total if json_total > 0 else 0.66
        usla_cash = total_cash * usla_ratio
        haa_cash = total_cash - usla_cash

    return {
        "USLA_Mode": usla_mode, "HAA_Mode": haa_mode,
        "USLA": {"mode": usla_mode, "total_usd": usla_eval + usla_cash,
                 "stock_eval": usla_eval, "cash": usla_cash, "stocks": usla_stocks},
        "HAA":  {"mode": haa_mode,  "total_usd": haa_eval + haa_cash,
                 "stock_eval": haa_eval,  "cash": haa_cash,  "stocks": haa_stocks},
        "USAA_total": usla_eval + usla_cash + haa_eval + haa_cash,
        "total_cash": total_cash,
        "USAA_TR_timestamp": usaa_timestamp
    }


# ══════════════════════════════════════════════════
#  JSON 저장
# ══════════════════════════════════════════════════

def save_json(snapshot: dict):
    date_str = datetime.now().strftime("%Y%m%d")
    filepath = os.path.join(SNAPSHOT_DIR, f"bal_63604155_{date_str}.json")
    existing = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = {}
    existing[snapshot["mode"]] = snapshot
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    return filepath


# ══════════════════════════════════════════════════
#  Telegram 포맷
# ══════════════════════════════════════════════════

def format_usd(msg, label, data, exrt=0):
    mode_str = data.get("mode", "")
    msg.append(f"\n── {label}{f' [{mode_str}]' if mode_str else ''} ──")
    msg.append(f"  주식: ${data['stock_eval']:,.2f}")
    msg.append(f"  현금: ${data['cash']:,.2f}")
    msg.append(f"  합계: ${data['total_usd']:,.2f}")
    if exrt > 0:
        msg.append(f"  원화환산: ₩{data['total_usd'] * exrt:,.0f}")
    for s in data.get("stocks", []):
        msg.append(f"    {s['code']}: {s['qty']}주 ${s['eval_amt']:,.2f} ({s['profit_rate']:+.1f}%)")


def format_overseas(msg, label, data, symbol):
    msg.append(f"\n── {label} ({data['currency']}) ──")
    msg.append(f"  주식: {symbol}{data['stock_eval']:,.0f}")
    msg.append(f"  현금: {symbol}{data['cash']:,.0f}")
    msg.append(f"  합계: {symbol}{data['total']:,.0f}")
    exrt = data.get("exchange_rate", 0)
    if exrt > 0:
        msg.append(f"  원화환산: ₩{data['total'] * exrt:,.0f} (환율 {exrt:,.2f})")
    msg.append(f"  보유종목수: {len(data.get('stocks', []))}개")
    for s in data.get("stocks", []):
        msg.append(f"    {s['code']}: {s['qty']}주 {symbol}{s['eval_amt']:,.0f} ({s['profit_rate']:+.1f}%)")


# ══════════════════════════════════════════════════
#  실행 (US / ASIA)
# ══════════════════════════════════════════════════

def run_us():
    """KST 08:00 실행 — USD 잔고"""
    msg = [f"📊 63604155 잔고 [USD] {datetime.now().strftime('%Y-%m-%d %H:%M')}"]

    usd = get_overseas_balance("840", "USD", "NASD", "AAPL")
    if "error" in usd:
        msg.append(f"❌ USD 조회 실패: {usd['error']}")
        return {"mode": "US", "timestamp": datetime.now().isoformat(), "error": usd["error"]}, msg

    mts_krw = usd.get("mts_krw_total", 0)
    if mts_krw > 0:
        msg.append(f"MTS 총자산(통화통합): ₩{mts_krw:,.0f}")

    usaa = split_usaa(usd)

    msg.append(f"\n{'='*30}")
    msg.append(f"USLA 모드: {usaa['USLA_Mode']}")
    msg.append(f"HAA  모드: {usaa['HAA_Mode']}")

    exrt = usd.get("exchange_rate", 0)
    msg.append(f"USAA 합계: ${usaa['USAA_total']:,.2f}")
    if exrt > 0:
        msg.append(f"  원화환산: ₩{usaa['USAA_total'] * exrt:,.0f} (환율 {exrt:,.2f})")
    msg.append(f"  주식합계: ${usd['stock_eval']:,.2f}")
    msg.append(f"  현금합계: ${usaa['total_cash']:,.2f}")
    msg.append(f"  보유종목: {len(usd.get('stocks', []))}개")
    msg.append(f"TR기준시점: {usaa['USAA_TR_timestamp']}")

    format_usd(msg, "USLA", usaa["USLA"], exrt)
    format_usd(msg, "HAA",  usaa["HAA"],  exrt)

    snapshot = {
        "mode": "US",
        "timestamp": datetime.now().isoformat(),
        "mts_krw_total": mts_krw,
        "USD": usd,
        "USAA": usaa
    }
    return snapshot, msg


def run_asia():
    """KST 17:00 실행 — KRW / JPY / HKD 잔고"""
    msg = [f"📊 63604155 잔고 [KRW/JPY/HKD] {datetime.now().strftime('%Y-%m-%d %H:%M')}"]

    # ── KRW ──
    krw = get_krw_balance()
    if "error" in krw:
        msg.append(f"❌ KRW 조회 실패: {krw['error']}")
    else:
        msg.append(f"\n── KRQT (KRW) ──")
        msg.append(f"  주식: ₩{krw['stock_eval']:,.0f}")
        msg.append(f"  현금: ₩{krw['cash']:,.0f}  (참조 매수가능: ₩{krw.get('nrcvb_buy_amt', 0):,.0f})")
        msg.append(f"  총평가(nass_amt): ₩{krw['total']:,.0f}")
        msg.append(f"  보유종목수: {len(krw.get('stocks', []))}개")
        for s in krw.get("stocks", []):
            msg.append(f"    {s['code']} {s['name']}: {s['qty']}주 ₩{s['eval_amt']:,.0f} ({s['profit_rate']:+.1f}%)")

    # ── JPY ──
    jpy = get_overseas_balance("392", "JPY", "TKSE", "7203", "1000")
    if "error" in jpy:
        msg.append(f"\n❌ JPY 조회 실패: {jpy.get('error')}")
    else:
        format_overseas(msg, "JPQT", jpy, "¥")

    # ── HKD ──
    hkd = get_overseas_balance("344", "HKD", "SEHK", "00700", "100")
    if "error" in hkd:
        msg.append(f"\n❌ HKD 조회 실패: {hkd.get('error')}")
    else:
        format_overseas(msg, "HKQT", hkd, "HK$")

    # ── MTS 총자산 (마지막 해외 조회의 output3 사용) ──
    mts_krw = 0.0
    for x in (jpy, hkd):
        if isinstance(x, dict) and x.get("mts_krw_total", 0) > 0:
            mts_krw = max(mts_krw, x["mts_krw_total"])

    # ── ASIA 원화환산 합계 ──
    krw_total_all = 0.0
    if "error" not in krw:
        krw_total_all += krw.get("total", 0)
    if "error" not in jpy:
        e = jpy.get("exchange_rate", 0)
        krw_total_all += jpy.get("total", 0) * e if e > 0 else 0
    if "error" not in hkd:
        e = hkd.get("exchange_rate", 0)
        krw_total_all += hkd.get("total", 0) * e if e > 0 else 0

    msg.append(f"\n{'='*30}")
    if mts_krw > 0:
        msg.append(f"MTS 총자산(통화통합): ₩{mts_krw:,.0f}")
    if krw_total_all > 0:
        msg.append(f"ASIA 원화환산 합계: ₩{krw_total_all:,.0f}")

    snapshot = {
        "mode": "ASIA",
        "timestamp": datetime.now().isoformat(),
        "mts_krw_total": mts_krw,
        "KRW": krw,
        "JPY": jpy,
        "HKD": hkd,
        "total_krw": krw_total_all
    }
    return snapshot, msg


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 Balance_63604155.py [US|ASIA]")
        sys.exit(1)

    mode = sys.argv[1].upper()
    if mode == "US":
        snapshot, msg = run_us()
    elif mode == "ASIA":
        snapshot, msg = run_asia()
    else:
        print(f"Unknown mode: {mode}. Use US or ASIA")
        sys.exit(1)

    try:
        path = save_json(snapshot)
        msg.append(f"\n✅ JSON: {path}")
    except Exception as e:
        msg.append(f"\n❌ JSON 저장 실패: {e}")

    TA.send_tele(msg)


if __name__ == "__main__":
    main()
