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

## ② 내용 튜닝 — 진행 상황
1. ✅ **example_dialogue.txt 작성** — 1:다수 + 선별 응답 스타일(침묵/응답 예시 6개). 페르소나(여고생 버튜버) 톤 유지.
2. ⏸ **페르소나 ↔ 선별 충돌**: roleplay_info "마지막 말에 무조건 반응" 문구 — 사용자 요청으로 **지금은 그대로 두고** 예시로 선별 학습. 테스트 후 거슬리면 그때 수정(파일이라 언제든 가능).
3. ⏭ live_rules 선별 기준 캘리브레이션 — test_stream.py로 침묵/응답 비율 보며 조정.
4. ⏭ (선택) now_playing 곡 정보 프롬프트 주입 — "지금 이 노래 틀고 있어" 인지.

## 다음 행동
- `python test_stream.py`로 선별 응답이 예시대로 잘 되는지 관찰 → live_rules 미세조정.

---

# ③ 구조 재설계 — 사용자 핵심 요구 (다음 단계, 천천히)

> "입력 1개 → 출력 1개"를 버리고, AI가 자기 리듬으로 말하는 모델로.

1. **출력 cadence (가장 중요)**: 입력 빈도와 출력을 분리. AI가 일정 리듬으로 "말할 차례"가 오면,
   그동안 쌓인 채팅 묶음을 보고 (말할지/무엇을) 한 번에 결정. 입력 빠르면 더, 오래 조용하면 먼저 말 검.
   지금처럼 채팅마다 응답할지 판단(토큰·지연 큼) → 묶음 1회 판단으로.
2. **답변 맥락화**: 한 입력에만 반응하면 안 본 사람은 무슨 얘긴지 모름.
   → 선택한 채팅의 (a) 작성자 아이디를 답에 표시 또는 (b) 내용을 되짚어 모두 이해 가능하게.
3. **스타일**: 너무 길거나 텍스트 티(쉼표·마침표 등) 나면 안 됨. 짧고 자연스럽게.
4. **메모리 3층 재정의**:
   - 원문 버퍼(운영용, 최근 채팅 묶음) — 휘발
   - **단기기억** = 발화자별 사실/간단한 대화 정보 (분 단위로 유지)
   - **장기기억** = 거시적 주제/상황 (잘 안 변함)
   → tick 출력의 remember를 short(발화자 사실)/long(상황)으로 분리.
5. **프롬프트 파일 정리**: prompts/ 가 너무 많고 복잡. 필요한 것만 남겨 단순화(2~3개로).
   (현재 5개: template, roleplay_info, topic_setting, example_dialogue, live_rules)

## 제안 순서 (천천히, 하나씩)
- A. 출력 cadence(speak-loop) — ✅ 완료 (commit b154eb7). tick 폐기, speak_interval/idle_initiate.
- B. 답변 맥락화(이름/되짚기) + 스타일 — ✅ 완료 (commit 97d1883). live_rules에 반영.
- C. 메모리 3층 재정의 — ✅ 완료(미커밋). short_term.json=원문버퍼 / facts.json=단기(발화자 사실, TTL 10분) / long_term.json=장기(상황).
     speak 출력 remember→facts/situation 분리. 프롬프트에 {{speaker_facts}} 주입. config: facts_ttl_sec/facts_max.
- D. prompts 파일 단순화 — ✅ 완료(미커밋). 5개→3개.
     template.txt(조립골격)는 코드(get_assembled_prompt)로 흡수, topic_setting→roleplay_info 병합,
     옛 chat_history.txt/memory.txt 제거. 남은 prompts/: roleplay_info(페르소나+화제) / live_rules(규칙) / example_dialogue(예시).
     동적 주입(분위기/장기·단기기억)은 코드에서 처리.

## ③ A~D 모두 완료. 남은 것
- 사용자가 말한 "살짝 수정하고 싶은 부분" 듣기.
- (미해결) 페르소나 roleplay_info "대화 방식: 시청자의 마지막 말에 가장 먼저 반응한다" ↔ live_rules 선별 충돌. 필요시 그 줄만 손보기.
- cadence 값(speak_interval 10초 / idle 25초) 실사용 튜닝.
