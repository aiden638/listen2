source .venv/bin/activate    

(base) dubdy@seodohyeong-ui-MacBookAir 들어줘 % cd frontend 
(base) dubdy@seodohyeong-ui-MacBookAir frontend % npm run dev 

lsof -i :8000
kill -9 PID번호
source .venv/bin/activate 
python -m pip install google-generativeai fastapi uvicorn python-dotenv
python -m uvicorn main:app --reload


### Backend Execution
```bash
cd backend
pip install -r requirements.txt
python main.py
```

### Frontend Execution
```bash
cd frontend
npm install
npm run dev
```

에러 뜨면 FastAPI에서 직접 확인해보기
http://localhost:8000/docs

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


new!