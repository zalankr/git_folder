import pandas as pd

def xlsx_to_dataframe(file_name):  # XLSX 불러오기 함수
    try:
        file_path = f'C:/Users/GSR/Desktop/Python_project/git_folder/{file_name}'
        df = pd.read_excel(file_path)
        return df
    except Exception as e:
        print(f"오류 발생: {e}")
        return None

# xlsx 파일 불러오기
file_name = 'tiger화장품.xlsx'
df_a = xlsx_to_dataframe(file_name)

file_name = 'tiger200중공업.xlsx'
df_b = xlsx_to_dataframe(file_name)

# date 컬럼을 datetime 형식으로 변환
df_a['date'] = pd.to_datetime(df_a['date'], errors='coerce')
df_b['date'] = pd.to_datetime(df_b['date'], errors='coerce')

# 필요한 컬럼만 추출 및 컬럼 이름 변경
df_a = df_a[['date', 'close']].rename(columns={'close': 'Stock_A'})
df_b = df_b[['date', 'close']].rename(columns={'close': 'Stock_B'})

# 날짜 기준 병합 (inner join: 공통 날짜만 유지)
merged_df = pd.merge(df_a, df_b, on='date', how='inner')
print(merged_df.tail(20))

# 상관계수 계산 (피어슨 기본값)
correlation = merged_df['Stock_A'].corr(merged_df['Stock_B'])
print(f"Stock_A와 Stock_B의 상관계수: {correlation:.4f}")
