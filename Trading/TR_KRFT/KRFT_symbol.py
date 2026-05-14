# -*- coding: utf-8 -*-
"""
KRFT_symbol.py
==============
선물 종목코드 (단축코드) 자동 산출. 캘린더 기반 (방식 C).

종목코드 규칙:
  KOSPI200 정규:  A 01 YMM   (예: A01612 = 2026-12)
  KOSPI200 미니:  A 05 YMM   (예: A05612 = 2026-12)
  KOSDAQ150:      A 41 YMM   (예: A41612 = 2026-12)

YMM 인코딩:
  Y = 연도 끝자리 1자 (2026 → 6)
  MM = 월 2자리

만기일 규칙:
  - 둘째 주 목요일
  - 만기일이 휴장이면 그 직전 거래일로 앞당김
  - 만기일까지가 해당 월물 거래기간. 만기일 다음 거래일부터는 차월물.

분기물 (정규 KOSPI200, KOSDAQ150):
  - 3, 6, 9, 12 월물만 거래 (만기월이 분기말월)
  - 예: 1월 → 3월물, 4월 → 6월물, 12월 만기 이후 → 다음해 3월물

월물 (미니 KOSPI200):
  - 매월 만기 → 다음달 물

근월물(near) / 차월물(far) 산출:
  current_near_quarter()  : 현재 거래 중인 분기 만기월 (YYYY, MM)
  next_quarter()          : 그 다음 분기 만기월
  current_near_monthly()  : 현재 거래 중인 월물 만기월
  next_monthly()          : 그 다음 월물 만기월
"""
from __future__ import annotations
from datetime import date, timedelta
from typing import Tuple

# exchange_calendars 는 KST 휴장일 처리에 사용
import exchange_calendars as ecals
_KRX = ecals.get_calendar("XKRX")


# ------------------------------------------------------------------
# 만기일 계산
# ------------------------------------------------------------------
def _second_thursday(year: int, month: int) -> date:
    """그 달의 둘째 주 목요일 (캘린더 날짜, 휴장 보정 전)"""
    first = date(year, month, 1)
    # weekday(): Mon=0 ... Thu=3
    offset = (3 - first.weekday()) % 7
    first_thu = first + timedelta(days=offset)
    return first_thu + timedelta(days=7)


def expiry_date(year: int, month: int) -> date:
    """선물/옵션 만기일. 둘째 주 목요일이 휴장이면 직전 거래일."""
    cal_thu = _second_thursday(year, month)
    if _KRX.is_session(cal_thu.isoformat()):
        return cal_thu
    return _KRX.previous_session(cal_thu.isoformat()).date()


def is_expiry_day(d: date) -> bool:
    """오늘이 그 달의 선물 만기일인가"""
    return d == expiry_date(d.year, d.month)


# ------------------------------------------------------------------
# 종목코드 인코딩
# ------------------------------------------------------------------
def _encode(prefix: str, year: int, month: int) -> str:
    """A + prefix(2자리) + Y(1자리) + MM(2자리)"""
    y1 = year % 10
    return f"A{prefix}{y1}{month:02d}"


def symbol_k200_regular(year: int, month: int) -> str:
    return _encode("01", year, month)


def symbol_k200_mini(year: int, month: int) -> str:
    return _encode("05", year, month)


def symbol_kq150(year: int, month: int) -> str:
    return _encode("41", year, month)


# ------------------------------------------------------------------
# 근월물/차월물 산출
# ------------------------------------------------------------------
QUARTER_MONTHS = (3, 6, 9, 12)


def _add_month(year: int, month: int, n: int) -> Tuple[int, int]:
    """(year, month)에 n개월 더한 (year, month)"""
    total = year * 12 + (month - 1) + n
    y, m0 = divmod(total, 12)
    return y, m0 + 1


def _next_quarter_month(year: int, month: int) -> Tuple[int, int]:
    """주어진 (year, month) 이후의 가장 가까운 분기월(3/6/9/12)"""
    for n in range(0, 12):
        y, m = _add_month(year, month, n)
        if m in QUARTER_MONTHS and (y, m) >= (year, month):
            return y, m
    raise RuntimeError("unreachable")


def current_near_monthly(today: date) -> Tuple[int, int]:
    """
    오늘 시점에서 거래중인 월물 만기월(year, month).
    - 이번 달 만기일 전(<=만기일 당일): 이번 달
    - 이번 달 만기일 이후: 다음 달
    """
    exp = expiry_date(today.year, today.month)
    if today <= exp:
        return today.year, today.month
    return _add_month(today.year, today.month, 1)


def next_monthly(today: date) -> Tuple[int, int]:
    """오늘 기준 차월물 만기월(롤오버 대상)"""
    cy, cm = current_near_monthly(today)
    return _add_month(cy, cm, 1)


def current_near_quarter(today: date) -> Tuple[int, int]:
    """
    오늘 시점에서 거래중인 분기물 만기월.
    - 만기월이라면 만기일 전까지는 현 분기, 만기일 후는 다음 분기
    - 분기월이 아니면 다음 분기월
    """
    # 우선 가장 가까운 미래 분기월을 찾는다
    qy, qm = _next_quarter_month(today.year, today.month)
    # 만약 그 분기월이 이번 달 = today.month 이고, 이미 만기일 지났으면 다음 분기
    if (qy, qm) == (today.year, today.month):
        exp = expiry_date(qy, qm)
        if today > exp:
            return _next_quarter_month(*_add_month(qy, qm, 1))
    return qy, qm


def next_quarter(today: date) -> Tuple[int, int]:
    """오늘 기준 차분기물 만기월 (롤오버 대상)"""
    cy, cm = current_near_quarter(today)
    return _next_quarter_month(*_add_month(cy, cm, 1))


# ------------------------------------------------------------------
# 편의 함수: 현재/다음 거래 종목코드 한 번에
# ------------------------------------------------------------------
def get_current_symbols(today: date) -> dict:
    """
    오늘 거래 가능한 근월물 코드들.
    Returns: {
      "k200_regular":  "A01612",
      "k200_mini":     "A05612",
      "kq150":         "A41612",
      "k200_reg_expiry":  "2026-12-11",
      "k200_mini_expiry": "2026-12-11",
      "kq150_expiry":     "2026-12-11",
    }
    """
    rq_y, rq_m = current_near_quarter(today)
    mo_y, mo_m = current_near_monthly(today)
    return {
        "k200_regular":     symbol_k200_regular(rq_y, rq_m),
        "k200_mini":        symbol_k200_mini(mo_y, mo_m),
        "kq150":            symbol_kq150(rq_y, rq_m),
        "k200_reg_expiry":  expiry_date(rq_y, rq_m).isoformat(),
        "k200_mini_expiry": expiry_date(mo_y, mo_m).isoformat(),
        "kq150_expiry":     expiry_date(rq_y, rq_m).isoformat(),
    }


def get_rollover_targets(today: date) -> dict:
    """
    만기일 당일 롤오버 대상 종목과 차월물 코드.
    Returns: {
      "k200_regular":  {"from": "A01609", "to": "A01612"} or None  (분기말월일 때만),
      "k200_mini":     {"from": "A05611", "to": "A05612"},          (항상)
      "kq150":         {"from": "A41609", "to": "A41612"} or None  (분기말월일 때만),
    }
    None 이면 그 종목은 오늘 롤오버 대상 아님.
    """
    result = {"k200_regular": None, "k200_mini": None, "kq150": None}

    # 미니: 매월 만기
    cy, cm = today.year, today.month
    if is_expiry_day(today):
        # 이번 달 미니물 → 다음 달 미니물
        ny, nm = _add_month(cy, cm, 1)
        result["k200_mini"] = {
            "from": symbol_k200_mini(cy, cm),
            "to":   symbol_k200_mini(ny, nm),
        }
        # 분기말월(3/6/9/12)이면 정규/KQ150도 롤오버
        if cm in QUARTER_MONTHS:
            nqy, nqm = _next_quarter_month(*_add_month(cy, cm, 1))
            result["k200_regular"] = {
                "from": symbol_k200_regular(cy, cm),
                "to":   symbol_k200_regular(nqy, nqm),
            }
            result["kq150"] = {
                "from": symbol_kq150(cy, cm),
                "to":   symbol_kq150(nqy, nqm),
            }

    return result


# ------------------------------------------------------------------
# CLI 테스트
# ------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    from datetime import datetime
    import pytz

    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg:
        today = datetime.strptime(arg, "%Y-%m-%d").date()
    else:
        today = datetime.now(pytz.timezone("Asia/Seoul")).date()

    print(f"기준일: {today}")
    print(f"\n현재 거래 종목:")
    for k, v in get_current_symbols(today).items():
        print(f"  {k:20s} = {v}")
    print(f"\n오늘이 만기일?: {is_expiry_day(today)}")
    print(f"\n오늘 롤오버 대상:")
    for k, v in get_rollover_targets(today).items():
        print(f"  {k:15s} = {v}")
