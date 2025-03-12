import pandas as pd
import numpy as np
import yfinance as yf

# GLD ETF 데이터 다운로드 (최대 기간)
data = yf.download('GLD', interval='1mo', multi_level_index=False)
if isinstance(data, pd.DataFrame) and not data.empty:
    if 'Close' in data.columns and not data['Close'].isnull().all():
        data = data[['Close']]
        data.dropna(inplace=True)
    else:
        raise ValueError("데이터에 'Close' 가격이 없습니다. 다운로드된 데이터를 확인하세요.")
else:
    raise ValueError("데이터를 불러오지 못했습니다. 인터넷 연결을 확인하세요.")

def calculate_metrics(returns):
    if returns.empty or returns.isnull().all():
        return 0, 0, 0, np.nan
    total_return = (returns + 1).prod() - 1
    total_return = total_return * 100
    cagr = (1 + total_return) ** (1 / (len(returns) / 52)) - 1
    cagr =cagr * 100
    mdd = (returns.cumsum() - returns.cumsum().cummax()).min()
    sharpe = returns.mean() / returns.std() * np.sqrt(52) if returns.std() != 0 else np.nan
    return total_return, cagr, mdd, sharpe

# 백테스트 실행
cash = 1.0  # 초기 자본 100%
position = 0  # 보유 상태 (0: 현금, 1: 매수)
entry_price = 0
returns = []
trade_dates = []

for i in range(2, len(data)):
    prev_close = float(data['Close'].iloc[i - 1])
    prev_prev_close = float(data['Close'].iloc[i - 2])
    current_close = float(data['Close'].iloc[i])
    
    if position == 0:  # 매수 조건 확인
        if (prev_close < prev_prev_close) and (current_close >= prev_close):
            position = 1
            entry_price = current_close * (1 + 0.0035)  # 수수료 및 슬리피지 포함
    
    elif position == 1:  # 매도 조건 확인
        if current_close < prev_close:
            position = 0
            exit_price = current_close * (1 - 0.0035)  # 수수료 및 슬리피지 포함
            returns.append((exit_price - entry_price) / entry_price)
            trade_dates.append(data.index[i])

# Buy & Hold 전략 비교
bh_returns = data['Close'].pct_change().dropna()

# 연도별 수익률 계산
def yearly_returns(returns, dates):
    returns_df = pd.DataFrame({'Date': dates, 'Returns': returns})
    returns_df['Year'] = returns_df['Date'].dt.year
    return returns_df.groupby('Year')['Returns'].sum()

strategy_yearly_returns = yearly_returns(returns, trade_dates)
bh_yearly_returns = data['Close'].resample('Y').ffill().pct_change().dropna()

# 지표 계산
returns_series = pd.Series(returns) if returns else pd.Series(dtype=float)
strategy_metrics = calculate_metrics(returns_series)
bh_metrics = calculate_metrics(bh_returns)

# 결과 출력
metrics_df = pd.DataFrame(
    [strategy_metrics, bh_metrics],
    columns=['Total Return', 'CAGR', 'MDD', 'Sharpe Ratio'],
    index=['Strategy', 'Buy & Hold']
)
print(metrics_df)

# 엑셀 저장
with pd.ExcelWriter("GOLD_Backtest.xlsx") as writer:
    metrics_df.to_excel(writer, sheet_name="Results")
    strategy_yearly_returns.to_excel(writer, sheet_name="Strategy Yearly Returns")
    bh_yearly_returns.to_excel(writer, sheet_name="Buy & Hold Yearly Returns")
