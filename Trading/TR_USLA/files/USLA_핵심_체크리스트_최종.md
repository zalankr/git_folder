# USLA 자동매매 핵심 이슈 체크리스트 (최종 수정본)

## 🚨 즉시 확인 필요한 핵심 이슈

### 1. 주문 실패 추적 문제 ⚠️

**현재 문제:**
```python
# ❌ 실패한 주문이 TR 파일에 저장되지 않음
if result.get('success') == True:
    Sell_order.append(order_info)
else:
    KA.SendMessage(f"주문 실패")  # 로그만 남기고 끝
```

**해결 방법:**
```python
# ✅ 실패한 주문도 저장
if result.get('success') == True:
    Sell_order.append({...})
else:
    Sell_order.append({
        'success': False,
        'ticker': ticker,
        'error_message': error_msg,
        ...
    })
```

**영향:**
- 다음 라운드에서 실패한 주문 재시도 불가
- 주문 실패율 파악 불가
- 디버깅 어려움

---

### 2. USD 예수금 내부 일관성 위험 ⚠️⚠️⚠️

**시스템 구조 이해:**
```
한 계좌 = 여러 전략이 USD 예수금을 나눠서 사용
├─ USLA: $3,000 (USLA_data.json으로 관리)
├─ 전략2: $4,000
└─ 전략3: $3,000

→ 실제 API 예수금($10,000)과 비교 불가
→ JSON 기반 내부 일관성 검증 필요
```

**현재 문제:**
```python
# Round 1
Hold_usd = USLA_data['CASH']     # USLA_data.json

# Round 2+
Hold_usd = TR_data['CASH']       # USLA_TR.json

# ❌ 두 파일이 동기화되지 않으면 예수금 차이 발생
# ❌ 라운드 간 USD 변화가 체결 금액과 일치하는지 검증 없음
```

**해결 방법:**
```python
# ✅ 내부 일관성 검증 함수
def validate_usd_consistency(prev_usd, sell_amount, buy_amount, current_usd, tolerance=5.0):
    """
    USD 예수금 내부 일관성 검증
    공식: 이전 USD + 매도 체결액 - 매수 체결액 = 현재 USD
    """
    expected_usd = prev_usd + sell_amount - buy_amount
    diff = abs(current_usd - expected_usd)
    is_valid = diff <= tolerance
    
    if not is_valid:
        KA.SendMessage(
            f"⚠️ USD 예수금 계산 불일치\n"
            f"이전: ${prev_usd:.2f}\n"
            f"매도: +${sell_amount:.2f}\n"
            f"매수: -${buy_amount:.2f}\n"
            f"예상: ${expected_usd:.2f}\n"
            f"실제: ${current_usd:.2f}\n"
            f"차이: ${diff:.2f}"
        )
    
    return is_valid, expected_usd, diff

# ✅ Round 2~25에서 매 라운드 검증
prev_round_usd = Hold_usd  # 체결 전 USD

# ... 체결 확인 후 ...

validate_usd_consistency(
    prev_usd=prev_round_usd,
    sell_amount=sell_net_amount,
    buy_amount=buy_total_amount,
    current_usd=Hold_usd,
    tolerance=5.0
)
```

**검증 흐름:**
```
Round N-1: CASH = $3,000 (USLA_TR.json 저장)
          ↓
Round N:  CASH = $3,000 (USLA_TR.json 로드)
          ↓
체결 확인: 매도 +$500, 매수 -$300
          ↓
USD 계산: $3,000 + $500 - $300 = $3,200
          ↓
검증:     예상 $3,200 = 실제 $3,200 ✓
          ↓
Round N:  CASH = $3,200 (USLA_TR.json 저장)
```

**영향:**
- 잘못된 예수금으로 주문 실패
- 누적 오차 발생
- 수익률 계산 오류

---

### 3. 체결 확인 시 실패한 주문 포함 ⚠️

**현재 문제:**
```python
# ❌ 모든 주문(성공/실패 포함)에 대해 체결 확인 시도
sell_summary = USLA.calculate_sell_summary(Sell_order)
```

**해결 방법:**
```python
# ✅ 성공한 주문만 필터링
successful_orders = [o for o in Sell_order if o.get('success', False)]
sell_summary = USLA.calculate_sell_summary(successful_orders)
```

**영향:**
- API 호출 낭비
- 불필요한 에러 메시지
- 처리 시간 증가

---

### 4. 데이터 저장 실패 시 유실 위험 ⚠️⚠️

**현재 문제:**
```python
# ❌ 저장 실패 시 예외 처리 없음
USLA.save_USLA_TR_json(TR_data)
# 저장 실패 시 데이터 유실 → 다음 라운드 실행 불가
```

**해결 방법:**
```python
# ✅ 3중 백업 메커니즘
try:
    # 1차: 정상 저장
    USLA.save_USLA_TR_json(TR_data)
except Exception as e:
    # 2차: 백업 파일 생성
    backup_path = f"USLA_TR_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(backup_path, 'w') as f:
        json.dump(TR_data, f)
    KA.SendMessage(f"백업 파일 생성: {backup_path}")
    
    # 3차: 카카오톡으로 요약 전송
    summary = {'round': TR_data['round'], 'CASH': TR_data['CASH'], ...}
    KA.SendMessage(f"TR 요약: {summary}")
```

**영향:**
- 데이터 유실
- 거래 중단
- 수동 복구 필요

---

## 📋 배포 전 필수 확인 사항

### Phase 1: 백업 (필수)
```bash
# 기존 파일 백업
cd /var/autobot/TR_USLA
cp USLA_Trading.py USLA_Trading_backup_$(date +%Y%m%d).py
cp USLA_model.py USLA_model_backup_$(date +%Y%m%d).py
cp USLA_data.json USLA_data_backup_$(date +%Y%m%d).json
cp USLA_TR.json USLA_TR_backup_$(date +%Y%m%d).json
```

### Phase 2: 코드 배포
```bash
# 개선된 코드 복사
cp /path/to/USLA_Trading_fixed.py /var/autobot/TR_USLA/USLA_Trading.py
```

### Phase 3: 검증 (필수)
```python
# 테스트 스크립트 실행
python3 -c "
import USLA_model
import KIS_Calender

# 1. 모듈 import 확인
print('✓ 모듈 import 성공')

# 2. JSON 파일 존재 확인
import os
files = [
    '/var/autobot/TR_USLA/USLA_data.json',
    '/var/autobot/TR_USLA/USLA_TR.json',
    '/var/autobot/TR_USLA/USLA_rebalancing_day.json'
]
for f in files:
    if os.path.exists(f):
        print(f'✓ {f} 존재')
    else:
        print(f'✗ {f} 없음')

# 3. API 토큰 확인
usla = USLA_model.USLA_Model(
    '/var/autobot/TR_USLA/kis63721147nkr.txt',
    '/var/autobot/TR_USLA/kis63721147_token.json',
    '63721147',
    '01'
)
if usla.access_token:
    print('✓ API 토큰 유효')
else:
    print('✗ API 토큰 없음')
"
```

### Phase 4: 드라이런 테스트 (권장)
1. 리밸런싱일이 아닌 날짜에 테스트
2. 소량 자금으로 실제 거래 테스트
3. 로그 확인

---

## 🔍 실시간 모니터링 포인트

### 실행 중 확인 사항

**1회차 (초기화):**
- [ ] target_weight 계산 정상
- [ ] USLA_data['CASH'] 초기값 로깅 확인
- [ ] 매도 주문 성공률 확인
- [ ] 매수 주문 성공률 확인
- [ ] TR 데이터 저장 확인

**2~24회차 (반복):**
- [ ] 미체결 주문 취소 확인
- [ ] 이전 라운드 USD 로깅
- [ ] 체결 확인 (성공한 주문만)
- [ ] **USD 내부 일관성 검증 통과** ⭐
- [ ] 새 주문 생성 정상
- [ ] TR 데이터 업데이트 확인

**25회차 (마무리):**
- [ ] 최종 체결 확인
- [ ] **USD 내부 일관성 최종 검증** ⭐
- [ ] USLA 티커만 필터링 확인
- [ ] USLA_data.json 최종 저장
- [ ] 카카오톡 최종 리포트

---

## 🚑 긴급 상황 대응

### 시나리오 1: USD 검증 실패
```bash
# ⚠️ USD 예수금 계산 불일치
# 이전: $3,000.00
# 매도: +$500.50
# 매수: -$300.00
# 예상: $3,200.50
# 실제: $3,210.00
# 차이: $9.50

# 1. 로그 확인
# - 어느 라운드에서 실패했는지
# - 차이 금액이 허용 오차($5) 초과하는지

# 2. 체결 내역 확인
cat USLA_TR.json | grep -A 10 "Sell_order"
cat USLA_TR.json | grep -A 10 "Buy_order"

# 3. 수수료 계산 확인
# - 매도 수수료: 0.09%
# - 매수 수수료: 체결가에 포함

# 4. 허용 오차 조정 (필요시)
# tolerance=5.0 → tolerance=10.0으로 변경

# 5. 수동 보정 (차이가 크면)
# USLA_TR.json의 CASH 값을 정확한 값으로 수정
vi /var/autobot/TR_USLA/USLA_TR.json
# "CASH": 3210.00  # 실제 계산된 값으로 수정
```

### 시나리오 2: 주문이 전혀 체결되지 않음
```bash
# 1. 미체결 주문 확인
# KIS API에서 직접 확인 또는 HTS 확인

# 2. 원인 파악
- 가격 조회 실패? → 로그 확인
- 주문 API 오류? → 로그 확인
- 거래 정지? → HTS 확인
- 분할 가격이 시장가와 너무 차이남? → split 전략 재검토
```

### 시나리오 3: USD 예수금이 음수
```bash
# ⚠️ 매수 가능 USD 부족: $-50.00 (목표: $500.00)

# 1. 즉시 거래 중단
killall python3

# 2. 원인 파악
# - 체결 금액이 잘못 계산되었는지
# - 누적 오차가 쌓였는지

# 3. USLA_data.json 확인
cat /var/autobot/TR_USLA/USLA_data.json | grep CASH

# 4. 수동 보정
# Round 1 시작 시 올바른 USD 값으로 설정
vi /var/autobot/TR_USLA/USLA_data.json
{
    ...
    "CASH": 3000.00,  # 정확한 값으로 수정
    ...
}

# 5. 다음 리밸런싱일부터 재시작
```

### 시나리오 4: TR 파일 저장 실패
```bash
# ✗ TR 데이터 저장 실패: Permission denied
# ✓ 백업 파일 생성: /var/autobot/TR_USLA/USLA_TR_backup_20251106_143025.json

# 1. 백업 파일 확인
ls -lt /var/autobot/TR_USLA/USLA_TR_backup_*

# 2. 최신 백업을 정식 파일로 복사
cd /var/autobot/TR_USLA
cp USLA_TR_backup_20251106_143025.json USLA_TR.json

# 3. 권한 확인 및 수정
ls -l USLA_TR.json
chmod 644 USLA_TR.json

# 4. 다음 라운드 재시작
```

### 시나리오 5: Round 1과 Round 2 USD 불일치
```bash
# Round 1: USLA_data.json의 CASH = $3,000
# Round 2: USLA_TR.json의 CASH = $2,500
# ⚠️ $500 차이 발생!

# 1. 원인 파악
# - Round 1에서 TR 저장 시 CASH가 잘못 기록되었는지
# - Round 1 체결 금액 계산 오류인지

# 2. Round 1 로그 확인
grep "Round 1 시작 USD" /var/log/autobot/USLA.log
grep "USD 변화" /var/log/autobot/USLA.log

# 3. 체결 내역 확인
# USLA_TR.json의 Sell_order, Buy_order 확인

# 4. 수동 보정
# 올바른 USD 값으로 USLA_TR.json 수정
vi /var/autobot/TR_USLA/USLA_TR.json
{
    "round": 1,
    "CASH": 3000.00,  # 정확한 값으로 수정
    ...
}

# 5. Round 2 재시작
```

---

## 📊 성능 모니터링 지표

### 주문 성공률
```python
# 매 라운드마다 확인
sell_success_rate = sum(1 for o in Sell_order if o['success']) / len(Sell_order)
buy_success_rate = sum(1 for o in Buy_order if o['success']) / len(Buy_order)

# 정상 범위: 90% 이상
# 80% 미만: 문제 조사 필요
# 50% 미만: 즉시 중단 및 조사
```

### USD 예수금 검증 통과율
```python
# Round 2~25에서 확인
validation_passed = True  # validate_usd_consistency 결과

# 정상: 모든 라운드 통과
# 1~2회 실패: 주의 (허용 오차 조정 검토)
# 3회 이상 실패: 즉시 중단 및 조사
```

### USD 오차 추이
```python
# 허용 오차: $5.00
actual_diff = abs(current_usd - expected_usd)

# $0~$2: 정상 범위
# $2~$5: 주의 범위
# $5 초과: 검증 실패
```

### 체결률
```python
# 25회차 종료 시 확인
total_filled = sell_summary['filled_quantity'] + buy_summary['filled_quantity']
total_ordered = sell_summary['total_quantity'] + buy_summary['total_quantity']
fill_rate = total_filled / total_ordered if total_ordered > 0 else 0

# 정상 범위: 95% 이상
# 90% 미만: 분할 전략 재검토
```

---

## 📝 로그 확인 방법

### 핵심 로그 패턴

**Round 1:**
```
✓ Round 1 시작 USD: $3,000.00
매도 주문 완료: 5/5 성공
매수 주문 완료: 4/5 성공
2025-11-06, USLA_winter 리밸런싱
14:30 1/25회차 저장완료
매도: 5/5, 매수: 4/5
```

**Round 2~24:**
```
미체결 주문 취소: 2/3
📤 매도 체결 요약:
주문: 5건 (완전체결:4, 부분:1, 미체결:0)
수량: 48/50
매도금액: $5,400.00
수수료: $4.86 (0.09%)
순입금: $5,395.14

📥 매수 체결 요약:
주문: 4건 (완전체결:3, 부분:1, 미체결:0)
수량: 45/50
매수금액: $3,150.00 (수수료 포함)

✓ USD 검증 통과 (차이: $2.50)
$3,000.00 → $5,245.14

매도 주문 완료: 5/5 성공
매수 주문 완료: 5/5 성공
```

**USD 검증 실패:**
```
⚠️ USD 예수금 계산 불일치
이전: $3,000.00
매도: +$500.50
매수: -$300.00
예상: $3,200.50
실제: $3,210.00
차이: $9.50
```

### 로그 파일 확인
```bash
# 시스템 로그
tail -f /var/log/autobot/USLA.log

# TR 데이터 히스토리
ls -lt /var/autobot/TR_USLA/USLA_TR*.json

# 백업 파일 확인
ls -lt /var/autobot/TR_USLA/*backup*

# 특정 패턴 검색
grep "USD 검증" /var/log/autobot/USLA.log
grep "실패" /var/log/autobot/USLA.log
grep "차이:" /var/log/autobot/USLA.log
```

---

## ✅ 최종 체크리스트

### 개발 단계
- [x] 기존 코드 백업 완료
- [x] 개선 코드 작성 완료
- [x] USD 내부 일관성 검증 로직 추가
- [x] 개선 보고서 작성 완료
- [ ] 코드 리뷰 완료
- [ ] 단위 테스트 완료

### 테스트 단계
- [ ] 드라이런 테스트 (주문 없이)
- [ ] 소액 실거래 테스트
- [ ] 전체 25회차 시뮬레이션
- [ ] **USD 내부 일관성 검증 테스트** ⭐
- [ ] 오류 복구 시나리오 테스트

### 배포 단계
- [ ] 프로덕션 백업 완료
- [ ] 개선 코드 배포
- [ ] health_check 실행 확인
- [ ] 첫 리밸런싱일 모니터링
- [ ] **USD 검증 통과 확인** ⭐
- [ ] 1회차~25회차 완주 확인

### 운영 단계
- [ ] 일일 모니터링 체계 구축
- [ ] USD 오차 추이 분석
- [ ] 주간 성능 리포트
- [ ] 월간 수익률 분석
- [ ] 분기별 전략 재검토

---

## 💡 추가 고려사항

### 1. USD 예수금 허용 오차 조정
```python
# 현재 설정
tolerance = 5.0  # $5

# 조정 기준
# - 거래 규모가 큰 경우: tolerance = 10.0
# - 거래 규모가 작은 경우: tolerance = 2.0
# - 최종 라운드(25): tolerance = 10.0 (현재 적용됨)
```

### 2. 누적 USD 추적 (선택적)
```python
# USLA_TR.json에 추가 필드
{
    "round": 14,
    "CASH": 3200.00,
    "cumulative_sell": 12500.00,   # ⭐ 누적 매도액
    "cumulative_buy": 11300.00,    # ⭐ 누적 매수액
    "initial_usd": 3000.00,        # ⭐ Round 1 초기 USD
    ...
}

# Round 25 최종 검증
final_usd = initial_usd + cumulative_sell - cumulative_buy
# 3000 + 12500 - 11300 = 4200
if abs(final_usd - Hold_usd) > 10:
    KA.SendMessage(f"⚠️ 누적 USD 검증 실패")
```

### 3. 알림 최적화
- **즉시 알림**: 주문 실패, USD 검증 실패, 저장 실패
- **요약 알림**: 라운드 시작/종료, 체결 요약
- **일일 알림**: 전체 통계 (1회/일)

### 4. 데이터 백업 전략
```bash
# 매일 자정 자동 백업 (crontab)
0 0 * * * cp /var/autobot/TR_USLA/USLA_data.json /var/backups/USLA_data_$(date +\%Y\%m\%d).json

# 주간 백업 (일요일 자정)
0 0 * * 0 tar -czf /var/backups/USLA_weekly_$(date +\%Y\%m\%d).tar.gz /var/autobot/TR_USLA/*.json

# 리밸런싱 직전 수동 백업
# Round 1 시작 전에 수동으로 백업
```

---

## 🎓 학습 포인트

### USD 예수금 관리 핵심 원칙

1. **분리 관리**: 전략별 USD는 JSON 파일로 독립 관리
2. **일관성 검증**: 라운드 간 USD 변화 = 체결 금액
3. **수수료 고려**: 
   - 매도: gross_amount × 0.0009 = fee, net = gross - fee
   - 매수: 체결가에 이미 수수료 포함
4. **허용 오차**: $5 이하는 정상 (거래 단위, 환율 등에 의한 오차)
5. **조기 감지**: 오차가 누적되기 전에 조기 감지 및 조치

### 오류 처리 핵심 원칙

1. **완전 추적**: 성공/실패 모두 기록
2. **다중 백업**: 정상 저장 → 백업 파일 → 카카오톡
3. **명확한 로깅**: 문제 진단에 필요한 모든 정보 기록
4. **자동 복구**: 가능한 경우 자동 복구 시도
5. **수동 개입**: 불가능한 경우 명확한 가이드 제공
