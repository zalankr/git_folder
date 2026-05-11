import os
from pathlib import Path
lines = [ln.strip() for ln in Path("/var/autobot/KIS/KRX_nkr.txt").read_text().splitlines() if ln.strip()]
os.environ["KRX_ID"] = lines[0]
os.environ["KRX_PW"] = lines[1]

from pykrx import stock

print("=== 모든 카테고리의 지수에서 '변동성' 키워드 검색 ===")
for market in ["KOSPI", "KOSDAQ", "KRX", "테마"]:
    try:
        tickers = stock.get_index_ticker_list(market=market)
        for t in tickers:
            try:
                name = stock.get_index_ticker_name(t)
                if any(k in name for k in ["변동성", "VKOSPI", "V-KOSPI", "Volatility"]):
                    print(f"  [{market}] 티커={t}, 이름={name}")
            except Exception:
                pass
    except Exception as e:
        print(f"  [{market}] 카테고리 실패: {e}")

print("\n=== KOSPI 카테고리 전체 티커 (참고) ===")
try:
    for t in stock.get_index_ticker_list(market="KOSPI")[:50]:
        try:
            print(f"  {t}: {stock.get_index_ticker_name(t)}")
        except Exception:
            pass
except Exception as e:
    print(f"  실패: {e}")