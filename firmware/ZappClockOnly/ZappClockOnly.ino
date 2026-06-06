#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>
#include <SPI.h>
#include <WiFi.h>
#include <WebServer.h>
#include <Preferences.h>
#include "time.h"
#include "wifi_secrets.h"
#include "pika_frames.h"
#include "pokemon_loading_frames.h"

// Zapp Clock - fase 2
// Layout inicial simples + WiFi + NTP.
// Primeira tela: ??:?? grande, segundos ?? pequenos e loading no canto superior esquerdo.
// Depois da primeira sincronizacao, o ESP32 mantem a hora localmente e
// ressincroniza pela internet em intervalo longo para evitar drift.

#define TFT_CS    27
#define TFT_DC    16
#define TFT_RST   17
#define TFT_SCLK  18
#define TFT_MOSI  23
#define TFT_LED_PIN 13

Adafruit_ST7735 tft = Adafruit_ST7735(TFT_CS, TFT_DC, TFT_MOSI, TFT_SCLK, TFT_RST);

// WiFi vem do arquivo .env da raiz do projeto.
// O script scripts/generate_wifi_header.py gera firmware/ZappClockOnly/wifi_secrets.h.
const char* ssid = ZAPP_WIFI_SSID;
const char* password = ZAPP_WIFI_PASSWORD;
Preferences wifiPrefs;
WebServer server(80);

const long gmtOffset_sec = -3 * 3600;  // Brasil/Fortaleza/Brasilia sem horario de verao
const int daylightOffset_sec = 0;

const unsigned long LOADING_FRAME_MS = 180;
const unsigned long CLOCK_UPDATE_MS = 1000;
const unsigned long WIFI_CONNECT_TIMEOUT_MS = 15000;
const unsigned long NTP_FIRST_SYNC_TIMEOUT_MS = 15000;
const unsigned long NTP_RESYNC_INTERVAL_MS = 6UL * 60UL * 60UL * 1000UL;  // 6 horas
const unsigned long WIFI_RETRY_INTERVAL_MS = 60UL * 1000UL;              // se falhar, tenta de novo em 1 min

unsigned long lastLoadingFrame = 0;
unsigned long lastClockUpdate = 0;
unsigned long lastWifiRetry = 0;
unsigned long lastNtpSync = 0;
int loadingFrame = 0;
bool timeSynced = false;
bool wifiConnecting = false;
bool webServerStarted = false;
bool showingPokemonLoading = false;

struct AlarmConfig {
  bool enabled;
  uint8_t hour;
  uint8_t minute;
};

Preferences alarmPrefs;
AlarmConfig alarms[7];  // 0=Domingo, 1=Segunda, ... 6=Sabado
const char* dayNames[7] = {"Domingo", "Segunda", "Terca", "Quarta", "Quinta", "Sexta", "Sabado"};
const char* dayShortNames[7] = {"Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sab"};

char lastHourMinute[6] = "";
char lastSeconds[3] = "";
char lastIpText[16] = "";
char lastNextAlarmText[18] = "";

const char loadingChars[] = {'|', '/', '-', '\\'};

String currentTimeText() {
  if (!timeSynced) return "??:??:??";

  struct tm timeinfo;
  if (!getLocalTime(&timeinfo, 50)) return "??:??:??";

  char buffer[9];
  strftime(buffer, sizeof(buffer), "%H:%M:%S", &timeinfo);
  return String(buffer);
}

String ipText() {
  if (WiFi.status() != WL_CONNECTED) return "--.--.--.--";
  return WiFi.localIP().toString();
}

String twoDigit(uint8_t value) {
  return String(value < 10 ? "0" : "") + String(value);
}

String alarmTimeText(uint8_t day) {
  if (day >= 7) return "--:--";
  return twoDigit(alarms[day].hour) + ":" + twoDigit(alarms[day].minute);
}

bool parseTimeText(const String& text, uint8_t &hour, uint8_t &minute) {
  if (text.length() != 5 || text.charAt(2) != ':') return false;
  int parsedHour = text.substring(0, 2).toInt();
  int parsedMinute = text.substring(3, 5).toInt();
  if (parsedHour < 0 || parsedHour > 23 || parsedMinute < 0 || parsedMinute > 59) return false;
  hour = (uint8_t)parsedHour;
  minute = (uint8_t)parsedMinute;
  return true;
}

void loadAlarmConfigs() {
  alarmPrefs.begin("zeppalarm", true);
  for (uint8_t day = 0; day < 7; day++) {
    String prefix = "d" + String(day);
    alarms[day].enabled = alarmPrefs.getBool((prefix + "en").c_str(), false);
    alarms[day].hour = alarmPrefs.getUChar((prefix + "h").c_str(), 7);
    alarms[day].minute = alarmPrefs.getUChar((prefix + "m").c_str(), 0);
    if (alarms[day].hour > 23) alarms[day].hour = 7;
    if (alarms[day].minute > 59) alarms[day].minute = 0;
  }
  alarmPrefs.end();
  Serial.println("[Zepp] Configuracoes de alarme carregadas da memoria.");
}

void saveAlarmConfigs() {
  alarmPrefs.begin("zeppalarm", false);
  for (uint8_t day = 0; day < 7; day++) {
    String prefix = "d" + String(day);
    alarmPrefs.putBool((prefix + "en").c_str(), alarms[day].enabled);
    alarmPrefs.putUChar((prefix + "h").c_str(), alarms[day].hour);
    alarmPrefs.putUChar((prefix + "m").c_str(), alarms[day].minute);
  }
  alarmPrefs.end();
  Serial.println("[Zepp] Configuracoes de alarme salvas na memoria.");
}

String alarmsJson() {
  String json = "[";
  for (uint8_t day = 0; day < 7; day++) {
    if (day > 0) json += ",";
    json += "{";
    json += "\"day\":" + String(day) + ",";
    json += "\"label\":\"" + String(dayNames[day]) + "\",";
    json += "\"shortLabel\":\"" + String(dayShortNames[day]) + "\",";
    json += "\"enabled\":" + String(alarms[day].enabled ? "true" : "false") + ",";
    json += "\"time\":\"" + alarmTimeText(day) + "\"";
    json += "}";
  }
  json += "]";
  return json;
}

String enabledAlarmsText() {
  String text = "";
  for (uint8_t day = 0; day < 7; day++) {
    if (!alarms[day].enabled) continue;
    if (text.length() > 0) text += ", ";
    text += String(dayShortNames[day]) + " " + alarmTimeText(day);
  }
  if (text.length() == 0) return "nenhum";
  return text;
}

String nextAlarmText(const struct tm& timeinfo) {
  int currentDay = timeinfo.tm_wday;  // 0=Domingo ... 6=Sabado
  int currentMinutes = timeinfo.tm_hour * 60 + timeinfo.tm_min;

  for (uint8_t offset = 0; offset < 7; offset++) {
    uint8_t day = (currentDay + offset) % 7;
    if (!alarms[day].enabled) continue;

    int alarmMinutes = alarms[day].hour * 60 + alarms[day].minute;

    // Se for hoje, so conta se o horario ainda nao passou.
    if (offset == 0 && alarmMinutes <= currentMinutes) continue;

    return String(dayShortNames[day]) + " " + alarmTimeText(day);
  }

  return "nenhum";
}

void drawIpText() {
  String ip = ipText();
  if (ip == String(lastIpText)) return;

  ip.toCharArray(lastIpText, sizeof(lastIpText));
  tft.fillRect(34, 0, 126, 12, ST77XX_BLACK);
  tft.setTextSize(1);
  tft.setTextColor(ST77XX_CYAN, ST77XX_BLACK);

  int16_t x = 34 + (126 - (ip.length() * 6)) / 2;
  if (x < 34) x = 34;
  tft.setCursor(x, 2);
  tft.print(ip);
}

void logStatus(const char* event) {
  Serial.print("[Zepp] ");
  Serial.print(event);
  Serial.print(" | wifi=");
  Serial.print(WiFi.status() == WL_CONNECTED ? "conectado" : "desconectado");
  Serial.print(" | ip=");
  Serial.print(ipText());
  Serial.print(" | ntp=");
  Serial.print(timeSynced ? "sincronizado" : "pendente");
  Serial.print(" | hora=");
  Serial.println(currentTimeText());
}

void handleStatusApi() {
  String json = "{";
  json += "\"wifi\":\"" + String(WiFi.status() == WL_CONNECTED ? "connected" : "disconnected") + "\",";
  json += "\"ip\":\"" + ipText() + "\",";
  json += "\"timeSynced\":" + String(timeSynced ? "true" : "false") + ",";
  json += "\"time\":\"" + currentTimeText() + "\",";
  json += "\"uptimeMs\":" + String(millis()) + ",";
  json += "\"webServer\":\"" + String(webServerStarted ? "started" : "stopped") + "\",";
  json += "\"alarmsSummary\":\"" + enabledAlarmsText() + "\",";
  json += "\"alarms\":" + alarmsJson() + ",";
  json += "\"motors\":\"disabled_in_phase_1\"";
  json += "}";
  server.send(200, "application/json", json);
}

void handleSaveAlarmsApi() {
  AlarmConfig updated[7];
  for (uint8_t day = 0; day < 7; day++) {
    String prefix = "d" + String(day);
    String timeValue = server.arg(prefix + "time");
    uint8_t hour = 7;
    uint8_t minute = 0;

    if (!parseTimeText(timeValue, hour, minute)) {
      server.send(400, "application/json", "{\"ok\":false,\"error\":\"horario invalido\"}");
      Serial.print("[Zepp] Horario de alarme invalido recebido no dia ");
      Serial.println(day);
      return;
    }

    updated[day].enabled = server.hasArg(prefix + "enabled");
    updated[day].hour = hour;
    updated[day].minute = minute;
  }

  for (uint8_t day = 0; day < 7; day++) {
    alarms[day] = updated[day];
  }
  saveAlarmConfigs();
  logStatus("Alarmes atualizados pela pagina web");
  server.send(200, "application/json", "{\"ok\":true,\"alarms\":" + alarmsJson() + "}");
}
void handleHomePage() {
  const char* page = R"HTML(
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Zepp Status</title>
  <style>
    body { font-family: system-ui, sans-serif; background:#101820; color:#f3f7fa; margin:0; padding:24px; }
    .card { max-width:620px; margin:auto; background:#182635; border:1px solid #2f4558; border-radius:18px; padding:20px; box-shadow:0 10px 30px #0006; }
    h1 { margin:0 0 8px; color:#ffd43b; }
    h2 { margin:22px 0 8px; color:#ffd43b; font-size:20px; }
    .hint { color:#9fb3c8; margin-bottom:18px; }
    .row { display:flex; justify-content:space-between; gap:16px; padding:10px 0; border-bottom:1px solid #2f4558; }
    .row:last-child { border-bottom:0; }
    .label { color:#9fb3c8; }
    .value { font-weight:700; text-align:right; }
    .ok { color:#69db7c; }
    .warn { color:#ffd43b; }
    .danger { color:#ff8787; }
    .alarm-grid { display:grid; gap:10px; margin-top:12px; }
    .alarm-row { display:grid; grid-template-columns:1fr auto auto; align-items:center; gap:12px; background:#101820; border:1px solid #2f4558; border-radius:12px; padding:10px; }
    .alarm-row label { color:#dbe7f3; font-weight:700; }
    input[type="time"] { background:#0b141d; color:#f3f7fa; border:1px solid #2f4558; border-radius:8px; padding:7px; font:inherit; }
    input[type="checkbox"] { width:22px; height:22px; accent-color:#ffd43b; }
    button { margin-top:14px; width:100%; border:0; border-radius:12px; padding:12px; background:#ffd43b; color:#101820; font-weight:800; font-size:16px; cursor:pointer; }
    button:disabled { opacity:.6; cursor:wait; }
    .save-status { min-height:20px; margin-top:10px; color:#9fb3c8; }
    footer { margin-top:18px; color:#748da6; font-size:13px; }
  </style>
</head>
<body>
  <main class="card">
    <h1>Zepp Status</h1>
    <div class="hint">Fase 2: relógio + configurações salvas. Alarmes ainda não disparam som.</div>
    <div class="row"><span class="label">Wi-Fi</span><span id="wifi" class="value warn">...</span></div>
    <div class="row"><span class="label">IP</span><span id="ip" class="value">...</span></div>
    <div class="row"><span class="label">Hora</span><span id="time" class="value">...</span></div>
    <div class="row"><span class="label">NTP</span><span id="ntp" class="value warn">...</span></div>
    <div class="row"><span class="label">Uptime</span><span id="uptime" class="value">...</span></div>
    <div class="row"><span class="label">Alarmes ativos</span><span id="alarmsSummary" class="value">...</span></div>
    <div class="row"><span class="label">Motores</span><span id="motors" class="value danger">desativados</span></div>

    <h2>Alarmes por dia</h2>
    <div class="hint">Configure 1 alarme para cada dia da semana. O Zepp salva na memória interna.</div>
    <form id="alarmForm">
      <div id="alarmGrid" class="alarm-grid"></div>
      <button id="saveButton" type="submit">Salvar alarmes no Zepp</button>
      <div id="saveStatus" class="save-status"></div>
    </form>

    <footer>O status atualiza a cada 1 segundo. Se você estiver editando, ele não sobrescreve os campos.</footer>
  </main>
  <script>
    const dayLabels = ['Domingo', 'Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado'];
    const alarmGrid = document.getElementById('alarmGrid');
    const alarmForm = document.getElementById('alarmForm');
    const saveButton = document.getElementById('saveButton');
    const saveStatus = document.getElementById('saveStatus');
    let alarmFormDirty = false;

    function buildAlarmRows() {
      alarmGrid.innerHTML = '';
      dayLabels.forEach((label, day) => {
        const row = document.createElement('div');
        row.className = 'alarm-row';
        row.innerHTML = `
          <label for="d${day}time">${label}</label>
          <input id="d${day}time" name="d${day}time" type="time" value="07:00" required>
          <input id="d${day}enabled" name="d${day}enabled" type="checkbox" value="1" title="Ativar ${label}">
        `;
        alarmGrid.appendChild(row);
      });
    }

    function fillAlarmForm(alarms) {
      if (alarmFormDirty || !Array.isArray(alarms)) return;
      alarms.forEach((alarm) => {
        const time = document.getElementById(`d${alarm.day}time`);
        const enabled = document.getElementById(`d${alarm.day}enabled`);
        if (time) time.value = alarm.time;
        if (enabled) enabled.checked = !!alarm.enabled;
      });
    }

    async function refresh() {
      try {
        const res = await fetch('/api/status');
        const s = await res.json();
        document.getElementById('wifi').textContent = s.wifi;
        document.getElementById('wifi').className = 'value ' + (s.wifi === 'connected' ? 'ok' : 'warn');
        document.getElementById('ip').textContent = s.ip;
        document.getElementById('time').textContent = s.time;
        document.getElementById('ntp').textContent = s.timeSynced ? 'sincronizado' : 'pendente';
        document.getElementById('ntp').className = 'value ' + (s.timeSynced ? 'ok' : 'warn');
        document.getElementById('uptime').textContent = Math.floor(s.uptimeMs / 1000) + ' s';
        document.getElementById('alarmsSummary').textContent = s.alarmsSummary || 'nenhum';
        document.getElementById('motors').textContent = s.motors;
        fillAlarmForm(s.alarms);
      } catch (err) {
        document.getElementById('wifi').textContent = 'sem resposta';
        document.getElementById('wifi').className = 'value danger';
      }
    }

    alarmForm.addEventListener('input', () => {
      alarmFormDirty = true;
      saveStatus.textContent = 'Alterações ainda não salvas.';
    });

    alarmForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      saveButton.disabled = true;
      saveStatus.textContent = 'Salvando no Zepp...';
      try {
        const body = new URLSearchParams(new FormData(alarmForm));
        const res = await fetch('/api/alarms', { method: 'POST', body });
        const data = await res.json();
        if (!res.ok || !data.ok) throw new Error(data.error || 'falha ao salvar');
        alarmFormDirty = false;
        saveStatus.textContent = 'Alarmes salvos na memória do Zepp!';
        await refresh();
      } catch (err) {
        saveStatus.textContent = 'Erro ao salvar: ' + err.message;
      } finally {
        saveButton.disabled = false;
      }
    });

    buildAlarmRows();
    refresh();
    setInterval(refresh, 1000);
  </script>
</body>
</html>
)HTML";
  server.send(200, "text/html; charset=utf-8", page);
}

void startWebServerIfNeeded() {
  if (webServerStarted || WiFi.status() != WL_CONNECTED) return;

  server.on("/", handleHomePage);
  server.on("/api/status", HTTP_GET, handleStatusApi);
  server.on("/api/alarms", HTTP_POST, handleSaveAlarmsApi);
  server.onNotFound([]() {
    server.send(404, "text/plain", "Zepp: rota nao encontrada");
  });
  server.begin();
  webServerStarted = true;
  logStatus("Servidor web iniciado");
  Serial.print("[Zepp] Abra no navegador: http://");
  Serial.println(WiFi.localIP());
}

void drawHourMinuteText(const char* hourMinute) {
  // Nao limpamos a area inteira a cada segundo: isso evita a piscada.
  // Como HH:MM sempre tem 5 caracteres, o fundo do texto ja apaga os pixels antigos.
  tft.setTextSize(4);
  tft.setTextColor(ST77XX_GREEN, ST77XX_BLACK);
  tft.setCursor(31, 50);
  tft.print(hourMinute);
}

void drawSecondsText(const char* seconds) {
  // Segundos pequenos ao lado direito. Tambem sem fillRect para nao piscar.
  // Sempre tem 2 caracteres: "00".."59" ou "??".
  tft.setTextSize(1);
  tft.setTextColor(ST77XX_YELLOW, ST77XX_BLACK);
  tft.setCursor(135, 58);
  tft.print(seconds);
}

void drawNextAlarmText(const String& nextAlarm) {
  String text = "Alarme: " + nextAlarm;
  if (text == String(lastNextAlarmText)) return;

  text.toCharArray(lastNextAlarmText, sizeof(lastNextAlarmText));

  // Texto pequeno, bem abaixo da hora, com tamanho parecido com o mostrador de segundos.
  tft.fillRect(20, 90, 120, 12, ST77XX_BLACK);
  tft.setTextSize(1);
  tft.setTextColor(ST77XX_CYAN, ST77XX_BLACK);

  int16_t x = 20 + (120 - (text.length() * 6)) / 2;
  if (x < 20) x = 20;

  tft.setCursor(x, 92);
  tft.print(text);
}

void drawClockText(const char* hourMinute, const char* seconds) {
  drawHourMinuteText(hourMinute);
  drawSecondsText(seconds);
}

void drawInitialClockLayout() {
  tft.fillScreen(ST77XX_BLACK);
  drawIpText();
  drawClockText("??:??", "??");
  drawNextAlarmText("--:--");
  strcpy(lastHourMinute, "??:??");
  strcpy(lastSeconds, "??");
}

void drawRunningPikaIcon(int frame) {
  // 4 frames 32x24 gerados a partir da referencia de cross-stitch indicada pelo Davi.
  // Fica isolado no canto para nao redesenhar nem piscar o relogio.
  drawPikaFrame(tft, frame, 0, 0);
}

void drawLoadingIcon() {
  if (millis() - lastLoadingFrame < LOADING_FRAME_MS) return;
  lastLoadingFrame = millis();

  if (WiFi.status() == WL_CONNECTED) {
    if (showingPokemonLoading) {
      // O Pokemon usa 32x32 e o Pikachu usa 32x24.
      // Limpa uma vez para remover qualquer sobra antes do Pikachu correr.
      tft.fillRect(0, 0, POKEMON_LOADING_W, POKEMON_LOADING_H, ST77XX_BLACK);
      showingPokemonLoading = false;
      loadingFrame = 0;
    }
    drawRunningPikaIcon(loadingFrame);
    loadingFrame = (loadingFrame + 1) % PIKA_FRAME_COUNT;
    return;
  }

  // Enquanto ainda nao tem Wi-Fi, mostra o Pokemon escolhido pelo Davi.
  // Nao limpamos com fillRect antes: o frame RGB565 ja tem fundo preto.
  // Assim evitamos o efeito de piscar "apaga -> desenha".
  showingPokemonLoading = true;
  drawPokemonLoadingFrame(tft, loadingFrame, 0, 0);
  loadingFrame = (loadingFrame + 1) % POKEMON_LOADING_FRAME_COUNT;
}

bool loadSavedWiFi(String &networkSsid, String &networkPassword) {
  wifiPrefs.begin("zappwifi", true);
  networkSsid = wifiPrefs.getString("ssid", "");
  networkPassword = wifiPrefs.getString("pass", "");
  wifiPrefs.end();
  return networkSsid.length() > 0;
}

bool waitForWiFi(unsigned long timeoutMs) {
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < timeoutMs) {
    drawLoadingIcon();
    delay(20);
  }
  return WiFi.status() == WL_CONNECTED;
}

bool tryConnectWiFi(const char* networkSsid, const char* networkPassword) {
  if (networkSsid == nullptr || networkSsid[0] == '\0') return false;

  wifiConnecting = true;
  WiFi.mode(WIFI_STA);
  // Nao usar WiFi.disconnect(true): true pode apagar credenciais salvas do ESP32.
  WiFi.disconnect(false);
  delay(150);
  WiFi.begin(networkSsid, networkPassword);

  Serial.println("[Zepp] Conectando WiFi...");

  bool connected = waitForWiFi(WIFI_CONNECT_TIMEOUT_MS);
  wifiConnecting = false;

  if (connected) {
    drawIpText();
    logStatus("WiFi conectado");
    startWebServerIfNeeded();
  } else {
    logStatus("WiFi nao conectou");
  }

  return connected;
}

bool connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    drawIpText();
    startWebServerIfNeeded();
    return true;
  }

  String savedSsid;
  String savedPassword;

  if (loadSavedWiFi(savedSsid, savedPassword)) {
    Serial.println("[Zepp] Tentando WiFi salvo em Preferences/zappwifi.");
    if (tryConnectWiFi(savedSsid.c_str(), savedPassword.c_str())) {
      return true;
    }
  } else {
    Serial.println("[Zepp] Nenhum WiFi salvo em Preferences/zappwifi.");
  }

  if (strcmp(ssid, "SUA_REDE_WIFI") != 0) {
    Serial.println("[Zepp] Tentando WiFi definido pelo .env/header.");
    if (tryConnectWiFi(ssid, password)) {
      return true;
    }
  }

  return false;
}

bool syncTimeFromNtp(unsigned long timeoutMs) {
  if (WiFi.status() != WL_CONNECTED) return false;

  Serial.println("[Zepp] Sincronizando hora via NTP...");
  configTime(gmtOffset_sec, daylightOffset_sec, "pool.ntp.org", "time.google.com", "time.cloudflare.com");

  unsigned long start = millis();
  struct tm timeinfo;
  while (millis() - start < timeoutMs) {
    drawLoadingIcon();
    if (getLocalTime(&timeinfo, 250)) {
      timeSynced = true;
      lastNtpSync = millis();
      logStatus("Hora NTP sincronizada");
      return true;
    }
    delay(20);
  }

  logStatus("NTP nao respondeu dentro do tempo limite");
  return false;
}

void updateClockDisplay() {
  if (millis() - lastClockUpdate < CLOCK_UPDATE_MS) return;
  lastClockUpdate = millis();
  drawIpText();

  if (!timeSynced) {
    if (strcmp(lastHourMinute, "??:??") != 0 || strcmp(lastSeconds, "??") != 0) {
      drawClockText("??:??", "??");
      strcpy(lastHourMinute, "??:??");
      strcpy(lastSeconds, "??");
    }
    return;
  }

  struct tm timeinfo;
  if (!getLocalTime(&timeinfo, 50)) {
    timeSynced = false;
    drawClockText("??:??", "??");
    strcpy(lastHourMinute, "??:??");
    strcpy(lastSeconds, "??");
    return;
  }

  char hourMinute[6];
  char seconds[3];
  strftime(hourMinute, sizeof(hourMinute), "%H:%M", &timeinfo);
  strftime(seconds, sizeof(seconds), "%S", &timeinfo);

  if (strcmp(hourMinute, lastHourMinute) != 0) {
    drawHourMinuteText(hourMinute);
    strcpy(lastHourMinute, hourMinute);
  }

  if (strcmp(seconds, lastSeconds) != 0) {
    drawSecondsText(seconds);
    strcpy(lastSeconds, seconds);
  }

  drawNextAlarmText(nextAlarmText(timeinfo));
}

void handleWiFiAndTime() {
  unsigned long now = millis();

  // Antes da primeira sincronizacao: tenta WiFi/NTP periodicamente.
  if (!timeSynced) {
    if (now - lastWifiRetry >= WIFI_RETRY_INTERVAL_MS || lastWifiRetry == 0) {
      lastWifiRetry = now;
      if (connectWiFi()) {
        syncTimeFromNtp(NTP_FIRST_SYNC_TIMEOUT_MS);
      }
    }
    return;
  }

  // Depois da primeira sincronizacao: intervalo longo, para evitar drift sem gastar rede toda hora.
  if (now - lastNtpSync >= NTP_RESYNC_INTERVAL_MS) {
    if (connectWiFi()) {
      syncTimeFromNtp(8000);
    }
  }
}

void setup() {
  Serial.begin(115200);

  pinMode(TFT_LED_PIN, OUTPUT);
  digitalWrite(TFT_LED_PIN, HIGH);

  tft.initR(INITR_BLACKTAB);
  tft.setRotation(1);

  loadAlarmConfigs();
  drawInitialClockLayout();
  Serial.println("[Zepp] Fase 4: relogio + WiFi + NTP + pagina web + alarmes salvos.");
  logStatus("Boot concluido");
}

void loop() {
  drawLoadingIcon();
  handleWiFiAndTime();
  if (webServerStarted) {
    server.handleClient();
  }
  updateClockDisplay();
}
