# 라이브 채팅 반응형 음악 에이전트 — 설계

대화 분위기에 맞춰 노래를 자동으로 골라 트는 방송 AI. 입력은 **1:다수의 짧은 라이브 채팅**이고,
모든 입력에 답하지 않고 선별 반응한다. 곡이 끝나기 전 지금 분위기에 맞는 다음 곡을 미리 고른다.

## 실행 모델 — 백그라운드 루프 2개

```
[채팅 수집]  POST /ingest {user,text}  →  buffer.json append (+ accept_live_chat 게이트)
                                              │
[채팅 tick]  (tick_seconds OR pending tick_messages개)  →  LLM 1회 → {respond, reply, mood, remember}
                                              │            침묵/응답(latest_response)  buffer/long_term
[음악 루프]  (_dj_enabled 일 때, 3초마다)
   - now_playing 없음        → 첫 곡 선정·재생
   - 종료 prefetch_lead초 전 → 다음 곡 미리 선정 → playback.next + broadcast.next_title
   - 종료 시점               → next 곡을 yt /play(mpv) 재생, now_playing 회전
```

## 파일 레이아웃 — 동적 JSON / 정적 txt

```
backend/
├── prompts/   ← 정적, 사람이 편집 (template/roleplay_info/topic_setting/example_dialogue .txt)
├── state/     ← 동적, 기계 관리 (JSON, gitignore, /new-chat 초기화)
│   ├── buffer.json  long_term.json  playback.json
├── memory_store.py   ← state/ JSON 을 다루는 유일한 모듈 (락으로 동시성 보호)
├── recommender_bridge.py  ← 루트 추천엔진 지연 로딩
└── main.py           ← 엔드포인트 + 백그라운드 루프
```

## JSON 스키마
- **buffer.json**: `{messages:[{ts,user,text,role}], current_mood:[], last_response_ts}`
  - role: "viewer"(→user) | "assistant". evict: ts가 ttl 초과 또는 개수 > max → 오래된 것부터 제거.
- **long_term.json**: `{stream_context:[문장...], updated_at}` — tick의 remember + 단기 evict 요약이 채움. `{{memory}}`로 주입.
- **playback.json**: `{now_playing:{title,artist,started_at,duration_sec}, next:{...}, history:[]}`. duration_sec는 추천곡 duration_ms 기반.

## 음악 채널 (music_source)
- `"dj"`    : HA가 고른 추천곡을 **yt 서비스(mpv)로 서버에서 재생**. broadcast: music_title/next_title/music_source="dj".
- `"upload"`: 운영자가 올린 로컬 파일을 **display 브라우저 audio(music_url)로 재생** (TEAM 경로).
- 둘은 배타적: 자동 DJ는 `_dj_enabled`(/dj/start·/dj/stop)로만 켜고, 끄면 기존 업로드 경로가 그대로 동작.

## 엔드포인트
- 채팅: `POST /chat`(is_admin 1:1 테스트), `POST /ingest`(라이브, accept_live_chat 게이트), `POST /new-chat`(초기화)
- 추천: `POST /mood-keywords`, `POST /recommend`
- DJ: `POST /dj/start`, `POST /dj/stop`, `GET /dj/status`
- 방송: `GET/POST /broadcast-settings`, `GET /latest-response`, 프롬프트 `GET /prompts` `GET/POST /prompt`

## config.json (튜닝)
`model, temperature, summary_model, keyword_temperature, buffer_ttl_sec, buffer_max, tick_seconds, tick_messages, prefetch_lead_sec, default_song_sec`

## 검증
- `python test_chat.py` : 1:1 채팅 + 키워드 + 추천
- `python test_stream.py` : 라이브 채팅 흘려보내며 침묵/응답 선별
- `python test_live.py` : 대화형, !음악으로 추천·재생
- 서버 + `/ingest`·`/dj/start` : 실제 흐름

## 구현 단계
- Phase 1 (JSON 메모리) — ✅
- Phase 2 (채팅 tick/선별응답) — ✅
- Phase 3 (자동 DJ 음악 루프) — ✅ (기본형; 아래 한계 참고)
- Phase 4 (다듬기) — 예정

### 알려진 한계 / 다음
- dj 모드의 진행바(current_time/duration)는 display가 브라우저 audio 기준으로 보고하므로 mpv 재생과 어긋남 → 표시는 곡 제목 위주. (개선: display가 music_source="dj"면 보고 생략하거나 백엔드가 경과시간 계산)
- 곡 종료 타이밍은 데이터셋 duration_ms 기반(유튜브 실제 길이와 다를 수 있음) → 추후 yt /status 폴링으로 정밀화 가능.
- long_term 무한 증가 → 주기적 압축(Phase 4).
