import React, { useState, useEffect, useRef } from 'react';
import { 
  Send, Sparkles, MessageSquare, Image as ImageIcon, Music, 
  Play, Pause, Monitor, Tv, Clock, Type, Layout, Volume2, ListMusic, User
} from 'lucide-react';
import './index.css';

const API_BASE = "http://localhost:8000";

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [moodInput, setMoodInput] = useState(''); // 운영자가 첫 곡 분위기를 직접 지정할 때 입력

  // Layout Resizing State
  const [chatWidth, setChatWidth] = useState(window.innerWidth * 0.35);
  const [isResizing, setIsResizing] = useState(false);
  const [tileSize, setTileSize] = useState(260);

  // Broadcast Settings State
  const [settings, setSettings] = useState({
    bg_image: '',
    music_url: '',
    music_title: '현재 로드된 음악 없음',
    font_size: 24,
    mode: 'live',
    is_playing: true,
    current_time: 0,
    duration: 0,
    show_character: true,
    accept_live_chat: true
  });

  const chatMessagesRef = useRef(null);

  useEffect(() => {
    fetchInitialSettings();
    const interval = setInterval(fetchInitialSettings, 1000); // 1초마다 동기화
    
    const handleMouseMove = (e) => {
      if (!isResizing) return;
      const newWidth = e.clientX - 24; 
      if (newWidth > 300 && newWidth < window.innerWidth - 800) {
        setChatWidth(newWidth);
      }
    };

    const handleMouseUp = () => {
      setIsResizing(false);
      document.body.style.cursor = 'default';
    };

    if (isResizing) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'col-resize';
    }

    return () => {
      clearInterval(interval);
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing]);

  const fetchInitialSettings = async () => {
    try {
      const res = await fetch(`${API_BASE}/broadcast-settings`);
      if (res.ok) {
        const data = await res.json();
        setSettings(data);
      }
    } catch (e) { console.error(e); }
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;
    const userMsg = { role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: input, is_admin: true }),
      });
      const data = await res.json();
      setMessages(prev => [...prev, { role: 'ai', content: data.response }]);
    } catch (e) { console.error(e); } finally { setIsLoading(false); }
  };

  const handleUpdateBroadcastSettings = async (updates) => {
    try {
      await fetch(`${API_BASE}/broadcast-settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      });
      setSettings(prev => ({ ...prev, ...updates }));
    } catch (e) { console.error(e); }
  };

  const handleFileUpload = (e, type) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async (event) => {
      if (type === 'image') {
        handleUpdateBroadcastSettings({ bg_image: event.target.result });
      } else {
        // 로컬 파일(테스트) 재생 모드로 전환. 자동 DJ(mpv)와 겹치지 않도록 DJ를 먼저 끈 뒤 전환.
        await handleStopDj();
        handleUpdateBroadcastSettings({
          music_url: event.target.result,
          music_title: file.name,
          music_source: 'upload',
          current_time: 0,
          is_playing: false // 자동 재생 방지
        });
      }
    };
    reader.readAsDataURL(file);
  };

  // 자동 DJ 시작. keywords를 주면 운영자가 지정한 분위기로 첫 곡을 시작한다(없으면 대화 맥락 기반).
  // 업로드 파일은 끄고 DJ로 전환.
  const handleStartDj = async (keywords) => {
    try {
      // display의 브라우저 audio가 업로드 파일을 계속 틀지 않도록 음원 URL을 비운다.
      handleUpdateBroadcastSettings({ music_url: '', music_source: 'dj' });
      const body = (Array.isArray(keywords) && keywords.length) ? { keywords } : {};
      await fetch(`${API_BASE}/dj/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    } catch (e) { console.error(e); }
  };

  // 자동 DJ 중지
  const handleStopDj = async () => {
    try {
      await fetch(`${API_BASE}/dj/stop`, { method: 'POST' });
    } catch (e) { console.error(e); }
  };

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="layout-split">
      {/* Left: Chat Control */}
      <section className="chat-large-area glass-card" style={{ width: `${chatWidth}px` }}>
        <div className="section-header">
          <div className="title-group">
            <MessageSquare size={20} className="text-accent" />
            <h1>라이브 채팅 컨트롤</h1>
          </div>
          <div className="status-badge">
            <div className="status-dot"></div>
            <span>ONLINE</span>
          </div>
        </div>
        
        <div className="chat-messages-scroll" ref={chatMessagesRef}>
          {messages.length === 0 && (
            <div className="empty-state">
              <Sparkles size={48} className="text-dim" />
              <p>시청자와의 실시간 소통을 시작하세요!</p>
            </div>
          )}
          {messages.map((msg, i) => (
            <div key={i} className={`message-box ${msg.role}`}>
              <div className="msg-header">{msg.role === 'user' ? 'ME' : 'AI BROADCAST'}</div>
              <div className="msg-bubble">{msg.content}</div>
            </div>
          ))}
          {isLoading && <div className="typing-dots-mini">...</div>}
        </div>

        <form className="chat-input-footer" onSubmit={handleSendMessage}>
          <input 
            type="text" 
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="메시지 입력..."
          />
          <button type="submit" disabled={isLoading} className="send-btn-circle">
            <Send size={20} />
          </button>
        </form>
      </section>

      {/* Resize Handle */}
      <div 
        className={`resizer-handle ${isResizing ? 'active' : ''}`}
        onMouseDown={() => setIsResizing(true)}
      >
        <div className="resizer-line"></div>
      </div>

      {/* Right: Modular Grid Area */}
      <main className="right-dashboard-area">
        <div className="modular-grid" style={{ '--tile-size': `${tileSize}px` }}>
          
          {/* 1. Mode Tile (1x1) */}
          <div className="tile-node glass-card">
            <div className="tile-header-node"><Monitor size={14} /> <span>장면 모드</span></div>
            <div className="tile-content-node">
              <div className="mode-stack">
                <button 
                  className={`mode-btn-node ${settings.mode === 'wait' ? 'active' : ''}`}
                  onClick={() => handleUpdateBroadcastSettings({ mode: 'wait' })}
                >
                  대기 모드
                </button>
                <button 
                  className={`mode-btn-node ${settings.mode === 'live' ? 'active live' : ''}`}
                  onClick={() => handleUpdateBroadcastSettings({ mode: 'live' })}
                >
                  라이브 송출
                </button>
              </div>
            </div>
          </div>

          {/* 2. Font Tile (1x1) */}
          <div className="tile-node glass-card">
            <div className="tile-header-node"><Type size={14} /> <span>자막 크기</span></div>
            <div className="tile-content-node">
              <div className="font-node-val">{settings.font_size}<span>px</span></div>
              <input 
                type="range" min="16" max="60" value={settings.font_size} 
                onChange={(e) => handleUpdateBroadcastSettings({ font_size: parseInt(e.target.value) })}
              />
            </div>
          </div>

          {/* 3. BG Tile (1x1) */}
          <div className="tile-node glass-card">
            <div className="tile-header-node"><ImageIcon size={14} /> <span>배경 소스</span></div>
            <div className="tile-content-node media-container-node">
              {settings.bg_image ? (
                <div className="preview-img-node" style={{ backgroundImage: `url(${settings.bg_image})` }}>
                  <label className="edit-trigger"><ImageIcon size={14} /><input type="file" hidden accept="image/*" onChange={(e) => handleFileUpload(e, 'image')} /></label>
                </div>
              ) : (
                <label className="upload-placeholder-node">
                  <ImageIcon size={28} />
                  <span>배경 선택</span>
                  <input type="file" hidden accept="image/*" onChange={(e) => handleFileUpload(e, 'image')} />
                </label>
              )}
            </div>
          </div>

          {/* 4. BGM Source Load Tile (1x1) - Separate from control */}
          <div className="tile-node glass-card">
            <div className="tile-header-node"><ListMusic size={14} /> <span>BGM 선택</span></div>
            <div className="tile-content-node">
              <label className="upload-placeholder-node">
                <Music size={28} />
                <span>{settings.music_url ? "음악 변경" : "음악 로드"}</span>
                <input type="file" hidden accept="audio/*" onChange={(e) => handleFileUpload(e, 'music')} />
              </label>
            </div>
          </div>

          {/* 4-b. Auto DJ Tile (1x1) — 대화 분위기 기반 자동 선곡/재생 (yt+mpv) */}
          <div className="tile-node glass-card">
            <div className="tile-header-node"><Music size={14} /> <span>자동 DJ (분위기 선곡)</span></div>
            <div className="tile-content-node">
              <div className="visibility-control">
                <div className="visibility-btn-group">
                  <button
                    className={`vis-btn ${settings.music_source === 'dj' ? 'active show' : ''}`}
                    onClick={() => handleStartDj()}
                  >
                    시작
                  </button>
                  <button
                    className={`vis-btn ${settings.music_source !== 'dj' ? 'active hide' : ''}`}
                    onClick={handleStopDj}
                  >
                    중지
                  </button>
                </div>
                <div className="vis-hint">
                  {settings.music_source === 'dj'
                    ? '대화 분위기로 곡을 자동 선곡·재생 중'
                    : '시작하면 대화 맥락에 맞는 음악이 흐릅니다'}
                </div>
              </div>
            </div>
          </div>

          {/* 4-c. Mood Tile (1x1) — 현재 분위기 보기 + 편집 + 그 분위기로 첫 곡 시작 */}
          <div className="tile-node glass-card">
            <div className="tile-header-node"><Sparkles size={14} /> <span>분위기 (첫 곡 지정)</span></div>
            <div className="tile-content-node">
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginBottom: '8px', minHeight: '20px' }}>
                {(settings.current_mood && settings.current_mood.length > 0)
                  ? settings.current_mood.map((m, i) => (
                      <span key={i} style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '10px', background: 'rgba(255,255,255,0.12)' }}>{m}</span>
                    ))
                  : <span style={{ fontSize: '12px', opacity: 0.5 }}>아직 분위기 없음</span>}
              </div>
              <input
                type="text"
                value={moodInput}
                onChange={(e) => setMoodInput(e.target.value)}
                placeholder="예: 신남, 설렘 (쉼표로 구분)"
                style={{ width: '100%', boxSizing: 'border-box', padding: '6px 8px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.15)', background: 'rgba(0,0,0,0.2)', color: 'inherit', fontSize: '12px' }}
              />
              <div style={{ display: 'flex', gap: '6px', marginTop: '6px' }}>
                <button
                  className="vis-btn"
                  style={{ flex: 1 }}
                  onClick={() => setMoodInput((settings.current_mood || []).join(', '))}
                >
                  현재 분위기 불러오기
                </button>
                <button
                  className="vis-btn active show"
                  style={{ flex: 1 }}
                  onClick={() => handleStartDj(moodInput.split(',').map(s => s.trim()).filter(Boolean))}
                >
                  이 분위기로 시작
                </button>
              </div>
            </div>
          </div>

          {/* 5. Character Visibility Tile (1x1) */}
          <div className="tile-node glass-card">
            <div className="tile-header-node"><User size={14} /> <span>캐릭터 표시 설정</span></div>
            <div className="tile-content-node">
              <div className="visibility-control">
                <div className="visibility-btn-group">
                  <button 
                    className={`vis-btn ${settings.show_character !== false ? 'active show' : ''}`}
                    onClick={() => handleUpdateBroadcastSettings({ show_character: true })}
                  >
                    ON
                  </button>
                  <button 
                    className={`vis-btn ${settings.show_character === false ? 'active hide' : ''}`}
                    onClick={() => handleUpdateBroadcastSettings({ show_character: false })}
                  >
                    OFF
                  </button>
                </div>
                <div className="vis-hint">
                  {settings.show_character !== false ? '캐릭터가 화면에 보입니다' : '캐릭터가 숨겨졌습니다'}
                </div>
              </div>
            </div>
          </div>

          {/* 6. Live Chat Toggle Tile (1x1) */}
          <div className="tile-node glass-card">
            <div className="tile-header-node"><MessageSquare size={14} /> <span>라이브 채팅 수신 (On / Off)</span></div>
            <div className="tile-content-node">
              <div className="visibility-control">
                <div className="visibility-btn-group">
                  <button 
                    className={`vis-btn ${settings.accept_live_chat !== false ? 'active show' : ''}`}
                    onClick={() => handleUpdateBroadcastSettings({ accept_live_chat: true })}
                  >
                    ON
                  </button>
                  <button 
                    className={`vis-btn ${settings.accept_live_chat === false ? 'active hide' : ''}`}
                    onClick={() => handleUpdateBroadcastSettings({ accept_live_chat: false })}
                  >
                    OFF
                  </button>
                </div>
                <div className="vis-hint">
                  {settings.accept_live_chat !== false ? '라이브 채팅(외부/스트림)을 받습니다' : '관리자 테스트 채팅만 허용합니다'}
                </div>
              </div>
            </div>
          </div>

          {/* 5. BGM Audio Deck (3x1) - LARGE Control Tile */}
          <div className="tile-node glass-card tile-span-3">
            <div className="tile-header-node">
              <Music size={14} /> 
              <span>BGM 오디오 실시간 제어 데크</span>
              {settings.is_playing && <div className="playing-tag">PLAYING</div>}
            </div>
            <div className="tile-content-node deck-layout">
              <div className="deck-main-row">
                <button 
                  className="deck-play-btn"
                  onClick={() => handleUpdateBroadcastSettings({ is_playing: !settings.is_playing })}
                  disabled={!settings.music_url}
                >
                  {settings.is_playing ? <Pause size={32} fill="currentColor" /> : <Play size={32} fill="currentColor" />}
                </button>
                
                <div className="deck-info-area">
                  <div className="deck-title-row">
                    <span className="deck-title-text">{settings.music_title}</span>
                    <span className="deck-time-display">{formatTime(settings.current_time)} / {formatTime(settings.duration)}</span>
                  </div>
                  
                  <div className="deck-progress-wrap">
                    <input 
                      type="range" 
                      min="0" 
                      max={settings.duration || 100} 
                      value={settings.current_time}
                      onChange={(e) => handleUpdateBroadcastSettings({ current_time: parseFloat(e.target.value) })}
                      className="deck-slider"
                      disabled={!settings.music_url}
                    />
                    <div className="slider-glow" style={{ width: `${(settings.current_time / settings.duration) * 100}%` }}></div>
                  </div>

                  {/* 자동 DJ가 미리 선정해 둔 다음 곡 */}
                  {settings.next_title && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '8px', fontSize: '12px', opacity: 0.7 }}>
                      <ListMusic size={12} />
                      <span>다음 곡: {settings.next_title}</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Empty Space for Future Tiles... */}
        </div>

        {/* Tile Size Control Bar */}
        <div className="grid-controls-bar glass-card">
          <div className="control-group">
            <Layout size={16} className="text-accent" />
            <span>타일 크기 조절</span>
          </div>
          <input 
            type="range" 
            min="150" 
            max="400" 
            value={tileSize} 
            onChange={(e) => setTileSize(parseInt(e.target.value))}
            className="tile-slider"
          />
          <div className="size-label">{tileSize}px</div>
        </div>
      </main>
    </div>
  );
}

export default App;
