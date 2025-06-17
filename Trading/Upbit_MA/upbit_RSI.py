import pyupbit as pu
import time
import pandas as pd

def GetRSI(ohlcv, period=14):
    ohlcv['close'] = ohlcv['close'].astype(float)
    delta = ohlcv['close'].diff()
    up, down = delta.copy(), delta.copy()
    up[up < 0] = 0
    down[down > 0] = 0
    _gain = up.ewm(com=(period - 1), min_periods=period).mean()
    _loss = down.abs().ewm(com=(period - 1), min_periods=period).mean()
    rs = _gain / _loss
    return pd.Series(100 - (100 / (1 + rs)), name='RSI')

# Get the RSI for the last 200 days of Bitcoin data
df = pu.get_ohlcv("KRW-BTC", interval="day", count=200)

print("어제RSI:", GetRSI(df, period=14).iloc[-2])
print("오늘RSI:", GetRSI(df, period=14).iloc[-1])
