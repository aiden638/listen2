"""OpenAI 연동이 잘 되는지 빠르게 확인하는 스크립트.

사용법 (backend 폴더에서):
    python test_chat.py
    python test_chat.py "오늘 기분이 무슨색이게"   # 메시지 직접 지정

서버를 띄우지 않고 /chat과 동일한 프롬프트 조립 + GPT 호출 경로를 타며,
chat_history.txt / memory.txt 같은 기억 파일은 건드리지 않는다.
"""
import sys
from main import client, get_config, get_assembled_prompt, call_gpt


def main():
    message = sys.argv[1] if len(sys.argv) > 1 else "안녕! 오늘 방송 재밌다 ㅎㅎ"

    # 1. API 키 확인
    if client is None:
        print("[실패] OPENAI_API_KEY가 설정되지 않았습니다. backend/.env를 확인하세요.")
        return

    config = get_config()
    print(f"[설정] 모델: {config['model']}, temperature: {config.get('temperature')}")

    # 2. 시스템 프롬프트 조립 확인
    system_prompt = get_assembled_prompt()
    print(f"[시스템 프롬프트 길이] {len(system_prompt)}자")

    # 3. 실제 호출
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]
    print(f"\n[보낸 메시지] {message}")
    try:
        ai_text = call_gpt(messages, config["model"], config.get("temperature"))
        print(f"[AI 응답] {ai_text}")
        print("\n[성공] OpenAI 연동이 정상 동작합니다.")
    except Exception as e:
        print(f"\n[실패] 호출 중 오류: {e}")


if __name__ == "__main__":
    main()
