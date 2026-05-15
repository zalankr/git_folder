# -*- coding: utf-8 -*-
"""
kakao_token_refresh.py
======================
카카오 토큰을 주기적으로 갱신하는 cron 스크립트.

동작:
  1. /var/autobot/kakao/kakao_token.json 의 refresh_token 으로 access_token 신규 발급
  2. 응답에 새 refresh_token이 포함되면 (만료 임박 시 갱신) 같이 저장
  3. 실패 시 → 텔레그램으로 강력 경고 송신 ("인가 코드 재발급 필요")

크론타브:
    0 9 1 * * /usr/bin/python3 /var/autobot/TR_KRFT/kakao_token_refresh.py >> /var/autobot/Logs/kakao_refresh.log 2>&1

수동 갱신 (필요 시):
    python3 /var/autobot/TR_KRFT/kakao_token_refresh.py

인가 코드 재발급이 필요할 때 (refresh_token 자체 만료):
    1) 브라우저로 다음 URL 접속 → 동의 → 리다이렉트된 URL의 code= 뒤 문자열 복사:
       https://kauth.kakao.com/oauth/authorize?response_type=code&client_id=APPKEY&redirect_uri=https://localhost:8080&scope=talk_message
    2) /var/autobot/kakao/make_kakao_token.py 의 authorize_code 변경 + 실행
    3) 토큰 파일 삭제 후 위 스크립트 실행 (rm /var/autobot/kakao/kakao_token.json)
"""
import json
import os
import sys
import requests
from datetime import datetime
from pathlib import Path

TOKEN_PATH = "/var/autobot/kakao/kakao_token.json"
APP_PATH   = "/var/autobot/kakao/kakao_app.json"
TOKEN_URL  = "https://kauth.kakao.com/oauth/token"

sys.path.insert(0, "/var/autobot")
import telegram_alert as TA


def _alert_on_failure(msg: str) -> None:
    """텔레그램으로 강력 경고"""
    full_msg = (
        "🚨 [KRFT 카카오 토큰 갱신 실패]\n"
        f"{msg}\n\n"
        "조치: 인가 코드 재발급 필요\n"
        "1) 브라우저: https://kauth.kakao.com/oauth/authorize"
        "?response_type=code&client_id=90d41aca9915d7346e1dd4a2596f767f"
        "&redirect_uri=https://localhost:8080&scope=talk_message\n"
        "2) 리다이렉트 URL의 code= 뒤 문자열 복사\n"
        "3) /var/autobot/kakao/make_kakao_token.py 의 authorize_code 교체\n"
        "4) rm /var/autobot/kakao/kakao_token.json && python3 make_kakao_token.py"
    )
    print(full_msg)
    try:
        TA.send_tele(full_msg)
    except Exception as e:
        print(f"  텔레그램 송신도 실패: {e}")


def main() -> int:
    print(f"=== 카카오 토큰 갱신: {datetime.now().isoformat(timespec='seconds')} ===")

    # 1) 파일 확인
    if not os.path.exists(TOKEN_PATH):
        _alert_on_failure(f"토큰 파일 없음: {TOKEN_PATH}")
        return 2
    if not os.path.exists(APP_PATH):
        _alert_on_failure(f"앱키 파일 없음: {APP_PATH}")
        return 2

    with open(TOKEN_PATH, "r", encoding="utf-8") as f:
        tok = json.load(f)
    with open(APP_PATH, "r", encoding="utf-8") as f:
        rest_api_key = json.load(f)["rest_api_key"]

    refresh_token = tok.get("refresh_token")
    if not refresh_token:
        _alert_on_failure("refresh_token 필드 없음")
        return 2

    # 2) 갱신 요청
    data = {
        "grant_type":    "refresh_token",
        "client_id":     rest_api_key,
        "refresh_token": refresh_token,
    }
    try:
        r = requests.post(TOKEN_URL, data=data, timeout=10)
    except requests.RequestException as e:
        _alert_on_failure(f"HTTP 오류: {e}")
        return 3

    if r.status_code != 200:
        try:
            body = r.json()
        except Exception:
            body = r.text
        _alert_on_failure(
            f"HTTP {r.status_code}: {body}\n"
            f"(KOE322=refresh_token 만료, KOE320=잘못된 grant 등)"
        )
        return 4

    new_tok = r.json()
    tok["access_token"] = new_tok.get("access_token", tok.get("access_token"))
    if "refresh_token" in new_tok:
        old_rt = tok["refresh_token"]
        tok["refresh_token"] = new_tok["refresh_token"]
        print(f"  ✓ refresh_token 자체도 갱신됨 (만료 임박이었음)")
    tok["issued_at"] = datetime.now().isoformat(timespec="seconds")
    tok["expires_in"] = new_tok.get("expires_in", tok.get("expires_in"))

    # 3) 저장 (atomic)
    Path(TOKEN_PATH).parent.mkdir(parents=True, exist_ok=True)
    tmp = TOKEN_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(tok, f, ensure_ascii=False, indent=2)
    os.replace(tmp, TOKEN_PATH)

    print(f"  ✓ access_token 갱신 완료 (issued_at={tok['issued_at']})")
    print(f"  ✓ expires_in={tok['expires_in']}초")
    return 0


if __name__ == "__main__":
    sys.exit(main())
