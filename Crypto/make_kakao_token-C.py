import requests
import json
import os

# Kakao token file path
# kakao_token_file_path = "/var/autobot/kakao/kakao_token.json"  # 변경: 실제 경로로 수정
kakao_token_file_path = "C:/Users/GSR\Desktop/Python_project/git_folder/Crypto/kakao_token.json"  # 경로
# Kakao API 정보
url = 'https://kauth.kakao.com/oauth/token'
rest_api_key = '90d41aca9915d7346e1dd4a2596f767f'  # REST API 키
redirect_uri = 'https://localhost:8080'  # 등록된 Redirect URI
authorize_code = 'IAiuiuQCageYEZoXGIiGLlMIpNurqyR0HH0IIcXj6GIDWunI1_8cFwAAAAQKDQ1fAAABl3bStGPGDcCf5rkkeA'  # 인가 코드

Tokens = {}
IsAlreadyGetToken = os.path.exists(kakao_token_file_path)

# 토큰 파일이 존재하면 읽기 시도
if IsAlreadyGetToken:
    try:
        with open(kakao_token_file_path, 'r') as json_file:
            Tokens = json.load(json_file)
            print("✅ 현재 저장된 토큰:", Tokens)
    except Exception as e:
        print(f"❌ 토큰 파일 읽기 오류: {e}")
        IsAlreadyGetToken = False

if IsAlreadyGetToken and "refresh_token" in Tokens:
    print("🔁 리프레시 토큰으로 액세스 토큰 재발급 중...")

    data = {
        "grant_type": "refresh_token",
        "client_id": rest_api_key,
        "refresh_token": Tokens["refresh_token"]
    }

    response = requests.post(url, data=data)

    if response.status_code == 200:
        new_tokens = response.json()
        print("✅ 토큰 재발급 성공:", new_tokens)

        Tokens['access_token'] = new_tokens.get('access_token', '')
        if 'refresh_token' in new_tokens:
            Tokens['refresh_token'] = new_tokens['refresh_token']

        with open(kakao_token_file_path, 'w') as outfile:
            json.dump(Tokens, outfile)
            print("💾 토큰 저장 완료!")
    else:
        print(f"❌ 토큰 재발급 실패! {response.status_code} - {response.text}")

else:
    print("🆕 최초 토큰 발급 중... (인가 코드 사용)")

    data = {
        'grant_type': 'authorization_code',
        'client_id': rest_api_key,
        'redirect_uri': redirect_uri,
        'code': authorize_code,
    }

    response = requests.post(url, data=data)

    if response.status_code == 200:
        tokens = response.json()
        print("✅ 최초 토큰 발급 성공:", tokens)

        with open(kakao_token_file_path, 'w') as outfile:
            json.dump(tokens, outfile)
            print("💾 토큰 저장 완료!")
    else:
        print(f"❌ 최초 토큰 발급 실패! {response.status_code}")
        print("응답 내용:", response.text)
