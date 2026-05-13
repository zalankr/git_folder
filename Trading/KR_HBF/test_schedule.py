from datetime import date, timedelta
from krft_scheduler import (
    is_trading_day, is_month_last_trading_day,
    is_rollover_day, expiry_day
)

start = date(2026, 5, 1)
end   = date(2026, 12, 31)

d = start
while d <= end:
    if is_trading_day(d):
        flags = []
        if is_month_last_trading_day(d):       flags.append("SIGNAL")
        if is_rollover_day(d, "MONTHLY"):      flags.append("ROLL-M")
        if is_rollover_day(d, "QUARTERLY"):    flags.append("ROLL-Q")
        if flags:
            print(f"{d} ({['월','화','수','목','금','토','일'][d.weekday()]}) {flags}")
    d += timedelta(days=1)