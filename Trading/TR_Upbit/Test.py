import json
import time as time_module  # time 모듈을 별칭으로 import
import UP_signal_weight as UP


Upbit_data_path = "C:/Users/ilpus/Desktop/git_folder/Trading/TR_Upbit/Upbit_data.json"

now, current_time, TR_time = UP.what_time()
print(f"현재 시간: {now.strftime('%Y-%m-%d %H:%M:%S')}, TR_time: {TR_time}")


with open(Upbit_data_path, 'r', encoding='utf-8') as f:
    Upbit_data = json.load(f)

print(Upbit_data)
print(type(Upbit_data))
print(Upbit_data["Invest_quantity"])
print(type(Upbit_data["Invest_quantity"]))