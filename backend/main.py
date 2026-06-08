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
latest_response = {"content": "", "timestamp": 0}
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

# --- 자동 마이그레이션 로직 제거 (TXT 기반으로 환원) ---

class ChatRequest(BaseModel):
    message: str

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

def call_gpt(messages, model, temperature=None):
    """OpenAI Chat Completions 호출 후 응답 텍스트를 반환한다."""
    if client is None:
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다. backend/.env를 확인하세요.")
    kwargs = {"model": model, "messages": messages}
    if temperature is not None:
        kwargs["temperature"] = temperature
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content.strip()

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
    
    latest_response = {"content": "", "timestamp": 0}
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

        # 6. 상태 업데이트 및 반환
        global latest_response
        latest_response = {"content": ai_text, "timestamp": time.time()}
        return {"response": ai_text}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
