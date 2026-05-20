"""
gold_snapshot_diag.py — daily_snapshot 의 fetch_gold_balance 실패 지점 추적
============================================================================
'Gold: [미연결] ₩0' 의 정확한 원인을 찍는다.
fetch_gold_balance() 와 똑같은 import 경로를 그대로 재현하되,
각 단계마다 무엇이 성공/실패했는지 출력한다.

실행:  /usr/bin/python3 /var/autobot/Balance/gold_snapshot_diag.py
       (daily_snapshot.py 와 같은 환경/위치에서 실행)
"""

import sys
import os
import traceback
import importlib

print("=" * 70)
print("  fetch_gold_balance 실패 지점 진단")
print("=" * 70)

GOLD_DIR = "/var/autobot/TR_GOLD"
print(f"\n[1] GOLD_DIR = {GOLD_DIR}")
print(f"    존재 여부: {os.path.isdir(GOLD_DIR)}")
print(f"    GOLD_TR.py 존재: {os.path.isfile(os.path.join(GOLD_DIR, 'GOLD_TR.py'))}")

if GOLD_DIR not in sys.path:
    sys.path.insert(0, GOLD_DIR)

# ── [2] import ──
print("\n[2] GOLD_TR import 시도")
try:
    if "GOLD_TR" in sys.modules:
        gold = importlib.reload(sys.modules["GOLD_TR"])
    else:
        gold = importlib.import_module("GOLD_TR")
    print("    ✅ import 성공")
except Exception as e:
    print(f"    ❌ import 실패: {e}")
    traceback.print_exc()
    sys.exit(1)

# ── [3] key 파일 ──
print(f"\n[3] key 파일 = {gold.KEY_FILE_PATH}")
print(f"    존재 여부: {os.path.isfile(gold.KEY_FILE_PATH)}")
print(f"    토큰 캐시 = {gold.TOKEN_FILE_PATH}")
print(f"    토큰 캐시 존재: {os.path.isfile(gold.TOKEN_FILE_PATH)}")

# ── [4] 토큰 발급 ──
print("\n[4] get_access_token() 시도")
token = None
try:
    token = gold.get_access_token()
    print(f"    ✅ 토큰 발급 성공 (길이 {len(token)})")
except RuntimeError as e:
    print(f"    ❌ RuntimeError: {e}")
    print("    → fetch_gold_balance 가 여기서 placeholder 처리 → [미연결]")
    sys.exit(1)
except SystemExit as e:
    print(f"    ❌ SystemExit: {e}")
    sys.exit(1)
except Exception as e:
    print(f"    ❌ 기타 예외: {type(e).__name__}: {e}")
    traceback.print_exc()
    sys.exit(1)

# ── [5] 잔고 조회 ──
print("\n[5] get_gold_balance(token) 시도")
try:
    bal = gold.get_gold_balance(token)
    print("    ✅ 잔고 조회 성공")
    print("    반환 dict:")
    for k, v in bal.items():
        print(f"      {k:18s} = {v:,}" if isinstance(v, (int, float))
              else f"      {k:18s} = {v}")
except RuntimeError as e:
    print(f"    ❌ RuntimeError: {e}")
    print("    → _post 의 return_code != 0 (API 오류). "
          "fetch_gold_balance 가 placeholder 처리 → [미연결]")
    print("    ▶ kt50020 응답이 실패. 토큰 만료, 장 시간대, 권한 등 확인 필요.")
    sys.exit(1)
except Exception as e:
    print(f"    ❌ 기타 예외: {type(e).__name__}: {e}")
    traceback.print_exc()
    sys.exit(1)

# ── [6] 최종 합산 ──
print("\n[6] 최종 결과")
eval_amt = float(bal.get("eval_amt", 0) or 0)
deposit  = float(bal.get("deposit", 0) or 0)
total    = float(bal.get("total_amt", 0) or 0)
print(f"    금평가금 = {eval_amt:,.0f}원")
print(f"    예수금   = {deposit:,.0f}원")
print(f"    총평가금 = {total:,.0f}원")
print("\n진단 완료. [미연결]이 아니라 정상 조회됨.")
print("위 [1]~[6] 출력 전체를 복사해 주세요.")
