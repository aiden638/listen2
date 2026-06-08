# backend 키는 방법!
cd backend
source .venv/bin/activate 
pip install -r requirements.txt (1회성)
python main.py

# frontend 키는 방법! ( 조작화면 )
cd frontend
npm install  (1회성)
npm run dev

# displat 키는 방법! ( 방송화면 )
cd display
npm install (1회성)
npm run dev
 

# 왠만하면 안쓸것들
lsof -i :8000
kill -9 PID번호  
-> 포트가 겹쳐서 막힌다

python -m pip install google-generativeai fastapi uvicorn python-dotenv
python -m uvicorn main:app --reload
-> 먼지 까먹음

에러 뜨면 FastAPI에서 직접 확인해보기
http://localhost:8000/docs
-> gemini API 문제로 채팅이 안될때

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

다른 repository
git remote -v
git remote set-url origin https://github.com/aiden638/listen.git

-> github 관련


vercel login
vercel --prod

-> vercel 관련