# -*- coding: utf-8 -*-
"""
KRFT_data.py
============
월말 시장 데이터 수집 및 krfuture_monthly.json 업데이트.

수집 데이터:
  - KOSPI 지수    (KIS API, FHPUP02100000 / TR='FHPUP02100000')
  - KOSDAQ 지수   (KIS API)
  - VKOSPI 지수   (KIS API)
  - KOSPI PBR     (KRX → kospi_pbr.py / 별도 venv 실행 → JSON 캐시 사용)

PBR 환산:
  KRX PBR은 그 KRX 기준일의 KOSPI 종가 기준값.
  당월말 KIS 시점 KOSPI와의 비율로 환산:
    PBR_now = PBR_krx * (kospi_kis_now / kospi_krx_basedate)
  (PBR = 시총/자본 이고 자본은 일별로 거의 안 변하므로 가격비율로 근사)
"""
from __future__ import annotations
import json
import os
import time
import requests
from datetime import datetime, date
from pathlib import Path
from typing import Optional

# ------------------------------------------------------------------
# 경로 설정 (운영 환경에 맞춰 조정)
# ------------------------------------------------------------------
MONTHLY_JSON_PATH = "/var/autobot/TR_KRFT/krfuture_monthly.json"
KOSPI_PBR_CACHE   = "/var/autobot/Cache/kospi_pbr.json"   # kospi_pbr.py가 venv에서 미리 저장
BASE_URL          = "https://openapi.koreainvestment.com:9443"


# ------------------------------------------------------------------
# KIS API: 지수 현재가
# ------------------------------------------------------------------
def _index_headers(kis, tr_id: str) -> dict:
    return {
        "authorization": f"Bearer {kis.access_token}",
        "appkey":        kis.app_key,
        "appsecret":     kis.app_secret,
        "tr_id":         tr_id,
        "custtype":      "P",
    }


def get_index_value(kis, market: str, code: str) -> Optional[float]:
    """
    KIS 국내 지수 현재가.
    market: 'U'(업종) / 'V'(VKOSPI는 'U'로 조회되며 코드 '20'대 사용)
    code  :
      - KOSPI            : '0001'
      - KOSDAQ           : '1001'
      - KOSPI200         : '2001'
      - VKOSPI           : '0050'   (실시간 변동성지수)

    TR: FHPUP02100000 (국내업종 현재지수)
    """
    kis._rate_limit_sleep()
    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-index-price"
    headers = _index_headers(kis, "FHPUP02100000")
    params = {
        "FID_COND_MRKT_DIV_CODE": market,
        "FID_INPUT_ISCD":         code,
    }
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        if r.status_code != 200:
            return None
        j = r.json()
        if j.get("rt_cd") != "0":
            return None
        out = j.get("output") or {}
        return float(out.get("bstp_nmix_prpr", 0) or 0)
    except Exception:
        return None


def get_kospi(kis) -> Optional[float]:
    return get_index_value(kis, "U", "0001")


def get_kosdaq(kis) -> Optional[float]:
    return get_index_value(kis, "U", "1001")


def get_vkospi(kis) -> Optional[float]:
    # VKOSPI 코드 = '0050' (KIS 국내업종 표준)
    return get_index_value(kis, "U", "0050")


# ------------------------------------------------------------------
# KRX PBR 캐시 로드
# ------------------------------------------------------------------
def load_krx_pbr_cache() -> Optional[dict]:
    """
    kospi_pbr.py (venv_krx) 가 미리 저장해둔 JSON 캐시 로드.

    캐시 포맷:
      {
        "date":        "2026-05-14",   # KRX 기준일
        "pbr":         0.984,
        "kospi_close": 2680.45,        # 그 KRX 기준일의 KOSPI 종가 (필수)
        "computed_at": "2026-05-14T16:35:00"
      }
    """
    if not os.path.exists(KOSPI_PBR_CACHE):
        return None
    try:
        with open(KOSPI_PBR_CACHE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not all(k in data for k in ("date", "pbr", "kospi_close")):
            return None
        return data
    except Exception:
        return None


def adjust_pbr_to_kis_time(krx_pbr: float, krx_kospi: float,
                            kis_kospi: float) -> float:
    """
    KRX 기준일 PBR을 KIS 호출 시점 KOSPI 가격으로 환산.
    PBR = 시가총액 / 자본총계 이고, 자본총계는 일별 거의 불변 가정.
    """
    if krx_kospi <= 0:
        return krx_pbr
    return krx_pbr * (kis_kospi / krx_kospi)


# ------------------------------------------------------------------
# monthly.json 입출력
# ------------------------------------------------------------------
def load_monthly(path: str = MONTHLY_JSON_PATH) -> dict:
    if not os.path.exists(path):
        return {"data": {}, "positions": {}, "signals": {}}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_monthly(obj: dict, path: str = MONTHLY_JSON_PATH) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ------------------------------------------------------------------
# 메인: 월말 데이터 갱신
# ------------------------------------------------------------------
def update_monthly_data(kis, today: date,
                        pbr_override: Optional[float] = None,
                        vkospi_override: Optional[float] = None) -> dict:
    """
    월말 데이터 수집 → krfuture_monthly.json["data"][YYYY-MM] 에 저장.

    Returns:
      {
        "ok": bool,
        "ym": "2026-05",
        "kospi":   float,
        "kosdaq":  float,
        "vkospi":  float,
        "kospi_pbr": float,
        "messages": [...]
      }
    """
    messages = []
    ym = today.strftime("%Y-%m")

    # 1) KIS 지수
    kospi = get_kospi(kis)
    if kospi is None or kospi <= 0:
        return {"ok": False, "ym": ym,
                "messages": ["KIS KOSPI 조회 실패"]}
    time.sleep(0.15)

    kosdaq = get_kosdaq(kis)
    if kosdaq is None or kosdaq <= 0:
        return {"ok": False, "ym": ym,
                "messages": ["KIS KOSDAQ 조회 실패"]}
    time.sleep(0.15)

    vkospi = vkospi_override if vkospi_override is not None else get_vkospi(kis)
    if vkospi is None or vkospi <= 0:
        # VKOSPI 조회 실패 시 이전 월 값 사용 (보수적 처리)
        prev = load_monthly()
        prev_ym = max(
            (k for k in prev["data"].keys() if k < ym),
            default=None,
        )
        if prev_ym:
            vkospi = float(prev["data"][prev_ym].get("vkospi", 0) or 0)
            messages.append(f"VKOSPI 조회 실패 → 직전월({prev_ym}) 값 {vkospi} 사용")
        else:
            return {"ok": False, "ym": ym,
                    "messages": ["VKOSPI 조회 실패 (이력 없음)"]}

    # 2) KOSPI PBR (override 우선, 없으면 KRX 캐시 환산)
    if pbr_override is not None:
        kospi_pbr = float(pbr_override)
        messages.append(f"PBR override 사용: {kospi_pbr}")
    else:
        krx = load_krx_pbr_cache()
        if not krx:
            return {"ok": False, "ym": ym,
                    "messages": [f"KRX PBR 캐시 없음: {KOSPI_PBR_CACHE} 확인. "
                                 "venv_krx로 kospi_pbr.py 먼저 실행 필요."]}
        kospi_pbr = adjust_pbr_to_kis_time(
            krx_pbr=float(krx["pbr"]),
            krx_kospi=float(krx["kospi_close"]),
            kis_kospi=kospi,
        )
        kospi_pbr = round(kospi_pbr, 4)
        messages.append(
            f"PBR 환산: KRX {krx['pbr']} @ KOSPI {krx['kospi_close']} "
            f"→ KIS KOSPI {kospi:.2f} → PBR {kospi_pbr}"
        )

    # 3) 저장
    obj = load_monthly()
    obj.setdefault("data", {})[ym] = {
        "kospi":      round(float(kospi), 2),
        "kosdaq":     round(float(kosdaq), 2),
        "kospi_pbr":  kospi_pbr,
        "vkospi":     round(float(vkospi), 2),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    save_monthly(obj)

    return {
        "ok":         True,
        "ym":         ym,
        "kospi":      float(kospi),
        "kosdaq":     float(kosdaq),
        "vkospi":     float(vkospi),
        "kospi_pbr":  kospi_pbr,
        "messages":   messages,
    }
