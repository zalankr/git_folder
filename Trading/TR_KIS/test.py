from datetime import datetime

now = datetime.now()

current_date = now.date()
current_time = now.time()
print(current_date, current_time)

current_date = datetime.strptime("2025-11-03", "%Y-%m-%d").date()
current_time = datetime.strptime("15:00:00", "%H:%M:%S").time()
print(current_date, current_time)