--- START OF FILE app.py ---
import sys
import socket
import re
import os # Importato per gestire i file
import tempfile # Importato per gestire i file temporanei
from functools import wraps
from datetime import datetime, timedelta
from flask import Flask, Response, request, abort, jsonify, render_template_string, redirect, url_for, flash, send_file
from flask_socketio import SocketIO
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
IMPORTANTE: Assicurati di aver installato Flask-WTF con "pip install Flask-WTF"
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField
from wtforms.validators import DataRequired
-------------------------------------------------------------------
SEZIONE CONFIGURAZIONE SICUREZZA POTENZIATA E LOGIN
-------------------------------------------------------------------
SECRET_KEY_FLASK = "questa-chiave-e-stata-cambiata-ed-e-molto-piu-sicura-del-2025-vetro-liquido-v2"
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
def init(self, id, name):
self.id = id
self.name = name
def get_user(user_id):
if user_id in USERS_DB:
return User(id=user_id, name=USERS_DB[user_id]["name"])
return None
class LoginForm(FlaskForm):
username = StringField('Username', validators=[DataRequired("Il nome utente è obbligatorio.")])
password = PasswordField('Password', validators=[DataRequired("La password è obbligatoria.")])
-------------------------------------------------------------------
1. IMPOSTAZIONI E APPLICAZIONE
-------------------------------------------------------------------
app = Flask(name)
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
-------------------------------------------------------------------
2. STATO GLOBALE DELL'APPLICAZIONE
-------------------------------------------------------------------
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
-------------------------------------------------------------------
3. TEMPLATE HTML INTEGRATI
-------------------------------------------------------------------
--- PAGINA DI LOGIN ---
LOGIN_PAGE_HTML = """
<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Accesso Riservato - Pannello Harzafi</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>
:root { --background-start: #111827; --background-end: #1F2937; --card-background: rgba(31, 41, 55, 0.8); --border-color: rgba(107, 114, 128, 0.2); --accent-color-start: #8A2387; --accent-color-end: #A244A7; --text-primary: #F9FAFB; --text-secondary: #9CA3AF; --danger-color: #EF4444; }
* { box-sizing: border-box; }
body { font-family: 'Inter', sans-serif; background: linear-gradient(135deg, var(--background-start), var(--background-end)); color: var(--text-primary); display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; }
.login-container { width: 100%; max-width: 420px; background: var(--card-background); border: 1px solid var(--border-color); padding: 40px; border-radius: 24px; box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.4); backdrop-filter: blur(10px); text-align: center; }
.logo { max-width: 150px; margin-bottom: 24px; filter: drop-shadow(0 0 15px rgba(255, 255, 255, 0.1)); }
h2 { color: var(--text-primary); font-weight: 700; font-size: 24px; margin: 0 0 32px 0; }
.flash-message { padding: 12px 15px; border-radius: 12px; margin-bottom: 20px; border: 1px solid; font-weight: 600; display: flex; align-items: center; gap: 10px; }
.flash-message.error { background-color: rgba(239, 68, 68, 0.1); color: var(--danger-color); border-color: rgba(239, 68, 68, 0.3); }
.form-group { margin-bottom: 20px; text-align: left; }
label { display: block; margin-bottom: 8px; font-weight: 600; color: var(--text-secondary); font-size: 14px; }
input { width: 100%; padding: 14px 16px; border-radius: 12px; border: 1px solid var(--border-color); background-color: #111827; color: var(--text-primary); font-size: 16px; }
input:focus { outline: none; border-color: var(--accent-color-end); box-shadow: 0 0 0 4px rgba(162, 68, 167, 0.2); }
button[type="submit"] { width: 100%; padding: 15px; border: none; background: linear-gradient(135deg, var(--accent-color-end), var(--accent-color-start)); color: white; font-size: 16px; font-weight: 700; border-radius: 12px; cursor: pointer; transition: transform 0.2s, box-shadow 0.2s; }
button[type="submit"]:hover { transform: translateY(-3px); box-shadow: 0 10px 20px rgba(138, 35, 135, 0.25); }
</style>
</head>
<body>
<div class="login-container">
<img src="https://i.ibb.co/nN5WRrHS/LOGO-HARZAFI.png" alt="Logo Harzafi" class="logo">
<h2>Accesso Area Riservata</h2>
{% with messages = get_flashed_messages(with_categories=true) %}
{% if messages %}
{% for category, message in messages %}
<div class="flash-message {{ category }}"><span>{{ message }}</span></div>
{% endfor %}
{% endif %}
{% endwith %}
<form method="post" novalidate>
{{ form.hidden_tag() }}
<div class="form-group">{{ form.username.label(for="username") }} {{ form.username(id="username", class="form-control", required=True) }}</div>
<div class="form-group">{{ form.password.label(for="password") }} {{ form.password(id="password", class="form-control", required=True) }}</div>
<button type="submit">Accedi</button>
</form>
</div>
</body>
</html>
"""
--- PANNELLO DI CONTROLLO (Invariato nella logica, uguale al precedente) ---
PANNELLO_CONTROLLO_COMPLETO_HTML = """
<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pannello di Controllo Harzafi</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
<style>
:root { --background: #000000; --content-background: #1D1D1F; --content-background-light: #2C2C2E; --border-color: #3A3A3C; --text-primary: #F5F5F7; --text-secondary: #86868B; --accent-primary: #A244A7; --accent-secondary: #8A2387; --success: #30D158; --danger: #FF453A; --blue: #0A84FF; }
body { font-family: 'Inter', sans-serif; background: var(--background); color: var(--text-primary); margin: 0; padding: 20px; overflow-y: scroll; }
.main-container { max-width: 1200px; margin: 0 auto; display: flex; flex-direction: column; gap: 40px; }
.main-header { display: flex; justify-content: space-between; align-items: center; padding: 20px 0; border-bottom: 1px solid var(--border-color); }
.header-title { display: flex; align-items: center; gap: 15px; } .header-title img { max-width: 100px; } .header-title h1 { font-size: 28px; font-weight: 700; margin: 0; }
.btn { padding: 8px 16px; border-radius: 99px; font-weight: 600; cursor: pointer; text-decoration: none; display: inline-block; }
.btn-viewer { background: var(--blue); color: white; border: 1px solid var(--blue); }
.control-section { background: var(--content-background); padding: 30px; border-radius: 20px; margin-bottom: 20px; }
.control-section h2 { font-size: 22px; margin-top: 0; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 25px; }
label { display: block; margin-bottom: 10px; font-weight: 500; color: var(--text-secondary); }
select, input[type="text"], textarea { width: 100%; padding: 12px; border-radius: 12px; border: 1px solid var(--border-color); background: var(--content-background-light); color: var(--text-primary); }
button { cursor: pointer; padding: 12px; border: none; font-weight: 600; border-radius: 12px; margin-top: 5px; }
.btn-primary { background: var(--blue); color: white; }
.btn-success { background: var(--success); color: white; }
.btn-danger { background: var(--danger); color: white; }
.btn-secondary { background: var(--content-background-light); color: white; border: 1px solid var(--border-color); }
#status-card { background: linear-gradient(135deg, var(--accent-secondary), var(--accent-primary)); padding: 25px; border-radius: 16px; color: white; }
.line-item { display: flex; justify-content: space-between; padding: 10px; background: var(--content-background-light); margin-bottom: 5px; border-radius: 8px; align-items: center; }
.line-actions button { margin-left: 5px; padding: 5px 10px; font-size: 12px; }
.preview-wrapper { max-width: 720px; margin: 0 auto; }
.viewer-preview-container { position: relative; width: 100%; padding-top: 56.25%; background-color: #000; border-radius: 16px; overflow: hidden; border: 1px solid var(--border-color); }
.viewer-preview-container iframe { position: absolute; top: 0; left: 0; width: 100%; height: 100%; border: 0; }
code
Code
.stop-item { display: flex; gap: 10px; margin-bottom: 10px; align-items: center; }
    .audio-upload-btn { width: 40px !important; height: 40px; padding: 8px !important; flex-shrink: 0; border-radius: 50% !important; line-height: 1; border: 2px solid; display: flex; align-items: center; justify-content: center; }
    .audio-upload-btn.status-red { background-color: var(--danger); color: white; } .audio-upload-btn.status-green { background-color: var(--success); color: white; }
    .remove-stop-btn { width: 40px; height: 40px; padding: 0 !important; }
    dialog { border-radius: 20px; border: 1px solid var(--border-color); background: var(--background); color: var(--text-primary); padding: 30px; width: 95%; max-width: 600px; }
    dialog::backdrop { background-color: rgba(0,0,0,0.7); backdrop-filter: blur(5px); }
</style>
</head>
<body>
<div class="main-container">
<header class="main-header">
<div class="header-title"><img src="https://i.ibb.co/nN5WRrHS/LOGO-HARZAFI.png" alt="Logo"><h1>Pannello</h1></div>
<a href="{{ url_for('pagina_visualizzatore') }}" target="_blank" class="btn btn-viewer">Apri Visualizzatore</a>
</header>
code
Code
<section class="control-section">
        <div class="grid">
            <div>
                <h2>Stato Attuale</h2>
                <div id="status-card">
                    <h3>Fermata: <span id="status-progress">--/--</span></h3>
                    <h1 id="status-stop-name" style="font-size: 28px; margin: 10px 0;">--</h1>
                    <p id="status-line-name">Nessuna Linea</p>
                </div>
            </div>
            <div>
                 <label>Controlli Linea</label>
                 <select id="line-selector" style="margin-bottom: 15px;"></select>
                 <div style="display: flex; gap: 10px; margin-bottom: 15px;">
                    <button id="prev-btn" class="btn-secondary" style="flex:1;">Precedente</button>
                    <button id="next-btn" class="btn-secondary" style="flex:1;">Successiva</button>
                 </div>
                 <button id="announce-btn" class="btn-primary" style="width:100%;">ANNUNCIA LINEA</button>
                 <button id="booked-btn" class="btn-primary" style="width:100%; margin-top: 10px;">PRENOTA FERMATA</button>
            </div>
        </div>
    </section>

    <section class="control-section">
         <h2>Gestione Messaggi & Media</h2>
         <div class="grid">
            <div>
                <label>Messaggi a scorrimento (uno per riga)</label>
                <textarea id="info-messages-input" style="min-height: 100px;"></textarea>
                <button id="save-messages-btn" class="btn-primary">Aggiorna Barra Info</button>
            </div>
            <div>
                <label>Importazione Media</label>
                <input type="file" id="video-importer" accept="video/*" style="display: none;">
                <button id="import-video-btn" class="btn-secondary">Carica Video (MP4)</button>
                <button id="remove-media-btn" class="btn-danger" style="margin-top: 5px;">Rimuovi Media</button>
                <div style="margin-top: 15px; border-top: 1px solid var(--border-color); padding-top: 10px;">
                    <label>Embed Youtube/Web</label>
                    <textarea id="embed-code-input" placeholder="Codice iframe..." style="min-height: 60px;"></textarea>
                    <button id="import-embed-btn" class="btn-secondary">Imposta Embed</button>
                </div>
            </div>
         </div>
    </section>

    <section class="control-section">
        <h2>Anteprima</h2>
        <div class="preview-wrapper">
            <div class="viewer-preview-container">
                <iframe id="viewer-iframe-preview" src="{{ url_for('pagina_visualizzatore') }}" frameborder="0"></iframe>
            </div>
        </div>
    </section>

    <section class="control-section">
        <h2>Editor Linee</h2>
        <button id="add-new-line-btn" class="btn-success">Aggiungi Nuova Linea</button>
        <div id="line-management-list" style="margin-top: 20px;"></div>
    </section>
</div>

<dialog id="line-editor-modal">
    <h2 id="modal-title">Modifica Linea</h2>
    <form id="line-editor-form">
        <input type="hidden" id="edit-line-id">
        <label>Nome Linea (es. 3)</label><input type="text" id="line-name" required style="margin-bottom: 15px;">
        <label>Destinazione</label><input type="text" id="line-direction" required style="margin-bottom: 15px;">
        <div id="stops-editor">
            <label>Elenco Fermate</label>
            <div id="stops-list" style="max-height: 250px; overflow-y: auto; padding-right: 5px;"></div>
            <button type="button" id="add-stop-btn" class="btn-secondary" style="width: 100%;">+ Aggiungi Fermata</button>
        </div>
        <div style="margin-top: 20px; text-align: right; display: flex; gap: 10px; justify-content: flex-end;">
            <button type="button" id="cancel-btn" class="btn-secondary">Annulla</button>
            <button type="submit" class="btn-primary">Salva</button>
        </div>
    </form>
</dialog>
<script>
const socket = io();
// Elementi
const lineSelector = document.getElementById('line-selector');
const infoMessagesInput = document.getElementById('info-messages-input');
const saveMessagesBtn = document.getElementById('save-messages-btn');
const stopsListContainer = document.getElementById('stops-list');

// Icone SVG
const iconMicRed = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M12 14c1.66 0 2.99-1.34 2.99-3L15 5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm-1.2-9.1c0-.66.54-1.2 1.2-1.2.66 0 1.2.54 1.2 1.2l-.01 6.2c0 .66-.53 1.2-1.19 1.2s-1.2-.54-1.2-1.2V4.9zM19 11h-1.7c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.49 6-3.31 6-6.72z"/></svg>';
const iconMicGreen = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M12 14c1.66 0 2.99-1.34 2.99-3L15 5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zM12 17.3c-3 0-5.3-2.1-5.3-5.1H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.49 6-3.31 6-6.72h-1.7c0-3-2.54-5.1-5.3-5.1z"/></svg>';

let linesData = {}, currentLineKey = null, currentStopIndex = 0;

// Inizializzazione dati
function getDefaultData() { return {"3": { "direction": "CORSA DEVIATA", "stops": [{ "name": "VALLETTE", "subtitle": "CAPOLINEA", "audio": null }] }}; }
function loadData() { linesData = JSON.parse(localStorage.getItem('busSystem-linesData')) || getDefaultData(); updateUI(); }
function saveData() { localStorage.setItem('busSystem-linesData', JSON.stringify(linesData)); sendState(); }

function updateUI() {
lineSelector.innerHTML = '';
Object.keys(linesData).forEach(key => {
let opt = document.createElement('option');
opt.value = key; opt.text = key + " -> " + linesData[key].direction;
lineSelector.add(opt);
});
if(currentLineKey) lineSelector.value = currentLineKey;
renderLineList();
}

function sendState() {
socket.emit('update_all', {
linesData: linesData,
currentLineKey: currentLineKey,
currentStopIndex: currentStopIndex,
infoMessages: infoMessagesInput.value.split('\\n').filter(x => x.trim() !== '')
});
}

// Gestori eventi principali
saveMessagesBtn.onclick = () => { saveData(); sendState(); alert('Barra aggiornata!'); };

lineSelector.onchange = (e) => {
currentLineKey = e.target.value;
currentStopIndex = 0;
localStorage.setItem('busSystem-currentLine', currentLineKey);
sendState();
};

document.getElementById('prev-btn').onclick = () => { if(currentStopIndex > 0) { currentStopIndex--; sendState(); } };
document.getElementById('next-btn').onclick = () => { if(linesData[currentLineKey] && currentStopIndex < linesData[currentLineKey].stops.length - 1) { currentStopIndex++; sendState(); } };

document.getElementById('announce-btn').onclick = () => {
socket.emit('update_all', { announcement: { timestamp: Date.now() } });
};
document.getElementById('booked-btn').onclick = () => {
socket.emit('update_all', { stopRequested: { timestamp: Date.now() } });
};

// Logica Modale e Upload
document.getElementById('line-editor-form').onsubmit = (e) => {
e.preventDefault();
const id = document.getElementById('line-name').value.toUpperCase();
const stops = Array.from(document.querySelectorAll('.stop-item')).map(item => ({
name: item.querySelector('.stop-name-input').value,
subtitle: item.querySelector('.stop-subtitle-input').value,
audio: item.dataset.audio || null
}));

linesData[id] = { direction: document.getElementById('line-direction').value, stops: stops };
saveData();
document.getElementById('line-editor-modal').close();
};

function addStopToModal(stop={name:'', subtitle:'', audio: null}) {
let d = document.createElement('div'); d.className='stop-item';
d.dataset.audio = stop.audio || "";
d.innerHTML = `
<input type="file" hidden onchange="handleAudio(this)">
<button type="button" class="audio-upload-btn ${stop.audio?'status-green':'status-red'}" onclick="this.previousElementSibling.click()">${stop.audio?iconMicGreen:iconMicRed}</button>
<input type="text" class="stop-name-input" value="${stop.name}" placeholder="Nome">
<input type="text" class="stop-subtitle-input" value="${stop.subtitle}" placeholder="Sottotitolo">
<button type="button" class="remove-stop-btn btn-danger" onclick="this.parentElement.remove()">-</button>
`;
stopsListContainer.appendChild(d);
}

window.handleAudio = function(input) {
if(input.files[0]) {
let r = new FileReader();
r.onload = (e) => {
input.parentElement.dataset.audio = e.target.result;
let btn = input.nextElementSibling;
btn.classList.remove('status-red'); btn.classList.add('status-green');
btn.innerHTML = iconMicGreen;
};
r.readAsDataURL(input.files[0]);
}
};

document.getElementById('add-stop-btn').onclick = () => addStopToModal();
document.getElementById('add-new-line-btn').onclick = () => { stopsListContainer.innerHTML=''; addStopToModal(); document.getElementById('line-editor-modal').showModal(); };
document.getElementById('cancel-btn').onclick = () => document.getElementById('line-editor-modal').close();

function renderLineList() {
let list = document.getElementById('line-management-list');
list.innerHTML = '';
for(let k in linesData) {
list.innerHTML += `<div class="line-item"><b>${k}</b> <div class="line-actions"><button class="btn-secondary" onclick="editLine('${k}')">Modifica</button><button class="btn-danger" onclick="deleteLine('${k}')">Elimina</button></div></div>`;
}
}

window.editLine = (key) => {
let l = linesData[key];
document.getElementById('line-name').value = key;
document.getElementById('line-direction').value = l.direction;
stopsListContainer.innerHTML='';
l.stops.forEach(s => addStopToModal(s));
document.getElementById('line-editor-modal').showModal();
};

window.deleteLine = (key) => {
if(confirm('Cancellare linea?')) { delete linesData[key]; saveData(); }
};

// Video Import logic (semplificata per brevità)
document.getElementById('import-video-btn').onclick = () => document.getElementById('video-importer').click();
document.getElementById('video-importer').onchange = async (e) => {
let f = new FormData(); f.append('video', e.target.files[0]);
await fetch('/upload-video', { method: 'POST', body: f });
localStorage.setItem('busSystem-mediaSource', 'server');
localStorage.setItem('busSystem-mediaLastUpdated', Date.now());
sendState();
};
document.getElementById('remove-media-btn').onclick = async () => {
await fetch('/clear-video', {method:'POST'});
localStorage.removeItem('busSystem-mediaSource');
sendState();
};

// Inizializza
loadData();
// Recupera messaggi
if(localStorage.getItem('busSystem-infoMessages')) {
infoMessagesInput.value = JSON.parse(localStorage.getItem('busSystem-infoMessages')).join('\\n');
}
</script>
</body>
</html>
"""
--- VISUALIZZATORE CON NUOVA BARRA LIQUID GLASS KIT ---
VISUALIZZATORE_COMPLETO_HTML = """
<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Visualizzazione Fermata Harzafi</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700;800;900&display=swap" rel="stylesheet">
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
overflow: hidden;
display: flex; flex-direction: column;
}
code
Code
/* LAYOUT PRINCIPALE */
    .content-area {
        flex-grow: 1; /* Occupa tutto lo spazio tranne la barra */
        display: flex;
        align-items: center; /* Centra verticalmente il contenuto */
        justify-content: center;
        padding-bottom: 120px; /* Spazio per la barra Liquid Glass */
        width: 100%;
    }

    .main-content-row {
        display: flex; align-items: center; justify-content: center; width: 100%;
        max-width: 1600px; padding: 0 40px; box-sizing: border-box;
    }
    
    /* VIDEO E LINEA (CSS Originale Mantenuto e Migliorato) */
    .line-graphic {
        flex-shrink: 0; width: 140px; height: 500px; display: flex;
        flex-direction: column; align-items: center; position: relative;
        justify-content: center; margin-right: 30px;
    }
    .line-graphic::before {
        content: ''; position: absolute; top: 15%; left: 50%; transform: translateX(-50%);
        width: 12px; height: 85%; background-color: rgba(255, 255, 255, 0.3);
        border-radius: 6px; z-index: 1;
    }
    .line-id-container {
        width: 110px; height: 110px; background-color: var(--main-text-color);
        border-radius: 50%; display: flex; align-items: center; justify-content: center;
        z-index: 2; box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        border: 5px solid var(--gradient-end); position: absolute; top: 5%;
    }
    #line-id { font-size: 52px; font-weight: 900; color: var(--line-color); }
    .current-stop-indicator {
        width: 60px; height: 60px; background-color: var(--main-text-color);
        border-radius: 14px; z-index: 2; position: absolute; bottom: 35%;
        left: 50%; transform: translateX(-50%);
        box-shadow: 0 0 25px rgba(255,255,255,0.8);
    }
    
    /* Info Testuali (Sinistra del video) */
    .text-content { flex: 1; padding-left: 20px; min-width: 300px; text-shadow: 0 4px 10px rgba(0,0,0,0.2); }
    .direction-header { font-size: 22px; font-weight: 700; opacity: 0.8; margin: 0; text-transform: uppercase; letter-spacing: 1px; }
    #direction-name { font-size: 48px; font-weight: 900; margin: 5px 0 50px 0; text-transform: uppercase; line-height: 1.1; }
    .next-stop-header { font-size: 20px; font-weight: 700; opacity: 0.8; margin: 0; text-transform: uppercase; letter-spacing: 1px; }
    #stop-name { font-size: 90px; font-weight: 900; margin: 0; line-height: 1; text-transform: uppercase; white-space: normal; }
    #stop-subtitle { font-size: 30px; font-weight: 500; margin: 10px 0 0 0; text-transform: uppercase; opacity: 0.9; }

    /* Contenitore Video (Destra) */
    .video-wrapper { flex: 1.5; padding: 20px; box-sizing: border-box; display: flex; justify-content: flex-end; }
    #video-player-container {
        width: 100%; aspect-ratio: 16/9; background-color: transparent;
        border-radius: 40px; 
        box-shadow: 0 20px 50px rgba(0,0,0,0.4);
        overflow: hidden; display: flex; align-items: center; justify-content: center; position: relative;
        transform: perspective(1000px) rotateY(-2deg); /* Leggero 3D */
        border: 2px solid rgba(255,255,255,0.1);
    }
    #ad-video-bg { position: absolute; top:0; left:0; width:100%; height:100%; object-fit: cover; filter: blur(30px) opacity(0.6); transform: scale(1.1); }
    #ad-video { width: 100%; height: 100%; object-fit: contain; position: relative; z-index: 2; }
    iframe { width:100%; height:100%; border:0; }
    
    /* ANIMAZIONI TESTI */
    #stop-name.exit { animation: slideOutUp 0.5s forwards; }
    #stop-name.enter { animation: slideInUp 0.5s forwards; }
    @keyframes slideInUp { from { opacity:0; transform:translateY(30px); } to { opacity:1; transform:translateY(0); } }
    @keyframes slideOutUp { from { opacity:1; transform:translateY(0); } to { opacity:0; transform:translateY(-30px); } }
    
    /* ========================================================= */
    /*   LIQUID GLASS KIT - BARRA INFERIORE (NUOVA IMPLEMENTAZIONE)   */
    /* ========================================================= */
    
    .liquid-glass-bar-container {
        position: fixed;
        bottom: 30px;
        left: 50%;
        transform: translateX(-50%);
        width: 95%;
        height: 90px;
        /* Struttura Griglia: Ora(SX) -- Ticker(Centro) -- Logo(DX) */
        display: grid;
        grid-template-columns: 240px 1fr 240px;
        border-radius: 50px;
        overflow: hidden; /* Fondamentale per ritagliare i contenuti */
        z-index: 900;
        
        /* EFFETTO BASE "VETRO CONTENITORE" (Pillola intera) */
        background: rgba(255, 255, 255, 0.05); /* Vetro molto leggero */
        border: 1px solid rgba(255, 255, 255, 0.15); /* Bordo sottile lucido */
        box-shadow: 0 15px 40px rgba(0, 0, 0, 0.25);
        /* Sfocatura "generale" dietro l'intera pillola */
        backdrop-filter: blur(10px); 
        -webkit-backdrop-filter: blur(10px);
    }

    /* I LATI: Clock e Logo (Glass Superiore) 
       Devono stare SOPRA il ticker (Z-Index alto) per fare l'effetto blur passante
    */
    .glass-end-section {
        position: relative;
        z-index: 10; /* Livello più alto del testo */
        height: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        
        /* Styling del Vetro per i blocchi laterali - Molto luminoso, molto blur */
        background: rgba(255, 255, 255, 0.12); /* Bianco semitrasparente più visibile */
        backdrop-filter: blur(25px); /* Il BLUR forte che sfoca il testo sotto */
        -webkit-backdrop-filter: blur(25px);
        
        border-left: 1px solid rgba(255,255,255,0.2);
        border-right: 1px solid rgba(255,255,255,0.2);
    }

    /* Orologio a Sinistra */
    .section-left {
        border-right: 1px solid rgba(255,255,255,0.1);
        border-left: none; /* Primo elemento */
        flex-direction: column;
    }

    /* Logo a Destra */
    .section-right {
        border-left: 1px solid rgba(255,255,255,0.1);
        border-right: none;
    }

    /* ZONA CENTRALE SCORRIMENTO 
       Sta "sotto" visivamente (o sullo stesso piano z-index, ma il layout a griglia gestisce lo spazio. 
       Per fare l'effetto "sotto" durante l'ingresso/uscita, 
       usiamo il fatto che le celle left/right hanno background e blur propri)
    */
    .marquee-section {
        position: relative;
        overflow: hidden;
        display: flex;
        align-items: center;
        z-index: 1; /* Livello basso */
        
        /* Vetro centrale (opzionale leggero) */
        background: rgba(255, 255, 255, 0.02);
    }

    /* EFFETTO MASK FONDAMENTALE: 
       Facciamo scorrere il testo in una fascia LUNGA che in realtà passa sotto i div laterali?
       No, la griglia separa gli spazi. Ma la richiesta è: 
       "quando il testo passa sotto il logo e la scritta dev'essere sfocato".
       Per farlo funzionare con la griglia, il ticker dovrebbe idealmente essere 
       LUNGO TUTTO LO SCHERMO in position absolute dietro i blocchi. 
       Proviamo l'approccio: MARQUEE ASSOLUTO SOTTOSTANTE.
    */
    
    /* Riprogettazione layout per effetto "Sotto" */
    /* Sovrascriviamo la struttura precedente per abilitare l'effetto "dietro" */
    
    .liquid-glass-bar-container {
         display: block; /* Non grid, useremo positioning assoluto */
         /* Le impostazioni vetro rimangono per il contorno */
    }

    .ticker-full-width-track {
        position: absolute;
        top: 0; left: 0; width: 100%; height: 100%;
        display: flex; align-items: center;
        z-index: 1; /* Livello 1: Sotto */
    }
    
    .ticker-text {
        white-space: nowrap;
        font-size: 32px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 2px;
        color: #ffffff;
        /* Ombreggiatura per leggibilità testo su vetro */
        text-shadow: 0 2px 5px rgba(0,0,0,0.3);
        
        /* Animazione Scorrimento Infinita */
        padding-left: 100%; /* Parte da fuori schermo a destra */
        animation: ticker-move 25s linear infinite;
    }
    
    @keyframes ticker-move {
        0% { transform: translateX(0); }
        100% { transform: translateX(-200%); } /* Va molto a sinistra */
    }

    /* I Blocchi ORA e LOGO sovrapposti in posizione assoluta */
    .glass-overlay-left {
        position: absolute; top:0; left:0; width: 220px; height: 100%;
        z-index: 10;
        /* Liquid Glass Effect */
        background: rgba(255, 255, 255, 0.1); 
        backdrop-filter: blur(25px); /* ECCO LA MAGIA: Sfoca quello che passa sotto */
        -webkit-backdrop-filter: blur(25px);
        border-right: 1px solid rgba(255,255,255,0.2);
        
        display: flex; flex-direction: column; align-items: center; justify-content: center;
    }

    .glass-overlay-right {
        position: absolute; top:0; right:0; width: 220px; height: 100%;
        z-index: 10;
        /* Liquid Glass Effect */
        background: rgba(255, 255, 255, 0.1);
        backdrop-filter: blur(25px);
        -webkit-backdrop-filter: blur(25px);
        border-left: 1px solid rgba(255,255,255,0.2);
        
        display: flex; align-items: center; justify-content: center;
    }

    /* Styling Orologio (in alto a sinistra nella barra) */
    #clock-time {
        font-size: 42px; font-weight: 800; line-height: 0.9;
        color: #fff;
        text-shadow: 0 2px 10px rgba(0,0,0,0.2);
    }
    #clock-date {
        font-size: 14px; font-weight: 600; margin-top: 5px; opacity: 0.9; letter-spacing: 1px;
        color: #ddd;
    }

    /* Styling Logo (in alto a destra nella barra) */
    .bar-logo {
        max-height: 55px;
        max-width: 160px;
        filter: drop-shadow(0 2px 5px rgba(0,0,0,0.3));
    }

    /* Overlay errori/caricamento */
    #video-error-modal, #loader, #service-offline-overlay {
        position: fixed; top: 0; left: 0; width: 100%; height: 100%;
        z-index: 2000; display: flex; align-items: center; justify-content: center;
    }
    #video-error-modal, #service-offline-overlay {
        background: rgba(10,10,10,0.8); backdrop-filter: blur(10px); visibility: hidden; opacity: 0; transition: 0.3s;
    }
    #video-error-modal.active, #service-offline-overlay.active { visibility: visible; opacity: 1; }
    
    #loader { background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end)); transition: opacity 0.5s; }
    #loader.hidden { opacity: 0; pointer-events: none; }
    
    /* Modal Content */
    .modal-box {
         background: #222; border: 1px solid #444; color: #fff; padding: 40px; 
         border-radius: 20px; text-align: center; max-width: 500px;
    }
    
</style>
</head>
<body>
<!-- AUDIO PRELOAD -->
<audio id="announcement-sound" src="/announcement-audio" preload="auto"></audio>
<audio id="stop-announcement-sound" preload="auto" style="display:none;"></audio>
<audio id="booked-sound-viewer" src="/booked-stop-audio" preload="auto" style="display:none;"></audio>
code
Code
<!-- CARICAMENTO INIZIALE -->
<div id="loader">
    <img src="https://i.ibb.co/nN5WRrHS/LOGO-HARZAFI.png" alt="Caricamento..." width="200" style="filter: drop-shadow(0 0 20px rgba(255,255,255,0.4));">
</div>

<!-- OVERLAY OFFLINE -->
<div id="service-offline-overlay">
    <h1 style="font-size: 60px; text-transform: uppercase; font-weight: 900;">Servizio Non Disponibile</h1>
</div>

<!-- MODALE ERRORE VIDEO -->
<div id="video-error-modal">
    <div class="modal-box">
         <div style="font-size:50px; color:#ff453a; margin-bottom:20px;">⚠️</div>
         <h2>Errore Caricamento Media</h2>
         <p>Impossibile riprodurre il contenuto video selezionato.</p>
         <button onclick="document.getElementById('video-error-modal').classList.remove('active')" style="margin-top:20px; padding:10px 30px; border-radius:10px; border:none; background:#0A84FF; color:white; font-weight:bold; cursor:pointer;">CHIUDI</button>
    </div>
</div>

<!-- LAYOUT PRINCIPALE -->
<div class="content-area">
    <div class="main-content-row">
        <!-- Colonna Info: ID Linea + Testi Fermata -->
        <div class="line-graphic">
            <div class="line-id-container"><span id="line-id">--</span></div>
            <div id="stop-indicator" class="current-stop-indicator"></div>
        </div>
        
        <div class="text-content">
            <p class="direction-header">DESTINAZIONE</p>
            <h1 id="direction-name">ATTENDERE...</h1>
            
            <p class="next-stop-header">PROSSIMA FERMATA</p>
            <h2 id="stop-name">--</h2>
            <p id="stop-subtitle"></p>
        </div>

        <!-- Colonna Video -->
        <div class="video-wrapper">
            <div id="video-player-container">
                <!-- Contenuto video dinamico qui -->
            </div>
        </div>
    </div>
</div>

<!-- *** BARRA LIQUID GLASS KIT (NUOVA) *** -->
<div class="liquid-glass-bar-container">
    <!-- Overlay Sinistro: OROLOGIO E DATA (Sopra al testo) -->
    <div class="glass-overlay-left section-left">
         <div id="clock-time">00:00</div>
         <div id="clock-date">01/01/24</div>
    </div>
    
    <!-- Overlay Destro: LOGO (Sopra al testo) -->
    <div class="glass-overlay-right section-right">
         <img src="https://i.ibb.co/nN5WRrHS/LOGO-HARZAFI.png" alt="Harzafi Logo" class="bar-logo">
    </div>
    
    <!-- Track del Testo che Scorre (Sotto ai lati, in mezzo) -->
    <div class="ticker-full-width-track">
         <div id="ticker-content" class="ticker-text">
              BENVENUTI A BORDO &bull; HARZAFI TRANSIT SYSTEM &bull; MANTENERE IL DISTANZIAMENTO
         </div>
    </div>
</div>
<script>
const socket = io();
const IMG_DEFAULT = 'https://i.ibb.co/1GnC8ZpN/Pronto-per-eseguire-contenuti-video.jpg';

// Elementi UI
const loader = document.getElementById('loader');
const offlineOverlay = document.getElementById('service-offline-overlay');
const errorModal = document.getElementById('video-error-modal');

const elLineId = document.getElementById('line-id');
const elDirection = document.getElementById('direction-name');
const elStopName = document.getElementById('stop-name');
const elStopSub = document.getElementById('stop-subtitle');
const elTicker = document.getElementById('ticker-content');
const containerVideo = document.getElementById('video-player-container');

// Audio
const audioAnnounce = document.getElementById('announcement-sound');
const audioBooked = document.getElementById('booked-sound-viewer');
const audioStop = document.getElementById('stop-announcement-sound');

let state = {};
let currentStateMedia = null;

// --- LOGICA OROLOGIO ITALIA/ROMA ---
function updateClock() {
const now = new Date();
const optionsTime = { timeZone: 'Europe/Rome', hour: '2-digit', minute: '2-digit', hour12: false };
const optionsDate = { timeZone: 'Europe/Rome', day: '2-digit', month: '2-digit', year: '2-digit' };

const timeString = new Intl.DateTimeFormat('it-IT', optionsTime).format(now);
const dateString = new Intl.DateTimeFormat('it-IT', optionsDate).format(now); // GG/MM/AA

document.getElementById('clock-time').textContent = timeString;
document.getElementById('clock-date').textContent = dateString;
}
setInterval(updateClock, 1000);
updateClock(); // Esegui subito

// --- SOCKET LISTENERS ---
socket.on('connect', () => {
socket.emit('request_initial_state');
console.log("Socket connected");
});

socket.on('disconnect', () => {
loader.classList.remove('hidden');
});

socket.on('initial_state', (s) => {
loader.classList.add('hidden');
applyState(s);
});

socket.on('state_updated', (s) => {
applyState(s);
});

function applyState(newState) {
// Service Status
if(newState.serviceStatus === 'offline') {
offlineOverlay.classList.add('active');
return;
} else {
offlineOverlay.classList.remove('active');
}

const oldState = state;
state = newState;

// Info Fermata e Linea
const line = state.linesData[state.currentLineKey];
if(line) {
elLineId.textContent = state.currentLineKey;
elDirection.textContent = line.direction;

const stop = line.stops[state.currentStopIndex];
if(stop) {
if(stop.name !== elStopName.textContent) {
// Animazione cambio testo
elStopName.classList.remove('enter');
elStopName.classList.add('exit');
setTimeout(() => {
elStopName.textContent = stop.name;
elStopSub.textContent = stop.subtitle;
elStopName.classList.remove('exit');
elStopName.classList.add('enter');

// Audio Stop Automatico
if(stop.audio) {
audioStop.src = stop.audio;
let vol = parseFloat(state.volumeLevel || 1.0);
duckVideoVolume(0.1, () => {
audioStop.play().then(() => {
audioStop.onended = () => duckVideoVolume(vol); // Ripristina
}).catch(e=>console.log(e));
});
}
}, 500);
}
}
}

// Ticker Messages
if(state.infoMessages && state.infoMessages.length > 0) {
let fullText = state.infoMessages.join(" • ") + " • ";
// Duplica per loop più lungo se il testo è corto
while(fullText.length < 50) fullText += fullText;
if(elTicker.textContent.trim() !== fullText.trim()) {
elTicker.textContent = fullText;
}
} else {
elTicker.textContent = "SISTEMA HARZAFI ONLINE • BUON VIAGGIO • ";
}

// Audio Triggers
if(isNewTrigger(oldState, state, 'announcement')) {
playAudioWithDucking(audioAnnounce);
}
if(isNewTrigger(oldState, state, 'stopRequested')) {
audioBooked.currentTime = 0; audioBooked.play().catch(e=>{});
}

// Gestione Video (Logica complessa)
handleMedia(state);
}

function isNewTrigger(oldS, newS, key) {
if(!newS[key]) return false;
if(!oldS[key]) return true;
return newS[key].timestamp > oldS[key].timestamp;
}

function duckVideoVolume(targetVol, callback=null) {
const v = document.getElementById('ad-video');
if(v) v.volume = targetVol;
if(callback) callback();
}

function playAudioWithDucking(audioElem) {
audioElem.currentTime = 0;
let originalVol = parseFloat(state.volumeLevel || 1.0);
duckVideoVolume(0.1); // Abbassa video
audioElem.play().then(() => {
audioElem.onended = () => duckVideoVolume(originalVol);
}).catch(err => {
console.warn("Audio play error", err);
duckVideoVolume(originalVol);
});
}

function handleMedia(s) {
const hasMedia = (s.mediaSource === 'server' || s.mediaSource === 'embed') && !s.videoNotAvailable;
const mediaKey = hasMedia ? (s.mediaSource + (s.mediaLastUpdated || '')) : 'default';

if(mediaKey !== currentStateMedia) {
currentStateMedia = mediaKey;
containerVideo.innerHTML = ''; // Reset

if(s.videoNotAvailable) {
// Opzionale: mostra immagine "non disponibile"
containerVideo.innerHTML = `<img src="${IMG_DEFAULT}" style="width:100%;height:100%;object-fit:cover;">`;
}
else if (s.mediaSource === 'server') {
// Video locale
const src = `/stream-video?t=${s.mediaLastUpdated}`;
containerVideo.innerHTML = `
<video id="ad-video-bg" loop playsinline muted src="${src}"></video>
<video id="ad-video" loop playsinline src="${src}" oncanplay="this.play()"></video>
`;
const v = document.getElementById('ad-video');
v.onerror = () => { errorModal.classList.add('active'); currentStateMedia = null; };
v.volume = parseFloat(s.volumeLevel || 1.0);
}
else if (s.mediaSource === 'embed') {
// Iframe
let code = s.embedCode; // Assume codice sicuro o pulito server-side
// Iniettalo
containerVideo.innerHTML = code;
// Aggiusta dimensioni iframe
let fr = containerVideo.querySelector('iframe');
if(fr) { fr.style.width='100%'; fr.style.height='100%'; fr.style.borderRadius='40px'; }
}
else {
// Default image
containerVideo.innerHTML = `<img src="${IMG_DEFAULT}" style="width:100%;height:100%;object-fit:cover;border-radius:40px;">`;
}
}

// Update volume/play state if media didn't change but controls did
if(s.mediaSource === 'server' && !s.videoNotAvailable) {
const v = document.getElementById('ad-video');
if(v) {
v.volume = parseFloat(s.volumeLevel || 1.0);
if(s.playbackState === 'paused') v.pause(); else v.play().catch(e=>{});
// Gestione seek se necessario (non implementato nel dettaglio per brevità ma struttura predisposta)
}
}
}
</script>
</body>
</html>
"""
-------------------------------------------------------------------
4. ROUTE FLASK E API
-------------------------------------------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
if current_user.is_authenticated: return redirect(url_for('dashboard'))
form = LoginForm()
if form.validate_on_submit():
user = USERS_DB.get(form.username.data)
if user and check_password_hash(user['password_hash'], form.password.data):
login_user(get_user(form.username.data))
return redirect(url_for('dashboard'))
flash('Credenziali non valide', 'error')
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
def announcement_audio_file():
# Placeholder per file audio di sistema. Sostituire con 'send_file("path")'
try: return send_file('LINEA 3. CORSA DEVIATA..mp3', mimetype='audio/mpeg')
except: return Response("Audio not found", 404)
@app.route('/booked-stop-audio')
@login_required
def booked_audio_file():
try: return send_file('bip.mp3', mimetype='audio/mpeg')
except: return Response("Audio not found", 404)
@app.route('/upload-video', methods=['POST'])
@login_required
def upload_video():
global current_video_file
if 'video' not in request.files: return jsonify({'error':'No file'}), 400
f = request.files['video']
if f.filename=='': return jsonify({'error':'Empty'}), 400
code
Code
# Rimuovi precedente
if current_video_file['path'] and os.path.exists(current_video_file['path']):
    try: os.remove(current_video_file['path'])
    except: pass

try:
    td = tempfile.gettempdir()
    fd, path = tempfile.mkstemp(dir=td, suffix="_"+f.filename)
    os.close(fd)
    f.save(path)
    current_video_file = {'path':path, 'mimetype':f.mimetype, 'name':f.filename}
    return jsonify({'success':True})
except Exception as e:
    return jsonify({'error':str(e)}), 500
@app.route('/stream-video')
@login_required
def stream_video():
if not current_video_file['path'] or not os.path.exists(current_video_file['path']): return abort(404)
return send_file(current_video_file['path'], mimetype=current_video_file['mimetype'])
@app.route('/clear-video', methods=['POST'])
@login_required
def clear_video():
global current_video_file
if current_video_file['path'] and os.path.exists(current_video_file['path']):
try: os.remove(current_video_file['path'])
except: pass
current_video_file = {'path':None, 'mimetype':None, 'name':None}
return jsonify({'ok':True})
-------------------------------------------------------------------
5. WEBSOCKET HANDLERS
-------------------------------------------------------------------
@socketio.on('connect')
def ws_connect():
if current_user.is_authenticated: socketio.emit('initial_state', current_app_state, room=request.sid)
@socketio.on('update_all')
def ws_update(data):
if current_user.is_authenticated:
global current_app_state
current_app_state.update(data)
socketio.emit('state_updated', current_app_state)
@socketio.on('request_initial_state')
def ws_req_state():
if current_user.is_authenticated: socketio.emit('initial_state', current_app_state, room=request.sid)
if name == 'main':
print("--- SERVER AVVIATO HARZAFI ---")
socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
