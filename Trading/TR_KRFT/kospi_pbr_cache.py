"""
kospi_pbr_cache.py
==================
KOSPI 시장 PBR + 같은 기준일의 KOSPI 종가를 JSON 캐시로 저장.
KRFT_data.py 의 PBR 시점 환산용 데이터 공급원.

실행 환경:
    venv_krx (Python 3.10+, pykrx 사용 가능)

crontab (UTC):
    # 매월 말 영업일 16:30 KST = 07:30 UTC, 말일 28-31 매일 시도
    30 7 28-31 * 1-5 timeout -s 9 3m /var/autobot/venv_krx/bin/python \
        /var/autobot/TR_KRFT/kospi_pbr_cache.py \
        >> /var/autobot/Logs/kospi_pbr.log 2>&1

출력 파일: /var/autobot/Cache/kospi_pbr.json
    {
      "date":        "2026-05-14",   # KRX 영업일 기준
      "pbr":         0.984,           # KRX 공식 산식 (시총합/자본총계합)
      "kospi_close": 2680.45,         # 같은 기준일의 KOSPI 종가
      "computed_at": "2026-05-14T16:35:00"
    }
"""
import io
import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

# 자격증명 파일 절대경로 (kospi_pbr.py와 동일)
_CRED_FILE = Path("/var/autobot/KIS/KRX_nkr.txt")

# pykrx import 전에 환경변수 주입
if _CRED_FILE.is_file():
    _lines = [
        ln.strip()
        for ln in _CRED_FILE.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    if len(_lines) >= 2:
        os.environ.setdefault("KRX_ID", _lines[0])
        os.environ.setdefault("KRX_PW", _lines[1])

# pykrx import 시 출력되는 KRX 안내 로그 차단
_buf, _stdout = io.StringIO(), sys.stdout
sys.stdout = _buf
from pykrx import stock  # noqa: E402
sys.stdout = _stdout


CACHE_PATH = "/var/autobot/Cache/kospi_pbr.json"


def _save_cache(payload: dict) -> None:
    Path(CACHE_PATH).parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CACHE_PATH)


def compute_kospi_pbr_with_close(max_lookback: int = 7) -> dict:
    """
    최신 영업일 기준 KOSPI 시장 PBR + 같은 기준일의 KOSPI 종가.

    Returns:
      {
        "date":        "YYYY-MM-DD",
        "pbr":         float,
        "kospi_close": float,
        "computed_at": "ISO datetime"
      }

    Raises:
      RuntimeError : 인증 누락 또는 룩백 기간 내 유효 데이터 없음
    """
    if not (os.getenv("KRX_ID") and os.getenv("KRX_PW")):
        raise RuntimeError(
            f"KRX 자격증명 누락: {_CRED_FILE} 파일을 확인하세요 "
            "(1행 ID, 2행 PW)."
        )

    today = datetime.now()
    for i in range(max_lookback):
        d = today - timedelta(days=i)
        ymd = d.strftime("%Y%m%d")
        try:
            # 1) PBR 계산용 데이터
            fund = stock.get_market_fundamental(date=ymd, market="KOSPI")
            cap = stock.get_market_cap_by_ticker(date=ymd, market="KOSPI")
        except Exception:
            continue

        if fund.empty or cap.empty:
            continue

        df = fund.join(cap[["시가총액", "상장주식수"]]).dropna()
        df = df[
            (df["BPS"] > 0)
            & (df["시가총액"] > 0)
            & (df["상장주식수"] > 0)
        ]
        if df.empty:
            continue

        total_cap = df["시가총액"].sum()
        total_equity = (df["BPS"] * df["상장주식수"]).sum()
        if total_equity <= 0:
            continue

        pbr = round(float(total_cap / total_equity), 4)

        # 2) 같은 기준일의 KOSPI 종가 (index code "1001" = KOSPI)
        try:
            ohlcv = stock.get_index_ohlcv(ymd, ymd, "1001")
        except Exception:
            ohlcv = None

        if ohlcv is None or ohlcv.empty:
            # 종가를 받지 못하면 이 영업일은 스킵 (정합성 보장 위해)
            continue

        kospi_close = float(ohlcv["종가"].iloc[-1])
        if kospi_close <= 0:
            continue

        return {
            "date":         d.strftime("%Y-%m-%d"),
            "pbr":          pbr,
            "kospi_close":  round(kospi_close, 2),
            "computed_at":  datetime.now().isoformat(timespec="seconds"),
        }

    raise RuntimeError(
        f"KOSPI PBR/종가 조회 실패: 최근 {max_lookback}일 룩백 내 "
        "유효 데이터 없음."
    )


def main() -> int:
    try:
        payload = compute_kospi_pbr_with_close()
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1

    _save_cache(payload)
    print(f"[OK] 캐시 저장: {CACHE_PATH}")
    print(f"  date        = {payload['date']}")
    print(f"  pbr         = {payload['pbr']}")
    print(f"  kospi_close = {payload['kospi_close']}")
    print(f"  computed_at = {payload['computed_at']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
