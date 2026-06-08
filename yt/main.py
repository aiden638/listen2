"""
YT Music Player — FastAPI 서버
- POST /play   {"title": "...", "artist": "..."} → mpv 백그라운드 재생
- POST /stop   → 재생 중지
- GET  /status → 현재 상태
"""

import os
import subprocess
import threading
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="YT Music Player")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 전역 상태 ──────────────────────────────────
_proc: subprocess.Popen | None = None
_lock = threading.Lock()

state = {
    "status": "idle",   # idle | searching | playing | stopped | error
    "title": None,
    "artist": None,
    "youtube_url": None,
    "error": None,
}


# ── 스키마 ─────────────────────────────────────
class PlayRequest(BaseModel):
    title: str
    artist: str


# ── 내부 함수 ──────────────────────────────────
def _run(title: str, artist: str):
    global _proc

    query = f"{title} {artist}"
    state.update(status="searching", title=title, artist=artist,
                 youtube_url=None, error=None)

    try:
        # 1) yt-dlp로 YouTube 검색 → 스트림 URL 획득
        result = subprocess.run(
            [
                "yt-dlp",
                f"ytsearch1:{query}",
                "--get-url",
                "--format", "bestaudio/best",
                "--no-playlist",
                "--quiet",
            ],
            capture_output=True, text=True, timeout=30,
        )
        url = result.stdout.strip().splitlines()[0] if result.stdout.strip() else None
        if not url:
            raise RuntimeError(f"YouTube 검색 실패: {result.stderr.strip()}")

        state["youtube_url"] = url
        state["status"] = "playing"

        # 2) 기존 mpv 종료
        with _lock:
            if _proc and _proc.poll() is None:
                _proc.terminate()
                _proc.wait(timeout=5)

        # 3) mpv 실행 (오디오만, 화면 없음, 백그라운드)
        proc = subprocess.Popen(
            ["mpv", "--no-video", "--really-quiet", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        with _lock:
            _proc = proc

        proc.wait()  # 재생 완료 대기

        if state["status"] == "playing":
            state["status"] = "idle"

    except Exception as e:
        state["status"] = "error"
        state["error"] = str(e)


# ── 엔드포인트 ─────────────────────────────────
@app.post("/play")
async def play(req: PlayRequest):
    """제목 + 아티스트 → yt-dlp 검색 → mpv 백그라운드 재생"""
    t = threading.Thread(target=_run, args=(req.title, req.artist), daemon=True)
    t.start()
    return {"status": "started", "title": req.title, "artist": req.artist}


@app.post("/stop")
async def stop():
    """재생 중지"""
    global _proc
    with _lock:
        if _proc and _proc.poll() is None:
            _proc.terminate()
            _proc.wait(timeout=5)
            state["status"] = "stopped"
            return {"status": "stopped"}
    return {"status": "already_idle"}


@app.get("/status")
async def status():
    """현재 재생 상태"""
    return state


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
