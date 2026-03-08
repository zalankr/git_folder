#!/usr/bin/env python3
"""
StockEasy 전략실 크롤러
- 보유 종목 / 이탈 종목 / 진입 종목 (holding_days=0) 추출
- 로그인 쿠키 지원
- 1호(모멘텀), 2호(피크), 3호(밸류) 전략 지원

사용법:
  python3 stockeasy_crawler.py                    # 2호 피크 (기본)
  python3 stockeasy_crawler.py --strategy peak    # 2호 피크
  python3 stockeasy_crawler.py --strategy momentum # 1호 모멘텀
  python3 stockeasy_crawler.py --strategy value   # 3호 밸류
  python3 stockeasy_crawler.py --all              # 전체 전략
  python3 stockeasy_crawler.py --cookie "세션쿠키값"  # 로그인 필요 시
"""

import re
import json
import requests
import argparse
from datetime import datetime

# =============================================================
# 설정
# =============================================================
STRATEGY_URLS = {
    "momentum": "https://stockeasy.intellio.kr/strategy-room/momentum",
    "peak":     "https://stockeasy.intellio.kr/strategy-room/peak",
    "value":    "https://stockeasy.intellio.kr/strategy-room/value",
}

STRATEGY_NAMES = {
    "momentum": "1호 - 모멘텀 Easy",
    "peak":     "2호 - 피크 Easy",
    "value":    "3호 - 밸류 Easy",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Referer": "https://stockeasy.intellio.kr/strategy-room",
}


# =============================================================
# 핵심 파싱 함수
# =============================================================
def fetch_page(url: str, cookie: str = None) -> str:
    headers = HEADERS.copy()
    if cookie:
        headers["Cookie"] = cookie
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.text


def extract_data_from_html(html: str) -> dict:
    """
    Next.js SSR 페이지에서 __next_f.push 스크립트 안의 initialData JSON 추출.
    로그인 없이도 공개 데이터 접근 가능.
    """
    # __next_f 청크 전체 수집
    scripts = re.findall(r'self\.__next_f\.push\(\[1,"(.+?)"\]\)', html, re.DOTALL)

    for s in scripts:
        if 'initialData' not in s:
            continue

        # JSON-encoded string 디코드
        try:
            decoded = json.loads('"' + s + '"')
        except Exception:
            continue

        # initialData 객체를 포함한 가장 바깥 배열의 마지막 } 찾기
        m = re.search(r'"initialData":(\{.+\})\}\]', decoded, re.DOTALL)
        if not m:
            continue

        try:
            data = json.loads(m.group(1))
            return data
        except json.JSONDecodeError:
            continue

    return {}


def parse_strategy(html: str, strategy_key: str) -> dict:
    """HTML에서 전략 데이터를 파싱하여 정리된 dict 반환"""
    raw = extract_data_from_html(html)
    if not raw or not raw.get("success"):
        return {"error": "데이터 추출 실패", "strategy": strategy_key}

    meta = raw.get("metadata", {})

    # 보유 종목 정리
    holdings = []
    new_entries = []  # 진입 종목 (holding_days == 0)

    for sector, stocks in raw.get("holdings", {}).items():
        for s in stocks:
            item = {
                "stock_code":   s.get("stock_code", ""),
                "stock_name":   s.get("stock_name", ""),
                "sector":       sector,
                "buy_price":    s.get("buy_price", 0),
                "current_price": s.get("current_price", 0),
                "buy_date":     s.get("buy_date", ""),
                "holding_days": s.get("holding_days", 0),
                "return_rate":  s.get("return_rate", 0),
            }
            holdings.append(item)
            if s.get("holding_days", 0) == 0:
                new_entries.append(item)

    # 이탈 종목 정리
    exits = []
    for sector, stocks in raw.get("exits", {}).items():
        for s in stocks:
            exits.append({
                "stock_code":   s.get("stock_code", ""),
                "stock_name":   s.get("stock_name", ""),
                "sector":       sector,
                "buy_price":    s.get("buy_price", 0),
                "sell_price":   s.get("current_price", 0),
                "buy_date":     s.get("buy_date", ""),
                "holding_days": s.get("holding_days", 0),
                "return_rate":  s.get("final_return_rate", 0),
            })

    return {
        "strategy":        strategy_key,
        "strategy_name":   STRATEGY_NAMES.get(strategy_key, strategy_key),
        "target_date":     meta.get("target_date", ""),
        "updated_at":      meta.get("updated_at", ""),
        "holdings":        holdings,
        "new_entries":     new_entries,   # 진입 종목 (당일)
        "exits":           exits,
        "holdings_count":  meta.get("holdings_count", len(holdings)),
        "exits_count":     meta.get("exits_count", len(exits)),
        "today_buy_count": meta.get("today_buy_count", len(new_entries)),
    }


# =============================================================
# 출력 함수
# =============================================================
def print_result(result: dict, show_all: bool = False):
    if "error" in result:
        print(f"\n❌ [{result['strategy']}] 오류: {result['error']}")
        return

    print(f"\n{'='*65}")
    print(f"📊 {result['strategy_name']}")
    print(f"   기준일: {result['target_date']}  |  갱신: {result['updated_at'][:19]}")
    print(f"{'='*65}")

    # 진입 종목 (오늘 새로 들어온 것)
    if result["new_entries"]:
        print(f"\n🟢 진입 종목 ({len(result['new_entries'])}개)")
        print(f"  {'종목코드':<8} {'종목명':<14} {'섹터':<14} {'매수가':>8}")
        print(f"  {'-'*50}")
        for s in result["new_entries"]:
            print(f"  {s['stock_code']:<8} {s['stock_name']:<14} {s['sector']:<14} {s['buy_price']:>8,}")

    # 보유 종목 전체
    print(f"\n📋 보유 종목 ({result['holdings_count']}개)")
    print(f"  {'종목코드':<8} {'종목명':<14} {'섹터':<14} {'매수가':>8} {'현재가':>8} {'수익률':>7} {'보유일':>5}")
    print(f"  {'-'*70}")
    for s in sorted(result["holdings"], key=lambda x: x["return_rate"], reverse=True):
        days_str = f"{s['holding_days']}일" if s['holding_days'] > 0 else "진입"
        ret_str = f"{s['return_rate']:+.2f}%"
        color = ""
        print(f"  {s['stock_code']:<8} {s['stock_name']:<14} {s['sector']:<14} "
              f"{s['buy_price']:>8,} {s['current_price']:>8,} {ret_str:>7} {days_str:>5}")

    # 이탈 종목
    if result["exits"]:
        print(f"\n🔴 이탈 종목 ({result['exits_count']}개)")
        print(f"  {'종목코드':<8} {'종목명':<14} {'섹터':<14} {'매수가':>8} {'매도가':>8} {'수익률':>7}")
        print(f"  {'-'*65}")
        for s in result["exits"]:
            ret_str = f"{s['return_rate']:+.2f}%"
            print(f"  {s['stock_code']:<8} {s['stock_name']:<14} {s['sector']:<14} "
                  f"{s['buy_price']:>8,} {s['sell_price']:>8,} {ret_str:>7}")


def to_json(results: list) -> str:
    return json.dumps(results, ensure_ascii=False, indent=2)


# =============================================================
# 메인
# =============================================================
def crawl(strategy_key: str, cookie: str = None) -> dict:
    url = STRATEGY_URLS[strategy_key]
    print(f"  ⏳ {STRATEGY_NAMES[strategy_key]} 크롤링 중... ", end="", flush=True)
    html = fetch_page(url, cookie)
    result = parse_strategy(html, strategy_key)
    print("완료!")
    return result


def main():
    parser = argparse.ArgumentParser(description="StockEasy 전략실 크롤러")
    parser.add_argument("--strategy", choices=["peak", "momentum", "value"],
                        default="peak", help="크롤링할 전략 (기본: peak)")
    parser.add_argument("--all", action="store_true", help="전체 전략 크롤링")
    parser.add_argument("--cookie", default=None,
                        help='로그인 쿠키 (예: "session=xxx; token=yyy")')
    parser.add_argument("--json", action="store_true", help="JSON 형식으로 출력")
    parser.add_argument("--save", default=None, help="결과를 JSON 파일로 저장")
    args = parser.parse_args()

    strategies = list(STRATEGY_URLS.keys()) if args.all else [args.strategy]
    results = []

    print(f"\n🔍 StockEasy 크롤러 시작 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

    for key in strategies:
        try:
            result = crawl(key, args.cookie)
            results.append(result)
            if not args.json:
                print_result(result)
        except Exception as e:
            print(f"\n❌ {key} 크롤링 실패: {e}")

    if args.json:
        print(to_json(results))

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n💾 저장 완료: {args.save}")

    return results


if __name__ == "__main__":
    main()
