import json

Upbit_data = {
  "time": {
    "saved_time": "9:26",
    "loaded_time": "8:58",
  },
  "trade": {
    "signal20": "ETH",
    "signal40": "ETH",
    "trade": "hold(ETH>ETH)",
    "weight": 1.0
  }
}

# JSON 파일로 저장
with open('C:/Users/ilpus/Desktop/git_folder/Trading/CR_TR_Upbit/Upbit_data.json', 'w', encoding='utf-8') as f:
    json.dump(Upbit_data, f, ensure_ascii=False, indent=4)

# JSON 파일에서 읽기 테스트
with open('C:/Users/ilpus/Desktop/git_folder/Trading/CR_TR_Upbit/Upbit_data.json', 'r', encoding='utf-8') as f:
    Upbit_data = json.load(f)
print(Upbit_data)
