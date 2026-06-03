#!/usr/bin/env python3
"""
PEAK 전략 파라미터 자동 튜닝 (grid search)

목적:
  한 달치 이상 누적된 stockeasy_picks(실제 사이트 종목)를 정답(ground truth)으로,
  vol_mult / run_up_max / recent_days 조합을 grid search 하여
  과거 각 날짜에서 클론 결과가 사이트와 가장 일치하는(F1 최대) 파라미터를 탐색.

원리:
  - 과거 날짜 D에 대해, price_db에는 D까지의 가격이 있으므로
    "그날 기준" 스크리닝을 재현할 수 있음 (look-ahead 없음).
  - 각 파라미터 조합으로 D의 클론 픽을 만들고, 같은 날 stockeasy_picks와 비교.
  - 모든 평가일에 대해 F1 평균이 가장 높은 조합 선택.

산출:
  /var/autobot/TR_KRTR/peak_best_params.json
  → screener_db.screen_peak_db 호출 시 이 값을 로드해 사용

실행:
  python3 param_tuning.py --strategy PEAK --eval-days 30
"""
import os
import sys
import json
import argparse
import itertools
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import duckdb

PRICE_DB      = "/var/autobot/DB/krx_prices.duckdb"
COMPARISON_DB = "/var/autobot/DB/comparison.duckdb"
BEST_PARAM_PATH = "/var/autobot/TR_KRTR/peak_best_params.json"

# 탐색 그리드
PEAK_GRID = {
    "vol_mult":    [1.2, 1.5, 1.8, 2.0, 2.5],
    "run_up_max":  [0.10, 0.15, 0.20, 0.25],
    "recent_days": [3, 5, 7, 10],
}


def _detect_breakout(close, high, vol, lookback, recent_days, vol_mult):
    n = len(close)
    if n < lookback + recent_days:
        return None
    for i in range(n - recent_days, n):
        if i - lookback < 0:
            continue
        prior_high = close[i - lookback:i].max()
        if close[i] > prior_high * 1.001 and high[i] > prior_high:
            avg_v = vol[i-20:i].mean() if i >= 20 else 0
            vr = vol[i] / avg_v if avg_v > 0 else 0
            if vr >= vol_mult:
                return {"vol_ratio": vr, "run_up": close[-1]/close[i]-1,
                        "days_since": n-1-i}
    return None


def screen_peak_asof(panel_by_code, cap_map, as_of_date,
                     vol_mult, run_up_max, recent_days,
                     min_mcap=100e9, min_val20=3e9, top_n=25):
    """as_of_date 시점 기준 PEAK 스크리닝 재현 (look-ahead 없음)"""
    picks = []
    for code, g in panel_by_code.items():
        sub = g[g["date"] <= as_of_date]
        if len(sub) < 255:
            continue
        close = sub["close"].values
        high  = sub["high"].values
        vol   = sub["volume"].values
        val   = sub["value"].values
        bo = _detect_breakout(close, high, vol, 250, recent_days, vol_mult)
        if bo is None or bo["run_up"] > run_up_max:
            continue
        ma50  = np.mean(close[-50:])
        ma150 = np.mean(close[-150:]) if len(close) >= 150 else np.nan
        if not (pd.notna(ma150) and ma50 > ma150):
            continue
        if cap_map.get(code, 0) < min_mcap:
            continue
        if np.mean(val[-20:]) < min_val20:
            continue
        score = bo["vol_ratio"]*10 + max(0, 5-bo["days_since"])*5 - bo["run_up"]*100
        picks.append((code, score))
    picks.sort(key=lambda x: -x[1])
    return [c for c, _ in picks[:top_n]]


def f1_score(pred_set, true_set):
    if not pred_set and not true_set:
        return 1.0
    if not pred_set or not true_set:
        return 0.0
    inter = len(pred_set & true_set)
    prec = inter / len(pred_set)
    rec  = inter / len(true_set)
    if prec + rec == 0:
        return 0.0
    return 2 * prec * rec / (prec + rec)


def tune_peak(eval_days: int = 30):
    # 1. 평가 대상 날짜: stockeasy_picks가 있는 PEAK 날짜들
    cdb = duckdb.connect(COMPARISON_DB, read_only=True)
    cutoff = (datetime.now() - timedelta(days=eval_days*2)).strftime("%Y-%m-%d")
    truth = cdb.execute(f"""
        SELECT date, code FROM stockeasy_picks
         WHERE strategy = 'PEAK' AND date >= '{cutoff}'
    """).df()
    cdb.close()
    if truth.empty:
        print("평가용 stockeasy_picks(PEAK) 데이터 없음")
        return None

    truth["date"] = pd.to_datetime(truth["date"])
    eval_dates = sorted(truth["date"].unique())[-eval_days:]
    truth_map = {d: set(truth[truth["date"] == d]["code"]) for d in eval_dates}
    print(f"평가일 {len(eval_dates)}일, 총 정답종목 {len(truth)}건")

    # 2. 가격 패널을 한 번만 로드 (전 평가일 공통)
    pdb = duckdb.connect(PRICE_DB, read_only=True)
    max_date = max(eval_dates)
    min_date = (pd.to_datetime(min(eval_dates)) - timedelta(days=420)).strftime("%Y-%m-%d")
    panel = pdb.execute(f"""
        SELECT date, code, high, close, volume, value
          FROM daily_ohlcv
         WHERE date >= '{min_date}' AND date <= '{max_date.strftime("%Y-%m-%d") if hasattr(max_date,"strftime") else max_date}'
         ORDER BY code, date
    """).df()
    panel["date"] = pd.to_datetime(panel["date"])
    cap = pdb.execute("""
        SELECT code, mcap FROM market_cap
         WHERE date = (SELECT MAX(date) FROM market_cap)
    """).df()
    pdb.close()
    cap_map = dict(zip(cap["code"], cap["mcap"]))
    panel_by_code = {code: g for code, g in panel.groupby("code", sort=False)}
    print(f"가격 패널 로드 완료: {len(panel_by_code)}종목")

    # 3. 그리드 탐색
    best = {"f1": -1, "params": None}
    combos = list(itertools.product(*PEAK_GRID.values()))
    print(f"그리드 조합 {len(combos)}개 평가 중...")

    for vol_mult, run_up_max, recent_days in combos:
        f1s = []
        for d in eval_dates:
            pred = set(screen_peak_asof(
                panel_by_code, cap_map, d,
                vol_mult, run_up_max, recent_days))
            f1s.append(f1_score(pred, truth_map[d]))
        avg_f1 = float(np.mean(f1s))
        if avg_f1 > best["f1"]:
            best = {"f1": avg_f1,
                    "params": {"vol_mult": vol_mult,
                               "run_up_max": run_up_max,
                               "recent_days": recent_days}}

    print(f"\n최적 파라미터: {best['params']}  (평균 F1={best['f1']:.3f})")

    # 4. 저장
    out = {
        "strategy": "PEAK",
        "tuned_at": datetime.now().isoformat(),
        "eval_days": eval_days,
        "best_f1": round(best["f1"], 4),
        "params": best["params"],
        "grid": PEAK_GRID,
    }
    os.makedirs(os.path.dirname(BEST_PARAM_PATH), exist_ok=True)
    with open(BEST_PARAM_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"저장: {BEST_PARAM_PATH}")
    return out


def load_best_params() -> dict:
    """screener_db에서 호출: 튜닝된 파라미터 로드 (없으면 기본값)"""
    default = {"vol_mult": 1.5, "run_up_max": 0.15, "recent_days": 5}
    if os.path.exists(BEST_PARAM_PATH):
        try:
            with open(BEST_PARAM_PATH, encoding="utf-8") as f:
                return json.load(f).get("params", default)
        except Exception:
            return default
    return default


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", default="PEAK")
    ap.add_argument("--eval-days", type=int, default=30)
    args = ap.parse_args()
    if args.strategy == "PEAK":
        tune_peak(args.eval_days)
    else:
        print(f"아직 {args.strategy} 튜닝 미지원 (PEAK만 구현)")
