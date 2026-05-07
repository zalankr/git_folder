"""
KIS API KOSPI 추정 PBR 모듈 — 사전 검증 스크립트
==================================================
본격 코딩 전, KIS API에서 다음 두 가지가 제대로 작동하는지 확인:
  1. KOSPI 종합지수 실시간 조회 (FHPUP02100000)
  2. 종목별 PBR/BPS 조회 (FHKST01010100)

실행:
    cd /var/autobot
    python3 verify_kis_kospi_fields.py
"""
from __future__ import annotations
import sys
import json
import requests

# ─── 사용자 설정 ───────────────────────────────────────────────
sys.path.insert(0, "/var/autobot")
from KIS_KR import KIS_API     # 기존 클래스 활용

# 노광래님이 보유한 계좌 중 토큰 발급된 임의의 계좌(예: KRQT) 사용
# 어떤 계좌든 무관 — 시세조회는 계좌 무관
KEY_FILE   = "/var/autobot/KIS/kis63604155P.txt"          # 본인 환경에 맞게
TOKEN_FILE = "/var/autobot/KIS/kis63604155_token.json"
CANO       = "63604155"
PRDT_CD    = "01"

# KOSPI 시가총액 상위 종목 (검증용)
TOP_TICKERS = {
    "005930": "삼성전자",
    "000660": "SK하이닉스",
    "373220": "LG에너지솔루션",
    "207940": "삼성바이오로직스",
    "005380": "현대차",
}


def hr(s=""):
    print()
    print("=" * 70)
    if s:
        print(f"  {s}")
        print("=" * 70)


# ─── 1) KOSPI 종합지수 실시간 조회 ────────────────────────────
def test_kospi_index(api):
    hr("[1] KIS KOSPI 종합지수 실시간 조회 (FHPUP02100000)")
    api._rate_limit_sleep()

    path = "uapi/domestic-stock/v1/quotations/inquire-index-price"
    url  = f"{api.url_base}/{path}"
    headers = {
        "Content-Type":  "application/json",
        "authorization": f"Bearer {api.access_token}",
        "appKey":        api.app_key,
        "appSecret":     api.app_secret,
        "tr_id":         "FHPUP02100000",
    }
    params = {
        "FID_COND_MRKT_DIV_CODE": "U",      # U: 업종지수
        "FID_INPUT_ISCD":         "0001",   # 0001: KOSPI 종합
    }

    try:
        r = requests.get(url, headers=headers, params=params, timeout=5)
        print(f"  HTTP status: {r.status_code}")
        data = r.json()
    except Exception as e:
        print(f"  ❌ 호출 실패: {e}")
        return None

    print(f"  rt_cd={data.get('rt_cd')}  msg={data.get('msg1')}")
    if data.get("rt_cd") != "0":
        print(f"  ❌ API 오류: {json.dumps(data, ensure_ascii=False, indent=2)}")
        return None

    output = data.get("output", {})
    print("  === output 전체 ===")
    print(json.dumps(output, ensure_ascii=False, indent=2))

    cur = output.get("bstp_nmix_prpr")
    print(f"\n  ✅ 현재 KOSPI 지수 (bstp_nmix_prpr): {cur}")
    return float(cur) if cur else None


# ─── 2) 종목 현재가 + PBR/BPS 조회 ────────────────────────────
def test_stock_pbr(api, ticker, name):
    api._rate_limit_sleep()

    path = "uapi/domestic-stock/v1/quotations/inquire-price"
    url  = f"{api.url_base}/{path}"
    headers = {
        "Content-Type":  "application/json",
        "authorization": f"Bearer {api.access_token}",
        "appKey":        api.app_key,
        "appSecret":     api.app_secret,
        "tr_id":         "FHKST01010100",
    }
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD":         ticker,
    }

    r = requests.get(url, headers=headers, params=params, timeout=5)
    data = r.json()
    if data.get("rt_cd") != "0":
        print(f"  [{ticker} {name}] ❌ {data.get('msg1')}")
        return None

    out = data["output"]
    return {
        "ticker":  ticker,
        "name":    name,
        "price":   int(out.get("stck_prpr", 0)),
        "pbr":     float(out.get("pbr", 0) or 0),
        "per":     float(out.get("per", 0) or 0),
        "bps":     int(out.get("bps", 0) or 0),
        "eps":     int(out.get("eps", 0) or 0),
        "mktcap":  int(out.get("hts_avls", 0) or 0),  # 시가총액 (백만원)
        "lstn":    int(out.get("lstn_stcn", 0) or 0), # 상장주수
    }


def test_top_stocks_pbr(api):
    hr("[2] KOSPI 시가총액 상위종목 PBR/BPS 조회 (FHKST01010100)")

    print(f"  {'티커':>7s} {'종목명':<10s} {'현재가':>10s} {'PBR':>7s} "
          f"{'BPS':>10s} {'시총(백만)':>14s}")
    print("  " + "-" * 65)

    results = []
    for ticker, name in TOP_TICKERS.items():
        info = test_stock_pbr(api, ticker, name)
        if info is None:
            continue
        results.append(info)
        print(f"  {info['ticker']:>7s} {info['name']:<10s} "
              f"{info['price']:>10,d} {info['pbr']:>7.2f} "
              f"{info['bps']:>10,d} {info['mktcap']:>14,d}")

    print("\n  === 시가총액 가중 PBR (상위 5개 기준) ===")
    total_mktcap = sum(r["mktcap"] for r in results)
    if total_mktcap == 0:
        print("  ❌ 시가총액 합계 0")
        return
    weighted_pbr = sum(r["pbr"] * r["mktcap"] for r in results) / total_mktcap
    print(f"  Σ(PBR × 시총) / Σ시총 = {weighted_pbr:.4f}")
    print(f"  (상위 5개만의 가중평균 — 실제 KOSPI 전체 PBR 산출 시 30~50개 권장)")


# ─── 메인 ──────────────────────────────────────────────────────
def main():
    hr("KIS API KOSPI 추정 PBR 사전 검증")

    api = KIS_API(
        key_file_path=KEY_FILE,
        token_file_path=TOKEN_FILE,
        cano=CANO,
        acnt_prdt_cd=PRDT_CD,
    )

    # 1) KOSPI 지수
    kospi = test_kospi_index(api)

    # 2) 종목 PBR
    test_top_stocks_pbr(api)

    hr("결론")
    if kospi:
        print(f"  ✅ KIS API로 KOSPI 지수 실시간 조회 가능 ({kospi})")
        print(f"  ✅ 종목별 PBR/BPS 조회 가능")
        print("  → 시가총액 가중 KOSPI PBR 자체 산출 모듈 제작 가능")
    else:
        print("  ❌ KOSPI 지수 조회 실패 — 추가 진단 필요")


if __name__ == "__main__":
    main()