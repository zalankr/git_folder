# -*- coding: utf-8 -*-
"""
KRFT_kakao.py
=============
카카오톡 알림 전송 (증거금 부족 시에만 사용).
- 호출 시점에 토큰 자동 갱신 (refresh_token 사용)
- 실패 시 텔레그램으로 fallback

설정 파일:
  /var/autobot/kakao/kakao_token.json
    {
      "access_token":  "...",
      "refresh_token": "...",
      "issued_at":     "2026-05-14T15:00:00"  # 토큰 발급 시점 (선택)
    }
  /var/autobot/kakao/kakao_app.json
    {
      "rest_api_key": "90d41aca...."
    }
"""
from __future__ import annotations
import json
import os
import requests
from datetime import datetime
from pathlib import Path

KAKAO_DIR        = "/var/autobot/kakao"
KAKAO_TOKEN_PATH = os.path.join(KAKAO_DIR, "kakao_token.json")
KAKAO_APP_PATH   = os.path.join(KAKAO_DIR, "kakao_app.json")

TOKEN_URL = "https://kauth.kakao.com/oauth/token"
MEMO_URL  = "https://kapi.kakao.com/v2/api/talk/memo/default/send"


def _load_token() -> dict:
    if not os.path.exists(KAKAO_TOKEN_PATH):
        raise FileNotFoundError(f"카카오 토큰 파일 없음: {KAKAO_TOKEN_PATH}")
    with open(KAKAO_TOKEN_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_token(tok: dict) -> None:
    Path(KAKAO_DIR).mkdir(parents=True, exist_ok=True)
    with open(KAKAO_TOKEN_PATH, "w", encoding="utf-8") as f:
        json.dump(tok, f, ensure_ascii=False, indent=2)


def _load_app_key() -> str:
    if not os.path.exists(KAKAO_APP_PATH):
        raise FileNotFoundError(f"카카오 앱키 파일 없음: {KAKAO_APP_PATH}")
    with open(KAKAO_APP_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["rest_api_key"]


def refresh_access_token() -> str:
    """refresh_token으로 access_token 신규 발급. 갱신된 토큰을 파일에 저장 후 반환."""
    tok = _load_token()
    rest_api_key = _load_app_key()

    data = {
        "grant_type":    "refresh_token",
        "client_id":     rest_api_key,
        "refresh_token": tok["refresh_token"],
    }
    r = requests.post(TOKEN_URL, data=data, timeout=10)
    if r.status_code != 200:
        raise RuntimeError(f"카카오 토큰 갱신 실패 {r.status_code}: {r.text}")

    new_tok = r.json()
    tok["access_token"] = new_tok.get("access_token", tok.get("access_token"))
    # refresh_token은 만료 임박일 때만 갱신해 응답에 포함됨
    if "refresh_token" in new_tok:
        tok["refresh_token"] = new_tok["refresh_token"]
    tok["issued_at"] = datetime.now().isoformat(timespec="seconds")
    _save_token(tok)
    return tok["access_token"]


def send_kakao_to_self(message: str) -> bool:
    """
    '나에게 보내기' API로 텍스트 메시지 전송.
    반드시 호출 직전에 토큰을 신규 발급(refresh)한다 (요구사항 16번).
    """
    try:
        access_token = refresh_access_token()
    except Exception as e:
        print(f"[KAKAO] 토큰 갱신 실패: {e}")
        return False

    headers = {"Authorization": f"Bearer {access_token}"}
    template = {
        "object_type": "text",
        "text":        message,
        "link":        {"web_url": "https://www.koreainvestment.com",
                        "mobile_web_url": "https://www.koreainvestment.com"},
        "button_title": "확인",
    }
    data = {"template_object": json.dumps(template, ensure_ascii=False)}
    try:
        r = requests.post(MEMO_URL, headers=headers, data=data, timeout=10)
        if r.status_code == 200 and r.json().get("result_code") == 0:
            return True
        print(f"[KAKAO] 전송 실패 {r.status_code}: {r.text}")
        return False
    except Exception as e:
        print(f"[KAKAO] 전송 예외: {e}")
        return False


if __name__ == "__main__":
    import sys
    msg = sys.argv[1] if len(sys.argv) > 1 else "[KRFT] 카카오 테스트 메시지"
    ok = send_kakao_to_self(msg)
    print("전송 성공" if ok else "전송 실패")
