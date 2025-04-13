import pandas as pd

# CSV 파일 불러오기
df_a = pd.read_csv('KODEX반도체invest.csv', parse_dates=['date'])
df_b = pd.read_csv('삼성전자.csv', parse_dates=['date'])

# 'close'에서 콤마 제거 후 숫자로 변환
df_a['close'] = df_a['close'].astype(str).str.replace(',', '').astype(float)
df_b['close'] = df_b['close'].astype(str).str.replace(',', '').astype(float)

# 필요한 컬럼만 추출 및 컬럼 이름 변경
df_a = df_a[['date', 'close']].rename(columns={'close': 'Stock_A'})
df_b = df_b[['date', 'close']].rename(columns={'close': 'Stock_B'})

# 날짜 기준 병합 (inner join: 공통 날짜만 유지)
merged_df = pd.merge(df_a, df_b, on='date', how='inner')
print(merged_df.tail(20))
# 상관계수 계산 (피어슨 기본값)
correlation = merged_df['Stock_A'].corr(merged_df['Stock_B'])

print(f"Stock_A와 Stock_B의 상관계수: {correlation:.4f}")
