import os
import json
import re
import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Global state for display synchronization
latest_response = {"content": "", "timestamp": 0, "emotion": "neutral"}

# 아바타 표정용 감정 라벨. display 쪽 표정 프리셋과 반드시 일치해야 한다.
EMOTIONS = ["neutral", "happy", "sad", "angry", "surprised", "relaxed"]
broadcast_settings = {
    "bg_image": None,
    "music_url": None,
    "music_title": "현재 재생 중인 음악이 없습니다",
    "font_size": 24,
    "mode": "live", # live or wait
    "is_playing": True,
    "current_time": 0,
    "duration": 0,
    "show_character": True,
    "timestamp": 0
}

app = FastAPI()

# Enable CORS
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

# config.json에서 모델/메모리 설정을 읽는다. 파일이 없거나 키가 빠져도 기본값으로 동작한다.
DEFAULT_CONFIG = {
    "model": "gpt-4o-mini",
    "temperature": 0.8,
    "short_term_turns": 3,
    "summary_model": "gpt-4o-mini",
    "keyword_temperature": 0.3,
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

# --- 자동 마이그레이션 로직 제거 (TXT 기반으로 환원) ---

class ChatRequest(BaseModel):
    message: str

class RecommendRequest(BaseModel):
    keywords: list[str] | None = None

class PromptRequest(BaseModel):
    filename: str
    content: str

class SettingsUpdate(BaseModel):
    bg_image: str = None
    music_url: str = None
    music_title: str = None
    font_size: int = None
    mode: str = None
    is_playing: bool | None = None
    current_time: float | None = None
    duration: float | None = None
    show_character: bool | None = None

def get_assembled_prompt():
    template_path = os.path.join(PROMPTS_DIR, "template.txt")
    if not os.path.exists(template_path): return "You are a helpful AI assistant."
    try:
        with open(template_path, "r", encoding="utf-8") as f: template = f.read()
        placeholders = re.findall(r"\{\{(.*?)\}\}", template)
        assembled = template
        for var_name in set(placeholders):
            clean_name = var_name.strip()
            txt_path = os.path.join(PROMPTS_DIR, f"{clean_name}.txt")
            content = ""
            if os.path.exists(txt_path):
                with open(txt_path, "r", encoding="utf-8") as f: content = f.read().strip()
            assembled = assembled.replace(f"{{{{{var_name}}}}}", content)
        return assembled
    except Exception as e:
        return "You are a helpful AI assistant."

def parse_history_to_messages(history_content):
    """chat_history.txt(단기 기억)를 OpenAI messages 형식으로 변환한다.

    저장 형식: 각 턴은 'User: ...\nAI: ...' 이고 턴 사이는 '---'로 구분된다.
    """
    messages = []
    if not history_content:
        return messages
    exchanges = [e.strip() for e in history_content.split("---") if e.strip()]
    for exchange in exchanges:
        match = re.match(r"User:\s*(.*?)\nAI:\s*(.*)", exchange, re.DOTALL)
        if match:
            user_text = match.group(1).strip()
            ai_text = match.group(2).strip()
            if user_text:
                messages.append({"role": "user", "content": user_text})
            if ai_text:
                messages.append({"role": "assistant", "content": ai_text})
    return messages

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

def classify_emotion(text, config):
    """AI 답변 텍스트가 드러내는 감정을 EMOTIONS 중 하나로 분류한다.

    분류에 실패해도(키 없음/네트워크 오류 등) 'neutral'로 안전하게 떨어지므로
    이 호출이 채팅 흐름을 깨뜨리지 않는다.
    """
    if client is None or not text:
        return "neutral"
    try:
        system_msg = (
            "너는 텍스트의 감정을 분류하는 도구다. 아래 답변이 드러내는 감정을 "
            + ", ".join(EMOTIONS)
            + " 중 정확히 하나로만 고른다. "
            '반드시 {"emotion": "<값>"} 형태의 JSON으로만 답하라.'
        )
        raw = call_gpt(
            [{"role": "system", "content": system_msg}, {"role": "user", "content": text}],
            config.get("summary_model", config["model"]),
            0.0,
            response_format={"type": "json_object"},
        )
        emotion = json.loads(raw).get("emotion", "neutral")
        return emotion if emotion in EMOTIONS else "neutral"
    except Exception:
        return "neutral"

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
    if not os.path.exists(file_path): raise HTTPException(status_code=404, detail="File not found")
    if filename.endswith(".json"):
        with open(file_path, "r", encoding="utf-8") as f: data = json.load(f)
        return {"content": data.get("content", "")}
    else:
        with open(file_path, "r", encoding="utf-8") as f: content = f.read()
        return {"content": content}

@app.post("/prompt")
async def update_prompt_file(request: PromptRequest):
    file_path = os.path.join(PROMPTS_DIR, request.filename)
    if request.filename.endswith(".json"):
        with open(file_path, "w", encoding="utf-8") as f: json.dump({"content": request.content}, f, indent=4, ensure_ascii=False)
    else:
        with open(file_path, "w", encoding="utf-8") as f: f.write(request.content)
    return {"status": "success"}

@app.post("/new-chat")
async def new_chat():
    global latest_response
    # 초기화할 파일 목록
    files_to_clear = ["chat_history.txt", "memory.txt"]
    for filename in files_to_clear:
        file_path = os.path.join(PROMPTS_DIR, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("")
    
    latest_response = {"content": "", "timestamp": 0, "emotion": "neutral"}
    return {"status": "success", "message": "Conversation history and memory cleared"}

@app.get("/latest-response")
async def get_latest_response():
    return latest_response

@app.get("/broadcast-settings")
async def get_broadcast_settings():
    return broadcast_settings

@app.post("/broadcast-settings")
async def update_broadcast_settings(settings: SettingsUpdate):
    global broadcast_settings
    if settings.bg_image is not None: broadcast_settings["bg_image"] = settings.bg_image
    if settings.music_url is not None: broadcast_settings["music_url"] = settings.music_url
    if settings.music_title is not None: broadcast_settings["music_title"] = settings.music_title
    if settings.font_size is not None: broadcast_settings["font_size"] = settings.font_size
    if settings.mode is not None: broadcast_settings["mode"] = settings.mode
    if settings.is_playing is not None: broadcast_settings["is_playing"] = settings.is_playing
    if settings.current_time is not None: broadcast_settings["current_time"] = settings.current_time
    if settings.duration is not None: broadcast_settings["duration"] = settings.duration
    if settings.show_character is not None: broadcast_settings["show_character"] = settings.show_character
    broadcast_settings["timestamp"] = time.time()
    return broadcast_settings

@app.post("/chat")
async def chat(request: ChatRequest):
    config = get_config()
    system_prompt = get_assembled_prompt()
    try:
        # 1. 파일 경로 설정
        history_path = os.path.join(PROMPTS_DIR, "chat_history.txt")
        memory_path = os.path.join(PROMPTS_DIR, "memory.txt")

        # 2. 단기 기억(최근 대화)을 messages 배열로 구성
        history_content = ""
        if os.path.exists(history_path):
            with open(history_path, "r", encoding="utf-8") as f:
                history_content = f.read().strip()

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(parse_history_to_messages(history_content))
        messages.append({"role": "user", "content": request.message})

        # 3. AI 답변 생성
        ai_text = call_gpt(messages, config["model"], config.get("temperature"))

        # 4. chat_history.txt 업데이트
        new_exchange = f"User: {request.message}\nAI: {ai_text}"
        if history_content:
            full_history = history_content + "\n---\n" + new_exchange
        else:
            full_history = new_exchange

        # 5. 메모리 관리 (최근 N개 턴만 단기 기억으로 유지, 나머지는 장기 기억으로 요약)
        short_term_turns = config.get("short_term_turns", 3)
        exchanges = [e.strip() for e in full_history.split("---") if e.strip()]
        if len(exchanges) > short_term_turns:
            # 요약할 대상 (단기 기억 범위를 벗어난 가장 오래된 대화들)
            overflow = exchanges[:-short_term_turns]
            remaining_history = "\n---\n".join(exchanges[-short_term_turns:])
            to_summarize = "\n---\n".join(overflow)

            # 기존 장기 기억 읽기
            old_memory = ""
            if os.path.exists(memory_path):
                with open(memory_path, "r", encoding="utf-8") as f:
                    old_memory = f.read().strip()

            # 요약 생성 요청
            summary_prompt = f"다음은 대화의 일부와 기존 요약본이다. 이를 합쳐서 핵심 내용을 짧게 요약해줘.대화 내용은 무조건 빠짐 없이 기억되어야 해. \n\n기존 요약: {old_memory}\n새로운 대화: {to_summarize}"
            new_memory = call_gpt(
                [{"role": "user", "content": summary_prompt}],
                config.get("summary_model", config["model"]),
            )

            # 파일 업데이트
            with open(memory_path, "w", encoding="utf-8") as f:
                f.write(new_memory)
            with open(history_path, "w", encoding="utf-8") as f:
                f.write(remaining_history)
        else:
            # 그대로 저장
            with open(history_path, "w", encoding="utf-8") as f:
                f.write(full_history)

        # 6. 답변 감정 분류 (아바타 표정용) 및 상태 업데이트, 반환
        global latest_response
        emotion = classify_emotion(ai_text, config)
        latest_response = {"content": ai_text, "timestamp": time.time(), "emotion": emotion}
        return {"response": ai_text, "emotion": emotion}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def select_mood_keywords(context, words, config, target_count=5, max_attempts=3):
    """대화 맥락(context)에 가장 어울리는 대표 단어 target_count개를 후보 목록(words) 안에서 고른다.

    추천 엔진이 앞쪽 단어에 더 큰 가중치를 주므로, 가장 잘 맞는 단어부터 순서대로 반환한다.
    GPT가 후보 목록에 없는 단어를 만들어내면 검증 단계에서 걸러지는데, 그렇게 개수가 모자라면
    이미 고른 단어를 제외하고 부족한 만큼 다시 요청한다(최대 max_attempts회). 그 결과 반환되는
    단어는 항상 후보 목록(words) 안에 존재함이 보장된다.
    """
    word_list_str = ", ".join(words)
    valid_set = set(words)
    selected = []
    rejected = []  # GPT가 골랐지만 후보 목록에 없어서 버린 단어들 (다음 시도에서 제외)

    for attempt in range(max_attempts):
        need = target_count - len(selected)
        if need <= 0:
            break

        # 일부가 또 걸러질 것에 대비해 여유 있게 요청
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

        # 후보 목록에 실제로 존재하는 단어만, 순서/중복 제거하여 채운다
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

def read_local_context():
    """국소적인(최근) 대화 맥락 = 단기 기억(chat_history). 비어있으면 최신 응답으로 대체."""
    history_path = os.path.join(PROMPTS_DIR, "chat_history.txt")
    context = ""
    if os.path.exists(history_path):
        with open(history_path, "r", encoding="utf-8") as f:
            context = f.read().strip()
    if not context and latest_response.get("content"):
        context = f"AI: {latest_response['content']}"
    return context

def song_to_dict(song):
    """recommender.recommend()가 반환한 pandas Series를 JSON 안전한 dict로 변환한다."""
    def to_native(v):
        if hasattr(v, "item"):  # numpy 스칼라 → 파이썬 기본 타입
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
    """대화 맥락에 어울리는 곡 1개를 추천한다.

    - keywords를 직접 넘기면 그 단어들로 추천한다.
    - 넘기지 않으면 국소적인 대화 맥락에서 무드 키워드 5개를 자동 추출해 추천한다.
    """
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
        recommender = get_recommender()
        song = recommender.recommend(keywords)
        return {"keywords": keywords, "song": song_to_dict(song)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
