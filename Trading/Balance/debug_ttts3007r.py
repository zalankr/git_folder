"""
debug_ttts3007r.py
==================
63604155 계좌의 TTTS3007R(해외주문가능금액)과 CTRP6504R(체결기준잔고) output을
거래소별/국가별로 조회하여 모든 필드를 그대로 출력.

목적: 통화별 예수금 분리 가능한 필드가 있는지 확인

사용:
  python3 debug_ttts3007r.py
"""

import os
import json
import requests
from datetime import datetime, timedelta

CANO = "63604155"
ACNT_PRDT_CD = "01"
KEY_FILE   = "/var/autobot/KIS/kis63604155nkr.txt"
TOKEN_FILE = "/var/autobot/KIS/kis63604155_token.json"
BASE_URL   = "https://openapi.koreainvestment.com:9443"


def load_keys():
    with open(KEY_FILE) as f:
        return [l.strip() for l in f.readlines()]


APP_KEY, APP_SECRET = load_keys()


def get_token():
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


def headers(tr_id):
    return {
        "Content-Type": "application/json",
        "authorization": f"Bearer {ACCESS_TOKEN}",
        "appKey": APP_KEY,
        "appSecret": APP_SECRET,
        "tr_id": tr_id,
        "custtype": "P"
    }


# ─────────────────────────────────────
#  1. TTTS3007R: 거래소별 주문가능금액
# ─────────────────────────────────────

print("\n" + "=" * 70)
print("TTTS3007R (해외주식 매수가능금액) — 거래소별")
print("=" * 70)

url = f"{BASE_URL}/uapi/overseas-stock/v1/trading/inquire-psamount"

cases = [
    ("NASD", "AAPL",  "100",  "미국(USD)"),
    ("TKSE", "7203",  "1000", "일본(JPY)"),
    ("SEHK", "00700", "100",  "홍콩(HKD)"),
]

for excg, item, price, label in cases:
    print(f"\n── [{label}] OVRS_EXCG_CD={excg}, ITEM_CD={item} ──")
    params = {
        "CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD,
        "OVRS_EXCG_CD": excg, "ITEM_CD": item,
        "OVRS_ORD_UNPR": price
    }
    try:
        r = requests.get(url, headers=headers("TTTS3007R"),
                         params=params, timeout=10)
        data = r.json()
        if data.get("rt_cd") != "0":
            print(f"❌ 오류: {data.get('msg1')}")
            continue
        output = data.get("output", {})
        # 모든 필드 key-value 출력
        for k, v in output.items():
            print(f"  {k}: {v}")
    except Exception as e:
        print(f"❌ 예외: {e}")


# ─────────────────────────────────────
#  2. CTRP6504R: 국가별 체결기준잔고 output2 (예수금 섹션)
# ─────────────────────────────────────

print("\n\n" + "=" * 70)
print("CTRP6504R (체결기준현재잔고) output2 — 국가별")
print("=" * 70)

url2 = f"{BASE_URL}/uapi/overseas-stock/v1/trading/inquire-present-balance"

cases2 = [
    ("840", "미국(USD)"),
    ("392", "일본(JPY)"),
    ("344", "홍콩(HKD)"),
]

for natn_cd, label in cases2:
    print(f"\n── [{label}] NATN_CD={natn_cd} ──")
    params = {
        "CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD,
        "WCRC_FRCR_DVSN_CD": "02", "NATN_CD": natn_cd,
        "TR_MKET_CD": "00", "INQR_DVSN_CD": "00",
        "CTX_AREA_FK200": "", "CTX_AREA_NK200": ""
    }
    try:
        r = requests.get(url2, headers=headers("CTRP6504R"),
                         params=params, timeout=10)
        data = r.json()
        if data.get("rt_cd") != "0":
            print(f"❌ 오류: {data.get('msg1')}")
            continue
        out2 = data.get("output2", [])
        if not out2:
            print("  (output2 비어있음)")
            continue
        # output2의 모든 필드 출력 (보통 단일 dict 또는 1-item list)
        entry = out2[0] if isinstance(out2, list) else out2
        for k, v in entry.items():
            print(f"  {k}: {v}")
    except Exception as e:
        print(f"❌ 예외: {e}")

print("\n" + "=" * 70)
print("완료. 결과 텍스트를 복사해서 전달해주세요.")
print("=" * 70)
