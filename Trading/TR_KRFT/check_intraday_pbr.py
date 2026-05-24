"""
check_intraday_pbr.py
======================
장중 시간에 실행하여 pykrx가 당일 PBR을 어떻게 응답하는지 확인.
실행:
    /var/autobot/venv_krx/bin/python /home/ec2-user/check_intraday_pbr.py

확인 포인트:
  1) get_index_fundamental(오늘, 오늘, "1001") → 빈값? 전일값? 장중잠정값?
  2) get_market_fundamental(오늘) → 빈값? 전일값?
  3) get_index_ohlcv(오늘, 오늘, "1001") → 실시간 KOSPI 지수 받아지나?
"""
import io
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

_CRED_FILE = Path("/var/autobot/KIS/KRX_nkr.txt")
if _CRED_FILE.is_file():
    lines = [ln.strip() for ln in _CRED_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if len(lines) >= 2:
        os.environ.setdefault("KRX_ID", lines[0])
        os.environ.setdefault("KRX_PW", lines[1])

_buf, _stdout = io.StringIO(), sys.stdout
sys.stdout = _buf
from pykrx import stock
sys.stdout = _stdout


def main():
    now = datetime.now()
    today = now.strftime("%Y%m%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y%m%d")
    # 주말 보정: 직전 영업일
    d = now - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    last_bday = d.strftime("%Y%m%d")

    print(f"실행 시각  : {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"오늘       : {today}")
    print(f"직전 영업일: {last_bday}")
    print("=" * 70)

    # 1) 오늘 지수 PBR
    print("\n[1] get_index_fundamental(오늘, 오늘, '1001')")
    print("-" * 70)
    try:
        df = stock.get_index_fundamental(today, today, "1001")
        if df.empty:
            print("  → 빈 DataFrame (당일 데이터 없음)")
        else:
            print(df)
            pbr_today = float(df["PBR"].iloc[-1])
            print(f"  PBR 값 : {pbr_today}")
            if pbr_today == 0:
                print("  → 값이 0 (당일 미공시)")
    except Exception as e:
        print(f"  오류: {e}")

    # 2) 직전 영업일 지수 PBR (KRX 공식값 - 비교 기준)
    print(f"\n[2] get_index_fundamental({last_bday}, {last_bday}, '1001')")
    print("-" * 70)
    try:
        df = stock.get_index_fundamental(last_bday, last_bday, "1001")
        if df.empty:
            print("  → 빈 DataFrame")
        else:
            print(df)
            pbr_yday = float(df["PBR"].iloc[-1])
            per_yday = float(df["PER"].iloc[-1])
            print(f"  [공식] 어제 PBR : {pbr_yday}")
            print(f"  [공식] 어제 PER : {per_yday}")
    except Exception as e:
        print(f"  오류: {e}")

    # 3) 오늘 KOSPI 지수 OHLCV (장중 실시간 지수 받기 테스트)
    print(f"\n[3] get_index_ohlcv({today}, {today}, '1001') - 장중 실시간 지수")
    print("-" * 70)
    try:
        df = stock.get_index_ohlcv(today, today, "1001")
        if df.empty:
            print("  → 빈 DataFrame (장중 지수 미수신)")
        else:
            print(df)
            today_close = float(df["종가"].iloc[-1])
            print(f"  오늘 종가/현재가 : {today_close}")
    except Exception as e:
        print(f"  오류: {e}")

    # 4) 어제 KOSPI 종가 (비례 환산 기준점)
    print(f"\n[4] get_index_ohlcv({last_bday}, {last_bday}, '1001') - 어제 종가")
    print("-" * 70)
    try:
        df = stock.get_index_ohlcv(last_bday, last_bday, "1001")
        if df.empty:
            print("  → 빈 DataFrame")
        else:
            yday_close = float(df["종가"].iloc[-1])
            print(f"  어제 종가 : {yday_close}")
    except Exception as e:
        print(f"  오류: {e}")

    # 5) 종목별 fundamental 당일 호출 테스트
    print(f"\n[5] get_market_fundamental(오늘={today}, market='KOSPI')")
    print("-" * 70)
    try:
        df = stock.get_market_fundamental(date=today, market="KOSPI")
        print(f"  반환 종목 수 : {len(df)}")
        if not df.empty:
            print(f"  샘플:")
            print(df.head(3))
            print(f"  주의: 이 BPS는 결산 보고서 기준이므로 장중에도 어제와 동일할 가능성 큼")
    except Exception as e:
        print(f"  오류: {e}")

    print("\n" + "=" * 70)
    print("[해석 가이드]")
    print("  - [1] 빈값/0  → 당일 PBR 직접 조회 불가 → 비례환산 방식 필수")
    print("  - [1] 정상값  → 직접 조회 가능 → 환산 불필요")
    print("  - [3] 정상값  → 장중 KOSPI 실시간 지수 조회 가능")
    print("  - [3] 빈값    → KIS API 등 다른 소스로 KOSPI 지수 조회 필요")


if __name__ == "__main__":
    main()
