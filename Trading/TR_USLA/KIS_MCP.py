import asyncio
import httpx
from mcp import ClientSession
from mcp.client.sse import sse_client

async def connect_kis_mcp():
    """Smithery를 통한 KIS MCP 연결"""
    
    # 올바른 Smithery 서버 URL
    url = "https://server.smithery.ai/@KISOpenAPI/kis-code-assistant-mcp/sse"
    url = "https://server.smithery.ai/@KISOpenAPI/kis-code-assistant-mcp/mcp"
    
    headers = {
        "Authorization": "Bearer 4940e847-47f9-4a49-ad99-7f97a2c83648"
    }
    
    print("=== KIS MCP 서버 연결 (HTTP/SSE) ===\n")
    print(f"URL: {url}")
    print("연결 중...\n")
    
    try:
        # SSE 클라이언트로 연결
        async with sse_client(url, headers=headers) as (read, write):
            print("✓ SSE 연결 성공")
            
            async with ClientSession(read, write) as session:
                print("✓ 세션 생성 완료")
                
                # 초기화
                print("세션 초기화 중...")
                init_result = await session.initialize()
                print(f"✓ 초기화 완료")
                print(f"  서버 이름: {init_result.serverInfo.name}")
                print(f"  버전: {init_result.serverInfo.version}")
                
                # 도구 목록 조회
                print("\n도구 목록 조회 중...")
                tools_result = await session.list_tools()
                
                print(f"\n{'='*60}")
                print(f"사용 가능한 도구: {len(tools_result.tools)}개")
                print(f"{'='*60}\n")
                
                for i, tool in enumerate(tools_result.tools, 1):
                    print(f"[{i}] {tool.name}")
                    print(f"    {tool.description}")
                    print()
                
                return session, tools_result
                
    except httpx.HTTPStatusError as e:
        print(f"\n❌ HTTP 오류: {e.response.status_code}")
        print(f"URL: {e.request.url}")
        print(f"응답: {e.response.text}")
        
        if e.response.status_code == 404:
            print("\n가능한 원인:")
            print("1. 잘못된 패키지 이름")
            print("2. Smithery에서 패키지를 찾을 수 없음")
            print("3. API 키가 만료되었거나 잘못됨")
        
    except Exception as e:
        print(f"\n❌ 오류: {type(e).__name__}")
        print(f"메시지: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(connect_kis_mcp())

# from mcp import ClientSession
# from mcp.client.streamable_http import streamablehttp_client

# # Construct server URL with authentication
# from urllib.parse import urlencode
# base_url = "https://server.smithery.ai/@KISOpenAPI/kis-code-assistant-mcp/mcp"
# params = {"api_key": "4940e847-47f9-4a49-ad99-7f97a2c83648"}
# url = f"{base_url}?{urlencode(params)}"

# async def main():
#     # Connect to the server using HTTP client
#     async with streamablehttp_client(url) as (read, write, _):
#         async with ClientSession(read, write) as session:
#             # Initialize the connection
#             await session.initialize()
            
#             # List available tools
#             tools_result = await session.list_tools()
#             print(f"Available tools: {', '.join([t.name for t in tools_result.tools])}")

# if __name__ == "__main__":
#     import asyncio
#     asyncio.run(main())
