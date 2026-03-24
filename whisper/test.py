from faster_whisper import WhisperModel
import sounddevice as sd
import numpy as np
import queue
import threading

# ── 설정 ──────────────────────────────────────
MODEL_SIZE = "small"       # tiny / base / small / medium
LANGUAGE = "ko"            # 한국어
SAMPLE_RATE = 16000
CHUNK_DURATION = 3         # 몇 초마다 인식할지
# ─────────────────────────────────────────────

print("모델 로딩 중... (처음 실행 시 다운로드로 1~2분 소요)")
model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
print("모델 로딩 완료!\n")

audio_queue = queue.Queue()

def audio_callback(indata, frames, time, status):
    """마이크 입력을 큐에 저장"""
    if status:
        print(f"[마이크 상태]: {status}")
    audio_queue.put(indata.copy())

def transcribe_loop():
    """큐에서 오디오를 꺼내 텍스트 변환"""
    buffer = np.array([], dtype=np.float32)

    while True:
        chunk = audio_queue.get()
        buffer = np.append(buffer, chunk.flatten())

        # CHUNK_DURATION초 분량이 쌓이면 인식
        if len(buffer) >= SAMPLE_RATE * CHUNK_DURATION:
            audio_data = buffer[:SAMPLE_RATE * CHUNK_DURATION].copy()
            buffer = buffer[SAMPLE_RATE * CHUNK_DURATION:]

            segments, info = model.transcribe(
                audio_data,
                language=LANGUAGE,
                beam_size=5
            )

            text = "".join([seg.text for seg in segments]).strip()
            if text:  # 빈 결과는 출력 안 함
                print(f"📝 {text}")

# 백그라운드 스레드로 인식 실행
t = threading.Thread(target=transcribe_loop, daemon=True)
t.start()

# 마이크 스트림 시작
print("🎤 실시간 음성 인식 중... (Enter 키로 종료)\n")
with sd.InputStream(
    samplerate=SAMPLE_RATE,
    channels=1,
    dtype='float32',
    callback=audio_callback
):
    input()  # Enter 누를 때까지 대기

print("종료되었습니다.")