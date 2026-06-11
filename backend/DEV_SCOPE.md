# 개발 범위 / 소유권 / 진행 상황 — 충돌 방지 + 현황 문서

> 목적: 같은 파일(특히 `main.py`)을 동시에 고쳐 충돌하는 일을 막고, **누가 뭘 했고 다음에 뭘 할지**를 한 곳에 둔다.
> 개발자 표기: **HA** = AI 페르소나·메모리·음악 추천/DJ 백엔드 담당. **TEAM** = 방송 화면/조작 UI·송출 상태·yt 서비스·추천 코어.

---

## 1. TEAM vs HA — 무엇을 하려는지 비교

| 영역 | TEAM이 하려는 것 | HA가 하려는 것 | 충돌? → 택한 방향 |
|---|---|---|---|
| 채팅 입력 | 조작 패널에서 `/chat`(is_admin) 관리자 테스트 + `accept_live_chat` 토글 | 라이브 1:다수 채팅을 `/ingest`→tick으로 선별 응답 | **공존**. /chat=관리자 1:1, /ingest=라이브. accept_live_chat 게이트는 둘 다 존중 |
| 기억 | (특별히 없음 — 기존 txt) | 단기/장기기억을 JSON으로 분리·자동관리 | **HA 방향 채택**(txt는 파싱 취약). 페르소나 txt는 그대로 |
| 음악 재생 | 운영자가 로컬 파일 업로드 → 브라우저 audio (`music_url`) | 추천곡을 yt(mpv)로 서버 재생 + 자동 큐잉 | **둘 다 유지**. `music_source`로 분기: "upload"=TEAM, "dj"=HA |
| 다음 곡 | (수동) | 곡 끝 60초 전 분위기로 자동 선곡 | **HA가 추가**(자동 DJ). 운영자는 /dj/stop으로 끄고 수동 업로드 사용 |
| 송출 표시 | `broadcast_settings`(display 폴링) 소유 | 곡/말풍선 정보를 broadcast_settings에 반영만 | **TEAM 소유 유지**. HA는 `set_broadcast()`로 합의된 필드만 갱신 |

**효율 판단으로 택한 방향**: 기억은 JSON(HA), 음악은 dj/upload 이중 채널 공존, 채팅은 관리자(/chat)·라이브(/ingest) 분리. → 서로의 기존 작업을 안 버리고 합쳤다.

---

## 2. 소유권 — 파일/영역

| 파일·영역 | 주인 | 비고 |
|---|---|---|
| `memory_store.py`, `state/*.json` | **HA** | 동적 상태 전담 |
| `recommender_bridge.py` | **HA** | 추천엔진 연결 |
| `DESIGN.md`, `DEV_SCOPE.md`, `test_chat/live/stream.py` | **HA** | 문서·검증 |
| `prompts/*.txt`, `config.json` | 공유 | 변경 시 공지 |
| `recommender.py`, `train_model.py`, `models/`, 루트 데이터 | **TEAM** | HA는 import만 |
| `yt/` (:8001) | **TEAM** | HA는 HTTP(`/play`,`/stop`)로만 호출 |
| `frontend/`, `display/` (React) | **TEAM** | UI |

### `main.py` 섹션별 주인 (배너 주석 `# ===== [HA]/[TEAM] =====` 로 표시)
| 섹션 | 주인 |
|---|---|
| `broadcast_settings`, `SettingsUpdate`, `/broadcast-settings`, `accept_live_chat`, `is_admin` 게이트 | **TEAM** |
| `/prompts`, `/prompt`, `/` | 공유 |
| `/chat`(JSON 기억), `/ingest`, 채팅 tick, `/new-chat` | **HA** |
| `/mood-keywords`, `/recommend`, `select_mood_keywords`, `song_to_dict` | **HA** |
| 자동 DJ(`/dj/*`, `music_loop`, `play_song`, `yt_play/stop`) | **HA** |
| `get_assembled_prompt`, `call_gpt`, `read_local_context`, `set_broadcast` | **HA**(공용 헬퍼) |

---

## 3. 인터페이스(서로 닿는 지점) — 여기만 합의하면 충돌 없음
1. **AI 응답 → 화면**: HA가 `latest_response={content,timestamp}` 갱신, display가 `/latest-response`로 읽음.
2. **재생 상태**: HA 내부 상태는 `state/playback.json`. 화면 표시는 `broadcast_settings`의 `music_title/next_title/music_source`를 `set_broadcast()`로 갱신.
3. **음악 채널**: `music_source` "dj"(HA/mpv) vs "upload"(TEAM/브라우저). 배타적. 자동 DJ는 `/dj/start`·`/dj/stop`로만.
4. **실제 재생**: HA는 yt 서비스 `POST :8001/play {title,artist}` 로만 재생 요청.

> ❗TEAM 협조 요청: 조작 패널에서 **로컬 음악 업로드 시 `music_source:"upload"` 도 함께 POST** 하면 dj/upload 구분이 더 깔끔해짐(현재는 _dj_enabled 플래그로만 배타 처리).

---

## 4. 이번에 HA가 한 일 (reconciliation 로그)

반쯤 머지된 `main.py`(HA 작업 일부 유실 + TEAM의 accept_live_chat/is_admin 잔존)를 하나로 재정리:
- **재생성**: `memory_store.py`, `DESIGN.md`, `DEV_SCOPE.md`, `test_stream.py` (리버트로 유실됨)
- **main.py 통합 재작성**: TEAM(`accept_live_chat`,`is_admin`,broadcast) + HA(Phase 1 JSON기억 / Phase 2 tick / Phase 3 자동DJ). 섹션 배너로 소유권 표시.
- **Phase 1**: `/chat`·`read_local_context`·`{{memory}}`를 JSON(state/) 기반으로. 옛 `chat_history.txt`/`memory.txt` 미사용.
- **Phase 2**: `/ingest` + 백그라운드 tick + 선별 응답(JSON 출력). accept_live_chat 게이트 반영.
- **Phase 3**: `music_source` dj/upload 이중 채널. `/dj/start|stop|status`, `music_loop`(60초 전 프리페치→회전), yt 연동. `song_to_dict`에 duration_sec 추가.
- **config.json** 키 정리, `.gitignore`에 state 재추가.

---

## 5. 다음 계획
- **Phase 4 다듬기**: long_term 주기적 압축, topic-drift 단기 evict(옵션), dj 진행바 정합(아래).
- **dj 진행바 정합**: display가 `music_source=="dj"`면 current_time 보고를 생략하거나, 백엔드가 `now-started_at`로 진행률 계산해 broadcast에 반영.
- **종료 타이밍 정밀화**: 데이터셋 duration_ms 대신 yt `/status` 폴링으로 실제 곡 종료 감지.
- **TEAM 협의 필요**: (1) 업로드 시 `music_source:"upload"` 전송, (2) 조작 패널에 `/dj/start|stop` 버튼 추가, (3) live_chat 스크래퍼가 `/ingest` 호출하도록 연결.

---

## 협업 규칙 (요약)
- 작업 전 위 표에서 **내 영역인지** 확인. 남의 영역이면 먼저 알린다.
- `main.py`는 **자기 배너 섹션만**. 공유(config/prompts/prompt API)는 변경 시 공지.
- 인터페이스 4가지는 **합의 후** 변경. 새 파일은 소유권 표에 한 줄 추가.
