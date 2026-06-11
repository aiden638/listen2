"""동적 대화 상태(JSON)를 다루는 유일한 모듈 — 단기기억 / 장기기억 / 재생상태.

설계 문서: backend/DESIGN.md

- short_term.json : 최근 채팅 메시지 버퍼 (TTL/개수로 자동 evict)
- long_term.json  : 방송 상황 맥락 (stream_context 리스트, 축적)
- playback.json   : 현재/다음 곡 재생 상태 (자동 DJ)

정적 페르소나/예시(txt)는 prompts/ 에 두고, 여기서는 '계속 바뀌는' 상태만 다룬다.
state/ 의 JSON 파일은 없으면 자동 생성된다(기본 구조로).
"""
import os
import json
import time
import threading

# /ingest(이벤트 루프)와 채팅/음악 tick(워커 스레드)이 동시에 state 파일을 건드리므로
# 모든 읽기-수정-쓰기를 이 락으로 직렬화한다.
_lock = threading.RLock()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(BASE_DIR, "state")
os.makedirs(STATE_DIR, exist_ok=True)

SHORT_TERM_PATH = os.path.join(STATE_DIR, "short_term.json")
LONG_TERM_PATH = os.path.join(STATE_DIR, "long_term.json")
PLAYBACK_PATH = os.path.join(STATE_DIR, "playback.json")

DEFAULTS = {
    SHORT_TERM_PATH: {"messages": [], "current_mood": [], "last_response_ts": 0},
    LONG_TERM_PATH: {"stream_context": [], "updated_at": 0},
    PLAYBACK_PATH: {"now_playing": None, "next": None, "history": []},
}


def now_ts():
    """현재 시각(초, 정수)."""
    return int(time.time())


def _default(path):
    return json.loads(json.dumps(DEFAULTS[path]))


def _load(path):
    with _lock:
        if not os.path.exists(path):
            _save(path, _default(path))
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return _default(path)


def _save(path, data):
    with _lock:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


# ─────────────────────────── 단기기억 ───────────────────────────

def load_short_term():
    return _load(SHORT_TERM_PATH)


def save_short_term(data):
    _save(SHORT_TERM_PATH, data)


def append_message(user, text, role="viewer"):
    """채팅 한 줄을 단기기억에 추가한다. role: "viewer" | "assistant"."""
    with _lock:
        st = load_short_term()
        st["messages"].append({"ts": now_ts(), "user": user, "text": text, "role": role})
        save_short_term(st)
        return st


def evict_short_term(ttl_sec, max_count):
    """오래되었거나(ts가 ttl 초과) 개수가 max_count를 넘은 메시지를 제거한다.

    제거된 메시지 리스트를 반환한다(호출부가 장기기억으로 요약 승격할 수 있도록).
    """
    with _lock:
        st = load_short_term()
        msgs = st["messages"]
        cutoff = now_ts() - ttl_sec

        fresh = [m for m in msgs if m.get("ts", 0) >= cutoff]
        evicted = [m for m in msgs if m.get("ts", 0) < cutoff]

        if len(fresh) > max_count:
            overflow = len(fresh) - max_count
            evicted.extend(fresh[:overflow])
            fresh = fresh[overflow:]

        st["messages"] = fresh
        save_short_term(st)
        return evicted


def short_term_openai_messages():
    """단기기억을 OpenAI messages(role/content)로 변환한다.

    viewer→user("이름: 내용"), assistant→assistant.
    """
    st = load_short_term()
    out = []
    for m in st["messages"]:
        if m.get("role") == "assistant":
            out.append({"role": "assistant", "content": m["text"]})
        else:
            who = m.get("user") or "시청자"
            out.append({"role": "user", "content": f"{who}: {m['text']}"})
    return out


def set_current_mood(mood):
    with _lock:
        st = load_short_term()
        st["current_mood"] = mood
        save_short_term(st)


def set_last_response_ts(ts):
    with _lock:
        st = load_short_term()
        st["last_response_ts"] = ts
        save_short_term(st)


# ─────────────────────────── 장기기억 ───────────────────────────

def load_long_term():
    return _load(LONG_TERM_PATH)


def append_long_term(items):
    """상황 맥락 문장들을 장기기억에 추가한다(중복은 무시)."""
    if not items:
        return
    with _lock:
        lt = load_long_term()
        for item in items:
            item = (item or "").strip()
            if item and item not in lt["stream_context"]:
                lt["stream_context"].append(item)
        lt["updated_at"] = now_ts()
        _save(LONG_TERM_PATH, lt)


def long_term_text():
    """장기기억을 프롬프트에 넣기 좋은 텍스트로 반환한다."""
    lt = load_long_term()
    return "\n".join(f"- {c}" for c in lt["stream_context"])


# ─────────────────────────── 재생상태 (자동 DJ) ───────────────────────────

def load_playback():
    return _load(PLAYBACK_PATH)


def save_playback(data):
    _save(PLAYBACK_PATH, data)


# ─────────────────────────── 초기화 ───────────────────────────

def reset_all():
    """모든 동적 상태를 기본 구조로 초기화한다(/new-chat)."""
    with _lock:
        for path in (SHORT_TERM_PATH, LONG_TERM_PATH, PLAYBACK_PATH):
            _save(path, _default(path))
