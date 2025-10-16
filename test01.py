import pandas as pd
import numpy as np
from typing import List, Dict
import random
from collections import Counter
import openpyxl
from datetime import datetime

class WorkScheduleGenerator:
    """월간 근무 패턴표 생성 클래스"""
    
    def __init__(self, num_workers=17, tolerance=2):
        """
        Parameters:
        -----------
        num_workers : int
            근무자 수 (기본값: 17명)
        tolerance : int
            개인별 근무형태별 허용 오차 범위 (기본값: 2)
        """
        self.num_workers = num_workers
        self.tolerance = tolerance
        
        # 근무 유형 및 월별 필요 인원
        self.shift_types = {
            '제작아침': 2,
            '제작주간': 1,
            '제작야간': 2,
            '진행아침': 3,
            '진행주간': 3,
            '진행야간': 3,
            '데이터': 3
        }
        
        # 로테이션 순서 (우선순위)
        self.rotation_order = [
            '진행아침',  # 1
            '진행야간',  # 2
            '진행주간',  # 3
            '제작아침',  # 4
            '제작야간',  # 5
            '제작주간',  # 6 (데이터와 교체 가능)
            '데이터'     # 6
        ]
        
        self.months = [f'{i}월' for i in range(1, 13)]
        self.worker_names = [f'근무자{i}' for i in range(1, num_workers + 1)]
        
    def calculate_annual_target(self) -> Dict[str, int]:
        """연간 각 근무형태별 목표 횟수 계산"""
        total_shifts_per_year = {}
        for shift_type, monthly_count in self.shift_types.items():
            total_shifts_per_year[shift_type] = monthly_count * 12
        
        return total_shifts_per_year
    
    def initialize_schedule(self) -> pd.DataFrame:
        """초기 스케줄 DataFrame 생성"""
        schedule = pd.DataFrame(
            index=self.worker_names,
            columns=self.months
        )
        return schedule
    
    def get_next_shift(self, current_shift: str, variant: int = 0) -> str:
        """현재 근무에서 다음 근무 결정 (로테이션 순서 기반)"""
        try:
            current_idx = self.rotation_order.index(current_shift)
        except ValueError:
            current_idx = 0
        
        # 제작주간과 데이터는 같은 순서(6)로 취급하여 교체 가능
        if current_shift in ['제작주간', '데이터']:
            # 변형을 주기 위해 다음 근무를 다르게 선택
            if random.random() < 0.3:  # 30% 확률로 패턴 변경
                next_idx = random.randint(0, len(self.rotation_order) - 1)
            else:
                next_idx = (current_idx + 1 + variant) % len(self.rotation_order)
        else:
            next_idx = (current_idx + 1 + variant) % len(self.rotation_order)
        
        return self.rotation_order[next_idx]
    
    def generate_schedule(self, pattern_variant: int = 0) -> pd.DataFrame:
        """근무 패턴 생성 (pattern_variant로 다양성 부여)"""
        schedule = self.initialize_schedule()
        
        # 각 근무자별 연간 근무 카운트 추적
        worker_shift_counts = {
            worker: {shift: 0 for shift in self.shift_types.keys()}
            for worker in self.worker_names
        }
        
        # 월별 근무 할당
        for month_idx, month in enumerate(self.months):
            # 이번 달에 필요한 근무 타입별 인원 수
            month_needs = self.shift_types.copy()
            available_workers = self.worker_names.copy()
            
            # 랜덤 섞기로 다양성 부여
            random.shuffle(available_workers)
            
            for worker in available_workers:
                if all(need == 0 for need in month_needs.values()):
                    break
                
                # 이전 달 근무 확인
                if month_idx > 0:
                    prev_shift = schedule.loc[worker, self.months[month_idx - 1]]
                    # 로테이션 순서에 따라 다음 근무 제안
                    suggested_shift = self.get_next_shift(prev_shift, pattern_variant)
                else:
                    # 첫 달은 로테이션 순서대로 할당
                    worker_idx = self.worker_names.index(worker)
                    suggested_shift = self.rotation_order[worker_idx % len(self.rotation_order)]
                
                # 제안된 근무가 필요하고 할당 가능한지 확인
                if month_needs.get(suggested_shift, 0) > 0:
                    assigned_shift = suggested_shift
                else:
                    # 필요한 근무 중 선택
                    available_shifts = [
                        shift for shift, need in month_needs.items() 
                        if need > 0
                    ]
                    if available_shifts:
                        # 해당 근무자가 연간으로 적게 한 근무 우선 배정
                        assigned_shift = min(
                            available_shifts,
                            key=lambda s: worker_shift_counts[worker][s]
                        )
                    else:
                        continue
                
                # 근무 할당
                schedule.loc[worker, month] = assigned_shift
                month_needs[assigned_shift] -= 1
                worker_shift_counts[worker][assigned_shift] += 1
        
        return schedule, worker_shift_counts
    
    def calculate_statistics(self, schedule: pd.DataFrame) -> pd.DataFrame:
        """통계 계산 (개인별 연간 근무 횟수)"""
        stats_df = pd.DataFrame(
            index=self.worker_names,
            columns=list(self.shift_types.keys()) + ['제작', '데이터', '진행']
        )
        
        for worker in self.worker_names:
            worker_schedule = schedule.loc[worker]
            shift_counts = Counter(worker_schedule)
            
            for shift_type in self.shift_types.keys():
                stats_df.loc[worker, shift_type] = shift_counts.get(shift_type, 0)
            
            # 카테고리별 합계
            stats_df.loc[worker, '제작'] = sum([
                shift_counts.get('제작아침', 0),
                shift_counts.get('제작주간', 0),
                shift_counts.get('제작야간', 0)
            ])
            stats_df.loc[worker, '데이터'] = shift_counts.get('데이터', 0)
            stats_df.loc[worker, '진행'] = sum([
                shift_counts.get('진행아침', 0),
                shift_counts.get('진행주간', 0),
                shift_counts.get('진행야간', 0)
            ])
        
        return stats_df
    
    def calculate_monthly_totals(self, schedule: pd.DataFrame) -> pd.DataFrame:
        """월별 카테고리별 인원 합계"""
        monthly_totals = pd.DataFrame(
            index=['제작', '진행', '데이터'],
            columns=self.months
        )
        
        for month in self.months:
            month_shifts = schedule[month]
            shift_counts = Counter(month_shifts)
            
            monthly_totals.loc['제작', month] = sum([
                shift_counts.get('제작아침', 0),
                shift_counts.get('제작주간', 0),
                shift_counts.get('제작야간', 0)
            ])
            monthly_totals.loc['진행', month] = sum([
                shift_counts.get('진행아침', 0),
                shift_counts.get('진행주간', 0),
                shift_counts.get('진행야간', 0)
            ])
            monthly_totals.loc['데이터', month] = shift_counts.get('데이터', 0)
        
        return monthly_totals
    
    def create_full_report(self, schedule: pd.DataFrame, stats: pd.DataFrame) -> pd.DataFrame:
        """전체 보고서 생성 (스케줄 + 통계)"""
        # 스케줄과 통계 병합
        full_report = pd.concat([schedule, stats], axis=1)
        
        # 월별 합계 추가
        monthly_totals = self.calculate_monthly_totals(schedule)
        
        # 월별 합계를 DataFrame 하단에 추가
        for category in ['제작', '진행', '데이터']:
            row_data = list(monthly_totals.loc[category]) + [''] * len(stats.columns)
            full_report.loc[category] = row_data
        
        return full_report
    
    def generate_multiple_patterns(self, num_patterns: int = 5) -> List[pd.DataFrame]:
        """여러 패턴의 근무표 생성"""
        patterns = []
        
        for i in range(num_patterns):
            print(f"\n패턴 {i+1} 생성 중...")
            schedule, worker_counts = self.generate_schedule(pattern_variant=i)
            stats = self.calculate_statistics(schedule)
            full_report = self.create_full_report(schedule, stats)
            patterns.append(full_report)
            
            # 형평성 체크
            self.check_fairness(worker_counts)
        
        return patterns
    
    def check_fairness(self, worker_shift_counts: Dict):
        """형평성 체크 - 개인별 근무 횟수 편차 확인"""
        print("\n=== 형평성 분석 ===")
        
        for shift_type in self.shift_types.keys():
            counts = [worker_shift_counts[w][shift_type] for w in self.worker_names]
            min_count = min(counts)
            max_count = max(counts)
            diff = max_count - min_count
            
            status = "✓" if diff <= self.tolerance else "✗"
            print(f"{shift_type}: 최소 {min_count}회, 최대 {max_count}회 (편차: {diff}) {status}")
    
    def export_to_excel(self, patterns: List[pd.DataFrame], filename: str = "근무패턴표.xlsx"):
        """Excel 파일로 저장"""
        filename = f"{filename}, {datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            for i, pattern in enumerate(patterns):
                sheet_name = f'패턴{i+1}'
                pattern.to_excel(writer, sheet_name=sheet_name)
        
        print(f"\n{filename} 파일이 생성되었습니다.")


# 사용 예시
if __name__ == "__main__":
    # 오차 범위를 사용자 입력으로 받기
    tolerance_input = input("근무 오차 범위를 입력하세요 (기본값: 2): ").strip()
    tolerance = int(tolerance_input) if tolerance_input else 2
    
    # 생성할 패턴 수 입력
    num_patterns_input = input("생성할 패턴 수를 입력하세요 (기본값: 5): ").strip()
    num_patterns = int(num_patterns_input) if num_patterns_input else 5
    
    # 근무표 생성기 초기화
    generator = WorkScheduleGenerator(num_workers=17, tolerance=tolerance)
    
    # 여러 패턴 생성
    patterns = generator.generate_multiple_patterns(num_patterns=num_patterns)
    
    # Excel 파일로 저장
    generator.export_to_excel(patterns, "근무패턴표_다양한버전")
    
    # 첫 번째 패턴 미리보기
    print("\n=== 첫 번째 패턴 미리보기 ===")
    print(patterns[0].head(20))