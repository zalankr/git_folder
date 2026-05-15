"""
backfill_monthly.py (v2)
=========================
krfuture_monthly.json 에 과거 월말 데이터를 백필.

데이터 소스:
  - KOSPI 종합 (코드 1001)     : pykrx (venv_krx)
  - KOSDAQ 종합 (코드 2001)    : pykrx (venv_krx)
  - KOSPI 시장 PBR             : pykrx (venv_krx)
  - VKOSPI                     : KIS API (U/0503)  ★

사용:
    # 1차: pykrx 데이터만 (venv_krx에서)
    /var/autobot/venv_krx/bin/python backfill_monthly.py kospi [START] [END]

    # 2차: VKOSPI 채움 (일반 venv에서, KIS API)
    /var/autobot/venv/bin/python backfill_monthly.py vkospi [START] [END]

    # 둘 다: auto (가능한 환경에서)
    python backfill_monthly.py auto [START] [END]

기본 범위: 2003-01 ~ 직전월
"""
import io
import os
import sys
import json
import time
import requests
from datetime import datetime, date, timedelta
from pathlib import Path
from calendar import monthrange

MONTHLY_JSON_PATH = "/var/autobot/TR_KRFT/krfuture_monthly.json"
DEFAULT_START     = "200301"
VKOSPI_START      = "200904"

KIS_KEY_FILE   = "/var/autobot/KIS/kis64753341nkr.txt"
KIS_TOKEN_FILE = "/var/autobot/KIS/kis64753341_token.json"


# ────────────────────────────────────────────────
# 공통 유틸
# ────────────────────────────────────────────────
def last_business_day_of_month(year: int, month: int) -> date:
    last_day = monthrange(year, month)[1]
    d = date(year, month, last_day)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def iter_months(start_ym: str, end_ym: str):
    sy, sm = int(start_ym[:4]), int(start_ym[4:])
    ey, em = int(end_ym[:4]), int(end_ym[4:])
    y, m = sy, sm
    while (y, m) <= (ey, em):
        yield y, m
        m += 1
        if m > 12:
            y, m = y + 1, 1


def load_json(path):
    if not os.path.exists(path):
        return {"data": {}, "positions": {}, "signals": {}}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(obj, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def default_end_ym():
    now = datetime.now()
    py = now.year if now.month > 1 else now.year - 1
    pm = now.month - 1 if now.month > 1 else 12
    return f"{py}{pm:02d}"


# ────────────────────────────────────────────────
# pykrx (지연 로딩)
# ────────────────────────────────────────────────
def _load_pykrx():
    _CRED_FILE = Path("/var/autobot/KIS/KRX_nkr.txt")
    if _CRED_FILE.is_file():
        _lines = [ln.strip() for ln in _CRED_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if len(_lines) >= 2:
            os.environ.setdefault("KRX_ID", _lines[0])
            os.environ.setdefault("KRX_PW", _lines[1])
    _buf, _stdout = io.StringIO(), sys.stdout
    sys.stdout = _buf
    from pykrx import stock
    sys.stdout = _stdout
    return stock


# ────────────────────────────────────────────────
# Phase 1: KOSPI/KOSDAQ/PBR (pykrx)
# ────────────────────────────────────────────────
def find_actual_trading_close(stock, target: date, lookback: int = 7):
    for i in range(lookback):
        d = target - timedelta(days=i)
        ymd = d.strftime("%Y%m%d")
        try:
            kospi_df  = stock.get_index_ohlcv(ymd, ymd, "1001")
            kosdaq_df = stock.get_index_ohlcv(ymd, ymd, "2001")
        except Exception:
            continue
        if kospi_df.empty or kosdaq_df.empty:
            continue
        return d, float(kospi_df["종가"].iloc[-1]), float(kosdaq_df["종가"].iloc[-1])
    return None, None, None


def get_kospi_pbr(stock, ymd: str):
    try:
        fund = stock.get_market_fundamental(date=ymd, market="KOSPI")
        cap = stock.get_market_cap_by_ticker(date=ymd, market="KOSPI")
    except Exception:
        return None
    if fund.empty or cap.empty:
        return None
    df = fund.join(cap[["시가총액", "상장주식수"]]).dropna()
    df = df[(df["BPS"] > 0) & (df["시가총액"] > 0) & (df["상장주식수"] > 0)]
    if df.empty:
        return None
    total_cap = df["시가총액"].sum()
    total_equity = (df["BPS"] * df["상장주식수"]).sum()
    if total_equity <= 0:
        return None
    return round(float(total_cap / total_equity), 4)


def backfill_kospi(start_ym: str, end_ym: str):
    print(f"[Phase 1] KOSPI/KOSDAQ/PBR 백필: {start_ym} ~ {end_ym}")
    stock = _load_pykrx()

    obj = load_json(MONTHLY_JSON_PATH)
    obj.setdefault("data", {})

    written = 0
    failed = []

    for y, m in iter_months(start_ym, end_ym):
        ym = f"{y}-{m:02d}"
        existing = obj["data"].get(ym, {})
        if existing.get("kospi") and existing.get("kospi_pbr") is not None:
            continue

        target = last_business_day_of_month(y, m)
        actual, kospi, kosdaq = find_actual_trading_close(stock, target)
        if actual is None:
            print(f"  [{ym}] 거래일 조회 실패")
            failed.append(ym)
            continue

        ymd_actual = actual.strftime("%Y%m%d")
        time.sleep(0.3)
        pbr = get_kospi_pbr(stock, ymd_actual)
        time.sleep(0.3)

        existing.update({
            "kospi":         round(kospi, 2),
            "kosdaq":        round(kosdaq, 2),
            "kospi_pbr":     pbr,
            "vkospi":        existing.get("vkospi"),
            "trading_date":  actual.isoformat(),
            "updated_at":    datetime.now().isoformat(timespec="seconds"),
        })
        obj["data"][ym] = existing
        written += 1
        print(f"  [{ym}] trade={actual} KOSPI={kospi:>8.2f} KOSDAQ={kosdaq:>8.2f} PBR={pbr}")

        if written % 50 == 0:
            save_json(obj, MONTHLY_JSON_PATH)
            print(f"  [중간저장] {written}건")

    save_json(obj, MONTHLY_JSON_PATH)
    print(f"\n[Phase 1] 완료: 신규 {written}건, 실패 {len(failed)}건")
    if failed:
        print(f"  실패월: {failed}")


# ────────────────────────────────────────────────
# Phase 2: VKOSPI (KIS API)
# ────────────────────────────────────────────────
def _kis_init():
    sys.path.insert(0, "/var/autobot")
    sys.path.insert(0, "/var/autobot/TR_KRFT")
    from KIS_KR import KIS_API
    return KIS_API(KIS_KEY_FILE, KIS_TOKEN_FILE, "64753341", "03")


def fetch_vkospi_daily(kis, start_ymd: str, end_ymd: str) -> dict:
    """
    KIS 일별 지수 시세로 VKOSPI 조회 (페이징).
    Returns: {YYYY-MM-DD: float} 종가 dict
    """
    url = f"{kis.url_base}/uapi/domestic-stock/v1/quotations/inquire-index-daily-price"
    headers = {
        "authorization": f"Bearer {kis.access_token}",
        "appkey":        kis.app_key,
        "appsecret":     kis.app_secret,
        "tr_id":         "FHPUP02120000",
        "custtype":      "P",
    }

    result = {}
    cursor = end_ymd
    iterations = 0
    max_iter = 500   # 안전장치

    while iterations < max_iter:
        iterations += 1
        kis._rate_limit_sleep()
        params = {
            "FID_PERIOD_DIV_CODE":    "D",
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_INPUT_ISCD":         "0503",
            "FID_INPUT_DATE_1":       cursor,
        }
        try:
            r = requests.get(url, headers=headers, params=params, timeout=15)
        except requests.RequestException as e:
            print(f"    HTTP 에러: {e}")
            time.sleep(2)
            continue

        if r.status_code != 200:
            print(f"    status={r.status_code}: {r.text[:200]}")
            break

        j = r.json()
        if j.get("rt_cd") != "0":
            print(f"    rt_cd={j.get('rt_cd')}: {j.get('msg1','')}")
            break

        rows = j.get("output2") or j.get("output1") or []
        if not rows:
            break

        oldest_in_page = None
        cnt_in_page = 0
        for row in rows:
            d = row.get("stck_bsop_date")
            v = row.get("bstp_nmix_prpr")
            if not d or not v:
                continue
            try:
                fv = float(v)
            except ValueError:
                continue
            if fv <= 0:
                continue
            iso = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
            result[iso] = round(fv, 2)
            cnt_in_page += 1
            if oldest_in_page is None or d < oldest_in_page:
                oldest_in_page = d

        print(f"    page {iterations}: cursor={cursor} got={cnt_in_page} "
              f"oldest={oldest_in_page} total={len(result)}")

        if oldest_in_page is None:
            break
        if oldest_in_page <= start_ymd:
            break

        # 다음 페이지: 가장 오래된 날짜의 전일
        oldest_dt = datetime.strptime(oldest_in_page, "%Y%m%d") - timedelta(days=1)
        next_cursor = oldest_dt.strftime("%Y%m%d")
        if next_cursor == cursor:
            break
        cursor = next_cursor

    return result


def backfill_vkospi(start_ym: str, end_ym: str):
    if start_ym < VKOSPI_START:
        start_ym = VKOSPI_START
    print(f"[Phase 2] VKOSPI 백필: {start_ym} ~ {end_ym}")

    obj = load_json(MONTHLY_JSON_PATH)
    data = obj.setdefault("data", {})

    need_dates = {}
    for y, m in iter_months(start_ym, end_ym):
        ym = f"{y}-{m:02d}"
        row = data.get(ym, {})
        if row.get("vkospi") is not None:
            continue
        td = row.get("trading_date")
        if not td:
            print(f"  [{ym}] trading_date 없음 — Phase 1 먼저 실행 필요")
            continue
        need_dates[td] = ym

    if not need_dates:
        print("  채울 VKOSPI 없음 — 종료")
        return

    print(f"  대상 {len(need_dates)} 개월")

    kis = _kis_init()
    start_ymd = min(need_dates.keys()).replace("-", "")
    end_ymd   = max(need_dates.keys()).replace("-", "")
    print(f"  KIS 일별 조회 범위: {start_ymd} ~ {end_ymd}")

    vk_map = fetch_vkospi_daily(kis, start_ymd, end_ymd)
    print(f"\n  수신: {len(vk_map)}일치")

    written = 0
    missing = []
    for td, ym in need_dates.items():
        vk = vk_map.get(td)
        if vk is None:
            # 같은 월 내 가장 가까운 거래일로 fallback
            same_month = sorted([k for k in vk_map.keys() if k.startswith(ym)])
            if same_month:
                vk = vk_map[same_month[-1]]
                print(f"  [{ym}] {td} 매칭실패 → {same_month[-1]} fallback = {vk}")
        if vk is None:
            missing.append(ym)
            continue
        data[ym]["vkospi"] = vk
        data[ym]["updated_at"] = datetime.now().isoformat(timespec="seconds")
        written += 1

    save_json(obj, MONTHLY_JSON_PATH)
    print(f"\n[Phase 2] 완료: 신규 {written}건 / 미매칭 {len(missing)}건")
    if missing:
        head = missing[:20]
        tail = "..." if len(missing) > 20 else ""
        print(f"  미매칭월: {head}{tail}")


# ────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────
def main():
    mode  = sys.argv[1] if len(sys.argv) > 1 else "auto"
    start = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_START
    end   = sys.argv[3] if len(sys.argv) > 3 else default_end_ym()

    print(f"모드={mode} 범위={start}~{end}")
    print()

    if mode == "kospi":
        backfill_kospi(start, end)
    elif mode == "vkospi":
        backfill_vkospi(start, end)
    elif mode == "auto":
        try:
            _load_pykrx()
            has_pykrx = True
        except ImportError:
            has_pykrx = False
            print("[INFO] pykrx 미설치 — Phase 1 스킵")

        if has_pykrx:
            backfill_kospi(start, end)
            print()

        try:
            _kis_init()
            backfill_vkospi(start, end)
        except (FileNotFoundError, SystemExit, ImportError) as e:
            print(f"[Phase 2 스킵] KIS 초기화 불가: {e}")
    else:
        print(f"Unknown mode: {mode}")
        print("Usage: backfill_monthly.py [kospi|vkospi|auto] [START] [END]")
        sys.exit(2)


if __name__ == "__main__":
    main()
