"""
diagnose_krqt.py
================
EC2에서 실행해 KRFT_TR이 사용한 KRQT 90M의 정확한 원인 파악.

실행:
    cd /var/autobot/TR_KRFT
    /usr/bin/python3 /home/ec2-user/diagnose_krqt.py
"""
import sys
import json

sys.path.insert(0, '/var/autobot')
sys.path.insert(0, '/var/autobot/TR_KRFT')

import daily_snapshot as DS

print("=" * 72)
print("[1] KRQT 4개 카테고리 각각의 반환값")
print("=" * 72)
DS._account_cache.clear()  # 캐시 초기화하여 신선한 호출
total_all = 0.0
total_stock = 0.0
total_cash = 0.0
for (market, strategy, sub, cano, acnt, handler_name, kwargs) in DS.ACCOUNTS:
    if strategy != 'KRQT':
        continue
    handler = DS.HANDLERS.get(handler_name)
    data = handler(cano, acnt, kwargs)
    tk = float(data.get('total_krw', 0) or 0)
    se = float(data.get('stock_eval_krw', 0) or 0)
    cs = float(data.get('cash_krw', 0) or 0)
    print(f"  {sub:25s}: total={tk:>15,.0f}  stock={se:>15,.0f}  cash={cs:>15,.0f}")
    total_all += tk
    total_stock += se
    total_cash += cs
print(f"  {'합계':25s}: total={total_all:>15,.0f}  stock={total_stock:>15,.0f}  cash={total_cash:>15,.0f}")

print()
print("=" * 72)
print("[2] KIS 잔고 원본 (전체 KRQT 계좌)")
print("=" * 72)
key = 'kr:63604155:01:'
if key in DS._account_cache:
    bal = DS._account_cache[key]
    print(f"  total      : {bal['total']:,.0f}")
    print(f"  stock_eval : {bal['stock_eval']:,.0f}")
    print(f"  cash       : {bal['cash']:,.0f}")
    print(f"  종목 수    : {len(bal.get('stocks', []))}")
    
    print()
    print("  --- 평가금 상위 15개 종목 ---")
    stocks = sorted(bal.get('stocks', []), key=lambda x: -float(x.get('eval_amt', 0) or 0))
    for s in stocks[:15]:
        print(f"    {str(s.get('code','')).zfill(6)} "
              f"{str(s.get('name',''))[:20]:20s} "
              f"qty={float(s.get('qty',0) or 0):>10,.2f} "
              f"eval={float(s.get('eval_amt',0) or 0):>15,.0f}")
else:
    print("  ⚠️ _account_cache에 없음 - handler가 정상 실행되지 않음")

print()
print("=" * 72)
print("[3] KRQT_result.json 구조 (시즌 매핑)")
print("=" * 72)
try:
    with open('/var/autobot/TR_KRQT/KRQT_result.json') as f:
        krqt_res = json.load(f)
    
    mapped_codes_per_cat = {}
    all_mapped = set()
    for cat, stocks in krqt_res.items():
        if cat == 'remain_last':
            continue
        if isinstance(stocks, list):
            codes = [str(s.get('code','')).zfill(6) for s in stocks]
            mapped_codes_per_cat[cat] = codes
            all_mapped.update(codes)
            print(f"  {cat:25s}: {len(stocks)}개 종목")
            for s in stocks[:3]:
                print(f"    - {str(s.get('code','')).zfill(6)} "
                      f"{str(s.get('name',''))[:15]:15s} "
                      f"qty={s.get('qty',0)}")
    
    remain = krqt_res.get('remain_last', [])
    print(f"  remain_last              : {len(remain)}개")
    for s in remain[:5]:
        print(f"    - {str(s.get('code','')).zfill(6)} "
              f"{str(s.get('name',''))[:15]:15s} "
              f"qty={s.get('qty',0)}")
except FileNotFoundError:
    print("  ⚠️ KRQT_result.json 파일 없음")
except Exception as e:
    print(f"  ⚠️ 읽기 실패: {e}")

print()
print("=" * 72)
print("[4] 매핑 불일치 분석")
print("=" * 72)
if key in DS._account_cache:
    bal = DS._account_cache[key]
    bal_codes = {str(s.get('code','')).zfill(6) for s in bal.get('stocks', []) 
                 if float(s.get('qty', 0) or 0) > 0}
    
    in_bal_not_mapped = bal_codes - all_mapped  # 잔고에는 있으나 매핑 안 됨
    in_mapped_not_bal = all_mapped - bal_codes  # 매핑에는 있으나 잔고 없음
    
    print(f"  실잔고 보유 종목 수: {len(bal_codes)}")
    print(f"  매핑된 종목 수    : {len(all_mapped)}")
    print(f"  잔고 있는데 미매핑: {len(in_bal_not_mapped)}개")
    if in_bal_not_mapped:
        bal_lookup = {str(s.get('code','')).zfill(6): s for s in bal.get('stocks', [])}
        sorted_unmapped = sorted(in_bal_not_mapped, 
                                  key=lambda c: -float(bal_lookup.get(c,{}).get('eval_amt',0) or 0))
        for c in sorted_unmapped[:10]:
            s = bal_lookup.get(c, {})
            print(f"    {c} {str(s.get('name',''))[:20]:20s} "
                  f"eval={float(s.get('eval_amt',0) or 0):>15,.0f}")
    
    print(f"  매핑은 있는데 잔고 없음(또는 0): {len(in_mapped_not_bal)}개")
    if in_mapped_not_bal:
        for c in list(in_mapped_not_bal)[:5]:
            print(f"    {c}")

print()
print("=" * 72)
print("[5] KRFT_TR.calc_spot_eval_krw 재실행 (현재 시점)")
print("=" * 72)
from KRFT_TR import calc_spot_eval_krw, load_result
result = load_result()
spot = calc_spot_eval_krw(result)
print(f"  spot_krw : {spot['krw']:,.0f}")
print(f"  KRQT     : {spot['krqt']:,.0f}")
print(f"  KRTR     : {spot['krtr']:,.0f}")
print(f"  source   : {spot['source']}")
