"""
manual_buy_JPQT.py
JPQT target 종목 수동 일괄 매수 (장 마감 전 긴급 복구용)

동작:
  1) 미체결 전량 취소 (수정된 cancel_all_unfilled_orders 사용)
  2) JPQT_target.json 읽어 target_qty > 0 종목만 대상
  3) 현재 보유분 차감 → 순매수 필요수량 산출
  4) 매수가능금(get_JP_order_available) 초과 시 비율 자동 조정
  5) 분할 없이 현재가 +0.5% 지정가로 1회 매수 (마감 전 체결 우선)

⚠️ 실제 매수 주문을 보냅니다.
⚠️ 7회차 자동 크론(JST 14:37) 전에 실행해 충돌을 피하세요.
실행: /usr/bin/python3 /var/autobot/TR_JPQT/manual_buy_JPQT.py
"""

import sys
import json
import time

sys.path.insert(0, "/var/autobot/TR_JPQT")
sys.path.insert(0, "/var/autobot/KIS")

import KIS_JP

key_file_path   = "/var/autobot/KIS/kis63604155nkr.txt"
token_file_path = "/var/autobot/KIS/kis63604155_token.json"
cano = "63604155"
acnt_prdt_cd = "01"

JPQT_target_path = "/var/autobot/TR_JPQT/JPQT_target.json"

HEDGE_TICKERS = {"1328", "1482"}
BUY_PRICE_RATE = 1.005   # 현재가 +0.5% 지정가 (체결 우선, 마감 전)

KIS = KIS_JP.KIS_API(key_file_path, token_file_path, cano, acnt_prdt_cd)
LINE = "=" * 60


def unit_size(ticker):
    return 1 if ticker in HEDGE_TICKERS else 100


def floor_unit(ticker, qty):
    u = unit_size(ticker)
    return (int(qty) // u) * u


def main():
    print(LINE)
    print("JPQT target 수동 일괄 매수")
    print(LINE)

    # ---- target 로드 ----
    try:
        with open(JPQT_target_path, "r", encoding="utf-8") as f:
            target = json.load(f)
    except Exception as e:
        print(f"❌ JPQT_target.json 로드 실패: {e}")
        sys.exit(1)

    target_qty = {}
    for t, info in target.items():
        if t == "_meta":
            continue
        q = int(info.get("target_qty", 0))
        if q > 0:
            target_qty[t] = {"qty": q, "name": info.get("name", "")}

    if not target_qty:
        print("target_qty > 0 종목 없음. 종료.")
        return
    print(f"target 매수대상: {len(target_qty)}종목")

    # ---- 1) 미체결 취소 ----
    print(f"\n[1] 미체결 취소")
    summary, msgs = KIS.cancel_all_unfilled_orders()
    print(f"  취소: {summary['success']}/{summary['total']} 성공")
    if summary.get("failed", 0) > 0:
        for fl in summary.get("failed_list", []):
            print(f"    실패 {fl['ticker']}: {fl.get('error','')}")
    time.sleep(2)

    # ---- 2) 보유 차감 → 순매수 필요수량 ----
    print(f"\n[2] 보유 차감 후 순매수 수량 산출")
    stocks = KIS.get_JP_stock_balance()
    if not isinstance(stocks, list):
        print(f"❌ 잔고 조회 불가: {stocks}")
        sys.exit(1)
    hold = {s["ticker"]: int(s["quantity"]) for s in stocks}

    buy = {}
    for t, info in target_qty.items():
        held = hold.get(t, 0)
        need = info["qty"] - held
        need = floor_unit(t, need)
        if need > 0:
            buy[t] = need
        print(f"  {t} {info['name']}: target {info['qty']} - 보유 {held} = 매수 {max(need,0)}")

    if not buy:
        print("\n✅ 추가 매수 불필요 (이미 target 충족). 종료.")
        return

    # ---- 3) 현재가 조회 + 목표매수금 ----
    print(f"\n[3] 현재가 조회 및 매수금 계산")
    buy_prices = {}
    target_JPY = 0.0
    for t, q in buy.items():
        price = KIS.get_JP_current_price(t)
        if not isinstance(price, float) or price <= 0:
            print(f"  ⚠️ {t} 현재가 조회 불가 ({price}) → 제외")
            continue
        buy_prices[t] = price
        target_JPY += price * BUY_PRICE_RATE * q
        time.sleep(0.15)
    buy = {t: q for t, q in buy.items() if t in buy_prices}

    orderable = KIS.get_JP_order_available()
    if orderable is None:
        print("❌ 매수가능금 조회 불가")
        sys.exit(1)
    orderable = float(orderable)
    print(f"  매수가능금: ¥{orderable:,.0f} | 목표매수금: ¥{target_JPY:,.0f}"
          + (f" | 조정비율: {orderable/target_JPY:.4f}" if target_JPY > 0 else ""))

    # ---- 4) 매수가능금 초과 시 비율 조정 ----
    if target_JPY > orderable and target_JPY > 0:
        rate = orderable / target_JPY
        for t in list(buy.keys()):
            adj = floor_unit(t, int(buy[t] * rate))
            if adj > 0:
                buy[t] = adj
            else:
                del buy[t]
        print(f"  ⚠️ 매수금 부족 → 비율 조정 (rate={rate:.4f})")
    else:
        print("  매수가능금 충분 → 전량 매수")

    if not buy:
        print("\n조정 후 매수 종목 없음. 종료.")
        return

    # ---- 5) 매수 주문 (분할 없이 1회) ----
    print(f"\n[4] 매수 주문 실행 (현재가 +0.5% 지정가)")
    ok, fail = 0, 0
    for t, q in buy.items():
        price = buy_prices[t]
        order_price = int(round(price * BUY_PRICE_RATE, 0))
        order_info, om = KIS.order_buy_JP(t, q, order_price)
        if order_info is None:
            time.sleep(2)
            order_info, om = KIS.order_buy_JP(t, q, order_price)
        if order_info and order_info.get("success"):
            ok += 1
            print(f"  ✅ 매수 {t} {q}주 @ ¥{order_price:,} "
                  f"주문번호:{order_info.get('order_number','')}")
        else:
            fail += 1
            err = order_info.get("error_message", "응답없음") if order_info else "응답없음"
            print(f"  ❌ 매수실패 {t} {q}주: {err}")
        time.sleep(0.3)

    print(f"\n{LINE}")
    print(f"매수 완료: 성공 {ok} / 실패 {fail} / 전체 {len(buy)}")
    print("→ check_JPQT_status.py 로 target 충족 확인 권장")
    print("→ 7회차 자동 크론(JST 14:37)은 target 충족 시 '매수 종목 없음'으로 자연 종료됨")
    print(LINE)


if __name__ == "__main__":
    main()
