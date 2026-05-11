"""
krx_market_caching.py
=====================
KOSPI 시장 PBR + 주요 지수 (KOSPI, KOSPI 200, VKOSPI, KOSDAQ, KOSDAQ 150)
를 한 번에 조회해 JSON 캐시 파일로 저장.

venv_krx (Python 3.12 + pykrx 1.2.8) 환경에서 실행.

지수 티커 (pykrx 기준):
    1001 = 코스피
    1028 = 코스피 200
    1320 = 코스피 변동성지수 (VKOSPI)
    2001 = 코스닥
    2203 = 코스닥 150

산식 (KOSPI 시장 PBR, KRX 공식과 동일):
    PBR_market = sum(시가총액) / sum(BPS * 상장주식수)

실행 (crontab):
    30 16 * * 1-5 /var/autobot/venv_krx/bin/python \
        /var/autobot/KR_HBF/krx_market_caching.py

출력:
    /var/autobot/Cache/krx_market.json
"""
import io
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

CRED_FILE = Path("/var/autobot/KIS/KRX_nkr.txt")
CACHE_FILE = Path("/var/autobot/Cache/krx_market.json")
KST = timezone(timedelta(hours=9))

# 조회할 지수 (티커, 라벨)
INDEX_TICKERS = [
    ("1001", "kospi"),
    ("1028", "kospi200"),
    ("1320", "vkospi"),
    ("2001", "kosdaq"),
    ("2203", "kosdaq150"),
]

# 자격증명 주입 (pykrx import 전)
if CRED_FILE.is_file():
    _lines = [
        ln.strip()
        for ln in CRED_FILE.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    if len(_lines) >= 2:
        os.environ.setdefault("KRX_ID", _lines[0])
        os.environ.setdefault("KRX_PW", _lines[1])

# pykrx import 로그 차단
_buf, _stdout = io.StringIO(), sys.stdout
sys.stdout = _buf
from pykrx import stock  # noqa: E402
sys.stdout = _stdout


def _find_business_day(max_lookback: int = 7) -> str | None:
    """최근 영업일 YYYYMMDD 반환. KOSPI 지수가 잡히는 첫 날짜."""
    today = datetime.now()
    for i in range(max_lookback):
        d = today - timedelta(days=i)
        ymd = d.strftime("%Y%m%d")
        try:
            df = stock.get_index_ohlcv(ymd, ymd, "1001")
            if not df.empty:
                return ymd
        except Exception:
            continue
    return None


def fetch_kospi_pbr(ymd: str) -> float | None:
    """KOSPI 시장 PBR (KRX 공식 산식)."""
    try:
        fund = stock.get_market_fundamental(date=ymd, market="KOSPI")
        cap = stock.get_market_cap_by_ticker(date=ymd, market="KOSPI")
    except Exception as e:
        print(f"[WARN] PBR 조회 예외: {e}", file=sys.stderr)
        return None

    if fund.empty or cap.empty:
        return None

    df = fund.join(cap[["시가총액", "상장주식수"]]).dropna()
    df = df[
        (df["BPS"] > 0)
        & (df["시가총액"] > 0)
        & (df["상장주식수"] > 0)
    ]
    if df.empty:
        return None

    total_cap = df["시가총액"].sum()
    total_equity = (df["BPS"] * df["상장주식수"]).sum()
    if total_equity <= 0:
        return None

    return round(float(total_cap / total_equity), 3)


def fetch_index_close(ticker: str, ymd: str) -> float | None:
    """특정 지수의 종가만 반환. 실패 시 None."""
    try:
        df = stock.get_index_ohlcv(ymd, ymd, ticker)
        if df.empty:
            return None
        return round(float(df["종가"].iloc[-1]), 2)
    except Exception as e:
        print(f"[WARN] 지수 {ticker} 조회 예외: {e}", file=sys.stderr)
        return None


def save_cache(payload: dict) -> None:
    """JSON 캐시 파일 저장 (원자적 쓰기)."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_FILE.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp.replace(CACHE_FILE)


def main() -> None:
    if not (os.getenv("KRX_ID") and os.getenv("KRX_PW")):
        raise RuntimeError(f"KRX 자격증명 누락: {CRED_FILE}")

    ymd = _find_business_day()
    if ymd is None:
        raise RuntimeError("최근 7일 룩백 내 KOSPI 영업일을 찾지 못함")

    date_str = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}"

    # 모든 데이터 수집
    indices: dict[str, float | None] = {}
    for ticker, label in INDEX_TICKERS:
        indices[label] = fetch_index_close(ticker, ymd)

    pbr = fetch_kospi_pbr(ymd)

    payload = {
        "date": date_str,
        "pbr": pbr,
        "indices": indices,
        "updated_at": datetime.now(KST).isoformat(timespec="seconds"),
    }

    save_cache(payload)

    # 콘솔 출력 (cron 로그용)
    print(f"[CACHED] {CACHE_FILE}")
    print(f"  기준일: {date_str}")
    print(f"  KOSPI PBR: {pbr}")
    for ticker, label in INDEX_TICKERS:
        v = indices.get(label)
        print(f"  {label:10s}: {v}")


if __name__ == "__main__":
    main()
