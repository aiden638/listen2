"""대화 → 무드 키워드 → 곡 추천 → 재생까지 한 번에 확인하는 대화형 테스트.

서버를 띄우지 않고, 실제 /chat·/mood-keywords·/recommend 와 동일한 함수들을 그대로 호출해
전체 파이프라인이 유기적으로 도는지 확인한다. (기억 파일은 건드리지 않고 메모리에서만 맥락 유지)

재생은 별도의 yt 재생 서비스(yt/main.py, 기본 http://localhost:8001)에 위임한다.
따라서 !음악으로 실제 소리까지 들으려면 yt 서버가 먼저 떠 있어야 한다:
    (다른 터미널에서) cd yt && uvicorn main:app --port 8001
    + yt-dlp, mpv 설치 필요

사용법 (backend 폴더에서):
    python test_live.py

명령어:
    (그냥 메시지 입력)  → AI와 대화 (페르소나 응답)
    !음악  또는 !music  → 지금까지의 대화 분위기로 곡을 추천하고 yt 서비스로 재생
    !종료  또는 !quit   → 종료
"""
import json as _json
import urllib.request
import urllib.error

from main import (
    client,
    get_config,
    get_assembled_prompt,
    call_gpt,
    load_mood_words,
    select_mood_keywords,
    song_to_dict,
)

YT_BASE = "http://localhost:8001"  # yt 재생 서비스 (yt/main.py)


def build_context(turns):
    """최근 대화 턴들을 'User: .. / AI: ..' 텍스트 맥락으로 만든다 (키워드 추출용)."""
    parts = []
    for user_msg, ai_msg in turns:
        parts.append(f"User: {user_msg}\nAI: {ai_msg}")
    return "\n---\n".join(parts)


def request_play(title, artist):
    """yt 재생 서비스(yt/main.py)의 /play에 곡을 보내 재생을 요청한다."""
    payload = _json.dumps({"title": title, "artist": artist}).encode("utf-8")
    req = urllib.request.Request(
        f"{YT_BASE}/play",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return _json.loads(resp.read().decode("utf-8"))


def play_music(turns, config):
    """현재 대화 맥락으로 곡을 추천하고 yt 재생 서비스로 재생을 요청한다."""
    if not turns:
        print("  아직 대화 내용이 없어 추천할 수 없어요. 먼저 몇 마디 나눠보세요.")
        return

    # 1. 무드 키워드 추출
    context = build_context(turns)
    words = load_mood_words()
    keywords = select_mood_keywords(context, words, config)
    print(f"  [무드 키워드] {keywords}")
    if not keywords:
        print("  유효한 키워드를 뽑지 못했습니다.")
        return

    # 2. 추천 엔진 로딩 (torch 등 필요)
    try:
        from recommender_bridge import get_recommender
        recommender = get_recommender()
    except Exception as e:
        print(f"  [건너뜀] 추천 엔진을 불러올 수 없습니다: {e}")
        print("  → pip install torch pandas numpy scikit-learn joblib scipy")
        return

    # 3. 곡 추천
    song = song_to_dict(recommender.recommend(keywords))
    title = song.get("track_name")
    artist = song.get("artist_name")
    print(f"  [추천곡] {title} — {artist}")

    # 4. 재생 위임 (yt 서비스에 title+artist 전달 → yt-dlp 검색 → mpv 재생)
    try:
        request_play(title, artist)
        print(f"  [재생] yt 서비스로 재생 요청 완료 ({YT_BASE}/play)")
    except urllib.error.URLError as e:
        print(f"  [재생 불가] yt 서비스에 연결할 수 없습니다: {e}")
        print(f"  → 다른 터미널에서: cd yt && uvicorn main:app --port 8001 (yt-dlp, mpv 필요)")


def main():
    if client is None:
        print("[실패] OPENAI_API_KEY가 설정되지 않았습니다. backend/.env를 확인하세요.")
        return

    config = get_config()
    buffer = config.get("buffer_turns", 3)
    system_prompt = get_assembled_prompt()

    print("=" * 60)
    print(" 대화형 테스트 — 대화하다가 '!음악'을 입력하면 곡을 추천/재생합니다.")
    print(" 종료: !종료")
    print("=" * 60)

    turns = []  # [(user_msg, ai_msg), ...] 단기 기억(메모리)

    while True:
        try:
            user_msg = input("\n나> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n종료합니다.")
            break

        if not user_msg:
            continue
        if user_msg in ("!종료", "!quit", "!exit"):
            print("종료합니다.")
            break
        if user_msg in ("!음악", "!music"):
            play_music(turns, config)
            continue

        # 대화 진행: system + 최근 단기기억 + 이번 입력
        messages = [{"role": "system", "content": system_prompt}]
        for u, a in turns[-buffer:]:
            messages.append({"role": "user", "content": u})
            messages.append({"role": "assistant", "content": a})
        messages.append({"role": "user", "content": user_msg})

        try:
            ai_text = call_gpt(messages, config["model"], config.get("temperature"))
        except Exception as e:
            print(f"AI> [오류] {e}")
            continue

        print(f"AI> {ai_text}")
        turns.append((user_msg, ai_text))


if __name__ == "__main__":
    main()
