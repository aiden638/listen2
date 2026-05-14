import React, { useState, useEffect, useRef } from 'react';
import { Music, Sparkles, MessageSquare, Play, Volume2, Move, Clock } from 'lucide-react';
import './App.css';

const API_BASE = "http://localhost:8000";

function App() {
  const [latestMessage, setLatestMessage] = useState("메시지를 기다리는 중...");
  const [lastMsgTimestamp, setLastMsgTimestamp] = useState(0);
  const [hasReceivedMessage, setHasReceivedMessage] = useState(false);

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

  // Drag & Resize State
  const [dragging, setDragging] = useState(null);
  const [offset, setOffset] = useState({ x: 0, y: 0 });

  // Update backend with current playback status
  const reportPlaybackStatus = async () => {
    if (!audioRef.current || !isAudioStarted) return;
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
          }
        }

        const setRes = await fetch(`${API_BASE}/broadcast-settings`);
        if (setRes.ok) {
          const setData = await setRes.json();
          
          // Handle Play/Pause
          if (audioRef.current && isAudioStarted) {
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
              setCurrentMusicUrl(setData.music_url);
              if (audioRef.current) {
                audioRef.current.src = setData.music_url;
                if (isAudioStarted && setData.is_playing) audioRef.current.play().catch(e => console.log(e));
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
        backgroundImage: settings.bg_image ? `url(${settings.bg_image})` : 'none',
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
              <div className="character-body" style={{ width: '100%', height: '100%', borderRadius: `${charLayout.w * 0.25}px` }}>
                <div className={`eye left ${hasReceivedMessage ? 'happy' : ''}`} style={{ top: `${charLayout.h * 0.33}px`, left: `${charLayout.w * 0.25}px` }}></div>
                <div className={`eye right ${hasReceivedMessage ? 'happy' : ''}`} style={{ top: `${charLayout.h * 0.33}px`, right: `${charLayout.w * 0.25}px` }}></div>
                <div className={`mouth ${hasReceivedMessage ? 'happy' : ''}`} style={{ bottom: `${charLayout.h * 0.33}px`, width: `${charLayout.w * 0.2}px` }}></div>
                <div className="blush" style={{ top: `${charLayout.h * 0.5}px`, width: `${charLayout.w * 0.15}px` }}></div>
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
