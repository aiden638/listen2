"""Phase 2 검증 — 라이브 채팅을 흘려보내며 AI가 '침묵 vs 응답'을 선별하는지 본다.

서버를 띄우지 않고 채팅 tick 로직(run_tick_sync)을 직접 호출한다.
실제 OpenAI 호출이 일어나므로 backend/.env 의 OPENAI_API_KEY 필요.

사용법 (backend 폴더에서): python test_stream.py
"""
import main
import memory_store as store


BURSTS = [
    ("단순 호응",   [("철수", "ㅋㅋㅋ"), ("영희", "ㅇㅇ"), ("민수", "ㅋㅋ"), ("도라", "ㅇㅈ")]),
    ("질문",        [("초코", "오늘 무슨 노래 틀 거야?")]),
    ("감정 토로",   [("바나나", "나 오늘 시험 망했어 ㅠㅠ")]),
    ("잡담",        [("키위", "배고프다"), ("멜론", "ㄹㅇ"), ("포도", "급식 뭐였지")]),
    ("호명",        [("수박", "스트리머야 이 노래 좋다 그치?")]),
]


def main_run():
    if main.client is None:
        print("[실패] OPENAI_API_KEY가 없습니다. backend/.env 확인.")
        return

    store.reset_all()
    config = main.get_config()
    print(f"[설정] tick_messages={config['tick_messages']}, model={config['model']}\n")

    for label, burst in BURSTS:
        for user, text in burst:
            store.append_message(user, text, "viewer")
        chat_line = " / ".join(f"{u}: {t}" for u, t in burst)
        print(f"[{label}] {chat_line}")

        before_ts = main.latest_response.get("timestamp", 0)
        main.run_tick_sync(config)
        after = main.latest_response

        if after.get("timestamp", 0) != before_ts and after.get("content"):
            print(f"   💬 응답: {after['content']}")
        else:
            print(f"   🤐 침묵 (맥락만 흡수)")
        print(f"   분위기: {store.load_short_term().get('current_mood', [])}\n")

    print("─" * 50)
    print("장기기억(stream_context):")
    for c in store.load_long_term()["stream_context"]:
        print(f"  - {c}")


if __name__ == "__main__":
    main_run()
