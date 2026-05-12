"""
vkospi_crawler.py
- Investing.com에서 VKOSPI 일별 historical data 크롤링
- HTML 파싱 없이 페이지 임베디드 JSON(__NEXT_DATA__)에서 추출
- 의존성: pip install curl_cffi
"""
from __future__ import annotations
import json
import re
from datetime import datetime
from curl_cffi import requests as cffi_req

URL = "https://kr.investing.com/indices/kospi-volatility-historical-data"
_NEXT_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)


def fetch_vkospi(timeout: int = 20) -> list[dict]:
    """
    Investing.com VKOSPI 일별 시세 반환 (최신순, 약 20영업일).

    각 dict 필드:
      date  : 'YYYY-MM-DD' (str)
      close : float (종가)
      open  : float
      high  : float
      low   : float
      change_pct : float (%, 등락률)
    """
    r = cffi_req.get(URL, impersonate="chrome", timeout=timeout)
    r.raise_for_status()

    m = _NEXT_RE.search(r.text)
    if not m:
        raise RuntimeError("페이지에서 __NEXT_DATA__를 찾지 못했습니다.")
    payload = json.loads(m.group(1))

    rows = payload["props"]["pageProps"]["state"] \
                  ["historicalDataStore"]["historicalData"]["data"]

    out = []
    for row in rows:
        out.append({
            "date":       row["rowDateTimestamp"][:10],   # 'YYYY-MM-DD'
            "close":      float(row["last_closeRaw"]),
            "open":       float(row["last_openRaw"]),
            "high":       float(row["last_maxRaw"]),
            "low":        float(row["last_minRaw"]),
            "change_pct": float(row["change_precentRaw"]),
        })
    return out


if __name__ == "__main__":
    data = fetch_vkospi()
    print(f"fetched {len(data)} rows  (최신: {data[0]['date']})")
    for d in data[:5]:
        print(d)