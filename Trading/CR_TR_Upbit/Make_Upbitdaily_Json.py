import json

Upbit_daily = {
  "ETH20": {
    "ticker": "ETH",
    "position": True,
    "weight in ticker ": 0.5,
    "Quantity": 2.74287979
  },
  "ETH40": {
    "ticker": "ETH",
    "position": True,
    "weight in ticker ": 0.5,
    "Quantity": 2.74287979
  },
  "BTC30": {
    "ticker": "BTC",
    "position": True,
    "weight in ticker ": 1.0,
    "Quantity": 0.06701798
  },
  "CASH": {
    "ticker": "CASH",
    "position": 0.0,
    "weight in balances ": 0.0,
    "Quantity": 2.74287979
  }  
}

# JSON 파일로 저장
with open('C:/Users/ilpus/Desktop/git_folder/Trading/CR_TR_Upbit/Upbit_daily.json', 'w', encoding='utf-8') as f:
    json.dump(Upbit_daily, f, ensure_ascii=False, indent=4)

# JSON 파일에서 읽기 테스트
with open('C:/Users/ilpus/Desktop/git_folder/Trading/CR_TR_Upbit/Upbit_daily.json', 'r', encoding='utf-8') as f:
    Upbit_daily = json.load(f)
print(Upbit_daily)
