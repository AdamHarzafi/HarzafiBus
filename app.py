import sys
import socket
from functools import wraps
from flask import Flask, Response, request, abort, jsonify, render_template_string, redirect, url_for, flash
from flask_socketio import SocketIO
# AGGIUNTO: Import per il sistema di login sicuro
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# -------------------------------------------------------------------
# NUOVA SEZIONE: CONFIGURAZIONE SICUREZZA E LOGIN
# -------------------------------------------------------------------

# In un'app reale, questa chiave sarebbe in una variabile d'ambiente e molto più complessa
# È FONDAMENTALE per rendere sicure le sessioni di login
SECRET_KEY_FLASK = "questa-chiave-deve-essere-super-segreta-e-difficile-da-indovinare-2025"

# Semplice database utenti in memoria. In un'app più grande, si userebbe un database vero (es. SQLite, PostgreSQL)
# La password è 'hashata'. Quella originale è 'adminpass'
USERS_DB = {
    "admin": {
        "password_hash": generate_password_hash("adminpass"),
        "name": "Amministratore"
    }
}

# Classe Utente richiesta da Flask-Login
class User(UserMixin):
    def __init__(self, id, name):
        self.id = id
        self.name = name

# Funzione per caricare un utente dalla nostra "DB"
def get_user(user_id):
    if user_id in USERS_DB:
        return User(id=user_id, name=USERS_DB[user_id]["name"])
    return None

# -------------------------------------------------------------------
# 1. IMPOSTAZIONI E APPLICAZIONE
# -------------------------------------------------------------------

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY_FLASK  # Configurazione chiave segreta per Flask
socketio = SocketIO(app)

# Configurazione di Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # Dice a Flask-Login qual è la pagina di login
login_manager.login_message = "Per favore, effettua il login per accedere a questa pagina."
login_manager.login_message_category = "error"

@login_manager.user_loader
def load_user(user_id):
    return get_user(user_id)

def get_local_ip():
    # Questa funzione rimane utile per i test locali
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
# 2. STATO GLOBALE DELL'APPLICAZIONE
# -------------------------------------------------------------------
current_app_state = None
current_video_file = {'data': None, 'mimetype': None, 'name': None}

# -------------------------------------------------------------------
# 3. TEMPLATE HTML, CSS e JAVASCRIPT INTEGRATI
# -------------------------------------------------------------------

# AGGIUNTO: Template per la pagina di Login
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

# MODIFICATO: Pannello di controllo con Logout e senza logica 'secret'
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
        input[type="range"] {
            -webkit-appearance: none; appearance: none;
            width: 100%; height: 8px; background: var(--border-color);
            border-radius: 5px; outline: none; padding: 0;
            transition: background 0.3s;
        }
        input[type="range"]:disabled { background: #e9ecef; }
        input[type="range"]::-webkit-slider-thumb {
            -webkit-appearance: none; appearance: none;
            width: 24px; height: 24px;
            background: var(--primary-color);
            cursor: pointer; border-radius: 50%;
            border: 4px solid var(--white);
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
            transition: background 0.3s;
        }
        input[type="range"]:disabled::-webkit-slider-thumb {
            background: #bdc3c7;
            cursor: not-allowed;
        }
        .local-video-controls {
            padding: 20px;
            border: 1px solid var(--border-color);
            border-radius: 16px;
            margin-top: 20px;
        }
        .playback-controls {
            display: flex;
            gap: 15px;
            align-items: center;
        }
        #play-pause-btn {
            flex-shrink: 0;
            width: 60px;
            height: 60px;
            padding: 0;
        }
        #play-pause-btn svg {
            width: 32px;
            height: 32px;
            fill: white;
        }
        .volume-stack {
            flex-grow: 1;
        }
        #video-progress-display {
            text-align: center;
            font-weight: 600;
            color: var(--text-secondary);
            font-size: 14px;
            margin-top: 10px;
            letter-spacing: 1px;
        }
        #current-status-display {
            background-color: var(--background-light);
            border-radius: 16px; padding: 25px; margin-top: 25px;
            text-align: left;
            border: 1px solid var(--border-color);
        }
        .status-grid {
            display: grid;
            grid-template-areas:
                "header header"
                "stop-label stop-name"
                "details-1 details-2";
            grid-template-columns: auto 1fr;
            gap: 15px 20px;
            align-items: center;
        }
        #current-status-display h3 {
            grid-area: header;
            margin: 0; margin-bottom: 10px; font-size: 18px; font-weight: 700;
            border-bottom: 1px solid var(--border-color); padding-bottom: 15px;
        }
        #status-stop-name-container { grid-area: stop-name; }
        #status-stop-name { font-size: 26px; font-weight: 800; color: var(--primary-color); margin: 0; line-height: 1.2; }
        #status-stop-subtitle { font-size: 16px; color: var(--text-secondary); margin: 4px 0 0 0; }
        .status-detail { display: flex; align-items: center; gap: 10px; }
        .status-detail svg { width: 20px; height: 20px; fill: var(--text-secondary); }
        .status-detail-1 { grid-area: details-1; }
        .status-detail-2 { grid-area: details-2; }
        .status-label {
            grid-area: stop-label; font-size: 12px; font-weight: 700; color: var(--text-secondary);
            text-transform: uppercase; letter-spacing: 0.5px;
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            background: var(--white); padding: 15px; border-radius: 12px; border: 1px solid var(--border-color);
        }
        #status-progress { font-size: 18px; font-weight: 700; color: var(--primary-color); display: block; margin-top: 5px; }
        .line-list { list-style: none; padding: 0; }
        .line-item { display: flex; align-items: center; justify-content: space-between; padding: 15px; border: 1px solid var(--border-color); border-radius: 12px; margin-bottom: 10px; gap: 15px; transition: all 0.2s ease-in-out; }
        .line-actions button { width: auto; padding: 8px 15px; font-size: 14px; }
        dialog { width: 90%; max-width: 600px; border-radius: 20px; border: none; box-shadow: 0 15px 50px rgba(0,0,0,0.2); padding: 30px; }
        dialog::backdrop { background-color: rgba(0, 0, 0, 0.5); backdrop-filter: blur(5px); }
        .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        #stops-editor { margin-top: 20px; padding: 20px; background-color: var(--background-light); border-radius: 12px; }
        .stop-item { display: flex; gap: 10px; margin-bottom: 10px; align-items: center; }
        .stop-item input { flex-grow: 1; }
        .modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 25px; }
        .service-status-container {
            display: flex;
            align-items: center;
            justify-content: space-between;
            background-color: var(--background-light);
            padding: 20px;
            border-radius: 16px;
        }
        #service-status-text.status-online { color: var(--success-color); }
        #service-status-text.status-offline { color: var(--danger-color); }
        .toggle-switch { position: relative; display: inline-block; width: 60px; height: 34px; }
        .toggle-switch input { opacity: 0; width: 0; height: 0; }
        .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: var(--danger-color); transition: .4s; border-radius: 34px; }
        .slider:before { position: absolute; content: ""; height: 26px; width: 26px; left: 4px; bottom: 4px; background-color: white; transition: .4s; border-radius: 50%; }
        input:checked + .slider { background-color: var(--success-color); }
        input:checked + .slider:before { transform: translateX(26px); }
        #media-upload-status {
            margin-top: 20px; padding: 15px; border: 1px dashed var(--border-color);
            border-radius: 12px; text-align: center; font-weight: 600; color: var(--text-secondary);
        }
        #media-upload-status span { display: block; margin-bottom: 15px; word-break: break-all; }
        .divider { height: 1px; background-color: var(--border-color); margin: 25px 0; }
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
             <p class="panel-subtitle">Usa questo pannello per controllare la pagina del <a id="viewer-link" href="{{ url_for('pagina_visualizzatore') }}" target="_blank">visualizzatore</a> in tempo reale.</p>
        </div>
        <div class="panel">
            <h2>Stato del Servizio</h2>
            <div class="service-status-container">
                <span id="service-status-text">Caricamento...</span>
                <label class="toggle-switch">
                    <input type="checkbox" id="service-status-toggle">
                    <span class="slider"></span>
                </label>
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
            <div class="local-video-controls">
                <label>Controlli (Solo per file locali)</label>
                <div class="playback-controls">
                    <button id="play-pause-btn" class="btn-primary"></button>
                    <div class="volume-stack">
                        <input type="range" id="volume-slider" min="0" max="1" step="0.05">
                        <div id="video-progress-display">--:-- / --:--</div>
                    </div>
                </div>
                 <button id="toggle-mute-btn" style="width: 100%; padding: 15px; margin-top: 15px;">Caricamento stato audio...</button>
            </div>
            <div id="media-upload-status">
                <span>Nessun media caricato.</span>
                <button id="remove-media-btn" class="btn-danger" style="display: none; width: auto; padding: 8px 15px; margin-top: 20px;">Rimuovi Media</button>
            </div>
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
            <div id="current-status-display">
                <div class="status-grid">
                    <h3>Stato Attuale</h3>
                    <div class="status-label"><span>Fermata</span><span id="status-progress">--/--</span></div>
                    <div id="status-stop-name-container">
                        <div id="status-stop-name">Nessuna fermata</div>
                        <p id="status-stop-subtitle">Selezionare una linea</p>
                    </div>
                    <div class="status-detail status-detail-1">
                         <svg xmlns="http://www.w3.org/2000/svg" height="24px" viewBox="0 0 24 24" width="24px"><path d="M0 0h24v24H0V0z" fill="none"/><path d="M20.5 6c-2.61.7-5.67 1-8.5 1s-5.89-.3-8.5-1L3 8c1.86.5 4.37.83 6.5.98V15H7v2h10v-2h-2.5V8.98c2.13-.15 4.64-.48 6.5-.98l-.5-2zM12 2c-4.42 0-8 3.58-8 8s3.58 8 8 8 8-3.58 8-8-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6s2.69-6 6-6 6 2.69 6 6-2.69-6-6-6z"/></svg>
                        <p><strong>Linea:</strong> <span id="status-line-name">N/D</span></p>
                    </div>
                     <div class="status-detail status-detail-2">
                        <svg xmlns="http://www.w3.org/2000/svg" height="24px" viewBox="0 0 24 24" width="24px"><path d="M0 0h24v24H0V0z" fill="none"/><path d="m12 2-5.5 9h11L12 2zm0 13.5 5.5 9h-11l5.5-9z"/></svg>
                        <p><strong>Destinazione:</strong> <span id="status-line-direction">N/D</span></p>
                    </div>
                </div>
                 <button id="announce-btn" title="Annuncia linea e destinazione" class="btn-primary" style="width:100%; margin-top: 20px; padding: 12px; display: flex; align-items: center; justify-content: center; gap: 10px;">
                    <svg xmlns="http://www.w3.org/2000/svg" height="24" viewBox="0 0 24 24" width="24" fill="white"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"></path></svg>
                    ANNUNCIA
                </button>
            </div>
        </div>
        <div class="panel">
            <h2>Gestione Linee</h2>
            <ul id="line-management-list" class="line-list"></ul>
            <button id="add-new-line-btn" class="btn-success" style="width: 100%; padding: 15px; margin-top: 20px;">+ Aggiungi Nuova Linea</button>
            <button id="reset-data-btn" class="btn-danger" style="width: 100%; padding: 15px; margin-top: 10px;">Reset e Ricarica Dati Predefiniti</button>
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

    <dialog id="line-editor-modal">
        <div class="modal-header">
            <h2 id="modal-title">Editor Linea</h2>
            <button id="close-modal-btn" style="background:none; border:none; font-size: 24px; cursor:pointer;">×</button>
        </div>
        <form id="line-editor-form">
            <input type="hidden" id="edit-line-id">
            <div class="control-group"><label for="line-name">Nome Linea</label><input type="text" id="line-name" required></div>
            <div class="control-group"><label for="line-direction">Destinazione</label><input type="text" id="line-direction" required></div>
            <div id="stops-editor">
                <label>Fermate</label>
                <div id="stops-list"></div>
                <button type="button" id="add-stop-btn" class="btn-secondary" style="margin-top: 10px;">+ Aggiungi Fermata</button>
            </div>
            <div class="modal-actions">
                <button type="button" id="cancel-btn" class="btn-secondary">Annulla</button>
                <button type="submit" class="btn-primary">Salva Modifiche</button>
            </div>
        </form>
    </dialog>

<script>
document.addEventListener('DOMContentLoaded', () => {
    const socket = io();

    // Funzione per gestire l'autenticazione scaduta
    function handleAuthError() {
        alert("Sessione scaduta o non valida. Verrai reindirizzato alla pagina di login.");
        window.location.href = "{{ url_for('login') }}";
    }

    // Wrapper per 'fetch' che controlla automaticamente gli errori di autenticazione
    async function fetchAuthenticated(url, options) {
        try {
            const response = await fetch(url, options);
            if (response.status === 401) { // 401 Unauthorized, tipico di @login_required fallito
                handleAuthError();
                return null;
            }
            if (response.redirected) { // Se il server ci ha reindirizzato (es. al login)
                 window.location.href = response.url;
                 return null;
            }
            return response;
        } catch (error) {
            console.error("Errore di rete:", error);
            alert("Errore di connessione con il server.");
            return null;
        }
    }

    function sendFullStateUpdate() {
        if (!socket.connected) return;
        
        const state = {
            linesData: linesData,
            currentLineKey: currentLineKey,
            currentStopIndex: currentStopIndex,
            mediaSource: localStorage.getItem('busSystem-mediaSource'),
            embedCode: localStorage.getItem('busSystem-embedCode'),
            videoName: localStorage.getItem('busSystem-videoName'),
            mediaLastUpdated: localStorage.getItem('busSystem-mediaLastUpdated'),
            muteState: localStorage.getItem('busSystem-muteState') || 'muted',
            volumeLevel: localStorage.getItem('busSystem-volumeLevel') || '1.0',
            playbackState: localStorage.getItem('busSystem-playbackState') || 'playing',
            videoProgress: JSON.parse(localStorage.getItem('busSystem-videoProgress') || 'null'),
            infoMessages: JSON.parse(localStorage.getItem('busSystem-infoMessages') || '[]'),
            serviceStatus: serviceStatus,
            announcement: JSON.parse(localStorage.getItem('busSystem-playAnnouncement') || 'null')
        };
        
        socket.emit('update_all', state);
        
        if (state.announcement) {
            localStorage.removeItem('busSystem-playAnnouncement');
        }
    }

    const importVideoBtn = document.getElementById('import-video-btn');
    const videoImporter = document.getElementById('video-importer');
    const importEmbedBtn = document.getElementById('import-embed-btn');
    const embedCodeInput = document.getElementById('embed-code-input');
    const removeMediaBtn = document.getElementById('remove-media-btn');
    const mediaUploadStatusText = document.querySelector('#media-upload-status span');
    const toggleMuteBtn = document.getElementById('toggle-mute-btn');
    const volumeSlider = document.getElementById('volume-slider');
    const videoProgressDisplay = document.getElementById('video-progress-display');
    const playPauseBtn = document.getElementById('play-pause-btn');

    const playIcon = `<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"></path></svg>`;
    const pauseIcon = `<svg viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"></path></svg>`;
    
    function updateMediaControlsState() {
        const mediaSource = localStorage.getItem('busSystem-mediaSource');
        const isLocalVideo = (mediaSource === 'server');
        toggleMuteBtn.disabled = !isLocalVideo;
        volumeSlider.disabled = !isLocalVideo;
        playPauseBtn.disabled = !isLocalVideo;
        if (!isLocalVideo) {
             videoProgressDisplay.textContent = '--:-- / --:--';
             localStorage.removeItem('busSystem-videoProgress');
        }
    }

    function loadMediaStatus() {
        const mediaSource = localStorage.getItem('busSystem-mediaSource');
        const videoName = localStorage.getItem('busSystem-videoName');
        
        if (mediaSource === 'embed') {
            mediaUploadStatusText.textContent = `Media da Embed attivo.`;
            removeMediaBtn.style.display = 'inline-block';
        } else if (mediaSource === 'server' && videoName) {
            mediaUploadStatusText.textContent = `Video locale attuale: ${videoName}`;
            removeMediaBtn.style.display = 'inline-block';
        } else {
            mediaUploadStatusText.textContent = 'Nessun media caricato.';
            removeMediaBtn.style.display = 'none';
        }
        updateMediaControlsState();
    }

    function renderMuteButton() {
        const muteState = localStorage.getItem('busSystem-muteState') || 'muted';
        toggleMuteBtn.textContent = (muteState === 'muted') ? 'Disattiva Muto (Audio ON)' : 'Attiva Muto (Audio OFF)';
        toggleMuteBtn.classList.toggle('btn-success', muteState === 'muted');
        toggleMuteBtn.classList.toggle('btn-secondary', muteState !== 'muted');
    }

    function renderPlayPauseButton() {
        playPauseBtn.innerHTML = (localStorage.getItem('busSystem-playbackState') || 'playing') === 'playing' ? pauseIcon : playIcon;
    }

    async function handleLocalVideoUpload(event) {
        const file = event.target.files[0];
        if (!file) return;

        const originalBtnText = importVideoBtn.textContent;
        importVideoBtn.disabled = true;
        importVideoBtn.textContent = 'CARICAMENTO...';

        const formData = new FormData();
        formData.append('video', file);

        const response = await fetchAuthenticated('/upload-video', {
            method: 'POST',
            body: formData
        });

        if (!response) { // Gestione errore auth o rete
             importVideoBtn.disabled = false;
             importVideoBtn.textContent = originalBtnText;
             return;
        }

        if (response.ok) {
            localStorage.setItem('busSystem-mediaSource', 'server');
            localStorage.setItem('busSystem-videoName', file.name);
            localStorage.removeItem('busSystem-embedCode');
            localStorage.removeItem('busSystem-videoProgress'); 
            localStorage.setItem('busSystem-playbackState', 'playing');
            localStorage.setItem('busSystem-mediaLastUpdated', Date.now());
            
            loadMediaStatus();
            updateProgressDisplay();
            renderPlayPauseButton();
            alert('Video locale importato e inviato al server con successo!');
            sendFullStateUpdate();
        } else {
             alert('Errore durante il caricamento del video sul server.');
        }
        
        importVideoBtn.disabled = false;
        importVideoBtn.textContent = originalBtnText;
    }
    
    async function handleEmbedImport() {
        const rawCode = embedCodeInput.value.trim();
        if (!rawCode.includes('<iframe')) {
            alert('Codice non valido. Assicurati di incollare il codice <iframe> completo.');
            return;
        }
        
        await removeMediaFromServer();
        
        localStorage.removeItem('busSystem-videoProgress');
        localStorage.setItem('busSystem-playbackState', 'paused');
        updateProgressDisplay();
        renderPlayPauseButton();

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
        localStorage.removeItem('busSystem-videoName');
        localStorage.setItem('busSystem-mediaLastUpdated', Date.now());
        
        loadMediaStatus();
        embedCodeInput.value = '';
        alert('Media da Embed impostato con successo!');
        sendFullStateUpdate();
    }

    async function removeMedia() {
        if (!confirm('Sei sicuro di voler rimuovere il media attualmente caricato?')) return;
        
        await removeMediaFromServer();
        
        localStorage.removeItem('busSystem-mediaSource');
        localStorage.removeItem('busSystem-videoName');
        localStorage.removeItem('busSystem-embedCode');
        localStorage.removeItem('busSystem-videoProgress');
        localStorage.setItem('busSystem-playbackState', 'paused');
        localStorage.setItem('busSystem-mediaLastUpdated', Date.now());
        
        loadMediaStatus();
        updateProgressDisplay();
        renderPlayPauseButton();
        alert('Media rimosso.');
        sendFullStateUpdate();
    }

    async function removeMediaFromServer() {
        await fetchAuthenticated('/clear-video', { method: 'POST' });
    }

    function formatTime(timeInSeconds) {
        if (isNaN(timeInSeconds) || timeInSeconds < 0) return '--:--';
        const minutes = Math.floor(timeInSeconds / 60);
        const seconds = Math.floor(timeInSeconds % 60);
        return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    }

    function updateProgressDisplay() {
        const progressData = localStorage.getItem('busSystem-videoProgress');
        if (progressData) {
            try {
                const { currentTime, duration } = JSON.parse(progressData);
                videoProgressDisplay.textContent = `${formatTime(currentTime)} / ${formatTime(duration)}`;
            } catch (e) { videoProgressDisplay.textContent = '--:-- / --:--'; }
        } else {
            videoProgressDisplay.textContent = '--:-- / --:--';
        }
    }

    const lineSelector = document.getElementById('line-selector');
    const prevBtn = document.getElementById('prev-btn');
    const nextBtn = document.getElementById('next-btn');
    const announceBtn = document.getElementById('announce-btn');
    const lineManagementList = document.getElementById('line-management-list');
    const addNewLineBtn = document.getElementById('add-new-line-btn');
    const modal = document.getElementById('line-editor-modal');
    const modalTitle = document.getElementById('modal-title');
    const closeModalBtn = document.getElementById('close-modal-btn');
    const cancelBtn = document.getElementById('cancel-btn');
    const lineEditorForm = document.getElementById('line-editor-form');
    const editLineId = document.getElementById('edit-line-id');
    const lineNameInput = document.getElementById('line-name');
    const lineDirectionInput = document.getElementById('line-direction');
    const stopsListContainer = document.getElementById('stops-list');
    const addStopBtn = document.getElementById('add-stop-btn');
    const statusLineName = document.getElementById('status-line-name');
    const statusLineDirection = document.getElementById('status-line-direction');
    const statusStopName = document.getElementById('status-stop-name');
    const statusStopSubtitle = document.getElementById('status-stop-subtitle');
    const statusProgress = document.getElementById('status-progress');
    const infoMessagesInput = document.getElementById('info-messages-input');
    const saveMessagesBtn = document.getElementById('save-messages-btn');
    const serviceStatusToggle = document.getElementById('service-status-toggle');
    const serviceStatusText = document.getElementById('service-status-text');
    const resetDataBtn = document.getElementById('reset-data-btn');

    let linesData = {};
    let currentLineKey = null;
    let currentStopIndex = 0;
    let serviceStatus = 'online';

    function getDefaultData() {
        return {
            "4": { "direction": "STRADA DEL DROSSO", "stops": [{ "name": "FALCHERA CAP.", "subtitle": "" }, { "name": "STAZIONE STURA", "subtitle": "FS" }, { "name": "PIOSSASCO", "subtitle": "" }, { "name": "MASPONS", "subtitle": "" }, { "name": "BERTOLLA", "subtitle": "CIMITERO" }] },
            "29": { "direction": "PIAZZA SOLFERINO", "stops": [{ "name": "VALLETTE CAP.", "subtitle": "" }, { "name": "PRIMO NEBIOLO", "subtitle": "" }, { "name": "MOLVENO", "subtitle": "" }, { "name": "PIANEZZA", "subtitle": "C.SO REGINA MARGHERITA" }, { "name": "TRECATE", "subtitle": "" }] },
            "S8": { "direction": "OSPEDALE SAN GIOVANNI BOSCO", "stops": [{ "name": "STAZIONE LINGOTTO", "subtitle": "FS" }, { "name": "POLITECNICO", "subtitle": "" }, { "name": "STATI UNITI", "subtitle": "" }, { "name": "PORTA SUSA", "subtitle": "STAZIONE FS" }, { "name": "GIULIO CESARE", "subtitle": "MERCATO" }] }
        };
    }
    
    function loadData() { linesData = JSON.parse(localStorage.getItem('busSystem-linesData')) || getDefaultData(); saveData(); }
    function saveData() { localStorage.setItem('busSystem-linesData', JSON.stringify(linesData)); sendFullStateUpdate(); }
    function loadMessages() {
        const messages = localStorage.getItem('busSystem-infoMessages');
        infoMessagesInput.value = messages ? JSON.parse(messages).join('\\n') : ["Benvenuti a bordo del servizio Harzafi.", "Si prega di mantenere il corretto distanziamento."].join('\\n');
        if (!messages) saveMessages(false);
    }

    function saveMessages(showFeedback = true) {
        const messagesArray = infoMessagesInput.value.split('\\n').filter(msg => msg.trim() !== '');
        localStorage.setItem('busSystem-infoMessages', JSON.stringify(messagesArray));
        sendFullStateUpdate();
        if(showFeedback) {
            const originalText = saveMessagesBtn.textContent;
            saveMessagesBtn.textContent = 'Salvato!'; saveMessagesBtn.style.background = 'var(--success-color)';
            setTimeout(() => { saveMessagesBtn.textContent = originalText; saveMessagesBtn.style.background = 'linear-gradient(135deg, var(--secondary-color), var(--primary-color))'; }, 2000);
        }
    }

    function loadServiceStatus() { serviceStatus = localStorage.getItem('busSystem-serviceStatus') || 'online'; renderServiceStatus(); }
    function saveServiceStatus() { localStorage.setItem('busSystem-serviceStatus', serviceStatus); sendFullStateUpdate(); }
    function renderServiceStatus() {
        const isOnline = serviceStatus === 'online';
        serviceStatusText.textContent = isOnline ? 'In Servizio' : 'Fuori Servizio';
        serviceStatusText.className = isOnline ? 'status-online' : 'status-offline';
        serviceStatusToggle.checked = isOnline;
    }

    function renderAll() { renderNavigationPanel(); renderManagementPanel(); renderStatusDisplay(); }
    function renderNavigationPanel() {
        lineSelector.innerHTML = '';
        if (Object.keys(linesData).length > 0) {
            Object.keys(linesData).sort().forEach(key => {
                const option = document.createElement('option');
                option.value = key; option.textContent = `${key} -> ${linesData[key].direction}`;
                lineSelector.appendChild(option);
            });
            if (linesData[currentLineKey]) lineSelector.value = currentLineKey;
        }
    }
    function renderManagementPanel() {
        lineManagementList.innerHTML = '';
        Object.keys(linesData).sort().forEach(key => {
            const item = document.createElement('li');
            item.className = 'line-item';
            item.innerHTML = `<div class="line-info">${key} → ${linesData[key].direction}</div><div class="line-actions"><button class="btn-primary edit-btn" data-id="${key}">Modifica</button><button class="btn-danger delete-btn" data-id="${key}">Elimina</button></div>`;
            lineManagementList.appendChild(item);
        });
    }
    function renderStatusDisplay() {
        const line = linesData[currentLineKey];
        const hasLine = line && line.stops && line.stops.length > 0;
        nextBtn.disabled = !hasLine || currentStopIndex >= line.stops.length - 1;
        prevBtn.disabled = !hasLine || currentStopIndex <= 0;
        announceBtn.disabled = !hasLine;
        if (!hasLine) {
            statusLineName.textContent = 'N/D'; statusLineDirection.textContent = 'N/D';
            statusStopName.textContent = 'Nessuna Fermata'; statusStopSubtitle.textContent = 'Selezionare una linea'; statusProgress.textContent = '--/--';
            return;
        }
        const stop = line.stops[currentStopIndex];
        if (!stop) return;
        statusLineName.textContent = currentLineKey; statusLineDirection.textContent = line.direction;
        statusStopName.textContent = stop.name; statusStopSubtitle.textContent = stop.subtitle || ' ';
        statusProgress.textContent = `${currentStopIndex + 1}/${line.stops.length}`;
    }
    function renderStopsInModal(stops = []) {
        stopsListContainer.innerHTML = '';
        (stops.length > 0 ? stops : [{ name: '', subtitle: '' }]).forEach(stop => addStopToModal(stop));
    }
    function addStopToModal(stop = { name: '', subtitle: '' }) {
        const stopItem = document.createElement('div');
        stopItem.className = 'stop-item';
        stopItem.innerHTML = `<input type="text" placeholder="Nome fermata" class="stop-name-input" value="${stop.name || ''}" required><input type="text" placeholder="Sottotitolo (opzionale)" class="stop-subtitle-input" value="${stop.subtitle || ''}"><button type="button" class="btn-danger remove-stop-btn" style="width:auto; padding: 10px 12px;">-</button>`;
        stopsListContainer.appendChild(stopItem);
    }
    function updateAndRenderStatus() {
        if (!linesData[currentLineKey] || Object.keys(linesData).length === 0) {
            currentLineKey = Object.keys(linesData).sort()[0] || null;
            currentStopIndex = 0;
        } else {
            const stopsCount = linesData[currentLineKey].stops.length;
            if (currentStopIndex >= stopsCount) currentStopIndex = Math.max(0, stopsCount - 1);
        }
        localStorage.setItem('busSystem-currentLine', currentLineKey);
        localStorage.setItem('busSystem-currentStopIndex', currentStopIndex);
        if (linesData[currentLineKey]) lineSelector.value = currentLineKey;
        renderStatusDisplay();
        sendFullStateUpdate();
    }

    function initialize() {
        loadMediaStatus();
        renderMuteButton();
        renderPlayPauseButton();
        volumeSlider.value = localStorage.getItem('busSystem-volumeLevel') || '1.0';
        updateProgressDisplay();
        
        loadData();
        loadMessages();
        loadServiceStatus();
        currentLineKey = localStorage.getItem('busSystem-currentLine');
        currentStopIndex = parseInt(localStorage.getItem('busSystem-currentStopIndex'), 10) || 0;
        renderAll();
        updateAndRenderStatus();
    }
    
    socket.on('state_updated', (state) => {
        if(state.videoProgress) {
            localStorage.setItem('busSystem-videoProgress', JSON.stringify(state.videoProgress));
            updateProgressDisplay();
        }
    });
    socket.on('connect_error', (err) => {
        if (err.message) {
             alert("Errore di connessione WebSocket: " + err.message + ". Verrai reindirizzato al login.");
             window.location.href = "{{ url_for('login') }}";
        }
    });

    lineSelector.addEventListener('change', (e) => { currentLineKey = e.target.value; currentStopIndex = 0; updateAndRenderStatus(); });
    resetDataBtn.addEventListener('click', () => { if (confirm('Sei sicuro? Questa azione cancellerà tutti i dati e richiederà un nuovo login.')) { localStorage.clear(); window.location.href="{{ url_for('logout') }}"; } });
    nextBtn.addEventListener('click', () => { const currentLine = linesData[currentLineKey]; if (currentLine && currentStopIndex < currentLine.stops.length - 1) { currentStopIndex++; updateAndRenderStatus(); } });
    prevBtn.addEventListener('click', () => { if (currentStopIndex > 0) { currentStopIndex--; updateAndRenderStatus(); } });
    announceBtn.addEventListener('click', () => { 
        if (currentLineKey && linesData[currentLineKey]) {
            const announcementData = { line: currentLineKey, direction: linesData[currentLineKey].direction, timestamp: Date.now() }; 
            localStorage.setItem('busSystem-playAnnouncement', JSON.stringify(announcementData)); 
            sendFullStateUpdate();
        } else { alert('Nessuna linea attiva selezionata.'); } 
    });
    serviceStatusToggle.addEventListener('change', () => { serviceStatus = serviceStatusToggle.checked ? 'online' : 'offline'; saveServiceStatus(); renderServiceStatus(); });
    
    importVideoBtn.addEventListener('click', () => videoImporter.click());
    videoImporter.addEventListener('change', handleLocalVideoUpload);
    importEmbedBtn.addEventListener('click', handleEmbedImport);
    removeMediaBtn.addEventListener('click', removeMedia);
    
    toggleMuteBtn.addEventListener('click', () => {
        const newState = (localStorage.getItem('busSystem-muteState') || 'muted') === 'muted' ? 'unmuted' : 'muted';
        localStorage.setItem('busSystem-muteState', newState);
        renderMuteButton(); sendFullStateUpdate();
    });
    volumeSlider.addEventListener('input', (e) => { localStorage.setItem('busSystem-volumeLevel', e.target.value); sendFullStateUpdate(); });
    playPauseBtn.addEventListener('click', () => {
        const newState = (localStorage.getItem('busSystem-playbackState') || 'playing') === 'playing' ? 'paused' : 'playing';
        localStorage.setItem('busSystem-playbackState', newState);
        renderPlayPauseButton(); sendFullStateUpdate();
    });

    addNewLineBtn.addEventListener('click', () => { editLineId.value = ''; modalTitle.textContent = 'Aggiungi Nuova Linea'; lineEditorForm.reset(); renderStopsInModal(); modal.showModal(); });
    lineManagementList.addEventListener('click', (e) => { const target = e.target.closest('button'); if (!target) return; const lineId = target.dataset.id; if (target.classList.contains('edit-btn')) { editLineId.value = lineId; modalTitle.textContent = `Modifica Linea: ${lineId}`; const line = linesData[lineId]; lineNameInput.value = lineId; lineDirectionInput.value = line.direction; renderStopsInModal(line.stops); modal.showModal(); } if (target.classList.contains('delete-btn')) { if (confirm(`Sei sicuro di voler eliminare la linea "${lineId}"?`)) { delete linesData[lineId]; saveData(); renderAll(); } } });
    addStopBtn.addEventListener('click', () => addStopToModal());
    stopsListContainer.addEventListener('click', (e) => { if (e.target.classList.contains('remove-stop-btn')) { if (stopsListContainer.children.length > 1) e.target.parentElement.remove(); else alert('Ogni linea deve avere almeno una fermata.'); } });
    lineEditorForm.addEventListener('submit', (e) => { e.preventDefault(); const originalId = editLineId.value; const newId = lineNameInput.value.trim().toUpperCase(); const direction = lineDirectionInput.value.trim(); if (!newId || !direction) { alert('Il nome della linea e la destinazione sono obbligatori.'); return; } const stops = []; const stopItems = stopsListContainer.querySelectorAll('.stop-item'); for (const item of stopItems) { const name = item.querySelector('.stop-name-input').value.trim().toUpperCase(); if (!name) { alert('Tutte le fermate devono avere un nome.'); return; } const subtitle = item.querySelector('.stop-subtitle-input').value.trim().toUpperCase(); stops.push({ name, subtitle }); } if (originalId && originalId !== newId) delete linesData[originalId]; linesData[newId] = { direction, stops }; saveData(); if (currentLineKey === originalId) { currentLineKey = newId; localStorage.setItem('busSystem-currentLine', newId); } renderAll(); updateAndRenderStatus(); modal.close(); });
    
    saveMessagesBtn.addEventListener('click', () => saveMessages(true));
    closeModalBtn.addEventListener('click', () => modal.close());
    cancelBtn.addEventListener('click', () => modal.close());

    initialize();
});
</script>
</body>
</html>
"""

# MODIFICATO: Visualizzatore protetto da login
VISUALIZZATORE_COMPLETO_HTML = """
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Visualizzazione Fermata Harzafi</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;700;900&display=swap" rel="stylesheet">
    <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
    <style>
        :root {
            --main-text-color: #ffffff;
            --gradient-start: #D544A7;
            --gradient-end: #4343A2;
            --line-color: #8A2387;
        }
        body {
            margin: 0;
            font-family: 'Montserrat', sans-serif;
            background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
            color: var(--main-text-color);
            height: 100vh;
            display: flex;
            overflow: hidden;
            font-size: 1.2em;
        }
        #loader {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
            z-index: 999; transition: opacity 0.8s ease;
        }
        #loader img { width: 250px; max-width: 70%; animation: pulse-logo 2s infinite ease-in-out; }
        #loader p { margin-top: 25px; font-size: 1.2em; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; opacity: 0.9; }
        @keyframes pulse-logo {
            0% { transform: scale(1); opacity: 0.8; }
            50% { transform: scale(1.05); opacity: 1; }
            100% { transform: scale(1); opacity: 0.8; }
        }
        #loader.hidden { opacity: 0; pointer-events: none; }
        
        .main-content-wrapper { flex: 3; display: flex; align-items: center; justify-content: center; height: 100%; padding: 0 40px; }
        .video-wrapper { flex: 2; height: 100%; display: flex; align-items: center; justify-content: center; padding: 40px; box-sizing: border-box; }
        .container { display: flex; align-items: center; width: 100%; max-width: 1400px; opacity: 0; transition: opacity 0.8s ease; }
        .container.visible { opacity: 1; }
        .line-graphic {
            flex-shrink: 0; width: 120px; height: 500px; display: flex;
            flex-direction: column; align-items: center; position: relative;
            justify-content: center; padding-bottom: 80px;
        }
        .line-graphic::before {
            content: ''; position: absolute; top: 22%; left: 50%; transform: translateX(-50%);
            width: 12px; height: 78%; background-color: rgba(255, 255, 255, 0.3);
            border-radius: 6px; z-index: 1;
        }
        .line-id-container {
            width: 100px; height: 100px; background-color: var(--main-text-color);
            border-radius: 50%; display: flex; align-items: center; justify-content: center;
            z-index: 2; box-shadow: 0 5px 25px rgba(0,0,0,0.2);
            border: 4px solid var(--gradient-end); position: absolute;
            top: 15%; left: 50%; transform: translateX(-50%);
        }
        #line-id { font-size: 48px; font-weight: 900; color: var(--line-color); }
        .current-stop-indicator {
            width: 60px; height: 60px; background-color: var(--main-text-color);
            border-radius: 12px; z-index: 2; position: absolute; bottom: 27%;
            left: 50%; transform: translateX(-50%); opacity: 1;
            box-shadow: 0 0 20px rgba(255,255,255,0.7);
        }
        .current-stop-indicator.exit { opacity: 0; transform: translateX(-50%) translateY(50px) scale(0.5); transition: opacity 0.4s cubic-bezier(0.68, -0.55, 0.27, 1.55), transform 0.4s cubic-bezier(0.68, -0.55, 0.27, 1.55); }
        .current-stop-indicator.enter { animation: slideInFromTopFadeIn 0.5s cubic-bezier(0.18, 0.89, 0.32, 1.28) forwards; }
        .current-stop-indicator.enter-reverse { animation: slideInFromBottomFadeIn 0.5s cubic-bezier(0.18, 0.89, 0.32, 1.28) forwards; }
        
        .text-content { padding-left: 70px; width: 100%; overflow: hidden; }
        .direction-header { font-size: 30px; font-weight: 700; opacity: 0.8; margin: 0; text-transform: uppercase; }
        #direction-name { font-size: 70px; font-weight: 900; margin: 5px 0 60px 0; text-transform: uppercase; }
        .next-stop-header { font-size: 28px; font-weight: 700; opacity: 0.8; margin: 0; text-transform: uppercase; }
        #stop-name { font-size: 140px; font-weight: 900; margin: 0; line-height: 1.1; text-transform: uppercase; white-space: normal; opacity: 1; transform: translateY(0); transition: opacity 0.3s ease-out, transform 0.3s ease-out; }
        #stop-name.exit { opacity: 0; transform: translateY(-30px); transition: opacity 0.3s ease-in, transform 0.3s ease-in; }
        #stop-name.enter { animation: slideInFadeIn 0.5s ease-out forwards; }
        #stop-subtitle { font-size: 42px; font-weight: 400; margin: 10px 0 0 0; text-transform: uppercase; opacity: 0.9; }
        
        .logo {
            position: absolute; bottom: 40px; right: 50px; width: 220px; opacity: 0;
            filter: brightness(1.2) contrast(1.1); transition: opacity 0.8s ease;
        }
        .logo.visible { opacity: 0.9; }

        @keyframes slideInFadeIn { from { opacity: 0; transform: translateY(40px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes slideInFromTopFadeIn { from { opacity: 0; transform: translateX(-50%) translateY(-100px); } to { opacity: 1; transform: translateX(-50%) translateY(0); } }
        @keyframes slideInFromBottomFadeIn { from { opacity: 0; transform: translateX(-50%) translateY(100px); } to { opacity: 1; transform: translateX(-50%) translateY(0); } }
        #service-offline-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: 1000; display: flex; align-items: center; justify-content: center; text-align: center; color: white; background-color: rgba(15, 23, 42, 0.6); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); opacity: 0; pointer-events: none; }
        #service-offline-overlay.visible { pointer-events: auto; animation: fadeInBlur 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards; }
        #service-offline-overlay.hiding { animation: fadeOutBlur 0.6s ease-out forwards; }
        #service-offline-overlay h2 { font-size: 5vw; font-weight: 900; margin: 0; text-shadow: 0 4px 20px rgba(0,0,0,0.4); }
        #service-offline-overlay p { font-size: 2vw; font-weight: 600; opacity: 0.9; margin-top: 15px; text-shadow: 0 2px 10px rgba(0,0,0,0.3); }
        @keyframes fadeInBlur { from { opacity: 0; } to { opacity: 1; } }
        @keyframes fadeOutBlur { from { opacity: 1; } to { opacity: 0; } }
        #video-player-container {
            width: 100%; max-width: 100%; background-color: rgba(0, 0, 0, 0.2);
            border-radius: 25px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); opacity: 0;
            overflow: hidden; display: flex; align-items: center; justify-content: center;
            transition: all 0.5s cubic-bezier(0.16, 1, 0.3, 1);
            position: relative;
        }
        #ad-video {
            width: 100%; height: 100%; object-fit: cover; border-radius: 25px; display: block;
            position: absolute; top: 0; left: 0;
            transition: volume 0.4s ease-in-out;
        }
        
        #video-player-container iframe {
            border-radius: 25px;
        }
        .aspect-ratio-16-9 { position: relative; width: 100%; height: 0; padding-top: 56.25%; }
        .placeholder-content {
            position: absolute;
            top: 0; left: 0; width: 100%; height: 100%;
            display: flex; flex-direction: column; align-items: center;
            justify-content: center; text-align: center; padding: 20px; box-sizing: border-box;
        }
        .placeholder-content h2 { font-size: 2vw; font-weight: 900; margin: 0 0 15px 0; text-transform: uppercase; }
        .placeholder-content p { font-size: 1.2vw; opacity: 0.8; margin: 0; }
        
        .box-enter-animation { animation: box-enter 0.8s cubic-bezier(0.16, 1, 0.3, 1) forwards; }
        .box-exit-animation { animation: box-exit 0.6s ease-out forwards; }
        @keyframes box-enter { from { opacity: 0; transform: translateX(50px) scale(0.98); } to { opacity: 1; transform: translateX(0) scale(1); } }
        @keyframes box-exit { from { opacity: 1; transform: translateX(0) scale(1); } to { opacity: 0; transform: translateX(50px) scale(0.98); } }
    </style>
</head>
<body>
    <div id="loader">
        <img src="https://i.ibb.co/8gSLmLCD/LOGO-HARZAFI.png" alt="Logo Harzafi in caricamento">
        <p>CONNESSIONE AL SERVER...</p>
    </div>
    <div class="main-content-wrapper">
        <div class="container">
            <div class="line-graphic">
                <div class="line-id-container"><span id="line-id">--</span></div>
                <div id="stop-indicator" class="current-stop-indicator"></div>
            </div>
            <div class="text-content">
                <p class="direction-header">DESTINAZIONE - DESTINATION</p>
                <h1 id="direction-name"></h1>
                <p class="next-stop-header">PROSSIMA FERMATA - NEXT STOP</p>
                <h2 id="stop-name"></h2>
                <p id="stop-subtitle"></p>
            </div>
        </div>
    </div>
    <div class="video-wrapper">
        <div id="video-player-container" class="aspect-ratio-16-9"></div>
    </div>
    
    <img src="https://i.ibb.co/8gSLmLCD/LOGO-HARZAFI.png" alt="Logo Harzafi" class="logo">
    <div id="service-offline-overlay">
        <div class="overlay-content">
            <h2>NESSUN SERVIZIO</h2>
            <p>AL MOMENTO, IL SISTEMA NON È DISPONIBILE.</p>
        </div>
    </div>

<script>
document.addEventListener('DOMContentLoaded', () => {
    const socket = io();
    
    const videoPlayerContainer = document.getElementById('video-player-container');
    let originalVideoVolume = 1.0;
    let speechCheckInterval = null;
    let lastProgressUpdate = 0;
    let lastKnownState = {};

    function applyAudioSettings(state) {
        const videoEl = document.getElementById('ad-video');
        if (videoEl) {
            videoEl.muted = (state.muteState === 'muted');
            videoEl.volume = parseFloat(state.volumeLevel);
        }
    }
    
    function applyPlaybackState(state) {
        const videoEl = document.getElementById('ad-video');
        if (videoEl) {
            if (state.playbackState === 'playing') {
                videoEl.play().catch(e => {});
            } else {
                videoEl.pause();
            }
        }
    }

    function animateAndChangeContent(changeFunction) {
        videoPlayerContainer.classList.remove('box-enter-animation');
        videoPlayerContainer.classList.add('box-exit-animation');
        setTimeout(() => {
            changeFunction();
            videoPlayerContainer.classList.remove('box-exit-animation');
            videoPlayerContainer.classList.add('box-enter-animation');
        }, 500);
    }
    
    function showPlaceholder() {
        animateAndChangeContent(() => {
            videoPlayerContainer.innerHTML = `<div class="placeholder-content"><h2>NESSUN MEDIA DISPONIBILE</h2></div>`;
        });
    }

    function showServerVideo(state) {
        animateAndChangeContent(() => {
            const videoUrl = `/stream-video?t=${state.mediaLastUpdated}`;
            videoPlayerContainer.innerHTML = `<video id="ad-video" loop playsinline autoplay></video>`;
            const videoEl = document.getElementById('ad-video');
            videoEl.src = videoUrl;
            
            applyAudioSettings(state);
            applyPlaybackState(state);

            videoEl.addEventListener('timeupdate', () => {
                const now = Date.now();
                if (now - lastProgressUpdate > 1000) {
                    const progress = { currentTime: videoEl.currentTime, duration: videoEl.duration };
                    socket.emit('update_all', { videoProgress: progress });
                    lastProgressUpdate = now;
                }
            });
        });
    }

    function showEmbed(embedCode) {
        animateAndChangeContent(() => {
            videoPlayerContainer.innerHTML = embedCode;
        });
    }

    function loadMediaOrPlaceholder(state) {
        if (state.mediaSource === 'embed' && state.embedCode) {
            showEmbed(state.embedCode);
        } else if (state.mediaSource === 'server') {
            showServerVideo(state);
        } else {
            showPlaceholder();
        }
    }

    const loaderEl = document.getElementById('loader');
    const containerEl = document.querySelector('.container');
    const logoEl = document.querySelector('.logo');
    const lineIdEl = document.getElementById('line-id');
    const directionNameEl = document.getElementById('direction-name');
    const stopNameEl = document.getElementById('stop-name');
    const stopSubtitleEl = document.getElementById('stop-subtitle');
    const stopIndicatorEl = document.getElementById('stop-indicator');
    const serviceOfflineOverlay = document.getElementById('service-offline-overlay');

    const synth = window.speechSynthesis;
    let vociDisponibili = [];

    function duckVideoVolume() {
        const videoEl = document.getElementById('ad-video');
        if (videoEl && !videoEl.muted) {
            originalVideoVolume = videoEl.volume;
            videoEl.volume = 0.2;
        }
    }

    function restoreVideoVolume() {
        const videoEl = document.getElementById('ad-video');
        if (videoEl) {
            videoEl.volume = originalVideoVolume;
        }
    }

    function manageAnnouncement(utterance) {
        if (synth.speaking) synth.cancel();
        if (speechCheckInterval) {
            clearInterval(speechCheckInterval);
            restoreVideoVolume();
        }
        duckVideoVolume();
        synth.speak(utterance);
        speechCheckInterval = setInterval(() => {
            if (!synth.speaking) {
                restoreVideoVolume();
                clearInterval(speechCheckInterval);
                speechCheckInterval = null;
            }
        }, 100);
    }

    function inizializzaSintesiVocale() {
        const carica = () => { vociDisponibili = synth.getVoices(); };
        if (synth.getVoices().length > 0) carica();
        else synth.onvoiceschanged = carica;
    }

    function trovaVoceMigliore(lang) {
        if (vociDisponibili.length === 0) return null;
        let criteri = [ v => v.lang === lang && v.name.toLowerCase().includes('google'), v => v.lang === lang && !v.localService, v => v.lang === lang ];
        for (const criterio of criteri) { const voce = vociDisponibili.find(criterio); if (voce) return voce; }
        return vociDisponibili.find(v => v.lang.startsWith(lang.split('-')[0])) || null;
    }

    function annunciaFermata(stop) {
        if (!stop || !stop.name) return;
        const nomeCompletoFermata = `${stop.name}${stop.subtitle ? ', ' + stop.subtitle : ''}`;
        const annuncio = new SpeechSynthesisUtterance(`Prossima fermata: ${nomeCompletoFermata}`);
        annuncio.voice = trovaVoceMigliore('it-IT');
        annuncio.lang = 'it-IT';
        manageAnnouncement(annuncio);
    }

    function annunciaLineaDirezione(lineInfo) {
        if (!lineInfo || !lineInfo.line || !lineInfo.direction) return;
        const textToSpeak = `Linea ${lineInfo.line}, destinazione ${lineInfo.direction}`;
        const annuncio = new SpeechSynthesisUtterance(textToSpeak);
        annuncio.voice = trovaVoceMigliore('it-IT');
        annuncio.lang = 'it-IT';
        manageAnnouncement(annuncio);
    }
    
    function adjustFontSize(element) {
        const maxFontSize = 140; const minFontSize = 40;
        element.style.fontSize = maxFontSize + 'px'; let currentFontSize = maxFontSize;
        while ((element.scrollWidth > element.parentElement.clientWidth || element.scrollHeight > element.parentElement.clientHeight) && currentFontSize > minFontSize) {
            currentFontSize -= 2; element.style.fontSize = currentFontSize + 'px';
        }
    }

    function checkServiceStatus(state) {
        if (state.serviceStatus === 'offline') {
            serviceOfflineOverlay.classList.remove('hiding');
            serviceOfflineOverlay.classList.add('visible');
            return false;
        } else if (serviceOfflineOverlay.classList.contains('visible')) {
            serviceOfflineOverlay.classList.add('hiding');
            setTimeout(() => serviceOfflineOverlay.classList.remove('visible', 'hiding'), 600);
        }
        return true;
    }
    
    function updateDisplay(state) {
        const isServiceOnline = checkServiceStatus(state);
        if (!isServiceOnline) {
            loaderEl.classList.add('hidden');
            containerEl.classList.remove('visible');
            logoEl.classList.remove('visible');
            return;
        }

        const { linesData, currentLineKey, currentStopIndex } = state;

        if (!linesData || !currentLineKey || currentStopIndex === null) {
            loaderEl.classList.remove('hidden');
            containerEl.classList.remove('visible');
            logoEl.classList.remove('visible');
            return;
        }
        
        const isInitialLoad = !lastKnownState.currentLineKey;
        const lineChanged = lastKnownState.currentLineKey !== currentLineKey;
        const stopIndexChanged = lastKnownState.currentStopIndex !== currentStopIndex;
        const playAnimation = !isInitialLoad && (lineChanged || stopIndexChanged);
        const direction = (!isInitialLoad && stopIndexChanged && currentStopIndex < lastKnownState.currentStopIndex) ? 'prev' : 'next';

        loaderEl.classList.add('hidden');
        containerEl.classList.add('visible');
        logoEl.classList.add('visible');

        const line = linesData[currentLineKey];
        if (!line) return;
        const stop = line.stops[currentStopIndex];
        
        const updateContent = () => {
            lineIdEl.textContent = currentLineKey;
            directionNameEl.textContent = line.direction;
            stopNameEl.textContent = stop ? stop.name : 'CAPOLINEA';
            stopSubtitleEl.textContent = stop ? (stop.subtitle || '') : '';
            adjustFontSize(stopNameEl);
        };

        if (playAnimation) {
            stopIndicatorEl.classList.add('exit');
            stopNameEl.classList.add('exit');
            setTimeout(() => {
                updateContent();
                stopIndicatorEl.classList.remove('exit');
                stopNameEl.classList.remove('exit');
                const enterClass = (direction === 'prev') ? 'enter-reverse' : 'enter';
                stopIndicatorEl.classList.add(enterClass);
                stopNameEl.classList.add('enter');
                setTimeout(() => {
                    stopIndicatorEl.classList.remove('enter', 'enter-reverse');
                    stopNameEl.classList.remove('enter');
                }, 500);
                if(stop) annunciaFermata(stop);
            }, 400);
        } else {
            updateContent();
        }

        if (state.announcement && state.announcement.timestamp > (lastKnownState.announcement?.timestamp || 0)) {
            annunciaLineaDirezione(state.announcement);
        }

        if (isInitialLoad || state.mediaLastUpdated > (lastKnownState.mediaLastUpdated || 0)) {
            loadMediaOrPlaceholder(state);
        } else {
            applyAudioSettings(state);
            applyPlaybackState(state);
        }
        
        lastKnownState = state;
    }
    
    socket.on('connect', () => {
        console.log('Connesso al server!');
        loaderEl.querySelector('p').textContent = "CONNESSO. IN ATTESA DI DATI...";
        socket.emit('request_initial_state');
    });

    socket.on('disconnect', () => {
        loaderEl.classList.remove('hidden');
        loaderEl.querySelector('p').textContent = "CONNESSIONE PERSA...";
        containerEl.classList.remove('visible');
        logoEl.classList.remove('visible');
    });

    socket.on('connect_error', (err) => {
        if (err.message) {
            loaderEl.querySelector('p').textContent = "ERRORE AUTENTICAZIONE. ACCESSO NEGATO.";
        }
    });

    socket.on('initial_state', (state) => {
        console.log('Stato iniziale ricevuto:', state);
        if (state) updateDisplay(state);
    });

    socket.on('state_updated', (state) => {
        console.log('Stato aggiornato ricevuto:', state);
        if (state) updateDisplay(state);
    });
    
    inizializzaSintesiVocale();
});
</script>
</body>
</html>
"""

# -------------------------------------------------------------------
# 4. ROUTE E API WEBSOCKET (CON SICUREZZA POTENZIATA)
# -------------------------------------------------------------------

# NUOVA ROUTE: Pagina di Login
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
            # 'next' viene usato da Flask-Login per reindirizzare alla pagina richiesta prima del login
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash("Credenziali non valide. Riprova.", "error")
            return redirect(url_for('login'))
            
    return render_template_string(LOGIN_PAGE_HTML)

# NUOVA ROUTE: Logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# MODIFICATO: Route protette da @login_required
@app.route('/')
@login_required
def dashboard():
    return render_template_string(PANNELLO_CONTROLLO_COMPLETO_HTML)

@app.route('/visualizzatore')
@login_required
def pagina_visualizzatore():
    return render_template_string(VISUALIZZATORE_COMPLETO_HTML)

# MODIFICATO: API protette da @login_required
@app.route('/upload-video', methods=['POST'])
@login_required
def upload_video():
    global current_video_file
    if 'video' not in request.files: return jsonify({'error': 'Nessun file inviato'}), 400
    file = request.files['video']
    if file.filename == '': return jsonify({'error': 'Nessun file selezionato'}), 400
    video_data = file.read()
    current_video_file = {'data': video_data, 'mimetype': file.mimetype, 'name': file.filename}
    print(f"Video '{file.filename}' caricato da {current_user.name}.")
    return jsonify({'success': True, 'filename': file.filename})

@app.route('/stream-video')
@login_required
def stream_video():
    if current_video_file and current_video_file['data']:
        return Response(current_video_file['data'], mimetype=current_video_file['mimetype'])
    abort(404)

@app.route('/clear-video', methods=['POST'])
@login_required
def clear_video():
    global current_video_file
    if current_video_file['data']:
        print(f"Video rimosso da {current_user.name}.")
        current_video_file = {'data': None, 'mimetype': None, 'name': None}
    return jsonify({'success': True})

# --- GESTIONE WEBSOCKET CON SICUREZZA ---

@socketio.on('connect')
def handle_connect():
    # MODIFICATO: Controllo di sicurezza all'atto della connessione WebSocket
    if not current_user.is_authenticated:
        print(f"Tentativo di connessione WebSocket non autorizzato.")
        return False # Rifiuta la connessione
        
    print(f"Client autorizzato connesso: {current_user.name} ({request.sid})")
    if current_app_state:
        socketio.emit('initial_state', current_app_state, room=request.sid)

@socketio.on('disconnect')
def handle_disconnect():
    if hasattr(current_user, 'name'):
        print(f"Client {current_user.name} disconnesso.")
    else:
        print("Client non autenticato disconnesso.")

# MODIFICATO: Anche gli eventi sono implicitamente protetti perché la connessione lo è
@socketio.on('update_all')
def handle_update_all(data):
    if not current_user.is_authenticated: return
    global current_app_state
    if current_app_state is None: current_app_state = {}
    current_app_state.update(data)
    socketio.emit('state_updated', current_app_state, skip_sid=request.sid)

@socketio.on('request_initial_state')
def handle_request_initial_state():
    if not current_user.is_authenticated: return
    if current_app_state:
        socketio.emit('initial_state', current_app_state, room=request.sid)

# -------------------------------------------------------------------
# 5. BLOCCO DI ESECUZIONE
# -------------------------------------------------------------------

if __name__ == '__main__':
    # RIMOSSO: Tutta la logica di ngrok è stata eliminata.
    
    local_ip = get_local_ip()
    print("================================================================")
    print("      SERVER HARZAFI POTENZIATO (v.Sicurezza) AVVIATO")
    print("================================================================")
    print("MODALITA' DI ESECUZIONE: Locale (per test)")
    print("Per l'accesso online, segui la guida per il deploy su Render.")
    print("\n--- ACCESSO LOCALE (dalla stessa macchina) ---")
    print(f"Login:          http://127.0.0.1:5000/login")
    print("\n--- ACCESSO DALLA RETE LOCALE (STESSA RETE WIFI) ---")
    print(f"Login:          http://{local_ip}:5000/login")
    print("================================================================")
    print("Credenziali di default: admin / adminpass")
    
    # Per il deploy su Render, gunicorn sarà il web server.
    # Per i test locali, usiamo il server di sviluppo di Flask/SocketIO.
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)