import os
import json
import re
import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai
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

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPTS_DIR = os.path.join(BASE_DIR, "prompts")

if not os.path.exists(PROMPTS_DIR):
    os.makedirs(PROMPTS_DIR)

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
    system_prompt = get_assembled_prompt()
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        
        # 1. AI 답변 생성
        full_prompt = f"System: {system_prompt}\n\nUser: {request.message}"
        response = model.generate_content(full_prompt)
        ai_text = response.text
        
        # 2. 파일 경로 설정
        history_path = os.path.join(PROMPTS_DIR, "chat_history.txt")
        memory_path = os.path.join(PROMPTS_DIR, "memory.txt")
        
        # 3. chat_history.txt 업데이트
        history_content = ""
        if os.path.exists(history_path):
            with open(history_path, "r", encoding="utf-8") as f:
                history_content = f.read().strip()
        
        new_exchange = f"User: {request.message}\nAI: {ai_text}"
        if history_content:
            full_history = history_content + "\n---\n" + new_exchange
        else:
            full_history = new_exchange
            
        # 4. 메모리 관리 (최근 3개 턴 유지)
        exchanges = [e.strip() for e in full_history.split("---") if e.strip()]
        if len(exchanges) > 3:
            # 요약할 대상 (가장 오래된 대화)
            to_summarize = exchanges[0]
            remaining_history = "\n---\n".join(exchanges[1:])
            
            # 기존 메모리 읽기
            old_memory = ""
            if os.path.exists(memory_path):
                with open(memory_path, "r", encoding="utf-8") as f:
                    old_memory = f.read().strip()
            
            # 요약 생성 요청
            summary_prompt = f"다음은 대화의 일부와 기존 요약본이다. 이를 합쳐서 핵심 내용을 짧게 요약해줘.대화 내용은 무조건 빠짐 없이 기억되어야 해. \n\n기존 요약: {old_memory}\n새로운 대화: {to_summarize}"
            summary_response = model.generate_content(summary_prompt)
            new_memory = summary_response.text.strip()
            
            # 파일 업데이트
            with open(memory_path, "w", encoding="utf-8") as f:
                f.write(new_memory)
            with open(history_path, "w", encoding="utf-8") as f:
                f.write(remaining_history)
        else:
            # 그대로 저장
            with open(history_path, "w", encoding="utf-8") as f:
                f.write(full_history)

        # 5. 상태 업데이트 및 반환
        global latest_response
        latest_response = {"content": ai_text, "timestamp": time.time()}
        return {"response": ai_text}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
