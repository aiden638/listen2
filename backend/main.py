import os
import json
import re
import time
import asyncio
import urllib.request
import urllib.error
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv

import memory_store as store

load_dotenv()

# yt 재생 서비스(yt/main.py) 주소 — 자동 DJ가 곡을 mpv로 재생할 때 호출한다.
YT_BASE = os.environ.get("YT_BASE", "http://localhost:8001")

# ───────────────────────── [TEAM] 방송 송출 동기화 상태 ─────────────────────────
latest_response = {"content": "", "timestamp": 0}
broadcast_settings = {
    "bg_image": None,
    "music_url": None,                                  # upload 모드: 브라우저 audio가 재생할 URL
    "music_title": "현재 재생 중인 음악이 없습니다",
    "next_title": None,                                 # 자동 DJ가 미리 큐잉한 '다음 곡'
    "music_source": None,                               # None | "dj"(추천곡/mpv 서버재생) | "upload"(로컬파일/브라우저 audio)
    "font_size": 24,
    "mode": "live",                                     # live or wait
    "is_playing": True,
    "current_time": 0,
    "duration": 0,
    "show_character": True,
    "accept_live_chat": True,                           # False면 /ingest·비관리자 /chat 거부(관리자 테스트만 허용)
    "timestamp": 0,
}

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPTS_DIR = os.path.join(BASE_DIR, "prompts")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

if not os.path.exists(PROMPTS_DIR):
    os.makedirs(PROMPTS_DIR)

# config.json에서 모델/메모리/tick/음악 설정을 읽는다. 파일이 없거나 키가 빠져도 기본값으로 동작한다.
DEFAULT_CONFIG = {
    "model": "gpt-4o-mini",
    "temperature": 0.8,
    "summary_model": "gpt-4o-mini",
    "keyword_temperature": 0.3,
    # 단기기억 evict (memory_store)
    "short_term_ttl_sec": 120,   # 이 시간(초)보다 오래된 메시지는 단기기억에서 삭제
    "short_term_max": 40,        # 단기기억 메시지 개수 상한
    # 채팅 tick (선별 응답)
    "tick_seconds": 4,           # 마지막 tick 후 이 시간 지나면 tick
    "tick_messages": 8,          # 대기 메시지가 이 개수 쌓이면 tick
    # 자동 DJ (음악 루프)
    "prefetch_lead_sec": 60,     # 곡 종료(추정) 몇 초 전에 다음 곡을 미리 선정할지
    "default_song_sec": 210,     # 추천곡에 길이 정보가 없을 때 가정할 곡 길이(초)
    "min_play_sec": 10,          # 회전 오탐 방지: 곡 시작 후 최소 이만큼 지나야 회전 판단
    "rotate_safety_sec": 30,     # yt가 종료를 못 알릴 때 추정시간 + 이만큼 지나면 강제 회전
}

def get_config():
    config = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config.update(json.load(f))
        except Exception:
            pass
    return config

# 음악 추천용 무드 단어 사전 (프로젝트 루트, backend의 부모 폴더에 위치)
WORD_PROFILES_PATH = os.path.join(os.path.dirname(BASE_DIR), "word_audio_profiles_2000_flat.json")
_mood_words_cache = None

def load_mood_words():
    """word_audio_profiles_2000_flat.json의 단어(키) 목록을 캐시해서 반환한다."""
    global _mood_words_cache
    if _mood_words_cache is None:
        with open(WORD_PROFILES_PATH, "r", encoding="utf-8") as f:
            _mood_words_cache = list(json.load(f).keys())
    return _mood_words_cache


# ───────────────────────── 요청 모델 ─────────────────────────

class ChatRequest(BaseModel):
    message: str
    is_admin: bool = False           # [TEAM] 관리자 테스트 채팅 여부

class IngestRequest(BaseModel):
    user: str | None = None
    text: str

class RecommendRequest(BaseModel):
    keywords: list[str] | None = None

class PromptRequest(BaseModel):
    filename: str
    content: str

class SettingsUpdate(BaseModel):
    bg_image: str = None
    music_url: str = None
    music_title: str = None
    next_title: str | None = None
    music_source: str | None = None
    font_size: int = None
    mode: str = None
    is_playing: bool | None = None
    current_time: float | None = None
    duration: float | None = None
    show_character: bool | None = None
    accept_live_chat: bool | None = None


# ───────────────────────── 공용 헬퍼 ─────────────────────────

def get_assembled_prompt():
    """template.txt의 {{변수}}를 채워 system 프롬프트를 조립한다.

    {{memory}}(장기기억)는 txt가 아니라 state/long_term.json에서 가져온다.
    그 외 {{name}}은 prompts/name.txt 내용으로 치환.
    """
    template_path = os.path.join(PROMPTS_DIR, "template.txt")
    if not os.path.exists(template_path):
        return "You are a helpful AI assistant."
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            template = f.read()
        placeholders = re.findall(r"\{\{(.*?)\}\}", template)
        assembled = template
        for var_name in set(placeholders):
            clean_name = var_name.strip()
            if clean_name == "memory":
                content = store.long_term_text()
            else:
                txt_path = os.path.join(PROMPTS_DIR, f"{clean_name}.txt")
                content = ""
                if os.path.exists(txt_path):
                    with open(txt_path, "r", encoding="utf-8") as f:
                        content = f.read().strip()
            assembled = assembled.replace(f"{{{{{var_name}}}}}", content)
        return assembled
    except Exception:
        return "You are a helpful AI assistant."

def call_gpt(messages, model, temperature=None, response_format=None):
    """OpenAI Chat Completions 호출 후 응답 텍스트를 반환한다."""
    if client is None:
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다. backend/.env를 확인하세요.")
    kwargs = {"model": model, "messages": messages}
    if temperature is not None:
        kwargs["temperature"] = temperature
    if response_format is not None:
        kwargs["response_format"] = response_format
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content.strip()

def read_local_context():
    """국소적인(최근) 대화 맥락 = 단기기억(short_term.json). 비어있으면 최신 응답으로 대체."""
    st = store.load_short_term()
    lines = []
    for m in st["messages"]:
        who = "AI" if m.get("role") == "assistant" else (m.get("user") or "시청자")
        lines.append(f"{who}: {m['text']}")
    context = "\n".join(lines).strip()
    if not context and latest_response.get("content"):
        context = f"AI: {latest_response['content']}"
    return context

def summarize_evicted(evicted, config):
    """단기기억에서 밀려난 메시지들을, 이후에도 기억할 '상황 맥락' 한두 문장으로 요약한다."""
    convo = "\n".join(f"{m.get('user') or 'AI'}: {m['text']}" for m in evicted)
    old = store.long_term_text()
    prompt = (
        "다음은 방송 대화에서 단기기억을 벗어난 부분이다. "
        "이후에도 기억해야 할 '상황/맥락'만 1~2개의 짧은 문장으로 요약해줘. "
        "사소한 잡담은 버려도 된다.\n\n"
        f"[기존 상황 맥락]\n{old}\n\n[밀려난 대화]\n{convo}"
    )
    return call_gpt([{"role": "user", "content": prompt}], config.get("summary_model", config["model"]))

def set_broadcast(**kwargs):
    """broadcast_settings 일부 필드를 갱신하고 timestamp를 찍는다(display 폴링용)."""
    global broadcast_settings
    for k, v in kwargs.items():
        broadcast_settings[k] = v
    broadcast_settings["timestamp"] = time.time()


# ───────────────────────── [TEAM] 기본/프롬프트/방송 엔드포인트 ─────────────────────────

@app.get("/")
async def root():
    return {"message": "Broadcast Backend is running"}

@app.get("/prompts")
async def list_prompts():
    files = [f for f in os.listdir(PROMPTS_DIR) if f.endswith(".txt")]
    return sorted(files)

@app.get("/prompt/{filename}")
async def get_prompt_file(filename: str):
    file_path = os.path.join(PROMPTS_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    if filename.endswith(".json"):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {"content": data.get("content", "")}
    else:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"content": content}

@app.post("/prompt")
async def update_prompt_file(request: PromptRequest):
    file_path = os.path.join(PROMPTS_DIR, request.filename)
    if request.filename.endswith(".json"):
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump({"content": request.content}, f, indent=4, ensure_ascii=False)
    else:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(request.content)
    return {"status": "success"}

@app.get("/latest-response")
async def get_latest_response():
    return latest_response

@app.get("/broadcast-settings")
async def get_broadcast_settings():
    # current_mood(채팅 tick이 short_term.json에 기록)도 함께 노출 — frontend 분위기 표시/지정용.
    return {**broadcast_settings, "current_mood": store.load_short_term().get("current_mood") or []}

@app.post("/broadcast-settings")
async def update_broadcast_settings(settings: SettingsUpdate):
    global broadcast_settings
    if settings.bg_image is not None: broadcast_settings["bg_image"] = settings.bg_image
    if settings.music_url is not None: broadcast_settings["music_url"] = settings.music_url
    if settings.music_title is not None: broadcast_settings["music_title"] = settings.music_title
    if settings.next_title is not None: broadcast_settings["next_title"] = settings.next_title
    if settings.music_source is not None: broadcast_settings["music_source"] = settings.music_source
    if settings.font_size is not None: broadcast_settings["font_size"] = settings.font_size
    if settings.mode is not None: broadcast_settings["mode"] = settings.mode
    if settings.is_playing is not None: broadcast_settings["is_playing"] = settings.is_playing
    if settings.current_time is not None: broadcast_settings["current_time"] = settings.current_time
    if settings.duration is not None: broadcast_settings["duration"] = settings.duration
    if settings.show_character is not None: broadcast_settings["show_character"] = settings.show_character
    if settings.accept_live_chat is not None: broadcast_settings["accept_live_chat"] = settings.accept_live_chat
    broadcast_settings["timestamp"] = time.time()
    return broadcast_settings

@app.post("/new-chat")
async def new_chat():
    """대화/기억/재생 상태를 모두 초기화하고 자동 DJ도 끈다."""
    global latest_response, _dj_enabled
    store.reset_all()
    _dj_enabled = False
    yt_stop()
    latest_response = {"content": "", "timestamp": 0}
    set_broadcast(next_title=None, music_source=None)
    return {"status": "success", "message": "State (short/long term, playback) reset"}


# ───────────────────────── [HA] 채팅: 1:1 관리자/테스트 (/chat) ─────────────────────────

@app.post("/chat")
async def chat(request: ChatRequest):
    # [TEAM] 라이브 채팅 OFF면 관리자(is_admin)만 허용
    if not request.is_admin and not broadcast_settings.get("accept_live_chat", True):
        raise HTTPException(status_code=403, detail="Live chat input is currently disabled.")
    config = get_config()
    system_prompt = get_assembled_prompt()
    try:
        # 입력 → 단기기억 → system+단기기억으로 응답 → 응답도 단기기억 → evict→장기 승격
        store.append_message(user="관리자" if request.is_admin else "시청자", text=request.message, role="viewer")
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(store.short_term_openai_messages())
        ai_text = call_gpt(messages, config["model"], config.get("temperature"))

        store.append_message(user=None, text=ai_text, role="assistant")
        store.set_last_response_ts(store.now_ts())
        evicted = store.evict_short_term(config["short_term_ttl_sec"], config["short_term_max"])
        if evicted:
            store.append_long_term([summarize_evicted(evicted, config)])

        global latest_response
        latest_response = {"content": ai_text, "timestamp": time.time()}
        return {"response": ai_text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ───────────────────────── [HA] 무드 키워드 / 추천 ─────────────────────────

def select_mood_keywords(context, words, config, target_count=5, max_attempts=3):
    """대화 맥락(context)에 가장 어울리는 대표 단어 target_count개를 후보 목록(words) 안에서 고른다.

    추천 엔진이 앞쪽 단어에 더 큰 가중치를 주므로 가장 잘 맞는 단어부터 순서대로 반환한다.
    목록에 없는 단어는 걸러내고, 모자라면 부족분을 다시 요청한다(항상 목록 내 단어만 반환).
    """
    word_list_str = ", ".join(words)
    valid_set = set(words)
    selected = []
    rejected = []

    for _ in range(max_attempts):
        need = target_count - len(selected)
        if need <= 0:
            break
        request_count = need + 3
        system_msg = (
            "너는 대화의 분위기를 분석해 배경 음악 추천용 키워드를 뽑는 도구다. "
            "반드시 아래 '후보 단어 목록'에 그대로 적혀 있는 단어들 중에서만 골라야 한다. "
            "목록에 없는 단어를 새로 만들거나 변형하는 것은 절대 금지다. "
            f"지금 대화의 분위기를 가장 잘 나타내는 대표 단어 {request_count}개를, 가장 잘 어울리는 것부터 순서대로 고른다. "
            '반드시 {"keywords": ["단어1", "단어2", ...]} 형태의 JSON으로만 답하라.'
        )
        if selected:
            system_msg += f" 다음 단어들은 이미 선택했으니 제외하라: {', '.join(selected)}."
        if rejected:
            system_msg += f" 다음 단어들은 후보 목록에 없으니 절대 다시 고르지 마라: {', '.join(rejected)}."
        system_msg += f"\n\n[후보 단어 목록]\n{word_list_str}"
        user_msg = f"[대화 맥락]\n{context}"

        raw = call_gpt(
            [{"role": "system", "content": system_msg}, {"role": "user", "content": user_msg}],
            config["model"],
            config.get("keyword_temperature", 0.3),
            response_format={"type": "json_object"},
        )
        parsed = json.loads(raw)
        candidates = parsed.get("keywords", []) if isinstance(parsed, dict) else []
        for w in candidates:
            if not isinstance(w, str):
                continue
            if w in valid_set:
                if w not in selected:
                    selected.append(w)
            elif w not in rejected:
                rejected.append(w)
            if len(selected) >= target_count:
                break

    return selected[:target_count]

def song_to_dict(song):
    """recommender.recommend()가 반환한 pandas Series를 JSON 안전한 dict로 변환한다."""
    def to_native(v):
        if hasattr(v, "item"):
            try:
                v = v.item()
            except Exception:
                pass
        if isinstance(v, float) and v != v:  # NaN
            return None
        return v

    result = {}
    for field in ["track_name", "artist_name", "album_name", "cluster_id", "final_score"]:
        val = song.get(field)
        if val is not None:
            result[field] = to_native(val)
    # 곡 길이(초) — 자동 DJ가 '종료 시점'을 계산하는 데 사용 (데이터셋 duration_ms 기반)
    dur_ms = to_native(song.get("duration_ms"))
    if isinstance(dur_ms, (int, float)) and dur_ms > 0:
        result["duration_sec"] = int(dur_ms / 1000)
    return result

@app.post("/mood-keywords")
async def mood_keywords():
    """지금까지의 국소적인 대화 맥락에서 분위기를 대표하는 단어 5개를 뽑아 반환한다."""
    config = get_config()
    context = read_local_context()
    if not context:
        raise HTTPException(status_code=400, detail="대화 맥락이 비어있어 키워드를 뽑을 수 없습니다.")
    try:
        words = load_mood_words()
        keywords = select_mood_keywords(context, words, config)
        if not keywords:
            raise HTTPException(status_code=500, detail="유효한 키워드를 뽑지 못했습니다.")
        return {"keywords": keywords}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/recommend")
async def recommend(request: RecommendRequest | None = None):
    """대화 맥락에 어울리는 곡 1개를 추천한다(keywords를 넘기면 그것으로)."""
    config = get_config()
    keywords = request.keywords if request and request.keywords else None
    if not keywords:
        context = read_local_context()
        if not context:
            raise HTTPException(status_code=400, detail="대화 맥락이 비어있어 추천할 수 없습니다.")
        words = load_mood_words()
        keywords = select_mood_keywords(context, words, config)
        if not keywords:
            raise HTTPException(status_code=500, detail="유효한 키워드를 뽑지 못했습니다.")
    try:
        from recommender_bridge import get_recommender
        song = song_to_dict(get_recommender().recommend(keywords))
        return {"keywords": keywords, "song": song}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ───────────────────────── [HA] 채팅 tick (선별 응답) ─────────────────────────
#
# 1:다수 라이브 채팅. /ingest 로 들어온 메시지를 단기기억에 쌓다가,
# (tick_seconds 경과) 또는 (대기 tick_messages개 누적) 중 먼저 오면 tick을 돌린다.
# tick은 LLM 1회로 {respond, reply, mood, remember}를 받아 선별 응답한다.

_pending_count = 0
_last_tick_ts = 0

TICK_RULES = """

[지금 상황 — 실시간 방송 채팅]
- 이것은 1:다수의 실시간 방송 채팅이다. 짧고 많은 메시지가 연속으로 들어온다.
- 모든 메시지에 답하지 마라. 단순 호응(ㅋㅋ, ㅇㅇ, 네, 아니, 와 등)은 침묵하고 맥락만 흡수한다.
- 분위기를 바꿀 만하거나, 너를 부르거나, 질문이거나, 반응할 가치가 분명할 때만 응답한다.
- 응답할 때는 1~2문장으로 방송 채팅처럼 짧고 자연스럽게.

[출력] 반드시 아래 JSON 형식으로만 답하라:
{"respond": true 또는 false, "reply": "응답문 (respond가 false면 빈 문자열)", "mood": ["지금 분위기 단어", ...], "remember": ["이후에도 기억할 상황 맥락 문장", ...]}
"""

def run_tick_sync(config):
    """대기 중인 채팅 맥락으로 LLM을 1회 호출해 선별 응답/분위기/기억을 처리한다(동기)."""
    messages = [{"role": "system", "content": get_assembled_prompt() + TICK_RULES}]
    messages.extend(store.short_term_openai_messages())
    if len(messages) == 1:
        return
    raw = call_gpt(messages, config["model"], config.get("temperature"), response_format={"type": "json_object"})
    try:
        data = json.loads(raw)
    except Exception:
        return

    mood = data.get("mood") or []
    if mood:
        store.set_current_mood(mood)
    remember = data.get("remember") or []
    if remember:
        store.append_long_term(remember)

    if data.get("respond") and (data.get("reply") or "").strip():
        reply = data["reply"].strip()
        store.append_message(user=None, text=reply, role="assistant")
        store.set_last_response_ts(store.now_ts())
        global latest_response
        latest_response = {"content": reply, "timestamp": time.time()}

    store.evict_short_term(config["short_term_ttl_sec"], config["short_term_max"])

async def chat_tick_loop():
    global _pending_count, _last_tick_ts
    while True:
        await asyncio.sleep(1)
        if _pending_count <= 0:
            continue
        config = get_config()
        elapsed = store.now_ts() - _last_tick_ts
        if _pending_count >= config["tick_messages"] or elapsed >= config["tick_seconds"]:
            _pending_count = 0
            _last_tick_ts = store.now_ts()
            try:
                await asyncio.to_thread(run_tick_sync, config)
            except Exception as e:
                print("[chat_tick] error:", e)

@app.post("/ingest")
async def ingest(request: IngestRequest):
    """라이브 채팅 한 줄을 받아 단기기억에 넣고 tick 대기열에 올린다."""
    if not broadcast_settings.get("accept_live_chat", True):
        raise HTTPException(status_code=403, detail="Live chat input is currently disabled.")
    global _pending_count
    store.append_message(user=request.user or "시청자", text=request.text, role="viewer")
    _pending_count += 1
    return {"status": "ok", "pending": _pending_count}


# ───────────────────────── [HA] 자동 DJ (음악 루프) ─────────────────────────
#
# music_source 의미(이전 맥락 존중):
#   "dj"     = HA가 고른 추천곡을 yt 서비스(mpv)로 서버에서 재생
#   "upload" = 운영자가 올린 로컬 파일을 display 브라우저 audio로 재생 (TEAM 경로)
# 자동 DJ는 _dj_enabled True일 때만 동작. /dj/start 로 켜고 /dj/stop 으로 끈다.
# 곡 종료(추정) prefetch_lead_sec 초 전에 다음 곡을 미리 선정(큐잉)하고,
# 회전(다음 곡으로 교체)은 yt가 알려주는 '실제 재생 종료'를 기준으로 한다(데이터셋 길이와 무관).

_dj_enabled = False

def yt_play(title, artist):
    payload = json.dumps({"title": title, "artist": artist or ""}).encode("utf-8")
    req = urllib.request.Request(f"{YT_BASE}/play", data=payload,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))

def yt_stop():
    try:
        req = urllib.request.Request(f"{YT_BASE}/stop", method="POST")
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception:
        pass

def yt_status():
    """yt 서비스의 현재 재생 상태를 반환한다(실패 시 None).

    mpv 재생이 자연 종료되면 yt가 status를 'idle'로 바꾸므로, 이것으로 '실제 곡 종료'를 안다.
    """
    try:
        with urllib.request.urlopen(f"{YT_BASE}/status", timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

def pick_song(config, override_keywords=None):
    """곡 1개를 추천한다(song dict).

    - override_keywords가 주어지면 그 분위기로 고른다(운영자가 첫 곡 분위기 지정).
    - 없으면 대화 맥락 → tick이 저장한 current_mood 순으로 키워드를 뽑는다.
    맥락/분위기가 전혀 없어도 추천 엔진의 랜덤 폴백으로 곡을 고른다(첫 곡 끊김 방지).
    엔진 로딩 자체가 실패할 때만 None.
    """
    words = load_mood_words()
    if override_keywords:
        # 사전에 있는 단어만 추천 엔진이 인식 — 하나도 없으면 원본을 넘겨 랜덤 폴백
        keywords = [w for w in override_keywords if w in set(words)] or list(override_keywords)
    else:
        context = read_local_context()
        keywords = select_mood_keywords(context, words, config) if context else []
        if not keywords:
            mood = store.load_short_term().get("current_mood") or []
            keywords = [w for w in mood if w in set(words)][:5]
    try:
        # keywords가 비어 있어도 recommender는 랜덤 인기곡으로 폴백한다 → 첫 곡 보장
        from recommender_bridge import get_recommender
        return song_to_dict(get_recommender().recommend(keywords))
    except Exception as e:
        print("[music] pick_song error:", e)
        return None

def _dj_kickoff(config, keywords):
    """운영자가 지정한 분위기로 첫 곡을 즉시 시작한다(pick→play, 한 스레드에서)."""
    song = pick_song(config, override_keywords=keywords)
    if song:
        play_song(song, config)
        store.set_current_mood(list(keywords))  # 표시용으로 현재 분위기도 갱신
    return song

def play_song(song, config):
    """yt로 재생을 요청하고 playback.json·broadcast_settings에 반영한다."""
    yt_play(song.get("track_name", ""), song.get("artist_name", ""))
    dur = song.get("duration_sec") or config["default_song_sec"]
    pb = store.load_playback()
    if pb.get("now_playing"):
        pb["history"].append(pb["now_playing"])
    pb["now_playing"] = {
        "title": song.get("track_name"),
        "artist": song.get("artist_name"),
        "started_at": store.now_ts(),
        "duration_sec": dur,
    }
    pb["next"] = None
    store.save_playback(pb)
    set_broadcast(
        music_source="dj",
        music_title=f"{song.get('track_name')} - {song.get('artist_name', '')}",
        next_title=None,
        is_playing=True,
        current_time=0,
        duration=dur,
    )

def run_music_tick(config):
    """자동 DJ 한 틱: 첫 곡 시작 / 다음 곡 프리페치 / 곡 종료 시 회전."""
    pb = store.load_playback()
    np = pb.get("now_playing")
    now = store.now_ts()

    if np is None:
        song = pick_song(config)
        if song:
            play_song(song, config)
        return

    started_at = np["started_at"]
    est_dur = np.get("duration_sec") or config["default_song_sec"]
    ends_at_est = started_at + est_dur
    lead = config["prefetch_lead_sec"]

    # 진행바: 추정 길이 기준 현재 재생 위치를 송출 상태에 반영(display/데크 진행바용).
    # 실제 회전은 mpv 종료 기준이라 추정과 약간 어긋날 수 있으나 시각 표시로는 충분.
    set_broadcast(current_time=min(max(0, now - started_at), est_dur), duration=est_dur)

    # 종료(추정) lead초 전: 다음 곡 미리 선정(큐잉). 추정 길이는 '미리 고를 시점' 판단에만 쓴다.
    if pb.get("next") is None and now >= ends_at_est - lead:
        song = pick_song(config)
        if song:
            pb = store.load_playback()
            pb["next"] = song
            store.save_playback(pb)
            set_broadcast(next_title=f"{song.get('track_name')} - {song.get('artist_name', '')}")

    # 회전 판단은 '실제 재생 종료'(yt가 idle/멈춤이 됨)를 기준으로 한다.
    # → 데이터셋 길이와 실제 YouTube 영상 길이가 달라도 무음/끊김이 생기지 않는다.
    #   추정 길이(ends_at_est)는 yt가 종료를 못 알릴 때만 쓰는 안전망(상한)이다.
    if now - started_at < config.get("min_play_sec", 10):
        return  # 시작 직후 yt 상태 race로 인한 오탐 방지

    st = yt_status()
    actually_ended = st is not None and st.get("status") in ("idle", "stopped", "error")
    safety_exceeded = now >= ends_at_est + config.get("rotate_safety_sec", 30)

    if actually_ended or safety_exceeded:
        nxt = store.load_playback().get("next") or pick_song(config)
        if nxt:
            play_song(nxt, config)

async def music_loop():
    while True:
        await asyncio.sleep(3)
        if not _dj_enabled:
            continue
        config = get_config()
        try:
            await asyncio.to_thread(run_music_tick, config)
        except Exception as e:
            print("[music] error:", e)

@app.post("/dj/start")
async def dj_start(request: RecommendRequest | None = None):
    """자동 DJ를 켜고 즉시 첫 곡을 선정·재생한다.

    keywords를 넘기면 운영자가 지정한 분위기로 첫 곡을 시작한다. 없으면 대화 맥락 기반.
    """
    global _dj_enabled
    _dj_enabled = True
    config = get_config()
    keywords = request.keywords if request and request.keywords else None
    try:
        if keywords:
            await asyncio.to_thread(_dj_kickoff, config, keywords)
        else:
            await asyncio.to_thread(run_music_tick, config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "started", "playback": store.load_playback()}

@app.post("/dj/stop")
async def dj_stop():
    """자동 DJ를 끄고 재생을 멈춘다."""
    global _dj_enabled
    _dj_enabled = False
    yt_stop()
    set_broadcast(music_source=None, is_playing=False, next_title=None)
    return {"status": "stopped"}

@app.get("/dj/status")
async def dj_status():
    return {"enabled": _dj_enabled, "playback": store.load_playback()}


# ───────────────────────── 백그라운드 루프 기동 ─────────────────────────

@app.on_event("startup")
async def _start_background_loops():
    asyncio.create_task(chat_tick_loop())
    asyncio.create_task(music_loop())


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
