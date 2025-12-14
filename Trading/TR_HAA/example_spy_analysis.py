"""
SPY ETF 60개월 전고가 분석 함수 사용 예제

한국투자증권 API를 활용하여 SPY ETF의 최근 60개월 동안의 
일별 종가를 조회하고, 전고가 대비 현재가 위치를 분석합니다.
"""

from KIS_US import KIS_API

# API 초기화
api = KIS_API(
    key_file_path="your_key_file.txt",
    token_file_path="your_token_file.json",
    cano="your_cano",
    acnt_prdt_cd="your_acnt_prdt_cd"
)

# SPY ETF 전고가 분석
result = api.get_spy_60month_analysis("SPY")

# 결과 출력
if isinstance(result, dict):
    print("=" * 50)
    print("SPY ETF 전고가 분석 결과")
    print("=" * 50)
    print(f"현재가: ${result['current_price']:,.2f}")
    print(f"전고가: ${result['all_time_high']:,.2f}")
    print(f"전고가 대비 비율: {result['percentage_from_ath']:.2f}%")
    print("=" * 50)
    
    # 추가 분석
    if result['percentage_from_ath'] >= 95:
        print("📈 현재 전고가 근처에 있습니다!")
    elif result['percentage_from_ath'] >= 90:
        print("📊 전고가 대비 약간 하락한 상태입니다.")
    elif result['percentage_from_ath'] >= 80:
        print("📉 전고가 대비 중간 조정 구간입니다.")
    else:
        print("⚠️ 전고가 대비 큰 조정 구간입니다.")
else:
    print(f"오류: {result}")


# 다른 ETF에도 적용 가능
print("\n다른 ETF 분석 예제:")
tickers = ["QQQ", "IWM", "DIA"]

for ticker in tickers:
    result = api.get_spy_60month_analysis(ticker)
    if isinstance(result, dict):
        print(f"\n{ticker}:")
        print(f"  현재가: ${result['current_price']:,.2f}")
        print(f"  전고가: ${result['all_time_high']:,.2f}")
        print(f"  전고가 대비: {result['percentage_from_ath']:.2f}%")
