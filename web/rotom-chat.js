const params = new URLSearchParams(location.search);
const token = params.get('token') || '';
const messagesEl = document.querySelector('#messages');
const form = document.querySelector('#chatForm');
const input = document.querySelector('#messageInput');
const sendBtn = document.querySelector('#sendBtn');
const clearBtn = document.querySelector('#clearBtn');
const labBtn = document.querySelector('#labBtn');
const backLink = document.querySelector('#backLink');
const statusEl = document.querySelector('#connectionStatus');
const quickActionsEl = document.querySelector('#quickActions');

const HISTORY_KEY = 'rotomWebChatHistory';
const MAX_HISTORY = 40;

function loadHistory() {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); }
  catch { return []; }
}

function saveHistory(history) {
  try { localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(-MAX_HISTORY))); }
  catch { /* segue sem salvar */ }
}

function setStatus(text, mode = '') {
  statusEl.textContent = text;
  statusEl.className = mode;
}

function messageRow(role, text, persist = true) {
  const row = document.createElement('div');
  row.className = `message-row ${role}`;

  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.textContent = role === 'user' ? '🧒' : role === 'system' ? '!' : '⚡';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = text;

  row.appendChild(avatar);
  row.appendChild(bubble);
  messagesEl.appendChild(row);
  messagesEl.scrollTop = messagesEl.scrollHeight;

  if (persist && role !== 'system') {
    const history = loadHistory();
    history.push({ role, text });
    saveHistory(history);
  }
  return row;
}

function resultCard(title, data = null) {
  const row = document.createElement('div');
  row.className = `message-row system result ${data && data.ok === false ? 'bad' : 'good'}`;
  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.textContent = data && data.ok === false ? '😅' : '✅';
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  const summary = document.createElement('div');
  summary.textContent = title;
  bubble.appendChild(summary);
  if (data) {
    const details = document.createElement('details');
    const detailsTitle = document.createElement('summary');
    detailsTitle.textContent = 'Detalhes para o papai';
    const pre = document.createElement('pre');
    pre.textContent = JSON.stringify(data, null, 2);
    details.appendChild(detailsTitle);
    details.appendChild(pre);
    bubble.appendChild(details);
  }
  row.appendChild(avatar);
  row.appendChild(bubble);
  messagesEl.appendChild(row);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return row;
}

function labUrl(hash = '') {
  const suffix = hash ? `#${hash}` : '';
  return token ? `/?token=${encodeURIComponent(token)}${suffix}` : `/${suffix}`;
}

function renderHistory() {
  messagesEl.innerHTML = '';
  const history = loadHistory();
  if (!history.length) {
    messageRow('rotom', 'Rotom! Oi, Davi ⚡ Este é seu chat local comigo. Me pergunte sobre programação, Linux, Arduino, ESP32 ou robótica!', true);
    messageRow('system', 'Aviso de segurança: comandos que podem apagar arquivos, revelar segredos ou mexer no sistema precisam de supervisão do papai.', false);
    return;
  }
  for (const msg of history) messageRow(msg.role, msg.text, false);
}

function setBusy(busy) {
  input.disabled = busy;
  sendBtn.disabled = busy;
  if (busy) {
    const row = messageRow('rotom', 'Rotom pensando', false);
    row.classList.add('typing');
    row.id = 'typingRow';
  } else {
    document.querySelector('#typingRow')?.remove();
  }
}

function contextForApi() {
  return {
    webChat: true,
    page: 'rotom-web-chat',
    safety: 'supervised-maker-laptop',
    selectedPort: selectedPort || null,
    lastResult,
    boardChoices,
    history: loadHistory().slice(-10),
  };
}

async function api(path, payload = null, method = 'POST') {
  if (!token) throw new Error('Falta o token na URL. Abra pelo endereço que aparece no terminal do Rotom Dex Lab.');
  const options = {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-Rotom-Token': token,
    },
  };
  if (payload !== null) options.body = JSON.stringify(payload);
  const res = await fetch(path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Erro ${res.status}`);
  return data;
}

function apiGet(path) {
  return api(path, null, 'GET');
}

const ACTION_LABELS = {
  'arduino.board_list': '🔎 Procurar placa',
  'arduino.compile': '🧪 Testar código',
  'arduino.upload': '🚀 Enviar para a placa',
  'serial.open': '👀 Abrir serial',
  'diagnostics.open': '🛠️ Diagnóstico',
  'templates.list': '🧩 Templates',
};

let selectedPort = localStorage.getItem('rotomWebChatPort') || '';
let boardChoices = null;
let lastResult = null;
let serialSessionId = null;
let serialWs = null;

function rememberPort(port) {
  selectedPort = port || '';
  if (selectedPort) localStorage.setItem('rotomWebChatPort', selectedPort);
}

function pickPortFromBoardChoices(data) {
  const devices = data.devices || [];
  if (!devices.length) return '';
  const knownLast = devices.find((device) => device.port === selectedPort);
  const preferred = data.selectedPort || (knownLast && knownLast.port) || devices[0].port;
  rememberPort(preferred);
  return preferred;
}

async function runBoardList() {
  const data = await apiGet('/api/arduino/board-choices');
  boardChoices = data;
  const port = pickPortFromBoardChoices(data);
  const suffix = port ? ` Vou usar ${port}.` : '';
  resultCard(`${data.message || 'Procurei as placas.'}${suffix}`, data);
  return data;
}

async function runCompile() {
  const data = await api('/api/arduino/compile', {});
  lastResult = { action: 'compile', ok: data.ok, message: data.message, stdout: data.stdout, stderr: data.stderr };
  resultCard(data.message || (data.ok === false ? 'O teste do código falhou.' : 'Código testado!'), data);
  return data;
}

async function ensurePort(actionText) {
  if (selectedPort) return selectedPort;
  const data = await runBoardList();
  if (selectedPort) return selectedPort;
  const typed = prompt(`Qual porta devo usar para ${actionText}? Exemplo: /dev/ttyUSB0 ou COM9`);
  if (typed && typed.trim()) {
    rememberPort(typed.trim());
    return selectedPort;
  }
  messageRow('system', 'Sem porta escolhida. Conecte a placa e use 🔎 Procurar placa.', false);
  return '';
}

async function runUpload() {
  const port = await ensurePort('enviar para a placa');
  if (!port) return null;
  if (!confirm(`Vou enviar o código para ${port}. A placa está certa?`)) return null;
  const data = await api('/api/arduino/upload', { port, confirmed: true });
  lastResult = { action: 'upload', ok: data.ok, message: data.message, stdout: data.stdout, stderr: data.stderr };
  resultCard(data.message || (data.ok === false ? 'Não consegui enviar.' : 'Enviei para a placa!'), data);
  return data;
}

async function runSerialOpen() {
  const port = await ensurePort('abrir o serial');
  if (!port) return null;
  if (serialWs) serialWs.close();
  const data = await api('/api/serial/open', { port, baud: 115200 });
  serialSessionId = data.sessionId;
  resultCard(data.fake ? `Serial aberto em simulação em ${port}.` : `Serial real aberto em ${port} @ 115200.`, data);
  serialWs = new WebSocket(`ws://${location.host}/api/serial/stream/${encodeURIComponent(serialSessionId)}?token=${encodeURIComponent(token)}`);
  serialWs.onmessage = (event) => resultCard(`Serial: ${event.data}`);
  serialWs.onerror = () => messageRow('system', 'O monitor serial teve um erro. Tente fechar e abrir de novo.', false);
  serialWs.onclose = () => { serialWs = null; };
  return data;
}

async function runDiagnostics() {
  const data = await apiGet('/api/diagnostics');
  if (data.boardChoices) {
    boardChoices = data.boardChoices;
    pickPortFromBoardChoices(data.boardChoices);
  }
  resultCard('Diagnóstico do papai pronto.', data);
  return data;
}

async function runTemplates() {
  const data = await apiGet('/api/templates');
  const names = (data.templates || []).map((template) => `• ${template.title || template.id}`).join('\n');
  resultCard(names ? `Templates seguros disponíveis:\n${names}` : 'Não achei templates seguros agora.', data);
  return data;
}

const ACTION_RUNNERS = {
  'arduino.board_list': runBoardList,
  'arduino.compile': runCompile,
  'arduino.upload': runUpload,
  'serial.open': runSerialOpen,
  'diagnostics.open': runDiagnostics,
  'templates.list': runTemplates,
};

async function runAction(action) {
  const runner = ACTION_RUNNERS[action.type];
  if (!runner) {
    messageRow('system', `Ainda não sei executar: ${action.type}`, false);
    return;
  }
  renderActions([]);
  setBusy(true);
  try {
    await runner(action);
  } catch (err) {
    messageRow('system', `A ação falhou: ${err.message}`, false);
  } finally {
    setBusy(false);
    input.focus();
  }
}

function renderActions(actions = []) {
  quickActionsEl.innerHTML = '';
  for (const action of actions) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = action.label || ACTION_LABELS[action.type] || action.type;
    btn.onclick = () => runAction(action);
    quickActionsEl.appendChild(btn);
  }
}

async function sendMessage(text) {
  messageRow('user', text);
  renderActions([]);
  setBusy(true);
  try {
    const data = await api('/api/chat', {
      message: text,
      context: contextForApi(),
    });
    setBusy(false);
    messageRow('rotom', data.reply || 'Rotom!');
    setStatus(data.offline ? 'modo seguro local' : 'online', data.offline ? 'offline' : 'online');
    renderActions(data.suggestedActions || []);
  } catch (err) {
    setBusy(false);
    setStatus('precisa do token', 'offline');
    messageRow('system', `Não consegui enviar: ${err.message}`, false);
  }
}

form.addEventListener('submit', (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  input.style.height = 'auto';
  sendMessage(text);
});

input.addEventListener('input', () => {
  input.style.height = 'auto';
  input.style.height = `${Math.min(input.scrollHeight, 144)}px`;
});

input.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

clearBtn.onclick = () => {
  saveHistory([]);
  renderActions([]);
  renderHistory();
};

labBtn.onclick = () => {
  location.href = labUrl();
};

renderHistory();
if (backLink) backLink.href = labUrl();
if (!token) setStatus('sem token', 'offline');
else setStatus(selectedPort ? `pronto • porta ${selectedPort}` : 'pronto para conversar', 'online');
input.focus();
