const statusBox = document.querySelector('#statusBox');
const deviceStatus = document.querySelector('#deviceStatus');
const deviceSelect = document.querySelector('#deviceSelect');
const deviceSelectLabel = document.querySelector('#deviceSelectLabel');
const chatLog = document.querySelector('#chatLog');
const chatForm = document.querySelector('#chatForm');
const chatInput = document.querySelector('#chatInput');
const suggestedActions = document.querySelector('#suggestedActions');
const portInput = document.querySelector('#portInput');
const serialBox = document.querySelector('#serialBox');
const serialMode = document.querySelector('#serialMode');
const chatStatus = document.querySelector('#chatStatus');
const missionList = document.querySelector('#missionList');
const diagnosticsBtn = document.querySelector('#diagnosticsBtn');
const baudSelect = document.querySelector('#baudSelect');
const serialInput = document.querySelector('#serialInput');
const serialSendBtn = document.querySelector('#serialSendBtn');
const serialClearBtn = document.querySelector('#serialClearBtn');
const templateList = document.querySelector('#templateList');
const imagePreview = document.querySelector('#imagePreview');
const imageThumb = document.querySelector('#imageThumb');
const imageName = document.querySelector('#imageName');
const imageRemoveBtn = document.querySelector('#imageRemoveBtn');
const imageAttachBtn = document.querySelector('#imageAttachBtn');
const imageInput = document.querySelector('#imageInput');

const TOKEN = new URLSearchParams(location.search).get('token') || '';
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const ALLOWED_IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/webp', 'image/gif'];

let serialWs = null;
let serialSessionId = null;
let lastResult = null;
let boardChoices = null;
let pendingImage = null; // { dataUrl, name }
let missionsState = [];

const MISSION_ICON = { done: '✅', doing: '🟡', todo: '⬜' };

function pretty(obj) {
  return JSON.stringify(obj, null, 2);
}

const CHAT_KEY = 'rotomDexChatHistory';
const CHAT_MAX = 60;

function chatHistory() {
  try {
    return JSON.parse(localStorage.getItem(CHAT_KEY) || '[]');
  } catch {
    return [];
  }
}

function saveChatHistory(history) {
  try {
    localStorage.setItem(CHAT_KEY, JSON.stringify(history.slice(-CHAT_MAX)));
  } catch {
    /* localStorage cheia ou indisponível: seguimos sem persistir */
  }
}

function renderMessage(role, text) {
  const row = document.createElement('div');
  row.className = `msg ${role}`;
  const avatar = document.createElement('span');
  avatar.className = 'avatar';
  avatar.textContent = role === 'user' ? '🧒' : '⚡';
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = text;
  row.appendChild(avatar);
  row.appendChild(bubble);
  chatLog.appendChild(row);
  chatLog.scrollTop = chatLog.scrollHeight;
  return row;
}

function appendChat(role, text) {
  renderMessage(role, text);
  const history = chatHistory();
  history.push({ role, text });
  saveChatHistory(history);
}

function restoreChat() {
  const history = chatHistory();
  for (const message of history) renderMessage(message.role, message.text);
  return history.length > 0;
}

function clearChat() {
  saveChatHistory([]);
  chatLog.innerHTML = '';
  appendChat('agent', 'Rotom! Conversa nova ⚡ Clique em Começar ou me diga o que você quer fazer.');
}

let thinkingEl = null;
function setChatBusy(busy) {
  chatInput.disabled = busy;
  const sendBtn = chatForm.querySelector('button:not([type="button"])');
  if (sendBtn) sendBtn.disabled = busy;
  if (busy && !thinkingEl) {
    thinkingEl = document.createElement('div');
    thinkingEl.className = 'msg agent thinking';
    thinkingEl.innerHTML = '<span class="avatar">⚡</span><div class="bubble">Rotom está pensando<span class="dots"></span></div>';
    chatLog.appendChild(thinkingEl);
    chatLog.scrollTop = chatLog.scrollHeight;
  } else if (!busy && thinkingEl) {
    thinkingEl.remove();
    thinkingEl = null;
  }
}

function appendCard(message, data) {
  const card = document.createElement('div');
  card.className = `result-card ${data && data.ok === false ? 'bad' : 'good'}`;
  const line = document.createElement('div');
  line.className = 'result-line';
  line.textContent = message;
  card.appendChild(line);
  if (data) {
    const details = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = 'Detalhes para o papai';
    const pre = document.createElement('pre');
    pre.textContent = pretty(data);
    details.appendChild(summary);
    details.appendChild(pre);
    card.appendChild(details);
  }
  chatLog.appendChild(card);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function tokenMissingMessage() {
  return 'Abra o Rotom Dex pelo endereço completo com ?token=... que aparece no terminal do papai.';
}

async function api(path, options = {}) {
  if (!TOKEN) throw new Error(tokenMissingMessage());
  const headers = {
    'Content-Type': 'application/json',
    'X-Rotom-Token': TOKEN,
    ...(options.headers || {}),
  };
  const res = await fetch(path, { headers, ...options });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Erro ${res.status}`);
  return data;
}

function setStatus(message, raw) {
  deviceStatus.textContent = message;
  statusBox.textContent = raw ? pretty(raw) : message;
}

async function showResult(title, promise, action) {
  deviceStatus.textContent = `${title}...`;
  statusBox.textContent = `${title}...`;
  try {
    const data = await promise;
    const message = data.message || (data.ok === false ? 'Algo não deu certo.' : 'Pronto!');
    setStatus(message, data);
    if (action) {
      lastResult = { action, ok: data.ok, message, stdout: data.stdout, stderr: data.stderr };
      appendCard(message, data);
      updateGuide();
    }
    return data;
  } catch (err) {
    setStatus(`Ops! ${err.message}`, { error: err.message });
    throw err;
  }
}

function selectPort(port) {
  portInput.value = port || '';
  if (port) localStorage.setItem('rotomDexLastPort', port);
  updateGuide();
}

function renderDevices(data) {
  boardChoices = data;
  const devices = data.devices || [];
  const lastPort = localStorage.getItem('rotomDexLastPort');
  deviceSelect.innerHTML = '';
  deviceSelectLabel.classList.toggle('hidden', devices.length === 0);

  if (devices.length === 1 && !data.needsChoice) {
    const device = devices[0];
    const option = document.createElement('option');
    option.value = device.port;
    const confidence = device.confidence === 'provavel' ? '⭐ provável' : 'porta genérica';
    option.textContent = `${device.label || `${device.name} em ${device.port}`} — ${confidence}`;
    option.title = device.reason || '';
    deviceSelect.appendChild(option);
    deviceSelect.value = device.port;
    selectPort(device.port);
    deviceStatus.textContent = `${data.message || 'Achei a placa.'} ${device.reason || ''}`.trim();
    return;
  }
  if (devices.length > 0) {
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = 'Escolha a sua placa';
    deviceSelect.appendChild(placeholder);
    for (const device of devices) {
      const option = document.createElement('option');
      option.value = device.port;
      const confidence = device.confidence === 'provavel' ? '⭐ provável' : 'porta genérica';
      option.textContent = `${device.label || `${device.name} em ${device.port}`} — ${confidence}`;
      option.title = device.reason || '';
      deviceSelect.appendChild(option);
    }
    const preferred = data.selectedPort || (devices.some((d) => d.port === lastPort) ? lastPort : '');
    if (preferred) {
      deviceSelect.value = preferred;
      selectPort(preferred);
      const found = devices.find((d) => d.port === preferred);
      deviceStatus.textContent = `${data.message || 'Achei portas.'} Usando ${found ? found.label : preferred}. ${found && found.reason ? found.reason : ''}`.trim();
    } else {
      selectPort('');
      deviceStatus.textContent = data.message || 'Achei portas. Escolha a que você quer usar.';
    }
    return;
  }
  selectPort('');
}

deviceSelect.onchange = () => {
  selectPort(deviceSelect.value);
  if (deviceSelect.value) {
    deviceStatus.textContent = `Beleza! Vou usar ${deviceSelect.options[deviceSelect.selectedIndex].text}.`;
  }
};

async function refreshDevices() {
  const data = await showResult('Procurando sua placa', api('/api/arduino/board-choices'));
  renderDevices(data);
  return data;
}

function requirePort(actionName) {
  const port = portInput.value.trim();
  if (!port) {
    appendChat('agent', `Primeiro clique em "Procurar minha placa". Depois eu consigo ${actionName}.`);
    return null;
  }
  return port;
}

async function doCompile() {
  return showResult('Testando o código', api('/api/arduino/compile', { method: 'POST', body: '{}' }), 'compile');
}

async function doUpload() {
  const port = requirePort('enviar o código para a placa');
  if (!port) return null;
  if (!confirm(`Vou enviar o código para ${port}. A placa está certa?`)) return null;
  return showResult('Enviando para a placa', api('/api/arduino/upload', {
    method: 'POST',
    body: JSON.stringify({ port, confirmed: true }),
  }), 'upload');
}

async function openSerial() {
  const port = requirePort('abrir o monitor');
  if (!port) return;
  const baud = Number(baudSelect.value || '115200');
  const data = await api('/api/serial/open', { method: 'POST', body: JSON.stringify({ port, baud }) });
  serialSessionId = data.sessionId;
  serialMode.textContent = data.fake ? 'Modo simulação (dev)' : `Lendo a placa de verdade @ ${baud}`;
  serialMode.classList.toggle('sim', !!data.fake);
  serialBox.textContent += `Monitor aberto em ${port} @ ${baud}.\n`;
  serialWs = new WebSocket(`ws://${location.host}/api/serial/stream/${serialSessionId}?token=${encodeURIComponent(TOKEN)}`);
  serialWs.onmessage = (ev) => {
    serialBox.textContent += `${ev.data}\n`;
    serialBox.scrollTop = serialBox.scrollHeight;
  };
}

async function closeSerial() {
  if (serialWs) serialWs.close();
  if (serialSessionId) await api('/api/serial/close', { method: 'POST', body: JSON.stringify({ sessionId: serialSessionId }) });
  serialBox.textContent += 'Monitor fechado.\n';
  serialSessionId = null;
}

async function clearSerial() {
  if (serialSessionId) await api('/api/serial/clear', { method: 'POST', body: JSON.stringify({ sessionId: serialSessionId }) });
  serialBox.textContent = '';
}

async function sendSerialText() {
  if (!serialSessionId) {
    appendChat('agent', 'Abra o monitor serial antes de enviar mensagem para a placa.');
    return;
  }
  const text = serialInput.value.trim();
  if (!text) return;
  const data = await api('/api/serial/write', { method: 'POST', body: JSON.stringify({ sessionId: serialSessionId, text }) });
  serialInput.value = '';
  serialBox.textContent += `Davi > ${text}\n`;
  appendCard(data.message, data);
}

async function runDiagnostics() {
  const data = await showResult('Gerando diagnóstico do papai', api('/api/diagnostics'), 'diagnostics');
  if (data.boardChoices) renderDevices(data.boardChoices);
  return data;
}

const ACTION_RUNNERS = {
  'arduino.board_list': refreshDevices,
  'arduino.compile': doCompile,
  'arduino.upload': doUpload,
  'serial.open': openSerial,
  'diagnostics.open': runDiagnostics,
  'templates.list': loadTemplates,
};

async function runAction(action) {
  const runner = ACTION_RUNNERS[action.type];
  if (!runner) {
    appendChat('agent', 'Essa ação eu ainda não sei fazer.');
    return;
  }
  if (action.requiresConfirmation && action.type !== 'arduino.upload') {
    if (!confirm(`Posso ${action.label.toLowerCase()}?`)) return;
  }
  try {
    await runner();
  } catch (err) {
    appendChat('agent', `Ops! ${err.message}`);
  }
}

function renderSuggestedActions(actions) {
  suggestedActions.innerHTML = '';
  for (const action of actions || []) {
    const btn = document.createElement('button');
    btn.className = 'suggestion';
    btn.textContent = action.requiresConfirmation ? `${action.label} (confirmar)` : action.label;
    btn.onclick = () => runAction(action);
    suggestedActions.appendChild(btn);
  }
}

function readFileAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('Não consegui ler a imagem.'));
    reader.readAsDataURL(file);
  });
}

function clearPendingImage() {
  pendingImage = null;
  imageThumb.removeAttribute('src');
  imageName.textContent = '';
  imagePreview.classList.add('hidden');
  imageInput.value = '';
}

async function setPendingImageFromFile(file) {
  if (!file) return;
  if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
    appendChat('agent', 'Rotom! Só consigo ver imagens PNG, JPG, WEBP ou GIF.');
    return;
  }
  if (file.size > MAX_IMAGE_BYTES) {
    appendChat('agent', 'Rotom! Essa imagem é grande demais (máximo 5 MB). Tente uma foto menor.');
    return;
  }
  try {
    const dataUrl = await readFileAsDataURL(file);
    pendingImage = { dataUrl, name: file.name || 'foto colada' };
    imageThumb.src = dataUrl;
    imageName.textContent = pendingImage.name;
    imagePreview.classList.remove('hidden');
  } catch (err) {
    appendChat('agent', `Ops! ${err.message}`);
  }
}

imageAttachBtn.onclick = () => imageInput.click();
imageInput.onchange = () => setPendingImageFromFile(imageInput.files[0]);
imageRemoveBtn.onclick = clearPendingImage;

chatInput.addEventListener('paste', (event) => {
  const items = event.clipboardData && event.clipboardData.items;
  if (!items) return;
  for (const item of items) {
    if (item.type && item.type.startsWith('image/')) {
      const file = item.getAsFile();
      if (file) {
        setPendingImageFromFile(file);
        event.preventDefault();
      }
      break;
    }
  }
});

['dragenter', 'dragover'].forEach((evt) =>
  chatLog.addEventListener(evt, (e) => {
    e.preventDefault();
    chatLog.classList.add('dragover');
  }));
['dragleave', 'drop'].forEach((evt) =>
  chatLog.addEventListener(evt, (e) => {
    e.preventDefault();
    chatLog.classList.remove('dragover');
  }));
chatLog.addEventListener('drop', (e) => {
  const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
  if (file) setPendingImageFromFile(file);
});

chatForm.onsubmit = async (event) => {
  event.preventDefault();
  const message = chatInput.value.trim();
  const image = pendingImage;
  if (!message && !image) return;
  chatInput.value = '';
  appendChat('user', image ? `${message} 📷 ${image.name}`.trim() : message);
  suggestedActions.innerHTML = '';
  clearPendingImage();
  setChatBusy(true);
  const context = { selectedPort: portInput.value.trim() || null, lastResult, boardChoices };
  try {
    const data = image
      ? await api('/api/chat/multimodal', {
          method: 'POST',
          body: JSON.stringify({ message, imageDataUrl: image.dataUrl, context }),
        })
      : await api('/api/chat', {
          method: 'POST',
          body: JSON.stringify({ message, context }),
        });
    appendChat('agent', data.reply);
    chatStatus.textContent = data.offline ? 'Rotom em modo local' : 'Rotom online';
    chatStatus.classList.toggle('offline', !!data.offline);
    renderSuggestedActions(data.suggestedActions);
  } catch (err) {
    appendChat('agent', `Ops! ${err.message}`);
  } finally {
    setChatBusy(false);
    chatInput.focus();
  }
};

function currentMissionText() {
  const focus = missionsState.find((m) => m.status === 'doing') || missionsState.find((m) => m.status === 'todo');
  if (!focus) return missionsState.length ? 'Tudo feito! 🎉 Bora inventar a próxima.' : 'Carregando missões…';
  return `${MISSION_ICON[focus.status] || '⬜'} ${focus.title}`;
}

function nextStepText() {
  const port = portInput.value.trim();
  if (!port) return '1) Clique em “🔎 Procurar minha placa” para eu achar a ESP32.';
  if (lastResult && lastResult.action === 'compile' && lastResult.ok) {
    return `3) Código testado! Se a placa certa for ${port}, clique em “🚀 Enviar para a placa”.`;
  }
  if (lastResult && lastResult.action === 'upload' && lastResult.ok) {
    return `4) Enviado! Clique em “👀 Abrir monitor” para ver a placa falando.`;
  }
  return `2) Placa pronta em ${port}. Clique em “🧪 Testar código”.`;
}

function updateGuide() {
  const cm = document.querySelector('#currentMission');
  const ns = document.querySelector('#nextStep');
  if (cm) cm.textContent = currentMissionText();
  if (ns) ns.textContent = nextStepText();
}

async function loadMissions() {
  if (!missionList) return;
  try {
    const data = await api('/api/missions');
    missionsState = data.missions || [];
    updateGuide();
    missionList.innerHTML = '';
    for (const mission of data.missions || []) {
      const li = document.createElement('li');
      const title = document.createElement('span');
      title.textContent = `${MISSION_ICON[mission.status] || '⬜'} ${mission.title}`;
      li.appendChild(title);
      for (const status of ['todo', 'doing', 'done']) {
        const btn = document.createElement('button');
        btn.className = 'mini';
        btn.textContent = MISSION_ICON[status];
        btn.title = `Marcar como ${status}`;
        btn.onclick = async () => {
          await api(`/api/missions/${encodeURIComponent(mission.id)}/status`, {
            method: 'POST',
            body: JSON.stringify({ status }),
          });
          renderMissionUpdate();
        };
        li.appendChild(btn);
      }
      missionList.appendChild(li);
    }
  } catch (err) {
    // Missions are secondary; keep the hardcoded fallback already in the page.
  }
}

function renderMissionUpdate() {
  return loadMissions();
}

async function loadTemplates() {
  if (!templateList) return;
  try {
    const data = await api('/api/templates');
    templateList.innerHTML = '';
    for (const item of data.templates || []) {
      const card = document.createElement('div');
      card.className = 'template-card';
      card.innerHTML = `<strong>${item.title}</strong><p>${item.description}</p><code>${item.filename}</code>`;
      const preview = document.createElement('button');
      preview.textContent = 'Ver preview';
      preview.onclick = async () => {
        const rendered = await api(`/api/templates/${encodeURIComponent(item.id)}`);
        appendCard(`Preview: ${rendered.title}`, { ok: true, filename: rendered.filename, content: rendered.content });
      };
      const create = document.createElement('button');
      create.textContent = 'Criar sketch';
      create.className = 'danger';
      create.onclick = async () => {
        if (!confirm(`Criar ${item.filename} na pasta do projeto?`)) return;
        const created = await api(`/api/templates/${encodeURIComponent(item.id)}/create`, {
          method: 'POST',
          body: JSON.stringify({ confirmed: true }),
        });
        appendCard(created.message, created);
      };
      card.appendChild(preview);
      card.appendChild(create);
      templateList.appendChild(card);
    }
  } catch (err) {
    templateList.textContent = `Não consegui carregar templates: ${err.message}`;
  }
}

function showSerialMode(fake) {
  serialMode.textContent = fake ? 'Modo simulação (dev)' : 'Pronto para ler a placa';
  serialMode.classList.toggle('sim', !!fake);
}

document.querySelector('#healthBtn').onclick = async () => {
  const health = await showResult('Verificando o laboratório', api('/api/health'));
  showSerialMode(health.fakeSerial);
  await refreshDevices();
};
document.querySelector('#boardsBtn').onclick = refreshDevices;
diagnosticsBtn.onclick = runDiagnostics;
document.querySelector('#compileBtn').onclick = doCompile;
document.querySelector('#uploadBtn').onclick = doUpload;
document.querySelector('#serialOpenBtn').onclick = openSerial;
serialClearBtn.onclick = clearSerial;
serialSendBtn.onclick = sendSerialText;
serialInput.onkeydown = (event) => {
  if (event.key === 'Enter') sendSerialText();
};
document.querySelector('#serialCloseBtn').onclick = closeSerial;

if (!TOKEN) {
  chatStatus.textContent = 'Sem token';
  chatStatus.classList.add('offline');
  const message = tokenMissingMessage();
  appendChat('agent', `Opa! ${message}`);
  setStatus(message, { ok: false, error: 'token_missing' });
  if (templateList) templateList.textContent = 'Abra com ?token=... para carregar os templates seguros.';
} else {
  const chatClearBtn = document.querySelector('#chatClearBtn');
  if (chatClearBtn) chatClearBtn.onclick = clearChat;
  if (!restoreChat()) {
    appendChat('agent', 'Oi, Davi! Eu sou o Rotom Dex ⚡ Clique em Começar para eu procurar sua placa, ou me mande uma mensagem (pode colar foto!).');
  }
  updateGuide();
  loadMissions();
  loadTemplates();
}
