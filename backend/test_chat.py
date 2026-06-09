"""OpenAI 연동 + 무드 키워드 추출이 잘 되는지 빠르게 확인하는 스크립트.

사용법 (backend 폴더에서):
    python test_chat.py
    python test_chat.py "오늘 기분이 무슨색이게"   # 메시지 직접 지정

서버를 띄우지 않고 /chat, /mood-keywords와 동일한 경로(프롬프트 조립 + GPT 호출)를 타며,
chat_history.txt / memory.txt 같은 기억 파일은 건드리지 않는다.
"""
import sys
from main import (
    client,
    get_config,
    get_assembled_prompt,
    call_gpt,
    load_mood_words,
    select_mood_keywords,
)


def main():
    message = sys.argv[1] if len(sys.argv) > 1 else "나 너무 힘든 일이 있었어ㅠㅜㅠㅜ"

    # 1. API 키 확인
    if client is None:
        print("[실패] OPENAI_API_KEY가 설정되지 않았습니다. backend/.env를 확인하세요.")
        return

    config = get_config()
    print(f"[설정] 모델: {config['model']}, temperature: {config.get('temperature')}")

    # 2. 시스템 프롬프트 조립 확인
    system_prompt = get_assembled_prompt()
    print(f"[시스템 프롬프트 길이] {len(system_prompt)}자")

    # 3. 채팅 응답 생성
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]
    print(f"\n[보낸 메시지] {message}")
    try:
        ai_text = call_gpt(messages, config["model"], config.get("temperature"))
        print(f"[AI 응답] {ai_text}")
    except Exception as e:
        print(f"\n[실패] 채팅 호출 중 오류: {e}")
        return

    # 4. 방금 대화 맥락으로 무드 키워드 5개 추출
    context = f"User: {message}\nAI: {ai_text}"
    print(f"\n[키워드 추출용 맥락]\n{context}")
    try:
        words = load_mood_words()
        print(f"[후보 단어 수] {len(words)}개")
        keywords = select_mood_keywords(context, words, config)
        print(f"[선정된 무드 키워드 5개] {keywords}")
        if not keywords:
            print("\n[경고] 채팅은 됐지만 유효한 키워드를 뽑지 못했습니다.")
            return
    except Exception as e:
        print(f"\n[실패] 키워드 추출 중 오류: {e}")
        return

    # 5. 추출된 키워드로 곡 추천 (torch 등 ML 의존성이 설치돼 있을 때만)
    try:
        from recommender_bridge import get_recommender
    except Exception as e:
        print(f"\n[건너뜀] 추천 엔진을 불러올 수 없습니다(채팅+키워드는 정상): {e}")
        print("  → /recommend까지 쓰려면: pip install torch pandas numpy scikit-learn joblib scipy")
        return

    try:
        recommender = get_recommender()
        song = recommender.recommend(keywords)
        print("\n[추천된 곡]")
        print(f"  제목   : {song.get('track_name')}")
        print(f"  아티스트: {song.get('artist_name')}")
        if song.get('album_name') is not None:
            print(f"  앨범   : {song.get('album_name')}")
        print(f"  클러스터: {song.get('cluster_id')}")
        print("\n[성공] 채팅 + 키워드 + 곡 추천이 모두 정상 동작합니다.")
    except Exception as e:
        print(f"\n[실패] 곡 추천 중 오류: {e}")


if __name__ == "__main__":
    main()
