#!/usr/bin/env python3
"""
StockEasy vs Clone 일일 비교 실행기 (cron 진입점)

매일 KST 08:50 (UTC 23:50) 실행:
  1. 실제 StockEasy 크롤링 (기존 PEAK_TR.py / MOMENTUM_TR.py / VALUE_TR.py에서 import)
  2. 클론 스크리너 실행
  3. 비교 분석 + DB 저장
  4. Telegram 요약 전송

매일 KST 17:00 (UTC 08:00) 실행:
  5. 사후 성과 업데이트 (1d/5d/20d 수익률)

실행:
  python3 daily_comparison.py morning   # 종목 비교
  python3 daily_comparison.py evening   # 성과 업데이트
"""
import sys
import json
import time
import traceback
from datetime import datetime
from typing import List, Dict

# 자동매매 디렉토리 (sys.path에 추가하여 기존 모듈 재활용)
sys.path.insert(0, "/var/autobot/TR_PEAK")
sys.path.insert(0, "/var/autobot/TR_MOMENTUM")
sys.path.insert(0, "/var/autobot/TR_VALUE")
sys.path.insert(0, "/var/autobot/TR_KRTR")  # 클론 스크리너 위치
sys.path.insert(0, "/var/autobot")          # telegram_alert.py

try:
    import telegram_alert as TA
except ImportError:
    class _DummyTA:
        @staticmethod
        def send_tele(msg): print(f"[TELE] {msg}")
    TA = _DummyTA()

from comparison_db import ComparisonDB

STRATEGIES = ["PEAK", "MOMENTUM", "VALUE"]


# ---------- StockEasy 크롤러 어댑터 ----------
def crawl_stockeasy(strategy: str) -> List[Dict]:
    """
    StockEasy 사이트를 직접 크롤링 (TR.py import 부작용 회피).
    holdings(현재 사이트 보유 전체)를 비교 대상으로 사용.
    반환: [{'code', 'name', 'rank', 'meta'}]
    """
    try:
        raw = _crawl_standalone(strategy)
        holdings = raw.get("holdings", [])
        picks = []
        for i, h in enumerate(holdings, 1):
            picks.append({
                "code": h.get("stock_code", ""),
                "name": h.get("stock_name", ""),
                "rank": i,
                "meta": json.dumps({
                    "sector": h.get("sector", ""),
                    "holding_days": h.get("holding_days", 0),
                    "return_rate": h.get("return_rate", 0),
                }, ensure_ascii=False)
            })
        return [p for p in picks if p["code"]]
    except Exception as e:
        TA.send_tele(f"[비교] {strategy} 크롤링 오류: {e}")
        traceback.print_exc()
        return []


import re
import requests

_CRAWL_URLS = {
    "PEAK":     "https://stockeasy.intellio.kr/strategy-room/peak",
    "MOMENTUM": "https://stockeasy.intellio.kr/strategy-room/momentum",
    "VALUE":    "https://stockeasy.intellio.kr/strategy-room/value",
}
_CRAWL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Referer": "https://stockeasy.intellio.kr/strategy-room",
}


def _extract_initial_data(html: str) -> dict:
    """Next.js __next_f.push 안의 initialData JSON 추출 (TR.py와 동일 로직)"""
    scripts = re.findall(r'self\.__next_f\.push\(\[1,"(.+?)"\]\)', html, re.DOTALL)
    for s in scripts:
        if 'initialData' not in s:
            continue
        try:
            decoded = json.loads('"' + s + '"')
        except Exception:
            continue
        marker = '"initialData":'
        idx = decoded.find(marker)
        if idx == -1:
            continue
        start = idx + len(marker)
        depth, end_pos = 0, start
        for j in range(start, len(decoded)):
            if decoded[j] == '{':
                depth += 1
            elif decoded[j] == '}':
                depth -= 1
                if depth == 0:
                    end_pos = j + 1
                    break
        try:
            return json.loads(decoded[start:end_pos])
        except json.JSONDecodeError:
            continue
    return {}


def _crawl_standalone(strategy: str) -> dict:
    url = _CRAWL_URLS[strategy]
    last_err = None
    for attempt in range(2):  # 최초 1회 + 재시도 1회
        try:
            resp = requests.get(url, headers=_CRAWL_HEADERS, timeout=15)
            resp.raise_for_status()
            raw = _extract_initial_data(resp.text)
            if not raw or not raw.get("success"):
                raise ValueError(f"{strategy} StockEasy 데이터 추출 실패")
            meta = raw.get("metadata", {})
            holdings = []
            for sector, stocks in raw.get("holdings", {}).items():
                for s in stocks:
                    holdings.append({
                        "stock_code": s.get("stock_code", ""),
                        "stock_name": s.get("stock_name", ""),
                        "sector": sector,
                        "holding_days": s.get("holding_days", 0),
                        "return_rate": s.get("return_rate", 0),
                    })
            return {"target_date": meta.get("target_date", ""), "holdings": holdings}
        except Exception as e:
            last_err = e
            if attempt == 0:
                time.sleep(5)  # 일시적 오류 시 5초 후 재시도
    raise last_err


# ---------- 클론 스크리너 어댑터 ----------
def run_clone_screener(strategy: str) -> List[Dict]:
    """price_db 기반 고속 스크리너 (5~10초). PEAK은 튜닝된 파라미터 적용."""
    try:
        from screener_db import screen_peak_db, screen_momentum_db, screen_value_db
        if strategy == "PEAK":
            from param_tuning import load_best_params
            p = load_best_params()
            raw = screen_peak_db(top_n=25, **p)
        elif strategy == "MOMENTUM":
            raw = screen_momentum_db(top_n=30)
        elif strategy == "VALUE":
            raw = screen_value_db(top_n=15)
        else:
            return []

        picks = []
        for i, p_ in enumerate(raw, 1):
            picks.append({
                "code": p_["code"],
                "name": p_.get("name", ""),
                "rank": i,
                "score": p_.get("score"),
                "meta": json.dumps({k: v for k, v in p_.items()
                                    if k not in ("code", "name", "score")},
                                   ensure_ascii=False, default=str)
            })
        return picks
    except Exception as e:
        TA.send_tele(f"[비교] {strategy} 클론 스크리닝 오류: {e}")
        traceback.print_exc()
        return []


# ---------- 메인 ----------
def run_morning():
    today = datetime.now().strftime("%Y-%m-%d")
    db = ComparisonDB()
    summary_lines = [f"📊 <b>StockEasy 비교</b> {today}\n"]

    for idx, strategy in enumerate(STRATEGIES):
        try:
            print(f"\n=== {strategy} ===")

            # 1. 실제 사이트 크롤링
            se_picks = crawl_stockeasy(strategy)
            print(f"  StockEasy: {len(se_picks)}종목")
            db.save_stockeasy_picks(today, strategy, se_picks)

            # 2. 클론 스크리너
            cl_picks = run_clone_screener(strategy)
            print(f"  Clone    : {len(cl_picks)}종목")
            db.save_clone_picks(today, strategy, cl_picks)

            # 3. 일치도 계산
            cmp_ = db.compute_daily_comparison(today, strategy)
            if cmp_ is None:
                summary_lines.append(f"  {strategy}: 데이터 없음")
                continue

            line = (f"<b>{strategy}</b> "
                    f"SE={cmp_['stockeasy_n']} "
                    f"CL={cmp_['clone_n']} "
                    f"∩={cmp_['intersect_n']} "
                    f"Jac={cmp_['jaccard']:.2f} "
                    f"P={cmp_['precision']:.2f} "
                    f"R={cmp_['recall']:.2f}")
            summary_lines.append(line)

            # 최근 7일 평균 추이
            hist = db.get_jaccard_history(strategy, days=7)
            if len(hist) >= 3:
                avg_jac = hist["jaccard"].mean()
                summary_lines.append(f"  └ 7일 평균 Jaccard: {avg_jac:.2f}")

        except Exception as e:
            TA.send_tele(f"[비교] {strategy} 처리 오류: {e}")
            traceback.print_exc()

        # 전략 간 3초 대기 (StockEasy IP 차단 방지). 마지막 전략 뒤에는 생략.
        if idx < len(STRATEGIES) - 1:
            time.sleep(3)

    db.close()
    TA.send_tele("\n".join(summary_lines))


def run_evening():
    db = ComparisonDB()
    try:
        n = db.update_performance(lookback_days=40)
        print(f"성과 업데이트: {n}건")

        # 최근 60일 성과 요약
        perf = db.get_performance_summary(days=60)
        if not perf.empty:
            lines = ["📈 <b>최근 60일 성과 비교</b>\n"]
            for _, r in perf.iterrows():
                lines.append(
                    f"<b>{r['strategy']}</b>/{r['source']}: "
                    f"n={int(r['picks'])} "
                    f"5d={r['avg_5d_pct']:+.1f}% "
                    f"20d={r['avg_20d_pct']:+.1f}% "
                    f"승률={r['win_rate_20d']:.1%}"
                )
            TA.send_tele("\n".join(lines))
    except Exception as e:
        TA.send_tele(f"[비교] 성과 업데이트 오류: {e}")
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: daily_comparison.py {morning|evening}")
        sys.exit(1)
    mode = sys.argv[1]
    if mode == "morning":
        run_morning()
    elif mode == "evening":
        run_evening()
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)
