# USLA 자동매매 개선 핵심 요약 (1페이지)

## 🎯 개선 목표
한 계좌에서 여러 전략이 USD 예수금을 나눠 쓰는 구조에서
**JSON 기반 예수금 추적의 정확성과 안정성 강화**

---

## 📊 시스템 구조

```
KIS 계좌 (실제 USD: $10,000)
├─ USLA 전략: $3,000 ← USLA_data.json으로 관리
├─ 전략2: $4,000
└─ 전략3: $3,000

→ 실제 API 예수금과 비교 불가
→ JSON 내부 일관성 검증 필수
```

---

## 🔧 핵심 개선 사항 (3가지)

### 1. 주문 실패 추적
```python
# 변경 전: 실패 주문 미기록
if result.get('success') == True:
    Sell_order.append(order_info)

# 변경 후: 모든 주문 기록
if result.get('success') == True:
    Sell_order.append({...})
else:
    Sell_order.append({'success': False, 'error_message': ...})
```

### 2. USD 내부 일관성 검증 ⭐
```python
# 공식: 이전 USD + 매도액 - 매수액 = 현재 USD

def validate_usd_consistency(prev_usd, sell_amount, buy_amount, current_usd, tolerance=5.0):
    expected_usd = prev_usd + sell_amount - buy_amount
    diff = abs(current_usd - expected_usd)
    
    if diff > tolerance:
        KA.SendMessage(f"⚠️ USD 불일치: 예상 ${expected_usd} vs 실제 ${current_usd}")
```

**적용 위치:**
- Round 2~24: 매 라운드 체결 후 검증 (tolerance=$5)
- Round 25: 최종 검증 (tolerance=$10)

### 3. 데이터 저장 백업 (3중)
```python
try:
    # 1차: 정상 저장
    USLA.save_USLA_TR_json(TR_data)
except:
    try:
        # 2차: 백업 파일
        with open(backup_path, 'w') as f:
            json.dump(TR_data, f)
    except:
        # 3차: 카카오톡
        KA.SendMessage(f"TR 요약: {summary}")
```

---

## ⚡ 주요 변경 코드 위치

| 파일 | 함수/위치 | 변경 내용 |
|------|-----------|----------|
| USLA_Trading.py | Selling() | 실패 주문도 Sell_order에 추가 |
| USLA_Trading.py | Buying() | 실패 주문도 Buy_order에 추가 |
| USLA_Trading.py | Round 2~25 | validate_usd_consistency() 호출 |
| USLA_Trading.py | save_TR_data() | 3중 백업 메커니즘 |
| USLA_Trading.py | Round 2~25 | 성공한 주문만 필터링하여 체결 확인 |
| USLA_model.py | calculate_sell_summary() | 상세 로깅 및 티커별 집계 |
| USLA_model.py | calculate_buy_summary() | 상세 로깅 및 티커별 집계 |

---

## 🚀 배포 절차 (3단계)

### 1. 백업
```bash
cd /var/autobot/TR_USLA
cp USLA_Trading.py USLA_Trading_backup_$(date +%Y%m%d).py
cp USLA_data.json USLA_data_backup_$(date +%Y%m%d).json
cp USLA_TR.json USLA_TR_backup_$(date +%Y%m%d).json
```

### 2. 배포
```bash
cp USLA_Trading_fixed.py /var/autobot/TR_USLA/USLA_Trading.py
```

### 3. 검증
- 드라이런 테스트
- 소액 실거래 테스트
- **USD 검증 통과 확인** ⭐

---

## 📊 모니터링 포인트

### 주문 성공률
- **정상**: 90% 이상
- **주의**: 80~90%
- **경고**: 80% 미만

### USD 검증 오차
- **정상**: $0~$2
- **주의**: $2~$5
- **경고**: $5 초과 (검증 실패)

### 체결률
- **정상**: 95% 이상
- **주의**: 90~95%
- **경고**: 90% 미만

---

## 🚨 긴급 대응 (3대 시나리오)

### 1. USD 검증 실패
```bash
# 로그 확인
grep "USD 불일치" /var/log/autobot/USLA.log

# 수동 보정
vi /var/autobot/TR_USLA/USLA_TR.json
# CASH 값을 정확한 값으로 수정

# 허용 오차 조정 (필요시)
# tolerance=5.0 → tolerance=10.0
```

### 2. TR 저장 실패
```bash
# 백업 파일 확인
ls -lt /var/autobot/TR_USLA/USLA_TR_backup_*

# 최신 백업 복사
cp USLA_TR_backup_YYYYMMDD_HHMMSS.json USLA_TR.json
```

### 3. USD 예수금 음수
```bash
# 즉시 중단
killall python3

# USLA_data.json 수정
vi /var/autobot/TR_USLA/USLA_data.json
# "CASH": 정확한값

# 다음 리밸런싱일부터 재시작
```

---

## ✅ 체크리스트

### 배포 전
- [ ] 기존 파일 백업
- [ ] 개선 코드 배포
- [ ] health_check 실행

### 첫 리밸런싱일
- [ ] Round 1 초기 USD 로깅 확인
- [ ] Round 2~24 USD 검증 통과 확인
- [ ] Round 25 최종 검증 통과 확인
- [ ] 주문 성공률 90% 이상 확인

### 정기 점검
- [ ] 주간 USD 오차 추이 분석
- [ ] 월간 주문 성공률 통계
- [ ] 분기별 전략 성과 분석

---

## 📞 문의 및 지원

### 로그 확인
```bash
# 전체 로그
tail -f /var/log/autobot/USLA.log

# USD 검증 관련
grep "USD 검증" /var/log/autobot/USLA.log

# 오류 관련
grep "실패\|오류\|Exception" /var/log/autobot/USLA.log
```

### 핵심 파일
- `/var/autobot/TR_USLA/USLA_Trading.py` - 메인 거래 로직
- `/var/autobot/TR_USLA/USLA_data.json` - 전략 잔고 데이터
- `/var/autobot/TR_USLA/USLA_TR.json` - 라운드별 거래 데이터

---

## 💡 핵심 원칙

1. **분리 관리**: 전략별 USD는 JSON으로 독립 관리
2. **일관성 검증**: 라운드 간 USD 변화 = 체결 금액
3. **완전 추적**: 성공/실패 모든 주문 기록
4. **다중 백업**: 저장 실패 시 자동 백업
5. **조기 감지**: 오차 누적 전 조기 발견

---

## 📚 상세 문서

- **USLA_Trading_fixed.py**: 개선된 메인 코드
- **USLA_개선_보고서_최종.md**: 상세 개선 보고서 (19KB)
- **USLA_핵심_체크리스트_최종.md**: 상세 체크리스트 (16KB)
- **USLA_model_improved_functions.py**: 개선된 체결 확인 함수

모든 파일은 `/mnt/user-data/outputs/` 에서 다운로드 가능

---

**배포 권장 사항**: 반드시 백업 후 배포, 테스트 환경에서 먼저 검증 권장
