"""
kospi_pbr.py
============
KOSPI 시장 PBR을 (기준일, 값) 형태로 반환.
전략 게이트(밸류 진입조건 판단)용.

산식 (KRX 공식과 동일):
    PBR_market = sum(시가총액) / sum(자본총계)
    자본총계   = BPS * 상장주식수

인증:
    /var/autobot/KIS/KRX_nkr.txt 에서 자격증명을 읽어 환경변수에 주입.
    1행 = KRX ID, 2행 = KRX PW

사용:
    from kospi_pbr import get_kospi_pbr
    date, pbr = get_kospi_pbr()      # ('2026-05-08', 0.984)
"""
import io
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 자격증명 파일 절대경로
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


def get_kospi_pbr(max_lookback: int = 7) -> tuple[str, float]:
    """
    최신 영업일 기준 KOSPI 시장 PBR을 반환 (KRX 공식 산식).

    Returns
    -------
    (기준일 'YYYY-MM-DD', PBR 소수3자리)

    Raises
    ------
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
            fund = stock.get_market_fundamental(date=ymd, market="KOSPI")
            cap = stock.get_market_cap_by_ticker(date=ymd, market="KOSPI")
        except Exception:
            continue

        if fund.empty or cap.empty:
            continue

        df = fund.join(cap[["시가총액", "상장주식수"]]).dropna()
        # BPS, 시가총액, 상장주식수가 모두 양수인 종목만
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

        pbr = total_cap / total_equity
        return d.strftime("%Y-%m-%d"), round(float(pbr), 3)

    raise RuntimeError(
        f"KOSPI PBR 조회 실패: 최근 {max_lookback}일 룩백 내 유효 데이터 없음."
    )


if __name__ == "__main__":
    date, pbr = get_kospi_pbr()
    print(f"[KOSPI] 기준일={date}  시장 PBR={pbr}")
