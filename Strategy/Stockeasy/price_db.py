#!/usr/bin/env python3
"""
KRX 가격 DB 관리 (DuckDB 기반)

설치:
  pip install duckdb pykrx pandas

구조:
  /var/autobot/DB/krx_prices.duckdb
    └─ daily_ohlcv (date, code, open, high, low, close, volume, value)
    └─ fundamentals (date, code, per, pbr, eps, bps, div, dps, roe_est)
    └─ market_cap (date, code, mcap, shares)

사용:
  # 초기 1회: 과거 1년 벌크 로드
  python3 price_db.py --init
  # 매일: 전일 데이터만 증분
  python3 price_db.py --daily
  # 스크리너에서 사용:
  from price_db import PriceDB
  db = PriceDB()
  df = db.get_ohlcv('005930', start='2024-01-01', end='2024-12-31')
"""
import os
import sys
import time
import argparse
from datetime import datetime, timedelta
import duckdb
import pandas as pd
from pykrx import stock as krx

DB_PATH = "/var/autobot/DB/krx_prices.duckdb"


class PriceDB:
    def __init__(self, db_path: str = DB_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.conn = duckdb.connect(db_path)
        self._ensure_schema()

    def _ensure_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_ohlcv (
                date    DATE    NOT NULL,
                code    VARCHAR NOT NULL,
                open    DOUBLE,
                high    DOUBLE,
                low     DOUBLE,
                close   DOUBLE,
                volume  BIGINT,
                value   BIGINT,
                PRIMARY KEY (date, code)
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS fundamentals (
                date    DATE    NOT NULL,
                code    VARCHAR NOT NULL,
                per     DOUBLE,
                pbr     DOUBLE,
                eps     DOUBLE,
                bps     DOUBLE,
                div_yld DOUBLE,
                dps     DOUBLE,
                roe_est DOUBLE,
                PRIMARY KEY (date, code)
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS market_cap (
                date   DATE    NOT NULL,
                code   VARCHAR NOT NULL,
                mcap   BIGINT,
                shares BIGINT,
                PRIMARY KEY (date, code)
            )
        """)
        # 인덱스: 종목별 시계열 조회 가속
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_ohlcv_code ON daily_ohlcv(code)")

    # ---------- 증분 업데이트 ----------
    def upsert_ohlcv_for_date(self, date: str) -> int:
        """
        특정 날짜의 전 시장 OHLCV를 한 번의 API 호출로 가져와 upsert.
        date: 'YYYYMMDD'
        
        핵심: pykrx의 get_market_ohlcv_by_ticker는 
              "그날 하루 전 종목의 OHLCV"를 한 번에 반환 → 2600회 호출이 1회로
        """
        total = 0
        for mkt in ("KOSPI", "KOSDAQ"):
            try:
                df = krx.get_market_ohlcv_by_ticker(date, market=mkt)
            except Exception as e:
                print(f"[WARN] {mkt} {date} OHLCV 실패: {e}")
                continue
            if df is None or df.empty:
                continue
            df = df.reset_index().rename(columns={
                "티커": "code", "시가": "open", "고가": "high", "저가": "low",
                "종가": "close", "거래량": "volume", "거래대금": "value"
            })
            df["date"] = pd.to_datetime(date).date()
            df = df[["date", "code", "open", "high", "low", "close", "volume", "value"]]
            # DuckDB의 INSERT OR REPLACE는 PK 충돌 시 덮어씀
            self.conn.execute("DELETE FROM daily_ohlcv WHERE date = ?", [df["date"].iloc[0]])
            self.conn.register("tmp_df", df)
            self.conn.execute("INSERT INTO daily_ohlcv SELECT * FROM tmp_df")
            total += len(df)
            time.sleep(0.3)
        print(f"  OHLCV {date}: {total}종목 저장")
        return total

    def upsert_fundamentals_for_date(self, date: str) -> int:
        total = 0
        for mkt in ("KOSPI", "KOSDAQ"):
            try:
                df = krx.get_market_fundamental(date, market=mkt)
            except Exception as e:
                print(f"[WARN] {mkt} {date} fundamental 실패: {e}")
                continue
            if df is None or df.empty:
                continue
            df = df.reset_index().rename(columns={
                "티커": "code", "PER": "per", "PBR": "pbr",
                "EPS": "eps", "BPS": "bps", "DIV": "div_yld", "DPS": "dps"
            })
            df["date"] = pd.to_datetime(date).date()
            # ROE 역산
            df["roe_est"] = ((df["pbr"] / df["per"]) * 100).where(
                (df["per"] > 0) & (df["pbr"] > 0)
            )
            df = df[["date", "code", "per", "pbr", "eps", "bps", "div_yld", "dps", "roe_est"]]
            self.conn.execute("DELETE FROM fundamentals WHERE date = ?", [df["date"].iloc[0]])
            self.conn.register("tmp_f", df)
            self.conn.execute("INSERT INTO fundamentals SELECT * FROM tmp_f")
            total += len(df)
            time.sleep(0.3)
        print(f"  Fundamental {date}: {total}종목 저장")
        return total

    def upsert_market_cap_for_date(self, date: str) -> int:
        total = 0
        for mkt in ("KOSPI", "KOSDAQ"):
            try:
                df = krx.get_market_cap(date, market=mkt)
            except Exception as e:
                print(f"[WARN] {mkt} {date} mcap 실패: {e}")
                continue
            if df is None or df.empty:
                continue
            df = df.reset_index().rename(columns={
                "티커": "code", "시가총액": "mcap", "상장주식수": "shares"
            })
            df["date"] = pd.to_datetime(date).date()
            df = df[["date", "code", "mcap", "shares"]]
            self.conn.execute("DELETE FROM market_cap WHERE date = ?", [df["date"].iloc[0]])
            self.conn.register("tmp_m", df)
            self.conn.execute("INSERT INTO market_cap SELECT * FROM tmp_m")
            total += len(df)
            time.sleep(0.3)
        print(f"  MarketCap {date}: {total}종목 저장")
        return total

    # ---------- 조회 ----------
    def get_ohlcv(self, code: str, start: str = None, end: str = None) -> pd.DataFrame:
        """단일 종목 시계열 조회 (수백μs 수준)"""
        where = ["code = ?"]
        params = [code]
        if start:
            where.append("date >= ?")
            params.append(start)
        if end:
            where.append("date <= ?")
            params.append(end)
        q = f"""
            SELECT date, open, high, low, close, volume, value
            FROM daily_ohlcv
            WHERE {' AND '.join(where)}
            ORDER BY date
        """
        return self.conn.execute(q, params).df()

    def get_all_latest_fundamentals(self) -> pd.DataFrame:
        """최신일 펀더멘털 전체 (VALUE 스크리너용 — 단일 쿼리로 끝)"""
        return self.conn.execute("""
            SELECT f.*, m.mcap
            FROM fundamentals f
            JOIN market_cap m USING (date, code)
            WHERE f.date = (SELECT MAX(date) FROM fundamentals)
        """).df()

    def get_latest_date(self) -> str:
        r = self.conn.execute("SELECT MAX(date) FROM daily_ohlcv").fetchone()
        return r[0].strftime("%Y%m%d") if r[0] else None

    def get_missing_trading_days(self, lookback_days: int = 30) -> list:
        """최근 lookback_days 거래일 중 DB에 누락된 날짜 리스트"""
        today = datetime.now().strftime("%Y%m%d")
        past  = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y%m%d")
        try:
            trading_days = krx.get_previous_business_days(fromdate=past, todate=today)
        except Exception:
            trading_days = []
        stored = self.conn.execute(
            "SELECT DISTINCT date FROM daily_ohlcv WHERE date >= ?", [past]
        ).df()
        stored_set = set(pd.to_datetime(stored["date"]).dt.strftime("%Y%m%d")) if not stored.empty else set()
        return [d.strftime("%Y%m%d") for d in trading_days if d.strftime("%Y%m%d") not in stored_set]

    # ---------- 오래된 데이터 정리 ----------
    def purge_old_data(self, keep_years: int = 3) -> dict:
        """
        keep_years년 이전 데이터 삭제.
        
        DuckDB는 DELETE만으로는 파일 크기가 줄지 않음 → CHECKPOINT로 공간 회수.
        큰 폭 삭제(50% 이상)가 일어난 경우 재작성 권장.
        """
        cutoff = (datetime.now() - timedelta(days=365 * keep_years)).strftime("%Y-%m-%d")
        stats = {}
        for table in ("daily_ohlcv", "fundamentals", "market_cap"):
            before = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            self.conn.execute(f"DELETE FROM {table} WHERE date < ?", [cutoff])
            after = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            stats[table] = {"before": before, "after": after, "deleted": before - after}
        # 체크포인트로 디스크 공간 회수
        self.conn.execute("CHECKPOINT")
        print(f"정리 완료 (기준일 < {cutoff}):")
        for t, s in stats.items():
            print(f"  {t}: {s['before']:,} → {s['after']:,} ({s['deleted']:,}건 삭제)")
        return stats

    def compact_db(self):
        """
        DB 파일을 완전히 재작성하여 용량 회수.
        CHECKPOINT로도 안 줄어들 때 사용 (월 1회 권장).
        
        주의: 실행 중에는 DB에 쓰기 불가 → 다른 스크립트 미실행 시간대에.
        """
        import shutil
        tmp_path = self.db_path + ".compact"
        # 새 파일에 전 테이블 복사
        new_conn = duckdb.connect(tmp_path)
        for table in ("daily_ohlcv", "fundamentals", "market_cap"):
            df = self.conn.execute(f"SELECT * FROM {table}").df()
            new_conn.register("tmp", df)
            # 원본과 동일한 스키마로 재생성
            if table == "daily_ohlcv":
                new_conn.execute("""CREATE TABLE daily_ohlcv (
                    date DATE, code VARCHAR, open DOUBLE, high DOUBLE,
                    low DOUBLE, close DOUBLE, volume BIGINT, value BIGINT,
                    PRIMARY KEY (date, code))""")
            elif table == "fundamentals":
                new_conn.execute("""CREATE TABLE fundamentals (
                    date DATE, code VARCHAR, per DOUBLE, pbr DOUBLE,
                    eps DOUBLE, bps DOUBLE, div_yld DOUBLE, dps DOUBLE,
                    roe_est DOUBLE, PRIMARY KEY (date, code))""")
            elif table == "market_cap":
                new_conn.execute("""CREATE TABLE market_cap (
                    date DATE, code VARCHAR, mcap BIGINT, shares BIGINT,
                    PRIMARY KEY (date, code))""")
            new_conn.execute(f"INSERT INTO {table} SELECT * FROM tmp")
            new_conn.unregister("tmp")
        new_conn.execute("CREATE INDEX idx_ohlcv_code ON daily_ohlcv(code)")
        new_conn.close()
        self.conn.close()
        # 원본 백업 후 교체
        backup = self.db_path + ".bak"
        shutil.move(self.db_path, backup)
        shutil.move(tmp_path, self.db_path)
        print(f"DB 재작성 완료. 기존 파일 백업: {backup}")
        # 재연결
        self.conn = duckdb.connect(self.db_path)

    def close(self):
        self.conn.close()


# ---------- CLI ----------
def cmd_init(days: int = 400):
    """초기 1회 — 과거 N일 벌크 로드 (약 20~30분 소요)"""
    db = PriceDB()
    today = datetime.now().strftime("%Y%m%d")
    past  = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    trading_days = krx.get_previous_business_days(fromdate=past, todate=today)
    print(f"초기 로드: {len(trading_days)}거래일")
    for i, d in enumerate(trading_days, 1):
        ds = d.strftime("%Y%m%d")
        print(f"[{i}/{len(trading_days)}] {ds}")
        db.upsert_ohlcv_for_date(ds)
        db.upsert_fundamentals_for_date(ds)
        db.upsert_market_cap_for_date(ds)
    db.close()


def cmd_daily():
    """매일 전일 데이터만 증분 업데이트 (약 30초)"""
    db = PriceDB()
    missing = db.get_missing_trading_days(lookback_days=10)
    if not missing:
        print("최신 상태입니다.")
        db.close()
        return
    print(f"누락일 업데이트: {missing}")
    for d in missing:
        db.upsert_ohlcv_for_date(d)
        db.upsert_fundamentals_for_date(d)
        db.upsert_market_cap_for_date(d)
    db.close()


def cmd_purge(keep_years: int = 3):
    """3년 이전 데이터 삭제 + CHECKPOINT"""
    db = PriceDB()
    db.purge_old_data(keep_years=keep_years)
    db.close()


def cmd_compact():
    """DB 파일 완전 재작성 (실제 용량 회수)"""
    db = PriceDB()
    db.compact_db()
    db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true", help="과거 400일 초기 로드")
    ap.add_argument("--daily", action="store_true", help="누락일 증분 업데이트")
    ap.add_argument("--purge", action="store_true", help="오래된 데이터 삭제")
    ap.add_argument("--compact", action="store_true", help="DB 재작성 (용량 회수)")
    ap.add_argument("--keep-years", type=int, default=3, help="보관 연수")
    ap.add_argument("--days", type=int, default=400)
    args = ap.parse_args()
    if args.init:
        cmd_init(args.days)
    elif args.daily:
        cmd_daily()
    elif args.purge:
        cmd_purge(args.keep_years)
    elif args.compact:
        cmd_compact()
    else:
        ap.print_help()
