"""동적 대화 상태(JSON)를 다루는 유일한 모듈 — 단기기억 / 장기기억 / 재생상태.

설계 문서: backend/DESIGN.md

- buffer.json : 최근 채팅 메시지 버퍼 (TTL/개수로 자동 evict)
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

BUFFER_PATH = os.path.join(STATE_DIR, "buffer.json")  # 원문 대화 버퍼(최근 메시지)
FACTS_PATH = os.path.join(STATE_DIR, "facts.json")           # 단기기억: 발화자별 사실 (분 단위)
LONG_TERM_PATH = os.path.join(STATE_DIR, "long_term.json")   # 장기기억: 거시 상황/주제
PLAYBACK_PATH = os.path.join(STATE_DIR, "playback.json")

DEFAULTS = {
    BUFFER_PATH: {"messages": [], "current_mood": [], "last_response_ts": 0},
    FACTS_PATH: {"facts": []},  # [{speaker, fact, ts}]
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

def load_buffer():
    return _load(BUFFER_PATH)


def save_buffer(data):
    _save(BUFFER_PATH, data)


def append_message(user, text, role="viewer"):
    """채팅 한 줄을 단기기억에 추가한다. role: "viewer" | "assistant"."""
    with _lock:
        st = load_buffer()
        st["messages"].append({"ts": now_ts(), "user": user, "text": text, "role": role})
        save_buffer(st)
        return st


def evict_buffer(ttl_sec, max_count):
    """오래되었거나(ts가 ttl 초과) 개수가 max_count를 넘은 메시지를 제거한다.

    제거된 메시지 리스트를 반환한다(호출부가 장기기억으로 요약 승격할 수 있도록).
    """
    with _lock:
        st = load_buffer()
        msgs = st["messages"]
        cutoff = now_ts() - ttl_sec

        fresh = [m for m in msgs if m.get("ts", 0) >= cutoff]
        evicted = [m for m in msgs if m.get("ts", 0) < cutoff]

        if len(fresh) > max_count:
            overflow = len(fresh) - max_count
            evicted.extend(fresh[:overflow])
            fresh = fresh[overflow:]

        st["messages"] = fresh
        save_buffer(st)
        return evicted


def buffer_openai_messages():
    """단기기억을 OpenAI messages(role/content)로 변환한다.

    viewer→user("이름: 내용"), assistant→assistant.
    """
    st = load_buffer()
    out = []
    for m in st["messages"]:
        if m.get("role") == "assistant":
            out.append({"role": "assistant", "content": m["text"]})
        else:
            who = m.get("user") or "시청자"
            # 유튜브 등에서 "표시명(채널ID)" 형태로 올 때 채널ID는 떼고 표시명만 쓴다
            who = who.split("(")[0].strip() or "시청자"
            out.append({"role": "user", "content": f"{who}: {m['text']}"})
    return out


def buffer_as_chatlog():
    """버퍼를 '발화자: 텍스트' 한 줄씩의 채팅 로그 텍스트로 만든다.

    여러 시청자가 동시에 친 1:다수 채팅을 한 덩어리로 보여줘 화자 혼동을 막는다.
    AI 자기 발언은 '나'로 표시한다.
    """
    st = load_buffer()
    lines = []
    for m in st["messages"]:
        if m.get("role") == "assistant":
            lines.append(f"나: {m['text']}")
        else:
            who = (m.get("user") or "시청자").split("(")[0].strip() or "시청자"
            lines.append(f"{who}: {m['text']}")
    return "\n".join(lines)


def set_current_mood(mood):
    with _lock:
        st = load_buffer()
        st["current_mood"] = mood
        save_buffer(st)


def set_last_response_ts(ts):
    with _lock:
        st = load_buffer()
        st["last_response_ts"] = ts
        save_buffer(st)


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
    """장기기억(거시 상황)을 프롬프트에 넣기 좋은 텍스트로 반환한다."""
    lt = load_long_term()
    return "\n".join(f"- {c}" for c in lt["stream_context"])


# ─────────────────────────── 단기기억: 발화자별 사실 (facts) ───────────────────────────

def load_facts():
    return _load(FACTS_PATH)


def add_facts(items):
    """발화자별 사실을 추가한다. items: [{"speaker": 이름, "fact": 사실}]. 중복은 무시."""
    if not items:
        return
    with _lock:
        data = load_facts()
        existing = {(x.get("speaker"), x.get("fact")) for x in data["facts"]}
        for it in items:
            if not isinstance(it, dict):
                continue
            sp = (it.get("speaker") or "").strip() or "시청자"
            fa = (it.get("fact") or "").strip()
            if fa and (sp, fa) not in existing:
                data["facts"].append({"speaker": sp, "fact": fa, "ts": now_ts()})
                existing.add((sp, fa))
        _save(FACTS_PATH, data)


def evict_facts(ttl_sec, max_count=None):
    """오래된(ts가 ttl 초과) 사실을 제거하고, 개수 상한이 있으면 최근 것만 남긴다."""
    with _lock:
        data = load_facts()
        cutoff = now_ts() - ttl_sec
        kept = [x for x in data["facts"] if x.get("ts", 0) >= cutoff]
        if max_count and len(kept) > max_count:
            kept = kept[-max_count:]
        data["facts"] = kept
        _save(FACTS_PATH, data)


def facts_text():
    """단기기억을 '발화자: 사실1, 사실2' 형태의 텍스트로 반환한다(프롬프트용)."""
    data = load_facts()
    by_speaker = {}
    for x in data["facts"]:
        by_speaker.setdefault(x.get("speaker") or "시청자", []).append(x.get("fact"))
    return "\n".join(f"- {sp}: {', '.join(facts)}" for sp, facts in by_speaker.items())


# ─────────────────────────── 재생상태 (자동 DJ) ───────────────────────────

def load_playback():
    return _load(PLAYBACK_PATH)


def save_playback(data):
    _save(PLAYBACK_PATH, data)


# ─────────────────────────── 초기화 ───────────────────────────

def reset_all():
    """모든 동적 상태를 기본 구조로 초기화한다(/new-chat)."""
    with _lock:
        for path in (BUFFER_PATH, FACTS_PATH, LONG_TERM_PATH, PLAYBACK_PATH):
            _save(path, _default(path))
