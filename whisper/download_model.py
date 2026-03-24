import ssl
import os

# SSL 검증 비활성화
ssl._create_default_https_context = ssl._create_unverified_context
os.environ["CURL_CA_BUNDLE"] = ""
os.environ["REQUESTS_CA_BUNDLE"] = ""

from huggingface_hub import snapshot_download

print("모델 다운로드 시작... (약 500MB, 시간 소요)")

snapshot_download(
    repo_id="guillaumekln/faster-whisper-small",
    local_dir="C:/Users/GSR/Desktop/Code/whisper-small",  # 저장 경로
    ignore_patterns=["*.msgpack", "*.h5"],
)

print("✅ 다운로드 완료!")