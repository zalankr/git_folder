import pyupbit as pu
import time
import pandas as pd
import kakao_alert

def GetRSI(ohlcv, period=14, st=-1):
    ohlcv['close'] = ohlcv['close'].astype(float)
    delta = ohlcv['close'].diff()
    up, down = delta.copy(), delta.copy()
    up[up < 0] = 0
    down[down > 0] = 0
    _gain = up.ewm(com=(period - 1), min_periods=period).mean()
    _loss = down.abs().ewm(com=(period - 1), min_periods=period).mean()
    rs = _gain / _loss
    return float(pd.Series(100 - (100 / (1 + rs)), name='RSI').iloc[st])

# Get the RSI for the last 200 days of Bitcoin data
df = pu.get_ohlcv("KRW-BTC", interval="minute240")

rsinow = GetRSI(df, period=14, st=-1)

if rsinow <= 30:
    kakao_alert.SendMessage("RSI가 30 이하로 떨어졌습니다. 'KRW-BTC'에 대해 5000원 시장가 매수 주문을 실행합니다.")
elif rsinow >= 70:
    kakao_alert.SendMessage("RSI가 70 이상으로 올라갔습니다. 'KRW-BTC'이 있다면 시장가 매도 주문을 실행합니다.")
else:
    kakao_alert.SendMessage(f"현재 RSI 값은 {rsinow}입니다. 매매 조건에 해당하지 않습니다.")
