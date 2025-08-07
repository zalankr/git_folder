import pyupbit
import myUpbit
import time

# Upbit 토큰 불러오기
with open("C:/Users/ilpus/Desktop/NKL_invest/upnkr.txt") as f:
# with open("C:/Users/GSR/Desktop/Python_project/upnkr.txt") as f:
    access_key, secret_key = [line.strip() for line in f.readlines()]

# 업비트 접속
upbit = pyupbit.Upbit(access_key, secret_key)
balances = upbit.get_balances()

# Ticker별 Balance 확인
ETH_Remain = upbit.get_balance("ETH")
BTC_Remain = upbit.get_balance("BTC")
KRW_Remain = upbit.get_balance("KRW")
Total_Balance = myUpbit.GetTotalRealMoney(balances)

print("ETH_Remain:", ETH_Remain)
print("BTC_Remain:", BTC_Remain)
print("KRW_Remain:", KRW_Remain)
print("Total_Balance:", Total_Balance)

# 전회 Json파일 불러오기

# Ticker별 현재가와 MA 비교
## ETH 20MA
ETH_data = pyupbit.get_ohlcv(ticker="KRW-ETH", interval="day")
ETH_20MA = myUpbit.GetMA(ETH_data, 20, -1)
ETH20_sigal = True
if ETH_data["close"].iloc[-1] > ETH_20MA:
    ETH20_sigal = True
    print("ETH_20MA UP")
else:
    ETH20_sigal = False
    print("ETH_20MA DOWN")

print(ETH20_sigal, type(ETH20_sigal))

## ETH 40MA

## BTC 30MA



# 테스트
