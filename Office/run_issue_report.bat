@echo off
REM ============================================================
REM  운영이슈 자동화 - 매일 실행 배치 파일
REM ============================================================

echo === STEP 1: Move to Script Directory ===
cd /d "C:\Users\GSR\Desktop\Code\git_folder\Office"
if errorlevel 1 (
    echo [ERROR] Failed to move directory.
    goto TOGGLE_MODE
)
echo Directory changed successfully.
echo.

echo === STEP 2: Run Python Script ===
REM -u 옵션으로 파이썬 print 출력을 버퍼링 없이 즉시 화면에 뿌립니다.
python -u Issueserching_v3.py

:TOGGLE_MODE
echo.
echo ============================================================
echo === STEP 3: Execution Finished. Choose Window Mode =======
echo ============================================================
REM ------------------------------------------------------------
REM [모드 조절 구역] 원하시는 모드에 따라 아래 두 줄 중 하나만 켜세요.
REM ------------------------------------------------------------

REM [옵션 A] 창 열어두기 모드 (현재 기본값) : 결과를 눈으로 확인한 뒤 아무 키나 눌러 닫습니다.
pause

REM [옵션 B] 자동 종료 모드 : 작업이 끝나면 CMD 창을 남기지 않고 즉시 닫습니다.
REM (나중에 완전히 모니터링이 필요 없어지면 아래 exit 앞의 REM을 지우고, 위의 pause 앞에 REM을 붙이세요)
REM exit /b %errorlevel%