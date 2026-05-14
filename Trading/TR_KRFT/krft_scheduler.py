# -*- coding: utf-8 -*-
"""
krft_scheduler.py
=================
KRFT 국내선물 자동매매 진입 스케줄러.

crontab (KST→UTC):
  # 매일 KST 15:15 = UTC 06:15 (만기일 확인 후 즉시 롤오버)
  15 6 * * 1-5  timeout -s 9 20m /var/autobot/venv/bin/python /var/autobot/TR_KRFT/krft_scheduler.py >> /var/autobot/Logs/krft.log 2>&1

동작:
  1) 휴장일 즉시 종료
  2) 만기일이면 → run_rollover() 즉시 실행 (15:15 시작, 15:20 전 완료 목표)
  3) 월말 거래일이면 → 15:25까지 대기 → run_signal_entry() 실행
  4) 둘 다 해당 (만기+월말 동일일자) → 롤오버 먼저, 그 후 신호진입
  5) 어느 것도 아니면 즉시 종료
"""
from __future__ import annotations
import sys
import os
import time
from datetime import date, datetime, timedelta

sys.path.insert(0, "/var/autobot")
sys.path.insert(0, "/var/autobot/TR_KRFT")

import pytz
import exchange_calendars as ecals
import telegram_alert as TA

# tendo singleton — 중복 실행 방지 (운영 환경에 설치되어 있다고 가정)
try:
    from tendo import singleton
    _me = singleton.SingleInstance()
except Exception:
    pass

_KRX = ecals.get_calendar("XKRX")


def today_kst() -> date:
    return datetime.now(pytz.timezone("Asia/Seoul")).date()


def is_trading_day(d: date) -> bool:
    return _KRX.is_session(d.isoformat())


def next_trading_day(d: date) -> date:
    return _KRX.next_session(d.isoformat()).date()


def is_month_last_trading_day(d: date) -> bool:
    """오늘이 거래일이고, 다음 거래일이 다른 달이면 월말 마지막 거래일"""
    if not is_trading_day(d):
        return False
    return next_trading_day(d).month != d.month


def _kst_now() -> datetime:
    return datetime.now(pytz.timezone("Asia/Seoul"))


def _sleep_until(hh: int, mm: int, ss: int = 0) -> None:
    """KST 기준 목표 시각까지 sleep (이미 지났으면 0초)"""
    now = _kst_now()
    tgt = now.replace(hour=hh, minute=mm, second=ss, microsecond=0)
    if tgt > now:
        time.sleep((tgt - now).total_seconds())


def main() -> None:
    today = today_kst()
    print(f"[{_kst_now().strftime('%Y-%m-%d %H:%M:%S')}] KRFT scheduler 시작 (today={today})")

    # 1) 휴장
    if not is_trading_day(today):
        print(f"  → 휴장. 종료")
        return

    # 2) 종목/만기 모듈 import는 늦게 (의존성 격리)
    sys.path.insert(0, "/var/autobot/TR_KRFT")
    import KRFT_symbol as SYM
    import KRFT_TR as TR

    is_expiry = SYM.is_expiry_day(today)
    is_signal = is_month_last_trading_day(today)

    print(f"  is_expiry_day = {is_expiry} | is_month_last = {is_signal}")

    if not (is_expiry or is_signal):
        print(f"  → 대상 아님. 종료")
        return

    # 3) 만기일이면 즉시 롤오버 (15:15 ~ 15:20)
    if is_expiry:
        print(f"[{_kst_now().strftime('%H:%M:%S')}] 롤오버 실행")
        try:
            TR.run_rollover()
        except Exception as e:
            TA.send_tele(f"[KRFT] 롤오버 예외: {e}")
            print(f"  롤오버 예외: {e}")

    # 4) 월말 거래일이면 15:25 대기 후 진입
    if is_signal:
        print(f"[{_kst_now().strftime('%H:%M:%S')}] 15:25 대기...")
        _sleep_until(15, 25, 0)
        print(f"[{_kst_now().strftime('%H:%M:%S')}] 월말 진입 실행")
        try:
            TR.run_signal_entry()
        except Exception as e:
            TA.send_tele(f"[KRFT] 월말진입 예외: {e}")
            print(f"  월말진입 예외: {e}")


if __name__ == "__main__":
    main()
