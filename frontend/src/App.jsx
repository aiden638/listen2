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
    show_character: true
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
        body: JSON.stringify({ message: input }),
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
    reader.onload = (event) => {
      if (type === 'image') {
        handleUpdateBroadcastSettings({ bg_image: event.target.result });
      } else {
        handleUpdateBroadcastSettings({ 
          music_url: event.target.result, 
          music_title: file.name, 
          current_time: 0, 
          is_playing: false // 자동 재생 방지
        });
      }
    };
    reader.readAsDataURL(file);
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
