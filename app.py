import sys
import socket
from functools import wraps
from flask import Flask, Response, request, abort, jsonify, render_template_string, redirect, url_for, flash
from flask_socketio import SocketIO
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
# Import per ElevenLabs e OS per la chiave API
from elevenlabs.client import ElevenLabs
import os

# -------------------------------------------------------------------
# CONFIGURAZIONE SICUREZZA E LOGIN
# -------------------------------------------------------------------

SECRET_KEY_FLASK = "questa-chiave-deve-essere-super-segreta-e-difficile-da-indovinare-2025"

USERS_DB = {
    "admin": {
        "password_hash": generate_password_hash("adminpass"),
        "name": "Amministratore"
    }
}

class User(UserMixin):
    def __init__(self, id, name):
        self.id = id
        self.name = name

def get_user(user_id):
    if user_id in USERS_DB:
        return User(id=user_id, name=USERS_DB[user_id]["name"])
    return None

# -------------------------------------------------------------------
# IMPOSTAZIONI E APPLICAZIONE
# -------------------------------------------------------------------

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY_FLASK
socketio = SocketIO(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Per favore, effettua il login per accedere a questa pagina."
login_manager.login_message_category = "error"

# Inizializzazione del client di ElevenLabs
# La chiave viene letta automaticamente dalla variabile d'ambiente ELEVEN_API_KEY
try:
    eleven_client = ElevenLabs()
    print("Client ElevenLabs (voce HD) inizializzato con successo.")
except Exception as e:
    eleven_client = None
    print(f"ATTENZIONE: Client ElevenLabs non inizializzato. Il sistema userà la voce standard del browser. Errore: {e}")


@login_manager.user_loader
def load_user(user_id):
    return get_user(user_id)

def get_local_ip():
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        if s:
            s.close()
    return IP

# -------------------------------------------------------------------
# STATO GLOBALE DELL'APPLICAZIONE
# -------------------------------------------------------------------
current_app_state = None
current_video_file = {'data': None, 'mimetype': None, 'name': None}

# -------------------------------------------------------------------
# TEMPLATE HTML, CSS e JAVASCRIPT INTEGRATI
# -------------------------------------------------------------------

LOGIN_PAGE_HTML = """
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Pannello Harzafi</title>
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Montserrat', sans-serif; background: linear-gradient(135deg, #fdf4f6, #f4f4fd); display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
        .login-container { background: white; padding: 40px; border-radius: 24px; box-shadow: 0 20px 50px -10px rgba(44, 62, 80, 0.1); text-align: center; width: 100%; max-width: 400px; }
        img { max-width: 180px; margin-bottom: 20px; }
        h2 { color: #2c3e50; font-weight: 700; }
        .flash-error { background-color: #f8d7da; color: #721c24; padding: 10px; border-radius: 12px; margin-bottom: 15px; border: 1px solid #f5c6cb; }
        .form-group { margin-bottom: 20px; text-align: left; }
        label { display: block; margin-bottom: 8px; font-weight: 600; color: #8492a6; font-size: 14px; }
        input { width: 100%; padding: 14px; border-radius: 12px; border: 1px solid #e0e6ed; font-size: 16px; box-sizing: border-box; font-family: 'Montserrat', sans-serif; }
        input:focus { outline: none; border-color: #8A2387; box-shadow: 0 0 0 4px rgba(138, 35, 135, 0.1); }
        button { width: 100%; padding: 15px; border: none; background: linear-gradient(135deg, #A244A7, #8A2387); color: white; font-size: 16px; font-weight: 700; border-radius: 12px; cursor: pointer; transition: transform 0.2s; }
        button:hover { transform: translateY(-3px); }
    </style>
</head>
<body>
    <div class="login-container">
        <img src="https://i.ibb.co/8gSLmLCD/LOGO-HARZAFI.png" alt="Logo Harzafi">
        <h2>Accesso Riservato</h2>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    {% if category == 'error' %}
                        <div class="flash-error">{{ message }}</div>
                    {% endif %}
                {% endfor %}
            {% endif %}
        {% endwith %}
        <form method="post">
            <div class="form-group">
                <label for="username">Nome Utente</label>
                <input type="text" id="username" name="username" required>
            </div>
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required>
            </div>
            <button type="submit">Accedi</button>
        </form>
    </div>
</body>
</html>
"""

PANNELLO_CONTROLLO_COMPLETO_HTML = """
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pannello di Controllo Harzafi</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700;800&display=swap" rel="stylesheet">
    <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
    <style>
        :root {
            --primary-color: #8A2387;
            --secondary-color: #A244A7;
            --accent-color: #F777A8;
            --danger-color: #e74c3c;
            --success-color: #2ecc71;
            --text-primary: #2c3e50;
            --text-secondary: #8492a6;
            --border-color: #e0e6ed;
            --white: #ffffff;
            --background-light: #f9fafb;
            --background-gradient: linear-gradient(135deg, #fdf4f6, #f4f4fd);
        }
        body {
            font-family: 'Montserrat', sans-serif;
            background: var(--background-gradient);
            color: var(--text-primary);
            margin: 0;
            padding: 30px;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
        }
        .container { max-width: 800px; margin: 0 auto; }
        .panel {
            background-color: var(--white);
            padding: 35px;
            border-radius: 24px;
            border: 1px solid var(--border-color);
            box-shadow: 0 20px 50px -10px rgba(44, 62, 80, 0.1);
            margin-bottom: 30px;
        }
        .panel-header { display: flex; justify-content: space-between; align-items: center; gap: 20px; margin-bottom: 10px; flex-wrap: wrap; }
        .panel-header-title { display: flex; align-items: center; gap: 20px; }
        .panel-header-title img { max-width: 140px; }
        .panel-header-title h1 { font-size: 28px; color: var(--text-primary); margin: 0; font-weight: 800; }
        .panel-subtitle { width: 100%; margin-top: -15px; margin-bottom: 20px; }
        .control-group { margin-bottom: 25px; }
        label { display: block; margin-bottom: 10px; font-weight: 600; color: var(--text-secondary); font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; }
        select, button, input[type="text"], textarea {
            width: 100%; padding: 14px; border-radius: 12px; border: 1px solid var(--border-color);
            font-size: 16px; box-sizing: border-box; font-family: 'Montserrat', sans-serif; transition: all 0.2s ease-in-out;
        }
        textarea { height: 120px; resize: vertical; }
        select:focus, input[type="text"]:focus, textarea:focus {
            outline: none; border-color: var(--primary-color); box-shadow: 0 0 0 4px rgba(138, 35, 135, 0.1);
        }
        .navigation-buttons { display: flex; gap: 15px; }
        button { cursor: pointer; border: none; font-weight: 700; color: white; border-radius: 12px; transition: all 0.2s ease-in-out; }
        button:disabled { background: #bdc3c7; cursor: not-allowed; transform: none; box-shadow: none; }
        button:not(:disabled):hover { transform: translateY(-3px); box-shadow: 0 8px 20px rgba(0,0,0,0.15); }
        button:active { transform: translateY(-1px); }
        .btn-primary { background: linear-gradient(135deg, var(--secondary-color), var(--primary-color)); }
        .btn-success { background: var(--success-color); }
        .btn-danger { background: var(--danger-color); }
        .btn-secondary { background: var(--text-secondary); }
        #logout-btn { background: var(--danger-color); width: auto; padding: 10px 20px; font-size: 14px; flex-shrink: 0;}
        .divider { height: 1px; background-color: var(--border-color); margin: 25px 0; }
        .info-box { padding: 15px; background-color: var(--background-light); border-radius: 12px; border-left: 5px solid var(--primary-color); color: var(--text-secondary); font-size: 14px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="panel">
            <div class="panel-header">
                <div class="panel-header-title">
                    <img src="https://i.ibb.co/8gSLmLCD/LOGO-HARZAFI.png" alt="Logo Harzafi">
                    <h1>Pannello di Controllo</h1>
                </div>
                <a href="{{ url_for('logout') }}"><button id="logout-btn">Logout</button></a>
            </div>
             <p class="panel-subtitle">Usa questo pannello per controllare la pagina del <a id="viewer-link" href="https://harzafibus.onrender.com/visualizzatore" target="_blank">visualizzatore</a> in tempo reale.</p>
        </div>
        
        <div class="panel">
             <h2>Istruzioni Annunci Sonori</h2>
             <div class="info-box">
                <strong>Importante:</strong> Per far funzionare gli annunci vocali, è necessario prima aprire la pagina del <a href="https://harzafibus.onrender.com/visualizzatore" target="_blank">visualizzatore</a> e cliccare sullo schermo per dare l'autorizzazione all'audio. Questa operazione va fatta solo una volta all'apertura della pagina.
             </div>
        </div>

        <div class="panel">
            <h2>Stato del Servizio</h2>
            <div class="control-group">
                <label for="service-status-toggle">Stato Attuale</label>
                <select id="service-status-toggle">
                    <option value="online">In Servizio</option>
                    <option value="offline">Fuori Servizio</option>
                </select>
            </div>
        </div>
        <div class="panel">
            <h2>Gestione Media</h2>
            <div class="control-group">
                <label for="embed-code-input">Codice Embed (iframe)</label>
                <textarea id="embed-code-input" placeholder="Incolla qui il codice <iframe>..."></textarea>
            </div>
            <button id="import-embed-btn" class="btn-primary" style="width: 100%; padding: 15px;">Imposta Media da Embed</button>
            <div class="divider"></div>
            <input type="file" id="video-importer" accept="video/*" style="display: none;">
            <button id="import-video-btn" class="btn-secondary" style="width: 100%; padding: 15px;">Importa Video da File Locale</button>
        </div>
        <div class="panel">
            <h2>Controllo Linea e Fermate</h2>
            <div class="control-group">
                <label for="line-selector">Seleziona Linea Attiva</label>
                <select id="line-selector"></select>
            </div>
            <div class="control-group">
                <label>Navigazione Fermate</label>
                <div class="navigation-buttons">
                    <button id="prev-btn" class="btn-primary">← Precedente</button>
                    <button id="next-btn" class="btn-primary">Successiva →</button>
                </div>
            </div>
             <button id="announce-btn" title="Annuncia linea e destinazione" class="btn-primary" style="width:100%; margin-top: 20px; padding: 12px;">
                ANNUNCIA LINEA E DESTINAZIONE
            </button>
        </div>
        <div class="panel">
            <h2>Gestione Messaggi Informativi</h2>
            <div class="control-group">
                <label for="info-messages-input">Messaggi a scorrimento (uno per riga)</label>
                <textarea id="info-messages-input" placeholder="Benvenuti a bordo..."></textarea>
            </div>
            <button id="save-messages-btn" class="btn-primary" style="width:100%; padding: 15px;">Salva Messaggi</button>
        </div>
    </div>
    <script>
document.addEventListener('DOMContentLoaded', () => {
    // Tutta la logica Javascript del pannello rimane invariata.
    // Il pannello si occupa solo di inviare lo stato, non di gestire l'audio.
    const socket = io();

    function sendFullStateUpdate() {
        if (!socket.connected) return;
        
        const state = {
            linesData: linesData,
            currentLineKey: currentLineKey,
            currentStopIndex: currentStopIndex,
            mediaSource: localStorage.getItem('busSystem-mediaSource'),
            embedCode: localStorage.getItem('busSystem-embedCode'),
            mediaLastUpdated: localStorage.getItem('busSystem-mediaLastUpdated'),
            infoMessages: JSON.parse(localStorage.getItem('busSystem-infoMessages') || '[]'),
            serviceStatus: serviceStatus,
            announcement: JSON.parse(localStorage.getItem('busSystem-playAnnouncement') || 'null')
        };
        
        socket.emit('update_all', state);
        
        if (state.announcement) {
            localStorage.removeItem('busSystem-playAnnouncement');
        }
    }

    const importEmbedBtn = document.getElementById('import-embed-btn');
    const embedCodeInput = document.getElementById('embed-code-input');
    const importVideoBtn = document.getElementById('import-video-btn');
    const videoImporter = document.getElementById('video-importer');

    async function handleEmbedImport() {
        const rawCode = embedCodeInput.value.trim();
        if (!rawCode.includes('<iframe')) {
            alert('Codice non valido. Assicurati di incollare il codice <iframe> completo.');
            return;
        }
        
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = rawCode;
        const iframe = tempDiv.querySelector('iframe');
        if (!iframe) {
            alert('Codice non valido. Non è stato trovato un tag <iframe> valido.'); return;
        }
        iframe.setAttribute('width', '100%');
        iframe.setAttribute('height', '100%');
        iframe.setAttribute('style', 'position:absolute; top:0; left:0; width:100%; height:100%;');
        const sanitizedCode = iframe.outerHTML;

        localStorage.setItem('busSystem-mediaSource', 'embed');
        localStorage.setItem('busSystem-embedCode', sanitizedCode);
        localStorage.setItem('busSystem-mediaLastUpdated', Date.now());
        
        embedCodeInput.value = '';
        alert('Media da Embed impostato con successo!');
        sendFullStateUpdate();
    }

    async function handleLocalVideoUpload(event) {
        const file = event.target.files[0];
        if (!file) return;

        const formData = new FormData();
        formData.append('video', file);

        const response = await fetch('/upload-video', {
            method: 'POST',
            body: formData
        });

        if (response.ok) {
            localStorage.setItem('busSystem-mediaSource', 'server');
            localStorage.removeItem('busSystem-embedCode');
            localStorage.setItem('busSystem-mediaLastUpdated', Date.now());
            alert('Video locale importato con successo!');
            sendFullStateUpdate();
        } else {
             alert('Errore durante il caricamento del video.');
        }
    }
    
    importEmbedBtn.addEventListener('click', handleEmbedImport);
    importVideoBtn.addEventListener('click', () => videoImporter.click());
    videoImporter.addEventListener('change', handleLocalVideoUpload);

    const lineSelector = document.getElementById('line-selector');
    const prevBtn = document.getElementById('prev-btn');
    const nextBtn = document.getElementById('next-btn');
    const announceBtn = document.getElementById('announce-btn');
    const infoMessagesInput = document.getElementById('info-messages-input');
    const saveMessagesBtn = document.getElementById('save-messages-btn');
    const serviceStatusToggle = document.getElementById('service-status-toggle');

    let linesData = {};
    let currentLineKey = null;
    let currentStopIndex = 0;
    let serviceStatus = 'online';

    function getDefaultData() {
        return {
            "4": { "direction": "STRADA DEL DROSSO", "stops": ["FALCHERA CAP.", "STAZIONE STURA", "PIOSSASCO", "MASPONS", "BERTOLLA"] },
            "29": { "direction": "PIAZZA SOLFERINO", "stops": ["VALLETTE CAP.", "PRIMO NEBIOLO", "MOLVENO", "PIANEZZA", "TRECATE"] },
            "S8": { "direction": "OSPEDALE G. BOSCO", "stops": ["LINGOTTO FS", "POLITECNICO", "STATI UNITI", "PORTA SUSA FS", "GIULIO CESARE"] }
        };
    }
    
    function loadData() { linesData = JSON.parse(localStorage.getItem('busSystem-linesData')) || getDefaultData(); saveData(); }
    function saveData() { localStorage.setItem('busSystem-linesData', JSON.stringify(linesData)); }
    function loadMessages() {
        const messages = localStorage.getItem('busSystem-infoMessages');
        infoMessagesInput.value = messages ? JSON.parse(messages).join('\\n') : "Benvenuti a bordo del servizio Harzafi.";
    }

    function saveMessages() {
        const messagesArray = infoMessagesInput.value.split('\\n').filter(msg => msg.trim() !== '');
        localStorage.setItem('busSystem-infoMessages', JSON.stringify(messagesArray));
        sendFullStateUpdate();
    }
    function renderLineSelector() {
        lineSelector.innerHTML = '';
        Object.keys(linesData).forEach(key => {
            const option = document.createElement('option');
            option.value = key; option.textContent = `${key} -> ${linesData[key].direction}`;
            lineSelector.appendChild(option);
        });
        if(currentLineKey) lineSelector.value = currentLineKey;
    }
    
    function updateAndRender() {
        localStorage.setItem('busSystem-currentLine', currentLineKey);
        localStorage.setItem('busSystem-currentStopIndex', currentStopIndex);
        sendFullStateUpdate();
    }

    function initialize() {
        loadData();
        loadMessages();
        currentLineKey = localStorage.getItem('busSystem-currentLine') || Object.keys(linesData)[0];
        currentStopIndex = parseInt(localStorage.getItem('busSystem-currentStopIndex'), 10) || 0;
        serviceStatus = localStorage.getItem('busSystem-serviceStatus') || 'online';
        serviceStatusToggle.value = serviceStatus;
        renderLineSelector();
        updateAndRender();
    }

    lineSelector.addEventListener('change', (e) => { currentLineKey = e.target.value; currentStopIndex = 0; updateAndRender(); });
    nextBtn.addEventListener('click', () => { if (currentStopIndex < linesData[currentLineKey].stops.length - 1) { currentStopIndex++; updateAndRender(); } });
    prevBtn.addEventListener('click', () => { if (currentStopIndex > 0) { currentStopIndex--; updateAndRender(); } });
    announceBtn.addEventListener('click', () => {
        const announcementData = { line: currentLineKey, direction: linesData[currentLineKey].direction, timestamp: Date.now() }; 
        localStorage.setItem('busSystem-playAnnouncement', JSON.stringify(announcementData));
        sendFullStateUpdate();
    });
    serviceStatusToggle.addEventListener('change', (e) => {
        serviceStatus = e.target.value;
        localStorage.setItem('busSystem-serviceStatus', serviceStatus);
        sendFullStateUpdate();
    });
    saveMessagesBtn.addEventListener('click', saveMessages);
    
    initialize();
});
</script>
</body>
</html>
"""

# --- INIZIO BLOCCO CODICE VISUALIZZATORE CORRETTO ---
VISUALIZZATORE_COMPLETO_HTML = """
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Visualizzazione Fermata Harzafi</title>
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@700;900&display=swap" rel="stylesheet">
    <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
    <style>
        :root {
            --main-text-color: #ffffff;
            --gradient-start: #D544A7;
            --gradient-end: #4343A2;
        }
        body { margin: 0; font-family: 'Montserrat', sans-serif; background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end)); color: var(--main-text-color); height: 100vh; display: flex; overflow: hidden; }
        .main-content { flex: 3; display: flex; align-items: center; justify-content: center; padding: 40px; }
        .video-content { flex: 2; display: flex; align-items: center; justify-content: center; padding: 40px; }
        #video-player-container { width: 100%; height: 0; padding-top: 56.25%; position: relative; background-color: rgba(0,0,0,0.2); border-radius: 25px; overflow: hidden; }
        #video-player-container iframe, #video-player-container video { position: absolute; top:0; left:0; width: 100%; height: 100%; border:0; }
        h1 { font-size: 70px; font-weight: 900; text-transform: uppercase; }
        h2 { font-size: 140px; font-weight: 900; line-height: 1.1; text-transform: uppercase; }
        /* Stile per la schermata di attivazione audio */
        #audio-unlock-overlay {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            z-index: 1001;
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            text-align: center; color: white;
            background-color: rgba(15, 23, 42, 0.8);
            backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
            cursor: pointer;
            transition: opacity 0.5s ease-out;
        }
        #audio-unlock-overlay.hidden { opacity: 0; pointer-events: none; }
        #audio-unlock-overlay h2 { font-size: 4vw; }
        #audio-unlock-overlay p { font-size: 1.5vw; opacity: 0.8; }
        #service-offline-overlay { display: none; /* Inizialmente nascosto */ }
        #service-offline-overlay.visible {
             position: fixed; top: 0; left: 0; width: 100%; height: 100%;
             z-index: 1000; display: flex; align-items: center; justify-content: center;
             text-align: center; color: white; background-color: rgba(15, 23, 42, 0.6);
             backdrop-filter: blur(10px);
        }
    </style>
</head>
<body>
    <div id="audio-unlock-overlay">
        <div>
            <h2>Benvenuto a Bordo</h2>
            <p>Clicca in un punto qualsiasi dello schermo per attivare gli annunci sonori.</p>
        </div>
    </div>
    <div id="service-offline-overlay">
        <h2>SERVIZIO MOMENTANEAMENTE NON DISPONIBILE</h2>
    </div>
    <div class="main-content">
        <div>
            <p>DESTINAZIONE</p>
            <h1 id="direction-name">CARICAMENTO...</h1>
            <p>PROSSIMA FERMATA</p>
            <h2 id="stop-name">...</h2>
        </div>
    </div>
    <div class="video-content">
        <div id="video-player-container"></div>
    </div>
<script>
document.addEventListener('DOMContentLoaded', () => {
    const socket = io();
    const audioUnlockOverlay = document.getElementById('audio-unlock-overlay');
    const serviceOfflineOverlay = document.getElementById('service-offline-overlay');
    let audioContext;
    let isAudioUnlocked = false;
    let announcementQueue = [];
    let isAnnouncing = false;
    let lastKnownState = {};

    // Pre-carica le voci del browser per il sistema di ripiego
    window.speechSynthesis.onvoiceschanged = () => { window.speechSynthesis.getVoices(); };

    function unlockAudio() {
        if (isAudioUnlocked) return;
        try {
            audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const buffer = audioContext.createBuffer(1, 1, 22050);
            const source = audioContext.createBufferSource();
            source.buffer = buffer;
            source.connect(audioContext.destination);
            source.start(0);
            isAudioUnlocked = true;
            console.log("Web Audio API sbloccata con successo.");
            audioUnlockOverlay.classList.add('hidden');
            socket.emit('request_initial_state');
        } catch (e) {
            console.error("Impossibile sbloccare Web Audio API:", e);
            alert("Il tuo browser potrebbe non supportare gli annunci audio automatici.");
        }
    }
    audioUnlockOverlay.addEventListener('click', unlockAudio, { once: true });

    async function playAnnouncement(textToSpeak) {
        // --- NUOVA LOGICA IBRIDA ---
        try {
            // 1. Prova a usare il servizio HD (ElevenLabs)
            const response = await fetch(`/synthesize-speech?text=${encodeURIComponent(textToSpeak)}`);
            if (!response.ok) throw new Error(`Il server TTS ha risposto con errore ${response.status}`);
            
            const audioData = await response.arrayBuffer();
            const audioBuffer = await audioContext.decodeAudioData(audioData);
            
            const source = audioContext.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(audioContext.destination);
            source.start(0);
            
            source.onended = () => { isAnnouncing = false; processQueue(); };

        } catch (error) {
            console.warn("Sintesi HD fallita, uso la voce standard del browser. Errore:", error);
            // 2. Se fallisce, usa la voce del browser (sempre funzionante)
            try {
                const utterance = new SpeechSynthesisUtterance(textToSpeak);
                const voices = window.speechSynthesis.getVoices();
                utterance.voice = voices.find(v => v.lang.startsWith('it')) || voices.find(v => v.default);
                utterance.lang = 'it-IT';
                utterance.onend = () => { isAnnouncing = false; processQueue(); };
                utterance.onerror = (e) => {
                    console.error("Anche la sintesi del browser è fallita:", e);
                    isAnnouncing = false; processQueue();
                };
                window.speechSynthesis.speak(utterance);
            } catch (fallbackError) {
                 console.error("Il sistema di sintesi di ripiego ha avuto un errore critico.", fallbackError);
                 isAnnouncing = false; processQueue();
            }
        }
    }

    function processQueue() {
        if (isAnnouncing || announcementQueue.length === 0 || !isAudioUnlocked) return;
        isAnnouncing = true;
        const textToPlay = announcementQueue.shift();
        playAnnouncement(textToPlay);
    }
    
    function updateDisplay(state) {
        if (state.serviceStatus === 'offline') {
            serviceOfflineOverlay.classList.add('visible');
            return;
        }
        serviceOfflineOverlay.classList.remove('visible');

        const { linesData, currentLineKey, currentStopIndex } = state;
        const line = linesData[currentLineKey];
        if (!line) return;
        const stopName = line.stops[currentStopIndex];

        document.getElementById('direction-name').textContent = line.direction;
        document.getElementById('stop-name').textContent = stopName;

        // Annuncio cambio fermata
        if (lastKnownState.currentStopIndex !== currentStopIndex && typeof lastKnownState.currentStopIndex !== 'undefined') {
            announcementQueue.push(`Prossima fermata: ${stopName}`);
        }
        // Annuncio manuale di linea/destinazione
        if (state.announcement && state.announcement.timestamp > (lastKnownState.announcement?.timestamp || 0)) {
            announcementQueue.push(`Linea ${state.announcement.line}, destinazione ${state.announcement.direction}`);
        }
        
        processQueue();

        // Gestione media
        if (state.mediaLastUpdated > (lastKnownState.mediaLastUpdated || 0)) {
            const container = document.getElementById('video-player-container');
            if (state.mediaSource === 'embed' && state.embedCode) {
                container.innerHTML = state.embedCode;
            } else if (state.mediaSource === 'server') {
                container.innerHTML = `<video src="/stream-video?t=${state.mediaLastUpdated}" autoplay loop muted playsinline></video>`;
            } else {
                container.innerHTML = '';
            }
        }
        lastKnownState = state;
    }
    
    socket.on('initial_state', (state) => {
        if (state && isAudioUnlocked) updateDisplay(state);
    });
    socket.on('state_updated', (state) => {
        if (state && isAudioUnlocked) updateDisplay(state);
    });
});
</script>
</body>
</html>
"""
# --- FINE BLOCCO CODICE VISUALIZZATORE CORRETTO ---

# -------------------------------------------------------------------
# ROUTE E API WEBSOCKET
# -------------------------------------------------------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user_in_db = USERS_DB.get(username)
        if user_in_db and check_password_hash(user_in_db['password_hash'], password):
            user = get_user(username)
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash("Credenziali non valide.", "error")
    return render_template_string(LOGIN_PAGE_HTML)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    return render_template_string(PANNELLO_CONTROLLO_COMPLETO_HTML)

@app.route('/visualizzatore')
# Rimossa l'autenticazione per la pagina pubblica del visualizzatore
def pagina_visualizzatore():
    return render_template_string(VISUALIZZATORE_COMPLETO_HTML)

# API per la sintesi vocale
@app.route('/synthesize-speech')
def synthesize_speech():
    text_to_speak = request.args.get('text', '')
    if not text_to_speak:
        return Response("Testo non fornito", status=400)
    if not eleven_client:
        return Response("Servizio sintesi vocale HD non configurato", status=503)
    try:
        audio_stream = eleven_client.generate(
            text=text_to_speak,
            voice="Antoni",
            model="eleven_multilingual_v2"
        )
        return Response(audio_stream, mimetype='audio/mpeg')
    except Exception as e:
        print(f"Errore ElevenLabs: {e}")
        return Response("Errore durante la generazione dell'audio", status=500)

# API per la gestione video
@app.route('/upload-video', methods=['POST'])
@login_required
def upload_video():
    global current_video_file
    file = request.files.get('video')
    if not file: return jsonify({'error': 'Nessun file'}), 400
    current_video_file = {'data': file.read(), 'mimetype': file.mimetype}
    return jsonify({'success': True})

@app.route('/stream-video')
def stream_video():
    if current_video_file['data']:
        return Response(current_video_file['data'], mimetype=current_video_file['mimetype'])
    abort(404)

# Gestione WebSocket
@socketio.on('connect')
def handle_connect():
    print(f"Client visualizzatore connesso: {request.sid}")

@socketio.on('request_initial_state')
def handle_request_initial_state():
    if current_app_state:
        socketio.emit('initial_state', current_app_state, room=request.sid)

@socketio.on('update_all')
def handle_update_all(data):
    # L'update può arrivare solo da un utente autenticato nel pannello
    if not current_user.is_authenticated: return
    global current_app_state
    current_app_state = data
    # Invia l'aggiornamento a tutti i visualizzatori connessi
    socketio.emit('state_updated', current_app_state, skip_sid=request.sid)

# -------------------------------------------------------------------
# BLOCCO DI ESECUZIONE
# -------------------------------------------------------------------

if __name__ == '__main__':
    local_ip = get_local_ip()
    print("================================================================")
    print("      SERVER HARZAFI POTENZIATO (v.Audio Ibrido) AVVIATO")
    print("================================================================")
    print(f"Pannello di Controllo (LAN): http://{local_ip}:5000")
    print(f"Visualizzatore Pubblico (LAN): http://{local_ip}:5000/visualizzatore")
    print("----------------------------------------------------------------")
    print("Assicurati di aver impostato la variabile d'ambiente ELEVEN_API_KEY")
    print("per la voce di alta qualità. Altrimenti, verrà usata la voce standard.")
    print("================================================================")
    
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
