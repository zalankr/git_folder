import pandas as pd
import pybithumb

data = pybithumb.get_ohlcv("XRP")
period = 10

수수료 = 0.0005
슬리피지 = 0.0002
tax = 수수료 + 슬리피지

df = data.copy()
df.loc[:, 'MA'] = df.loc[:, 'close'].rolling(window=period).mean()
df.loc[:, 'MA120'] = df.loc[:, 'close'].rolling(window=120).mean()

df.loc[:, 'bsignal'] = (df.loc[:, 'close'].shift(1) >= df.loc[:, 'MA'].shift(1)) & \
    (df.loc[:, 'close'].shift(1) >= df.loc[:, 'MA120'].shift(1))

df.loc[:, 'ssignal'] = df.loc[:, 'close'].shift(1) < df.loc[:, 'MA'].shift(1)
df.loc[:, 'differ'] = df.bsignal != df.bsignal.shift(1)

save_path = "c:/users/ilpus/pythonprojects/git_folder/XRP_data.xlsx"  # 원하는 경로로 변경
df.to_excel(save_path, index=True, sheet_name="XRP Data")

print(f"파일이 저장되었습니다: {save_path}")
# df.loc[:, 'Buy'] = df.loc[bsignal, 'open']
# df.loc[:, 'Sell'] = df.loc[ssignal, 'open']

# df.loc[:, 'Buy'] = df.loc[differ, 'Buy']
# df.loc[:, 'Sell'] = df.loc[differ, 'Sell']

# df = df.drop(df[differ == False].index, axis=0)

# # 🛠️ trade와 sell의 길이를 맞춰줌
# trade = pd.DataFrame(df.loc[:, 'Buy'].dropna())
# sell = df.loc[:, 'Sell'].dropna()

# if len(trade) > len(sell):
#     trade = trade.iloc[:len(sell)]
# elif len(sell) > len(trade):
#     sell = sell.iloc[:len(trade)]

# # 🛠️ trade가 비어 있을 경우 예외 처리
# if trade.empty or sell.empty:
#     print("거래 데이터가 없습니다.")
#     cacul = 1
#     trade_count = 0
# else:
#     trade.loc[:, 'Sell'] = sell.values
#     trade_count = len(trade)
#     trade.insert(loc=2, column='return', 
#                  value=((trade['Sell'] - (trade['Sell'] * tax)) / 
#                         (trade['Buy'] + (trade['Buy'] * tax))))
#     cacul = trade.loc[:, 'return'].cumprod().iloc[-1]

# buy0 = data.iloc[0, 0]
# sell0 = data.iloc[-1, 3]
# buy_and_hold = (sell0 - (sell0 * tax)) / (buy0 + (buy0 * tax))

# print("Buy and Hold:", buy_and_hold)
# print("*" * 50)

# if not df.empty:
#     print("MA : {}".format(df.iloc[-1, 0]))
#     print("Return : {:.2%}".format(df.iloc[-1, 1] - 1))
#     print("투자횟수 :", trade_count, "수수료 : {:.2%}".format(수수료), 
#           "슬리피지 : {:.2%}".format(슬리피지))
# else:
#     print("데이터가 부족하여 계산할 수 없습니다.")


