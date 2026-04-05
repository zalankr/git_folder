"""
Balance_63604155.py
====================
63604155 계좌 4통화 일별 잔고 스냅샷 (Simple 버전)

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
    한국주식 잔고 조회 (페이지네이션 포함)
    nass_amt = 순자산(주식평가+D+2현금) → total
    stock_eval = output1 합산 → 주식평가금
    cash = nass_amt - stock_eval
    """
    url = f"{BASE_URL}/uapi/domestic-stock/v1/trading/inquire-balance"
    params = {
        "CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD,
        "AFHR_FLPR_YN": "N", "OFL_YN": "", "INQR_DVSN": "00",
        "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N",
        "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00",
        "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""
    }

    stock_eval = 0.0
    total = 0.0
    stocks = []

    while True:
        time.sleep(0.1)
        r = requests.get(url, headers=headers("TTTC8434R"), params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("rt_cd") != "0":
            return {"error": data.get("msg1", "API 오류")}

        for s in data.get("output1", []):
            qty = int(s.get("hldg_qty", 0))
            if qty == 0:
                continue
            evl = float(s.get("evlu_amt", 0))
            stock_eval += evl
            stocks.append({
                "code": s.get("pdno", ""),
                "name": s.get("prdt_name", ""),
                "qty": qty,
                "eval_amt": evl,
                "price": int(s.get("prpr", 0)),
                "profit_rate": float(s.get("evlu_pfls_rt", 0))
            })

        out2 = data.get("output2", [{}])
        total = float((out2[0] if out2 else {}).get("nass_amt", 0))

        fk = data.get("ctx_area_fk100", "").strip()
        nk = data.get("ctx_area_nk100", "").strip()
        if not fk or not nk:
            break
        params["CTX_AREA_FK100"] = fk
        params["CTX_AREA_NK100"] = nk

    cash = total - stock_eval

    return {
        "currency": "KRW",
        "label": "KRQT",
        "stock_eval": stock_eval,
        "cash": cash,
        "total": total,
        "stocks": stocks
    }


# ══════════════════════════════════════════════════
#  해외 잔고 공통 (CTRP6504R + TTTS3007R)
# ══════════════════════════════════════════════════

def get_overseas_balance(natn_cd: str, currency: str,
                         excg_order: str, item_cd: str,
                         price: str = "100") -> dict:
    """
    해외 주식 잔고 (체결기준현재잔고 CTRP6504R)
    + 주문가능금액 (TTTS3007R)

    natn_cd:    840=미국, 392=일본, 344=홍콩
    excg_order: NASD(미국), TKSE(일본), SEHK(홍콩) — TTTS3007R용
    item_cd:    대표종목 AAPL / 7203 / 00700
    """
    # ── 종목 잔고 (CTRP6504R) ──
    url = f"{BASE_URL}/uapi/overseas-stock/v1/trading/inquire-present-balance"
    params = {
        "CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD,
        "WCRC_FRCR_DVSN_CD": "02", "NATN_CD": natn_cd,
        "TR_MKET_CD": "00", "INQR_DVSN_CD": "00"
    }

    time.sleep(0.1)
    r = requests.get(url, headers=headers("CTRP6504R"), params=params, timeout=10)
    r.raise_for_status()
    data = r.json()

    if data.get("rt_cd") != "0":
        return {"error": data.get("msg1", "API 오류"), "currency": currency}

    stocks = []
    stock_eval = 0.0
    for s in data.get("output1", []):
        qty = int(float(s.get("ccld_qty_smtl1", 0)))
        if qty == 0:
            continue
        evl = float(s.get("frcr_evlu_amt2", 0))
        stock_eval += evl
        stocks.append({
            "code": s.get("pdno", ""),
            "name": s.get("prdt_name", ""),
            "qty": qty,
            "eval_amt": evl,
            "price": float(s.get("ovrs_now_pric1", 0)),
            "avg_price": float(s.get("avg_unpr3", 0)),
            "profit_rate": float(s.get("evlu_pfls_rt1", 0))
        })

    out2 = data.get("output2", [])
    info = out2[0] if out2 else {}
    deposit = float(info.get("frcr_dncl_amt_2", 0))
    exrt = float(info.get("frst_bltn_exrt", 0))

    # ── 주문가능금액 (TTTS3007R) — 더 정확한 현금 ──
    time.sleep(0.1)
    url2 = f"{BASE_URL}/uapi/overseas-stock/v1/trading/inquire-psamount"
    params2 = {
        "CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD,
        "OVRS_EXCG_CD": excg_order, "ITEM_CD": item_cd,
        "OVRS_ORD_UNPR": price
    }
    try:
        r2 = requests.get(url2, headers=headers("TTTS3007R"), params=params2, timeout=10)
        r2.raise_for_status()
        d2 = r2.json()
        orderable = float(d2.get("output", {}).get("ovrs_ord_psbl_amt", 0)) \
            if d2.get("rt_cd") == "0" else None
    except Exception:
        orderable = None

    return {
        "currency": currency,
        "stock_eval": stock_eval,
        "cash_deposit": deposit,
        "orderable_cash": orderable,
        "total": stock_eval + deposit,
        "exchange_rate": exrt,
        "stocks": stocks
    }


# ══════════════════════════════════════════════════
#  USD 전략 분리 (USLA / HAA)
# ══════════════════════════════════════════════════

USLA_TICKERS = {"UPRO", "TQQQ", "EDC", "TMV", "TMF"}
HAA_TICKERS  = {"SPY", "IWM", "VEA", "VWO", "PDBC", "VNQ", "TLT", "IEF", "BIL"}


def split_usaa(usd_balance: dict) -> dict:
    """
    USD 잔고를 USLA / HAA로 분리
    - USLA 현재 헷징모드 → 주식 보유 없이 USD 현금화 상태
      → USAA_TR.json의 USD_USLA 값을 USLA 잔고로 사용
    - HAA → API 실제 주식 평가금 + (전체 USD - USLA분 = HAA 현금)
    """
    # USAA_TR.json 로드
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

    # API 종목을 USLA / HAA로 분류
    usla_stocks = []
    usla_eval = 0.0
    haa_stocks = []
    haa_eval = 0.0

    for s in usd_balance.get("stocks", []):
        ticker = s["code"]
        if ticker in USLA_TICKERS:
            usla_stocks.append(s)
            usla_eval += s["eval_amt"]
        elif ticker in HAA_TICKERS:
            haa_stocks.append(s)
            haa_eval += s["eval_amt"]
        else:
            # 미분류 종목은 HAA로
            haa_stocks.append(s)
            haa_eval += s["eval_amt"]

    # USLA 총 잔고: USAA_TR.json의 USD_USLA 사용 (헷징모드 → 현금=달러RP)
    # HAA 총 잔고: API 주식 평가금 + HAA에 배정된 현금(USD_HAA from json)
    #   → HAA 현금 = USD_HAA - haa_eval (주식외 잔여)
    haa_cash = max(haa_usd_from_json - haa_eval, 0)
    haa_total = haa_eval + haa_cash

    # 전체 USD = USLA + HAA
    usaa_total = usla_usd_from_json + haa_total

    return {
        "USLA": {
            "total_usd": usla_usd_from_json,
            "stock_eval": usla_eval,
            "cash": usla_usd_from_json - usla_eval,
            "stocks": usla_stocks,
            "note": "헷징모드 - USAA_TR.json 기준"
        },
        "HAA": {
            "total_usd": haa_total,
            "stock_eval": haa_eval,
            "cash": haa_cash,
            "stocks": haa_stocks
        },
        "USAA_total": usaa_total,
        "USAA_TR_timestamp": usaa_timestamp,
        "api_total": usd_balance.get("total", 0),
        "api_cash": usd_balance.get("orderable_cash")
    }


# ══════════════════════════════════════════════════
#  JSON 저장
# ══════════════════════════════════════════════════

def save_json(snapshot: dict):
    """일별 JSON 저장 (모드별 병합)"""
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

def format_usd(msg: list, label: str, data: dict):
    """USD 전략별 텔레그램 메시지 포맷"""
    msg.append(f"\n── {label} ──")
    msg.append(f"  주식: ${data['stock_eval']:,.2f}")
    msg.append(f"  현금: ${data['cash']:,.2f}")
    msg.append(f"  합계: ${data['total_usd']:,.2f}")
    for s in data.get("stocks", []):
        msg.append(f"    {s['code']}: {s['qty']}주 ${s['eval_amt']:,.2f} ({s['profit_rate']:+.1f}%)")


def format_overseas(msg: list, label: str, data: dict, symbol: str):
    """해외 잔고 텔레그램 메시지 포맷"""
    msg.append(f"\n── {label} ({data['currency']}) ──")
    msg.append(f"  주식: {symbol}{data['stock_eval']:,.0f}")
    msg.append(f"  예수금: {symbol}{data['cash_deposit']:,.0f}")
    if data.get("orderable_cash") is not None:
        msg.append(f"  주문가능: {symbol}{data['orderable_cash']:,.0f}")
    msg.append(f"  합계: {symbol}{data['total']:,.0f}")
    if data.get("exchange_rate"):
        msg.append(f"  환율: {data['exchange_rate']:,.2f}")
    for s in data.get("stocks", []):
        msg.append(f"    {s['code']}: {s['qty']}주 {symbol}{s['eval_amt']:,.0f} ({s['profit_rate']:+.1f}%)")


# ══════════════════════════════════════════════════
#  메인
# ══════════════════════════════════════════════════

def run_us():
    """KST 08:00 실행 — USD 잔고"""
    msg = [f"📊 63604155 잔고 [USD] {datetime.now().strftime('%Y-%m-%d %H:%M')}"]

    # USD 잔고 조회
    usd = get_overseas_balance("840", "USD", "NASD", "AAPL")
    if "error" in usd:
        msg.append(f"❌ USD 조회 실패: {usd['error']}")
        return {"mode": "US", "timestamp": datetime.now().isoformat(), "error": usd["error"]}, msg

    # USLA / HAA 분리
    usaa = split_usaa(usd)

    msg.append(f"\n{'='*30}")
    msg.append(f"USAA 합계: ${usaa['USAA_total']:,.2f}")
    msg.append(f"API 합계: ${usaa['api_total']:,.2f}")
    if usaa.get("api_cash") is not None:
        msg.append(f"API 주문가능: ${usaa['api_cash']:,.2f}")
    msg.append(f"TR기준시점: {usaa['USAA_TR_timestamp']}")

    format_usd(msg, "USLA (헷징모드)", usaa["USLA"])
    format_usd(msg, "HAA", usaa["HAA"])

    snapshot = {
        "mode": "US",
        "timestamp": datetime.now().isoformat(),
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
        msg.append(f"  현금: ₩{krw['cash']:,.0f}")
        msg.append(f"  합계: ₩{krw['total']:,.0f}")
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

    snapshot = {
        "mode": "ASIA",
        "timestamp": datetime.now().isoformat(),
        "KRW": krw,
        "JPY": jpy,
        "HKD": hkd
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

    # JSON 먼저 저장
    try:
        path = save_json(snapshot)
        msg.append(f"\n✅ JSON: {path}")
    except Exception as e:
        msg.append(f"\n❌ JSON 저장 실패: {e}")

    # Telegram 발송
    TA.send_tele(msg)
    print("\n".join(msg)) ###


if __name__ == "__main__":
    main()
