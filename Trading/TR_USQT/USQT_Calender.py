"""
USQT 헤지/리밸런싱 일정 및 회차 매핑 모듈
경로: /var/autobot/TR_USAA/USQT_Calender.py
(USAA_Calender.py 와 같은 폴더에 둠 → 둘 다 USAA 폴더에서 공용 사용)

기능:
1. 헤지 매매일 여부 확인 (USQT_hedge_day.json 의 summer_dst / winter_standard 참조)
2. 분기 리밸런싱일 여부 확인 (USQT_day.json 의 rebal_dates 참조)
3. USAA 와 동일한 round 시각 매핑 차용 (24회차)

전략 사양:
- 신호 계산: 월말 마지막 거래일 장마감 후 / 매주 금요일 장마감 후
- 매매 집행: 신호일 익일 장전부터 24회차 1일 매매
- 즉, 'USQT 헤지 매매일' = '신호 발생 익일 거래일'
  → 이 날짜를 미리 산출하여 USQT_hedge_day.json 에 등록해 두는 운영방식
  (USAA 와 동일하게 운영자가 사전 등록)

JSON 파일 구조 예시 (USQT_hedge_day.json):
{
  "summer_dst":       ["2026-06-01", "2026-06-05", ...],  # DST 기간 헤지 매매일 (UTC 08:00 시작)
  "winter_standard":  ["2026-11-03", ...]                  # EST 기간 헤지 매매일 (UTC 09:00 시작)
}

USQT_day.json 구조:
{
  "day": 1,                                      # 분기 리밸 day 추적 (기존 그대로)
  "rebal_dates": ["2026-06-30", "2026-07-01"]    # ✅ 추가: 분기 리밸 14회차 매매일 (2일)
}
"""

from datetime import datetime, timezone, time as time_obj
import json


# ============================================
# 경로 정의 (USAA 폴더 공용)
# ============================================
USQT_HEDGE_DAY_PATH = "/var/autobot/TR_USQT/USQT_hedge_day.json"
USQT_DAY_PATH       = "/var/autobot/TR_USQT/USQT_day.json"


# ============================================
# 헤지일 / 리밸일 판단
# ============================================
def check_USQT_hedge_day(current_date):
    """오늘이 USQT 헤지 매매일인지 확인. USAA 패턴 동일.
    Returns: "USQT_hedge_summer" | "USQT_hedge_winter" | "USQT_not_hedge_day"
    """
    try:
        with open(USQT_HEDGE_DAY_PATH, 'r', encoding='utf-8') as f:
            hedge_day = json.load(f)
    except Exception as e:
        try:
            import telegram_alert as TA
            TA.send_tele(f"USQT_hedge_day.json 로드 실패: {e}")
        except:
            pass
        return "USQT_not_hedge_day"

    if str(current_date) in hedge_day.get("summer_dst", []):
        return "USQT_hedge_summer"
    elif str(current_date) in hedge_day.get("winter_standard", []):
        return "USQT_hedge_winter"
    else:
        return "USQT_not_hedge_day"


def check_USQT_rebal_day(current_date):
    """오늘이 USQT 분기 리밸런싱 14회차 매매일인지 확인.
    USQT_day.json 의 rebal_dates 리스트 참조.
    Returns: True | False
    """
    try:
        with open(USQT_DAY_PATH, 'r', encoding='utf-8') as f:
            day_data = json.load(f)
    except Exception:
        return False
    return str(current_date) in day_data.get("rebal_dates", [])


# ============================================
# 회차 시각 매핑 (USAA 동일 24회차)
# ============================================
def check_order_time():
    """헤지 매매 회차 확인. USAA_Calender 와 동일한 시각→round 매핑 사용."""
    now = datetime.now()                      # EC2 = UTC
    current_date = now.date()
    current_time = now.time()

    check_hedge = check_USQT_hedge_day(current_date)

    order_time = {
        'season': check_hedge,
        'date':   current_date,
        'time':   current_time,
        'month':  current_date.month,
        'round':  0,
        'total_round': 24
    }

    if check_hedge == "USQT_hedge_winter":
        # EST(UTC-5): 정규장 UTC 14:30~21:00 → 장전 09:00부터 운영 (USAA 와 동일)
        current = time_obj(current_time.hour, current_time.minute)
        start   = time_obj(9, 0)
        end     = time_obj(20, 35)
        if start <= current < end:
            order_time['round'] = 1 + (current.hour - 9) * 2 + (current.minute // 30)

    elif check_hedge == "USQT_hedge_summer":
        # EDT(UTC-4): 정규장 UTC 13:30~20:00 → 장전 08:00부터 운영 (USAA 와 동일)
        current = time_obj(current_time.hour, current_time.minute)
        start   = time_obj(8, 0)
        end     = time_obj(19, 35)
        if start <= current < end:
            order_time['round'] = 1 + (current.hour - 8) * 2 + (current.minute // 30)

    return order_time


# ============================================
# DST 판단 (신호계산 스크립트가 자기 자신 실행 시간대 확인용)
# ============================================
def is_us_dst():
    """미국이 현재 DST(서머타임)인지 판단."""
    try:
        import pytz
        eastern = pytz.timezone('America/New_York')
        now_et = datetime.now(timezone.utc).astimezone(eastern)
        return bool(now_et.dst())
    except ImportError:
        # pytz 미설치 → 간이판단 (3~10월)
        month = datetime.now(timezone.utc).month
        return 3 <= month <= 10
