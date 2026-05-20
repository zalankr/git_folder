"""
gold_diag.py — 키움 금현물 API 원본 응답 진단 (조회 전용, 주문 안 함)
============================================================================
용도: 금현물 평가금이 실제의 2.02배로 나오는 원인 추적.
      kt50020(잔고) / ka50100(시세) / kt50021(예수금) 원본 JSON 을
      그대로 출력해 어떤 필드가 잘못 쓰이는지 확정한다.

실행:  /usr/bin/python3 /var/autobot/TR_GOLD/gold_diag.py
       (GOLD_TR.py 와 같은 디렉토리에 두고 실행)

⚠️ 이 스크립트는 시세/잔고/예수금 조회만 한다. 주문·취소 일절 없음.
"""

import os
import sys
import json

# GOLD_TR.py 와 같은 폴더에서 실행 → import 가능
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import GOLD_TR as G


def dump(title, obj):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main():
    print("키움 금현물 API 원본 응답 진단 시작 (조회 전용)")
    print(f"종목코드: {G.GOLD_STOCK_CODE}")

    # ── 토큰 ──
    try:
        token = G.get_access_token()
        print("토큰 발급 OK")
    except Exception as e:
        print(f"토큰 발급 실패: {e}")
        sys.exit(1)

    # ── 1) ka50100 금현물 시세정보 원본 ──
    try:
        raw_price = G._post(token, "ka50100", {"stk_cd": G.GOLD_STOCK_CODE})
        dump("[1] ka50100 시세정보 원본 JSON", raw_price)
        # 가격 관련 필드만 추려서 강조
        price_keys = [k for k in raw_price
                      if any(t in k for t in
                             ("pric", "prc", "pred", "close", "open",
                              "high", "low", "cur", "base"))]
        print("\n  ▼ 가격 관련 필드 발췌:")
        for k in sorted(price_keys):
            print(f"    {k:24s} = {raw_price.get(k)!r}")
    except Exception as e:
        print(f"\nka50100 조회 실패: {e}")

    # ── 2) get_gold_current_price() 가 계산한 현재가 ──
    try:
        cur = G.get_gold_current_price(token)
        print(f"\n  ▶ get_gold_current_price() 반환 = {cur:,}원")
        print(f"    (정상 KRX 금현물 1g 시세는 대략 100,000~150,000원/g 범위)")
    except Exception as e:
        print(f"\nget_gold_current_price 실패: {e}")

    # ── 3) kt50020 금현물 잔고확인 원본 ──
    try:
        raw_bal = G._post(token, "kt50020", {})
        dump("[3] kt50020 잔고확인 원본 JSON", raw_bal)
        # 잔고 종목 배열 강조
        arr = raw_bal.get("gold_acnt_evlt_prst", []) or []
        print(f"\n  ▼ gold_acnt_evlt_prst 항목 수: {len(arr)}")
        for i, item in enumerate(arr):
            print(f"\n  [종목 {i}]")
            for k in sorted(item.keys()):
                print(f"    {k:24s} = {item.get(k)!r}")
        print(f"\n  ▼ 최상위 예수금/금액 필드 발췌:")
        for k in sorted(raw_bal):
            if k == "gold_acnt_evlt_prst":
                continue
            if any(t in k for t in ("entr", "amt", "dpst", "cash", "evlt")):
                print(f"    {k:24s} = {raw_bal.get(k)!r}")
    except Exception as e:
        print(f"\nkt50020 조회 실패: {e}")

    # ── 4) kt50021 금현물 예수금 원본 ──
    try:
        raw_dep = G._post(token, "kt50021", {})
        dump("[4] kt50021 예수금 원본 JSON", raw_dep)
    except Exception as e:
        print(f"\nkt50021 조회 실패: {e}")

    # ── 5) get_gold_balance() 최종 산출값 ──
    try:
        bal = G.get_gold_balance(token)
        dump("[5] get_gold_balance() 최종 반환 dict", bal)
        total = bal["eval_amt"] + bal["deposit"]
        print(f"\n  ▶ 총평가금(코드) = 평가금 {bal['eval_amt']:,} + 예수금 {bal['deposit']:,}")
        print(f"                  = {total:,}원")
        if bal["hold_qty"] > 0:
            print(f"  ▶ g당 단가(코드) = {bal['eval_amt'] // bal['hold_qty']:,}원/g")
        print(f"\n  ※ 실제값(사용자 제공): 총 30,761,166원 / 금 56g / 예수금 24,716,370원")
        print(f"     실제 g당 단가 = {(30761166-24716370)//56:,}원/g")
    except Exception as e:
        print(f"\nget_gold_balance 실패: {e}")

    print("\n진단 완료. 위 [1]~[5] 출력 전체를 복사해 주세요.")


if __name__ == "__main__":
    main()
