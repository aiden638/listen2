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