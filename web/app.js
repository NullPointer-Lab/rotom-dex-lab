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
let serialWs = null;
let serialSessionId = null;

function pretty(obj) {
  return JSON.stringify(obj, null, 2);
}

function friendlyResult(data) {
  if (typeof data === 'string') return data;
  if (data.message) return data.message;
  if (data.ok === true) return 'Deu certo! ✅';
  if (data.ok === false) return 'Algo não deu certo. Peça ajuda ao papai.';
  return 'Pronto.';
}

function appendChat(role, text) {
  const item = document.createElement('div');
  item.className = `msg ${role}`;
  item.textContent = `${role === 'user' ? 'Davi' : 'Rotom Dex'}: ${text}`;
  chatLog.appendChild(item);
  chatLog.scrollTop = chatLog.scrollHeight;
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || pretty(data));
  return data;
}

async function showResult(title, promise) {
  deviceStatus.textContent = `${title}...`;
  statusBox.textContent = `${title}...`;
  try {
    const data = await promise;
    deviceStatus.textContent = friendlyResult(data);
    statusBox.textContent = pretty(data);
    return data;
  } catch (err) {
    deviceStatus.textContent = `Ops! ${err.message}`;
    statusBox.textContent = `Erro: ${err.message}`;
    throw err;
  }
}

function selectPort(port) {
  portInput.value = port || '';
}

function renderDevices(data) {
  const devices = data.devices || [];
  deviceSelect.innerHTML = '';
  deviceSelectLabel.classList.toggle('hidden', devices.length <= 1 && !data.needsChoice);

  if (devices.length === 1 && !data.needsChoice) {
    selectPort(devices[0].port);
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
      option.textContent = device.label || `${device.name} em ${device.port}`;
      deviceSelect.appendChild(option);
    }
    selectPort('');
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
    alert(`Primeiro clique em “Procurar minha placa”. Depois eu consigo ${actionName}.`);
    return null;
  }
  return port;
}

document.querySelector('#healthBtn').onclick = async () => {
  await showResult('Verificando o laboratório', api('/api/health'));
  await refreshDevices();
};
document.querySelector('#boardsBtn').onclick = refreshDevices;
document.querySelector('#compileBtn').onclick = () => showResult('Testando o código', api('/api/arduino/compile', { method: 'POST', body: '{}' }));
document.querySelector('#uploadBtn').onclick = async () => {
  const port = requirePort('enviar o código para a placa');
  if (!port) return;
  if (!confirm(`Vou enviar o código para ${port}. A placa está certa?`)) return;
  return showResult('Enviando para a placa', api('/api/arduino/upload', {
    method: 'POST',
    body: JSON.stringify({ port, confirmed: true }),
  }));
};

chatForm.onsubmit = async (event) => {
  event.preventDefault();
  const message = chatInput.value.trim();
  if (!message) return;
  chatInput.value = '';
  appendChat('user', message);
  suggestedActions.innerHTML = '';
  try {
    const data = await api('/api/chat', { method: 'POST', body: JSON.stringify({ message }) });
    appendChat('agent', data.reply);
    for (const action of data.suggestedActions || []) {
      const btn = document.createElement('button');
      btn.textContent = `${action.type}${action.requiresConfirmation ? ' (confirmar)' : ''}`;
      btn.onclick = () => alert(`Ação sugerida: ${pretty(action)}\n\nNo MVP, use os botões do painel Arduino para executar.`);
      suggestedActions.appendChild(btn);
    }
  } catch (err) {
    appendChat('agent', `Ops! ${err.message}`);
  }
};

document.querySelector('#serialOpenBtn').onclick = async () => {
  const port = requirePort('abrir o monitor');
  if (!port) return;
  const data = await api('/api/serial/open', { method: 'POST', body: JSON.stringify({ port, baud: 115200 }) });
  serialSessionId = data.sessionId;
  serialBox.textContent += `Monitor aberto em ${port}.\n`;
  serialWs = new WebSocket(`ws://${location.host}/api/serial/stream/${serialSessionId}`);
  serialWs.onmessage = (ev) => {
    serialBox.textContent += `${ev.data}\n`;
    serialBox.scrollTop = serialBox.scrollHeight;
  };
};

document.querySelector('#serialCloseBtn').onclick = async () => {
  if (serialWs) serialWs.close();
  if (serialSessionId) await api('/api/serial/close', { method: 'POST', body: JSON.stringify({ sessionId: serialSessionId }) });
  serialBox.textContent += 'Monitor fechado.\n';
};

appendChat('agent', 'Oi, Davi! Eu sou o Rotom Dex. Clique em Começar para procurar sua placa.');
