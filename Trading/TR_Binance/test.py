import USDTManager

# API 키 불러오기
with open("/var/autobot/TR_Binance/bnnkr.txt") as f:
    API_KEY, API_SECRET = [line.strip() for line in f.readlines()]


USDTM = USDTManager.USDTM(API_KEY, API_SECRET)
print(USDTM.get_spot_balance("BTC")['free'])
print(USDTM.get_spot_balance("BTC")['locked'])
print(USDTM.get_spot_balance("BTC")['balance'])