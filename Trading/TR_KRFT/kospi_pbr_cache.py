"""
kospi_pbr_cache.py (최종 확정판)
=================================
KRX 공식 KOSPI 지수 PBR 및 기준 종가를 야간에 캐시 저장.
KRFT_data.py 의 PBR 시점 환산용 데이터 공급원.

[변경 사항 (2026-05-21)]
- 자체 산식(종목별 BPS×상장주식수 합산) → KRX 공식 지수 PBR 직접 사용
  · pykrx.stock.get_index_fundamental(date, date, "1001")
  · KRX 정보데이터시스템 공시값과 동일
- 룩백 14일로 확장 (연휴/임시휴장 대비)
- PER, 배당수익률도 함께 저장 (확장성)
- 자체 산식 추정값(pbr_estimated)도 검증용으로 함께 기록
- 호환성: 기존 키 "pbr", "kospi_close" 유지 (KRFT_data.py 무수정)

실행 환경:
    venv_krx (Python 3.10+, pykrx 사용 가능)

crontab (UTC) - 평일 KST 20:15 = UTC 11:15:
    15 11 * * 1-5 timeout -s 9 3m /var/autobot/venv_krx/bin/python \\
        /var/autobot/TR_KRFT/kospi_pbr_cache.py \\
        >> /var/autobot/Logs/kospi_pbr.log 2>&1

출력 파일: /var/autobot/Cache/kospi_pbr.json
    {
      "date":          "2026-05-20",
      "pbr":           2.21,          # 구 키 (KRX 공식값)
      "kospi_close":   7208.95,       # 구 키
      "pbr_official":  2.21,          # 신규 (명시적)
      "per_official":  27.44,
      "div_yield":     0.88,
      "base_close":    7208.95,
      "pbr_estimated": 2.2315,        # 검증용 (종목별 합산 추정)
      "computed_at":   "2026-05-20T20:15:00"
    }
"""
import io
import os
import sys
import json
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


CACHE_PATH = "/var/autobot/Cache/kospi_pbr.json"


def _save_cache(payload: dict) -> None:
    Path(CACHE_PATH).parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CACHE_PATH)


def compute_kospi_pbr_with_close(max_lookback: int = 14) -> dict:
    """
    최신 영업일 기준 KRX 공식 KOSPI 지수 PBR + 같은 기준일의 KOSPI 종가.

    KRX 공식 산식 사용:
      pykrx.stock.get_index_fundamental(ymd, ymd, "1001")
      → KRX 정보데이터시스템 KOSPI 지수 PBR/PER/배당수익률 공식값.

    Returns:
      {
        "date":          "YYYY-MM-DD",
        "pbr":           float,    # 구 키 (= pbr_official)
        "kospi_close":   float,    # 구 키 (= base_close)
        "pbr_official":  float,    # KRX 공식 KOSPI 지수 PBR
        "per_official":  float,    # KRX 공식 PER
        "div_yield":     float,    # KRX 공식 배당수익률 (%)
        "base_close":    float,    # 같은 기준일 KOSPI 종가
        "pbr_estimated": float,    # 종목별 합산 추정치 (검증용)
        "computed_at":   "ISO datetime"
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
        # 주말 사전 스킵 (불필요한 API 호출 감소)
        if d.weekday() >= 5:
            continue
        ymd = d.strftime("%Y%m%d")

        # 1) KRX 공식 KOSPI 지수 PBR
        try:
            idx_fund = stock.get_index_fundamental(ymd, ymd, "1001")
        except Exception:
            continue
        if idx_fund is None or idx_fund.empty:
            continue

        try:
            pbr_official = float(idx_fund["PBR"].iloc[-1])
            per_official = float(idx_fund["PER"].iloc[-1])
            div_yield    = float(idx_fund["배당수익률"].iloc[-1])
        except (KeyError, ValueError, IndexError):
            continue

        # PBR이 0이면 당일 미공시 → 더 이전 영업일로
        if pbr_official <= 0:
            continue

        # 2) 같은 기준일 KOSPI 종가 (장중 환산 기준점)
        try:
            ohlcv = stock.get_index_ohlcv(ymd, ymd, "1001")
        except Exception:
            continue
        if ohlcv is None or ohlcv.empty:
            continue
        base_close = float(ohlcv["종가"].iloc[-1])
        if base_close <= 0:
            continue

        # 3) 종목별 합산 추정치 (검증용, 실패해도 결과 반환)
        pbr_estimated = None
        try:
            fund = stock.get_market_fundamental(date=ymd, market="KOSPI")
            cap = stock.get_market_cap_by_ticker(date=ymd, market="KOSPI")
            if not fund.empty and not cap.empty:
                df = fund.join(cap[["시가총액", "상장주식수"]]).dropna()
                df = df[
                    (df["BPS"] > 0)
                    & (df["시가총액"] > 0)
                    & (df["상장주식수"] > 0)
                ]
                if not df.empty:
                    total_cap = df["시가총액"].sum()
                    total_equity = (df["BPS"] * df["상장주식수"]).sum()
                    if total_equity > 0:
                        pbr_estimated = round(
                            float(total_cap / total_equity), 4
                        )
        except Exception:
            pass

        return {
            "date":          d.strftime("%Y-%m-%d"),
            # 구 키 호환성 유지 (KRFT_data.py 무수정 가능)
            "pbr":           round(pbr_official, 4),
            "kospi_close":   round(base_close, 2),
            # 신규 명시적 키
            "pbr_official":  round(pbr_official, 4),
            "per_official":  round(per_official, 4),
            "div_yield":     round(div_yield, 4),
            "base_close":    round(base_close, 2),
            "pbr_estimated": pbr_estimated,
            "computed_at":   datetime.now().isoformat(timespec="seconds"),
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
    print(f"  date           = {payload['date']}")
    print(f"  pbr (KRX 공식) = {payload['pbr_official']}")
    print(f"  per            = {payload['per_official']}")
    print(f"  div_yield (%)  = {payload['div_yield']}")
    print(f"  base_close     = {payload['base_close']}")
    print(f"  pbr_estimated  = {payload['pbr_estimated']}  (자체 추정, 검증용)")
    print(f"  computed_at    = {payload['computed_at']}")

    # 공식값 vs 추정값 차이 경고
    if payload.get("pbr_estimated"):
        diff = payload["pbr_official"] - payload["pbr_estimated"]
        diff_pct = (diff / payload["pbr_official"]) * 100
        if abs(diff_pct) > 5:
            print(
                f"[WARN] 공식 PBR과 추정 PBR 차이 {diff_pct:+.2f}% "
                f"(공식={payload['pbr_official']}, 추정={payload['pbr_estimated']})"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
