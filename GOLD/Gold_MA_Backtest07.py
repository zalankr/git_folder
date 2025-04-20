import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def download_data(ticker, start, end):
    data = yf.download(ticker, start=start, end=end, auto_adjust=True, multi_level_index=False)
    
    return data['Close']

def calculate_performance(df, strategy_col, fee=0.0033, slippage=0.0001):
    buy_price = 0
    position = 0
    equity = 1
    cash = 1

    for i in range(1, len(df)):
        if df[strategy_col].iloc[i] == 1 and position == 0:  # Buy signal
            buy_price = df['Price'].iloc[i] * (1 + fee + slippage)
            position = cash / buy_price
            cash = 0

        elif df[strategy_col].iloc[i] == -1 and position > 0:  # Sell signal
            cash = position * df['Price'].iloc[i] * (1 - fee - slippage)
            position = 0

        equity = cash if position == 0 else position * df['Price'].iloc[i]
        df.at[df.index[i], 'Equity'] = equity

    return df

def calculate_metrics(df, equity_col):
    final_return = df[equity_col].iloc[-1] - 1
    years = (df.index[-1] - df.index[0]).days / 365.25
    cagr = (df[equity_col].iloc[-1]) ** (1 / years) - 1

    rolling_max = df[equity_col].cummax()
    mdd = ((rolling_max - df[equity_col]) / rolling_max).max()

    return final_return, cagr, mdd

# Parameters
ticker = 'GLD'
start_date = '2010-01-01'
end_date = '2024-01-01'

# Download data
prices = download_data(ticker, start_date, end_date)
data = pd.DataFrame(prices)
data.columns = ['Price']
data['52W_High'] = data['Price'].rolling(window=252).max()

# Strategy Logic
data['Signal'] = np.where(data['Price'] > data['52W_High'].shift(1), 1, 0)
data['Signal'] = np.where(data['Price'] < data['52W_High'].shift(1) * 0.97, -1, data['Signal'])

# Backtest
data['Equity'] = 1
result = calculate_performance(data, 'Signal')

# Buy & Hold Performance
data['BuyHold'] = (data['Price'] / data['Price'].iloc[0])

# Metrics
strategy_return, strategy_cagr, strategy_mdd = calculate_metrics(result, 'Equity')
bh_return, bh_cagr, bh_mdd = calculate_metrics(result, 'BuyHold')

print("=== Strategy Performance ===")
print(f"Final Return: {strategy_return:.2%}")
print(f"CAGR: {strategy_cagr:.2%}")
print(f"MDD: {strategy_mdd:.2%}")

print("\n=== Buy & Hold Performance ===")
print(f"Final Return: {bh_return:.2%}")
print(f"CAGR: {bh_cagr:.2%}")
print(f"MDD: {bh_mdd:.2%}")

# Plotting
plt.figure(figsize=(12, 6))
plt.plot(data.index, data['Equity'], label='52W Breakout Strategy')
plt.plot(data.index, data['BuyHold'], label='Buy & Hold')
plt.legend()
plt.title('GLD: 52-Week Breakout vs Buy & Hold')
plt.ylabel('Equity Growth')
plt.show()

