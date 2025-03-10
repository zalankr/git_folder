import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


# 데이터 다운로드
file_path = "C:/Users/ilpus/Desktop/INVEST/R&D/KRX_gold/gold_1.xlsx"
data = pd.read_excel(file_path)

data.set_index(keys='date', inplace = True)


# 거래수수료와 슬리피지 설정
transaction_fee = 0.0033  # 0.33% 거래 수수료
slippage = 0.0002  # 0.02% 슬리피지

# 18개월 전 가격을 계산하는 함수
def get_price_18_months_ago(df, current_date):
    months_ago = pd.DateOffset(months=20)
    date_18_months_ago = current_date - months_ago
    return df.loc[df.index <= date_18_months_ago].iloc[-1]['close'] if date_18_months_ago in df.index else None

# 백테스트 로직
cash = 1000000  # 초기 자산 100만원
holding = 0  # 초기 보유 금액 0
buy_price = 0  # 매수 가격
portfolio_value = []  # 자산 변화 기록
buy_dates = []  # 매수일 기록
sell_dates = []  # 매도일 기록


for i in range(18, len(data)):  # 18일 이후부터 시작
    current_date = data.index[i]
    current_price = data['close'][i]
    price_18_months_ago = get_price_18_months_ago(data, current_date)
    
    # 매수 조건: 오늘 종가가 18개월 전 가격보다 크거나 같으면 매수
    if price_18_months_ago and current_price >= price_18_months_ago and holding == 0:
        buy_price = current_price * (1 + slippage)  # 슬리피지 고려
        holding = cash / buy_price * (1 - transaction_fee)  # 거래 수수료 반영
        cash = 0  # 매수 후 현금은 0
        buy_dates.append(current_date)  # 매수일 기록
        
    # 매도 조건: 오늘 종가가 18개월 전 가격보다 낮으면 매도
    elif price_18_months_ago and current_price < price_18_months_ago and holding > 0:
        sell_price = current_price * (1 - slippage)  # 슬리피지 고려
        cash = holding * sell_price * (1 - transaction_fee)  # 거래 수수료 반영
        holding = 0  # 매도 후 보유 금액은 0
        sell_dates.append(current_date)  # 매도일 기록
        
    # 자산 기록 (현재 보유 금액과 현금)
    portfolio_value.append(cash + holding * current_price)


# 데이터 보정
j = len(portfolio_value)
if i != j:
    for k in range(i - j + 1):
        portfolio_value.insert(0, 1000000)
    
# 결과 시각화
data['Portfolio'] = portfolio_value
data[['close', 'Portfolio']].plot(figsize=(10, 6))
plt.title('Backtest of Gold Trading Strategy')
plt.show()

# 최종 자산
final_portfolio_value = cash + holding * data['close'].iloc[-1]
print(f"최종 자산: {final_portfolio_value:,.2f} 원")

# 수익률 계산
initial_investment = 1000000
total_return = (final_portfolio_value - initial_investment) / initial_investment * 100
print(f"전체 수익률: {total_return:.2f}%")

# CAGR (연평균 성장률) 계산
years = (data.index[-1] - data.index[0]).days / 365.25
CAGR = (final_portfolio_value / initial_investment) ** (1 / years) - 1
print(f"CAGR (연평균 성장률): {CAGR * 100:.2f}%")

# MDD (Maximum Drawdown) 계산
portfolio_series = pd.Series(portfolio_value, index=data.index[0:])
drawdowns = portfolio_series / portfolio_series.cummax() - 1
MDD = drawdowns.min()
print(f"MDD (최대 낙폭): {MDD * 100:.2f}%")

# 연도별 수익률 계산
# data['Year'] = data.index.year
# yearly_returns = data.groupby('Year').apply(lambda x: (x['Portfolio'].iloc[-1] - x['Portfolio'].iloc[0]) / x['Portfolio'].iloc[0])
# print("연도별 수익률:")
# print(yearly_returns * 100)
