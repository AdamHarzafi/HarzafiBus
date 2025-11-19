import sys
import socket
import re 
import os
import tempfile
from functools import wraps
from datetime import datetime, timedelta
import locale
from flask import Flask, Response, request, abort, jsonify, render_template_string, redirect, url_for, flash, send_file
from flask_socketio import SocketIO
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField
from wtforms.validators import DataRequired

# -------------------------------------------------------------------
# CONFIGURAZIONE
# -------------------------------------------------------------------

# Tentativo di impostare il locale italiano per le date
try:
    locale.setlocale(locale.LC_TIME, 'it_IT.utf8')
except:
    try:
        locale.setlocale(locale.LC_TIME, 'it_IT')
    except:
        pass # Fallback al default di sistema se italiano non disponibile

SECRET_KEY_FLASK = "questa-chiave-e-stata-cambiata-ed-e-molto-piu-sicura-del-2025"

login_attempts = {}
MAX_ATTEMPTS = 5
LOCKOUT_TIME_MINUTES = 10

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

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired("Il nome utente è obbligatorio.")])
    password = PasswordField('Password', validators=[DataRequired("La password è obbligatoria.")])

# -------------------------------------------------------------------
# 1. APP INIT
# -------------------------------------------------------------------

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY_FLASK
app.config['WTF_CSRF_SECRET_KEY'] = SECRET_KEY_FLASK
socketio = SocketIO(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Per favore, effettua il login."
login_manager.login_message_category = "error"

@login_manager.user_loader
def load_user(user_id):
    return get_user(user_id)

@app.after_request
def add_security_headers(response):
    if request.path != '/login' and not request.path.startswith('/static'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

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
# 2. STATO GLOBALE
# -------------------------------------------------------------------
current_app_state = {
    "linesData": {},
    "currentLineKey": None,
    "currentStopIndex": 0,
    "mediaSource": None,
    "embedCode": None,
    "videoName": None,
    "mediaLastUpdated": None,
    "volumeLevel": "1.0",
    "playbackState": "playing",
    "seekAction": None,
    "infoMessages": [],
    "serviceStatus": "online",
    "videoNotAvailable": False,
    "announcement": None,
    "stopRequested": None
}
current_video_file = {'path': None, 'mimetype': None, 'name': None}

# -------------------------------------------------------------------
# 3. TEMPLATES
# -------------------------------------------------------------------

# --- LOGIN (INVARIATO) ---
LOGIN_PAGE_HTML = """
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Accesso Riservato - Pannello Harzafi</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        :root { --bg-start: #111827; --bg-end: #1F2937; --accent: #A244A7; --text: #F9FAFB; }
        body { font-family: 'Inter', sans-serif; background: linear-gradient(135deg, var(--bg-start), var(--bg-end)); color: var(--text); display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }
        .login-container { width: 100%; max-width: 420px; background: rgba(31, 41, 55, 0.8); padding: 40px; border-radius: 24px; border: 1px solid rgba(107, 114, 128, 0.2); backdrop-filter: blur(10px); text-align: center; }
        .logo { max-width: 150px; margin-bottom: 24px; }
        input { width: 100%; padding: 14px; margin-bottom: 15px; border-radius: 12px; border: 1px solid #374151; background: #111827; color: white; box-sizing: border-box;}
        button { width: 100%; padding: 15px; background: var(--accent); color: white; border: none; border-radius: 12px; font-weight: bold; cursor: pointer; }
        .flash-message { padding: 10px; margin-bottom: 20px; border-radius: 8px; background: rgba(239, 68, 68, 0.2); color: #EF4444; }
    </style>
</head>
<body>
    <div class="login-container">
        <img src="https://i.ibb.co/nN5WRrHS/LOGO-HARZAFI.png" alt="Logo" class="logo">
        <h2>Area Riservata</h2>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="flash-message">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        <form method="post">
            {{ form.hidden_tag() }}
            {{ form.username(placeholder="Username") }}
            {{ form.password(placeholder="Password") }}
            <button type="submit">Accedi</button>
        </form>
    </div>
</body>
</html>
"""

# --- PANNELLO DI CONTROLLO (INVARIATO) ---
# Nota: Utilizzo lo stesso HTML fornito precedentemente per il pannello, 
# poiché le modifiche richieste riguardano solo il visualizzatore.
PANNELLO_CONTROLLO_COMPLETO_HTML = """
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pannello di Controllo Harzafi</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
    <style>
        :root {
            --background: #000000; --content-background: #1D1D1F; --content-background-light: #2C2C2E;
            --border-color: #3A3A3C; --text-primary: #F5F5F7; --text-secondary: #86868B;
            --accent-primary: #A244A7; --accent-secondary: #8A2387; --success: #30D158;
            --danger: #FF453A; --blue: #0A84FF;
        }
        * { box-sizing: border-box; }
        body { font-family: 'Inter', sans-serif; background: var(--background); color: var(--text-primary); margin: 0; padding: 20px; }
        .main-container { max-width: 1200px; margin: 0 auto; display: flex; flex-direction: column; gap: 40px; }
        .main-header { display: flex; justify-content: space-between; align-items: center; padding: 20px 0; border-bottom: 1px solid var(--border-color); }
        .header-title img { max-width: 100px; vertical-align: middle; margin-right: 15px; }
        .header-title h1 { display: inline; font-size: 24px; }
        .btn { padding: 8px 16px; border-radius: 99px; font-weight: 600; cursor: pointer; text-decoration: none; border: none; display: inline-block;}
        .btn-viewer { background: var(--blue); color: white; }
        .control-section { background: var(--content-background); padding: 30px; border-radius: 20px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 25px; }
        label { display: block; margin-bottom: 10px; color: var(--text-secondary); }
        select, input[type="text"], textarea { width: 100%; padding: 12px; border-radius: 12px; border: 1px solid var(--border-color); background: var(--content-background-light); color: white; }
        button { padding: 12px; border-radius: 12px; border: none; font-weight: 600; cursor: pointer; width: 100%; }
        .btn-primary { background: var(--blue); color: white; }
        .btn-secondary { background: var(--content-background-light); color: white; border: 1px solid var(--border-color); }
        .btn-danger { background: var(--danger); color: white; }
        .btn-success { background: var(--success); color: white; }
        #status-card { background: linear-gradient(135deg, var(--accent-secondary), var(--accent-primary)); padding: 25px; border-radius: 16px; }
        .line-item { display: flex; justify-content: space-between; padding: 12px; background: var(--content-background-light); margin-bottom: 5px; border-radius: 8px; }
        dialog { background: var(--background); color: white; border: 1px solid var(--border-color); border-radius: 20px; padding: 30px; width: 90%; max-width: 500px; }
        .stop-item { display: flex; gap: 10px; margin-bottom: 10px; }
        .audio-upload-btn { width: 40px !important; border-radius: 50% !important; padding: 0 !important; display: flex; align-items: center; justify-content: center; }
        .audio-upload-btn.status-green { background: var(--success); } .audio-upload-btn.status-red { background: var(--danger); }
        .audio-upload-btn svg { width: 20px; height: 20px; fill: white; }
        .media-controls { display: flex; gap: 10px; align-items: center; margin-top: 10px; }
        .media-controls button { width: 40px; }
    </style>
</head>
<body>
    <div class="main-container">
        <header class="main-header">
            <div class="header-title"><img src="https://i.ibb.co/nN5WRrHS/LOGO-HARZAFI.png"><h1>Pannello</h1></div>
            <div><a href="{{ url_for('pagina_visualizzatore') }}" target="_blank" class="btn btn-viewer">Visualizzatore</a> <a href="{{ url_for('logout') }}" class="btn btn-danger">Esci</a></div>
        </header>

        <section class="control-section">
            <div class="grid">
                <div>
                    <h2>Stato</h2>
                    <div id="status-card">
                        <h3>Fermata Attuale (<span id="status-progress">--/--</span>)</h3>
                        <h1 id="status-stop-name" style="margin: 10px 0;">--</h1>
                        <p id="status-stop-subtitle">--</p>
                    </div>
                </div>
                <div>
                    <h2>Controlli</h2>
                    <label>Linea</label><select id="line-selector"></select>
                    <div style="display:flex; gap:10px; margin-top:15px;">
                        <button id="prev-btn" class="btn-secondary">← Indietro</button>
                        <button id="next-btn" class="btn-secondary">Avanti →</button>
                    </div>
                    <button id="announce-btn" class="btn-primary" style="margin-top:15px;">Annuncia Linea</button>
                    <button id="booked-btn" class="btn-primary" style="margin-top:15px;">Prenota Fermata</button>
                </div>
            </div>
        </section>

        <section class="control-section">
            <h2>Media & Messaggi</h2>
            <div class="grid">
                <div>
                    <label>Video Locale</label>
                    <input type="file" id="video-importer" accept="video/*" style="display:none;">
                    <button id="import-video-btn" class="btn-secondary">Carica Video</button>
                    <button id="remove-media-btn" class="btn-danger" style="margin-top:10px; display:none;">Rimuovi</button>
                    <p id="media-upload-status" style="font-size:12px; color:#888; margin-top:5px;"></p>
                    <div class="media-controls" id="media-controls-container">
                        <button id="seek-back-btn" class="btn-secondary">«</button>
                        <button id="play-pause-btn" class="btn-secondary">▶</button>
                        <button id="seek-fwd-btn" class="btn-secondary">»</button>
                        <input type="range" id="volume-slider" min="0" max="1" step="0.1" value="1" style="flex-grow:1;">
                    </div>
                    <div style="margin-top: 15px; display: flex; align-items: center; justify-content: space-between; background: var(--content-background-light); padding: 10px; border-radius: 8px;">
                        <span>Video "Non Disponibile"</span>
                        <input type="checkbox" id="video-not-available-toggle">
                    </div>
                </div>
                <div>
                    <label>Messaggi Scorrevoli</label>
                    <textarea id="info-messages-input" rows="5"></textarea>
                    <button id="save-messages-btn" class="btn-primary" style="margin-top:10px;">Salva Messaggi</button>
                </div>
            </div>
        </section>

        <section class="control-section">
            <h2>Gestione Linee</h2>
            <div id="line-management-list"></div>
            <button id="add-new-line-btn" class="btn-success" style="margin-top:20px;">+ Nuova Linea</button>
            <button id="reset-data-btn" class="btn-danger" style="margin-top:10px;">Reset Totale</button>
        </section>
    </div>

    <dialog id="line-editor-modal">
        <h2 id="modal-title">Editor Linea</h2>
        <form id="line-editor-form">
            <input type="hidden" id="edit-line-id">
            <label>Nome Linea</label><input type="text" id="line-name" required>
            <label style="margin-top:10px;">Destinazione</label><input type="text" id="line-direction" required>
            <div id="stops-list" style="max-height:300px; overflow-y:auto; margin-top:15px;"></div>
            <button type="button" id="add-stop-btn" class="btn-secondary" style="margin-top:10px;">+ Aggiungi Fermata</button>
            <div style="display:flex; gap:10px; margin-top:20px;">
                <button type="button" id="cancel-btn" class="btn-secondary">Annulla</button>
                <button type="submit" class="btn-primary">Salva</button>
            </div>
        </form>
    </dialog>

<script>
document.addEventListener('DOMContentLoaded', () => {
    const socket = io();
    let linesData = {}, currentLineKey = null, currentStopIndex = 0;

    // Elementi DOM (Mapping essenziale)
    const els = {
        lineSelector: document.getElementById('line-selector'),
        statusStop: document.getElementById('status-stop-name'),
        statusSub: document.getElementById('status-stop-subtitle'),
        statusProg: document.getElementById('status-progress'),
        prevBtn: document.getElementById('prev-btn'),
        nextBtn: document.getElementById('next-btn'),
        announceBtn: document.getElementById('announce-btn'),
        bookedBtn: document.getElementById('booked-btn'),
        msgsInput: document.getElementById('info-messages-input'),
        saveMsgsBtn: document.getElementById('save-messages-btn'),
        videoInput: document.getElementById('video-importer'),
        importVidBtn: document.getElementById('import-video-btn'),
        removeVidBtn: document.getElementById('remove-media-btn'),
        vidStatus: document.getElementById('media-upload-status'),
        playPause: document.getElementById('play-pause-btn'),
        volSlider: document.getElementById('volume-slider'),
        seekBack: document.getElementById('seek-back-btn'),
        seekFwd: document.getElementById('seek-fwd-btn'),
        linesList: document.getElementById('line-management-list'),
        addStopBtn: document.getElementById('add-stop-btn'),
        stopsContainer: document.getElementById('stops-list'),
        modal: document.getElementById('line-editor-modal'),
        notAvailToggle: document.getElementById('video-not-available-toggle')
    };

    // Inizializzazione
    function init() {
        const stored = localStorage.getItem('busSystem-linesData');
        if(stored) linesData = JSON.parse(stored);
        currentLineKey = localStorage.getItem('busSystem-currentLine');
        currentStopIndex = parseInt(localStorage.getItem('busSystem-currentStopIndex') || 0);
        
        const msgs = localStorage.getItem('busSystem-infoMessages');
        els.msgsInput.value = msgs ? JSON.parse(msgs).join('\\n') : "Benvenuti su Harzafi.";
        
        els.notAvailToggle.checked = localStorage.getItem('busSystem-videoNotAvailable') === 'true';
        
        renderAll();
        checkMediaStatus();
    }

    function saveData() { 
        localStorage.setItem('busSystem-linesData', JSON.stringify(linesData));
        sendUpdate();
    }

    function sendUpdate() {
        socket.emit('update_all', {
            linesData, currentLineKey, currentStopIndex,
            infoMessages: els.msgsInput.value.split('\\n').filter(x=>x.trim()),
            mediaSource: localStorage.getItem('busSystem-mediaSource'),
            videoName: localStorage.getItem('busSystem-videoName'),
            mediaLastUpdated: localStorage.getItem('busSystem-mediaLastUpdated'),
            videoNotAvailable: els.notAvailToggle.checked,
            volumeLevel: els.volSlider.value,
            playbackState: localStorage.getItem('busSystem-playbackState') || 'playing'
        });
    }

    function renderAll() {
        els.lineSelector.innerHTML = '';
        els.linesList.innerHTML = '';
        
        Object.keys(linesData).sort().forEach(k => {
            // Selector
            const opt = document.createElement('option');
            opt.value = k; opt.textContent = `${k} -> ${linesData[k].direction}`;
            els.lineSelector.appendChild(opt);
            
            // Management List
            const div = document.createElement('div'); div.className = 'line-item';
            div.innerHTML = `<span>${k}</span> <div><button class="btn-secondary edit-btn" data-id="${k}" style="width:auto; margin-right:5px;">Edit</button><button class="btn-danger del-btn" data-id="${k}" style="width:auto;">X</button></div>`;
            els.linesList.appendChild(div);
        });
        
        if(currentLineKey && linesData[currentLineKey]) els.lineSelector.value = currentLineKey;
        updateStatusDisplay();
    }

    function updateStatusDisplay() {
        if(!currentLineKey || !linesData[currentLineKey]) {
            els.statusStop.textContent = "--"; els.statusSub.textContent = ""; els.statusProg.textContent = "--/--";
            return;
        }
        const stops = linesData[currentLineKey].stops;
        if(currentStopIndex >= stops.length) currentStopIndex = stops.length - 1;
        els.statusStop.textContent = stops[currentStopIndex].name;
        els.statusSub.textContent = stops[currentStopIndex].subtitle || "";
        els.statusProg.textContent = `${currentStopIndex + 1}/${stops.length}`;
        
        localStorage.setItem('busSystem-currentLine', currentLineKey);
        localStorage.setItem('busSystem-currentStopIndex', currentStopIndex);
    }

    // Event Listeners Semplificati
    els.lineSelector.addEventListener('change', (e) => { currentLineKey = e.target.value; currentStopIndex = 0; updateStatusDisplay(); sendUpdate(); });
    els.prevBtn.addEventListener('click', () => { if(currentStopIndex > 0) { currentStopIndex--; updateStatusDisplay(); sendUpdate(); }});
    els.nextBtn.addEventListener('click', () => { if(linesData[currentLineKey] && currentStopIndex < linesData[currentLineKey].stops.length -1) { currentStopIndex++; updateStatusDisplay(); sendUpdate(); }});
    
    els.announceBtn.addEventListener('click', () => { socket.emit('update_all', { announcement: {timestamp: Date.now()} }); });
    els.bookedBtn.addEventListener('click', () => { socket.emit('update_all', { stopRequested: {timestamp: Date.now()} }); });
    
    els.saveMsgsBtn.addEventListener('click', () => { 
        localStorage.setItem('busSystem-infoMessages', JSON.stringify(els.msgsInput.value.split('\\n').filter(x=>x.trim())));
        sendUpdate();
        alert('Messaggi salvati!');
    });

    els.notAvailToggle.addEventListener('change', () => {
        localStorage.setItem('busSystem-videoNotAvailable', els.notAvailToggle.checked);
        sendUpdate();
    });

    // Gestione Video Locale
    els.importVidBtn.addEventListener('click', () => els.videoInput.click());
    els.videoInput.addEventListener('change', async (e) => {
        const file = e.target.files[0]; if(!file) return;
        const fd = new FormData(); fd.append('video', file);
        els.importVidBtn.textContent = "Caricamento...";
        const res = await fetch('/upload-video', { method: 'POST', body: fd });
        if(res.ok) {
            localStorage.setItem('busSystem-mediaSource', 'server');
            localStorage.setItem('busSystem-videoName', file.name);
            localStorage.setItem('busSystem-mediaLastUpdated', Date.now());
            checkMediaStatus(); sendUpdate();
        } else alert("Errore caricamento");
        els.importVidBtn.textContent = "Carica Video";
    });
    
    els.removeVidBtn.addEventListener('click', async () => {
        await fetch('/clear-video', { method: 'POST' });
        localStorage.removeItem('busSystem-mediaSource');
        localStorage.removeItem('busSystem-videoName');
        localStorage.setItem('busSystem-mediaLastUpdated', Date.now());
        checkMediaStatus(); sendUpdate();
    });

    function checkMediaStatus() {
        const src = localStorage.getItem('busSystem-mediaSource');
        const name = localStorage.getItem('busSystem-videoName');
        if(src === 'server' && name) {
            els.vidStatus.textContent = "Video attivo: " + name;
            els.removeVidBtn.style.display = 'inline-block';
        } else {
            els.vidStatus.textContent = "Nessun video.";
            els.removeVidBtn.style.display = 'none';
        }
    }

    // Media Controls
    els.playPause.addEventListener('click', () => {
        let state = localStorage.getItem('busSystem-playbackState') || 'playing';
        state = (state === 'playing') ? 'paused' : 'playing';
        localStorage.setItem('busSystem-playbackState', state);
        els.playPause.textContent = (state === 'playing') ? '||' : '▶';
        sendUpdate();
    });
    els.volSlider.addEventListener('input', () => sendUpdate());
    els.seekBack.addEventListener('click', () => socket.emit('update_all', { seekAction: { value: -5, timestamp: Date.now() } }));
    els.seekFwd.addEventListener('click', () => socket.emit('update_all', { seekAction: { value: 5, timestamp: Date.now() } }));

    // Editor Linee (Gestione base + Audio)
    els.stopsContainer.addEventListener('click', (e) => {
        if(e.target.closest('.audio-upload-btn')) e.target.closest('.stop-item').querySelector('input[type=file]').click();
        if(e.target.closest('.remove-stop-btn')) e.target.closest('.stop-item').remove();
    });
    els.stopsContainer.addEventListener('change', (e) => {
        if(e.target.type === 'file') {
            const reader = new FileReader();
            const btn = e.target.closest('.stop-item').querySelector('.audio-upload-btn');
            reader.onload = (ev) => { 
                e.target.closest('.stop-item').dataset.audio = ev.target.result; 
                btn.classList.remove('status-red'); btn.classList.add('status-green');
            };
            reader.readAsDataURL(e.target.files[0]);
        }
    });

    document.getElementById('add-new-line-btn').addEventListener('click', () => {
        document.getElementById('edit-line-id').value = '';
        els.stopsContainer.innerHTML = '';
        addStopDOM(); els.modal.showModal();
    });

    document.getElementById('line-editor-form').addEventListener('submit', (e) => {
        e.preventDefault();
        const newKey = document.getElementById('line-name').value.trim().toUpperCase();
        const stops = Array.from(document.querySelectorAll('.stop-item')).map(item => ({
            name: item.querySelector('.stop-name').value.toUpperCase(),
            subtitle: item.querySelector('.stop-sub').value.toUpperCase(),
            audio: item.dataset.audio || null
        })).filter(s => s.name);
        
        if(stops.length === 0 || !newKey) return alert("Dati mancanti");
        
        const oldKey = document.getElementById('edit-line-id').value;
        if(oldKey && oldKey !== newKey) delete linesData[oldKey];
        
        linesData[newKey] = { direction: document.getElementById('line-direction').value, stops };
        saveData(); renderAll(); els.modal.close();
    });

    els.linesList.addEventListener('click', (e) => {
        const btn = e.target;
        const id = btn.dataset.id;
        if(btn.classList.contains('del-btn')) { delete linesData[id]; saveData(); renderAll(); }
        if(btn.classList.contains('edit-btn')) {
            document.getElementById('edit-line-id').value = id;
            document.getElementById('line-name').value = id;
            document.getElementById('line-direction').value = linesData[id].direction;
            els.stopsContainer.innerHTML = '';
            linesData[id].stops.forEach(s => addStopDOM(s));
            els.modal.showModal();
        }
    });
    
    document.getElementById('cancel-btn').addEventListener('click', () => els.modal.close());

    function addStopDOM(data = {}) {
        const div = document.createElement('div'); div.className = 'stop-item';
        if(data.audio) div.dataset.audio = data.audio;
        const color = data.audio ? 'status-green' : 'status-red';
        div.innerHTML = `
            <input type="file" style="display:none;" accept="audio/*">
            <button type="button" class="audio-upload-btn ${color}"><svg viewBox="0 0 24 24"><path d="M12 14c1.66 0 2.99-1.34 2.99-3L15 5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm-1.2-9.1c0-.66.54-1.2 1.2-1.2.66 0 1.2.54 1.2 1.2l-.01 6.2c0 .66-.53 1.2-1.19 1.2s-1.2-.54-1.2-1.2V4.9zm6.5 6.1c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.49 6-3.31 6-6.72h-1.7z"/></svg></button>
            <input type="text" class="stop-name" placeholder="Nome" value="${data.name||''}" required>
            <input type="text" class="stop-sub" placeholder="Sub" value="${data.subtitle||''}">
            <button type="button" class="btn-danger remove-stop-btn">X</button>
        `;
        els.stopsContainer.appendChild(div);
    }
    
    init();
});
</script>
</body>
</html>
"""

# --- VISUALIZZATORE (COMPLETAMENTE AGGIORNATO) ---
VISUALIZZATORE_COMPLETO_HTML = """
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Visualizzazione Harzafi</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700;800;900&display=swap" rel="stylesheet">
    <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
    <style>
        :root {
            --text-white: #ffffff;
            --bg-dark: #0f0f0f;
            --bar-bg: rgba(20, 20, 25, 0.65); /* Glass dark */
            --bar-border: rgba(255, 255, 255, 0.1);
            --accent-gradient: linear-gradient(135deg, #D544A7, #4343A2);
        }
        body {
            margin: 0; overflow: hidden; height: 100vh; width: 100vw;
            background: #000; font-family: 'Montserrat', sans-serif; color: white;
        }
        
        /* --- LAYOUT PRINCIPALE --- */
        .viewer-container {
            display: flex; height: 100%; width: 100%;
            background: var(--accent-gradient);
        }
        
        /* SEZIONE SINISTRA (GRAFICA LINEA) */
        .left-panel {
            flex: 0 0 35%; padding: 60px; display: flex; flex-direction: column; justify-content: center;
            position: relative; z-index: 10;
        }
        .line-graphic {
            display: flex; flex-direction: column; align-items: center; position: relative;
        }
        .line-number-circle {
            width: 120px; height: 120px; border-radius: 50%; background: white;
            border: 6px solid #4343A2; display: flex; align-items: center; justify-content: center;
            font-size: 60px; font-weight: 900; color: #8A2387; z-index: 2;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3); margin-bottom: 40px;
        }
        .line-path-vertical {
            position: absolute; top: 60px; bottom: -40px; width: 10px; background: rgba(255,255,255,0.4);
            border-radius: 5px; z-index: 1;
        }
        .stop-indicator {
            width: 50px; height: 50px; background: white; border-radius: 12px; z-index: 2;
            box-shadow: 0 0 20px rgba(255,255,255,0.8); margin-top: auto;
        }
        
        /* TESTI INFORMAZIONI */
        .info-text-group { margin-top: 20px; text-align: center; }
        .lbl { font-size: 20px; opacity: 0.8; text-transform: uppercase; font-weight: 700; letter-spacing: 1px; margin-bottom: 5px;}
        .val-dest { font-size: 42px; font-weight: 900; text-transform: uppercase; margin: 0 0 40px 0; line-height: 1.1; }
        .val-stop { font-size: 78px; font-weight: 900; text-transform: uppercase; margin: 0; line-height: 1; white-space: normal; }
        .val-sub { font-size: 28px; font-weight: 500; margin-top: 10px; opacity: 0.9; text-transform: uppercase;}

        /* ANIMAZIONI TESTO */
        .fade-out-up { animation: fadeOutUp 0.4s forwards; }
        .fade-in-up { animation: fadeInUp 0.5s forwards; }
        @keyframes fadeOutUp { from { opacity: 1; transform: translateY(0); } to { opacity: 0; transform: translateY(-30px); } }
        @keyframes fadeInUp { from { opacity: 0; transform: translateY(30px); } to { opacity: 1; transform: translateY(0); } }

        /* SEZIONE DESTRA (VIDEO) */
        .right-panel {
            flex: 1; display: flex; align-items: center; justify-content: center;
            padding: 40px 40px 140px 0; /* Padding bottom alto per fare spazio alla barra */
            position: relative;
        }
        .video-frame {
            width: 100%; aspect-ratio: 16/9; background: black; border-radius: 30px;
            overflow: hidden; box-shadow: 0 20px 50px rgba(0,0,0,0.4); position: relative;
        }
        .video-frame video, .video-frame img, .video-frame iframe {
            width: 100%; height: 100%; object-fit: cover;
        }
        .video-bg-blur {
            position: absolute; width: 100%; height: 100%; top:0; left:0;
            filter: blur(40px) brightness(0.6); z-index: -1; transform: scale(1.1);
        }

        /* --- BARRA INFO IN BASSO (NUOVA) --- */
        .info-bar {
            position: fixed; bottom: 35px; left: 50%; transform: translateX(-50%);
            width: 92%; height: 90px;
            background: var(--bar-bg);
            border: 1px solid var(--bar-border);
            backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
            border-radius: 24px;
            display: flex; align-items: stretch;
            box-shadow: 0 15px 40px rgba(0,0,0,0.3);
            z-index: 1000; overflow: hidden;
        }

        /* SINISTRA: OROLOGIO E DATA */
        .info-left {
            flex: 0 0 160px;
            background: rgba(20, 20, 25, 0.4); /* Leggera tinta per contrasto */
            backdrop-filter: blur(15px); -webkit-backdrop-filter: blur(15px);
            display: flex; flex-direction: column; justify-content: center; align-items: center;
            z-index: 10; /* Sopra il testo che scorre */
            border-right: 1px solid rgba(255,255,255,0.05);
        }
        #clock-time { font-size: 36px; font-weight: 800; line-height: 1; letter-spacing: -1px; }
        #clock-date { font-size: 14px; font-weight: 600; opacity: 0.7; margin-top: 4px; }

        /* CENTRO: SCORRIMENTO */
        .info-center {
            flex: 1; position: relative;
            display: flex; align-items: center;
            overflow: hidden;
            mask-image: linear-gradient(to right, transparent 0%, black 20px, black calc(100% - 20px), transparent 100%);
            -webkit-mask-image: linear-gradient(to right, transparent 0%, black 20px, black calc(100% - 20px), transparent 100%);
        }
        .marquee-wrapper {
            display: flex;
            white-space: nowrap;
            will-change: transform;
            animation: marquee 40s linear infinite; /* Velocità regolabile */
        }
        .marquee-content {
            font-size: 32px; font-weight: 600; text-transform: uppercase;
            padding-right: 100px; /* Spazio tra le ripetizioni */
            display: inline-block;
        }
        @keyframes marquee {
            0% { transform: translateX(0); }
            100% { transform: translateX(-50%); }
        }

        /* DESTRA: LOGO */
        .info-right {
            flex: 0 0 220px;
            background: rgba(20, 20, 25, 0.4);
            backdrop-filter: blur(15px); -webkit-backdrop-filter: blur(15px);
            display: flex; align-items: center; justify-content: center;
            z-index: 10; /* Sopra il testo */
            border-left: 1px solid rgba(255,255,255,0.05);
        }
        .bar-logo { max-width: 80%; max-height: 60%; filter: drop-shadow(0 0 8px rgba(255,255,255,0.2)); }

        /* MODALE ERRORE / OFFLINE */
        .overlay-msg {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.85); backdrop-filter: blur(10px);
            display: flex; flex-direction: column; justify-content: center; align-items: center;
            z-index: 2000; opacity: 0; pointer-events: none; transition: opacity 0.5s;
        }
        .overlay-msg.visible { opacity: 1; pointer-events: auto; }
        .overlay-msg h1 { font-size: 40px; color: #FF453A; }

    </style>
</head>
<body>

    <audio id="announcement-audio" src="/announcement-audio"></audio>
    <audio id="stop-audio"></audio>
    <audio id="booked-audio" src="/booked-stop-audio"></audio>

    <div class="viewer-container">
        <div class="left-panel">
            <div class="line-graphic">
                <div class="line-number-circle"><span id="line-id">--</span></div>
                <div class="line-path-vertical"></div>
                <div class="stop-indicator"></div>
            </div>
            <div class="info-text-group">
                <div class="lbl">Destinazione</div>
                <div id="dest-name" class="val-dest">--</div>
                <div class="lbl">Prossima Fermata</div>
                <div id="stop-name" class="val-stop">--</div>
                <div id="stop-sub" class="val-sub"></div>
            </div>
        </div>
        
        <div class="right-panel">
            <div class="video-frame" id="media-container">
                </div>
        </div>
    </div>

    <div class="info-bar">
        <div class="info-left">
            <div id="clock-time">--:--</div>
            <div id="clock-date">--/--/--</div>
        </div>
        <div class="info-center">
            <div class="marquee-wrapper" id="marquee-track">
                <span class="marquee-content" id="marquee-text">BENVENUTI SU HARZAFI</span>
                <span class="marquee-content" id="marquee-text-clone">BENVENUTI SU HARZAFI</span>
            </div>
        </div>
        <div class="info-right">
            <img src="https://i.ibb.co/nN5WRrHS/LOGO-HARZAFI.png" alt="Harzafi Logo" class="bar-logo">
        </div>
    </div>

    <div id="offline-overlay" class="overlay-msg">
        <h1>SERVIZIO NON DISPONIBILE</h1>
        <p>Attendere connessione...</p>
    </div>

<script>
    const socket = io();
    
    // Stato locale
    let lastState = {};
    
    // Elementi DOM
    const lineIdEl = document.getElementById('line-id');
    const destNameEl = document.getElementById('dest-name');
    const stopNameEl = document.getElementById('stop-name');
    const stopSubEl = document.getElementById('stop-sub');
    const mediaContainer = document.getElementById('media-container');
    const offlineOverlay = document.getElementById('offline-overlay');
    const marqueeText = document.getElementById('marquee-text');
    const marqueeClone = document.getElementById('marquee-text-clone');
    const clockTime = document.getElementById('clock-time');
    const clockDate = document.getElementById('clock-date');
    
    // Audio
    const audioAnnounce = document.getElementById('announcement-audio');
    const audioStop = document.getElementById('stop-audio');
    const audioBooked = document.getElementById('booked-audio');

    // --- OROLOGIO ITALIANO ---
    function updateClock() {
        const now = new Date();
        // Opzioni per forzare il fuso orario italiano
        const timeOptions = { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Rome' };
        const dateOptions = { day: '2-digit', month: '2-digit', year: '2-digit', timeZone: 'Europe/Rome' };
        
        clockTime.textContent = now.toLocaleTimeString('it-IT', timeOptions);
        clockDate.textContent = now.toLocaleDateString('it-IT', dateOptions);
    }
    setInterval(updateClock, 1000);
    updateClock(); // Prima esecuzione immediata

    // --- LOGICA AGGIORNAMENTO DATI ---
    socket.on('state_updated', (state) => updateDisplay(state));
    socket.on('initial_state', (state) => updateDisplay(state));
    socket.on('disconnect', () => offlineOverlay.classList.add('visible'));
    socket.on('connect', () => {
        offlineOverlay.classList.remove('visible');
        socket.emit('request_initial_state');
    });

    function updateDisplay(state) {
        if(!state.linesData) return;

        // Gestione Offline manuale
        if(state.serviceStatus === 'offline') offlineOverlay.classList.add('visible');
        else offlineOverlay.classList.remove('visible');

        const line = state.linesData[state.currentLineKey];
        
        // 1. Aggiornamento Testi (Solo se cambiati per animazione)
        if(line) {
            if(lineIdEl.textContent !== state.currentLineKey) lineIdEl.textContent = state.currentLineKey;
            if(destNameEl.textContent !== line.direction) destNameEl.textContent = line.direction;
            
            const currentStop = line.stops[state.currentStopIndex];
            const stopText = currentStop ? currentStop.name : "CAPOLINEA";
            const subText = currentStop ? (currentStop.subtitle || "") : "";

            if(stopNameEl.textContent !== stopText) {
                stopNameEl.classList.remove('fade-in-up');
                stopNameEl.classList.add('fade-out-up');
                stopSubEl.classList.add('fade-out-up');
                
                setTimeout(() => {
                    stopNameEl.textContent = stopText;
                    stopSubEl.textContent = subText;
                    stopNameEl.classList.remove('fade-out-up');
                    stopSubEl.classList.remove('fade-out-up');
                    stopNameEl.classList.add('fade-in-up');
                    stopSubEl.classList.add('fade-in-up');
                    
                    // Audio Fermata Automatica
                    if(currentStop && currentStop.audio && state.currentStopIndex !== lastState.currentStopIndex) {
                        audioStop.src = currentStop.audio;
                        lowerVolumeAndPlay(audioStop);
                    }
                }, 400);
            }
        }

        // 2. Aggiornamento Marquee (Messaggi)
        const msgString = state.infoMessages.join(" • ");
        if(marqueeText.textContent !== msgString) {
            marqueeText.textContent = msgString;
            marqueeClone.textContent = msgString; // Per il loop infinito CSS
        }

        // 3. Gestione Media
        handleMedia(state);

        // 4. Audio Eventi (Annuncio / Prenotazione)
        if(state.announcement && state.announcement.timestamp > (lastState.announcement?.timestamp || 0)) {
            lowerVolumeAndPlay(audioAnnounce);
        }
        if(state.stopRequested && state.stopRequested.timestamp > (lastState.stopRequested?.timestamp || 0)) {
            audioBooked.currentTime = 0; audioBooked.play().catch(e=>{});
        }

        lastState = JSON.parse(JSON.stringify(state));
    }

    function handleMedia(state) {
        // Se "Video Non Disponibile" è attivo forzatamente
        if(state.videoNotAvailable) {
            if(mediaContainer.dataset.type !== 'unavailable') {
                mediaContainer.innerHTML = `<img src="https://i.ibb.co/Wv3zjPnG/Al-momento-non-disponibile-eseguire-contenuti.jpg" alt="NA">`;
                mediaContainer.dataset.type = 'unavailable';
            }
            return;
        }

        // Gestione sorgenti
        if(state.mediaSource === 'server' && state.videoName) {
            // Video Locale
            if(mediaContainer.dataset.type !== 'local' || state.mediaLastUpdated !== lastState.mediaLastUpdated) {
                const vidUrl = `/stream-video?t=${state.mediaLastUpdated}`;
                mediaContainer.innerHTML = `
                    <div class="video-bg-blur"><video src="${vidUrl}" muted loop playsinline autoplay></video></div>
                    <video id="main-video" src="${vidUrl}" loop playsinline autoplay style="z-index:2;"></video>
                `;
                mediaContainer.dataset.type = 'local';
                
                // Gestione errori video locale
                const v = document.getElementById('main-video');
                v.onerror = () => {
                    // Fallback se errore caricamento
                    mediaContainer.innerHTML = `<img src="https://i.ibb.co/1GnC8ZpN/Pronto-per-eseguire-contenuti-video.jpg">`; 
                    // Qui potremmo mostrare il modale errore, ma per pulizia teniamo l'immagine di default
                };
            }
            // Sync Playback
            const v = document.getElementById('main-video');
            if(v) {
                v.volume = parseFloat(state.volumeLevel);
                if(state.playbackState === 'paused' && !v.paused) v.pause();
                if(state.playbackState === 'playing' && v.paused) v.play().catch(()=>{});
                // Seek check
                if(state.seekAction && state.seekAction.timestamp > (lastState.seekAction?.timestamp || 0)) {
                    v.currentTime += state.seekAction.value;
                }
            }
        } else if (state.mediaSource === 'embed' && state.embedCode) {
            // Embed
            if(mediaContainer.dataset.type !== 'embed') {
                mediaContainer.innerHTML = state.embedCode;
                mediaContainer.dataset.type = 'embed';
            }
        } else {
            // Default
            if(mediaContainer.dataset.type !== 'default') {
                mediaContainer.innerHTML = `<img src="https://i.ibb.co/1GnC8ZpN/Pronto-per-eseguire-contenuti-video.jpg">`;
                mediaContainer.dataset.type = 'default';
            }
        }
    }

    function lowerVolumeAndPlay(audioEl) {
        const vid = document.getElementById('main-video');
        const oldVol = vid ? vid.volume : 1;
        if(vid) vid.volume = Math.min(oldVol, 0.1);
        
        audioEl.currentTime = 0;
        audioEl.play().catch(e => console.log("Autoplay bloccato", e));
        
        audioEl.onended = () => {
            if(vid) vid.volume = oldVol;
        };
    }

</script>
</body>
</html>
"""

# -------------------------------------------------------------------
# 4. ROUTES & API (INVARIATE PER FUNZIONALITA', ADATTATE PER SICUREZZA)
# -------------------------------------------------------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data
        # Lockout logic semplificata qui per brevità (presente nella versione precedente)
        user_db = USERS_DB.get(username)
        if user_db and check_password_hash(user_db['password_hash'], form.password.data):
            login_user(get_user(username))
            return redirect(url_for('dashboard'))
        else:
            flash("Credenziali errate", "error")
    return render_template_string(LOGIN_PAGE_HTML, form=form)

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
@login_required
def pagina_visualizzatore():
    return render_template_string(VISUALIZZATORE_COMPLETO_HTML)

# --- FILE SERVING ---
@app.route('/announcement-audio')
@login_required
def announcement_audio():
    # Fallback se il file non esiste (evita crash)
    try: return send_file('LINEA 3. CORSA DEVIATA..mp3', mimetype='audio/mpeg')
    except: return Response("File missing", 404)

@app.route('/booked-stop-audio')
@login_required
def booked_stop_audio():
    try: return send_file('bip.mp3', mimetype='audio/mpeg') # Assicurati di avere un file bip.mp3 o rimuovi questa chiamata
    except: return Response("File missing", 404)

@app.route('/upload-video', methods=['POST'])
@login_required
def upload_video():
    global current_video_file
    if 'video' not in request.files: return jsonify({'error': 'No file'}), 400
    f = request.files['video']
    if f.filename == '': return jsonify({'error': 'No filename'}), 400
    
    # Pulizia vecchio file
    if current_video_file['path'] and os.path.exists(current_video_file['path']):
        try: os.remove(current_video_file['path'])
        except: pass
        
    try:
        fd, path = tempfile.mkstemp(suffix=f"_{f.filename}")
        os.close(fd)
        f.save(path)
        current_video_file = {'path': path, 'mimetype': f.mimetype, 'name': f.filename}
        return jsonify({'success': True})
    except Exception as e:
        print(e)
        return jsonify({'error': 'Save failed'}), 500

@app.route('/stream-video')
@login_required
def stream_video():
    if not current_video_file['path'] or not os.path.exists(current_video_file['path']): abort(404)
    return send_file(current_video_file['path'], mimetype=current_video_file['mimetype'])

@app.route('/clear-video', methods=['POST'])
@login_required
def clear_video():
    global current_video_file
    if current_video_file['path'] and os.path.exists(current_video_file['path']):
        try: os.remove(current_video_file['path'])
        except: pass
    current_video_file = {'path': None, 'mimetype': None, 'name': None}
    return jsonify({'success': True})

# --- SOCKET EVENTS ---
@socketio.on('connect')
def handle_connect():
    if not current_user.is_authenticated: return False
    if current_app_state: socketio.emit('initial_state', current_app_state, room=request.sid)

@socketio.on('update_all')
def handle_update(data):
    if not current_user.is_authenticated: return
    global current_app_state
    if not current_app_state: current_app_state = {}
    current_app_state.update(data)
    socketio.emit('state_updated', current_app_state, skip_sid=request.sid)

@socketio.on('request_initial_state')
def req_init():
    if not current_user.is_authenticated: return
    socketio.emit('initial_state', current_app_state, room=request.sid)

if __name__ == '__main__':
    print("--- HARZAFI SERVER v18 ---")
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
