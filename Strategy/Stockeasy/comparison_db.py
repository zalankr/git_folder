#!/usr/bin/env python3
"""
StockEasy vs Clone Screener 비교 분석 모듈

DB 테이블:
  - stockeasy_picks    : 실제 StockEasy 사이트에서 크롤링한 종목
  - clone_picks        : 자체 클론 스크리너 결과
  - comparison_daily   : 일별 일치도 지표 (Jaccard, Precision, Recall)
  - performance_daily  : 종목별 1일/5일/20일 수익률 추적

사용:
  from comparison_db import ComparisonDB
  db = ComparisonDB()
  db.save_stockeasy_picks('2025-06-03', 'PEAK', ['005930', '000660', ...])
  db.save_clone_picks('2025-06-03', 'PEAK', [{'code':'005930','score':95.2}, ...])
  db.compute_daily_comparison('2025-06-03', 'PEAK')
  db.update_performance(lookback_days=30)
"""
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import duckdb
import pandas as pd

DB_PATH = "/var/autobot/DB/comparison.duckdb"


class ComparisonDB:
    def __init__(self, db_path: str = DB_PATH,
                 price_db_path: str = "/var/autobot/DB/krx_prices.duckdb"):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.price_db_path = price_db_path
        self.conn = duckdb.connect(db_path)
        # price_db를 ATTACH해서 cross-DB JOIN 가능 (DuckDB 강점)
        if os.path.exists(price_db_path):
            self.conn.execute(f"ATTACH '{price_db_path}' AS pdb (READ_ONLY)")
        self._ensure_schema()

    def _ensure_schema(self):
        # 1. 실제 StockEasy 크롤링 결과
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS stockeasy_picks (
                date     DATE    NOT NULL,
                strategy VARCHAR NOT NULL,   -- 'PEAK', 'MOMENTUM', 'VALUE'
                code     VARCHAR NOT NULL,
                name     VARCHAR,
                rank_in_list INTEGER,        -- 사이트에서의 표시 순서
                meta     VARCHAR,            -- JSON 문자열 (RS, MTT 등 부가 정보)
                PRIMARY KEY (date, strategy, code)
            )
        """)
        # 2. 클론 스크리너 결과
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS clone_picks (
                date     DATE    NOT NULL,
                strategy VARCHAR NOT NULL,
                code     VARCHAR NOT NULL,
                name     VARCHAR,
                rank_in_list INTEGER,
                score    DOUBLE,
                meta     VARCHAR,
                PRIMARY KEY (date, strategy, code)
            )
        """)
        # 3. 일별 일치도 지표
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS comparison_daily (
                date          DATE    NOT NULL,
                strategy      VARCHAR NOT NULL,
                stockeasy_n   INTEGER,   -- 사이트 종목 수
                clone_n       INTEGER,   -- 클론 종목 수
                intersect_n   INTEGER,   -- 교집합 종목 수
                jaccard       DOUBLE,    -- |A∩B| / |A∪B|
                precision_val DOUBLE,    -- |A∩B| / |Clone|  (클론이 얼마나 정확한가)
                recall_val    DOUBLE,    -- |A∩B| / |StockEasy| (클론이 얼마나 빠뜨리지 않는가)
                stockeasy_only VARCHAR,  -- 사이트에만 있는 종목 (콤마 구분)
                clone_only     VARCHAR,  -- 클론에만 있는 종목
                intersect_codes VARCHAR,
                PRIMARY KEY (date, strategy)
            )
        """)
        # 4. 종목별 사후 성과 (다음날, 5일, 20일 수익률)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS performance_daily (
                pick_date     DATE    NOT NULL,
                strategy      VARCHAR NOT NULL,
                source        VARCHAR NOT NULL,  -- 'stockeasy' or 'clone' or 'both'
                code          VARCHAR NOT NULL,
                entry_price   DOUBLE,            -- pick_date 종가
                ret_1d        DOUBLE,            -- 다음 거래일 수익률
                ret_5d        DOUBLE,            -- 5거래일 후
                ret_20d       DOUBLE,            -- 20거래일 후
                max_ret_20d   DOUBLE,            -- 20일 내 최고점 수익률
                mdd_20d       DOUBLE,            -- 20일 내 최대 낙폭
                PRIMARY KEY (pick_date, strategy, source, code)
            )
        """)

    # ---------- 저장 ----------
    def save_stockeasy_picks(self, date: str, strategy: str, picks: List[Dict]):
        """
        picks: [{'code': '005930', 'name': '삼성전자', 'rank': 1, 'meta': '{}'}]
        """
        d = pd.to_datetime(date).date()
        self.conn.execute(
            "DELETE FROM stockeasy_picks WHERE date = ? AND strategy = ?",
            [d, strategy])
        if not picks:
            return
        df = pd.DataFrame(picks)
        df["date"] = d
        df["strategy"] = strategy
        df = df.rename(columns={"rank": "rank_in_list"})
        for col in ("name", "rank_in_list", "meta"):
            if col not in df.columns:
                df[col] = None
        df = df[["date", "strategy", "code", "name", "rank_in_list", "meta"]]
        self.conn.register("tmp", df)
        self.conn.execute("INSERT INTO stockeasy_picks SELECT * FROM tmp")
        self.conn.unregister("tmp")

    def save_clone_picks(self, date: str, strategy: str, picks: List[Dict]):
        """picks: [{'code', 'name', 'rank', 'score', 'meta'}]"""
        d = pd.to_datetime(date).date()
        self.conn.execute(
            "DELETE FROM clone_picks WHERE date = ? AND strategy = ?",
            [d, strategy])
        if not picks:
            return
        df = pd.DataFrame(picks)
        df["date"] = d
        df["strategy"] = strategy
        df = df.rename(columns={"rank": "rank_in_list"})
        for col in ("name", "rank_in_list", "score", "meta"):
            if col not in df.columns:
                df[col] = None
        df = df[["date", "strategy", "code", "name", "rank_in_list", "score", "meta"]]
        self.conn.register("tmp", df)
        self.conn.execute("INSERT INTO clone_picks SELECT * FROM tmp")
        self.conn.unregister("tmp")

    # ---------- 일치도 분석 ----------
    def compute_daily_comparison(self, date: str, strategy: str) -> Optional[Dict]:
        d = pd.to_datetime(date).date()
        se = self.conn.execute(
            "SELECT code FROM stockeasy_picks WHERE date = ? AND strategy = ?",
            [d, strategy]).df()["code"].tolist()
        cl = self.conn.execute(
            "SELECT code FROM clone_picks WHERE date = ? AND strategy = ?",
            [d, strategy]).df()["code"].tolist()

        if not se and not cl:
            return None

        set_se, set_cl = set(se), set(cl)
        inter = set_se & set_cl
        union = set_se | set_cl
        se_only = set_se - set_cl
        cl_only = set_cl - set_se

        jaccard   = len(inter) / len(union) if union else 0.0
        precision = len(inter) / len(set_cl) if set_cl else 0.0
        recall    = len(inter) / len(set_se) if set_se else 0.0

        self.conn.execute(
            "DELETE FROM comparison_daily WHERE date = ? AND strategy = ?",
            [d, strategy])
        self.conn.execute("""
            INSERT INTO comparison_daily VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, [d, strategy, len(set_se), len(set_cl), len(inter),
              jaccard, precision, recall,
              ",".join(sorted(se_only)),
              ",".join(sorted(cl_only)),
              ",".join(sorted(inter))])

        return {
            "date": d, "strategy": strategy,
            "stockeasy_n": len(set_se), "clone_n": len(set_cl),
            "intersect_n": len(inter),
            "jaccard": round(jaccard, 3),
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "stockeasy_only": sorted(se_only),
            "clone_only": sorted(cl_only),
        }

    # ---------- 사후 성과 추적 ----------
    def update_performance(self, lookback_days: int = 40):
        """
        최근 lookback_days 내 pick들의 1d/5d/20d 수익률 업데이트.
        price_db.daily_ohlcv를 JOIN하여 계산.
        매일 돌리면 됨 (idempotent).
        """
        cutoff = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        # 통합 pick 뷰 생성 (stockeasy/clone/both)
        # 각 pick_date에 대해 entry_price와 +1d/+5d/+20d 종가 JOIN
        sql = f"""
            WITH all_picks AS (
                SELECT date AS pick_date, strategy, code, 'stockeasy' AS source
                  FROM stockeasy_picks WHERE date >= '{cutoff}'
                UNION ALL
                SELECT date AS pick_date, strategy, code, 'clone' AS source
                  FROM clone_picks WHERE date >= '{cutoff}'
            ),
            entry AS (
                SELECT p.pick_date, p.strategy, p.code, p.source,
                       o.close AS entry_price
                  FROM all_picks p
                  JOIN pdb.daily_ohlcv o
                    ON o.code = p.code AND o.date = p.pick_date
            ),
            future_returns AS (
                SELECT e.pick_date, e.strategy, e.code, e.source, e.entry_price,
                    -- +1d
                    (SELECT close FROM pdb.daily_ohlcv
                      WHERE code = e.code AND date > e.pick_date
                      ORDER BY date LIMIT 1) AS p1,
                    -- +5d (정확히 5번째 거래일)
                    (SELECT close FROM pdb.daily_ohlcv
                      WHERE code = e.code AND date > e.pick_date
                      ORDER BY date LIMIT 1 OFFSET 4) AS p5,
                    -- +20d
                    (SELECT close FROM pdb.daily_ohlcv
                      WHERE code = e.code AND date > e.pick_date
                      ORDER BY date LIMIT 1 OFFSET 19) AS p20,
                    -- 20일 내 max close, min close
                    (SELECT MAX(close) FROM pdb.daily_ohlcv
                      WHERE code = e.code
                        AND date > e.pick_date
                        AND date <= e.pick_date + INTERVAL '30 days') AS max20,
                    (SELECT MIN(close) FROM pdb.daily_ohlcv
                      WHERE code = e.code
                        AND date > e.pick_date
                        AND date <= e.pick_date + INTERVAL '30 days') AS min20
                  FROM entry e
            )
            SELECT pick_date, strategy, source, code, entry_price,
                CASE WHEN p1  IS NOT NULL THEN (p1  / entry_price - 1) END AS ret_1d,
                CASE WHEN p5  IS NOT NULL THEN (p5  / entry_price - 1) END AS ret_5d,
                CASE WHEN p20 IS NOT NULL THEN (p20 / entry_price - 1) END AS ret_20d,
                CASE WHEN max20 IS NOT NULL THEN (max20 / entry_price - 1) END AS max_ret_20d,
                CASE WHEN min20 IS NOT NULL THEN (min20 / entry_price - 1) END AS mdd_20d
              FROM future_returns
        """
        df = self.conn.execute(sql).df()
        if df.empty:
            return 0
        # 중복(stockeasy+clone 동일 종목) 처리: source가 다르면 별개 행
        self.conn.execute(
            f"DELETE FROM performance_daily WHERE pick_date >= '{cutoff}'")
        self.conn.register("perf", df)
        self.conn.execute("INSERT INTO performance_daily SELECT * FROM perf")
        self.conn.unregister("perf")
        return len(df)

    # ---------- 리포트용 쿼리 ----------
    def get_jaccard_history(self, strategy: str, days: int = 90) -> pd.DataFrame:
        """전략별 Jaccard 추이"""
        return self.conn.execute(f"""
            SELECT date, jaccard, precision_val, recall_val,
                   stockeasy_n, clone_n, intersect_n
              FROM comparison_daily
             WHERE strategy = ?
               AND date >= CURRENT_DATE - {days}
             ORDER BY date
        """, [strategy]).df()

    def get_performance_summary(self, days: int = 60) -> pd.DataFrame:
        """source별 평균 수익률 비교"""
        return self.conn.execute(f"""
            SELECT strategy, source,
                   COUNT(*) AS picks,
                   AVG(ret_1d)  * 100 AS avg_1d_pct,
                   AVG(ret_5d)  * 100 AS avg_5d_pct,
                   AVG(ret_20d) * 100 AS avg_20d_pct,
                   AVG(max_ret_20d) * 100 AS avg_max20_pct,
                   AVG(mdd_20d)     * 100 AS avg_mdd20_pct,
                   SUM(CASE WHEN ret_20d > 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS win_rate_20d
              FROM performance_daily
             WHERE pick_date >= CURRENT_DATE - {days}
               AND ret_20d IS NOT NULL
             GROUP BY strategy, source
             ORDER BY strategy, source
        """).df()

    def get_frequent_mismatches(self, strategy: str, days: int = 30, top_n: int = 20) -> Dict:
        """
        클론만 픽한 종목 vs 사이트만 픽한 종목의 빈도 TOP-N.
        파라미터 튜닝 단서가 됨.
        """
        rows = self.conn.execute(f"""
            SELECT stockeasy_only, clone_only
              FROM comparison_daily
             WHERE strategy = ? AND date >= CURRENT_DATE - {days}
        """, [strategy]).fetchall()

        se_only_counter, cl_only_counter = {}, {}
        for se_str, cl_str in rows:
            for c in (se_str or "").split(","):
                if c: se_only_counter[c] = se_only_counter.get(c, 0) + 1
            for c in (cl_str or "").split(","):
                if c: cl_only_counter[c] = cl_only_counter.get(c, 0) + 1

        return {
            "stockeasy_only_top": sorted(se_only_counter.items(), key=lambda x: -x[1])[:top_n],
            "clone_only_top":     sorted(cl_only_counter.items(), key=lambda x: -x[1])[:top_n],
        }

    def close(self):
        self.conn.close()


if __name__ == "__main__":
    db = ComparisonDB()
    print("ComparisonDB 스키마 생성 완료")
    print(f"  DB: {db.db_path}")
    db.close()
