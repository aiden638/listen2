# backend 키는 방법!
cd backend

# 가상환경 만들기 (1회성)
python -m venv .venv

# 가상환경 활성화 (본인이 사용하는 터미널에 맞춰 선택해서 실행하세요)
# 1) Command Prompt (기본 CMD)
.venv\Scripts\activate

# ( 안되면 아래 해보는데, 일단 위에있는 1번만 쓰세요 )
<!-- # 2) PowerShell
.\.venv\Scripts\Activate.ps1
# ※ 만약 권한 오류(Execution_Policies)가 발생하면 터미널에 아래 명령어 입력 후 다시 실행:
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process

# 3) Git Bash (또는 WSL)
source .venv/Scripts/activate -->

# 라이브러리 설치 (1회성)
pip install -r requirements.txt

# 백엔드 실행
python main.py


# frontend 키는 방법! ( 조작화면 )
cd frontend

npm install  (1회성)

npm run dev


# display 키는 방법! ( 방송화면 )
cd display

npm install (1회성)

npm run dev
 

# 웬만하면 안 쓸 것들 (포트가 겹쳐서 막힐 때 해결법)
# 8000번 포트를 사용하고 있는 프로세스 ID(PID) 찾기
netstat -ano | findstr :8000

# 찾은 PID 번호의 프로세스 강제 종료 (PID번호에 위 명령어 결과의 맨 오른쪽 숫자 입력)
taskkill /F /PID PID번호
-> 포트가 충돌하여 서버가 실행되지 않을 때 사용합니다.


python -m pip install google-generativeai fastapi uvicorn python-dotenv
python -m uvicorn main:app --reload
-> 뭔지 까먹음


에러 뜨면 FastAPI에서 직접 확인해보기
http://localhost:8000/docs
-> gemini API 문제로 채팅이 안될때


# github 관련
git init
git status
git add .
git commit -m "first commit"
git remote add origin https://github.com/아이디/저장소이름.git
git branch -M main
git push -u origin main

git add .
git commit -m "수정 내용 설명"
git push

# 다른 repository 연결
git remote -v
git remote set-url origin https://github.com/aiden638/listen.git


# vercel 관련
vercel login
vercel --prod


===================================================================
# 🎵 AI 음악 추천 + 재생 파이프라인 (2026.06 추가)
===================================================================

대화 분위기에 맞는 노래를 골라 자동으로 틀어주는 흐름:
대화(GPT) → 무드 키워드 5개 → 곡 추천 → YouTube 검색 → mpv 재생

## ⚠️ 중요 변경 (기존 팀원 주목)
- 채팅이 **Gemini → OpenAI(gpt-4o-mini)** 로 바뀜.
  → `backend/.env` 에 `OPENAI_API_KEY=sk-...` 필요 (GEMINI_API_KEY는 더 이상 안 씀)
- venv를 **루트 공용 `.venv` 하나로 통일** (backend/.venv는 폐기).
  → 기존 venv 그대로 써도 되지만, `pip install -r requirements.txt` 다시 한 번 + OpenAI 키만 넣으면 됨. 충돌 없음.

## 서비스 구성 (각각 별도 터미널)
| 폴더 | 포트 | 역할 |
|------|------|------|
| backend | 8000 | GPT 대화 · 무드 키워드 · 곡 선정 |
| yt      | 8001 | title+artist → yt-dlp 검색 → mpv 재생 |
| frontend| -    | 조작 화면 (npm) |
| display | -    | 방송 화면 (npm) |

## 1회 환경설정 (루트에서)
# 1) 루트 공용 venv 생성 + 활성화 (cmd)
python -m venv .venv
.venv\Scripts\activate.bat

# 2) Python 의존성 한 번에 (torch 등 포함, 시간 좀 걸림)
pip install -r requirements.txt

# 3) mpv 설치 (재생용, pip 아님 / winget 없으면 scoop 사용)
#    PowerShell에서:
#      Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
#      irm get.scoop.sh | iex
#      scoop bucket add extras
#      scoop install mpv
#    확인: mpv --version

# 4) backend/.env 에 OpenAI 키
#    OPENAI_API_KEY=sk-...

## 빠른 점검 (서버 없이)
cd backend
python test_chat.py     # 채팅 + 키워드 + 추천까지 한 번에 확인 (mpv 불필요)
python test_live.py     # 대화형: 대화하다 !음악 입력하면 추천+재생 (yt 서버 필요)

## 실제 실행 (터미널 2개, 둘 다 .venv 활성화)
# 터미널 A — yt 재생 서버
.venv\Scripts\activate.bat
cd yt
uvicorn main:app --port 8001

# 터미널 B — backend
.venv\Scripts\activate.bat
cd backend
uvicorn main:app --port 8000

## ⚠️ mpv PATH 함정 (재생 안 될 때 99%)
증상: yt 서버 status가 {"error":"[WinError 2] 지정된 파일을 찾을 수 없습니다"}, 소리 안 남.
원인: mpv는 scoop이 C:\Users\<사용자>\scoop\apps\mpv\current 폴더를 PATH에 등록하는데,
      VS Code 통합 터미널은 VS Code 켤 때의 옛 PATH를 물고 있어 mpv를 못 찾음.
해결(택1):
  - VS Code를 완전히 껐다 켜기 (영구 해결, 권장)
  - yt 서버 띄울 창에서 먼저: set PATH=%PATH%;C:\Users\<사용자>\scoop\apps\mpv\current
검증: yt 서버 띄우는 창에서 `where mpv` 가 경로를 보여줘야 재생됨.

## 엔드포인트 / 설정 메모
- backend(:8000): POST /chat, POST /mood-keywords, POST /recommend(키워드 자동추출 or {"keywords":[...]}), POST /new-chat
- yt(:8001): POST /play {title,artist}, POST /stop, GET /status  (루트 / 는 404가 정상)
- 모델/메모리 설정: backend/config.json (model, temperature, short_term_turns, summary_model, keyword_temperature)
- 프롬프트(페르소나·주제·예시·기억)는 backend/prompts/*.txt — 직접 편집하거나 /prompt API로 수정
- 단기기억=chat_history.txt(최근 N턴), 장기기억=memory.txt(자동 요약). /new-chat 으로 둘 다 초기화