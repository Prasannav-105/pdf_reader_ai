"""
tts_player.py: Interactive Offline Text-to-Speech (TTS) Audio Player.
Uses browser Web Speech API for zero-latency, cross-platform playback
with dynamic OS voice selection, speed adjustments, and full playback controls.
"""
import re
import json
import streamlit.components.v1 as components

def clean_text_for_speech(markdown_text: str) -> str:
    """Cleans markdown formatting, code blocks, and diagrams for smooth vocal narration."""
    # Remove code blocks and mermaid
    text = re.sub(r'```.*?```', ' [Code block omitted for audio lecture] ', markdown_text, flags=re.DOTALL)
    # Remove HTML tags
    text = re.sub(r'<.*?>', '', text)
    # Remove markdown headers and formatting
    text = re.sub(r'#+\s*', '', text)
    text = re.sub(r'\[(.*?)\]\(.*?\)', r'', text)
    text = re.sub(r'[*_`~]', '', text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def render_tts_player(lecture_text: str, label: str = "Textbook Audio Narration"):
    """
    Renders an interactive audio narration bar directly above the lesson.
    Allows students to choose system voices, adjust speed (0.5x - 2.0x),
    and play / pause / stop narration.
    """
    clean_speech_text = clean_text_for_speech(lecture_text)
    escaped_json_text = json.dumps(clean_speech_text)

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{
                margin: 0;
                padding: 0;
                background-color: transparent;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                color: #F8FAFC;
            }}
            .tts-container {{
                background: #111C2E;
                border: 1px solid #233876;
                border-radius: 10px;
                padding: 10px 16px;
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: 12px;
                margin-bottom: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.25);
            }}
            .tts-label {{
                display: flex;
                align-items: center;
                gap: 6px;
                font-weight: 600;
                font-size: 13px;
                color: #38BDF8;
                min-width: 140px;
            }}
            .tts-controls {{
                display: flex;
                align-items: center;
                gap: 6px;
            }}
            .tts-btn {{
                background: #1E293B;
                color: #F8FAFC;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 5px 12px;
                cursor: pointer;
                font-weight: 600;
                font-size: 12px;
                transition: all 0.2s;
                display: flex;
                align-items: center;
                gap: 4px;
            }}
            .tts-btn:hover {{
                background: #4F46E5;
                border-color: #6366F1;
                color: #FFFFFF;
            }}
            .tts-btn.active {{
                background: #059669;
                border-color: #10B981;
            }}
            .tts-select {{
                background: #1E293B;
                color: #F1F5F9;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 5px 10px;
                font-size: 12px;
                max-width: 220px;
                outline: none;
            }}
            .tts-speed-wrap {{
                display: flex;
                align-items: center;
                gap: 6px;
                font-size: 12px;
                color: #94A3B8;
            }}
            .status-indicator {{
                font-size: 11px;
                color: #94A3B8;
                margin-left: auto;
                font-style: italic;
            }}
        </style>
    </head>
    <body>
        <div class="tts-container">
            <div class="tts-label">
                <span>🎧</span>
                <span>{label}</span>
            </div>
            <div class="tts-controls">
                <button id="btnPlay" class="tts-btn" onclick="togglePlay()">▶️ Play</button>
                <button id="btnPause" class="tts-btn" onclick="togglePause()">⏸️ Pause</button>
                <button id="btnStop" class="tts-btn" onclick="stopNarration()">⏹️ Stop</button>
            </div>
            <select id="voiceSelect" class="tts-select" onchange="updateVoice()">
                <option value="">Default System Voice</option>
            </select>
            <div class="tts-speed-wrap">
                <span>Speed:</span>
                <select id="speedSelect" class="tts-select" style="max-width: 75px;" onchange="updateSpeed()">
                    <option value="0.75">0.75x</option>
                    <option value="1.0" selected>1.0x</option>
                    <option value="1.25">1.25x</option>
                    <option value="1.5">1.5x</option>
                    <option value="1.75">1.75x</option>
                    <option value="2.0">2.0x</option>
                </select>
            </div>
            <span id="statusText" class="status-indicator">Ready</span>
        </div>

        <script>
            const textToSpeak = {escaped_json_text};
            let synth = window.speechSynthesis;
            let utterance = null;
            let voices = [];
            let isPaused = false;
            let selectedVoiceIndex = 0;
            let currentRate = 1.0;

            function populateVoiceList() {{
                if (!synth) return;
                voices = synth.getVoices();
                const select = document.getElementById('voiceSelect');
                if (!select || voices.length === 0) return;
                select.innerHTML = '';
                
                voices.forEach((voice, i) => {{
                    const option = document.createElement('option');
                    option.textContent = `${{voice.name}} (${{voice.lang}})`;
                    option.value = i;
                    if (voice.default || voice.lang.startsWith('en')) {{
                        if (select.selectedIndex === 0) option.selected = true;
                    }}
                    select.appendChild(option);
                }});
            }}

            populateVoiceList();
            if (synth && synth.onvoiceschanged !== undefined) {{
                synth.onvoiceschanged = populateVoiceList;
            }}

            function updateVoice() {{
                const select = document.getElementById('voiceSelect');
                selectedVoiceIndex = parseInt(select.value) || 0;
                if (synth.speaking && !synth.paused) {{
                    stopNarration();
                    togglePlay();
                }}
            }}

            function updateSpeed() {{
                const sel = document.getElementById('speedSelect');
                currentRate = parseFloat(sel.value) || 1.0;
                if (synth.speaking && !synth.paused) {{
                    stopNarration();
                    togglePlay();
                }}
            }}

            function togglePlay() {{
                if (!synth) {{
                    alert('Web Speech API is not supported in this browser.');
                    return;
                }}
                if (synth.paused) {{
                    synth.resume();
                    document.getElementById('statusText').innerText = 'Playing...';
                    document.getElementById('btnPlay').classList.add('active');
                    return;
                }}
                if (synth.speaking) return;

                utterance = new SpeechSynthesisUtterance(textToSpeak);
                if (voices.length > 0) {{
                    utterance.voice = voices[selectedVoiceIndex] || voices[0];
                }}
                utterance.rate = currentRate;
                utterance.pitch = 1.0;

                utterance.onstart = () => {{
                    document.getElementById('statusText').innerText = 'Speaking...';
                    document.getElementById('btnPlay').classList.add('active');
                }};

                utterance.onend = () => {{
                    document.getElementById('statusText').innerText = 'Completed';
                    document.getElementById('btnPlay').classList.remove('active');
                }};

                utterance.onerror = (e) => {{
                    document.getElementById('statusText').innerText = 'Stopped';
                    document.getElementById('btnPlay').classList.remove('active');
                }};

                synth.speak(utterance);
            }}

            function togglePause() {{
                if (!synth) return;
                if (synth.speaking && !synth.paused) {{
                    synth.pause();
                    document.getElementById('statusText').innerText = 'Paused';
                    document.getElementById('btnPlay').classList.remove('active');
                }} else if (synth.paused) {{
                    synth.resume();
                    document.getElementById('statusText').innerText = 'Playing...';
                    document.getElementById('btnPlay').classList.add('active');
                }}
            }}

            function stopNarration() {{
                if (!synth) return;
                synth.cancel();
                document.getElementById('statusText').innerText = 'Stopped';
                document.getElementById('btnPlay').classList.remove('active');
            }}
        </script>
    </body>
    </html>
    """
    components.html(html_code, height=75, scrolling=False)
