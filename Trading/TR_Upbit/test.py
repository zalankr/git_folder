from datetime import datetime, timezone


now = datetime.now(timezone.utc)
current_date = now.date()
current_time = now.time()
print(current_date, current_time)