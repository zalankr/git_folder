# -*- coding: utf-8 -*-
"""
test_live_trade.py
==================
실거래 검증용 - 미니 KOSPI200 1계약 매수 → 즉시 환매도 청산.

목적:
  KRFT 시스템 실거래 전 마지막 검증.
  주문 → 체결 → 잔고 → 청산 → 체결 → 잔고 흐름이 모두 정상 동작하는지.

위험:
  - 미니 K200 1계약 명목금액 ≈ 6천만원
  - 위탁증거금 ≈ 800만원
  - 시장가 슬리피지 1-2틱 = 약 2만~4만원 손실 (정상)
  - 보유시간 < 30초 목표

안전장치:
  - 정규장 시간 (09:00~15:35) 내에서만 실행
  - 매수 체결 미발생 시 즉시 취소 후 종료
  - 매수 체결 후 청산은 시장가로 즉시 (대기 X)
  - 사용자 확인 입력 단계 (--yes 옵션 없이는 발사 안 함)

사용:
  python3 /var/autobot/TR_KRFT/test_live_trade.py            # dry-run (조회만)
  python3 /var/autobot/TR_KRFT/test_live_trade.py --execute  # 실행 (대화형 확인)
  python3 /var/autobot/TR_KRFT/test_live_trade.py --execute --yes  # 무조건 실행 (위험)
"""
import sys
import os
import time
import argparse
from datetime import datetime
import pytz

sys.path.insert(0, "/var/autobot")
sys.path.insert(0, "/var/autobot/TR_KRFT")

from KIS_KR import KIS_API
import KRFT_order as ORDER
import KRFT_symbol as SYM

# ── 설정 ────────────────────────────────────────────
FUT_CANO         = "64753341"
FUT_ACNT_PRDT_CD = "03"
FUT_KEY_FILE     = f"/var/autobot/KIS/kis{FUT_CANO}nkr.txt"
FUT_TOKEN_FILE   = f"/var/autobot/KIS/kis{FUT_CANO}_token.json"

TEST_QTY = 1   # 미니 K200 1계약


def _now_kst() -> datetime:
    return datetime.now(pytz.timezone("Asia/Seoul"))


def _hr(label: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true",
                        help="실거래 실행 (없으면 조회만)")
    parser.add_argument("--yes", action="store_true",
                        help="사용자 확인 입력 생략 (위험)")
    parser.add_argument("--no-cleanup", action="store_true",
                        help="청산 단계 건너뛰기 (포지션 유지)")
    args = parser.parse_args()

    now = _now_kst()
    print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] test_live_trade 시작")
    print(f"  모드: {'★ 실거래 ★' if args.execute else 'dry (조회만)'}")

    # 1) 시간대 체크 (실거래 시에만)
    if args.execute:
        h, m = now.hour, now.minute
        cur_min = h * 60 + m
        if not (9*60 <= cur_min <= 15*60+30):
            print(f"\n⚠️  정규장 시간(09:00~15:30)이 아닙니다 (현재 {h:02d}:{m:02d})")
            print(f"    실거래는 정규장 중에만 가능합니다. 종료.")
            return 1
        if cur_min >= 15*60+25:
            print(f"\n⚠️  장 마감 임박(15:25 이후) — 청산 실패 위험. 종료.")
            return 1

    # 2) KIS 초기화
    _hr("STEP 1: KIS 초기화")
    try:
        kis = KIS_API(FUT_KEY_FILE, FUT_TOKEN_FILE, FUT_CANO, FUT_ACNT_PRDT_CD)
        print(f"  ✓ KIS 인증 OK")
    except Exception as e:
        print(f"  ✗ KIS 초기화 실패: {e}")
        return 2

    # 3) 종목 결정
    _hr("STEP 2: 거래 종목 산출")
    today = now.date()
    symbols = SYM.get_current_symbols(today)
    symbol = symbols["k200_mini"]
    print(f"  미니 KOSPI200 = {symbol} (만기 {symbols['k200_mini_expiry']})")

    # 4) 현재가/호가
    _hr("STEP 3: 시세 조회")
    cur = ORDER.get_futures_price(kis, symbol)
    if not cur:
        print(f"  ✗ 현재가 조회 실패")
        return 3
    print(f"  현재가: {cur['price']} (상한 {cur['upper']} / 하한 {cur['lower']})")
    print(f"  거래량: {cur['volume']:,} / 미결제: {cur['open_int']:,}")

    ob = ORDER.get_futures_orderbook(kis, symbol)
    if not ob:
        print(f"  ✗ 호가 조회 실패")
        return 3
    print(f"  1호가: 매수 {ob['bid1']} × {ob['bid1_qty']} / "
          f"매도 {ob['ask1']} × {ob['ask1_qty']}")
    spread = ob['ask1'] - ob['bid1']
    print(f"  스프레드: {spread:.2f} 포인트 (≈ {spread*50000:,.0f}원/계약)")

    # 5) 잔고 (사전)
    _hr("STEP 4: 잔고 조회 (매매 전)")
    bal_before = ORDER.get_futures_balance(kis)
    if not bal_before:
        print(f"  ✗ 잔고 조회 실패")
        return 4
    print(f"  예수금        : {bal_before['dnca_cash']:>15,.0f}원")
    print(f"  추정예탁자산  : {bal_before['prsm_dpast_amt']:>15,.0f}원")
    print(f"  주문가능현금  : {bal_before['ord_psbl_cash']:>15,.0f}원")
    print(f"  현재 포지션  : {len(bal_before['positions'])}건")
    for p in bal_before['positions']:
        print(f"    - {p['symbol']} {p['side']} {p['qty']}계약 @ {p['avg_price']}")

    # 6) 주문가능
    _hr("STEP 5: 매수 주문가능 수량")
    psbl = ORDER.get_futures_orderable(
        kis, symbol, ob['ask1'],
        side=ORDER.SIDE_BUY, cls=ORDER.CLS_OPEN)
    if not psbl:
        print(f"  ✗ 주문가능 조회 실패")
        return 5
    print(f"  ord_psbl_qty : {psbl['ord_psbl_qty']}")
    print(f"  bass_idx     : {psbl['bass_idx']}")
    if psbl['ord_psbl_qty'] < TEST_QTY:
        print(f"  ✗ 주문가능수량 부족 ({psbl['ord_psbl_qty']} < {TEST_QTY})")
        return 5

    # 7) 실거래 발사 여부
    if not args.execute:
        print("\n" + "─"*60)
        print("  dry-run 종료. 실거래는 --execute 옵션과 함께 실행.")
        print("─"*60)
        return 0

    # 사용자 확인
    if not args.yes:
        print("\n" + "⚠️ "*15)
        print("  실거래 발사 직전입니다.")
        print(f"    종목     : {symbol} (미니 KOSPI200)")
        print(f"    수량     : {TEST_QTY}계약")
        print(f"    예상가   : 시장가 (≈ {ob['ask1']})")
        print(f"    명목금액 : 약 {ob['ask1']*50000:,.0f}원")
        print(f"    슬리피지 : 약 {spread*50000*TEST_QTY:,.0f}원 (스프레드 1틱)")
        print(f"    이후     : {'유지' if args.no_cleanup else '즉시 시장가 환매도 청산'}")
        ans = input("\n  계속하려면 정확히 'YES' 입력: ")
        if ans != "YES":
            print(f"  취소됨 (입력: {ans!r})")
            return 0

    # 8) 매수 (시장가)
    _hr("STEP 6: 시장가 매수 발사")
    t0 = time.time()
    buy_r = ORDER.order_futures(
        kis, symbol, TEST_QTY, 0,
        side=ORDER.SIDE_BUY, cls=ORDER.CLS_OPEN,
        market_order=True,
    )
    print(f"  주문결과: {buy_r}")
    if not (buy_r and buy_r.get("ok")):
        print(f"  ✗ 매수 주문 실패 — 종료")
        return 6
    buy_order_no = buy_r["order_no"]
    print(f"  ✓ 매수 주문번호: {buy_order_no}")

    # 9) 체결 확인 (최대 10초)
    _hr("STEP 7: 매수 체결 확인 (최대 10초)")
    filled = False
    for i in range(20):  # 0.5초 × 20 = 10초
        time.sleep(0.5)
        bal_mid = ORDER.get_futures_balance(kis)
        if not bal_mid:
            continue
        my_pos = [p for p in bal_mid['positions']
                  if p['symbol'] == symbol and p['side'] == 'long']
        if my_pos and my_pos[0]['qty'] >= TEST_QTY:
            elapsed = time.time() - t0
            print(f"  ✓ 체결 확인 ({elapsed:.1f}초): "
                  f"{my_pos[0]['qty']}계약 avg={my_pos[0]['avg_price']}")
            filled = True
            break
        if i % 4 == 3:
            print(f"  대기 중... ({i*0.5+0.5:.1f}초)")

    if not filled:
        print(f"  ⚠️ 10초 내 체결 확인 안 됨. 미체결 조회 시도...")
        unfilled = ORDER.get_unfilled(kis)
        my_unfilled = [u for u in unfilled if u['order_no'] == buy_order_no]
        if my_unfilled:
            print(f"  미체결 상태: {my_unfilled[0]}")
            print(f"  → 미체결 취소 후 종료")
            ORDER.cancel_order(kis, "", buy_order_no, qty=0)
            return 7
        else:
            print(f"  미체결도 없음 (체결됐는데 잔고에 안 잡힘?). 잔고 재조회 시도")
            time.sleep(2)

    # 10) 청산
    if args.no_cleanup:
        _hr("STEP 8: 청산 건너뜀 (--no-cleanup)")
        return 0

    _hr("STEP 8: 시장가 환매도 청산")
    sell_r = ORDER.order_futures(
        kis, symbol, TEST_QTY, 0,
        side=ORDER.SIDE_SELL, cls=ORDER.CLS_CLOSE,
        market_order=True,
    )
    print(f"  청산결과: {sell_r}")
    if not (sell_r and sell_r.get("ok")):
        print(f"  ✗ 청산 실패 — 수동 청산 필요!")
        print(f"    심각: 매수 포지션 보유 중. 즉시 MTS로 청산하세요.")
        return 8
    sell_order_no = sell_r["order_no"]
    print(f"  ✓ 청산 주문번호: {sell_order_no}")

    # 11) 청산 체결 확인
    _hr("STEP 9: 청산 체결 확인 (최대 10초)")
    cleared = False
    for i in range(20):
        time.sleep(0.5)
        bal_after = ORDER.get_futures_balance(kis)
        if not bal_after:
            continue
        my_pos = [p for p in bal_after['positions']
                  if p['symbol'] == symbol and p['side'] == 'long']
        if not my_pos or my_pos[0]['qty'] == 0:
            elapsed = time.time() - t0
            print(f"  ✓ 청산 완료 (총 소요 {elapsed:.1f}초)")
            cleared = True
            break

    if not cleared:
        print(f"  ⚠️ 청산 체결 확인 안 됨. 미체결 조회 시도...")
        unfilled = ORDER.get_unfilled(kis)
        for u in unfilled:
            if u['order_no'] == sell_order_no:
                print(f"  청산 미체결: {u}")
                print(f"  → MTS에서 수동 청산 필요!")
                return 9

    # 12) 최종 잔고 + 손익
    _hr("STEP 10: 매매 후 잔고 + 손익")
    time.sleep(1)
    bal_final = ORDER.get_futures_balance(kis)
    if bal_final:
        diff_cash = bal_final['dnca_cash'] - bal_before['dnca_cash']
        diff_eval = bal_final['prsm_dpast_amt'] - bal_before['prsm_dpast_amt']
        print(f"  예수금 변동  : {diff_cash:+,.0f}원")
        print(f"  추정자산 변동 : {diff_eval:+,.0f}원")
        print(f"  잔여 포지션  : {len(bal_final['positions'])}건")
        for p in bal_final['positions']:
            print(f"    - {p['symbol']} {p['side']} {p['qty']}계약")

    _hr("✓ 테스트 종료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
