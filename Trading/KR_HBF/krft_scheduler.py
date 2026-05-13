# -*- coding: utf-8 -*-
"""
KRFT 국내선물 자동매매 스케줄러
실행: 평일 매일 (crontab)
동작:
  - 매월 마지막 거래일  → 신규 포지션(시그널) 실행
  - 매월 둘째 주 목요일(만기일) → 롤오버 실행
    · 분기물: 3·6·9·12월에만
    · 월물:   매월
  - 그 외       → 즉시 종료
"""
import sys
import os
from datetime import date, timedelta
import exchange_calendars as ecals

# ── 설정 ────────────────────────────────────────────
# 운용 상품: "QUARTERLY"(KOSPI200 정규선물) 또는 "MONTHLY"(미니선물)
PRODUCT_TYPE = "MONTHLY"    # 미니KOSPI200
# 분기물 만기월 (분기물일 때만 사용)
QUARTERLY_MONTHS = {3, 6, 9, 12}

# ── 캘린더 초기화 ───────────────────────────────────
KRX = ecals.get_calendar("XKRX")

def today_kst() -> date:
    """EC2가 UTC라도 KST 기준 '오늘'을 반환"""
    import pytz
    from datetime import datetime
    return datetime.now(pytz.timezone("Asia/Seoul")).date()

def is_trading_day(d: date) -> bool:
    return KRX.is_session(d.isoformat())

def next_trading_day(d: date) -> date:
    """d 다음 첫 거래일"""
    nxt = KRX.next_session(d.isoformat())
    return nxt.date()

def prev_trading_day(d: date) -> date:
    prv = KRX.previous_session(d.isoformat())
    return prv.date()

def is_month_last_trading_day(d: date) -> bool:
    """오늘이 거래일이고, 다음 거래일이 다른 달이면 = 월말 마지막 거래일"""
    if not is_trading_day(d):
        return False
    return next_trading_day(d).month != d.month

def second_thursday(year: int, month: int) -> date:
    """그 달의 둘째 주 목요일 캘린더상 날짜 (휴장 보정 전)"""
    first = date(year, month, 1)
    # weekday(): 월=0 ... 목=3
    offset = (3 - first.weekday()) % 7
    first_thu = first + timedelta(days=offset)
    return first_thu + timedelta(days=7)

def expiry_day(year: int, month: int) -> date:
    """
    KOSPI200 (미니)선물 최종거래일:
    - 원칙: 둘째 주 목요일
    - 휴장이면 직전 거래일로 앞당겨짐
    """
    cal_thu = second_thursday(year, month)
    if is_trading_day(cal_thu):
        return cal_thu
    return prev_trading_day(cal_thu)

def is_rollover_day(d: date, product_type: str) -> bool:
    """오늘이 만기일(=롤오버일)인가?"""
    exp = expiry_day(d.year, d.month)
    if d != exp:
        return False
    if product_type == "QUARTERLY":
        return d.month in QUARTERLY_MONTHS
    return True   # MONTHLY는 매월

# ── 메인 ────────────────────────────────────────────
def main():
    today = today_kst()

    # 1) 휴장일이면 즉시 종료
    if not is_trading_day(today):
        print(f"[KRFT] {today} 휴장. 종료.")
        sys.exit(0)

    is_signal_day   = is_month_last_trading_day(today)
    is_roll_day     = is_rollover_day(today, PRODUCT_TYPE)

    # 2) 어느 것도 해당 없음 → 종료
    if not (is_signal_day or is_roll_day):
        print(f"[KRFT] {today} 실행대상 아님 (signal=F, roll=F). 종료.")
        sys.exit(0)

    # 3) 둘 다 해당하는 날도 있을 수 있음 (예: 월말+만기일 동시)
    if is_roll_day:
        print(f"[KRFT] {today} 롤오버 실행 ({PRODUCT_TYPE})")
        from KRFT_TR import run_rollover         # 실제 모듈명에 맞춰 변경
        run_rollover()

    if is_signal_day:
        print(f"[KRFT] {today} 신규 시그널 포지션 실행")
        from KRFT_TR import run_signal_entry    # 실제 모듈명에 맞춰 변경
        run_signal_entry()

if __name__ == "__main__":
    main()