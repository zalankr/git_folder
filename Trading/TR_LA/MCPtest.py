import asyncio
import subprocess
import os
import shutil

async def test_mcp_server():
    """MCP 서버를 직접 실행하고 출력 확인"""
    
    env = os.environ.copy()
    env["SMITHERY_API_KEY"] = "4940e847-47f9-4a49-ad99-7f97a2c83648"
    
    print("=== MCP 서버 직접 실행 테스트 ===\n")
    
    # npx 경로 찾기
    npx_paths = [
        "npx",  # PATH에 있는 경우
        "npx.cmd",  # Windows CMD
        r"C:\Program Files\nodejs\npx.cmd",
        r"C:\Program Files (x86)\nodejs\npx.cmd",
    ]
    
    # APPDATA 경로도 추가
    appdata = os.environ.get('APPDATA', '')
    if appdata:
        npx_paths.append(os.path.join(appdata, 'npm', 'npx.cmd'))
    
    npx_cmd = None
    for path in npx_paths:
        if os.path.exists(path) if os.path.isabs(path) else shutil.which(path):
            npx_cmd = path
            print(f"✓ npx 찾음: {path}\n")
            break
    
    if not npx_cmd:
        print("❌ npx를 찾을 수 없습니다!\n")
        print("Node.js 설치 방법:")
        print("1. https://nodejs.org/ 접속")
        print("2. LTS 버전 다운로드 (왼쪽 버튼)")
        print("3. 설치 후 컴퓨터 재시작")
        print("\n설치 확인:")
        print("  명령 프롬프트에서 'node --version' 실행")
        return

    try:
        # 서버 프로세스 시작
        process = subprocess.Popen(
            [npx_cmd, "-y", "@KISOpenAPI/kis-code-assistant-mcp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            bufsize=1,
            shell=True  # Windows에서 .cmd 파일 실행
        )
        
        print(f"서버 PID: {process.pid}")
        print("서버 시작 중... (5초 대기)\n")
        
        # 5초 동안 출력 확인
        try:
            stdout, stderr = process.communicate(timeout=5)
            print("=== STDOUT ===")
            print(stdout if stdout else "(출력 없음)")
            print("\n=== STDERR ===")
            print(stderr if stderr else "(오류 없음)")
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            print("=== STDOUT (타임아웃 후) ===")
            print(stdout if stdout else "(출력 없음)")
            print("\n=== STDERR (타임아웃 후) ===")
            print(stderr if stderr else "(오류 없음)")
            
    except Exception as e:
        print(f"❌ 오류: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_mcp_server())