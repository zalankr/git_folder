"""
USQT 헤지 매매일 자동 생성 유틸리티
경로: /var/autobot/TR_USQT/gen_hedge_days.py

기능:
- 미국 증시 정상시간 개장일 기준
- (월말 마지막 거래일 + 1) → 월말 정기 신호 익일 매매일
- (매주 금요일 + 1)        → 주간 RSI 신호 익일 매매일
- 위 두 날짜가 휴장이면 다음 거래일로 보정
- 두 신호가 같은 날 겹치면 한 번만 등록
- DST/EST 자동 구분하여 summer_dst / winter_standard 에 분배
- 오늘 이전 지난 날짜는 자동 삭제
- 기존 파일 백업 후 갱신

사용법:
  # 기본 (오늘 ~ 1년 후) 자동 생성, 기존 파일에 머지
  python3 gen_hedge_days.py

  # 특정 시작일 + 기간(일수) 지정
  python3 gen_hedge_days.py --start 2026-01-01 --days 365

  # 드라이런 (파일 쓰지 않고 결과만 출력)
  python3 gen_hedge_days.py --dry-run

  # 기존 파일을 무시하고 완전히 새로 생성 (수동 등록 분 모두 삭제됨)
  python3 gen_hedge_days.py --overwrite

  # crontab 자동 갱신용 (매주 일요일 1회 + quiet mode)
  python3 gen_hedge_days.py --quiet

크론 예시 (매주 일요일 UTC 12:00 자동 갱신):
  0 12 * * 0 /usr/bin/python3 /var/autobot/TR_USQT/gen_hedge_days.py --quiet
"""

import os
import sys
import json
import argparse
import shutil
from datetime import datetime, timedelta, date
from typing import List, Set, Tuple


# ============================================
# 경로
# ============================================
USQT_HEDGE_DAY_PATH = "/var/autobot/TR_USQT/USQT_hedge_day.json"


# ============================================
# 미국 증시 거래일 / DST 판단
# ============================================
def _get_xnys_calendar():
    """exchange_calendars 의 XNYS 캘린더 반환. 미설치 시 None."""
    try:
        import exchange_calendars as xcals
        return xcals.get_calendar("XNYS")
    except ImportError:
        return None


def is_us_trading_day(d: date, cal=None) -> bool:
    """미국 증시 거래일 여부.
    - exchange_calendars 가 있으면 정확 판정
    - 없으면 평일 + US 공휴일 라이브러리 fallback
    - 둘 다 없으면 평일만 판정
    """
    if cal is not None:
        try:
            import pandas as pd
            return cal.is_session(pd.Timestamp(d))
        except Exception:
            pass

    # fallback 1: holidays 라이브러리 (NYSE 공휴일)
    try:
        import holidays
        us_holidays = holidays.country_holidays('US', subdiv='NY')
        if d.weekday() >= 5:
            return False
        # NYSE 휴장 = 일부 미국 공휴일 (Good Friday 등 별도 처리)
        if d in us_holidays:
            return False
        # Good Friday 등 NYSE 특화 휴장일은 fallback 에서 누락 가능
        return True
    except ImportError:
        pass

    # fallback 2: 평일 판정만
    return d.weekday() < 5


def next_trading_day(d: date, cal=None) -> date:
    """d 다음 거래일 (d 자체가 거래일이어도 다음 거래일을 반환)."""
    d = d + timedelta(days=1)
    for _ in range(30):  # 최대 30일 안에 거래일 보장
        if is_us_trading_day(d, cal):
            return d
        d += timedelta(days=1)
    raise RuntimeError(f"30일 내 다음 거래일을 찾지 못함: {d}")


def is_us_dst(d: date) -> bool:
    """date d 가 미국 동부 시간 기준 DST(서머타임) 기간인지.
    미국 DST: 3월 둘째 일요일 02:00 ~ 11월 첫째 일요일 02:00
    """
    year = d.year

    # 3월 둘째 일요일
    march_first = date(year, 3, 1)
    days_to_sunday = (6 - march_first.weekday()) % 7
    first_sunday_march = march_first + timedelta(days=days_to_sunday)
    dst_start = first_sunday_march + timedelta(days=7)

    # 11월 첫째 일요일
    november_first = date(year, 11, 1)
    days_to_sunday = (6 - november_first.weekday()) % 7
    dst_end = november_first + timedelta(days=days_to_sunday)

    return dst_start <= d < dst_end


# ============================================
# 헤지일 후보 생성
# ============================================
def generate_signal_days(start: date, end: date, cal=None
                         ) -> Tuple[Set[date], List[Tuple[date, str]]]:
    """start ~ end 기간 동안 헤지 매매일 후보 생성.
    Returns:
        (헤지매매일 set, [(매매일, 신호유형), ...] 로그)
    신호유형: 'month_end' | 'friday' | 'both'
    """
    hedge_days: Set[date] = set()
    log: List[Tuple[date, str]] = []

    # 1) 매주 금요일 → 다음 거래일
    d = start
    while d <= end:
        if d.weekday() == 4:    # 금요일
            # 금요일 자체는 거래일이 아닐 수 있음(휴장) → 그 경우는 그래도 다음 거래일 계산
            trade_day = next_trading_day(d, cal)
            if start <= trade_day <= end:
                hedge_days.add(trade_day)
                log.append((trade_day, 'friday'))
        d += timedelta(days=1)

    # 2) 매월 마지막 거래일 → 다음 거래일
    cur = date(start.year, start.month, 1)
    while cur <= end:
        # 해당 월의 마지막 날부터 거꾸로 검색하며 거래일 찾기
        if cur.month == 12:
            month_last = date(cur.year, 12, 31)
        else:
            month_last = date(cur.year, cur.month + 1, 1) - timedelta(days=1)

        scan = month_last
        last_trading = None
        for _ in range(15):
            if is_us_trading_day(scan, cal):
                last_trading = scan
                break
            scan -= timedelta(days=1)

        if last_trading is not None:
            trade_day = next_trading_day(last_trading, cal)
            if start <= trade_day <= end:
                # 같은 날 금요일 매매일과 겹치면 'both' 로 마킹
                already = any(t == trade_day for t, _ in log)
                if already:
                    # 기존 log 항목을 'both' 로 갱신
                    log = [(t, ('both' if t == trade_day else s)) for t, s in log]
                else:
                    hedge_days.add(trade_day)
                    log.append((trade_day, 'month_end'))

        # 다음 달
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)

    return hedge_days, sorted(log)


# ============================================
# DST/EST 분배
# ============================================
def split_by_dst(days: Set[date]) -> Tuple[List[str], List[str]]:
    """date set 을 DST(여름) 와 EST(겨울) 로 분리."""
    summer, winter = [], []
    for d in sorted(days):
        if is_us_dst(d):
            summer.append(str(d))
        else:
            winter.append(str(d))
    return summer, winter


# ============================================
# 기존 파일 머지 + 지난 날짜 제거
# ============================================
def load_existing(path: str) -> Tuple[Set[str], Set[str]]:
    """기존 USQT_hedge_day.json 로드. (summer, winter) set 반환."""
    if not os.path.exists(path):
        return set(), set()
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return set(data.get("summer_dst", [])), set(data.get("winter_standard", []))
    except Exception as e:
        print(f"⚠ 기존 파일 로드 실패 ({e}). 빈 set 으로 처리.")
        return set(), set()


def remove_past(dates: Set[str], today: date) -> Tuple[Set[str], int]:
    """오늘 이전 날짜 제거. (남은 set, 제거된 수) 반환."""
    today_s = str(today)
    keep = {d for d in dates if d >= today_s}
    removed = len(dates) - len(keep)
    return keep, removed


# ============================================
# 메인
# ============================================
def main():
    parser = argparse.ArgumentParser(
        description="USQT 헤지 매매일 자동 생성 (월말+1, 금요일+1)"
    )
    parser.add_argument('--start', type=str, default=None,
                        help='시작일 (YYYY-MM-DD). default: 오늘')
    parser.add_argument('--days', type=int, default=365,
                        help='생성 기간(일). default: 365')
    parser.add_argument('--end', type=str, default=None,
                        help='종료일 (YYYY-MM-DD). 지정 시 --days 무시')
    parser.add_argument('--path', type=str, default=USQT_HEDGE_DAY_PATH,
                        help=f'출력 경로. default: {USQT_HEDGE_DAY_PATH}')
    parser.add_argument('--dry-run', action='store_true',
                        help='파일 쓰지 않고 결과만 출력')
    parser.add_argument('--overwrite', action='store_true',
                        help='기존 파일 무시하고 완전히 새로 작성 (수동 등록 모두 삭제)')
    parser.add_argument('--no-backup', action='store_true',
                        help='기존 파일 백업 생성하지 않음')
    parser.add_argument('--quiet', action='store_true',
                        help='최소 출력 (cron 용)')
    args = parser.parse_args()

    # 시작/종료 날짜
    today = date.today()
    start_d = datetime.strptime(args.start, "%Y-%m-%d").date() if args.start else today
    if args.end:
        end_d = datetime.strptime(args.end, "%Y-%m-%d").date()
    else:
        end_d = start_d + timedelta(days=args.days)

    if start_d > end_d:
        print(f"❌ start({start_d}) > end({end_d}). 종료.")
        sys.exit(1)

    cal = _get_xnys_calendar()
    if not args.quiet:
        print(f"=== USQT 헤지일 자동 생성 ===")
        print(f"  기간   : {start_d} ~ {end_d} ({(end_d - start_d).days}일)")
        print(f"  캘린더 : {'exchange_calendars XNYS' if cal else 'fallback (평일+공휴일)'}")
        print(f"  출력   : {args.path}{' [DRY-RUN]' if args.dry_run else ''}")
        print()

    # 1) 신규 헤지일 생성
    new_days, log = generate_signal_days(start_d, end_d, cal)

    # 2) 기존 파일 머지 (overwrite 가 아닐 때)
    if args.overwrite:
        existing_summer, existing_winter = set(), set()
        if not args.quiet:
            print("  --overwrite: 기존 파일 무시, 완전히 새로 작성")
    else:
        existing_summer, existing_winter = load_existing(args.path)
        if not args.quiet and (existing_summer or existing_winter):
            print(f"  기존 파일: summer={len(existing_summer)}건, winter={len(existing_winter)}건")

    # 3) 지난 날짜 제거 (기존 파일에서)
    existing_summer, removed_s = remove_past(existing_summer, today)
    existing_winter, removed_w = remove_past(existing_winter, today)
    if not args.quiet and (removed_s + removed_w) > 0:
        print(f"  지난 날짜 제거: summer={removed_s}건, winter={removed_w}건")

    # 4) 신규 + 기존 머지
    new_summer, new_winter = split_by_dst(new_days)
    merged_summer = sorted(set(new_summer) | existing_summer)
    merged_winter = sorted(set(new_winter) | existing_winter)

    # 5) 머지 후에도 지난 날짜는 한 번 더 정리 (신규에 과거가 들어왔을 경우)
    merged_summer = [d for d in merged_summer if d >= str(today)]
    merged_winter = [d for d in merged_winter if d >= str(today)]

    # 6) 결과 출력
    if not args.quiet:
        print()
        print(f"=== 생성 결과 ===")
        print(f"  신규 헤지일      : {len(new_days)}건")
        print(f"  - month_end만    : {sum(1 for _, s in log if s == 'month_end')}건")
        print(f"  - friday만       : {sum(1 for _, s in log if s == 'friday')}건")
        print(f"  - 양쪽 겹침(both): {sum(1 for _, s in log if s == 'both')}건")
        print()
        print(f"  최종 summer_dst     : {len(merged_summer)}건")
        print(f"  최종 winter_standard: {len(merged_winter)}건")
        print()

        # 상세 로그 (앞 10개만 표시)
        print(f"=== 생성된 헤지일 상세 (앞 10개) ===")
        for trade_day, signal_type in log[:10]:
            tag = '☀ DST' if is_us_dst(trade_day) else '❄ EST'
            print(f"  {trade_day} ({trade_day.strftime('%a')}) {tag} [{signal_type}]")
        if len(log) > 10:
            print(f"  ... 외 {len(log) - 10}건")
        print()

    # 7) 저장
    if args.dry_run:
        if not args.quiet:
            print("=== DRY-RUN: 파일 저장하지 않음 ===")
            print(json.dumps({
                "summer_dst": merged_summer[:5] + (["..."] if len(merged_summer) > 5 else []),
                "winter_standard": merged_winter[:5] + (["..."] if len(merged_winter) > 5 else [])
            }, indent=2, ensure_ascii=False, default=str))
        return

    # 백업 생성
    if not args.no_backup and os.path.exists(args.path):
        bp = args.path + f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            shutil.copy2(args.path, bp)
            if not args.quiet:
                print(f"  백업 생성: {bp}")
        except Exception as e:
            print(f"  ⚠ 백업 실패: {e}")

    # 본 파일 저장
    output = {
        "_generated_at": datetime.now().isoformat(timespec='seconds'),
        "_generated_range": f"{start_d} ~ {end_d}",
        "_dst_window": "DST(서머타임): UTC 08:00 ~ 19:30 (24회차)",
        "_est_window": "EST(겨울표준시): UTC 09:00 ~ 20:30 (24회차)",
        "summer_dst":      merged_summer,
        "winter_standard": merged_winter
    }
    try:
        os.makedirs(os.path.dirname(args.path), exist_ok=True)
        with open(args.path, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=4, default=str)
        if not args.quiet:
            print(f"  ✓ 저장 완료: {args.path}")
        else:
            print(f"USQT 헤지일 갱신: summer={len(merged_summer)}, winter={len(merged_winter)} → {args.path}")
    except Exception as e:
        print(f"❌ 저장 실패: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
