import json
from datetime import datetime

now = datetime.now()
# Upbit_data 만들고 저장하기
Upbit_data = {
    "Date" : now.strftime('%Y-%m-%d'),
    "Position" : "Hold_full",
    "ETH_weight" : 0.99,
    "ETH_target" : 5.48575958,
    "CASH_weight" : 0.01,
    "Invest_quantity" : 0.0,
    "Total_balance" : 45522195.0,
    "ETH" : 5.48575958,
    "KRW" : 10536887.0,
    "Last_month_Total" : 43448578.0,
    "Last_year_Total" : 40859674.0,
    "Daily_return" : 0.0,
    "Monthly_return" : 0.0,
    "Yearly_return" : 5.55
}

# 0.0, 0.01, 0.495, 0.505, 0.99, 1.0

# JSON 파일로 저장
with open('C:/Users/ilpus/Desktop/git_folder/Trading/TR_Upbit/Upbit_data.json', 'w', encoding='utf-8') as f:
    json.dump(Upbit_data, f, ensure_ascii=False, indent=4)

# JSON 파일에서 읽기 테스트
with open('C:/Users/ilpus/Desktop/git_folder/Trading/TR_Upbit/Upbit_data.json', 'r', encoding='utf-8') as f:
    Upbit_data = json.load(f)
print(Upbit_data)
