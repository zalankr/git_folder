import json

Upbit_data = {
  "date": {
    "record day": "2025-08-23"
  },
  "position": {
    "position": "Hold_full",
    "ETH_weight": 0.99,
    "ETH_target": 5.48575958,
    "CASH_weight": 0.01,
    "Invest_Quantity": 0.0,
    "ETH_balance": 5.48575958,
    "KRW_balance": 10536887.0
  }
}

# 0.0, 0.01, 0.495, 0.505, 0.99, 1.0

# JSON 파일로 저장
with open('C:/Users/ilpus/Desktop/git_folder/Trading/CR_TR_Upbit/Upbit_data.json', 'w', encoding='utf-8') as f:
    json.dump(Upbit_data, f, ensure_ascii=False, indent=4)

# JSON 파일에서 읽기 테스트
with open('C:/Users/ilpus/Desktop/git_folder/Trading/CR_TR_Upbit/Upbit_data.json', 'r', encoding='utf-8') as f:
    Upbit_data = json.load(f)
print(Upbit_data)
