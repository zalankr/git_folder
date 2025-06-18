import pyupbit as pu
import time
import pandas as pd
import kakao_alert

# Function to calculate the Relative Strength Index (RSI)
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

# Function to calculate the Moving Average (MA)
def GetMA(ohlcv, period=20, st=-1):
    close = ohlcv['close'].astype(float)
    ma = close.rolling(window=period).mean()
    return float(ma.iloc[st])

#
def GetCurrentPrice(ticker):
    price = pu.get_current_price(ticker)
    return price

df = pu.get_ohlcv("KRW-BTC", interval="day")
MAnow = GetMA(df, period=20, st=-1)
current_price = GetCurrentPrice("KRW-BTC")


kakao_alert.SendMessage(f"현재 20일 이동평균선(MA)은 {MAnow}입니다.")
kakao_alert.SendMessage(f"현재 가격은 {current_price}입니다.")

if current_price > MAnow:
    kakao_alert.SendMessage("현재 가격이 20일 이동평균선(MA)보다 높습니다. 매수 신호입니다.")
if current_price < MAnow:
    kakao_alert.SendMessage("현재 가격이 20일 이동평균선(MA)보다 낮습니다. 매도 신호입니다.")

# Get the RSI for the last 200 days of Bitcoin data
# df = pu.get_ohlcv("KRW-BTC", interval="minute240")

# rsinow = GetRSI(df, period=14, st=-1)

# if rsinow <= 30:
#     kakao_alert.SendMessage("RSI가 30 이하로 떨어졌습니다. 'KRW-BTC'에 대해 5000원 시장가 매수 주문을 실행합니다.")
# elif rsinow >= 70:
#     kakao_alert.SendMessage("RSI가 70 이상으로 올라갔습니다. 'KRW-BTC'이 있다면 시장가 매도 주문을 실행합니다.")
# else:
#     kakao_alert.SendMessage(f"현재 RSI 값은 {rsinow}입니다. 매매 조건에 해당하지 않습니다.")
