from __future__ import annotations  # ← 이 줄 추가
import time
import requests
import sys

# telegram 로드
key_file_path = "/var/autobot/telegram/telegram_TRbot.txt"
try:
    with open(key_file_path) as f:
        BOT_TOKEN, CHAT_ID = [line.strip() for line in f.readlines()]
except Exception as e:
    print("Exception", e)
    sys.exit(1)

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
MAX_CHARS = 4096

def send_tele(
    message: str | list[str],
    chat_id: str = CHAT_ID,
    parse_mode: str = "HTML",
    interval: float = 1.1,
    max_retries: int = 3,
) -> None:
    """
    텔레그램 메시지 전송 (rate limit + 4096자 제한 자동 처리)

    Args:
        message : 단일 문자열 또는 문자열 리스트 (리스트는 줄바꿈 결합)
        chat_id : 텔레그램 채팅 ID
        parse_mode: HTML / Markdown / MarkdownV2
        interval : 청크 간 전송 간격 (초) — 동일 채팅 1msg/초 제한 준수
        max_retries: 429 수신 시 최대 재시도 횟수
    """
    # 1. 리스트 → 줄바꿈 결합
    full_text = "\n".join(message) if isinstance(message, list) else message
    
    # 2. 4096자 기준 줄 단위 청크 분할
    chunks, current = [], ""
    for line in full_text.splitlines(keepends=True):
        if len(line) > MAX_CHARS:                          # 단일 줄 초과 시 강제 슬라이싱
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(line[i:i + MAX_CHARS] for i in range(0, len(line), MAX_CHARS))
        elif len(current) + len(line) > MAX_CHARS:         # 청크 초과 시 확정 후 새 청크
            chunks.append(current)
            current = line
        else:
            current += line
    if current:
        chunks.append(current)

    # 3. 순차 전송 (rate limit 준수 + 429 자동 재시도)
    url = f"{BASE_URL}/sendMessage"
    for i, chunk in enumerate(chunks):
        for attempt in range(max_retries):
            resp = requests.post(url, json={"chat_id": chat_id, "text": chunk, "parse_mode": parse_mode}, timeout=10)
            if resp.status_code == 200:
                break
            if resp.status_code == 429:
                wait = resp.json().get("parameters", {}).get("retry_after", 5) + 1
                print(f"[Rate Limit] {wait}초 대기 ({attempt + 1}/{max_retries})...")
                time.sleep(wait)
            else:
                resp.raise_for_status()
        else:
            raise RuntimeError(f"청크 {i + 1} 전송 실패: {max_retries}회 재시도 초과")

        if i < len(chunks) - 1:
            time.sleep(interval)