"""
krx_market_reader.py
====================
KRX 시장 데이터 캐시(KOSPI PBR + 주요 지수)를 읽어오는 헬퍼.
시스템 Python 3.9 (KIS-API 자동매매 환경)에서 사용.

캐시 파일:
    /var/autobot/Cache/krx_market.json
    venv_krx 의 krx_market_caching.py 가 생성/갱신

거래 스크립트에서 사용 예:
    from krx_market_reader import read_krx_market, is_pbr_below

    data = read_krx_market()
    date  = data["date"]
    pbr   = data["pbr"]
    idx   = data["indices"]            # {"kospi": ..., "kospi200": ..., ...}
    vkospi = idx.get("vkospi")

    if pbr is not None and pbr < 1.0:
        # 저평가 → 진입 허용
        ...
    if vkospi is not None and vkospi > 30:
        # 변동성 급등 → 진입 보류
        ...
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

CACHE_FILE = Path("/var/autobot/Cache/krx_market.json")
KST = timezone(timedelta(hours=9))

# 캐시 허용 최대 연령 (영업일 기준 3일). 휴장·연휴 대응.
MAX_CACHE_AGE_DAYS = 3


class KRXCacheError(RuntimeError):
    """캐시 파일이 없거나, 오래되었거나, 손상된 경우."""


def read_krx_market(strict=True):
    """
    KRX 시장 캐시 전체를 dict로 반환.

    Returns
    -------
    {
        "date":      "2026-05-08",
        "pbr":       0.984,
        "indices":   {"kospi": 3200.12, "kospi200": 432.5, "vkospi": 18.3,
                      "kosdaq": 750.2, "kosdaq150": 1320.4},
        "updated_at": "2026-05-11T16:30:01+09:00"
    }

    Parameters
    ----------
    strict : True 면 캐시가 오래됐을 때 KRXCacheError 발생.
             False 면 오래된 값이라도 그대로 반환.
    """
    if not CACHE_FILE.is_file():
        raise KRXCacheError("KRX 캐시 파일 없음: " + str(CACHE_FILE))

    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        updated_at = datetime.fromisoformat(data["updated_at"])
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        raise KRXCacheError("KRX 캐시 파싱 실패: " + str(e))

    if strict:
        age = datetime.now(KST) - updated_at
        if age > timedelta(days=MAX_CACHE_AGE_DAYS):
            raise KRXCacheError(
                "KRX 캐시가 {0}일 됨 (허용 {1}일). 기준일={2}".format(
                    age.days, MAX_CACHE_AGE_DAYS, data.get("date")
                )
            )

    return data


def get_pbr(default=None):
    """KOSPI PBR만 반환. 캐시 오류 시 default."""
    try:
        return read_krx_market(strict=True).get("pbr")
    except KRXCacheError:
        return default


def get_index(label, default=None):
    """
    특정 지수 종가만 반환.
    label: 'kospi', 'kospi200', 'vkospi', 'kosdaq', 'kosdaq150'
    """
    try:
        return read_krx_market(strict=True).get("indices", {}).get(label, default)
    except KRXCacheError:
        return default


def is_pbr_below(threshold, default_on_fail=False):
    """KOSPI PBR이 threshold 미만이면 True. 오류 시 default_on_fail."""
    pbr = get_pbr()
    if pbr is None:
        return default_on_fail
    return pbr < threshold


if __name__ == "__main__":
    # 단독 실행 시 캐시 상태 확인
    try:
        data = read_krx_market(strict=False)
        print("기준일      : {0}".format(data["date"]))
        print("KOSPI PBR  : {0}".format(data.get("pbr")))
        idx = data.get("indices", {})
        for label in ("kospi", "kospi200", "vkospi", "kosdaq", "kosdaq150"):
            print("{0:11s}: {1}".format(label, idx.get(label)))
        print("갱신 시각   : {0}".format(data.get("updated_at")))
        try:
            read_krx_market(strict=True)
            print("신선도       : OK")
        except KRXCacheError as e:
            print("신선도 경고 : {0}".format(e))
    except KRXCacheError as e:
        print("[ERROR] {0}".format(e))
