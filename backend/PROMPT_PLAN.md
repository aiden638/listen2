# (임시) 프롬프트 구조 보강 계획 — 작업 메모

> 음악 문제 처리 후 여기로 돌아와 작업한다. 확정되면 DESIGN.md로 통합.

## 현재 프롬프트 조립 구조 (실측)
```
system = get_assembled_prompt() + TICK_RULES(코드 하드코딩)
get_assembled_prompt() = template.txt 조립:
  [Topic Setting]    {{topic_setting}}     ← prompts/topic_setting.txt
  [Example Dialogue] {{example_dialogue}}   ← prompts/example_dialogue.txt
  [AI의 기억]        {{memory}}            ← state/long_term.json (stream_context)
  {{roleplay_info}}                         ← prompts/roleplay_info.txt (페르소나)
+ 단기기억 messages (short_term.json → user/assistant)
```
- 동적: short_term.json(messages, current_mood), long_term.json(stream_context)
- 선별응답 성공 확인됨(3개 중 2개 응답, "나 오늘 안잘래"는 침묵).

## 보강 포인트 (발견)
1. **선별응답 규칙(TICK_RULES)이 코드에 하드코딩** → `prompts/live_rules.txt`로 외부화(편집 가능).
2. **current_mood가 프롬프트에 미주입** → "지금 방송 분위기"로 system에 넣기. (필요시 now_playing도)
3. **페르소나 ↔ 선별응답 충돌**: roleplay_info "마지막 말에 무조건 반응"(1:1) vs TICK_RULES "다 답하지 마라".
   → HOW(페르소나) / WHEN(선별) 역할 분리·정렬.
4. **시청자 이름이 채널ID 원문**(예: `10-oh4mu(UCe...)`)으로 프롬프트에 들어감 → 표시명 정리(토큰/가독성).
5. **example_dialogue를 라이브 버튜버 스타일로 보강** (침묵/선별 뉘앙스 포함).

## 작업 순서
- ① 구조 — ✅ 완료
- ② 내용: 페르소나·선별기준·예시 튜닝 (언제 답/침묵 캘리브레이션) — 다음

## ① 구조 — 한 일 (완료)
- 선별응답 규칙 외부화 → `prompts/live_rules.txt` (편집 가능). JSON 출력형식만 코드(`TICK_OUTPUT_SPEC`)에 잔류.
- `build_tick_system_prompt()` = template(페르소나/상황/기억) + live_rules + 출력형식.
- `{{current_mood}}` 주입(get_assembled_prompt) — short_term.current_mood가 프롬프트에 들어감.
- `template.txt` 재설계: 페르소나 → 방송상황(분위기) → 기억 → 예시 → 주제 순.
- 시청자 이름 정리: "표시명(채널ID)" → 표시명만 (memory_store.short_term_openai_messages).

## ② 내용 튜닝 — 할 일 (다음)
1. **example_dialogue.txt 가 비어 있음** → 라이브 버튜버 스타일 예시 작성(말투·선별 뉘앙스). 영향 큼.
2. **페르소나 ↔ 선별 충돌**: roleplay_info "시청자의 마지막 말에 가장 먼저 반응한다"(=무조건 반응) ↔ live_rules "다 답하지 마라".
   → roleplay_info는 HOW(말투/성격)만, WHEN은 live_rules가 담당하도록 페르소나 문구 수정.
3. live_rules 선별 기준 캘리브레이션(테스트하며 침묵/응답 비율 조정).
4. (선택) now_playing 곡 정보도 프롬프트에 주입할지 — "지금 이 노래 틀고 있어" 인지.
