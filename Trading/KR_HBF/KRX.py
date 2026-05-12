"""
V-KOSPI200 크롤링 - 두 가지 방식
"""
from __future__ import annotations  # float | None 등 PEP 604 문법을 3.9에서도 사용

import requests
import pandas as pd
from io import StringIO
from datetime import date, timedelta
import time


# ══════════════════════════════════════════════════════
# 방식 A: pykrx 라이브러리 (가장 안정적)
# pip install pykrx --break-system-packages
# ══════════════════════════════════════════════════════
def get_vkospi_pykrx(lookback_days: int = 1) -> float | None:
    """
    pykrx로 V-KOSPI200 최근값 조회.
    장중에는 전일 종가, 장 마감 후 당일 종가 반환.
    """
    try:
        from pykrx import stock
        today = date.today().strftime("%Y%m%d")
        start = (date.today() - timedelta(days=lookback_days + 5)).strftime("%Y%m%d")
        # V-KOSPI200 티커: "1174"
        df = stock.get_index_ohlcv(start, today, "1174")
        if df.empty:
            return None
        return float(df["종가"].iloc[-1])
    except Exception as e:
        print(f"[pykrx 오류] {e}")
        return None


def get_vkospi_history_pykrx(start_date: str, end_date: str) -> pd.DataFrame:
    """
    pykrx로 V-KOSPI200 일별 이력 조회.
    start_date, end_date: "YYYYMMDD"
    """
    from pykrx import stock
    df = stock.get_index_ohlcv(start_date, end_date, "1174")
    if df.empty or "종가" not in df.columns:
        return pd.DataFrame(columns=["V-KOSPI200"])
    df = df[["종가"]].rename(columns={"종가": "V-KOSPI200"})
    df.index.name = "날짜"
    return df


# ══════════════════════════════════════════════════════
# 방식 B: KRX 직접 크롤링 (세션 방식)
# ══════════════════════════════════════════════════════
_KRX_BASE   = "http://data.krx.co.kr"
_JSON_URL   = f"{_KRX_BASE}/comm/bldAttendant/getJsonData.cmd"
_OTP_URL    = f"{_KRX_BASE}/comm/fileDn/GenerateOTP/generate.cmd"
_DOWN_URL   = f"{_KRX_BASE}/comm/fileDn/download_csv/download.cmd"
_VKOSPI_TICKER = "1174"    # KRX 내부 V-KOSPI200 지수 코드


def _make_session() -> requests.Session:
    """KRX 세션 쿠키 획득"""
    session = requests.Session()
    browser_hdr = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }
    # 메인 → 지수 페이지 순서로 방문해야 JSESSIONID 발급
    session.get(f"{_KRX_BASE}/contents/MDC/MAIN/main/index.cmd",
                headers=browser_hdr, timeout=10)
    session.get(
        f"{_KRX_BASE}/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201010101",
        headers=browser_hdr, timeout=10,
    )
    return session


def get_vkospi_direct(retry: int = 3) -> float | None:
    """
    KRX 직접 크롤링으로 V-KOSPI200 현재값 반환.
    """
    today = date.today().strftime("%Y%m%d")
    session = _make_session()

    api_hdr = {
        "User-Agent": "Mozilla/5.0 Chrome/124.0",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": _KRX_BASE,
        "Referer": f"{_KRX_BASE}/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201010101",
        "X-Requested-With": "XMLHttpRequest",
    }

    # 지수 전종목 시세 조회 (idxIndMidclssCd=04 = 파생/변동성 계열)
    payload = {
        "bld":               "dbms/MDC/STAT/standard/MDCSTAT00101",
        "locale":            "ko_KR",
        "trdDd":             today,
        "idxIndMidclssCd":   "04",   # ← 변동성 지수 분류
        "share":             "1",
        "money":             "1",
        "csvxls_isNo":       "false",
    }

    for attempt in range(retry):
        try:
            r = session.post(_JSON_URL, headers=api_hdr, data=payload, timeout=10)
            r.raise_for_status()
            rows = r.json().get("OutBlock_1", [])
            for row in rows:
                name = row.get("IDX_NM", "")
                if "V-KOSPI" in name or "변동성" in name:
                    val = str(row.get("CLSPRC", "")).replace(",", "").strip()
                    if val and val != "-":
                        return float(val)
        except Exception as e:
            print(f"[시도 {attempt+1}] {e}")
            if attempt < retry - 1:
                time.sleep(2)
    return None


def get_vkospi_history_direct(start_date: str, end_date: str) -> pd.DataFrame:
    """
    KRX OTP → CSV 방식으로 V-KOSPI200 일별 이력 다운로드.
    start_date, end_date: "YYYYMMDD"
    """
    session = _make_session()
    api_hdr = {
        "User-Agent": "Mozilla/5.0 Chrome/124.0",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": _KRX_BASE,
        "Referer": f"{_KRX_BASE}/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201010101",
        "X-Requested-With": "XMLHttpRequest",
    }

    # OTP 발급
    otp_params = {
        "locale":          "ko_KR",
        "idxIndMidclssCd": "04",
        "strtDd":          start_date,
        "endDd":           end_date,
        "share":           "1",
        "money":           "1",
        "csvxls_isNo":     "false",
        "name":            "fileDown",
        "url":             "dbms/MDC/STAT/standard/MDCSTAT00301",
    }
    otp_r = session.post(_OTP_URL, headers=api_hdr, data=otp_params, timeout=10)
    otp = otp_r.text.strip()
    if not otp or otp.upper() == "LOGOUT":
        print(f"[OTP 실패] 응답: {otp}")
        return pd.DataFrame()

    # CSV 다운로드
    down_r = session.post(_DOWN_URL, data={"code": otp},
                          headers=api_hdr, timeout=15)
    down_r.encoding = "euc-kr"
    try:
        df = pd.read_csv(StringIO(down_r.text), thousands=",")
        # V-KOSPI200 행 필터
        name_col  = next((c for c in df.columns if "지수명" in c or "IDX_NM" in c), None)
        date_col  = next((c for c in df.columns if "날짜" in c or "일자" in c), None)
        price_col = next((c for c in df.columns if "종가" in c or "현재가" in c), None)

        if name_col:
            df = df[df[name_col].str.contains("V-KOSPI|변동성", na=False)]
        if date_col and price_col:
            df = df[[date_col, price_col]].copy()
            df.columns = ["날짜", "V-KOSPI200"]
            df["날짜"] = pd.to_datetime(df["날짜"], errors="coerce")
            df["V-KOSPI200"] = df["V-KOSPI200"].astype(str).str.replace(",","").astype(float)
            return df.dropna().sort_values("날짜").reset_index(drop=True)
    except Exception as e:
        print(f"[파싱 오류] {e}")
    return pd.DataFrame()


# ══════════════════════════════════════════════════════
# 실행 예시
# ══════════════════════════════════════════════════════
if __name__ == "__main__":
    # 방식 A: pykrx (권장)
    val = get_vkospi_pykrx()
    print(f"V-KOSPI200 (pykrx): {val}")

    # 방식 B: KRX 직접
    val2 = get_vkospi_direct()
    print(f"V-KOSPI200 (직접): {val2}")

    # 이력 조회 (pykrx)
    df = get_vkospi_history_pykrx("20250101", "20250418")
    print(df.tail(5))