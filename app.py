# -------------------------------------------------------------------
# !!! CORREZIONE CRITICA PER EVENTLET !!!
# Eventlet deve eseguire il monkey_patching prima di qualsiasi altro import.
# Questo risolve l'eccezione che blocca la comunicazione SocketIO.
# -------------------------------------------------------------------
import eventlet
eventlet.monkey_patch()
# -------------------------------------------------------------------

import sys
import socket
from functools import wraps
from datetime import datetime, timedelta
from flask import Flask, Response, request, abort, jsonify, render_template_string, redirect, url_for, flash, send_file
from flask_socketio import SocketIO
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
# IMPORTANTE: Assicurati di aver installato Flask-WTF con "pip install Flask-WTF"
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField
from wtforms.validators import DataRequired

# -------------------------------------------------------------------
# SEZIONE CONFIGURAZIONE SICUREZZA POTENZIATA E LOGIN
# -------------------------------------------------------------------

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

# --- PAGINA DI LOGIN (FUNZIONANTE) ---
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
            --background-start: #111827; --background-end: #1F2937;
            --card-background: rgba(31, 41, 55, 0.8); --border-color: rgba(107, 114, 128, 0.2);
            --accent-color-start: #8A2387; --accent-color-end: #A244A7;
            --text-primary: #F9FAFB; --text-secondary: #9CA3AF; --danger-color: #EF4444;
        }
        * { box-sizing: border-box; }
        body {
            font-family: 'Inter', sans-serif; background: linear-gradient(135deg, var(--background-start), var(--background-end));
            color: var(--text-primary); display: flex; align-items: center; justify-content: center;
            min-height: 100vh; margin: 0; padding: 20px;
        }
        .login-container {
            width: 100%; max-width: 420px; background: var(--card-background);
            border: 1px solid var(--border-color); padding: 40px; border-radius: 24px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.4); backdrop-filter: blur(10px);
            text-align: center; animation: fadeIn 0.5s ease-out;
        }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
        .logo { max-width: 150px; margin-bottom: 24px; filter: drop-shadow(0 0 15px rgba(255, 255, 255, 0.1)); }
        h2 { color: var(--text-primary); font-weight: 700; font-size: 24px; margin: 0 0 32px 0; }
        .flash-message {
            padding: 12px 15px; border-radius: 12px; margin-bottom: 20px; border: 1px solid; font-weight: 600;
            display: flex; align-items: center; gap: 10px; animation: slideIn .3s ease-out;
        }
        @keyframes slideIn { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); } }
        .flash-message.error {
            background-color: rgba(239, 68, 68, 0.1); color: var(--danger-color); border-color: rgba(239, 68, 68, 0.3);
        }
        .form-group { margin-bottom: 20px; text-align: left; position: relative; }
        label { display: block; margin-bottom: 8px; font-weight: 600; color: var(--text-secondary); font-size: 14px; }
        input {
            width: 100%; padding: 14px 16px; border-radius: 12px; border: 1px solid var(--border-color);
            background-color: #111827; color: var(--text-primary); font-size: 16px; font-family: 'Inter', sans-serif;
            transition: border-color 0.2s, box-shadow 0.2s;
        }
        input:focus { outline: none; border-color: var(--accent-color-end); box-shadow: 0 0 0 4px rgba(162, 68, 167, 0.2); }
        input:-webkit-autofill { -webkit-box-shadow: 0 0 0 30px #111827 inset !important; -webkit-text-fill-color: var(--text-primary) !important;}
        .password-wrapper { position: relative; }
        #password-toggle {
            position: absolute; top: 50%; right: 14px; transform: translateY(-50%);
            background: none; border: none; cursor: pointer; padding: 5px; color: var(--text-secondary);
        }
        #password-toggle svg { width: 20px; height: 20px; }
        button[type="submit"] {
            width: 100%; padding: 15px; border: none; background: linear-gradient(135deg, var(--accent-color-end), var(--accent-color-start));
            color: white; font-size: 16px; font-weight: 700; border-radius: 12px; cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        button[type="submit"]:hover { transform: translateY(-3px); box-shadow: 0 10px 20px rgba(138, 35, 135, 0.25); }
        button[type="submit"]:disabled { background: #4B5563; cursor: not-allowed; transform: none; box-shadow: none; }
    </style>
</head>
<body>
    <div class="login-container">
        <img src="https://i.ibb.co/nN5WRrHS/LOGO-HARZAFI.png" alt="Logo Harzafi" class="logo">
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
                        <svg id="eye-closed" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" style="display:none;"><path d="M0 0h24v24H0V0z" fill="none"/><path d="M12 6.5c2.76 0 5 2.24 5 5 0 .69-.14 1.35-.38 1.96l1.56 1.56c.98-1.29 1.82-2.88 2.32-4.52C19.27 7.11 15 4 12 4c-1.27 0-2.49 .2-3.64.57l1.65 1.65c.61-.24 1.27-.37 1.99-.37zm-1.07 1.07L8.98 5.62C10.03 5.2 11 5 12 5c2.48 0 4.75 .99 6.49 2.64l-1.42 1.42c-.63-.63-1.42-1.06-2.29-1.28l-1.78 1.78zm-3.8 3.8l-1.57-1.57C4.6 10.79 3.66 11.5 3 12.5c1.73 4.39 6 7.5 9 7.5 1.33 0 2.6-.25 3.77-.69l-1.63-1.63c-.67 .24-1.38 .37-2.14 .37-2.76 0-5-2.24-5-5 0-.76 .13-1.47 .37-2.14zM2.14 2.14L.73 3.55l2.09 2.09C2.01 6.62 1.35 7.69 1 9c1.73 4.39 6 7.5 9 7.5 1.55 0 3.03-.3 4.38-.84l2.06 2.06 1.41-1.41L2.14 2.14z"/></svg>
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
                const type = passwordInput.getAttribute('type') === 'password' ? 'text' : 'password';
                passwordInput.setAttribute('type', type);
                eyeOpen.style.display = type === 'password' ? 'block' : 'none';
                eyeClosed.style.display = type === 'password' ? 'none' : 'block';
            });
        }
    });
</script>
</body>
</html>
"""

# --- PANNELLO DI CONTROLLO (CON LOGICA 'loadData' CORRETTA) ---
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
            --background: #000000; --content-background: #1D1D1F; --content-background-light: #2C2C2E;
            --border-color: #3A3A3C; --text-primary: #F5F5F7; --text-secondary: #86868B;
            --accent-primary: #A244A7; --accent-secondary: #8A2387; --success: #30D158;
            --danger: #FF453A; --blue: #0A84FF;
        }
        * { box-sizing: border-box; }
        ::selection { background-color: var(--accent-primary); color: var(--text-primary); }
        body {
            font-family: 'Inter', sans-serif; background: var(--background); color: var(--text-primary);
            margin: 0; padding: 20px; overflow-y: scroll;
        }
        .main-container { max-width: 1200px; margin: 0 auto; display: flex; flex-direction: column; gap: 40px; }
        .main-header {
            display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center;
            gap: 20px; padding: 20px 0; border-bottom: 1px solid var(--border-color);
        }
        .header-title { display: flex; align-items: center; gap: 15px; }
        .header-title img { max-width: 100px; }
        .header-title h1 { font-size: 28px; font-weight: 700; margin: 0; }
        .header-actions { display: flex; align-items: center; gap: 15px; }
        .btn {
            padding: 8px 16px; border-radius: 99px; font-weight: 600; cursor: pointer;
            text-decoration: none; display: inline-block;
            transition: all 0.2s cubic-bezier(0.25, 0.1, 0.25, 1);
        }
        .btn-viewer { background: var(--blue); color: white; border: 1px solid var(--blue); }
        .btn-viewer:hover { filter: brightness(1.1); }
        #logout-btn { background: var(--content-background); color: var(--danger); border: 1px solid var(--border-color); }
        #logout-btn:hover { background: var(--danger); color: white; border-color: var(--danger); }
        .control-section {
            background: var(--content-background); padding: 30px; border-radius: 20px;
            animation: fadeIn 0.5s ease-out forwards; opacity: 0;
        }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(15px); } to { opacity: 1; transform: translateY(0); } }
        .control-section h2 { font-size: 22px; font-weight: 600; margin: 0 0 10px 0; letter-spacing: -0.5px; }
        .control-section .subtitle { font-size: 16px; color: var(--text-secondary); margin: -5px 0 25px 0; max-width: 600px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 25px; }
        .control-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 10px; font-weight: 500; color: var(--text-secondary); font-size: 14px; }
        select, button, input[type="text"], textarea {
            width: 100%; padding: 12px 14px; border-radius: 12px; border: 1px solid var(--border-color);
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
        .btn-primary { background: var(--blue); color: var(--text-primary); }
        .btn-success { background: var(--success); color: var(--text-primary); }
        .btn-danger { background: var(--danger); color: var(--text-primary); }
        .btn-secondary { background: var(--content-background-light); color: var(--text-primary); border: 1px solid var(--border-color); }
        #status-card {
            background: linear-gradient(135deg, var(--accent-secondary), var(--accent-primary)); padding: 25px;
            border-radius: 16px; color: var(--white);
        }
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
        dialog {
            width: 95%; max-width: 500px; border-radius: 20px; border: 1px solid var(--border-color);
            background: var(--background); color: var(--text-primary);
            box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5); padding: 30px;
            animation: dialog-in 0.4s cubic-bezier(0.16, 1, 0.3, 1);
        }
        dialog::backdrop { background-color: rgba(0,0,0,0.7); backdrop-filter: blur(8px); animation: backdrop-in 0.3s ease; }
        @keyframes dialog-in { from { opacity: 0; transform: translateY(30px) scale(0.95); } to { opacity: 1; transform: translateY(0) scale(1); } }
        @keyframes backdrop-in { from { opacity: 0; } to { opacity: 1; } }
        .modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 25px; }
        .toggle-switch { position: relative; display: inline-block; width: 50px; height: 28px; }
        .toggle-switch input { opacity: 0; width: 0; height: 0; }
        .slider {
            position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
            background-color: var(--content-background-light); transition: .4s; border-radius: 28px;
        }
        .slider:before {
            position: absolute; content: ""; height: 22px; width: 22px; left: 3px; bottom: 3px;
            background-color: white; transition: .4s cubic-bezier(0.16, 1, 0.3, 1); border-radius: 50%;
        }
        input:checked + .slider { background-color: var(--success); }
        input:checked + .slider:before { transform: translateX(22px); }
        .media-controls { display: flex; gap: 10px; align-items: center; }
        .media-controls button { width: 44px; height: 44px; padding: 0; font-size: 16px; flex-shrink: 0; }
        .volume-container { display: flex; align-items: center; background-color: #3A3A3C; border-radius: 12px; padding: 0 15px; flex-grow: 1; height: 44px; }
        #volume-slider { width: 100%; padding: 0; margin-left: 10px; background: transparent; border: none; }
        #volume-slider:focus { box-shadow: none; }
        input[type=range] { -webkit-appearance: none; background: transparent; cursor: pointer; }
        input[type=range]::-webkit-slider-runnable-track { height: 4px; background: var(--border-color); border-radius: 2px; }
        input[type=range]::-webkit-slider-thumb { -webkit-appearance: none; margin-top: -6px; width: 16px; height: 16px; background: var(--text-primary); border-radius: 50%; border: none; }
        #media-controls-container.disabled { opacity: 0.4; pointer-events: none; }

        /* NUOVO CSS PER L'ANTEPRIMA RIDIMENSIONATA E INTERATTIVA */
        .preview-wrapper {
            max-width: 720px; /* Imposta una larghezza massima per rimpicciolire */
            margin: 0 auto 20px auto; /* Centra l'anteprima e aggiunge spazio sotto */
        }
        .viewer-preview-container {
            position: relative;
            width: 100%;
            padding-top: 56.25%; /* Aspect Ratio 16:9 */
            background-color: #000;
            border-radius: 16px;
            overflow: hidden;
            border: 1px solid var(--border-color);
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }
        .viewer-preview-container iframe {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            border: 0;
        }
        .preview-controls {
            display: flex;
            justify-content: center;
            gap: 15px;
            flex-wrap: wrap;
        }
        .preview-controls .btn {
            width: auto;
            flex-shrink: 0;
        }
    </style>
</head>
<body>
    <div class="main-container">
        <header class="main-header">
            <div class="header-title">
                <img src="https://i.ibb.co/nN5WRrHS/LOGO-HARZAFI.png" alt="Logo Harzafi">
                <h1>Pannello</h1>
            </div>
            <div class="header-actions">
                <a href="{{ url_for('pagina_visualizzatore') }}" target="_blank" class="btn btn-viewer">Apri Visualizzatore</a>
                <a href="{{ url_for('logout') }}"><button id="logout-btn" class="btn">Logout</button></a>
            </div>
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
                    <button id="announce-btn" title="Annuncia" class="btn-primary" style="padding: 12px;">ANNUNCIA LINEA.</button>
                </div>
                
                <div class="control-group">
                    <label>Prenotazione Fermata</label>
                    <button id="booked-btn" class="btn-primary" style="padding: 12px;">PRENOTA FERMATA</button>
                </div>

            </div>
        </section>

        <section class="control-section">
            <h2>Anteprima Interattiva</h2>
            <p class="subtitle">Questa è un'anteprima live e interattiva. Puoi cliccare e interagire direttamente con gli elementi al suo interno.</p>
            <div class="preview-wrapper">
                <div class="viewer-preview-container">
                    <iframe id="viewer-iframe-preview" src="{{ url_for('pagina_visualizzatore') }}" frameborder="0"></iframe>
                </div>
            </div>
            <div class="preview-controls">
                <button id="toggle-preview-playback-btn" class="btn btn-secondary">▶ Riproduci in anteprima</button>
                <a href="{{ url_for('pagina_visualizzatore') }}" target="_blank" class="btn btn-secondary">Apri in Schermo Intero</a>
            </div>
        </section>
        
        <section class="control-section">
            <h2>Gestione Media e Messaggi</h2>
             <p class="subtitle">Carica contenuti video, controlla la riproduzione o imposta messaggi a scorrimento.</p>
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
                    
                    <button id="disable-media-btn" class="btn-secondary" style="margin-top: 10px; width: 100%;">DISATTIVARE CONTENUTI VIDEO</button>

                 </div>
                 <div>
                     <label for="info-messages-input">Messaggi a scorrimento (uno per riga)</label>
                     <textarea id="info-messages-input" placeholder="Benvenuti a bordo..."></textarea>
                     <button id="save-messages-btn" class="btn-primary" style="margin-top: 10px;">Salva Messaggi</button>
                 </div>
                 <div>
                    <label>Controlli Riproduzione (Globale)</label>
                    <div id="media-controls-container" class="media-controls">
                        <button id="seek-back-btn" class="btn-secondary" title="Indietro 5s">«</button>
                        <button id="play-pause-btn" class="btn-secondary" title="Play/Pausa">▶</button>
                        <button id="seek-fwd-btn" class="btn-secondary" title="Avanti 5s">»</button>
                        <div class="volume-container">
                            <span id="volume-icon">🔊</span>
                            <input type="range" id="volume-slider" min="0" max="1" step="0.05" value="1" title="Volume">
                        </div>
                    </div>
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
            mediaSource: localStorage.getItem('busSystem-mediaSource'),
            embedCode: localStorage.getItem('busSystem-embedCode'),
            videoName: localStorage.getItem('busSystem-videoName'),
            mediaLastUpdated: localStorage.getItem('busSystem-mediaLastUpdated'),
            volumeLevel: localStorage.getItem('busSystem-volumeLevel') || '1.0',
            playbackState: localStorage.getItem('busSystem-playbackState') || 'playing',
            seekAction: JSON.parse(localStorage.getItem('busSystem-seekAction') || 'null'),
            infoMessages: JSON.parse(localStorage.getItem('busSystem-infoMessages') || '[]'),
            serviceStatus: serviceStatus,
            announcement: JSON.parse(localStorage.getItem('busSystem-playAnnouncement') || 'null'),
            stopRequested: JSON.parse(localStorage.getItem('busSystem-stopRequested') || 'null')
        };
        socket.emit('update_all', state);
        // Reset one-time actions
        if (state.announcement) localStorage.removeItem('busSystem-playAnnouncement');
        if (state.stopRequested) localStorage.removeItem('busSystem-stopRequested');
        if (state.seekAction) localStorage.removeItem('busSystem-seekAction');
    }

    const importVideoBtn = document.getElementById('import-video-btn');
    const videoImporter = document.getElementById('video-importer');
    const importEmbedBtn = document.getElementById('import-embed-btn');
    const embedCodeInput = document.getElementById('embed-code-input');
    const removeMediaBtn = document.getElementById('remove-media-btn');
    const disableMediaBtn = document.getElementById('disable-media-btn'); 
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
    
    const bookedBtn = document.getElementById('booked-btn');

    // Media Controls
    const mediaControlsContainer = document.getElementById('media-controls-container');
    const playPauseBtn = document.getElementById('play-pause-btn');
    const volumeSlider = document.getElementById('volume-slider');
    const volumeIcon = document.getElementById('volume-icon');
    const seekBackBtn = document.getElementById('seek-back-btn');
    const seekFwdBtn = document.getElementById('seek-fwd-btn');

    let linesData = {}, currentLineKey = null, currentStopIndex = 0, serviceStatus = 'online';

    function getDefaultData() {
        return {
            "3": { "direction": "CORSA DEVIATA", "stops": [{ "name": "VALLETTE", "subtitle": "CAPOLINEA - TERMINAL" }, { "name": "PRIMULE", "subtitle": "" }, { "name": "PERVINCHE", "subtitle": "" }, { "name": "SANSOVINO", "subtitle": "" }, { "name": "CINCINNATO", "subtitle": "MERCATO RIONALE" }, { "name": "LOMBARDIA", "subtitle": "FERMATA PIU VICINA PER LA PISCINA LOMBARDIA" }, { "name": "BORSI", "subtitle": "" }, { "name": "LARGO TOSCANA", "subtitle": "" }, { "name": "LARGO BORGARO", "subtitle": "" }, { "name": "PIERO DELLA FRANCESCA", "subtitle": "FERMATA PIU VICINA PER IL MUSEO A COME AMBIENTE" }, { "name": "OSPEDALE AMEDEO DI SAVOIA", "subtitle": "UNIVERSITÀ - DIPARTIMENTO DI INFORMATICA" }, { "name": "TASSONI", "subtitle": "" }, { "name": "AVELLINO", "subtitle": "" }, { "name": "LIVORNO", "subtitle": "" }, { "name": "INDUSTRIA", "subtitle": "" }, { "name": "RONDÒ FORCA OVEST", "subtitle": "MARIA AUSILIATRICE" }, { "name": "OSPEDALE COTTOLENGO", "subtitle": "ANAGRAFE CENTRALE" }, { "name": "PORTA PALAZZO", "subtitle": "PIAZZA DELLA REPBLICA" }, { "name": "PORTA PALAZZO EST", "subtitle": "PIAZZA DELLA REPBLICA" }, { "name": "XI FEBBRAIO", "subtitle": "AUTOSTAZIONE DORA" }, { "name": "GIARDINI REALI", "subtitle": "RONDÒ RIVELLA" }, { "name": "ROSSINI", "subtitle": "MOLE ANTONELLIANA" }, { "name": "CAMPUS EINAUDI", "subtitle": "" }, { "name": "LARGO BERARDI", "subtitle": "" }, { "name": "OSPEDALE GRADENIGO", "subtitle": "" }, { "name": "TORTONA", "subtitle": "CAPOLINEA - TERMINAL" }] }
        };
    }

    // ===================================================================
    // !!! INIZIO CODICE CORRETTO !!!
    // Questa funzione ora controlla se i dati caricati sono vuoti
    // e, in caso affermativo, carica i dati predefiniti.
    // ===================================================================
    function loadData() {
        let loadedData = JSON.parse(localStorage.getItem('busSystem-linesData'));
        // SE I DATI MANCANO O SONO UN OGGETTO VUOTO, USA I PREDEFINITI
        if (!loadedData || Object.keys(loadedData).length === 0) {
            linesData = getDefaultData();
        } else {
            linesData = loadedData;
        }
        saveData(); // Salva lo stato (corretto o predefinito)
    }
    // ===================================================================
    // !!! FINE CODICE CORRETTO !!!
    // ===================================================================

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
        const hasMedia = mediaSource === 'embed' || (mediaSource === 'server' && videoName);
        
        mediaControlsContainer.classList.toggle('disabled', !hasMedia);

        if (mediaSource === 'embed') {
            mediaUploadStatusText.textContent = `Media da Embed attivo.`;
            removeMediaBtn.textContent = 'Rimuovi Media';
            removeMediaBtn.style.display = 'inline-block';
            disableMediaBtn.style.display = 'inline-block';
        } else if (mediaSource === 'server' && videoName) {
            mediaUploadStatusText.textContent = `Video locale: ${videoName}`;
            removeMediaBtn.textContent = 'Rimuovi Media';
            removeMediaBtn.style.display = 'inline-block';
            disableMediaBtn.style.display = 'inline-block';
        } else if (mediaSource === 'disabled') {
            mediaUploadStatusText.textContent = `Contenuti video disattivati.`;
            removeMediaBtn.textContent = 'Riattiva (pulisci stato)';
            removeMediaBtn.style.display = 'inline-block';
            disableMediaBtn.style.display = 'none';
        } else {
            mediaUploadStatusText.textContent = 'Nessun media caricato.';
            removeMediaBtn.style.display = 'none';
            disableMediaBtn.style.display = 'inline-block';
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
        } else { alert('Errore during the upload.'); }
        importVideoBtn.disabled = false; importVideoBtn.textContent = 'Importa Video Locale';
    }
    async function handleEmbedImport() {
        const rawCode = embedCodeInput.value.trim();
        if (!rawCode.includes('<iframe')) { alert('Codice <iframe> non valido.'); return; }
        await fetchAuthenticated('/clear-video', { method: 'POST' });
        const tempDiv = document.createElement('div'); tempDiv.innerHTML = rawCode;
        const iframe = tempDiv.querySelector('iframe'); if (!iframe) { alert('Tag <iframe> non trovato.'); return; }
        iframe.setAttribute('width', '100%'); iframe.setAttribute('height', '100%');
        iframe.setAttribute('style', 'position:absolute; top:0; left:0; width:100%; height:100%; border:0;');
        localStorage.setItem('busSystem-mediaSource', 'embed');
        localStorage.setItem('busSystem-embedCode', iframe.outerHTML);
        localStorage.removeItem('busSystem-videoName');
        localStorage.setItem('busSystem-mediaLastUpdated', Date.now());
        loadMediaStatus(); embedCodeInput.value = ''; sendFullStateUpdate();
    }
    
    async function removeMedia() {
        const mediaSource = localStorage.getItem('busSystem-mediaSource');
        const confirmMsg = (mediaSource === 'disabled') ? 
            'Vuoi riattivare il player? (Questo pulirà lo stato "disattivato")' : 
            'Rimuovere il media attuale?';
            
        if (!confirm(confirmMsg)) return;
        
        await fetchAuthenticated('/clear-video', { method: 'POST' });
        localStorage.removeItem('busSystem-mediaSource'); 
        localStorage.removeItem('busSystem-videoName');
        localStorage.removeItem('busSystem-embedCode');
        localStorage.setItem('busSystem-mediaLastUpdated', Date.now());
        loadMediaStatus(); sendFullStateUpdate();
    }
    
    async function disableMedia() {
        if (!confirm('Disattivare la riproduzione di tutti i contenuti video? Il player mostrerà un\'immagine "Non disponibile".')) return;
        await fetchAuthenticated('/clear-video', { method: 'POST' }); 
        localStorage.setItem('busSystem-mediaSource', 'disabled'); 
        localStorage.removeItem('busSystem-videoName');
        localStorage.removeItem('busSystem-embedCode');
        localStorage.setItem('busSystem-mediaLastUpdated', Date.now());
        loadMediaStatus();
        sendFullStateUpdate();
    }

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
    
    // --- FUNZIONE CON CORREZIONE ---
    function renderManagementPanel() {
        lineManagementList.innerHTML = '';
        Object.keys(linesData).sort().forEach(key => {
            const item = document.createElement('li');
            item.className = 'line-item';
            // --- ERRORE CORRETTO QUI ---
            // Era: </button</div>`
            // Ora: </button></div>` (aggiunto >)
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
    
    // --- Media Controls Logic ---
    function setupMediaControls() {
        const initialVolume = localStorage.getItem('busSystem-volumeLevel') || '1.0';
        const initialPlaybackState = localStorage.getItem('busSystem-playbackState') || 'playing';
        volumeSlider.value = initialVolume;
        updateVolumeIcon(initialVolume);
        playPauseBtn.innerHTML = initialPlaybackState === 'playing' ? '❚❚' : '▶';

        playPauseBtn.addEventListener('click', () => {
            let currentState = localStorage.getItem('busSystem-playbackState') || 'playing';
            const newState = currentState === 'playing' ? 'paused' : 'playing';
            localStorage.setItem('busSystem-playbackState', newState);
            playPauseBtn.innerHTML = newState === 'playing' ? '❚❚' : '▶';
            sendFullStateUpdate();
        });

        volumeSlider.addEventListener('input', () => {
            const newVolume = volumeSlider.value;
            localStorage.setItem('busSystem-volumeLevel', newVolume);
            updateVolumeIcon(newVolume);
            sendFullStateUpdate();
        });

        seekBackBtn.addEventListener('click', () => {
            localStorage.setItem('busSystem-seekAction', JSON.stringify({ value: -5, timestamp: Date.now() }));
            sendFullStateUpdate();
        });

        seekFwdBtn.addEventListener('click', () => {
            localStorage.setItem('busSystem-seekAction', JSON.stringify({ value: 5, timestamp: Date.now() }));
            sendFullStateUpdate();
        });
    }

    function updateVolumeIcon(volume) {
        const vol = parseFloat(volume);
        if (vol === 0) { volumeIcon.textContent = '🔇'; }
        else if (vol < 0.5) { volumeIcon.textContent = '🔈'; }
        else { volumeIcon.textContent = '🔊'; }
    }
    
    // --- NUOVA LOGICA PER CONTROLLO ANTEPRIMA ---
    function setupPreviewControls() {
        const previewIframe = document.getElementById('viewer-iframe-preview');
        const togglePlaybackBtn = document.getElementById('toggle-preview-playback-btn');
        let videoInIframe = null;

        const updateButtonState = () => {
            if (videoInIframe) {
                if (videoInIframe.paused) {
                    togglePlaybackBtn.textContent = '▶ Riproduci in anteprima';
                } else {
                    togglePlaybackBtn.textContent = '❚❚ Pausa in anteprima';
                }
            }
        };
        
        previewIframe.addEventListener('load', () => {
            try {
                const iframeDoc = previewIframe.contentDocument || previewIframe.contentWindow.document;
                videoInIframe = iframeDoc.getElementById('ad-video');
                const announcementAudio = iframeDoc.getElementById('announcement-sound');
                const bookedAudio = iframeDoc.getElementById('booked-sound-viewer');

                if (announcementAudio) announcementAudio.muted = true;
                if (bookedAudio) bookedAudio.muted = true;
                
                if (videoInIframe) {
                    videoInIframe.muted = true;
                    videoInIframe.pause();
                    
                    videoInIframe.addEventListener('play', updateButtonState);
                    videoInIframe.addEventListener('pause', updateButtonState);

                    togglePlaybackBtn.disabled = false;
                    updateButtonState();
                } else {
                    throw new Error("Elemento video non trovato.");
                }

            } catch (e) {
                console.warn("Contenuto iframe non accessibile. Controlli anteprima disabilitati.");
                togglePlaybackBtn.disabled = true;
                togglePlaybackBtn.textContent = 'Riproduzione non controllabile';
            }
        });

        togglePlaybackBtn.addEventListener('click', () => {
            if (videoInIframe && !togglePlaybackBtn.disabled) {
                if (videoInIframe.paused) {
                    videoInIframe.play();
                } else {
                    videoInIframe.pause();
                }
            }
        });
    }

    function initialize() {
        loadMediaStatus();
        setupMediaControls();
        setupPreviewControls();
        loadData();
        loadMessages();
        serviceStatus = 'online';
        saveServiceStatus();
        renderServiceStatus();
        currentLineKey = localStorage.getItem('busSystem-currentLine');
        currentStopIndex = parseInt(localStorage.getItem('busSystem-currentStopIndex'), 10) || 0;
        renderAll();
        updateAndRenderStatus();
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
    
    bookedBtn.addEventListener('click', () => {
        localStorage.setItem('busSystem-stopRequested', JSON.stringify({ timestamp: Date.now() }));
        sendFullStateUpdate();
        
        bookedBtn.textContent = 'PRENOTATA!';
        bookedBtn.classList.add('btn-danger');
        bookedBtn.classList.remove('btn-primary');
        bookedBtn.disabled = true;
        
        setTimeout(() => {
            bookedBtn.textContent = 'PRENOTA FERMATA';
            bookedBtn.classList.remove('btn-danger');
            bookedBtn.classList.add('btn-primary');
            bookedBtn.disabled = false;
        }, 2500); 
    });

    importVideoBtn.addEventListener('click', () => videoImporter.click());
    videoImporter.addEventListener('change', handleLocalVideoUpload);
    importEmbedBtn.addEventListener('click', handleEmbedImport);
    removeMediaBtn.addEventListener('click', removeMedia);
    disableMediaBtn.addEventListener('click', disableMedia); 
    addNewLineBtn.addEventListener('click', () => { document.getElementById('edit-line-id').value = ''; document.getElementById('modal-title').textContent = 'Aggiungi Nuova Linea'; lineEditorForm.reset(); stopsListContainer.innerHTML = ''; addStopToModal(); modal.showModal(); });
    
    lineManagementList.addEventListener('click', (e) => {
        const target = e.target.closest('button'); 
        if (!target) return; 
        const lineId = target.dataset.id;
        
        if (target.classList.contains('edit-btn')) {
            editLineId.value = lineId; 
            document.getElementById('modal-title').textContent = `Modifica Linea: ${lineId}`; 
            const line = linesData[lineId];
            lineNameInput.value = lineId; 
            lineDirectionInput.value = line.direction; 
            stopsListContainer.innerHTML = ''; 
            (line.stops || []).forEach(s => addStopToModal(s)); 
            modal.showModal();
        } 
        if (target.classList.contains('delete-btn')) { 
            if (confirm(`Eliminare la linea "${lineId}"?`)) { 
                delete linesData[lineId]; 
                saveData(); 
                renderAll(); 
            } 
        }
    });

    addStopBtn.addEventListener('click', () => addStopToModal());
    stopsListContainer.addEventListener('click', (e) => { if (e.target.classList.contains('remove-stop-btn')) { if (stopsListContainer.children.length > 1) e.target.parentElement.remove(); else alert('Ogni linea deve avere almeno una fermata.'); } });
    function addStopToModal(stop = { name: '', subtitle: '' }) {
        const stopItem = document.createElement('div'); stopItem.style.display='flex'; stopItem.style.gap='10px'; stopItem.style.marginBottom='10px';
        stopItem.innerHTML = `<input type="text" placeholder="Nome fermata" class="stop-name-input" value="${stop.name || ''}" required style="flex-grow:1;"><input type="text" placeholder="Sottotitolo (opz.)" class="stop-subtitle-input" value="${stop.subtitle || ''}" style="flex-grow:1;"><button type="button" class="btn-danger remove-stop-btn" style="width:auto; padding: 10px 12px;">-</button>`;
        stopsListContainer.appendChild(stopItem);
    }
    lineEditorForm.addEventListener('submit', (e) => {
        e.preventDefault(); const originalId = editLineId.value; const newId = lineNameInput.value.trim().toUpperCase(); const direction = lineDirectionInput.value.trim().toUpperCase();
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

# --- VISUALIZZATORE (Nessuna modifica necessaria, era corretto) ---
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
        
        /* Loader pagina (originale) */
        #loader {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
            z-index: 999; transition: opacity 0.8s ease;
        }
        #loader img {
            width: 250px; max-width: 70%; 
            animation: pulse-logo 2s infinite ease-in-out;
        }
        #loader p {
            margin-top: 25px; font-size: 1.2em; font-weight: 700; 
            text-transform: uppercase; letter-spacing: 1px; opacity: 0.9;
        }
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
        .direction-header { font-size: 24px; font-weight: 700; opacity: 0.8; margin: 0; text-transform: uppercase; }
        #direction-name { font-size: 56px; font-weight: 900; margin: 5px 0 60px 0; text-transform: uppercase; }
        .next-stop-header { font-size: 22px; font-weight: 700; opacity: 0.8; margin: 0; text-transform: uppercase; }
        #stop-name { font-size: 112px; font-weight: 900; margin: 0; line-height: 1.1; text-transform: uppercase; white-space: normal; opacity: 1; transform: translateY(0); transition: opacity 0.3s ease-out, transform 0.3s ease-out; }
        #stop-name.exit { opacity: 0; transform: translateY(-30px); transition: opacity 0.3s ease-in, transform 0.3s ease-in; }
        #stop-name.enter { animation: slideInFadeIn 0.5s ease-out forwards; }
        #stop-subtitle { font-size: 34px; font-weight: 400; margin: 10px 0 0 0; text-transform: uppercase; opacity: 0.9; }
        
        .logo {
            position: absolute; bottom: 40px; right: 50px; width: 220px; opacity: 0;
            filter: brightness(1.2) contrast(1.1); transition: opacity 0.8s ease;
        }
        .logo.visible { opacity: 0.9; }

        @keyframes slideInFadeIn { from { opacity: 0; transform: translateY(40px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes slideInFromTopFadeIn { from { opacity: 0; transform: translateX(-50%) translateY(-100px); } to { opacity: 1; transform: translateX(-50%) translateY(0); } }
        @keyframes slideInFromBottomFadeIn { from { opacity: 0; transform: translateX(-50%) translateY(100px); } to { opacity: 1; transform: translateX(-50%) translateY(0); } }
        
        /* Stile "Fuori Servizio" (testo) */
        #service-offline-overlay { 
            position: fixed; top: 0; left: 0; width: 100%; height: 100%; 
            z-index: 1000; display: flex; align-items: center; justify-content: center; 
            text-align: center; color: white; background-color: rgba(15, 23, 42, 0.6); 
            backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); 
            opacity: 0; pointer-events: none; 
        }
        #service-offline-overlay.visible { pointer-events: auto; animation: fadeInBlur 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards; }
        #service-offline-overlay.hiding { animation: fadeOutBlur 0.6s ease-out forwards; }
        #service-offline-overlay h2 { font-size: 5vw; font-weight: 900; margin: 0; text-shadow: 0 4px 20px rgba(0,0,0,0.4); }
        #service-offline-overlay p { font-size: 2vw; font-weight: 600; opacity: 0.9; margin-top: 15px; text-shadow: 0 2px 10px rgba(0,0,0,0.3); }
        
        @keyframes fadeInBlur { from { opacity: 0; } to { opacity: 1; } }
        @keyframes fadeOutBlur { from { opacity: 1; } to { opacity: 0; } }
        
        #video-player-container {
            width: 100%; max-width: 100%; background-color: transparent;
            border-radius: 25px; box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            overflow: hidden; display: flex; align-items: center; justify-content: center;
            position: relative;
            transition: opacity 0.5s ease, transform 0.5s ease;
        }
        #video-player-container::before {
            content: '';
            position: absolute;
            top: -30px; left: -30px; right: -30px; bottom: -30px;
            background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
            filter: blur(25px) brightness(0.7);
            z-index: 1;
        }
        #video-player-container iframe { border-radius: 25px; z-index: 2; }
        .aspect-ratio-16-9 { position: relative; width: 100%; height: 0; padding-top: 56.25%; }
        .placeholder-content {
            position: absolute; top: 0; left: 0; width: 100%; height: 100%;
            display: flex; flex-direction: column; align-items: center; justify-content: center; 
            text-align: center; padding: 20px; box-sizing: border-box; z-index: 2;
        }
        .placeholder-content img {
            width: 100%; height: 100%; object-fit: cover;
        }
        .placeholder-content.padded {
            padding: 0; overflow: hidden;
        }
        
        .video-background-blur {
            position: absolute; top: 0; left: 0; width: 100%; height: 100%;
            filter: blur(30px) brightness(0.7); transform: scale(1.15);
            opacity: 0.8; overflow: hidden; z-index: 3;
        }
        #ad-video-bg, #ad-video { width: 100%; height: 100%; position: absolute; top: 0; left: 0; }
        #ad-video-bg { object-fit: cover; }
        #ad-video { object-fit: contain; z-index: 4; }
        
        .box-enter-animation { animation: box-enter 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards; }
        .box-exit-animation { animation: box-exit 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards; }
        @keyframes box-enter { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); } }
        @keyframes box-exit { from { opacity: 1; transform: scale(1); } to { opacity: 0; transform: scale(0.95); } }
    </style>
</head>
<body>
    <audio id="announcement-sound" src="/announcement-audio" preload="auto"></audio>
    <audio id="booked-sound-viewer" src="{{ url_for('booked_stop_audio') }}" preload="auto" style="display:none;"></audio>

    <div id="loader">
        <img src="https://i.ibb.co/nN5WRrHS/LOGO-HARZAFI.png" alt="Logo Harzafi in caricamento">
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
        <div id="video-player-container" class="aspect-ratio-16-9" style="opacity: 0;"></div>
    </div>
    
    <img src="https://i.ibb.co/nN5WRrHS/LOGO-HARZAFI.png" alt="Logo Harzafi" class="logo">

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
    const announcementSound = document.getElementById('announcement-sound');
    const bookedSoundViewer = document.getElementById('booked-sound-viewer');

    let lastKnownState = {};

    function applyMediaState(state) {
        const videoEl = document.getElementById('ad-video');
        const videoBgEl = document.getElementById('ad-video-bg');
        if (!videoEl) return; // Se non c'è video (es. placeholder), non fare nulla

        const newVolume = parseFloat(state.volumeLevel);
        if (videoEl.volume !== newVolume) { videoEl.volume = newVolume; }

        if (state.playbackState === 'playing') {
            if (videoEl.paused) videoEl.play().catch(e => {});
            if (videoBgEl && videoBgEl.paused) videoBgEl.play().catch(e => {});
        } else if (state.playbackState === 'paused') {
            if (!videoEl.paused) videoEl.pause();
            if (videoBgEl && !videoBgEl.paused) videoBgEl.pause();
        }
        
        if (state.seekAction && state.seekAction.timestamp > (lastKnownState.seekAction?.timestamp || 0)) {
            const newTime = videoEl.currentTime + state.seekAction.value;
            const finalTime = Math.max(0, Math.min(newTime, isNaN(videoEl.duration) ? Infinity : videoEl.duration));
            videoEl.currentTime = finalTime;
            if (videoBgEl) {
                videoBgEl.currentTime = finalTime;
            }
        }
    }
    
    function loadMediaOrPlaceholder(state) {
        let newContent = '';
        let isLoadingMedia = false; 

        if (state.mediaSource === 'embed' && state.embedCode) {
            newContent = state.embedCode;
            isLoadingMedia = true;
        } else if (state.mediaSource === 'server') {
            const videoUrl = `/stream-video?t=${state.mediaLastUpdated}`;
            newContent = `
                <div class="video-background-blur">
                    <video id="ad-video-bg" loop playsinline muted src="${videoUrl}"></video>
                </div>
                <video id="ad-video" loop playsinline src="${videoUrl}"></video>`;
            isLoadingMedia = true;
        } else if (state.mediaSource === 'disabled') {
            // Stato "Disattivato"
            newContent = `<div class="placeholder-content padded">
                            <img src="https://i.ibb.co/Wv3zjPnG/Al-momento-non-disponibile-eseguire-contenuti.jpg" alt="Contenuti non disponibili">
                         </div>`;
            isLoadingMedia = false;
        } else {
            // Stato "Pronto" (nessun media)
            newContent = `<div class="placeholder-content padded">
                            <img src="https://i.ibb.co/1GnC8ZpN/Pronto-per-eseguire-contenuti-video.jpg" alt="Pronto per contenuti video">
                         </div>`;
            isLoadingMedia = false;
        }
        
        const loadingContent = `<div class="placeholder-content padded">
                                  <img src="https://i.ibb.co/WNL6KW51/Carico-Attendi.jpg" alt="Caricamento in corso...">
                                </div>`;

        videoPlayerContainer.classList.remove('box-enter-animation');
        videoPlayerContainer.classList.add('box-exit-animation');
        
        if (isLoadingMedia) {
            // --- FLUSSO MEDIA ---
            setTimeout(() => {
                videoPlayerContainer.innerHTML = loadingContent;
                videoPlayerContainer.classList.remove('box-exit-animation');
                videoPlayerContainer.classList.add('box-enter-animation');
            }, 500); 

            setTimeout(() => {
                videoPlayerContainer.classList.remove('box-enter-animation');
                videoPlayerContainer.classList.add('box-exit-animation');
            }, 1500); 

            setTimeout(() => {
                videoPlayerContainer.innerHTML = newContent;
                videoPlayerContainer.classList.remove('box-exit-animation');
                videoPlayerContainer.classList.add('box-enter-animation');
                applyMediaState(state); 
            }, 2000); 

        } else {
            // --- FLUSSO PLACEHOLDER ("Pronto" o "Disattivato") ---
            setTimeout(() => {
                videoPlayerContainer.innerHTML = newContent;
                videoPlayerContainer.classList.remove('box-exit-animation');
                videoPlayerContainer.classList.add('box-enter-animation');
                // Rimosso applyMediaState(state) perché qui non c'è <video>
            }, 500);
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

    function playAnnouncement() {
        const videoEl = document.getElementById('ad-video');
        const originalVolume = parseFloat(lastKnownState.volumeLevel || 1.0);
        
        if (videoEl && !videoEl.muted) {
            videoEl.volume = Math.min(originalVolume, 0.15);
        }
        
        announcementSound.currentTime = 0;
        announcementSound.play().catch(e => console.error("Errore riproduzione annuncio:", e));
        
        announcementSound.onended = () => {
            if (videoEl) {
                videoEl.volume = originalVolume;
            }
        };
    }

    function adjustFontSize(element) {
        const maxFontSize = 112; const minFontSize = 40;
        element.style.fontSize = maxFontSize + 'px'; let currentFontSize = maxFontSize;
        while ((element.scrollWidth > element.parentElement.clientWidth || element.scrollHeight > element.parentElement.clientHeight) && currentFontSize > minFontSize) {
            currentFontSize -= 2; element.style.fontSize = currentFontSize + 'px';
        }
    }

    function checkServiceStatus(state) {
        const isOffline = state.serviceStatus === 'offline';
        const isVisible = serviceOfflineOverlay.classList.contains('visible');

        if (isOffline && !isVisible) {
            serviceOfflineOverlay.classList.remove('hiding');
            serviceOfflineOverlay.classList.add('visible');
        } else if (!isOffline && isVisible) {
            serviceOfflineOverlay.classList.add('hiding');
            serviceOfflineOverlay.addEventListener('animationend', () => {
                if (serviceOfflineOverlay.classList.contains('hiding')) {
                   serviceOfflineOverlay.classList.remove('visible', 'hiding');
                }
            }, { once: true });
        } else if (isOffline && isVisible) {
             serviceOfflineOverlay.classList.remove('hiding');
        }
        return !isOffline;
    }
    
    function updateDisplay(state) {
        if (!checkServiceStatus(state) || !state.linesData || !state.currentLineKey) {
            return;
        }

        const isInitialLoad = !lastKnownState.currentLineKey;
        const lineChanged = lastKnownState.currentLineKey !== state.currentLineKey;
        const stopIndexChanged = lastKnownState.currentStopIndex !== state.currentStopIndex;
        const mediaChanged = state.mediaLastUpdated > (lastKnownState.mediaLastUpdated || 0);

        loaderEl.classList.add('hidden');
        containerEl.classList.add('visible');
        logoEl.classList.add('visible');
        if (isInitialLoad) {
            videoPlayerContainer.style.opacity = '1';
            videoPlayerContainer.classList.add('box-enter-animation');
        }

        const line = state.linesData[state.currentLineKey];
        if (!line) return;
        const stop = line.stops[state.currentStopIndex];
        
        const updateContent = () => {
            lineIdEl.textContent = state.currentLineKey;
            directionNameEl.textContent = line.direction;
            stopNameEl.textContent = stop ? stop.name : 'CAPOLINEA';
            stopSubtitleEl.textContent = stop ? (stop.subtitle || '') : '';
            adjustFontSize(stopNameEl);
        };

        if (!isInitialLoad && (lineChanged || stopIndexChanged)) {
            const direction = (!isInitialLoad && stopIndexChanged && state.currentStopIndex < lastKnownState.currentStopIndex) ? 'prev' : 'next';
            stopIndicatorEl.className = 'current-stop-indicator exit';
            stopNameEl.className = 'exit';
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
            }, 400);
        } else {
            updateContent();
        }

        if (state.announcement && state.announcement.timestamp > (lastKnownState.announcement?.timestamp || 0)) {
            playAnnouncement();
        }

        if (state.stopRequested && state.stopRequested.timestamp > (lastKnownState.stopRequested?.timestamp || 0)) {
            if (bookedSoundViewer) {
                bookedSoundViewer.currentTime = 0;
                bookedSoundViewer.play().catch(e => console.error("Errore riproduzione 'bip' prenotazione:", e));
            }
        }

        // --- LOGICA MEDIA CORRETTA ---
        if (isInitialLoad || mediaChanged) {
            loadMediaOrPlaceholder(state);
        } else if (state.mediaSource === 'server' || state.mediaSource === 'embed') {
            // Se il media NON è cambiato (es. cambio fermata) E c'è un video attivo,
            // applica solo lo stato (volume, play/pausa, seek).
            applyMediaState(state);
        }
        // Se non c'è media (Pronto/Disattivato) e il media non è cambiato, non fare nulla.
        
        lastKnownState = JSON.parse(JSON.stringify(state));
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

    if form.validate_on_submit():
        username = form.username.data

        if username in login_attempts:
            attempt_info = login_attempts[username]
            if attempt_info['attempts'] >= MAX_ATTEMPTS:
                lockout_end_time = attempt_info['time'] + timedelta(minutes=LOCKOUT_TIME_MINUTES)
                if datetime.now() < lockout_end_time:
                    remaining_time = round((lockout_end_time - datetime.now()).total_seconds())
                    flash(f"Troppi tentativi falliti. Riprova tra {remaining_time} secondi.", "error")
                    return render_template_string(LOGIN_PAGE_HTML, form=form)
                else:
                    login_attempts.pop(username, None)

        user_in_db = USERS_DB.get(username)
        if user_in_db and check_password_hash(user_in_db['password_hash'], form.password.data):
            login_attempts.pop(username, None)
            user = get_user(username)
            login_user(user)
            return redirect(request.args.get('next') or url_for('dashboard'))
        else:
            if username not in login_attempts:
                login_attempts[username] = {'attempts': 0, 'time': None}
            
            login_attempts[username]['attempts'] += 1
            login_attempts[username]['time'] = datetime.now()

            remaining = MAX_ATTEMPTS - login_attempts[username]['attempts']
            if remaining > 0:
                flash(f"Credenziali non valide. Hai ancora {remaining} tentativi.", "error")
            else:
                flash(f"Account bloccato per {LOCKOUT_TIME_MINUTES} minuti.", "error")
            
            return render_template_string(LOGIN_PAGE_HTML, form=form)
    
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

@app.route('/booked-stop-audio')
@login_required
def booked_stop_audio():
    try:
        return send_file('bip.mp3', mimetype='audio/mpeg')
    except FileNotFoundError:
        print("ERRORE CRITICO: Il file 'bip.mp3' non è stato trovato!")
        return Response("File audio di prenotazione non trovato sul server.", status=404)

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

# -------------------------------------------------------------------
# !!! INIZIO CODICE CORRETTO !!!
# GESTIONE WEBSOCKET (CORRETTA)
# -------------------------------------------------------------------

@socketio.on('connect')
def handle_connect():
    if not current_user.is_authenticated: return False
    print(f"Client autorizzato connesso: {current_user.name} ({request.sid})")
    global current_app_state # AGGIUNTA PER GESTIRE IL CASO INIZIALE
    # CORREZIONE: Invia uno stato iniziale (anche vuoto)
    if current_app_state: 
        socketio.emit('initial_state', current_app_state, room=request.sid)
    else:
        # Questo sblocca il visualizzatore anche se il pannello
        # non ha mai inviato dati.
        socketio.emit('initial_state', {}, room=request.sid)

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
    # CORREZIONE: Invia uno stato iniziale (anche vuoto)
    if current_app_state: 
        socketio.emit('initial_state', current_app_state, room=request.sid)
    else:
        socketio.emit('initial_state', {}, room=request.sid)
# -------------------------------------------------------------------
# !!! FINE CODICE CORRETTO !!!
# -------------------------------------------------------------------


# -------------------------------------------------------------------
# 5. BLOCCO DI ESECUZIONE (Rimosso per il deploy con Gunicorn)
# -------------------------------------------------------------------

# L'applicazione verrà eseguita da Gunicorn utilizzando l'oggetto 'app'.
# La sezione 'if __name__ == '__main__': ...' è stata rimossa per evitare
# conflitti in produzione.

# Se vuoi eseguire in locale per test, puoi usare:
# socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)

# L'istruzione che segue è solo per dare visibilità all'IP locale
# in caso di esecuzione manuale in un terminale standard.
try:
    if sys.argv[0] == 'app.py' or sys.argv[0].endswith('gunicorn'):
        local_ip = get_local_ip()
        print("===================================================================")
        print("   SERVER HARZAFI v10 (SOLUZIONE DEFINITIVA WEBSOCKET)")
        print("===================================================================")
        print(f"Login: http://127.0.0.1:5000/login  |  http://{local_ip}:5000/login")
        print("Credenziali di default: admin / adminpass")
        print("===================================================================")
except:
    pass

# Fine del file. Gunicorn prenderà l'oggetto 'app'.
