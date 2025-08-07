import pyupbit
import myUpbit

# Upbit 토큰 불러오기
with open("C:\Users\ilpus\Desktop\NKL_invest\upnkr.txt") as f:
# with open("C:/Users/GSR/Desktop/Python_project/upnkr.txt") as f:
    access_key, secret_key = [line.strip() for line in f.readlines()]

# 업비트 접속
upbit = pyupbit.Upbit(access_key, secret_key)
balances = upbit.get_balances()

# 테스트
TotalMoney = myUpbit.GetTotalMoney(balances)
print(TotalMoney)
Money = myUpbit.GetTotalRealMoney(balances)
print(Money)