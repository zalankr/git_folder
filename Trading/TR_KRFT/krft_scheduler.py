# -*- coding: utf-8 -*-
"""
krft_scheduler.py (v2)
======================
KRFT 국내선물 자동매매 진입 스케줄러.

crontab (KST 15:15 = UTC 06:15):
  15 6 * * 1-5  timeout -s 9 25m /usr/bin/python3 /var/autobot/TR_KRFT/krft_scheduler.py >> /var/autobot/Logs/krft.log 2>&1

흐름 분기:
  Step 1: 휴장일 → 즉시 종료
  Step 2: 만기일 → 15:15~15:20 롤오버 실행
  Step 3: 월말 거래일 → 15:25 대기 후 run_signal_entry
  Step 4: Hedge3 ON 평일 → 15:25 대기 후 run_hedge3_daily
  Step 5: Hedge3 OFF 일반 평일 → 종료 (cron 로그에만 기록)
"""
from __future__ import annotations
import sys
import os
import json
import time
from datetime import date, datetime, timedelta

sys.path.insert(0, "/var/autobot")
sys.path.insert(0, "/var/autobot/TR_KRFT")

import pytz
import exchange_calendars as ecals

try:
    from tendo import singleton
    _me = singleton.SingleInstance()
except Exception:
    pass

import telegram_alert as TA

_KRX = ecals.get_calendar("XKRX")

RESULT_PATH = "/var/autobot/TR_KRFT/KRFT_result.json"


def today_kst() -> date:
    return datetime.now(pytz.timezone("Asia/Seoul")).date()


def _kst_now() -> datetime:
    return datetime.now(pytz.timezone("Asia/Seoul"))


def _sleep_until(hh: int, mm: int, ss: int = 0) -> None:
    now = _kst_now()
    tgt = now.replace(hour=hh, minute=mm, second=ss, microsecond=0)
    if tgt > now:
        time.sleep((tgt - now).total_seconds())


def is_trading_day(d: date) -> bool:
    return _KRX.is_session(d.isoformat())


def next_trading_day(d: date) -> date:
    return _KRX.next_session(d.isoformat()).date()


def is_month_last_trading_day(d: date) -> bool:
    if not is_trading_day(d):
        return False
    return next_trading_day(d).month != d.month


def is_hedge3_enabled() -> bool:
    if not os.path.exists(RESULT_PATH):
        return False
    try:
        with open(RESULT_PATH, "r", encoding="utf-8") as f:
            r = json.load(f)
        return bool(r.get("manual_config", {})
                    .get("strategy_enabled", {})
                    .get("hedge3", False))
    except Exception:
        return False


def _load_result_ctx() -> dict:
    """KRFT_result.json 의 알림용 컨텍스트 일부 추출"""
    if not os.path.exists(RESULT_PATH):
        return {}
    try:
        with open(RESULT_PATH, "r", encoding="utf-8") as f:
            rj = json.load(f)
        return {
            "enabled":   rj.get("manual_config", {}).get("strategy_enabled", {}),
            "positions": rj.get("positions", {}),
            "holdings":  rj.get("holdings", {}),
            "snapshots": rj.get("snapshots", {}),
        }
    except Exception:
        return {}


def main() -> None:
    today = today_kst()
    now = _kst_now()
    print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] KRFT scheduler 시작 today={today}")

    # ── Step 1: 휴장 ──
    if not is_trading_day(today):
        print(f"  → 휴장. 종료")
        return

    import KRFT_symbol as SYM
    import KRFT_TR as TR
    import KRFT_notify as NF

    is_expiry = SYM.is_expiry_day(today)
    is_signal = is_month_last_trading_day(today)
    h3_on     = is_hedge3_enabled()

    print(f"  is_expiry_day={is_expiry} is_month_last={is_signal} hedge3_on={h3_on}")

    did_any = False

    # ── Step 2: 만기일 → 즉시 롤오버 (15:15~15:20) ──
    if is_expiry:
        print(f"[{_kst_now().strftime('%H:%M:%S')}] 롤오버 실행")
        try:
            TR.run_rollover()
            did_any = True
        except Exception as e:
            TA.send_tele(f"[KRFT] 롤오버 예외: {e}")

    # ── 15:25 대기 (signal 또는 Hedge3 daily 필요 시) ──
    if is_signal or h3_on:
        print(f"[{_kst_now().strftime('%H:%M:%S')}] 15:25 대기...")
        _sleep_until(15, 25, 0)

    # ── Step 3: 월말 거래일 → 정규 signal entry ──
    if is_signal:
        print(f"[{_kst_now().strftime('%H:%M:%S')}] 월말 진입 실행")
        try:
            TR.run_signal_entry()
            did_any = True
        except Exception as e:
            TA.send_tele(f"[KRFT] 월말진입 예외: {e}")

    # ── Step 4: Hedge3 ON + 월말 아님 → daily 매매 ──
    elif h3_on:
        print(f"[{_kst_now().strftime('%H:%M:%S')}] Hedge3 daily 실행")
        try:
            res = TR.run_hedge3_daily()
            did_any = True

            # daily 알림
            try:
                ctx_extra = _load_result_ctx()
                msg_ctx = {
                    "today":     today.isoformat(),
                    "kospi":     res.get("kospi", 0),
                    "kosdaq":    res.get("kosdaq", 0),
                    "pbr":       res.get("pbr", 0),
                    "vkospi":    res.get("vkospi", 0),
                    "pnl":       res.get("pnl", 0),
                    "eval_amt":  res.get("eval_amt", 0),
                    **ctx_extra,
                }
                if res.get("executed"):
                    msg = NF.build_trade_end_message(
                        today.isoformat(), "hedge3_daily", True, msg_ctx)
                else:
                    msg = NF.build_daily_message(msg_ctx, mode="hedge3_active")
                TA.send_tele(msg)
            except Exception as e:
                print(f"  알림 빌드 실패: {e}")
                TA.send_tele(f"[KRFT Hedge3] 결과 알림 빌드 실패: {e}")

            # 알림 발송 후 prev_day snapshot 커밋 (다음날 비교용)
            try:
                with open(RESULT_PATH, "r", encoding="utf-8") as f:
                    r2 = json.load(f)
                pending = r2.pop("_pending_prev_day_update", None)
                if pending:
                    r2.setdefault("snapshots", {})["prev_day"] = pending
                    tmp = RESULT_PATH + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(r2, f, ensure_ascii=False, indent=2)
                    os.replace(tmp, RESULT_PATH)
                    print(f"  prev_day 갱신: {pending['date']} pnl={pending['evlu_pfls']:,.0f}")
            except Exception as e:
                print(f"  prev_day 커밋 실패: {e}")

        except Exception as e:
            TA.send_tele(f"[KRFT] Hedge3 daily 예외: {e}")

    # ── Step 5: Hedge3 OFF + 거래일 아님 → 종료 ──
    if not did_any:
        print(f"  → 매매일 아님 + Hedge3 OFF. 종료 (텔레그램 송신 없음)")


if __name__ == "__main__":
    main()
