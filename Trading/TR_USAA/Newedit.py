# ========================================
# 치명적 에러 수정 패치 (간결한 버전)
# ========================================

# ========================================
# 6. ADJUST_RATE 적용 후 검증 (1292-1299라인)
# ========================================
# 기존:
# if FULL_BUYUSD > USD:
#     ADJUST_RATE = USD / FULL_BUYUSD
#     for ticker in USLA_ticker:
#         USLA[ticker]['buy_qty'] = int(USLA[ticker]['buy_qty'] * ADJUST_RATE)

# 수정:
if FULL_BUYUSD > USD:
    ADJUST_RATE = USD / FULL_BUYUSD
    message.append(f"⚠️ 예수금 부족 - 매수 수량 {ADJUST_RATE:.1%}로 조정")
    
    # 조정 적용
    for ticker in USLA_ticker:
        USLA[ticker]['buy_qty'] = int(USLA[ticker]['buy_qty'] * ADJUST_RATE)
    for ticker in HAA_ticker:
        HAA[ticker]['buy_qty'] = int(HAA[ticker]['buy_qty'] * ADJUST_RATE)
    
    # 조정 후 재계산
    adjusted_total = 0
    for ticker in USLA_ticker:
        adjusted_total += USLA[ticker]['buy_qty'] * USLA[ticker]['current_price']
    for ticker in HAA_ticker:
        adjusted_total += HAA[ticker]['buy_qty'] * HAA[ticker]['current_price']
    
    message.append(f"조정 후 필요금액: ${adjusted_total:,.2f} / 예수금: ${USD:,.2f}")
    
    # 안전 마진 체크
    if adjusted_total > USD * 0.99:
        message.append("⚠️ 조정 후에도 예수금 부족 가능성 있음")
else:
    message.append(f"✓ 예수금 충분 (필요: ${FULL_BUYUSD:,.2f} / 보유: ${USD:,.2f})")


# ========================================
# 7. 매수/매도 순서 개선 (1회차만 매도 우선)
# ========================================
# 1회차 (1277-1302라인)
if order_time['round'] == 1:
    # 1회차: 매도 → 대기 → 매수
    Sell_order, sell_messages = Selling(USLA, HAA, sell_split_USLA, sell_split_HAA, order_time)
    message.extend(sell_messages)
    
    # 10초 대기 (매도 주문 전송 시간)
    time_module.sleep(10)
    
    # 예수금 재조회
    USD = KIS.get_US_dollar_balance().get('withdrawable', 0)
    message.append(f"매도 주문 후 예수금: ${USD:,.2f}")
    
    # 매수 수량 조정
    # ... FULL_BUYUSD 계산 및 ADJUST_RATE 적용 ...
    
    Buy_order, buy_messages = Buying(USLA, HAA, buy_split_USLA, buy_split_HAA, order_time)
    message.extend(buy_messages)

# 2-24회차 (1383-1409라인)
else:
    # 2회차부터: 매수 → 매도 (이미 매도 주문 진행 중)
    # 예수금 조정 로직
    # ... FULL_BUYUSD 계산 및 ADJUST_RATE 적용 ...
    
    Buy_order, buy_messages = Buying(USLA, HAA, buy_split_USLA, buy_split_HAA, order_time)
    message.extend(buy_messages)
    
    time_module.sleep(5)
    
    Sell_order, sell_messages = Selling(USLA, HAA, sell_split_USLA, sell_split_HAA, order_time)
    message.extend(sell_messages)





# ========================================
# 전체 수정 요약
# ========================================
"""
6. ADJUST_RATE 검증: 조정 후 재계산 + 메시지
7. 매수/매도 순서: 1회차만 매도 우선
"""