import React, { useState, useEffect, useRef } from 'react';
import { Music, Sparkles, MessageSquare, Play, Volume2, Move, Clock } from 'lucide-react';
import './App.css';
import VrmAvatar from './VrmAvatar';

// 3D 아바타 경로. display/public/Hayakawa_Aoi.vrm 가 있으면 3D 모델을,
// 없으면 2D 이미지(/avatar.png)로 자동 폴백한다.
const VRM_URL = '/Hayakawa_Aoi.vrm';

// 컨트롤러가 배경을 지정하지 않았을 때 쓰는 기본 배경. display/public/background.jpg.
const DEFAULT_BG = '/background.jpg';

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

// 반응 표정을 neutral로 되돌리기 전까지 유지하는 시간(ms).
const EXPRESSION_HOLD_MS = 5000;

// 백엔드가 emotion 필드를 주지 않을 때(구버전 백엔드 등)만 쓰는 답변 텍스트 기반 감정 추측.
function guessEmotion(text) {
  const t = text || '';
  if (/[ㅠㅜ]|슬프|미안|죄송|아쉽|속상|눈물|😢|😭/.test(t)) return 'sad';
  if (/화나|짜증|화가|분노|😠|😡/.test(t)) return 'angry';
  if (/헐|대박|놀라|세상에|뭐라고|믿기지|😮|😲|!\?|\?!/.test(t)) return 'surprised';
  if (/ㅎㅎ|ㅋㅋ|좋아|기뻐|행복|최고|즐거|신나|반가|😊|😄|😁|❤️/.test(t)) return 'happy';
  if (/괜찮|편안|여유|쉬어|차분|평온|☺️/.test(t)) return 'relaxed';
  return 'neutral';
}

function App() {
  const [latestMessage, setLatestMessage] = useState("메시지를 기다리는 중...");
  const [lastMsgTimestamp, setLastMsgTimestamp] = useState(0);
  const [hasReceivedMessage, setHasReceivedMessage] = useState(false);

  // 아바타 표정. 새 메시지가 오면 답변 감정으로 설정하고, 잠시 유지 후 neutral로 되돌린다.
  const [expression, setExpression] = useState('neutral');
  const expressionTimer = useRef(null);

  // 개발용 미리보기: 0~5 키로 라이브 채팅 없이 표정을 강제 전환.
  // (0 neutral, 1 happy, 2 sad, 3 angry, 4 surprised, 5 relaxed)
  useEffect(() => {
    const names = ['neutral', 'happy', 'sad', 'angry', 'surprised', 'relaxed'];
    const onKey = (e) => {
      const n = parseInt(e.key, 10);
      if (!Number.isNaN(n) && n >= 0 && n < names.length) setExpression(names[n]);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Broadcast Settings
  const [settings, setSettings] = useState({
    bg_image: null,
    music_url: null,
    music_title: "현재 재생 중인 음악이 없습니다",
    font_size: 24,
    mode: 'live',
    is_playing: true,
    current_time: 0,
    duration: 0,
    show_character: true,
    accept_live_chat: true,
    timestamp: 0
  });

  // Layout State (Saved in LocalStorage)
  const [bubbleLayout, setBubbleLayout] = useState(() => {
    const saved = localStorage.getItem('bubbleLayout');
    return saved ? JSON.parse(saved) : { x: 50, y: 30, w: 400, h: 'auto' };
  });
  const [charLayout, setCharLayout] = useState(() => {
    const saved = localStorage.getItem('charLayout');
    return saved ? JSON.parse(saved) : { x: 50, y: 70, w: 180, h: 180 };
  });

  const [isAudioStarted, setIsAudioStarted] = useState(false);
  const audioRef = useRef(null);
  const [currentMusicUrl, setCurrentMusicUrl] = useState(null);

  // .vrm 파일이 실제로 있을 때만 3D 아바타를 쓰고, 없으면 2D 이미지로 폴백한다.
  // 마운트 시 한 번 확인.
  const [use3D, setUse3D] = useState(false);
  useEffect(() => {
    let cancelled = false;
    fetch(VRM_URL, { method: 'HEAD' })
      .then((res) => {
        const ok = res.ok && !(res.headers.get('content-type') || '').includes('text/html');
        if (!cancelled) setUse3D(ok);
      })
      .catch(() => { if (!cancelled) setUse3D(false); });
    return () => { cancelled = true; };
  }, []);

  // Drag & Resize State
  const [dragging, setDragging] = useState(null);
  const [offset, setOffset] = useState({ x: 0, y: 0 });

  // Update backend with current playback status
  // 업로드(로컬 파일) 재생일 때만 브라우저 <audio>의 시간을 보고한다.
  // DJ 추천곡은 yt/mpv가 서버에서 재생하므로(music_url 없음) 시간을 보고하면 안 된다.
  const reportPlaybackStatus = async () => {
    if (!audioRef.current || !isAudioStarted || !currentMusicUrl) return;
    try {
      await fetch(`${API_BASE}/broadcast-settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          current_time: audioRef.current.currentTime,
          duration: audioRef.current.duration || 0
        }),
      });
    } catch (e) {}
  };

  // Poll for messages and settings
  useEffect(() => {
    const poll = async () => {
      try {
        const msgRes = await fetch(`${API_BASE}/latest-response`);
        if (msgRes.ok) {
          const msgData = await msgRes.json();
          if (msgData.timestamp > lastMsgTimestamp && msgData.content) {
            setLatestMessage(msgData.content);
            setLastMsgTimestamp(msgData.timestamp);
            setHasReceivedMessage(true);

            // 답변 감정으로 표정을 바꾸고, 일정 시간 뒤 neutral로 복귀.
            const emotion = msgData.emotion || guessEmotion(msgData.content);
            setExpression(emotion);
            if (expressionTimer.current) clearTimeout(expressionTimer.current);
            expressionTimer.current = setTimeout(
              () => setExpression('neutral'),
              EXPRESSION_HOLD_MS
            );
          }
        }

        const setRes = await fetch(`${API_BASE}/broadcast-settings`);
        if (setRes.ok) {
          const setData = await setRes.json();
          
          // 업로드(로컬 파일) 재생일 때만 브라우저 audio를 제어한다.
          // DJ 추천곡은 yt/mpv가 서버에서 재생하므로 브라우저 audio는 관여하지 않는다.
          if (audioRef.current && isAudioStarted && setData.music_url) {
            if (setData.is_playing && audioRef.current.paused) {
              audioRef.current.play().catch(e => console.log(e));
            } else if (!setData.is_playing && !audioRef.current.paused) {
              audioRef.current.pause();
            }

            // Handle Seeking from Controller (if diff > 3s)
            if (Math.abs(setData.current_time - audioRef.current.currentTime) > 3) {
                audioRef.current.currentTime = setData.current_time;
            }
          }

          if (setData.timestamp > settings.timestamp) {
            setSettings(setData);
            if (setData.music_url && setData.music_url !== currentMusicUrl) {
              // 새 업로드 파일 로드
              setCurrentMusicUrl(setData.music_url);
              if (audioRef.current) {
                audioRef.current.src = setData.music_url;
                if (isAudioStarted && setData.is_playing) audioRef.current.play().catch(e => console.log(e));
              }
            } else if (!setData.music_url && currentMusicUrl) {
              // DJ 전환 등으로 음원 URL이 비워짐 → 업로드 오디오를 멈춰 이중재생 방지
              setCurrentMusicUrl(null);
              if (audioRef.current) {
                audioRef.current.pause();
                audioRef.current.removeAttribute('src');
                audioRef.current.load();
              }
            }
          }
        }
      } catch (err) { console.error("Polling error:", err); }
    };

    const interval = setInterval(poll, 1000);
    const reportInterval = setInterval(reportPlaybackStatus, 2000);
    return () => {
        clearInterval(interval);
        clearInterval(reportInterval);
    };
  }, [lastMsgTimestamp, settings.timestamp, isAudioStarted, currentMusicUrl]);

  // Mouse Event Handlers
  const handleMouseDown = (e, type) => {
    if (e.button !== 0) return;
    setDragging(type);
    const rect = e.currentTarget.getBoundingClientRect();
    setOffset({ x: e.clientX - rect.left, y: e.clientY - rect.top });
    e.stopPropagation();
  };

  const handleMouseMove = (e) => {
    if (!dragging) return;
    if (dragging === 'bubble') {
      const x = ((e.clientX - offset.x) / window.innerWidth) * 100;
      const y = ((e.clientY - offset.y) / window.innerHeight) * 100;
      setBubbleLayout(prev => ({ ...prev, x, y }));
    } else if (dragging === 'char') {
      const x = ((e.clientX - offset.x) / window.innerWidth) * 100;
      const y = ((e.clientY - offset.y) / window.innerHeight) * 100;
      setCharLayout(prev => ({ ...prev, x, y }));
    } else if (dragging === 'resize-bubble') {
      const bubble = document.getElementById('draggable-bubble').getBoundingClientRect();
      const w = Math.max(200, e.clientX - bubble.left);
      const h = Math.max(100, e.clientY - bubble.top);
      setBubbleLayout(prev => ({ ...prev, w, h }));
    } else if (dragging === 'resize-char') {
      const char = document.getElementById('draggable-char').getBoundingClientRect();
      const size = Math.max(80, e.clientX - char.left);
      setCharLayout(prev => ({ ...prev, w: size, h: size }));
    }
  };

  const handleMouseUp = () => {
    if (dragging) {
      localStorage.setItem('bubbleLayout', JSON.stringify(bubbleLayout));
      localStorage.setItem('charLayout', JSON.stringify(charLayout));
    }
    setDragging(null);
  };

  useEffect(() => {
    if (dragging) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    }
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [dragging, offset, bubbleLayout, charLayout]);

  return (
    <div 
      className={`display-container mode-${settings.mode}`}
      style={{ 
        backgroundImage: `url(${settings.bg_image || DEFAULT_BG})`,
        backgroundSize: 'cover',
        backgroundPosition: 'center'
      }}
    >
      <div className="bg-overlay"></div>
      
      {!isAudioStarted && (
        <div className="audio-start-overlay" onClick={() => setIsAudioStarted(true)}>
          <div className="start-btn">
            <Play size={40} fill="currentColor" />
            <span>방송 환경 준비 완료 (클릭하여 오디오 활성화)</span>
          </div>
        </div>
      )}

      <audio ref={audioRef} loop />

      {settings.mode === 'live' ? (
        <div className="scene-live animate-fade-in">
          {/* Draggable Speech Bubble */}
          <div 
            id="draggable-bubble"
            className={`speech-bubble draggable ${hasReceivedMessage ? 'active' : 'waiting'} ${dragging === 'bubble' ? 'dragging' : ''}`}
            onMouseDown={(e) => handleMouseDown(e, 'bubble')}
            style={{
              left: `${bubbleLayout.x}%`,
              top: `${bubbleLayout.y}%`,
              width: typeof bubbleLayout.w === 'number' ? `${bubbleLayout.w}px` : bubbleLayout.w,
              height: typeof bubbleLayout.h === 'number' ? `${bubbleLayout.h}px` : bubbleLayout.h,
              position: 'absolute',
              cursor: 'grab'
            }}
          >
            <div className="bubble-content" style={{ fontSize: `${settings.font_size}px` }}>
              <MessageSquare className="bubble-icon" size={settings.font_size * 0.8} />
              <p>{latestMessage}</p>
            </div>
            <div className="bubble-tail"></div>
            <div className="resize-handle" onMouseDown={(e) => handleMouseDown(e, 'resize-bubble')}></div>
            <div className="drag-icon-hint"><Move size={14} /></div>
          </div>

          {/* Draggable Character */}
          {settings.show_character !== false && (
            <div 
              id="draggable-char"
              className={`character-container draggable animate-float ${dragging === 'char' ? 'dragging' : ''}`}
              onMouseDown={(e) => handleMouseDown(e, 'char')}
              style={{
                left: `${charLayout.x}%`,
                top: `${charLayout.y}%`,
                width: `${charLayout.w}px`,
                height: `${charLayout.h}px`,
                position: 'absolute',
                cursor: 'grab'
              }}
            >
              <div className={`character-body image-avatar ${hasReceivedMessage ? 'happy' : ''}`} style={{ width: '100%', height: '100%' }}>
                {use3D ? (
                  <VrmAvatar
                    url={VRM_URL}
                    expression={expression}
                    onError={() => setUse3D(false)}
                  />
                ) : (
                  <img src="/avatar.png" alt="Student Avatar" className="avatar-img" />
                )}
              </div>
              <div className="character-shadow" style={{ width: `${charLayout.w * 0.6}px` }}></div>
              <div className="resize-handle char-resize" onMouseDown={(e) => handleMouseDown(e, 'resize-char')}></div>
              <div className="drag-icon-hint char-hint"><Move size={14} /></div>
            </div>
          )}
        </div>
      ) : (
        /* Wait Mode Scene */
        <div className="scene-wait animate-fade-in">
          <div className="wait-content">
            <div className="wait-status">
              <Clock className="animate-spin-slow" size={32} />
              <span>STARTING SOON</span>
            </div>
            <h1 className="wait-title">곧 방송이 시작됩니다!</h1>
            <div className="wait-music-info glass-card">
              <div className="music-icon-ring animate-pulse">
                <Music size={40} />
              </div>
              <div className="music-details">
                <span className="now-playing-label">NOW PLAYING</span>
                <h2 className="music-title-large">{settings.music_title}</h2>
                <div className="wait-progress-container">
                  <div className="wait-progress-bar" style={{ width: `${(settings.current_time / settings.duration) * 100}%` }}></div>
                </div>
              </div>
            </div>
            <div className="social-hints">
              <div className="hint-item"><Sparkles size={16} /> <span>대화하며 기다려주세요!</span></div>
            </div>
          </div>
        </div>
      )}

      {/* Music Bar (Live Scene Only) */}
      {settings.mode === 'live' && (
        <div className="music-bar-container fixed-bottom">
          <div className={`music-card ${settings.is_playing ? 'playing' : ''}`}>
            <div className="music-visualizer">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="bar" style={{ animationDelay: `${i * 0.2}s` }}></div>
              ))}
            </div>
            <div className="music-info-wrap">
              <div className="music-header">
                <Music size={14} className="text-accent" />
                <span className="label">NOW PLAYING</span>
              </div>
              <div className="music-title-scroll">
                <div className="marquee-inner">
                  <span>{settings.music_title}</span>
                  <span>{settings.music_title}</span>
                </div>
              </div>
              <div className="progress-container">
                <div className="progress-bar" style={{ width: `${(settings.current_time / settings.duration) * 100}%` }}></div>
              </div>
              {settings.next_title && (
                <div className="next-up" style={{ fontSize: '11px', opacity: 0.65, marginTop: '4px' }}>
                  다음 곡 ▸ {settings.next_title}
                </div>
              )}
            </div>
            <div className="audio-status">
              <Volume2 size={18} className={settings.is_playing ? "text-accent" : "text-muted"} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
