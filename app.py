import sys
import socket
from functools import wraps
from datetime import datetime, timedelta
from flask import Flask, Response, request, abort, jsonify, render_template_string, redirect, url_for, flash, send_file
from flask_socketio import SocketIO
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField
from wtforms.validators import DataRequired

# -------------------------------------------------------------------
# SEZIONE CONFIGURAZIONE SICUREZZA POTENZIATA E LOGIN
# -------------------------------------------------------------------

SECRET_KEY_FLASK = "questa-chiave-e-stata-cambiata-ed-e-molto-piu-sicura-del-2025"

# Dizionario in-memory per tracciare i tentativi di login falliti (protezione da brute-force)
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
# 1. IMPOSTAZIONI E APPLICAZIONE
# -------------------------------------------------------------------

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY_FLASK
app.config['WTF_CSRF_SECRET_KEY'] = SECRET_KEY_FLASK
socketio = SocketIO(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Per favore, effettua il login per accedere a questa pagina."
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
# 2. STATO GLOBALE DELL'APPLICAZIONE
# -------------------------------------------------------------------
current_app_state = None
current_video_file = {'data': None, 'mimetype': None, 'name': None}

# -------------------------------------------------------------------
# 3. TEMPLATE HTML, CSS e JAVASCRIPT INTEGRATI
# -------------------------------------------------------------------

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
        :root {
            --background-start: #111827;
            --background-end: #1F2937;
            --card-background: rgba(31, 41, 55, 0.8);
            --border-color: rgba(107, 114, 128, 0.2);
            --accent-color-start: #8A2387;
            --accent-color-end: #A244A7;
            --text-primary: #F9FAFB;
            --text-secondary: #9CA3AF;
            --danger-color: #EF4444;
        }
        * { box-sizing: border-box; }
        body {
            font-family: 'Inter', sans-serif;
            background: linear-gradient(135deg, var(--background-start), var(--background-end));
            color: var(--text-primary);
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
            padding: 20px;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
        }
        .login-container {
            width: 100%;
            max-width: 420px;
            background: var(--card-background);
            border: 1px solid var(--border-color);
            padding: 40px;
            border-radius: 24px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.4);
            backdrop-filter: blur(10px);
            text-align: center;
            animation: fadeIn 0.5s ease-out;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .logo {
            max-width: 150px;
            margin-bottom: 24px;
            filter: drop-shadow(0 0 15px rgba(255, 255, 255, 0.1));
        }
        h2 {
            color: var(--text-primary);
            font-weight: 700;
            font-size: 24px;
            margin: 0 0 32px 0;
        }
        .flash-message {
            padding: 12px 15px;
            border-radius: 12px;
            margin-bottom: 20px;
            border: 1px solid;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 10px;
            animation: slideIn .3s ease-out;
        }
        @keyframes slideIn {
            from { opacity: 0; transform: translateY(-10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .flash-message.error {
            background-color: rgba(239, 68, 68, 0.1);
            color: var(--danger-color);
            border-color: rgba(239, 68, 68, 0.3);
        }
        .form-group {
            margin-bottom: 20px;
            text-align: left;
            position: relative;
        }
        label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: var(--text-secondary);
            font-size: 14px;
        }
        input {
            width: 100%;
            padding: 14px 16px;
            border-radius: 12px;
            border: 1px solid var(--border-color);
            background-color: #111827;
            color: var(--text-primary);
            font-size: 16px;
            font-family: 'Inter', sans-serif;
            transition: border-color 0.2s, box-shadow 0.2s;
        }
        input:focus {
            outline: none;
            border-color: var(--accent-color-end);
            box-shadow: 0 0 0 4px rgba(162, 68, 167, 0.2);
        }
        input:-webkit-autofill {
             -webkit-box-shadow: 0 0 0 30px #111827 inset !important;
             -webkit-text-fill-color: var(--text-primary) !important;
        }
        .password-wrapper {
            position: relative;
        }
        #password-toggle {
            position: absolute;
            top: 50%;
            right: 14px;
            transform: translateY(-50%);
            background: none;
            border: none;
            cursor: pointer;
            padding: 5px;
            color: var(--text-secondary);
        }
        #password-toggle svg {
            width: 20px;
            height: 20px;
        }
        button[type="submit"] {
            width: 100%;
            padding: 15px;
            border: none;
            background: linear-gradient(135deg, var(--accent-color-end), var(--accent-color-start));
            color: white;
            font-size: 16px;
            font-weight: 700;
            border-radius: 12px;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        button[type="submit"]:hover {
            transform: translateY(-3px);
            box-shadow: 0 10px 20px rgba(138, 35, 135, 0.25);
        }
        button[type="submit"]:disabled {
            background: #4B5563;
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <img src="https://i.ibb.co/8gSLmLCD/LOGO-HARZAFI.png" alt="Logo Harzafi" class="logo">
        <h2>Accesso Area Riservata</h2>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="flash-message {{ category }}">
                        <svg xmlns="http://www.w3.org/2000/svg" height="20px" viewBox="0 0 24 24" width="20px" fill="currentColor"><path d="M0 0h24v24H0V0z" fill="none"/><path d="M11 15h2v2h-2zm0-8h2v6h-2zm.99-5C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8z"/></svg>
                        <span>{{ message }}</span>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        <form method="post" novalidate>
            {{ form.hidden_tag() }}
            <div class="form-group">
                {{ form.username.label(for="username") }}
                {{ form.username(id="username", class="form-control", required=True) }}
            </div>
            <div class="form-group">
                {{ form.password.label(for="password") }}
                <div class="password-wrapper">
                    {{ form.password(id="password", class="form-control", required=True) }}
                    <button type="button" id="password-toggle" title="Mostra/Nascondi password">
                        <svg id="eye-open" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M0 0h24v24H0V0z" fill="none"/><path d="M12 4C7 4 2.73 7.11 1 11.5 2.73 15.89 7 19 12 19s9.27-3.11 11-7.5C21.27 7.11 17 4 12 4zm0 12.5c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>
                        <svg id="eye-closed" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" style="display:none;"><path d="M0 0h24v24H0V0z" fill="none"/><path d="M12 6.5c2.76 0 5 2.24 5 5 0 .69-.14 1.35-.38 1.96l1.56 1.56c.98-1.29 1.82-2.88 2.32-4.52C19.27 7.11 15 4 12 4c-1.27 0-2.49.2-3.64.57l1.65 1.65c.61-.24 1.27-.37 1.99-.37zm-1.07 1.07L8.98 5.62C10.03 5.2 11 5 12 5c2.48 0 4.75.99 6.49 2.64l-1.42 1.42c-.63-.63-1.42-1.06-2.29-1.28l-1.78 1.78zm-3.8 3.8l-1.57-1.57C4.6 10.79 3.66 11.5 3 12.5c1.73 4.39 6 7.5 9 7.5 1.33 0 2.6-.25 3.77-.69l-1.63-1.63c-.67.24-1.38.37-2.14.37-2.76 0-5-2.24-5-5 0-.76.13-1.47.37-2.14zM2.14 2.14L.73 3.55l2.09 2.09C2.01 6.62 1.35 7.69 1 9c1.73 4.39 6 7.5 9 7.5 1.55 0 3.03-.3 4.38-.84l2.06 2.06 1.41-1.41L2.14 2.14z"/></svg>
                    </button>
                </div>
            </div>
            <button type="submit">Accedi</button>
        </form>
    </div>
<script>
    document.addEventListener('DOMContentLoaded', () => {
        const passwordInput = document.getElementById('password');
        const toggleButton = document.getElementById('password-toggle');
        const eyeOpen = document.getElementById('eye-open');
        const eyeClosed = document.getElementById('eye-closed');

        if (toggleButton) {
            toggleButton.addEventListener('click', () => {
                if (passwordInput.type === 'password') {
                    passwordInput.type = 'text';
                    eyeOpen.style.display = 'none';
                    eyeClosed.style.display = 'block';
                } else {
                    passwordInput.type = 'password';
                    eyeOpen.style.display = 'block';
                    eyeClosed.style.display = 'none';
                }
            });
        }
    });
</script>
</body>
</html>
"""

#
# --- NUOVO DESIGN "APPLE-STYLE": PANNELLO_CONTROLLO_COMPLETO_HTML ---
#
PANNELLO_CONTROLLO_COMPLETO_HTML = """
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pannello di Controllo Harzafi</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
    <style>
        :root {
            --background: #000000;
            --content-background: #1D1D1F;
            --content-background-light: #2C2C2E;
            --border-color: #3A3A3C;
            --text-primary: #F5F5F7;
            --text-secondary: #86868B;
            --accent-primary: #A244A7;
            --accent-secondary: #8A2387;
            --success: #30D158;
            --danger: #FF453A;
            --blue: #0A84FF;
        }
        * { box-sizing: border-box; }
        ::selection { background-color: var(--accent-primary); color: var(--text-primary); }
        body {
            font-family: 'Inter', sans-serif;
            background: var(--background);
            color: var(--text-primary);
            margin: 0;
            padding: 20px;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
            overflow-y: scroll;
        }
        .main-container {
            max-width: 1200px;
            margin: 0 auto;
            display: flex;
            flex-direction: column;
            gap: 40px;
        }
        .main-header {
            display: flex; justify-content: space-between; align-items: center;
            padding: 20px 0; border-bottom: 1px solid var(--border-color);
        }
        .header-title { display: flex; align-items: center; gap: 15px; }
        .header-title img { max-width: 100px; }
        .header-title h1 { font-size: 28px; font-weight: 700; margin: 0; }
        #logout-btn {
            background: var(--content-background); color: var(--danger); border: 1px solid var(--border-color);
            padding: 8px 16px; border-radius: 99px; font-weight: 600; cursor: pointer;
            transition: all 0.2s cubic-bezier(0.25, 0.1, 0.25, 1);
        }
        #logout-btn:hover { background: var(--danger); color: var(--white); border-color: var(--danger); }
        .control-section {
            background: var(--content-background);
            padding: 30px; border-radius: 20px;
            animation: fadeIn 0.5s ease-out forwards;
            opacity: 0;
        }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(15px); } to { opacity: 1; transform: translateY(0); } }
        .control-section h2 {
            font-size: 22px; font-weight: 600; margin: 0 0 10px 0;
            color: var(--text-primary); letter-spacing: -0.5px;
        }
        .control-section .subtitle {
            font-size: 16px; color: var(--text-secondary);
            margin: -5px 0 25px 0; max-width: 600px;
        }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 25px; }
        .control-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 10px; font-weight: 500; color: var(--text-secondary); font-size: 14px; }
        select, button, input[type="text"], textarea {
            width: 100%; padding: 12px 14px; border-radius: 12px;
            border: 1px solid var(--border-color);
            font-size: 15px; box-sizing: border-box; font-family: 'Inter', sans-serif;
            background-color: var(--content-background-light); color: var(--text-primary);
            transition: all 0.2s cubic-bezier(0.25, 0.1, 0.25, 1);
        }
        textarea { min-height: 100px; resize: vertical; }
        select:focus, input:focus, textarea:focus { outline: none; border-color: var(--blue); box-shadow: 0 0 0 3px rgba(10, 132, 255, 0.3); }
        button { cursor: pointer; border: none; font-weight: 600; border-radius: 12px; }
        button:disabled { background: #3A3A3C; color: #86868B; cursor: not-allowed; transform: none !important; }
        button:not(:disabled):hover { filter: brightness(1.1); }
        button:not(:disabled):active { transform: scale(0.98); }
        .btn-primary { background: var(--blue); color: var(--white); }
        .btn-success { background: var(--success); color: var(--white); }
        .btn-danger { background: var(--danger); color: var(--white); }
        .btn-secondary { background: var(--content-background-light); color: var(--text-primary); border: 1px solid var(--border-color); }
        #status-card { background: linear-gradient(135deg, var(--accent-secondary), var(--accent-primary)); padding: 25px; border-radius: 16px; color: var(--white); }
        #status-card h3 { margin: 0 0 10px; font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; opacity: 0.8; }
        #status-stop-name { font-size: 32px; font-weight: 700; margin: 0; line-height: 1.1; letter-spacing: -1px; }
        #status-stop-subtitle { font-size: 16px; opacity: 0.9; margin: 4px 0 0 0; }
        .status-details-grid { display: flex; gap: 20px; margin-top: 15px; border-top: 1px solid rgba(255,255,255,0.2); padding-top: 15px; }
        .status-detail { font-size: 14px; }
        #status-progress { font-weight: 600; }
        .line-list { list-style: none; padding: 0; margin: 0; }
        .line-item { display: flex; align-items: center; justify-content: space-between; padding: 12px; border-radius: 12px; transition: background-color 0.2s; }
        .line-item:not(:last-child) { margin-bottom: 5px; }
        .line-item:hover { background-color: var(--content-background-light); }
        .line-actions { display: flex; gap: 10px; }
        .line-actions button { width: auto; padding: 6px 12px; font-size: 13px; }
        dialog { width: 95%; max-width: 500px; border-radius: 20px; border: 1px solid var(--border-color); background: var(--background); color: var(--text-primary); box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5); padding: 30px; animation: dialog-in 0.4s cubic-bezier(0.16, 1, 0.3, 1); }
        dialog::backdrop { background-color: rgba(0,0,0,0.7); backdrop-filter: blur(8px); animation: backdrop-in 0.3s ease; }
        @keyframes dialog-in { from { opacity: 0; transform: translateY(30px) scale(0.95); } to { opacity: 1; transform: translateY(0) scale(1); } }
        @keyframes backdrop-in { from { opacity: 0; } to { opacity: 1; } }
        .modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 25px; }
        .toggle-switch { position: relative; display: inline-block; width: 50px; height: 28px; }
        .toggle-switch input { opacity: 0; width: 0; height: 0; }
        .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: var(--content-background-light); transition: .4s; border-radius: 28px; }
        .slider:before { position: absolute; content: ""; height: 22px; width: 22px; left: 3px; bottom: 3px; background-color: white; transition: .4s cubic-bezier(0.16, 1, 0.3, 1); border-radius: 50%; }
        input:checked + .slider { background-color: var(--success); }
        input:checked + .slider:before { transform: translateX(22px); }
    </style>
</head>
<body>
    <div class="main-container">
        <header class="main-header">
            <div class="header-title">
                <img src="https://i.ibb.co/8gSLmLCD/LOGO-HARZAFI.png" alt="Logo Harzafi">
                <h1>Pannello</h1>
            </div>
            <a href="{{ url_for('logout') }}"><button id="logout-btn">Logout</button></a>
        </header>

        <section class="control-section">
            <div class="grid" style="align-items: center;">
                <div>
                    <h2>Stato Attuale</h2>
                    <p class="subtitle">Monitora e naviga la linea attiva in tempo reale.</p>
                </div>
                <div id="status-card">
                    <h3>Stato Attuale (<span id="status-progress">--/--</span>)</h3>
                    <h4 id="status-stop-name">Nessuna fermata</h4>
                    <p id="status-stop-subtitle">Selezionare una linea</p>
                    <div class="status-details-grid">
                        <div class="status-detail"><strong>Linea:</strong> <span id="status-line-name">N/D</span></div>
                        <div class="status-detail"><strong>Dest.:</strong> <span id="status-line-direction">N/D</span></div>
                    </div>
                </div>
            </div>
        </section>

        <section class="control-section">
            <h2>Controlli Principali</h2>
            <p class="subtitle">Modifica la linea, naviga tra le fermate e gestisci lo stato del servizio.</p>
            <div class="grid">
                 <div class="control-group">
                    <label for="line-selector">Linea Attiva</label>
                    <select id="line-selector"></select>
                </div>
                <div class="control-group">
                    <label>Navigazione Fermate</label>
                    <div style="display: flex; gap: 15px;">
                        <button id="prev-btn" class="btn-secondary" style="font-size: 20px;">←</button>
                        <button id="next-btn" class="btn-secondary" style="font-size: 20px;">→</button>
                    </div>
                </div>
                <div class="control-group">
                     <label>Stato del Servizio</label>
                     <div style="display: flex; align-items: center; justify-content: space-between; background-color: var(--content-background-light); padding: 10px 15px; border-radius: 12px;">
                        <span id="service-status-text" style="font-weight: 600;">Caricamento...</span>
                        <label class="toggle-switch">
                            <input type="checkbox" id="service-status-toggle">
                            <span class="slider"></span>
                        </label>
                    </div>
                </div>
                <div class="control-group">
                    <label>Annuncio Vocale</label>
                    <button id="announce-btn" title="Annuncia" class="btn-primary" style="padding: 12px;">ANNUNCIA PROSSIMA FERMATA</button>
                </div>
            </div>
        </section>

        <section class="control-section">
            <h2>Gestione Media e Messaggi</h2>
             <p class="subtitle">Carica contenuti video o imposta messaggi informativi a scorrimento.</p>
             <div class="grid">
                 <div>
                    <label for="embed-code-input">Codice Embed (iframe)</label>
                    <textarea id="embed-code-input" placeholder="Incolla qui il codice <iframe>..."></textarea>
                    <button id="import-embed-btn" class="btn-secondary" style="margin-top: 10px;">Imposta da Embed</button>
                    <hr style="border-color: var(--border-color); margin: 20px 0;">
                    <input type="file" id="video-importer" accept="video/*" style="display: none;">
                    <button id="import-video-btn" class="btn-secondary">Importa Video Locale</button>
                    <p id="media-upload-status" style="font-size: 14px; color: var(--text-secondary); margin-top: 15px;">Nessun media caricato.</p>
                    <button id="remove-media-btn" class="btn-danger" style="display: none; width: auto; padding: 8px 15px; font-size: 13px;">Rimuovi Media</button>
                 </div>
                 <div>
                     <label for="info-messages-input">Messaggi a scorrimento (uno per riga)</label>
                     <textarea id="info-messages-input" placeholder="Benvenuti a bordo..."></textarea>
                     <button id="save-messages-btn" class="btn-primary" style="margin-top: 10px;">Salva Messaggi</button>
                 </div>
             </div>
        </section>

        <section class="control-section">
            <h2>Gestione Linee</h2>
            <p class="subtitle">Crea, modifica o elimina le linee e le relative fermate.</p>
            <ul id="line-management-list" class="line-list"></ul>
            <div style="display: flex; gap: 10px; margin-top: 20px; flex-wrap: wrap;">
                 <button id="add-new-line-btn" class="btn-success" style="flex-grow: 1;">+ Aggiungi Nuova Linea</button>
                 <button id="reset-data-btn" class="btn-danger" style="flex-grow: 1;">Reset Dati Predefiniti</button>
            </div>
        </section>
    </div>

    <dialog id="line-editor-modal">
        <h2 id="modal-title" style="margin-bottom: 25px;">Editor Linea</h2>
        <form id="line-editor-form">
            <input type="hidden" id="edit-line-id">
            <div class="control-group"><label for="line-name">Nome Linea</label><input type="text" id="line-name" required></div>
            <div class="control-group"><label for="line-direction">Destinazione</label><input type="text" id="line-direction" required></div>
            <div id="stops-editor">
                <label>Fermate</label>
                <div id="stops-list" style="max-height: 250px; overflow-y: auto; padding-right: 10px;"></div>
                <button type="button" id="add-stop-btn" class="btn-secondary" style="margin-top: 10px; width: 100%;">+ Aggiungi Fermata</button>
            </div>
            <div class="modal-actions">
                <button type="button" id="cancel-btn" class="btn-secondary">Annulla</button>
                <button type="submit" class="btn-primary">Salva Modifiche</button>
            </div>
        </form>
    </dialog>

<script>
// Il codice Javascript è stato mantenuto nella sua logica,
// ma alcuni selettori sono stati aggiornati per il nuovo HTML.
document.addEventListener('DOMContentLoaded', () => {
    const socket = io();

    function handleAuthError() {
        alert("Sessione scaduta o non valida. Verrai reindirizzato alla pagina di login.");
        window.location.href = "{{ url_for('login') }}";
    }

    async function fetchAuthenticated(url, options) {
        try {
            const response = await fetch(url, options);
            if (response.status === 401 || response.redirected) { 
                handleAuthError();
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
            linesData: linesData, currentLineKey: currentLineKey, currentStopIndex: currentStopIndex,
            mediaSource: localStorage.getItem('busSystem-mediaSource'), embedCode: localStorage.getItem('busSystem-embedCode'),
            videoName: localStorage.getItem('busSystem-videoName'), mediaLastUpdated: localStorage.getItem('busSystem-mediaLastUpdated'),
            muteState: localStorage.getItem('busSystem-muteState') || 'muted', volumeLevel: localStorage.getItem('busSystem-volumeLevel') || '1.0',
            playbackState: localStorage.getItem('busSystem-playbackState') || 'playing',
            videoProgress: JSON.parse(localStorage.getItem('busSystem-videoProgress') || 'null'),
            infoMessages: JSON.parse(localStorage.getItem('busSystem-infoMessages') || '[]'),
            serviceStatus: serviceStatus,
            announcement: JSON.parse(localStorage.getItem('busSystem-playAnnouncement') || 'null')
        };
        socket.emit('update_all', state);
        if (state.announcement) localStorage.removeItem('busSystem-playAnnouncement');
    }

    const importVideoBtn = document.getElementById('import-video-btn');
    const videoImporter = document.getElementById('video-importer');
    const importEmbedBtn = document.getElementById('import-embed-btn');
    const embedCodeInput = document.getElementById('embed-code-input');
    const removeMediaBtn = document.getElementById('remove-media-btn');
    const mediaUploadStatusText = document.getElementById('media-upload-status');
    const lineSelector = document.getElementById('line-selector');
    const prevBtn = document.getElementById('prev-btn');
    const nextBtn = document.getElementById('next-btn');
    const announceBtn = document.getElementById('announce-btn');
    const lineManagementList = document.getElementById('line-management-list');
    const addNewLineBtn = document.getElementById('add-new-line-btn');
    const modal = document.getElementById('line-editor-modal');
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

    let linesData = {}, currentLineKey = null, currentStopIndex = 0, serviceStatus = 'online';

    function getDefaultData() {
        return {
            "3": { "direction": "CORSA DEVIATA", "stops": [{ "name": "VALLETTE", "subtitle": "CAPOLINEA - TERMINAL" }, { "name": "PRIMULE", "subtitle": "" }, { "name": "PERVINCHE", "subtitle": "" }, { "name": "SANSOVINO", "subtitle": "" }, { "name": "CINCINNATO", "subtitle": "MERCATO RIONALE" }, { "name": "LOMBARDIA", "subtitle": "PISCINA LOMBARDIA" }, { "name": "BORSI", "subtitle": "" }, { "name": "LARGO TOSCANA", "subtitle": "" }, { "name": "LARGO BORGARO", "subtitle": "" }, { "name": "PIERO DELLA FRANCESCA", "subtitle": "MUSEO A COME AMBIENTE" }, { "name": "OSPEDALE AMEDEO DI SAVOIA", "subtitle": "DIPARTIMENTO DI INFORMATICA" }, { "name": "TASSONI", "subtitle": "" }, { "name": "AVELLINO", "subtitle": "" }, { "name": "LIVORNO", "subtitle": "" }, { "name": "INDUSTRIA", "subtitle": "" }, { "name": "RONDÒ FORCA OVEST", "subtitle": "MARIA AUSILIATRICE" }, { "name": "OSPEDALE COTTOLENGO", "subtitle": "ANAGRAFE CENTRALE" }, { "name": "PORTA PALAZZO", "subtitle": "PIAZZA DELLA REPUBBLICA" }, { "name": "PORTA PALAZZO EST", "subtitle": "PIAZZA DELLA REPUBBLICA" }, { "name": "XI FEBBRAIO", "subtitle": "AUTOSTAZIONE DORA" }, { "name": "GIARDINI REALI", "subtitle": "RONDÒ RIVELLA" }, { "name": "ROSSINI", "subtitle": "MOLE ANTONELLIANA" }, { "name": "CAMPUS EINAUDI", "subtitle": "" }, { "name": "LARGO BERARDI", "subtitle": "" }, { "name": "OSPEDALE GRADENIGO", "subtitle": "" }, { "name": "TORTONA", "subtitle": "CAPOLINEA - TERMINAL" }] }
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
            saveMessagesBtn.textContent = 'Salvato!'; saveMessagesBtn.classList.add('btn-success'); saveMessagesBtn.classList.remove('btn-primary');
            setTimeout(() => { saveMessagesBtn.textContent = originalText; saveMessagesBtn.classList.remove('btn-success'); saveMessagesBtn.classList.add('btn-primary'); }, 2000);
        }
    }

    function loadMediaStatus() {
        const mediaSource = localStorage.getItem('busSystem-mediaSource');
        const videoName = localStorage.getItem('busSystem-videoName');
        if (mediaSource === 'embed') {
            mediaUploadStatusText.textContent = `Media da Embed attivo.`;
            removeMediaBtn.style.display = 'inline-block';
        } else if (mediaSource === 'server' && videoName) {
            mediaUploadStatusText.textContent = `Video locale: ${videoName}`;
            removeMediaBtn.style.display = 'inline-block';
        } else {
            mediaUploadStatusText.textContent = 'Nessun media caricato.';
            removeMediaBtn.style.display = 'none';
        }
    }

    async function handleLocalVideoUpload(event) {
        const file = event.target.files[0]; if (!file) return;
        importVideoBtn.disabled = true; importVideoBtn.textContent = 'CARICAMENTO...';
        const formData = new FormData(); formData.append('video', file);
        const response = await fetchAuthenticated('/upload-video', { method: 'POST', body: formData });
        if (response && response.ok) {
            localStorage.setItem('busSystem-mediaSource', 'server'); localStorage.setItem('busSystem-videoName', file.name);
            localStorage.removeItem('busSystem-embedCode');
            localStorage.setItem('busSystem-mediaLastUpdated', Date.now());
            loadMediaStatus(); sendFullStateUpdate();
        } else { alert('Errore durante il caricamento del video.'); }
        importVideoBtn.disabled = false; importVideoBtn.textContent = 'Importa Video Locale';
    }
    async function handleEmbedImport() {
        const rawCode = embedCodeInput.value.trim();
        if (!rawCode.includes('<iframe')) { alert('Codice <iframe> non valido.'); return; }
        await fetchAuthenticated('/clear-video', { method: 'POST' });
        const tempDiv = document.createElement('div'); tempDiv.innerHTML = rawCode;
        const iframe = tempDiv.querySelector('iframe'); if (!iframe) { alert('Tag <iframe> non trovato.'); return; }
        iframe.setAttribute('width', '100%'); iframe.setAttribute('height', '100%');
        iframe.setAttribute('style', 'position:absolute; top:0; left:0; width:100%; height:100%;');
        localStorage.setItem('busSystem-mediaSource', 'embed');
        localStorage.setItem('busSystem-embedCode', iframe.outerHTML);
        localStorage.removeItem('busSystem-videoName');
        localStorage.setItem('busSystem-mediaLastUpdated', Date.now());
        loadMediaStatus(); embedCodeInput.value = ''; sendFullStateUpdate();
    }
    async function removeMedia() {
        if (!confirm('Rimuovere il media attuale?')) return;
        await fetchAuthenticated('/clear-video', { method: 'POST' });
        localStorage.removeItem('busSystem-mediaSource'); localStorage.removeItem('busSystem-videoName');
        localStorage.removeItem('busSystem-embedCode');
        localStorage.setItem('busSystem-mediaLastUpdated', Date.now());
        loadMediaStatus(); sendFullStateUpdate();
    }

    function loadServiceStatus() { serviceStatus = localStorage.getItem('busSystem-serviceStatus') || 'online'; renderServiceStatus(); }
    function saveServiceStatus() { localStorage.setItem('busSystem-serviceStatus', serviceStatus); sendFullStateUpdate(); }
    function renderServiceStatus() {
        const isOnline = serviceStatus === 'online';
        serviceStatusText.textContent = isOnline ? 'In Servizio' : 'Fuori Servizio';
        serviceStatusText.style.color = isOnline ? 'var(--success)' : 'var(--danger)';
        serviceStatusToggle.checked = isOnline;
    }

    function renderAll() { renderNavigationPanel(); renderManagementPanel(); renderStatusDisplay(); }
    function renderNavigationPanel() {
        lineSelector.innerHTML = '';
        const keys = Object.keys(linesData).sort();
        if (keys.length > 0) {
            keys.forEach(key => {
                const option = document.createElement('option');
                option.value = key; option.textContent = `${key} → ${linesData[key].direction}`;
                lineSelector.appendChild(option);
            });
            if (linesData[currentLineKey]) lineSelector.value = currentLineKey;
        } else {
            lineSelector.innerHTML = '<option>Nessuna linea disponibile</option>';
        }
    }
    function renderManagementPanel() {
        lineManagementList.innerHTML = '';
        Object.keys(linesData).sort().forEach(key => {
            const item = document.createElement('li');
            item.className = 'line-item';
            item.innerHTML = `<span>${key} → ${linesData[key].direction}</span><div class="line-actions"><button class="btn-secondary edit-btn" data-id="${key}">Modifica</button><button class="btn-danger delete-btn" data-id="${key}">Elimina</button></div>`;
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
        const stop = line.stops[currentStopIndex]; if (!stop) return;
        statusLineName.textContent = currentLineKey; statusLineDirection.textContent = line.direction;
        statusStopName.textContent = stop.name; statusStopSubtitle.textContent = stop.subtitle || ' ';
        statusProgress.textContent = `${currentStopIndex + 1}/${line.stops.length}`;
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
        loadMediaStatus(); loadData(); loadMessages(); loadServiceStatus();
        currentLineKey = localStorage.getItem('busSystem-currentLine');
        currentStopIndex = parseInt(localStorage.getItem('busSystem-currentStopIndex'), 10) || 0;
        renderAll(); updateAndRenderStatus();
    }
    
    lineSelector.addEventListener('change', (e) => { currentLineKey = e.target.value; currentStopIndex = 0; updateAndRenderStatus(); });
    resetDataBtn.addEventListener('click', () => { if (confirm('Sei sicuro? Questa azione cancellerà tutti i dati e richiederà un nuovo login.')) { localStorage.clear(); window.location.href="{{ url_for('logout') }}"; } });
    nextBtn.addEventListener('click', () => { const currentLine = linesData[currentLineKey]; if (currentLine && currentStopIndex < currentLine.stops.length - 1) { currentStopIndex++; updateAndRenderStatus(); } });
    prevBtn.addEventListener('click', () => { if (currentStopIndex > 0) { currentStopIndex--; updateAndRenderStatus(); } });
    announceBtn.addEventListener('click', () => { 
        if (currentLineKey && linesData[currentLineKey]) {
            localStorage.setItem('busSystem-playAnnouncement', JSON.stringify({ timestamp: Date.now() })); 
            sendFullStateUpdate();
        } else { alert('Nessuna linea attiva selezionata.'); } 
    });
    serviceStatusToggle.addEventListener('change', () => { serviceStatus = serviceStatusToggle.checked ? 'online' : 'offline'; saveServiceStatus(); renderServiceStatus(); });
    importVideoBtn.addEventListener('click', () => videoImporter.click());
    videoImporter.addEventListener('change', handleLocalVideoUpload);
    importEmbedBtn.addEventListener('click', handleEmbedImport);
    removeMediaBtn.addEventListener('click', removeMedia);
    addNewLineBtn.addEventListener('click', () => { document.getElementById('edit-line-id').value = ''; document.getElementById('modal-title').textContent = 'Aggiungi Nuova Linea'; lineEditorForm.reset(); stopsListContainer.innerHTML = ''; modal.showModal(); });
    lineManagementList.addEventListener('click', (e) => {
        const target = e.target.closest('button'); if (!target) return; const lineId = target.dataset.id;
        if (target.classList.contains('edit-btn')) {
            editLineId.value = lineId; document.getElementById('modal-title').textContent = `Modifica Linea: ${lineId}`; const line = linesData[lineId];
            lineNameInput.value = lineId; lineDirectionInput.value = line.direction; stopsListContainer.innerHTML = ''; (line.stops || []).forEach(s => addStopToModal(s)); modal.showModal();
        } if (target.classList.contains('delete-btn')) { if (confirm(`Eliminare la linea "${lineId}"?`)) { delete linesData[lineId]; saveData(); renderAll(); } }
    });
    addStopBtn.addEventListener('click', () => addStopToModal());
    stopsListContainer.addEventListener('click', (e) => { if (e.target.classList.contains('remove-stop-btn')) { if (stopsListContainer.children.length > 1) e.target.parentElement.remove(); else alert('Ogni linea deve avere almeno una fermata.'); } });
    function addStopToModal(stop = { name: '', subtitle: '' }) {
        const stopItem = document.createElement('div'); stopItem.style.display='flex'; stopItem.style.gap='10px'; stopItem.style.marginBottom='10px';
        stopItem.innerHTML = `<input type="text" placeholder="Nome fermata" class="stop-name-input" value="${stop.name || ''}" required style="flex-grow:1;"><input type="text" placeholder="Sottotitolo (opz.)" class="stop-subtitle-input" value="${stop.subtitle || ''}" style="flex-grow:1;"><button type="button" class="btn-danger remove-stop-btn" style="width:auto; padding: 10px 12px;">-</button>`;
        stopsListContainer.appendChild(stopItem);
    }
    lineEditorForm.addEventListener('submit', (e) => {
        e.preventDefault(); const originalId = editLineId.value; const newId = lineNameInput.value.trim().toUpperCase(); const direction = lineDirectionInput.value.trim();
        if (!newId || !direction) { alert('Nome linea e destinazione sono obbligatori.'); return; }
        const stops = Array.from(stopsListContainer.querySelectorAll('.stop-name-input')).map((input, i) => {
            const name = input.value.trim().toUpperCase();
            const subtitle = stopsListContainer.querySelectorAll('.stop-subtitle-input')[i].value.trim().toUpperCase();
            return { name, subtitle };
        }).filter(s => s.name);
        if (stops.length === 0) { alert('Aggiungere almeno una fermata con un nome.'); return; }
        if (originalId && originalId !== newId) delete linesData[originalId]; linesData[newId] = { direction, stops }; saveData();
        if (currentLineKey === originalId) { currentLineKey = newId; localStorage.setItem('busSystem-currentLine', newId); }
        renderAll(); updateAndRenderStatus(); modal.close();
    });
    saveMessagesBtn.addEventListener('click', () => saveMessages(true));
    const cancelBtn = document.getElementById('cancel-btn');
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.close(); });
    cancelBtn.addEventListener('click', () => modal.close());

    initialize();
});
</script>
</body>
</html>
"""

#
# --- NUOVO DESIGN "APPLE-STYLE": VISUALIZZATORE_COMPLETO_HTML ---
#
VISUALIZZATORE_COMPLETO_HTML = """
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Visualizzazione Fermata Harzafi</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
    <style>
        :root {
            --background: #000;
            --text-primary: #FFFFFF;
            --text-secondary: #86868B;
            --line-color: #A244A7;
            --line-border: #3A3A3C;
            --ease-out-quint: cubic-bezier(0.22, 1, 0.36, 1);
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: 'Inter', sans-serif;
            background: var(--background);
            color: var(--text-primary);
            height: 100vh;
            display: flex;
            overflow: hidden;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
        }
        #loader {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            background: var(--background); z-index: 999; transition: opacity 0.8s ease;
        }
        #loader img { width: 200px; animation: pulse-logo 2.5s infinite ease-in-out; }
        #loader p { margin-top: 25px; font-size: 1em; font-weight: 500; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 1px; }
        @keyframes pulse-logo {
            0%, 100% { transform: scale(1); opacity: 0.8; }
            50% { transform: scale(1.03); opacity: 1; }
        }
        #loader.hidden { opacity: 0; pointer-events: none; }
        .main-grid {
            width: 100%; height: 100%;
            display: grid; grid-template-columns: 55% 45%;
            padding: 5vh; gap: 5vh;
        }
        .info-container {
            display: flex; flex-direction: column; justify-content: space-between;
            opacity: 0; animation: fadeIn 1s var(--ease-out-quint) forwards;
        }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        .header { display: flex; align-items: center; gap: 20px; }
        .line-id-display {
            width: 90px; height: 90px; flex-shrink: 0;
            background: var(--text-primary); border-radius: 25px;
            display: flex; align-items: center; justify-content: center;
        }
        #line-id { font-size: 48px; font-weight: 800; color: var(--line-color); }
        .direction-info {
            overflow: hidden; white-space: nowrap;
        }
        .direction-header { font-size: 24px; font-weight: 500; color: var(--text-secondary); margin: 0; }
        #direction-name { font-size: 42px; font-weight: 700; margin: 0; letter-spacing: -1px; }
        .stop-info { padding: 20px 0; }
        .next-stop-header { font-size: 28px; font-weight: 500; color: var(--text-secondary); margin: 0; }
        .stop-name-wrapper {
            position: relative; margin-top: 10px; height: 150px; /* Altezza fissa per animazione stabile */
        }
        #stop-name {
            font-size: 130px; font-weight: 800; margin: 0; line-height: 1; letter-spacing: -5px;
            position: absolute; top: 0; left: 0; width: 100%;
            transition: opacity 0.6s var(--ease-out-quint), transform 0.6s var(--ease-out-quint);
        }
        #stop-name.exit-up { opacity: 0; transform: translateY(-50px); }
        #stop-name.exit-down { opacity: 0; transform: translateY(50px); }
        #stop-name.enter-up { opacity: 0; transform: translateY(50px); }
        #stop-name.enter-down { opacity: 0; transform: translateY(-50px); }
        #stop-subtitle {
            font-size: 42px; font-weight: 400; color: var(--text-secondary); margin-top: 10px;
            transition: opacity 0.6s var(--ease-out-quint), transform 0.6s var(--ease-out-quint);
        }
        .logo-footer { display: flex; align-items: center; gap: 15px; border-top: 1px solid var(--line-border); padding-top: 25px; }
        .logo-footer img { width: 100px; }
        .logo-footer p { font-size: 16px; font-weight: 500; color: var(--text-secondary); }
        .video-container {
            width: 100%; height: 100%;
            opacity: 0; animation: fadeIn 1s var(--ease-out-quint) 0.2s forwards;
            position: relative;
        }
        #video-player-container {
            width: 100%; height: 100%; background-color: #111;
            border-radius: 25px; overflow: hidden;
            box-shadow: 0 20px 40px rgba(0,0,0,0.5);
            transition: all 0.5s var(--ease-out-quint);
        }
        #ad-video, #video-player-container iframe { width: 100%; height: 100%; object-fit: cover; border: 0; }
        .placeholder-content {
            width: 100%; height: 100%; display: flex; align-items: center; justify-content: center;
            font-size: 24px; font-weight: 600; color: var(--text-secondary);
        }
        #service-offline-overlay {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: 1000;
            display: flex; align-items: center; justify-content: center; text-align: center;
            background-color: rgba(0,0,0,0.7); backdrop-filter: blur(15px);
            transition: opacity 0.5s ease; opacity: 0; pointer-events: none;
        }
        #service-offline-overlay.visible { opacity: 1; pointer-events: auto; }
        #service-offline-overlay h2 { font-size: 5vw; font-weight: 700; margin: 0; letter-spacing: -2px; }
    </style>
</head>
<body>
    <audio id="announcement-sound" src="/announcement-audio" preload="auto"></audio>
    <div id="loader">
        <img src="https://i.ibb.co/8gSLmLCD/LOGO-HARZAFI.png" alt="Logo Harzafi">
        <p>Inizializzazione Sistema...</p>
    </div>
    <div class="main-grid">
        <div class="info-container">
            <header class="header">
                <div class="line-id-display"><span id="line-id">--</span></div>
                <div class="direction-info">
                    <p class="direction-header">DESTINAZIONE</p>
                    <h1 id="direction-name">Caricamento...</h1>
                </div>
            </header>
            <main class="stop-info">
                <p class="next-stop-header">PROSSIMA FERMATA</p>
                <div class="stop-name-wrapper">
                    <h2 id="stop-name">In attesa di dati...</h2>
                </div>
                <p id="stop-subtitle"></p>
            </main>
            <footer class="logo-footer">
                <img src="https://i.ibb.co/8gSLmLCD/LOGO-HARZAFI.png" alt="Logo Harzafi">
                <p>Sistema informativo di bordo</p>
            </footer>
        </div>
        <div class="video-container">
            <div id="video-player-container"></div>
        </div>
    </div>
    <div id="service-offline-overlay"><h2>SERVIZIO NON ATTIVO</h2></div>

<script>
document.addEventListener('DOMContentLoaded', () => {
    const socket = io();
    const videoPlayerContainer = document.getElementById('video-player-container');
    const announcementSound = document.getElementById('announcement-sound');
    let lastKnownState = {};

    function applyMediaState(state) {
        const videoEl = document.getElementById('ad-video');
        if (videoEl) {
            videoEl.muted = (state.muteState === 'muted');
            videoEl.volume = parseFloat(state.volumeLevel);
            if (state.playbackState === 'playing' && videoEl.paused) videoEl.play().catch(e => {});
            else if (state.playbackState === 'paused' && !videoEl.paused) videoEl.pause();
        }
    }
    
    function loadMediaOrPlaceholder(state) {
        let newContent = '';
        if (state.mediaSource === 'embed' && state.embedCode) {
            newContent = state.embedCode;
        } else if (state.mediaSource === 'server') {
            const videoUrl = `/stream-video?t=${state.mediaLastUpdated}`;
            newContent = `<video id="ad-video" loop playsinline autoplay></video>`;
            setTimeout(() => { 
                const videoEl = document.getElementById('ad-video');
                if(videoEl) videoEl.src = videoUrl;
            }, 10);
        } else {
            newContent = `<div class="placeholder-content"></div>`;
        }
        
        if (videoPlayerContainer.innerHTML !== newContent) {
            videoPlayerContainer.innerHTML = newContent;
        }

        applyMediaState(state);
    }

    const loaderEl = document.getElementById('loader');
    const lineIdEl = document.getElementById('line-id');
    const directionNameEl = document.getElementById('direction-name');
    const stopNameEl = document.getElementById('stop-name');
    const stopSubtitleEl = document.getElementById('stop-subtitle');
    const serviceOfflineOverlay = document.getElementById('service-offline-overlay');

    function playAnnouncement() {
        const videoEl = document.getElementById('ad-video');
        let originalVolume = 1.0;
        if (videoEl && !videoEl.muted) {
            originalVolume = videoEl.volume;
            videoEl.volume = Math.min(originalVolume, 0.15);
        }
        announcementSound.currentTime = 0;
        announcementSound.play().catch(e => console.error("Errore riproduzione annuncio:", e));
        announcementSound.onended = () => {
            if (videoEl) videoEl.volume = originalVolume;
        };
    }

    function adjustFontSize(element, baseSize, minSize, maxChars) {
        const len = element.textContent.length;
        let newSize = baseSize;
        if (len > maxChars) {
            newSize = Math.max(minSize, baseSize * (maxChars / len));
        }
        element.style.fontSize = `${newSize}px`;
        element.style.letterSpacing = `${newSize < 100 ? -2 : -5}px`;
    }

    function checkServiceStatus(state) {
        if (state.serviceStatus === 'offline') {
            serviceOfflineOverlay.classList.add('visible');
            return false;
        }
        serviceOfflineOverlay.classList.remove('visible');
        return true;
    }
    
    function updateDisplay(state) {
        if (!checkServiceStatus(state) || !state.linesData || !state.currentLineKey) {
            return;
        }

        const isInitialLoad = !lastKnownState.currentLineKey;
        const lineChanged = lastKnownState.currentLineKey !== state.currentLineKey;
        const stopIndexChanged = lastKnownState.currentStopIndex !== state.currentStopIndex;

        loaderEl.classList.add('hidden');

        const line = state.linesData[state.currentLineKey];
        if (!line) return;
        const stop = line.stops[state.currentStopIndex];

        const updateTextContent = () => {
            lineIdEl.textContent = state.currentLineKey;
            directionNameEl.textContent = line.direction;
            stopNameEl.textContent = stop ? stop.name : 'CAPOLINEA';
            stopSubtitleEl.textContent = stop ? (stop.subtitle || '') : '';
            adjustFontSize(stopNameEl, 130, 70, 12);
        };
        
        if (!isInitialLoad && (lineChanged || stopIndexChanged)) {
            const isForward = state.currentStopIndex > lastKnownState.currentStopIndex;
            stopNameEl.className = isForward ? 'exit-up' : 'exit-down';
            stopSubtitleEl.style.opacity = 0;
            
            setTimeout(() => {
                stopNameEl.className = isForward ? 'enter-up' : 'enter-down';
                updateTextContent();
                
                setTimeout(() => {
                    stopNameEl.className = '';
                    stopSubtitleEl.style.opacity = 1;
                }, 20);
            }, 600);
        } else {
            updateTextContent();
        }

        if (state.announcement && state.announcement.timestamp > (lastKnownState.announcement?.timestamp || 0)) {
            playAnnouncement();
        }

        if (isInitialLoad || state.mediaLastUpdated > (lastKnownState.mediaLastUpdated || 0)) {
            loadMediaOrPlaceholder(state);
        } else {
            applyMediaState(state);
        }
        
        lastKnownState = JSON.parse(JSON.stringify(state)); // Deep copy
    }
    
    socket.on('connect', () => {
        loaderEl.querySelector('p').textContent = "Connesso. In attesa di dati...";
        socket.emit('request_initial_state');
    });

    socket.on('disconnect', () => {
        loaderEl.classList.remove('hidden');
        loaderEl.querySelector('p').textContent = "Connessione persa...";
    });

    socket.on('initial_state', updateDisplay);
    socket.on('state_updated', updateDisplay);
});
</script>
</body>
</html>
"""

# -------------------------------------------------------------------
# 4. ROUTE E API WEBSOCKET (CON SICUREZZA POTENZIATA E CORRETTA)
# -------------------------------------------------------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    form = LoginForm()

    # Esegui la logica solo quando l'utente invia il form
    if form.validate_on_submit():
        username = form.username.data

        # --- LOGICA DI SICUREZZA CORRETTA ---
        # 1. Controlla PRIMA se l'utente è bloccato
        if username in login_attempts:
            attempt_info = login_attempts[username]
            if attempt_info['attempts'] >= MAX_ATTEMPTS:
                lockout_end_time = attempt_info['time'] + timedelta(minutes=LOCKOUT_TIME_MINUTES)
                if datetime.now() < lockout_end_time:
                    remaining_time = round((lockout_end_time - datetime.now()).total_seconds())
                    flash(f"Troppi tentativi falliti. Riprova tra {remaining_time} secondi.", "error")
                    # Ricarica la pagina CON il messaggio di errore, senza fare redirect.
                    # Questo mantiene lo stato di blocco anche se la pagina viene ricaricata.
                    return render_template_string(LOGIN_PAGE_HTML, form=form)
                else:
                    # Se il tempo di blocco è scaduto, lo sblocchiamo
                    login_attempts.pop(username, None)

        # 2. Se non è bloccato, controlla la password
        user_in_db = USERS_DB.get(username)
        if user_in_db and check_password_hash(user_in_db['password_hash'], form.password.data):
            # Successo: pulisci i tentativi e fai il login
            login_attempts.pop(username, None)
            user = get_user(username)
            login_user(user)
            return redirect(request.args.get('next') or url_for('dashboard'))
        else:
            # Fallimento: registra il tentativo e mostra il messaggio
            if username not in login_attempts:
                login_attempts[username] = {'attempts': 0, 'time': None}
            
            login_attempts[username]['attempts'] += 1
            login_attempts[username]['time'] = datetime.now()

            remaining = MAX_ATTEMPTS - login_attempts[username]['attempts']
            if remaining > 0:
                flash(f"Credenziali non valide. Hai ancora {remaining} tentativi.", "error")
            else:
                flash(f"Account bloccato per {LOCKOUT_TIME_MINUTES} minuti.", "error")
            
            # Ricarica la pagina mostrando l'errore
            return render_template_string(LOGIN_PAGE_HTML, form=form)
    
    # Questo viene eseguito per la richiesta GET iniziale (quando si visita la pagina)
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

@app.route('/announcement-audio')
@login_required
def announcement_audio():
    try:
        return send_file('LINEA 3. CORSA DEVIATA..mp3', mimetype='audio/mpeg')
    except FileNotFoundError:
        print("ERRORE CRITICO: Il file 'LINEA 3. CORSA DEVIATA..mp3' non è stato trovato!")
        return Response("File audio dell'annuncio non trovato sul server.", status=404)

@app.route('/upload-video', methods=['POST'])
@login_required
def upload_video():
    global current_video_file
    if 'video' not in request.files: return jsonify({'error': 'Nessun file inviato'}), 400
    file = request.files['video']
    if file.filename == '': return jsonify({'error': 'Nessun file selezionato'}), 400
    current_video_file = {'data': file.read(), 'mimetype': file.mimetype, 'name': file.filename}
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
    current_video_file = {'data': None, 'mimetype': None, 'name': None}
    return jsonify({'success': True})

# --- GESTIONE WEBSOCKET ---

@socketio.on('connect')
def handle_connect():
    if not current_user.is_authenticated: return False
    print(f"Client autorizzato connesso: {current_user.name} ({request.sid})")
    if current_app_state: socketio.emit('initial_state', current_app_state, room=request.sid)

@socketio.on('disconnect')
def handle_disconnect():
    if hasattr(current_user, 'name'): print(f"Client {current_user.name} disconnesso.")

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
    if current_app_state: socketio.emit('initial_state', current_app_state, room=request.sid)

# -------------------------------------------------------------------
# 5. BLOCCO DI ESECUZIONE
# -------------------------------------------------------------------

if __name__ == '__main__':
    local_ip = get_local_ip()
    print("===================================================================")
    print("      SERVER HARZAFI v3 (Apple Design & Sicurezza Corretta)")
    print("===================================================================")
    print(f"Login: http://127.0.0.1:5000/login  |  http://{local_ip}:5000/login")
    print("Credenziali di default: admin / adminpass")
    print("===================================================================")
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
