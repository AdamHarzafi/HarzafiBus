import sys
import socket
import re 
import os
import tempfile
import time
from functools import wraps
from datetime import datetime, timedelta
from flask import Flask, Response, request, abort, jsonify, render_template_string, redirect, url_for, flash, send_file
from flask_socketio import SocketIO
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField
from wtforms.validators import DataRequired

# ==============================================================================
# CONFIGURAZIONE DI SICUREZZA E SISTEMA
# ==============================================================================

SECRET_KEY_FLASK = "chiave-segreta-molto-complessa-e-sicura-v2025-final-release"

# Protezione Brute-Force
login_attempts = {}
MAX_ATTEMPTS = 5
LOCKOUT_TIME_MINUTES = 10

# Database Utenti Simulato
USERS_DB = {
    "admin": {
        "password_hash": generate_password_hash("adminpass"),
        "name": "Amministratore Harzafi"
    }
}

# Variabili Globali di Stato (Memoria Volatile)
current_app_state = {
    "linesData": {},
    "currentLineKey": None,
    "currentStopIndex": 0,
    "mediaSource": None,      # 'server' o 'embed'
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

# Gestione File Video (Percorso su disco)
current_video_file = {'path': None, 'mimetype': None, 'name': None}

# ==============================================================================
# CLASSI E FUNZIONI DI SUPPORTO
# ==============================================================================

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

def get_local_ip():
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        if s: s.close()
    return IP

# ==============================================================================
# INIZIALIZZAZIONE FLASK
# ==============================================================================

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY_FLASK
app.config['WTF_CSRF_SECRET_KEY'] = SECRET_KEY_FLASK
# Max upload size (es. 500MB)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024 

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Accesso negato. Effettua il login."

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

# ==============================================================================
# TEMPLATE HTML (INCLUSI DIRETTAMENTE PER PORTABILITÀ)
# ==============================================================================

# 1. LOGIN PAGE (Design Interfaccia Pulita)
LOGIN_PAGE_HTML = """
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Harzafi System - Login</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-dark: #0f172a; --bg-card: #1e293b; --primary: #8b5cf6; --text: #f8fafc;
        }
        body {
            background-color: var(--bg-dark); color: var(--text); font-family: 'Inter', sans-serif;
            display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0;
            background-image: radial-gradient(circle at center, #1e293b 0%, #0f172a 100%);
        }
        .login-box {
            background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(12px);
            padding: 40px; border-radius: 20px; border: 1px solid rgba(255,255,255,0.1);
            width: 100%; max-width: 400px; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5);
            text-align: center;
        }
        .logo { width: 120px; margin-bottom: 20px; filter: drop-shadow(0 0 10px rgba(139, 92, 246, 0.3)); }
        h2 { margin-bottom: 30px; font-weight: 700; letter-spacing: -0.5px; }
        input {
            width: 100%; padding: 14px; margin-bottom: 15px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.1);
            background: rgba(15, 23, 42, 0.6); color: white; box-sizing: border-box; font-size: 16px;
            transition: all 0.3s ease;
        }
        input:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 2px rgba(139, 92, 246, 0.2); }
        button {
            width: 100%; padding: 14px; border: none; border-radius: 10px;
            background: linear-gradient(135deg, #8b5cf6, #d946ef); color: white;
            font-weight: 700; font-size: 16px; cursor: pointer; transition: transform 0.2s;
        }
        button:hover { transform: translateY(-2px); box-shadow: 0 10px 20px rgba(139, 92, 246, 0.3); }
        .alert {
            background: rgba(239, 68, 68, 0.2); color: #fca5a5; padding: 10px;
            border-radius: 8px; margin-bottom: 20px; font-size: 14px; border: 1px solid rgba(239, 68, 68, 0.3);
        }
    </style>
</head>
<body>
    <div class="login-box">
        <img src="https://i.ibb.co/nN5WRrHS/LOGO-HARZAFI.png" alt="Logo" class="logo">
        <h2>Area Riservata</h2>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        <form method="post">
            {{ form.hidden_tag() }}
            {{ form.username(placeholder="Username...") }}
            {{ form.password(placeholder="Password...") }}
            <button type="submit">ACCEDI AL SISTEMA</button>
        </form>
    </div>
</body>
</html>
"""

# 2. DASHBOARD (Pannello di Controllo Completo - Codice "lungo" originale)
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Harzafi Control Center</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
    <style>
        :root {
            --bg-main: #000000; --bg-panel: #1c1c1e; --bg-input: #2c2c2e;
            --text-main: #f2f2f7; --text-muted: #8e8e93;
            --accent: #0a84ff; --danger: #ff453a; --success: #30d158; --warning: #ff9f0a;
            --border: #3a3a3c;
        }
        * { box-sizing: border-box; }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background-color: var(--bg-main); color: var(--text-main);
            margin: 0; padding: 0; height: 100vh; display: flex; flex-direction: column;
        }
        
        /* Header */
        header {
            background: rgba(28, 28, 30, 0.8); backdrop-filter: blur(20px);
            padding: 15px 30px; border-bottom: 1px solid var(--border);
            display: flex; justify-content: space-between; align-items: center;
            position: sticky; top: 0; z-index: 100;
        }
        .brand { display: flex; align-items: center; gap: 15px; }
        .brand img { height: 40px; }
        .brand h1 { font-size: 20px; font-weight: 700; margin: 0; letter-spacing: -0.5px; }
        
        /* Layout */
        .container {
            flex: 1; padding: 30px; overflow-y: auto;
            display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 25px;
            max-width: 1600px; margin: 0 auto; width: 100%;
        }
        
        /* Cards */
        .card {
            background: var(--bg-panel); border-radius: 18px; padding: 25px;
            border: 1px solid var(--border); transition: transform 0.2s;
        }
        .card h2 { margin-top: 0; font-size: 18px; color: var(--text-muted); text-transform: uppercase; font-weight: 600; letter-spacing: 1px; margin-bottom: 20px; }
        
        /* Inputs & Controls */
        label { display: block; margin-bottom: 8px; font-weight: 500; font-size: 14px; color: var(--text-muted); }
        input[type="text"], input[type="number"], select, textarea {
            width: 100%; padding: 12px; background: var(--bg-input); border: 1px solid var(--border);
            border-radius: 10px; color: white; font-size: 15px; margin-bottom: 15px;
            font-family: inherit;
        }
        input:focus { outline: none; border-color: var(--accent); }
        
        button {
            padding: 12px 20px; border-radius: 10px; border: none; font-weight: 600;
            font-size: 14px; cursor: pointer; transition: filter 0.2s;
            display: inline-flex; align-items: center; justify-content: center; gap: 8px;
        }
        button:hover { filter: brightness(1.1); }
        .btn-primary { background: var(--accent); color: white; }
        .btn-danger { background: var(--danger); color: white; }
        .btn-success { background: var(--success); color: white; }
        .btn-secondary { background: var(--bg-input); color: white; border: 1px solid var(--border); }
        .btn-full { width: 100%; margin-bottom: 10px; }
        
        /* Status Card Special */
        .status-display {
            background: linear-gradient(135deg, #2c2c2e 0%, #000000 100%);
            border-radius: 12px; padding: 20px; text-align: center; border: 1px solid var(--border);
        }
        .status-big { font-size: 32px; font-weight: 800; margin: 10px 0; line-height: 1.1; }
        .status-sub { color: var(--text-muted); font-size: 14px; }
        
        /* Toggle Switch */
        .switch-container { display: flex; align-items: center; justify-content: space-between; background: var(--bg-input); padding: 12px; border-radius: 10px; margin-bottom: 10px; }
        .toggle-switch { position: relative; width: 50px; height: 28px; }
        .toggle-switch input { opacity: 0; width: 0; height: 0; }
        .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #48484a; transition: .4s; border-radius: 34px; }
        .slider:before { position: absolute; content: ""; height: 24px; width: 24px; left: 2px; bottom: 2px; background-color: white; transition: .4s; border-radius: 50%; }
        input:checked + .slider { background-color: var(--success); }
        input:checked + .slider:before { transform: translateX(22px); }
        
        /* Media Controls */
        .media-controls { display: flex; gap: 10px; margin-bottom: 15px; }
        .media-btn { width: 45px; height: 45px; border-radius: 50%; font-size: 18px; padding: 0; }
        
        /* List Management */
        .list-group { list-style: none; padding: 0; margin: 0; max-height: 300px; overflow-y: auto; }
        .list-item {
            background: var(--bg-input); padding: 12px; margin-bottom: 8px; border-radius: 10px;
            display: flex; justify-content: space-between; align-items: center;
        }
        .list-actions button { padding: 5px 10px; font-size: 12px; margin-left: 5px; }

        /* Modal */
        dialog {
            background: var(--bg-panel); color: white; border: 1px solid var(--border);
            border-radius: 20px; padding: 30px; width: 90%; max-width: 600px;
            box-shadow: 0 50px 100px -20px rgba(0,0,0,0.8);
        }
        dialog::backdrop { background: rgba(0,0,0,0.7); backdrop-filter: blur(5px); }
        
        /* Stop Item in Editor */
        .stop-row { display: flex; gap: 10px; margin-bottom: 10px; align-items: center; }
        .audio-indicator { width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; cursor: pointer; border: 2px solid transparent; }
        .has-audio { background: var(--success); color: black; }
        .no-audio { background: var(--danger); color: white; }
        
    </style>
</head>
<body>
    <header>
        <div class="brand">
            <img src="https://i.ibb.co/nN5WRrHS/LOGO-HARZAFI.png" alt="Logo">
            <h1>CONTROL CENTER</h1>
        </div>
        <div>
            <a href="{{ url_for('pagina_visualizzatore') }}" target="_blank"><button class="btn-secondary">Apri Visualizzatore</button></a>
            <a href="{{ url_for('logout') }}"><button class="btn-danger">Logout</button></a>
        </div>
    </header>

    <div class="container">
        <!-- COLONNA 1: STATO E NAVIGAZIONE -->
        <div class="card">
            <h2>Monitoraggio Live</h2>
            <div class="status-display">
                <span class="status-sub">FERMATA ATTUALE</span>
                <div class="status-big" id="live-stop-name">--</div>
                <div class="status-sub" id="live-line-info">NESSUNA LINEA ATTIVA</div>
            </div>
            
            <div style="margin-top: 25px;">
                <label>Seleziona Linea</label>
                <select id="line-selector"></select>
                
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                    <button id="prev-btn" class="btn-secondary">◀ INDIETRO</button>
                    <button id="next-btn" class="btn-secondary">AVANTI ▶</button>
                </div>
            </div>
            
            <div style="margin-top: 20px; display: grid; gap: 10px;">
                <button id="announce-btn" class="btn-primary btn-full">📢 ANNUNCIO VOCALE</button>
                <button id="booked-btn" class="btn-warning btn-full">🔔 PRENOTA FERMATA</button>
            </div>
        </div>

        <!-- COLONNA 2: MEDIA E VIDEO -->
        <div class="card">
            <h2>Gestione Multimedia</h2>
            
            <label>Modalità "Video Non Disponibile"</label>
            <div class="switch-container">
                <span>Forza Schermata Errore</span>
                <label class="toggle-switch">
                    <input type="checkbox" id="video-not-available-toggle">
                    <span class="slider"></span>
                </label>
            </div>

            <hr style="border-color: var(--border); margin: 20px 0;">

            <label>Caricamento Video (Locale)</label>
            <input type="file" id="video-upload-input" accept="video/*" style="display: none;">
            <button class="btn-secondary btn-full" onclick="document.getElementById('video-upload-input').click()">📂 Scegli File Video</button>
            <div id="upload-progress" style="height: 4px; background: var(--bg-input); margin-top: 5px; border-radius: 2px; overflow: hidden;">
                <div id="upload-bar" style="width: 0%; height: 100%; background: var(--accent); transition: width 0.3s;"></div>
            </div>
            <p id="current-video-label" style="font-size: 12px; color: var(--text-muted); margin-top: 5px;">Nessun video caricato</p>

            <hr style="border-color: var(--border); margin: 20px 0;">
            
            <label>Controlli Riproduzione</label>
            <div class="media-controls">
                <button class="btn-secondary media-btn" id="seek-back">⏪</button>
                <button class="btn-primary media-btn" id="play-pause">⏯</button>
                <button class="btn-secondary media-btn" id="seek-fwd">⏩</button>
            </div>
            <input type="range" id="volume-slider" min="0" max="1" step="0.1" value="1" style="width: 100%;">
        </div>

        <!-- COLONNA 3: MESSAGGI E CONFIGURAZIONE -->
        <div class="card">
            <h2>Ticker & Configurazioni</h2>
            
            <label>Messaggi Scorrevoli (Liquid Bar)</label>
            <textarea id="ticker-input" rows="5" placeholder="Inserisci messaggi, uno per riga..."></textarea>
            <button id="save-ticker-btn" class="btn-success btn-full">Aggiorna Barra</button>
            
            <hr style="border-color: var(--border); margin: 20px 0;">
            
            <label>Gestione Database Linee</label>
            <ul id="lines-list" class="list-group"></ul>
            
            <div style="margin-top: 15px; display: grid; gap: 10px;">
                <button id="add-line-btn" class="btn-secondary btn-full">➕ Nuova Linea</button>
                <button id="reset-db-btn" class="btn-danger btn-full">⚠️ Reset Fabbrica</button>
            </div>
        </div>
    </div>

    <!-- MODALE EDITOR LINEA -->
    <dialog id="editor-modal">
        <h2 style="margin-top: 0;">Editor Linea</h2>
        <form id="editor-form">
            <input type="hidden" id="edit-original-id">
            
            <label>Codice Linea (es. 3, 15, 68)</label>
            <input type="text" id="edit-line-code" required>
            
            <label>Destinazione</label>
            <input type="text" id="edit-line-dest" required>
            
            <label>Lista Fermate</label>
            <div id="editor-stops-container" style="max-height: 300px; overflow-y: auto; margin-bottom: 20px; padding-right: 10px;">
                <!-- Stop rows injected here -->
            </div>
            
            <button type="button" id="add-stop-row-btn" class="btn-secondary btn-full" style="margin-bottom: 20px;">+ Aggiungi Fermata</button>
            
            <div style="display: flex; justify-content: flex-end; gap: 10px;">
                <button type="button" id="close-modal-btn" class="btn-secondary">Annulla</button>
                <button type="submit" class="btn-success">Salva Modifiche</button>
            </div>
        </form>
    </dialog>

<script>
    const socket = io();
    
    // Stato Locale
    let linesData = {};
    let currentLineKey = null;
    let currentStopIndex = 0;
    
    // Default Data Factory
    function getDefaultData() {
        return {
            "3": { "direction": "CORSA DEVIATA", "stops": [
                { "name": "VALLETTE", "subtitle": "TERMINAL", "audio": null }, 
                { "name": "PRIMULE", "subtitle": "", "audio": null },
                { "name": "PERVINCHE", "subtitle": "", "audio": null }
            ]}
        };
    }

    // --- LOGICA DI CARICAMENTO ---
    function init() {
        const stored = localStorage.getItem('harzafi_data');
        if (stored) linesData = JSON.parse(stored);
        else linesData = getDefaultData();
        
        renderLineSelector();
        renderLinesList();
        
        // Restore Ticker
        const storedTicker = JSON.parse(localStorage.getItem('harzafi_ticker') || '[]');
        document.getElementById('ticker-input').value = storedTicker.join('\\n');
        
        // Restore Line Selection
        const savedLine = localStorage.getItem('harzafi_current_line');
        if (savedLine && linesData[savedLine]) {
            currentLineKey = savedLine;
            document.getElementById('line-selector').value = savedLine;
        } else {
            // Select first available
            const keys = Object.keys(linesData);
            if(keys.length > 0) currentLineKey = keys[0];
        }
        
        updateLiveStatus();
        sendFullUpdate();
    }

    function sendFullUpdate() {
        const state = {
            linesData: linesData,
            currentLineKey: currentLineKey,
            currentStopIndex: currentStopIndex,
            infoMessages: document.getElementById('ticker-input').value.split('\\n').filter(l => l.trim() !== ''),
            videoNotAvailable: document.getElementById('video-not-available-toggle').checked,
            volumeLevel: document.getElementById('volume-slider').value,
            // Media info is handled by server, but client triggers display updates
            timestamp: Date.now()
        };
        socket.emit('update_all', state);
    }

    function saveData() {
        localStorage.setItem('harzafi_data', JSON.stringify(linesData));
        localStorage.setItem('harzafi_current_line', currentLineKey);
        renderLineSelector();
        renderLinesList();
        updateLiveStatus();
        sendFullUpdate();
    }

    // --- RENDERING UI ---
    function renderLineSelector() {
        const sel = document.getElementById('line-selector');
        sel.innerHTML = '';
        Object.keys(linesData).sort().forEach(key => {
            const opt = document.createElement('option');
            opt.value = key;
            opt.text = `${key} ➝ ${linesData[key].direction}`;
            sel.appendChild(opt);
        });
        if(currentLineKey) sel.value = currentLineKey;
    }

    function renderLinesList() {
        const list = document.getElementById('lines-list');
        list.innerHTML = '';
        Object.keys(linesData).sort().forEach(key => {
            const li = document.createElement('li');
            li.className = 'list-item';
            li.innerHTML = `
                <div><strong>${key}</strong> <span style="font-size:12px; opacity:0.7">${linesData[key].direction}</span></div>
                <div class="list-actions">
                    <button class="btn-secondary" onclick="openEditor('${key}')">✏️</button>
                    <button class="btn-danger" onclick="deleteLine('${key}')">🗑️</button>
                </div>
            `;
            list.appendChild(li);
        });
    }

    function updateLiveStatus() {
        if (!currentLineKey || !linesData[currentLineKey]) {
            document.getElementById('live-stop-name').innerText = "--";
            document.getElementById('live-line-info').innerText = "NESSUNA LINEA";
            return;
        }
        const line = linesData[currentLineKey];
        // Bounds check
        if (currentStopIndex >= line.stops.length) currentStopIndex = line.stops.length - 1;
        if (currentStopIndex < 0) currentStopIndex = 0;
        
        const stop = line.stops[currentStopIndex];
        document.getElementById('live-stop-name').innerText = stop.name;
        document.getElementById('live-line-info').innerText = `${currentLineKey} ➝ ${line.direction} (${currentStopIndex + 1}/${line.stops.length})`;
    }

    // --- EVENT LISTENERS ---
    document.getElementById('line-selector').addEventListener('change', (e) => {
        currentLineKey = e.target.value;
        currentStopIndex = 0;
        saveData();
    });

    document.getElementById('next-btn').addEventListener('click', () => {
        if(currentLineKey && linesData[currentLineKey] && currentStopIndex < linesData[currentLineKey].stops.length - 1) {
            currentStopIndex++;
            saveData();
        }
    });

    document.getElementById('prev-btn').addEventListener('click', () => {
        if(currentStopIndex > 0) {
            currentStopIndex--;
            saveData();
        }
    });
    
    // Ticker Save
    document.getElementById('save-ticker-btn').addEventListener('click', () => {
        localStorage.setItem('harzafi_ticker', JSON.stringify(document.getElementById('ticker-input').value.split('\\n')));
        sendFullUpdate();
        alert("Barra aggiornata!");
    });

    // One-Shot Events
    document.getElementById('announce-btn').addEventListener('click', () => {
        socket.emit('update_all', { announcement: { timestamp: Date.now() } });
    });
    document.getElementById('booked-btn').addEventListener('click', () => {
        socket.emit('update_all', { stopRequested: { timestamp: Date.now() } });
    });
    
    // Video Not Available Toggle
    document.getElementById('video-not-available-toggle').addEventListener('change', sendFullUpdate);
    
    // Volume & Media Controls
    document.getElementById('volume-slider').addEventListener('input', sendFullUpdate);
    document.getElementById('play-pause').addEventListener('click', () => {
        // Toggle Logic simplistic
        socket.emit('update_all', { playbackState: 'toggle', timestamp: Date.now() });
    });
    
    // --- VIDEO UPLOAD LOGIC ---
    document.getElementById('video-upload-input').addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if(!file) return;
        
        const formData = new FormData();
        formData.append('video', file);
        
        document.getElementById('current-video-label').innerText = "Caricamento in corso...";
        
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/upload-video', true);
        
        xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) {
                const percent = (e.loaded / e.total) * 100;
                document.getElementById('upload-bar').style.width = percent + '%';
            }
        };
        
        xhr.onload = () => {
            if (xhr.status === 200) {
                document.getElementById('current-video-label').innerText = "Video attivo: " + file.name;
                document.getElementById('upload-bar').style.width = '0%';
                socket.emit('update_all', { mediaSource: 'server', mediaLastUpdated: Date.now() });
                alert("Upload completato!");
            } else {
                alert("Errore upload!");
            }
        };
        
        xhr.send(formData);
    });

    // --- EDITOR MODAL LOGIC ---
    window.openEditor = (key) => {
        const line = linesData[key];
        document.getElementById('edit-original-id').value = key;
        document.getElementById('edit-line-code').value = key;
        document.getElementById('edit-line-dest').value = line.direction;
        
        const container = document.getElementById('editor-stops-container');
        container.innerHTML = '';
        line.stops.forEach(stop => addStopRow(stop));
        
        document.getElementById('editor-modal').showModal();
    };
    
    window.deleteLine = (key) => {
        if(confirm('Sei sicuro di eliminare la linea ' + key + '?')) {
            delete linesData[key];
            if(currentLineKey === key) currentLineKey = null;
            saveData();
        }
    };
    
    document.getElementById('close-modal-btn').addEventListener('click', () => document.getElementById('editor-modal').close());
    
    document.getElementById('add-stop-row-btn').addEventListener('click', () => addStopRow());
    
    function addStopRow(data = {name: '', subtitle: '', audio: null}) {
        const div = document.createElement('div');
        div.className = 'stop-row';
        div.innerHTML = `
            <div class="audio-indicator ${data.audio ? 'has-audio' : 'no-audio'}" onclick="triggerAudio(this)" title="Carica Audio">🎤</div>
            <input type="file" style="display:none" accept="audio/*" onchange="handleAudioSelect(this)">
            <input type="text" placeholder="Nome" value="${data.name}" class="stop-name-input">
            <input type="text" placeholder="Sottotitolo" value="${data.subtitle}" class="stop-sub-input">
            <button type="button" class="btn-danger" onclick="this.parentElement.remove()" style="padding: 8px;">✕</button>
        `;
        // Store existing audio data in DOM element property if needed, simplified here by logic
        div.dataset.audio = data.audio || '';
        document.getElementById('editor-stops-container').appendChild(div);
    }
    
    window.triggerAudio = (el) => el.nextElementSibling.click();
    window.handleAudioSelect = (input) => {
        const file = input.files[0];
        if(file) {
            const reader = new FileReader();
            reader.onload = (e) => {
                input.parentElement.dataset.audio = e.target.result;
                const ind = input.previousElementSibling;
                ind.classList.remove('no-audio');
                ind.classList.add('has-audio');
            };
            reader.readAsDataURL(file);
        }
    };
    
    document.getElementById('editor-form').addEventListener('submit', (e) => {
        e.preventDefault();
        const oldKey = document.getElementById('edit-original-id').value;
        const newKey = document.getElementById('edit-line-code').value;
        const newDest = document.getElementById('edit-line-dest').value;
        
        const stops = [];
        document.querySelectorAll('.stop-row').forEach(row => {
            stops.push({
                name: row.querySelector('.stop-name-input').value.toUpperCase(),
                subtitle: row.querySelector('.stop-sub-input').value.toUpperCase(),
                audio: row.dataset.audio || null
            });
        });
        
        if (oldKey && oldKey !== newKey) delete linesData[oldKey];
        linesData[newKey] = { direction: newDest, stops: stops };
        
        if (currentLineKey === oldKey) currentLineKey = newKey;
        
        saveData();
        document.getElementById('editor-modal').close();
    });
    
    document.getElementById('reset-db-btn').addEventListener('click', () => {
        if(confirm("ATTENZIONE: Questo cancellerà tutte le linee salvate. Continuare?")) {
            linesData = getDefaultData();
            currentLineKey = "3";
            currentStopIndex = 0;
            saveData();
            alert("Database resettato.");
        }
    });

    // Start
    init();
</script>
</body>
</html>
"""

# 3. VISUALIZZATORE (LIQUID GLASS TICKER - EFFETTO VETRO AVANZATO)
# Nota: CSS ottimizzato per l'effetto "Passaggio Sotto" e "Blur Reale"
VISUALIZZATORE_HTML = """
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Harzafi Viewer</title>
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;700;900&display=swap" rel="stylesheet">
    <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
    <style>
        :root {
            --glass-blur-amt: 30px; /* IL SEGRETO: Sfocatura alta */
            --glass-bg: rgba(255, 255, 255, 0.12);
            --glass-border: rgba(255, 255, 255, 0.3);
            --glass-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
            
            --grad-1: #D544A7;
            --grad-2: #4343A2;
        }
        
        body {
            margin: 0; overflow: hidden; height: 100vh; width: 100vw;
            font-family: 'Montserrat', sans-serif;
            background: linear-gradient(135deg, var(--grad-1), var(--grad-2));
            color: white;
        }

        /* SFONDO VIDEO / CONTENITORE PRINCIPALE */
        #media-layer {
            position: absolute;
            top: 20px; left: 20px; right: 20px; bottom: 140px; /* Lascia spazio alla barra */
            border-radius: 30px;
            overflow: hidden;
            box-shadow: 0 20px 50px rgba(0,0,0,0.5);
            background: #000;
            z-index: 1; /* Livello Base */
        }
        #media-layer video, #media-layer img, #media-layer iframe {
            width: 100%; height: 100%; object-fit: cover;
        }
        
        /* INFO FLUTTUANTI (Alto Sinistra) */
        .info-overlay {
            position: absolute; top: 50px; left: 60px; z-index: 10;
            text-shadow: 0 4px 20px rgba(0,0,0,0.8);
        }
        .info-overlay .label {
            font-size: 16px; font-weight: 700; letter-spacing: 2px;
            background: rgba(0,0,0,0.5); padding: 5px 12px; border-radius: 20px;
            backdrop-filter: blur(5px); display: inline-block; margin-bottom: 10px;
        }
        .info-overlay h1 {
            font-size: 7vw; font-weight: 900; line-height: 0.9; margin: 0;
            text-transform: uppercase;
        }
        .info-overlay h2 {
            font-size: 2.5vw; font-weight: 400; margin: 5px 0 0 0; opacity: 0.9;
        }

        /* ==========================================================================
           IL CUORE DEL DESIGN: LA LIQUID GLASS BAR (LAYERED)
           ========================================================================== */
        
        /* Contenitore Generale Posizionato in basso */
        .liquid-dock-container {
            position: absolute;
            bottom: 30px;
            left: 50%; transform: translateX(-50%);
            width: 95%; height: 100px;
            z-index: 100; /* Sopra al video */
            /* Non ha background, serve solo a posizionare gli elementi */
        }

        /* LAYER 1: IL TESTO CHE SCORRE (SOTTO) */
        /* Questo div è largo quanto tutta la barra, ma ha z-index inferiore ai lati */
        .ticker-layer {
            position: absolute;
            top: 0; bottom: 0; left: 0; right: 0;
            border-radius: 24px;
            background: rgba(255, 255, 255, 0.05); /* Vetro molto leggero al centro */
            border: 1px solid rgba(255, 255, 255, 0.15);
            box-shadow: var(--glass-shadow);
            backdrop-filter: blur(10px); /* Blur leggero per il centro */
            display: flex; align-items: center;
            overflow: hidden; /* Taglia il testo */
            z-index: 1; /* IMPORTANTE: Livello 1 */
        }

        .scrolling-text {
            white-space: nowrap;
            position: absolute;
            font-size: 42px; font-weight: 800; text-transform: uppercase;
            color: #ffffff; text-shadow: 0 2px 10px rgba(0,0,0,0.5);
            animation: marquee 25s linear infinite;
        }
        
        @keyframes marquee {
            0% { transform: translateX(100%); left: 100%; }
            100% { transform: translateX(-100%); left: -20%; }
        }

        /* LAYER 2: I PANNELLI LATERALI (SOPRA) - EFFETTO FROSTED */
        /* Questi pannelli si sovrappongono al Ticker Layer. */
        /* Grazie al backdrop-filter, il testo che ci passa sotto verrà sfocato */
        
        .glass-side {
            position: absolute; top: 0; bottom: 0;
            width: 280px;
            z-index: 5; /* IMPORTANTE: Livello superiore al testo */
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            
            /* STILE VETRO SPESSO */
            background: var(--glass-bg);
            backdrop-filter: blur(var(--glass-blur-amt)); /* SFOCA CIO' CHE C'E' SOTTO (IL TESTO) */
            -webkit-backdrop-filter: blur(var(--glass-blur-amt));
            box-shadow: inset 0 0 20px rgba(255,255,255,0.1); /* Luce interna */
            border: 1px solid var(--glass-border);
        }
        
        .glass-side.left {
            left: 0;
            border-top-left-radius: 24px; border-bottom-left-radius: 24px;
            border-right: 1px solid rgba(255,255,255,0.2);
        }
        
        .glass-side.right {
            right: 0;
            border-top-right-radius: 24px; border-bottom-right-radius: 24px;
            border-left: 1px solid rgba(255,255,255,0.2);
        }

        /* Contenuti Pannelli */
        #clock-time { font-size: 40px; font-weight: 900; line-height: 0.9; text-shadow: 0 2px 5px rgba(0,0,0,0.2); }
        #clock-date { font-size: 14px; font-weight: 600; text-transform: uppercase; margin-top: 4px; letter-spacing: 1px; }
        
        .logo-container img {
            max-height: 65px;
            filter: drop-shadow(0 4px 8px rgba(0,0,0,0.3));
        }
        
        /* Modale Errore Video (Stile Apple) */
        #error-modal {
            position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
            background: rgba(30,30,30, 0.9); backdrop-filter: blur(20px);
            padding: 40px; border-radius: 24px; text-align: center;
            border: 1px solid rgba(255,255,255,0.2);
            box-shadow: 0 20px 60px rgba(0,0,0,0.6);
            display: none; z-index: 2000;
        }
        #error-modal.visible { display: block; animation: popIn 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275); }
        @keyframes popIn { from { transform: translate(-50%, -50%) scale(0.8); opacity: 0; } to { transform: translate(-50%, -50%) scale(1); opacity: 1; } }
        
        /* Loader */
        #loader {
            position: fixed; inset: 0; background: #000; z-index: 3000;
            display: flex; align-items: center; justify-content: center;
            transition: opacity 1s;
        }
        #loader.fade-out { opacity: 0; pointer-events: none; }

    </style>
</head>
<body>

    <!-- LOADER INIZIALE -->
    <div id="loader">
        <img src="https://i.ibb.co/nN5WRrHS/LOGO-HARZAFI.png" width="200">
    </div>

    <!-- CONTENUTO MULTIMEDIALE -->
    <div id="media-layer">
        <!-- Contenuto iniettato via JS -->
    </div>

    <!-- INFO STOP -->
    <div class="info-overlay">
        <span class="label">PROSSIMA FERMATA</span>
        <h1 id="stop-main">--</h1>
        <h2 id="stop-sub">--</h2>
        <div style="margin-top: 15px; font-size: 14px; font-weight: 600; background: rgba(0,0,0,0.6); display: inline-block; padding: 4px 10px; border-radius: 4px;">
            DESTINAZIONE: <span id="line-dest">--</span>
        </div>
    </div>

    <!-- BARRA LIQUID GLASS -->
    <div class="liquid-dock-container">
        
        <!-- SX: OROLOGIO (Layer Top) -->
        <div class="glass-side left">
            <div id="clock-time">00:00</div>
            <div id="clock-date">LOADING...</div>
        </div>

        <!-- CENTER: TESTO (Layer Bottom) -->
        <div class="ticker-layer">
            <div class="scrolling-text" id="ticker-text">
                HARZAFI TRANSPORT SYSTEM - SISTEMA DI INFORMAZIONE PASSEGGERI AVANZATO
            </div>
        </div>

        <!-- DX: LOGO (Layer Top) -->
        <div class="glass-side right">
            <div class="logo-container">
                <img src="https://i.ibb.co/nN5WRrHS/LOGO-HARZAFI.png" alt="Harzafi Logo">
            </div>
        </div>
    </div>

    <!-- AUDIO -->
    <audio id="audio-ann" src="/announcement-audio"></audio>
    <audio id="audio-stop"></audio>
    <audio id="audio-bip" src="{{ url_for('booked_stop_audio') }}"></audio>

    <!-- ERROR MODAL -->
    <div id="error-modal">
        <h2 style="margin:0 0 10px 0;">⚠️ Errore Riproduzione</h2>
        <p>Il contenuto video non è disponibile o è danneggiato.</p>
        <button onclick="document.getElementById('error-modal').classList.remove('visible')" style="margin-top:20px; padding:10px 20px; border-radius:20px; border:none; background:white; color:black; font-weight:bold; cursor:pointer;">CHIUDI</button>
    </div>

<script>
    const socket = io();
    
    // Elements
    const mediaDiv = document.getElementById('media-layer');
    const stopMain = document.getElementById('stop-main');
    const stopSub = document.getElementById('stop-sub');
    const lineDest = document.getElementById('line-dest');
    const tickerEl = document.getElementById('ticker-text');
    
    // State
    let lastState = {};
    let currentMediaType = 'none';

    // Clock
    function updateClock() {
        const now = new Date();
        document.getElementById('clock-time').innerText = now.toLocaleTimeString('it-IT', {timeZone:'Europe/Rome', hour:'2-digit', minute:'2-digit'});
        document.getElementById('clock-date').innerText = now.toLocaleDateString('it-IT', {timeZone:'Europe/Rome', day:'2-digit', month:'2-digit', year:'2-digit'});
    }
    setInterval(updateClock, 1000); updateClock();

    // Socket
    socket.on('connect', () => {
        document.getElementById('loader').classList.add('fade-out');
        socket.emit('request_initial_state');
    });

    socket.on('initial_state', updateUI);
    socket.on('state_updated', updateUI);

    function updateUI(state) {
        if(!state.linesData) return;

        // Line & Stop Info
        const line = state.linesData[state.currentLineKey];
        if(line) {
            lineDest.innerText = line.direction;
            const stop = line.stops[state.currentStopIndex];
            
            // Check for stop change (Audio trigger)
            if (stop && lastState.currentStopIndex !== state.currentStopIndex) {
                if (stop.audio) {
                    const audio = document.getElementById('audio-stop');
                    audio.src = stop.audio;
                    audio.play().catch(e => console.log(e));
                    duckVolume();
                }
            }
            
            if(stop) {
                stopMain.innerText = stop.name;
                stopSub.innerText = stop.subtitle;
            }
        }

        // Ticker
        if(state.infoMessages && state.infoMessages.length > 0) {
            const txt = state.infoMessages.join("  •  ");
            if(tickerEl.innerText !== txt) tickerEl.innerText = txt;
        }

        // Media Logic
        handleMedia(state);
        
        // One-Shots
        if(state.announcement && state.announcement.timestamp > (lastState.announcement?.timestamp || 0)) {
            document.getElementById('audio-ann').play(); duckVolume();
        }
        if(state.stopRequested && state.stopRequested.timestamp > (lastState.stopRequested?.timestamp || 0)) {
            document.getElementById('audio-bip').play();
        }

        lastState = JSON.parse(JSON.stringify(state));
    }

    function duckVolume() {
        const vid = document.getElementById('bg-video');
        if(vid) { vid.volume = 0.1; setTimeout(() => vid.volume = parseFloat(lastState.volumeLevel || 1), 3000); }
    }

    function handleMedia(state) {
        let type = 'default';
        if (state.videoNotAvailable) type = 'error_static';
        else if (state.mediaSource === 'server') type = 'server';
        else if (state.mediaSource === 'embed') type = 'embed';

        // Reload content only if type changed or explicit update
        if (type !== currentMediaType || (state.mediaLastUpdated > (lastState.mediaLastUpdated || 0))) {
            currentMediaType = type;
            mediaDiv.innerHTML = '';
            
            if (type === 'error_static') {
                 mediaDiv.innerHTML = `<img src="https://i.ibb.co/Wv3zjPnG/Al-momento-non-disponibile-eseguire-contenuti.jpg">`;
            } else if (type === 'default') {
                 mediaDiv.innerHTML = `<img src="https://i.ibb.co/1GnC8ZpN/Pronto-per-eseguire-contenuti-video.jpg">`;
            } else if (type === 'server') {
                 mediaDiv.innerHTML = `<video id="bg-video" src="/stream-video?t=${Date.now()}" loop autoplay playsinline muted></video>`;
                 const vid = document.getElementById('bg-video');
                 vid.volume = parseFloat(state.volumeLevel || 1);
                 vid.muted = false; // Try unmute
                 vid.play().catch(e => { console.log("Autoplay block", e); vid.muted = true; vid.play(); });
                 vid.onerror = () => document.getElementById('error-modal').classList.add('visible');
            } else if (type === 'embed') {
                 mediaDiv.innerHTML = state.embedCode;
            }
        }
        
        // Continuous Playback State
        const vid = document.getElementById('bg-video');
        if(vid && type === 'server') {
            vid.volume = parseFloat(state.volumeLevel || 1);
            if(state.playbackState === 'toggle') { 
                // Toggle handled by server timestamp usually, simple implementation here:
                if(vid.paused) vid.play(); else vid.pause(); 
            }
        }
    }
</script>
</body>
</html>
"""

# ==============================================================================
# ROUTE E LOGICA FLASK
# ==============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = USERS_DB.get(form.username.data)
        if user and check_password_hash(user['password_hash'], form.password.data):
            login_user(get_user(form.username.data))
            return redirect(url_for('dashboard'))
        flash("Credenziali non valide", "error")
    return render_template_string(LOGIN_PAGE_HTML, form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    return render_template_string(DASHBOARD_HTML)

@app.route('/visualizzatore')
@login_required
def pagina_visualizzatore():
    return render_template_string(VISUALIZZATORE_HTML)

# --- Gestione File Audio (Placeholder) ---
@app.route('/announcement-audio')
def announcement_audio():
    # In produzione, questo file dovrebbe esistere
    return send_file('LINEA 3. CORSA DEVIATA..mp3', mimetype='audio/mpeg') if os.path.exists('LINEA 3. CORSA DEVIATA..mp3') else Response(status=404)

@app.route('/booked-stop-audio')
def booked_stop_audio():
    return send_file('bip.mp3', mimetype='audio/mpeg') if os.path.exists('bip.mp3') else Response(status=404)

# --- Gestione Upload Video ---
@app.route('/upload-video', methods=['POST'])
@login_required
def upload_video():
    global current_video_file
    if 'video' not in request.files: return jsonify({'error': 'No file'}), 400
    file = request.files['video']
    if file.filename == '': return jsonify({'error': 'No name'}), 400
    
    # Pulizia vecchio file
    if current_video_file['path'] and os.path.exists(current_video_file['path']):
        try: os.remove(current_video_file['path'])
        except: pass
        
    try:
        # Salvataggio sicuro in temp
        fd, path = tempfile.mkstemp(suffix=f"_{secure_filename(file.filename)}")
        os.close(fd)
        file.save(path)
        
        current_video_file = {'path': path, 'mimetype': file.mimetype, 'name': file.filename}
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/stream-video')
def stream_video():
    # Streaming con supporto Range (send_file lo gestisce in automatico)
    if not current_video_file['path'] or not os.path.exists(current_video_file['path']):
        abort(404)
    return send_file(current_video_file['path'], mimetype=current_video_file['mimetype'])

# ==============================================================================
# SOCKET IO EVENTS
# ==============================================================================

@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        socketio.emit('initial_state', current_app_state, room=request.sid)

@socketio.on('update_all')
def handle_update(data):
    if current_user.is_authenticated:
        current_app_state.update(data)
        # Broadcast a tutti tranne al mittente (opzionale, qui mandiamo a tutti per sync)
        socketio.emit('state_updated', current_app_state)

@socketio.on('request_initial_state')
def handle_req_init():
    socketio.emit('initial_state', current_app_state, room=request.sid)

# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================

if __name__ == '__main__':
    local_ip = get_local_ip()
    print(f"""
    =======================================================
    HARZAFI TRANSPORT SYSTEM v2.0 - FINAL BUILD
    Design: Apple Style (Panel) + Liquid Glass (Viewer)
    Indirizzo Locale: http://127.0.0.1:5000
    Indirizzo Rete:   http://{local_ip}:5000
    Login:            admin / adminpass
    =======================================================
    """)
    # allow_unsafe_werkzeug serve per l'ambiente di sviluppo se non si usa gunicorn
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    return render_template_string(PANNELLO_CONTROLLO_COMPLETO_HTML)

@app.route('/visualizzatore')
@login_required
def pagina_visualizzatore():
    return render_template_string(VISUALIZZATORE_COMPLETO_HTML)

@app.route('/announcement-audio')
@login_required
def announcement_audio():
    try: return send_file('LINEA 3. CORSA DEVIATA..mp3', mimetype='audio/mpeg')
    except: return Response("Audio mancante", 404)

@app.route('/booked-stop-audio')
@login_required
def booked_stop_audio():
    try: return send_file('bip.mp3', mimetype='audio/mpeg')
    except: return Response("Audio mancante", 404)

@app.route('/upload-video', methods=['POST'])
@login_required
def upload_video():
    global current_video_file
    if 'video' not in request.files: return jsonify({'error': 'No file'}), 400
    file = request.files['video']
    if file.filename == '': return jsonify({'error': 'No filename'}), 400
    
    if current_video_file['path'] and os.path.exists(current_video_file['path']):
        try: os.remove(current_video_file['path'])
        except: pass
        
    try:
        fd, temp_path = tempfile.mkstemp(suffix=f"_{file.filename}")
        os.close(fd)
        file.save(temp_path)
        current_video_file = {'path': temp_path, 'mimetype': file.mimetype, 'name': file.filename}
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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

# --- SOCKET IO ---
@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated: socketio.emit('initial_state', current_app_state, room=request.sid)

@socketio.on('update_all')
def handle_update(data):
    if current_user.is_authenticated:
        current_app_state.update(data)
        socketio.emit('state_updated', current_app_state, skip_sid=request.sid)

@socketio.on('request_initial_state')
def req_init():
    if current_user.is_authenticated: socketio.emit('initial_state', current_app_state, room=request.sid)

if __name__ == '__main__':
    local_ip = get_local_ip()
    print(f"HARZAFI SERVER v20 - PREMIUM GLASS UI | Login: http://{local_ip}:5000/login")
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
