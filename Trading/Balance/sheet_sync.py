"""
sheet_sync.py
====================
daily_snapshot.py 보조 모듈 — 일별 잔고 스냅샷을 Google Sheet에 기록.

기능:
  1. balance_YYYYMMDD.json 의 strategy/sub 별 total_krw 를 지정 셀에 기록
  2. 동일 열의 "현재 연월 행"(A열 인덱스 검색)에도 같은 값 복사
  3. 수기 입력 자산(manual_assets.json) 은 종목 수량 + 예수금만 보관,
     현재가는 KIS API 로 매번 조회해 평가금 산출

사용 (daily_snapshot.py 에서):
    import sheet_sync
    sheet_sync.update_google_sheet(items, mode, kis_headers_fn, base_url)

의존성:
    pip3 install --break-system-packages gspread google-auth

⚠️ 사전 준비 (사용자 직접):
   서비스계정 JSON 의 client_email 을 대상 스프레드시트에 "편집자"로 공유할 것.
   공유 안 하면 gspread.exceptions.APIError(PermissionDenied) 발생.
"""

import os
import json
import time
import re
from datetime import datetime

import requests
import gspread
from google.oauth2.service_account import Credentials

# ══════════════════════════════════════════════════
#  설정 — 환경에 맞게 이 블록만 수정
# ══════════════════════════════════════════════════

# 서비스계정 키 경로 (사용자 확정 경로로 교체)
GOOGLE_SA_KEY_PATH = "/var/autobot/gspread/service_account.json"

# 대상 스프레드시트 ID (URL 의 /d/ 와 /edit 사이)
SPREADSHEET_ID = "1_9kp7fv0_gZXpaUmMqLgpDC80poa7qkW3FjWbs_K03M"

# 수기 입력 자산 JSON
MANUAL_ASSETS_PATH = "/var/autobot/Balance/manual_assets.json"

# A열 연월 인덱스가 시작되는 행 (헤더 아래 첫 데이터 행). 검색 시 fallback 용.
A_COL_SEARCH_START = 1

GSPREAD_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]


# ══════════════════════════════════════════════════
#  셀 매핑 테이블
#  (sheet_name, fixed_cell)  ← fixed_cell 의 '열'을 떼어 현재월 행에도 기록
# ══════════════════════════════════════════════════
# key 는 (strategy, sub) 매칭에 사용. sub 가 None 이면 strategy 전체 합산.
# KRQT 는 4개 sub 합산 → 단일 셀. GBFT 는 sub 전체 합산 → 단일 셀.

CELL_MAP = {
    # ── KR 시트 ─────────────────────────────────
    ("KRQT", None):                ("KR",          "T4"),   # 4개 sub 합산
    ("KRTR", "PEAK"):              ("KR",          "Z4"),
    ("KRTR", "VALUE"):             ("KR",          "AC4"),
    ("KRTR", "MOMENTUM"):          ("KR",          "AF4"),
    ("KRTR", "Coverdcall"):        ("KR",          "AI4"),
    ("KRFT", None):                ("KR",          "AL4"),  # Hedge & Boost

    # ── Global 시트 ─────────────────────────────
    ("USAA", "USLA"):              ("Global",      "AC4"),  # 시트 표기 UALA
    ("USAA", "HAA"):               ("Global",      "AF4"),
    ("USQT", None):                ("Global",      "AO4"),  # SCG+TCM 합산
    ("JPQT", None):                ("Global",      "AR4"),
    ("HKQT", None):                ("Global",      "AU4"),
    ("GBFT", None):                ("Global",      "BA4"),  # Hedge&Boost + Commodity 합산
    # ETC(JPUSbond) 는 수기 자산 → MANUAL_CELL_MAP

    # ── Alternative 시트 ───────────────────────
    ("Crypto", None):              ("Alternative", "P3"),

    # ── PENSION 시트 ───────────────────────────
    ("Pension", "연금저축-2"):     ("PENSION",     "S4"),
    ("Pension", "IRP"):            ("PENSION",     "V4"),
    ("ISA", "ISA"):                ("PENSION",     "AE4"),
    ("ISA", "윤숙ISA"):            ("PENSION",     "AK4"),
}

# 수기 입력 자산 → 셀 매핑. key 는 manual_assets.json 의 최상위 key.
MANUAL_CELL_MAP = {
    "JPUSbond":          ("Global",      "AX4"),
    "Gold":              ("Alternative", "M3"),
    "Pension_퇴직연금":  ("PENSION",     "J4"),
    "Pension_연금저축-1":("PENSION",     "P4"),
}


# ══════════════════════════════════════════════════
#  유틸 — 셀 좌표 파싱 / 연월 정규화
# ══════════════════════════════════════════════════

def _split_cell(cell: str) -> tuple:
    """'AC4' → ('AC', 4).  열문자/행번호 분리."""
    m = re.match(r"^([A-Z]+)(\d+)$", cell.strip().upper())
    if not m:
        raise ValueError(f"잘못된 셀 주소: {cell}")
    return m.group(1), int(m.group(2))


def _normalize_ym(raw) -> tuple:
    """
    A열 셀 값을 (year, month) 로 정규화.
    구글시트 날짜셀은 gspread 가 보통 다음 형태로 반환:
      - "2026-05-01"          (ISO)
      - "5/1/2026" / "5/1/26" (US locale)
      - "2026. 5. 1"          (KR locale)
      - "2026-05"             (텍스트)
      - "2026년 5월"          (한글 텍스트)
      - 45444 (정수 직렬번호, 드물게)
    매칭 불가 시 None 반환.
    """
    if raw is None or raw == "":
        return None

    # 정수 직렬번호 (Google/Excel epoch 1899-12-30)
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        try:
            from datetime import date, timedelta
            base = date(1899, 12, 30)
            d = base + timedelta(days=int(raw))
            return (d.year, d.month)
        except Exception:
            return None

    s = str(raw).strip()

    # "2026년 5월"
    m = re.match(r"(\d{4})\s*년\s*(\d{1,2})\s*월", s)
    if m:
        return (int(m.group(1)), int(m.group(2)))

    # ISO/하이픈/점 구분: 2026-05-01, 2026-05, 2026.5.1, 2026. 5
    m = re.match(r"(\d{4})[.\-/]\s*(\d{1,2})", s)
    if m:
        return (int(m.group(1)), int(m.group(2)))

    # US locale: 5/1/2026, 5/1/26
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", s)
    if m:
        yr = int(m.group(3))
        if yr < 100:
            yr += 2000
        return (yr, int(m.group(1)))

    return None


def _find_month_row(ws, target_ym: tuple) -> int:
    """
    워크시트 A열에서 target_ym (year, month) 과 일치하는 행 번호 반환.
    못 찾으면 0.
    """
    col_vals = ws.col_values(1)   # A열 전체 (1-indexed list)
    for idx, raw in enumerate(col_vals, start=1):
        if idx < A_COL_SEARCH_START:
            continue
        ym = _normalize_ym(raw)
        if ym == target_ym:
            return idx
    return 0


# ══════════════════════════════════════════════════
#  수기 자산 평가금 계산
# ══════════════════════════════════════════════════

def _kis_kr_price(kis_headers_fn, base_url: str, cano: str, code: str) -> float:
    """국내 ETF/주식 현재가 (FHKST01010100)."""
    url = f"{base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
    h = kis_headers_fn(cano, "FHKST01010100")
    params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code}
    try:
        r = requests.get(url, headers=h, params=params, timeout=10)
        r.raise_for_status()
        d = r.json()
        if d.get("rt_cd") == "0":
            return float(d["output"]["stck_prpr"] or 0)
    except Exception:
        pass
    return 0.0


def _kis_jp_price(kis_headers_fn, base_url: str, cano: str,
                  code: str, excg: str = "TKSE") -> tuple:
    """
    일본주식 현재가 + 환율. (HHDFS00000300)
    Returns: (price_jpy, krw_per_jpy)
    """
    url = f"{base_url}/uapi/overseas-price/v1/quotations/price"
    h = kis_headers_fn(cano, "HHDFS00000300")
    params = {"AUTH": "", "EXCD": excg, "SYMB": code}
    price = 0.0
    try:
        r = requests.get(url, headers=h, params=params, timeout=10)
        r.raise_for_status()
        d = r.json()
        if d.get("rt_cd") == "0":
            out = d.get("output", {})
            for f in ("last", "base", "open"):
                v = str(out.get(f, "")).strip()
                if v and v != "0":
                    price = float(v)
                    break
    except Exception:
        pass
    return price, 0.0


def _get_fx_rate(kis_headers_fn, base_url: str, cano: str,
                 acnt: str, currency: str) -> float:
    """
    통화 → KRW 환율 조회 (해외주식 체결기준현재잔고 CTRP6504R 의 frst_bltn_exrt).
    실패 시 0.
    """
    if currency == "KRW":
        return 1.0
    natn = {"USD": "840", "JPY": "392", "HKD": "344"}.get(currency, "840")
    url = f"{base_url}/uapi/overseas-stock/v1/trading/inquire-present-balance"
    h = kis_headers_fn(cano, "CTRP6504R")
    params = {
        "CANO": cano, "ACNT_PRDT_CD": acnt or "01",
        "WCRC_FRCR_DVSN_CD": "02", "NATN_CD": natn,
        "TR_MKET_CD": "00", "INQR_DVSN_CD": "00",
    }
    try:
        r = requests.get(url, headers=h, params=params, timeout=10)
        r.raise_for_status()
        d = r.json()
        if d.get("rt_cd") == "0":
            for o in d.get("output2", []):
                if o.get("crcy_cd") == currency:
                    rt = float(o.get("frst_bltn_exrt", 0) or 0)
                    if rt > 0:
                        return rt
    except Exception:
        pass
    return 0.0


def calc_manual_asset_krw(asset_key: str, asset: dict,
                          kis_headers_fn, base_url: str) -> dict:
    """
    수기 자산 1건의 총 원화 평가금 계산.
    asset: manual_assets.json 의 한 항목 (deposit + holdings).
    Returns: {"total_krw": float, "detail": [...], "error": ""}
    """
    market = asset.get("market", "KR")
    # 평가금 계산에 쓸 임시 계좌 (토큰 발급용) — 국내조회는 어떤 계좌든 무관
    quote_cano = "63604155"

    stock_krw = 0.0
    detail = []

    for h in asset.get("holdings", []):
        code = str(h.get("code", "")).strip()
        qty = float(h.get("qty", 0) or 0)
        if qty <= 0 or not code:
            detail.append({"code": code, "name": h.get("name", ""),
                           "qty": qty, "eval_krw": 0.0})
            continue

        if market in ("KR", "KR_GOLD"):
            # KRX 금현물(KR_GOLD)도 종목코드로 inquire-price 조회 시도.
            # 코드가 ETF가 아니면 0 반환 → 사용자가 deposit에 평가금 합산하거나
            # holdings code 를 KRX 금현물 종목코드로 지정.
            price = _kis_kr_price(kis_headers_fn, base_url, quote_cano, code)
            eval_krw = price * qty
        elif market == "JP":
            excg = asset.get("excg", "TKSE")
            price_jpy, _ = _kis_jp_price(kis_headers_fn, base_url,
                                         quote_cano, code, excg)
            fx = _get_fx_rate(kis_headers_fn, base_url,
                              quote_cano, "01", "JPY")
            eval_krw = price_jpy * qty * fx
        else:
            eval_krw = 0.0

        stock_krw += eval_krw
        detail.append({"code": code, "name": h.get("name", ""),
                       "qty": qty, "eval_krw": eval_krw})
        time.sleep(0.12)

    # 예수금 (통화별 → KRW 환산)
    cash_krw = 0.0
    for cur, amt in asset.get("deposit", {}).items():
        amt = float(amt or 0)
        if cur == "KRW":
            cash_krw += amt
        else:
            fx = _get_fx_rate(kis_headers_fn, base_url, quote_cano, "01", cur)
            cash_krw += amt * fx
            time.sleep(0.12)

    return {
        "total_krw": stock_krw + cash_krw,
        "stock_krw": stock_krw,
        "cash_krw": cash_krw,
        "detail": detail,
        "error": "",
    }


# ══════════════════════════════════════════════════
#  items → (strategy, sub) 별 total_krw 집계
# ══════════════════════════════════════════════════

def _aggregate_items(items: list) -> dict:
    """
    collect_accounts 의 items 를 CELL_MAP key 별 total_krw 로 집계.
    Returns: {(strategy, sub or None): total_krw}
    """
    agg = {}

    # 1) sub 단위 값 (CELL_MAP 에 sub 명시된 것)
    for it in items:
        strat = it.get("strategy", "")
        sub = it.get("sub", "")
        tk = float(it.get("total_krw", 0) or 0)
        agg[(strat, sub)] = agg.get((strat, sub), 0.0) + tk

    # 2) strategy 전체 합산 (CELL_MAP key 의 sub 가 None 인 것)
    for (strat, sub) in CELL_MAP:
        if sub is None:
            total = sum(float(it.get("total_krw", 0) or 0)
                        for it in items if it.get("strategy") == strat)
            agg[(strat, None)] = total

    return agg


# ══════════════════════════════════════════════════
#  메인 — Google Sheet 업데이트
# ══════════════════════════════════════════════════

def update_google_sheet(items: list, mode: str,
                        kis_headers_fn, base_url: str) -> list:
    """
    items 와 수기 자산을 Google Sheet 에 기록.

    Parameters:
      items         : collect_accounts(mode) 결과
      mode          : "US" | "ASIA"
      kis_headers_fn: daily_snapshot.kis_headers (수기 자산 시세 조회용)
      base_url      : daily_snapshot.BASE_URL

    Returns: 로그 메시지 리스트 (telegram 전송용)
    """
    log = ["📑 Google Sheet 업데이트"]

    # ── 1. 인증 ──
    if not os.path.exists(GOOGLE_SA_KEY_PATH):
        log.append(f"❌ 서비스계정 키 없음: {GOOGLE_SA_KEY_PATH}")
        return log
    try:
        creds = Credentials.from_service_account_file(
            GOOGLE_SA_KEY_PATH, scopes=GSPREAD_SCOPES)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SPREADSHEET_ID)
    except Exception as e:
        log.append(f"❌ 시트 연결 실패: {e}")
        return log

    # ── 2. 워크시트 핸들 캐시 + 현재월 행 캐시 ──
    today = datetime.now()
    target_ym = (today.year, today.month)
    ws_cache = {}
    month_row_cache = {}

    def _get_ws(name):
        if name not in ws_cache:
            try:
                ws_cache[name] = sh.worksheet(name)
            except Exception as e:
                ws_cache[name] = None
                log.append(f"⚠️ 시트 '{name}' 없음: {e}")
        return ws_cache[name]

    def _get_month_row(name):
        if name not in month_row_cache:
            ws = _get_ws(name)
            month_row_cache[name] = _find_month_row(ws, target_ym) if ws else 0
        return month_row_cache[name]

    # ── 3. 기록 대상 수집: {sheet_name: [(cell, value, label), ...]} ──
    writes = {}

    def _queue(sheet_name, cell, value, label):
        writes.setdefault(sheet_name, []).append((cell, value, label))

    # 3-1. API 자동 수집 자산
    agg = _aggregate_items(items)
    for (strat, sub), (sheet_name, cell) in CELL_MAP.items():
        val = agg.get((strat, sub))
        if val is None:
            # mode=US 등으로 해당 전략 미수집 → 스킵 (덮어쓰지 않음)
            continue
        label = f"{strat}/{sub or '합산'}"
        _queue(sheet_name, cell, round(val), label)

    # 3-2. 수기 입력 자산
    manual = {}
    if os.path.exists(MANUAL_ASSETS_PATH):
        try:
            with open(MANUAL_ASSETS_PATH, encoding="utf-8") as f:
                manual = json.load(f)
        except Exception as e:
            log.append(f"⚠️ manual_assets.json 로드 실패: {e}")
    else:
        log.append(f"⚠️ manual_assets.json 없음: {MANUAL_ASSETS_PATH}")

    for akey, (sheet_name, cell) in MANUAL_CELL_MAP.items():
        asset = manual.get(akey)
        if not isinstance(asset, dict):
            log.append(f"⚠️ 수기자산 '{akey}' 항목 없음 → 스킵")
            continue
        try:
            res = calc_manual_asset_krw(akey, asset, kis_headers_fn, base_url)
            _queue(sheet_name, cell, round(res["total_krw"]), f"수기:{akey}")
            log.append(f"  · {akey}: ₩{res['total_krw']:,.0f} "
                       f"(주식 ₩{res['stock_krw']:,.0f} + 예수금 ₩{res['cash_krw']:,.0f})")
        except Exception as e:
            log.append(f"⚠️ 수기자산 '{akey}' 계산 실패: {e}")

    # ── 4. 시트별 batch_update ──
    for sheet_name, entries in writes.items():
        ws = _get_ws(sheet_name)
        if ws is None:
            continue
        month_row = _get_month_row(sheet_name)

        batch = []   # gspread batch_update payload
        for (cell, value, label) in entries:
            col, _row = _split_cell(cell)
            # 4-1. 고정 셀
            batch.append({"range": cell, "values": [[value]]})
            # 4-2. 현재월 행 (열 동일, 행만 교체)
            if month_row > 0:
                batch.append({"range": f"{col}{month_row}",
                              "values": [[value]]})

        if not batch:
            continue
        try:
            ws.batch_update(batch, value_input_option="USER_ENTERED")
            mr = month_row if month_row > 0 else "미발견"
            log.append(f"  ✅ {sheet_name}: {len(entries)}개 셀 "
                       f"(고정 + 월행 {mr})")
        except Exception as e:
            log.append(f"  ❌ {sheet_name} 기록 실패: {e}")
        time.sleep(1.0)   # gspread API quota (분당 60회) 여유

    if target_ym not in [month_row_cache and None]:
        ym_str = f"{target_ym[0]}-{target_ym[1]:02d}"
        log.append(f"  현재월 인덱스: {ym_str}")

    return log
