import KIS_US
import sys

# KIS instance 생성
key_file_path = "/var/autobot/TR_USAA/kis63604155nkr.txt"
token_file_path = "/var/autobot/TR_USAA/kis63604155_token.json"
cano = "63604155"
acnt_prdt_cd = "01"
KIS = KIS_US.KIS_API(key_file_path, token_file_path, cano, acnt_prdt_cd)

message = []

USD1 = KIS.get_US_dollar_balance()
for key, value in USD1.items():
    message.append(f"{key}: {value}")
USD2 = KIS.get_US_order_available()
message.append(f"USD: {USD2}")

USLA_ticker = ['UPRO', 'TQQQ', 'EDC', 'TMV', 'TMF']
HAA_ticker = ['SPY', 'IWM', 'VEA', 'VWO', 'PDBC', 'VNQ', 'TLT', 'IEF', 'BIL']

stock_balance1 = 0
stock_balance2 = 0

for ticker in USLA_ticker:
    result = KIS.get_ticker_balance(ticker)
    if isinstance(result, dict):
        for key, value in result.items():
            message.append(f"{key}: {value}")
            eval_amt = result['eval_amount']
            stock_balance1 += eval_amt
        price = KIS.get_US_current_price(ticker)
        message.append(f"ticker: {ticker}, current price: {price}")

for ticker in HAA_ticker:
    result = KIS.get_ticker_balance(ticker)
    if isinstance(result, dict):   
        for key, value in result.items():
            message.append(f"{key}: {value}")
            eval_amt = result['eval_amount']
            stock_balance1 += eval_amt
        price = KIS.get_US_current_price(ticker)
        message.append(f"ticker: {ticker}, current price: {price}")

stocks = KIS.get_US_stock_balance()
for stock in stocks:
    eval_amt = stock.get('eval_amt', 0)
    message.append(f"ticker: {stock['ticker']}, eval_amt: {eval_amt}")
    stock_balance2 += eval_amt
    message.append(f"stock_balance: {stock_balance2}")


total1_1 = stock_balance1 + USD2
total1_2 = stock_balance1 + USD1['withdrawable']

total2_1 = stock_balance2 + USD2
total2_2 = stock_balance2 + USD1['withdrawable']
message.append(f"total1_1: {total1_1}, total1_2: {total1_2}")
message.append(f"total2_1: {total2_1}, total2_2: {total2_2}")
print("\n".join(message))

sys.exit(0)