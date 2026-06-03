#!/usr/bin/env python3
"""
클론 스크리너 (price_db 버전) — 3전략 통합

기존 *_screener.py는 종목마다 pykrx를 호출해 8~12분 소요.
이 버전은 price_db(DuckDB)에서 전 종목을 한 번에 메모리로 로드하여
pandas 벡터 연산으로 처리 → 5~10초.

전제: price_db.py로 daily_ohlcv/fundamentals/market_cap이 적재되어 있어야 함.

사용:
  from screener_db import screen_peak_db, screen_momentum_db, screen_value_db
  picks = screen_peak_db(top_n=25)
"""
import os
import numpy as np
import pandas as pd
import duckdb
from datetime import datetime, timedelta

PRICE_DB = "/var/autobot/DB/krx_prices.duckdb"


# ============================================================
# 공통: 전 종목 가격 매트릭스를 한 번에 로드
# ============================================================
def _load_price_panel(conn, days: int = 400) -> pd.DataFrame:
    """
    daily_ohlcv 전체를 한 번의 쿼리로 로드.
    반환: long-format DataFrame [date, code, open, high, low, close, volume, value]
    """
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    df = conn.execute(f"""
        SELECT date, code, open, high, low, close, volume, value
          FROM daily_ohlcv
         WHERE date >= '{cutoff}'
         ORDER BY code, date
    """).df()
    df["date"] = pd.to_datetime(df["date"])
    return df


def _load_universe_meta(conn):
    """최신일 시총·펀더멘털. 종목명은 market_cap에 없으므로 코드만."""
    latest = conn.execute("SELECT MAX(date) FROM daily_ohlcv").fetchone()[0]
    cap = conn.execute("""
        SELECT code, mcap FROM market_cap
         WHERE date = (SELECT MAX(date) FROM market_cap)
    """).df()
    fund = conn.execute("""
        SELECT code, per, pbr, eps, bps, div_yld, roe_est
          FROM fundamentals
         WHERE date = (SELECT MAX(date) FROM fundamentals)
    """).df()
    return latest, cap, fund


def _exclude_codes(code: str) -> bool:
    """우선주(끝자리 5/7) 등 제외"""
    return code[-1] in ("5", "7", "9") and len(code) == 6 and not code.endswith("0")


# ============================================================
# 지표 계산 (벡터)
# ============================================================
def _compute_indicators(panel: pd.DataFrame) -> pd.DataFrame:
    """
    종목별 최신 지표를 한 번에 계산.
    반환: index=code, columns=[price, ma50, ma150, ma200, ma200_1m,
           low_252, high_252, prior_high_excl, last_vol, avg_vol20,
           avg_val20, ret_63, ret_126, ret_60, breakout_recent, ...]
    """
    rows = []
    for code, g in panel.groupby("code", sort=False):
        if len(g) < 60:
            continue
        close = g["close"].values
        high  = g["high"].values
        vol   = g["volume"].values
        val   = g["value"].values
        n = len(close)

        def ma(arr, w):
            return np.mean(arr[-w:]) if len(arr) >= w else np.nan

        price = close[-1]
        ma50  = ma(close, 50)
        ma150 = ma(close, 150)
        ma200 = ma(close, 200)
        ma200_1m = np.mean(close[-222:-22]) if n >= 222 else np.nan
        low_252  = close[-252:].min() if n >= 252 else close.min()
        high_252 = close[-252:].max() if n >= 252 else close.max()

        # 거래량/대금
        last_vol  = vol[-1]
        avg_vol20 = np.mean(vol[-21:-1]) if n >= 21 else np.mean(vol[:-1]) if n > 1 else 0
        avg_val20 = np.mean(val[-20:]) if n >= 20 else np.mean(val)

        # 수익률
        ret_63  = price / close[-64]  - 1 if n >= 64  else np.nan
        ret_126 = price / close[-127] - 1 if n >= 127 else np.nan
        ret_60  = price / close[-61]  - 1 if n >= 61  else np.nan

        # PEAK용: 최근 5일내 52주 신고가 돌파 여부 + 돌파 정보
        breakout = _detect_breakout(close, high, vol, lookback=250,
                                    recent_days=5, vol_mult=1.5)

        rows.append({
            "code": code, "price": price,
            "ma50": ma50, "ma150": ma150, "ma200": ma200, "ma200_1m": ma200_1m,
            "low_252": low_252, "high_252": high_252,
            "last_vol": last_vol, "avg_vol20": avg_vol20, "avg_val20": avg_val20,
            "ret_63": ret_63, "ret_126": ret_126, "ret_60": ret_60,
            "bo_pass": breakout.get("pass", False),
            "bo_date_idx": breakout.get("days_since", None),
            "bo_vol_ratio": breakout.get("vol_ratio", None),
            "bo_run_up": breakout.get("run_up", None),
            "bo_price": breakout.get("breakout_price", None),
            "n_days": n,
        })
    return pd.DataFrame(rows).set_index("code")


def _detect_breakout(close, high, vol, lookback=250, recent_days=5,
                     vol_mult=1.5) -> dict:
    """최근 recent_days 내 52주 신고가 돌파 + 거래량 급증 탐지"""
    n = len(close)
    if n < lookback + recent_days:
        return {"pass": False}
    for i in range(n - recent_days, n):
        if i - lookback < 0:
            continue
        prior_high = close[i - lookback:i].max()
        if close[i] > prior_high * 1.001 and high[i] > prior_high:
            avg_v = vol[i-20:i].mean() if i >= 20 else 0
            vr = vol[i] / avg_v if avg_v > 0 else 0
            if vr >= vol_mult:
                run_up = close[-1] / close[i] - 1
                return {
                    "pass": True,
                    "days_since": n - 1 - i,
                    "vol_ratio": round(float(vr), 2),
                    "run_up": round(float(run_up), 4),
                    "breakout_price": int(close[i]),
                }
    return {"pass": False}


# ============================================================
# MOMENTUM
# ============================================================
def screen_momentum_db(top_n: int = 30, db_path: str = PRICE_DB,
                       min_mcap: float = 50e9, min_val20: float = 1e9) -> list:
    conn = duckdb.connect(db_path, read_only=True)
    try:
        panel = _load_price_panel(conn, days=400)
        _, cap, fund = _load_universe_meta(conn)
        ind = _compute_indicators(panel)
    finally:
        conn.close()

    df = ind.join(cap.set_index("code"), how="left")
    df = df[~df.index.map(_exclude_codes)]
    df = df[(df["mcap"] >= min_mcap) & (df["avg_val20"] >= min_val20)]
    df = df[df["n_days"] >= 220]

    # MTT 7조건
    c1 = (df["price"] > df["ma150"]) & (df["price"] > df["ma200"])
    c2 = df["ma150"] > df["ma200"]
    c3 = df["ma200"] > df["ma200_1m"]
    c4 = (df["ma50"] > df["ma150"]) & (df["ma50"] > df["ma200"])
    c5 = df["price"] > df["ma50"]
    c6 = df["price"] >= df["low_252"] * 1.30
    c7 = df["price"] >= df["high_252"] * 0.75
    df["mtt_score"] = (c1.astype(int) + c2 + c3 + c4 + c5 + c6 + c7)
    df = df[df["mtt_score"] >= 6]

    # 상승 초입: 52주 고점의 75~98%
    ratio = df["price"] / df["high_252"]
    df = df[(ratio >= 0.75) & (ratio <= 0.98)]

    # RS (KOSPI 대비)
    conn = duckdb.connect(db_path, read_only=True)
    try:
        bench = conn.execute("""
            SELECT date, close FROM daily_ohlcv WHERE code = '__KOSPI__'
        """).df()
    except Exception:
        bench = pd.DataFrame()
    finally:
        conn.close()
    # 벤치 없으면 종목 절대 모멘텀으로 RS 대체
    df["rs_63"]  = df["ret_63"]  * 100
    df["rs_126"] = df["ret_126"] * 100
    df["rs_combined"] = df[["rs_63", "rs_126"]].mean(axis=1)
    df["rs_pct"] = df["rs_combined"].rank(pct=True) * 100
    df = df[df["rs_pct"] >= 70]

    df["final_score"] = df["mtt_score"] * 10 + df["rs_pct"]
    df = df.sort_values("final_score", ascending=False).head(top_n)

    return [{
        "code": code,
        "score": round(r["final_score"], 2),
        "mtt_score": int(r["mtt_score"]),
        "rs_63": round(r["rs_63"], 2) if pd.notna(r["rs_63"]) else None,
        "price": int(r["price"]),
        "dist_to_high_pct": round((r["price"]/r["high_252"] - 1)*100, 2),
    } for code, r in df.iterrows()]


# ============================================================
# PEAK
# ============================================================
def screen_peak_db(top_n: int = 25, db_path: str = PRICE_DB,
                   min_mcap: float = 100e9, min_val20: float = 3e9,
                   vol_mult: float = 1.5, run_up_max: float = 0.15,
                   recent_days: int = 5) -> list:
    """
    vol_mult, run_up_max, recent_days는 튜닝 파라미터 (param_tuning.py에서 주입)
    """
    conn = duckdb.connect(db_path, read_only=True)
    try:
        panel = _load_price_panel(conn, days=400)
        _, cap, _ = _load_universe_meta(conn)
    finally:
        conn.close()

    # 파라미터를 반영한 지표 재계산
    rows = []
    for code, g in panel.groupby("code", sort=False):
        if len(g) < 255:
            continue
        close = g["close"].values
        high  = g["high"].values
        vol   = g["volume"].values
        val   = g["value"].values
        bo = _detect_breakout(close, high, vol, lookback=250,
                              recent_days=recent_days, vol_mult=vol_mult)
        if not bo.get("pass"):
            continue
        if bo["run_up"] > run_up_max:
            continue
        ma50  = np.mean(close[-50:])
        ma150 = np.mean(close[-150:]) if len(close) >= 150 else np.nan
        if not (pd.notna(ma150) and ma50 > ma150):
            continue
        avg_val20 = np.mean(val[-20:])
        rows.append({
            "code": code, "price": int(close[-1]),
            "vol_ratio": bo["vol_ratio"], "run_up": bo["run_up"],
            "days_since": bo["days_since"], "avg_val20": avg_val20,
            "breakout_price": bo["breakout_price"],
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return []
    df = df.set_index("code").join(cap.set_index("code"), how="left")
    df = df[~df.index.map(_exclude_codes)]
    df = df[(df["mcap"] >= min_mcap) & (df["avg_val20"] >= min_val20)]
    if df.empty:
        return []

    # 스코어: 거래량비율↑ + 돌파초기↑ + 과열↓
    df["score"] = (df["vol_ratio"] * 10
                   + (5 - df["days_since"]).clip(lower=0) * 5
                   - df["run_up"] * 100)
    df = df.sort_values("score", ascending=False).head(top_n)

    return [{
        "code": code, "score": round(r["score"], 2),
        "vol_ratio": r["vol_ratio"], "run_up_pct": round(r["run_up"]*100, 2),
        "days_since_breakout": int(r["days_since"]), "price": int(r["price"]),
    } for code, r in df.iterrows()]


# ============================================================
# VALUE
# ============================================================
def screen_value_db(top_n: int = 15, db_path: str = PRICE_DB,
                    min_mcap: float = 200e9, min_roe: float = 5.0) -> list:
    conn = duckdb.connect(db_path, read_only=True)
    try:
        panel = _load_price_panel(conn, days=120)
        _, cap, fund = _load_universe_meta(conn)
    finally:
        conn.close()

    # 3개월 수익률
    ret3 = {}
    for code, g in panel.groupby("code", sort=False):
        c = g["close"].values
        if len(c) >= 60:
            ret3[code] = c[-1] / c[-60] - 1
    ret3_s = pd.Series(ret3, name="ret_3m")

    df = fund.set_index("code").join(cap.set_index("code"), how="inner")
    df = df.join(ret3_s, how="left")
    df = df[~df.index.map(_exclude_codes)]

    df = df[
        (df["per"] > 0) & (df["per"] < 50) &
        (df["pbr"] > 0.2) & (df["pbr"] < 5) &
        (df["mcap"] >= min_mcap) &
        (df["roe_est"] >= min_roe)
    ]
    # 가치함정 회피: 3개월 -20% 이하 제외
    df = df[(df["ret_3m"].isna()) | (df["ret_3m"] >= -0.20)]
    if df.empty:
        return []

    df["per_pct"] = df["per"].rank(pct=True) * 100
    df["pbr_pct"] = df["pbr"].rank(pct=True) * 100
    df["roe_pct"] = df["roe_est"].rank(pct=True) * 100
    df["div_pct"] = df["div_yld"].fillna(0).rank(pct=True) * 100
    df["value_score"] = ((100 - df["per_pct"]) * 0.30
                         + (100 - df["pbr_pct"]) * 0.30
                         + df["roe_pct"] * 0.30
                         + df["div_pct"] * 0.10)
    df = df.sort_values("value_score", ascending=False).head(top_n)

    return [{
        "code": code, "score": round(r["value_score"], 2),
        "PER": round(r["per"], 2), "PBR": round(r["pbr"], 2),
        "ROE_est": round(r["roe_est"], 2),
        "DIV_pct": round(r["div_yld"], 2) if pd.notna(r["div_yld"]) else 0,
        "ret_3m_pct": round(r["ret_3m"]*100, 2) if pd.notna(r["ret_3m"]) else None,
    } for code, r in df.iterrows()]


if __name__ == "__main__":
    import time
    for name, fn in [("PEAK", screen_peak_db),
                     ("MOMENTUM", screen_momentum_db),
                     ("VALUE", screen_value_db)]:
        t0 = time.time()
        picks = fn()
        print(f"[{name}] {len(picks)}종목, {time.time()-t0:.1f}초")
        for p in picks[:5]:
            print(f"  {p['code']} score={p['score']}")
