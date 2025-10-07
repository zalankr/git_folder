import pandas_market_calendars as mcal
from datetime import datetime, timedelta
import pytz

class US_Market_Calendar:
    """미국 증시 거래일 체크 클래스"""
    
    def __init__(self):
        # NYSE 캘린더 (나스닥과 동일한 거래일)
        self.nyse = mcal.get_calendar('NYSE')
        
    def is_trading_day(self, date=None):
        """
        특정 날짜가 거래일인지 확인
        
        Parameters:
        date: datetime 객체 또는 'YYYY-MM-DD' 문자열 (None이면 오늘)
        
        Returns:
        bool: 거래일이면 True
        """
        if date is None:
            date = datetime.now()
        elif isinstance(date, str):
            date = datetime.strptime(date, '%Y-%m-%d')
        
        # 해당 날짜의 거래일 스케줄 조회
        schedule = self.nyse.schedule(
            start_date=date.strftime('%Y-%m-%d'),
            end_date=date.strftime('%Y-%m-%d')
        )
        
        return len(schedule) > 0
    
    def get_next_trading_day(self, date=None):
        """
        다음 거래일 찾기
        
        Parameters:
        date: 기준 날짜 (None이면 오늘)
        
        Returns:
        datetime: 다음 거래일
        """
        if date is None:
            date = datetime.now()
        elif isinstance(date, str):
            date = datetime.strptime(date, '%Y-%m-%d')
        
        # 최대 14일 앞까지 조회 (주말+공휴일 대비)
        end_date = date + timedelta(days=14)
        
        schedule = self.nyse.schedule(
            start_date=date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d')
        )
        
        # 오늘 이후의 거래일 찾기
        future_days = schedule[schedule.index.date > date.date()]
        
        if len(future_days) > 0:
            return future_days.index[0].date()
        return None
    
    def get_previous_trading_day(self, date=None):
        """
        이전 거래일 찾기
        
        Parameters:
        date: 기준 날짜 (None이면 오늘)
        
        Returns:
        datetime: 이전 거래일
        """
        if date is None:
            date = datetime.now()
        elif isinstance(date, str):
            date = datetime.strptime(date, '%Y-%m-%d')
        
        # 최대 14일 전까지 조회
        start_date = date - timedelta(days=14)
        
        schedule = self.nyse.schedule(
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=date.strftime('%Y-%m-%d')
        )
        
        # 오늘 이전의 거래일 찾기
        past_days = schedule[schedule.index.date < date.date()]
        
        if len(past_days) > 0:
            return past_days.index[-1].date()
        return None
    
    def get_trading_days_in_month(self, year=None, month=None):
        """
        특정 월의 모든 거래일 조회
        
        Parameters:
        year: 연도 (None이면 올해)
        month: 월 (None이면 이번달)
        
        Returns:
        list: 거래일 리스트
        """
        if year is None or month is None:
            today = datetime.now()
            year = year or today.year
            month = month or today.month
        
        # 월 시작일과 마지막일
        from calendar import monthrange
        last_day = monthrange(year, month)[1]
        
        start_date = f"{year}-{month:02d}-01"
        end_date = f"{year}-{month:02d}-{last_day}"
        
        schedule = self.nyse.schedule(
            start_date=start_date,
            end_date=end_date
        )
        
        return [day.date() for day in schedule.index]
    
    def get_market_hours(self, date=None):
        """
        거래 시간 조회 (ET 시간대)
        
        Parameters:
        date: 조회 날짜 (None이면 오늘)
        
        Returns:
        dict: 시장 개장/마감 시간 또는 None
        """
        if date is None:
            date = datetime.now()
        elif isinstance(date, str):
            date = datetime.strptime(date, '%Y-%m-%d')
        
        schedule = self.nyse.schedule(
            start_date=date.strftime('%Y-%m-%d'),
            end_date=date.strftime('%Y-%m-%d')
        )
        
        if len(schedule) == 0:
            return None
        
        row = schedule.iloc[0]
        
        return {
            'market_open': row['market_open'].to_pydatetime(),
            'market_close': row['market_close'].to_pydatetime(),
            'is_early_close': row['market_close'].hour < 16
        }
    
    def get_holidays(self, year=None):
        """
        연간 휴장일 조회
        
        Parameters:
        year: 연도 (None이면 올해)
        
        Returns:
        list: (날짜, 휴일명) 튜플 리스트
        """
        if year is None:
            year = datetime.now().year
        
        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"
        
        # 전체 달력과 거래일 비교
        all_days = mcal.date_range(
            self.nyse.schedule(start_date=start_date, end_date=end_date),
            frequency='1D'
        )
        
        holidays = self.nyse.holidays().holidays
        
        result = []
        for holiday in holidays:
            if holiday.year == year:
                result.append((holiday, holidays[holiday]))
        
        return sorted(result, key=lambda x: x[0])


# 사용 예시
if __name__ == "__main__":
    calendar = US_Market_Calendar()
    
    # 오늘이 거래일인지 확인
    print("="*60)
    today = datetime.now()
    is_trading = calendar.is_trading_day()
    print(f"오늘 ({today.strftime('%Y-%m-%d')}): {'거래일' if is_trading else '휴장일'}")
    
    # 특정 날짜 확인 (크리스마스)
    christmas = "2025-12-25"
    is_trading = calendar.is_trading_day(christmas)
    print(f"{christmas}: {'거래일' if is_trading else '휴장일'}")
    
    # 다음 거래일
    next_day = calendar.get_next_trading_day()
    print(f"\n다음 거래일: {next_day}")
    
    # 이전 거래일
    prev_day = calendar.get_previous_trading_day()
    print(f"이전 거래일: {prev_day}")
    
    # 이번 달 거래일 수
    trading_days = calendar.get_trading_days_in_month()
    print(f"\n이번 달 거래일: {len(trading_days)}일")
    print(f"거래일 목록: {[d.strftime('%Y-%m-%d') for d in trading_days[:5]]}...")
    
    # 오늘의 거래 시간
    hours = calendar.get_market_hours()
    if hours:
        print(f"\n오늘의 거래 시간:")
        print(f"개장: {hours['market_open'].strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"마감: {hours['market_close'].strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"조기 마감: {'예' if hours['is_early_close'] else '아니오'}")
    else:
        print("\n오늘은 휴장일입니다.")
    
    # 2025년 휴장일 목록
    print("\n" + "="*60)
    print("2025년 미국 증시 휴장일:")
    print("="*60)
    holidays = calendar.get_holidays(2025)
    for date, name in holidays:
        print(f"{date.strftime('%Y-%m-%d')}: {name}")