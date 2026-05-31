#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>
#include <SPI.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include "time.h"
#include <math.h>

#define ROBOEYES_TFT_MODE
#include <TFT_RoboEyes.h>

#include <Bluepad32.h>   // controle Bluetooth (gamepad) — core esp32-bluepad32

#define TFT_CS    27
#define TFT_DC    16
#define TFT_RST   17
#define TFT_SCLK  18
#define TFT_MOSI  23

#define STOP_SENSOR_PIN 32
#define CONVERSATION_SENSOR_PIN 34
#define BUZZER_PIN 25
#define TFT_LED_PIN 13
#define SENSOR_ACTIVE LOW
#define CONVERSATION_SENSOR_ACTIVE LOW

// ── Ponte H L298N — 2 motores DC do chassi ──────────────────────────────────
// Chassi: motor esquerdo (OUT1/OUT2) + motor direito (OUT3/OUT4) + 1 roda boba.
//
// LIGAÇÃO DE FORÇA (terminais parafuso):
//   +12V  ← (+) do pacote de pilhas (alimenta os MOTORES)
//   GND   ← (−) das pilhas  E TAMBÉM o GND do ESP32  ◄── TERRA COMUM (obrigatório!)
//   +5V   ← ver nota de alimentação abaixo (depende do jumper de 5V)
//   OUT1/OUT2 → motor ESQUERDO     OUT3/OUT4 → motor DIREITO
//
// JUMPERS: deixe os jumpers ENA e ENB COLOCADOS (motores sempre habilitados).
// Aqui o PWM vai direto nas entradas INx, então NÃO ligamos ENA/ENB ao ESP32 —
// economiza 2 GPIOs (o Zapp tem pouquíssimos livres).
//
// SINAIS (pinos de header da L298N ← GPIOs livres do Zapp; 5 e 2 são strapping
// pins: podem dar um tranco mínimo de ~100 ms nos motores no boot):
// Mapa confirmado pelo teste de pinos (qual GPIO move qual roda e p/ que lado):
//   esquerda: GPIO2 = frente, GPIO5 = trás   |   direita: GPIO19 = frente, GPIO4 = trás
// IN1 = pino que faz "frente"; IN2 = pino que faz "trás".
#define MOTOR_L_IN1 2    // motor ESQUERDO  - frente
#define MOTOR_L_IN2 5    //                 - trás
#define MOTOR_R_IN1 19   // motor DIREITO   - frente
#define MOTOR_R_IN2 4    //                 - trás
//
// ⚠️ ALIMENTAÇÃO COM 4×AA (~6V) — a L298N "come" ~2V, então:
//   • Motores recebem só ~4V (ficam fracos). Se puder, use 6×AA (~9V): muito melhor.
//   • Jumper de 5V: a L298N regula o +12V pra 5V (que alimenta a lógica dela).
//     Esse regulador precisa de ~7V+ pra dar 5V firme. Com 6V ele fica no limite
//     e a lógica pode falhar. Duas saídas confiáveis:
//       (a) RECOMENDADO: use 6×AA (9V) com o jumper de 5V COLOCADO → tudo estável.
//       (b) Ficar com 6V: TIRE o jumper de 5V e ligue o terminal +5V da L298N no
//           pino 5V/VIN do ESP32 (quando ele estiver no USB). Nunca faça (a) e (b)
//           juntos. Os 6V vão só no +12V; jamais ligue 6V no 5V/VIN do ESP32.

Adafruit_ST7735 tft = Adafruit_ST7735(TFT_CS, TFT_DC, TFT_MOSI, TFT_SCLK, TFT_RST);
TFTRoboEyes<Adafruit_ST7735> roboEyes(tft);

const char* ssid = "SUA_REDE_WIFI";
const char* password = "SUA_SENHA_WIFI";

const float LATITUDE = -3.7319;
const float LONGITUDE = -38.5267;

const long gmtOffset_sec = -3 * 3600;
const int daylightOffset_sec = 0;

#define ROBOT_BLUE  0x031F
#define FACE_EDGE   ST77XX_CYAN
#define CHEEK       0xF81F
#define CLOUD       0xC618
#define SUNSET_ORANGE 0xFD20

unsigned long robotStartTime;
unsigned long lastBlinkTime = 0;
unsigned long lastClockUpdate = 0;
unsigned long lastWeatherUpdate = 0;
unsigned long lastBuzzerToggle = 0;
unsigned long lastMiniFaceBlink = 0;
unsigned long miniFaceBlinkStarted = 0;
unsigned long lastSensorAction = 0;
unsigned long sensorHoldStart = 0;
unsigned long conversationSensorStart = 0;
unsigned long lastConversationSensorAction = 0;
unsigned long lastRoboEyesFaceChange = 0;

bool eyesOpen = true;
bool clockMode = false;
bool roboEyesFaceMode = false;
bool alarmSoundOn = false;
bool buzzerState = false;
bool miniFaceEyesOpen = true;
bool sensorWasActive = false;
bool sensorHoldTriggered = false;
bool conversationSensorWasActive = false;
bool conversationHoldTriggered = false;
// ── Controle Bluetooth (gamepad) + modo Kart ────────────────────────────────
ControllerPtr gamepad = nullptr;
bool kartMode = false;
int motorTrim = 0;               // -TRIM_MAX..+TRIM_MAX: equilíbrio entre os motores
const int KART_DEADZONE = 120;   // zona morta do analógico (eixo ~ -512..+511)
const int TRIM_MAX = 8;
bool prevTrimL = false, prevTrimR = false, prevKartExit = false;
bool prevMenuA = false, prevMenuB = false, prevMenuNavUp = false, prevMenuNavDown = false;
bool conversationMode = false;
bool hasWeatherData = false;
bool hasTomorrowWeatherData = false;

float temperature = 0;
float tomorrowTempMin = 0;
float tomorrowTempMax = 0;
int weatherCode = -1;
int tomorrowWeatherCode = -1;
int isDay = 1;
int lastAlarmCode = -1;
int lastPeriodMode = -1;
int lastMoonPhase = -1;
int brightnessIndex = 3;
int conversationOption = 0;

const int brightnessLevels[] = {0, 60, 140, 255};

void centerText(const char *text, int y, int size, uint16_t color) {
  int16_t x1, y1;
  uint16_t w, h;
  tft.setTextSize(size);
  tft.getTextBounds(text, 0, y, &x1, &y1, &w, &h);
  int x = (160 - w) / 2;
  tft.setCursor(x, y);
  tft.setTextColor(color);
  tft.print(text);
}

void intro() {
  tft.fillScreen(ST77XX_BLACK);
  centerText("Oi Davi", 48, 3, ST77XX_CYAN);
  delay(1800);
  tft.fillScreen(ST77XX_BLACK);
  delay(400);
  centerText("Meu nome e", 36, 2, ST77XX_WHITE);
  centerText("Zapp", 68, 3, ST77XX_CYAN);
  delay(2200);
  tft.fillScreen(ST77XX_BLACK);
  delay(400);
  centerText("Sou seu", 34, 2, ST77XX_WHITE);
  centerText("assistente", 64, 2, ST77XX_CYAN);
  delay(2200);
  tft.fillScreen(ST77XX_BLACK);
  delay(400);
  centerText("Em que posso", 34, 2, ST77XX_WHITE);
  centerText("ajudar?", 64, 2, ST77XX_CYAN);
  delay(2200);
  tft.fillScreen(ST77XX_BLACK);
  delay(400);
}

void connectWiFiAndTime() {
  tft.fillScreen(ST77XX_BLACK);
  centerText("Conectando", 34, 2, ST77XX_CYAN);
  centerText("WiFi...", 64, 2, ST77XX_WHITE);

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  // Tenta por ~15 s; se não conectar, SEGUE mesmo assim (não trava o robô).
  unsigned long startAttempt = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startAttempt < 15000) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("WiFi conectado. IP: ");
    Serial.println(WiFi.localIP());
    configTime(gmtOffset_sec, daylightOffset_sec, "pool.ntp.org", "time.google.com");
    tft.fillScreen(ST77XX_BLACK);
    centerText("Hora online", 44, 2, ST77XX_GREEN);
    delay(1200);
  } else {
    Serial.println("WiFi NAO conectou (timeout). Seguindo sem hora online.");
    tft.fillScreen(ST77XX_BLACK);
    centerText("Sem WiFi", 44, 2, ST77XX_RED);
    delay(1200);
  }
}

void drawRobotBase() {
  tft.fillScreen(ST77XX_BLACK);
  tft.fillRoundRect(24, 12, 112, 82, 12, ROBOT_BLUE);
  tft.drawRoundRect(24, 12, 112, 82, 12, FACE_EDGE);
  tft.fillRoundRect(12, 38, 12, 28, 4, FACE_EDGE);
  tft.fillRoundRect(136, 38, 12, 28, 4, FACE_EDGE);
  tft.fillCircle(43, 68, 4, CHEEK);
  tft.fillCircle(117, 68, 4, CHEEK);
  tft.drawLine(58, 68, 66, 74, ST77XX_BLACK);
  tft.drawLine(66, 74, 80, 77, ST77XX_BLACK);
  tft.drawLine(80, 77, 94, 74, ST77XX_BLACK);
  tft.drawLine(94, 74, 102, 68, ST77XX_BLACK);
  tft.drawLine(58, 69, 66, 75, ST77XX_BLACK);
  tft.drawLine(66, 75, 80, 78, ST77XX_BLACK);
  tft.drawLine(80, 78, 94, 75, ST77XX_BLACK);
  tft.drawLine(94, 75, 102, 69, ST77XX_BLACK);
}

void drawOpenEyes() {
  tft.fillRoundRect(38, 30, 84, 28, 6, ROBOT_BLUE);
  tft.fillRoundRect(45, 34, 28, 20, 8, ST77XX_WHITE);
  tft.fillRoundRect(87, 34, 28, 20, 8, ST77XX_WHITE);
  tft.fillCircle(59, 44, 5, ST77XX_BLACK);
  tft.fillCircle(101, 44, 5, ST77XX_BLACK);
  tft.fillCircle(57, 42, 2, ST77XX_WHITE);
  tft.fillCircle(99, 42, 2, ST77XX_WHITE);
}

void drawClosedEyes() {
  tft.fillRoundRect(38, 30, 84, 28, 6, ROBOT_BLUE);
  tft.drawLine(46, 44, 72, 44, ST77XX_WHITE);
  tft.drawLine(46, 45, 72, 45, ST77XX_WHITE);
  tft.drawLine(88, 44, 114, 44, ST77XX_WHITE);
  tft.drawLine(88, 45, 114, 45, ST77XX_WHITE);
}

void drawHappyEyes() {
  tft.fillRoundRect(38, 30, 84, 28, 6, ROBOT_BLUE);
  tft.drawLine(46, 46, 59, 38, ST77XX_WHITE);
  tft.drawLine(59, 38, 72, 46, ST77XX_WHITE);
  tft.drawLine(88, 46, 101, 38, ST77XX_WHITE);
  tft.drawLine(101, 38, 114, 46, ST77XX_WHITE);
}

void drawSleepyEyes() {
  tft.fillRoundRect(38, 30, 84, 28, 6, ROBOT_BLUE);
  tft.drawLine(45, 39, 72, 45, ST77XX_WHITE);
  tft.drawLine(88, 45, 115, 39, ST77XX_WHITE);
}

void drawSurprisedMouth() {
  tft.fillCircle(80, 74, 9, ST77XX_BLACK);
  tft.drawCircle(80, 74, 9, ST77XX_CYAN);
}

void drawTongueMouth() {
  tft.fillRoundRect(62, 67, 36, 12, 5, ST77XX_BLACK);
  tft.fillRoundRect(73, 75, 14, 12, 6, ST77XX_RED);
}

void drawKissMouth() {
  tft.fillCircle(75, 73, 5, ST77XX_BLACK);
  tft.fillCircle(85, 73, 5, ST77XX_BLACK);
  tft.drawCircle(117, 70, 5, CHEEK);
}

void updateRobotAnimation() {
  roboEyes.update();

  unsigned long now = millis();
  if (now - lastBlinkTime >= 3000) {
    roboEyes.setMood(HAPPY);
    roboEyes.blink();
    lastBlinkTime = now;
  }
}

void snapRoboEyes(unsigned char mood, unsigned char position) {
  roboEyes.setMood(mood);
  roboEyes.setPosition(position);
  for (int i = 0; i < 8; i++) {
    roboEyes.drawEyes();
  }
}

void snapRoboBlink() {
  roboEyes.close();
  for (int i = 0; i < 4; i++) {
    roboEyes.drawEyes();
  }
  roboEyes.open();
  for (int i = 0; i < 6; i++) {
    roboEyes.drawEyes();
  }
}

float getNumberFromCurrent(String json, const char* key) {
  int currentPos = json.indexOf("\"current\":");
  if (currentPos < 0) return 0;

  String searchKey = String("\"") + key + "\":";
  int pos = json.indexOf(searchKey, currentPos);
  if (pos < 0) return 0;

  pos = json.indexOf(':', pos) + 1;
  while (json[pos] == ' ' || json[pos] == '"') pos++;

  int endPos = pos;
  while ((json[endPos] >= '0' && json[endPos] <= '9') || json[endPos] == '-' || json[endPos] == '.') {
    endPos++;
  }

  return json.substring(pos, endPos).toFloat();
}

bool currentHasKey(String json, const char* key) {
  int currentPos = json.indexOf("\"current\":");
  if (currentPos < 0) return false;

  String searchKey = String("\"") + key + "\":";
  return json.indexOf(searchKey, currentPos) >= 0;
}

float getNumberFromArray(String json, const char* key, int wantedIndex) {
  String searchKey = String("\"") + key + "\":[";
  int keyPos = json.indexOf(searchKey);
  if (keyPos < 0) return 0;

  int pos = json.indexOf('[', keyPos) + 1;

  for (int index = 0; index <= wantedIndex; index++) {
    while (json[pos] == ' ' || json[pos] == '"') pos++;

    if (index == wantedIndex) {
      int endPos = pos;
      while ((json[endPos] >= '0' && json[endPos] <= '9') || json[endPos] == '-' || json[endPos] == '.') {
        endPos++;
      }
      return json.substring(pos, endPos).toFloat();
    }

    pos = json.indexOf(',', pos);
    if (pos < 0) return 0;
    pos++;
  }

  return 0;
}

bool fetchWeather() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi caiu. Tentando reconectar...");
    WiFi.disconnect();
    WiFi.begin(ssid, password);
    unsigned long startAttempt = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - startAttempt < 10000) {
      delay(250);
    }
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Sem WiFi para buscar clima.");
    return false;
  }

  String url = "https://api.open-meteo.com/v1/forecast?latitude=";
  url += String(LATITUDE, 4);
  url += "&longitude=";
  url += String(LONGITUDE, 4);
  url += "&current=temperature_2m,weather_code,is_day";
  url += "&daily=weather_code,temperature_2m_max,temperature_2m_min";
  url += "&forecast_days=2&timezone=auto";

  WiFiClientSecure client;
  client.setInsecure();

  HTTPClient http;
  http.setTimeout(15000);
  http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);
  http.begin(client, url);

  int httpCode = http.GET();
  Serial.print("HTTP clima: ");
  Serial.println(httpCode);

  if (httpCode != 200) {
    http.end();
    return false;
  }

  String payload = http.getString();
  http.end();

  if (!currentHasKey(payload, "temperature_2m") ||
      !currentHasKey(payload, "weather_code") ||
      !currentHasKey(payload, "is_day")) {
    Serial.println("Resposta do clima veio sem os campos esperados.");
    return false;
  }

  temperature = getNumberFromCurrent(payload, "temperature_2m");
  weatherCode = (int)getNumberFromCurrent(payload, "weather_code");
  isDay = (int)getNumberFromCurrent(payload, "is_day");
  hasWeatherData = true;

  if (payload.indexOf("\"daily\":") >= 0 && payload.indexOf("\"temperature_2m_max\"") >= 0) {
    tomorrowWeatherCode = (int)getNumberFromArray(payload, "weather_code", 1);
    tomorrowTempMax = getNumberFromArray(payload, "temperature_2m_max", 1);
    tomorrowTempMin = getNumberFromArray(payload, "temperature_2m_min", 1);
    hasTomorrowWeatherData = true;
  } else {
    hasTomorrowWeatherData = false;
  }

  Serial.print("Temperatura: ");
  Serial.println(temperature);
  Serial.print("Codigo clima: ");
  Serial.println(weatherCode);
  Serial.print("Dia/noite: ");
  Serial.println(isDay);

  return true;
}

void drawSun(int x, int y, int r) {
  tft.fillCircle(x, y, r, ST77XX_YELLOW);
  tft.drawLine(x, y - r - 8, x, y - r - 2, ST77XX_YELLOW);
  tft.drawLine(x, y + r + 2, x, y + r + 8, ST77XX_YELLOW);
  tft.drawLine(x - r - 8, y, x - r - 2, y, ST77XX_YELLOW);
  tft.drawLine(x + r + 2, y, x + r + 8, y, ST77XX_YELLOW);
}

void drawCloud(int x, int y) {
  tft.fillCircle(x + 12, y + 18, 10, CLOUD);
  tft.fillCircle(x + 28, y + 12, 14, CLOUD);
  tft.fillCircle(x + 44, y + 18, 10, CLOUD);
  tft.fillRoundRect(x + 6, y + 18, 48, 16, 7, CLOUD);
}

void drawRain(int x, int y) {
  for (int i = 0; i < 4; i++) {
    int rx = x + i * 10;
    tft.drawLine(rx, y, rx - 4, y + 10, ST77XX_CYAN);
    tft.drawLine(rx + 1, y, rx - 3, y + 10, ST77XX_CYAN);
  }
}

void drawLightning(int x, int y) {
  tft.fillTriangle(x, y, x + 12, y, x + 3, y + 18, ST77XX_YELLOW);
  tft.fillTriangle(x + 3, y + 14, x + 15, y + 14, x - 4, y + 34, ST77XX_YELLOW);
}

void drawMoon(int x, int y) {
  tft.fillCircle(x, y, 14, ST77XX_YELLOW);
  tft.fillCircle(x + 7, y - 4, 14, ST77XX_BLACK);
}

void drawSunset(int x, int y) {
  tft.fillCircle(x, y, 9, SUNSET_ORANGE);
  tft.fillRect(x - 12, y, 24, 12, ST77XX_BLACK);
  tft.drawFastHLine(x - 14, y, 28, SUNSET_ORANGE);
  tft.drawFastHLine(x - 18, y + 5, 36, ST77XX_RED);
}

int getPeriodMode(int hour) {
  if (hour >= 5 && hour < 12) return 0;
  if (hour >= 12 && hour < 18) return 1;
  return 2;
}

int getMoonPhase(struct tm timeinfo) {
  int year = timeinfo.tm_year + 1900;
  int month = timeinfo.tm_mon + 1;
  int day = timeinfo.tm_mday;

  if (month < 3) {
    year--;
    month += 12;
  }

  month++;
  double days = floor(365.25 * year) + floor(30.6 * month) + day - 694039.09;
  double cycles = days / 29.5305882;
  cycles = cycles - floor(cycles);

  int phase = (int)(cycles * 8 + 0.5);
  return phase & 7;
}

void drawMoonPhaseIcon(int x, int y, int phase) {
  uint16_t moonColor = ST77XX_YELLOW;
  uint16_t outlineColor = 0x8410;

  tft.fillCircle(x, y, 7, moonColor);

  if (phase == 0) {
    tft.fillCircle(x, y, 7, ST77XX_BLACK);
    tft.drawCircle(x, y, 7, outlineColor);
  } else if (phase == 1) {
    tft.fillCircle(x - 4, y, 7, ST77XX_BLACK);
  } else if (phase == 2) {
    tft.fillRect(x - 7, y - 7, 7, 15, ST77XX_BLACK);
  } else if (phase == 3) {
    tft.fillCircle(x - 8, y, 7, ST77XX_BLACK);
  } else if (phase == 4) {
    tft.fillCircle(x, y, 7, moonColor);
  } else if (phase == 5) {
    tft.fillCircle(x + 8, y, 7, ST77XX_BLACK);
  } else if (phase == 6) {
    tft.fillRect(x, y - 7, 8, 15, ST77XX_BLACK);
  } else {
    tft.fillCircle(x + 4, y, 7, ST77XX_BLACK);
  }

  tft.drawCircle(x, y, 7, outlineColor);
}

void drawPeriodIcon(struct tm timeinfo) {
  int periodMode = getPeriodMode(timeinfo.tm_hour);
  int moonPhase = periodMode == 2 ? getMoonPhase(timeinfo) : -1;

  if (periodMode == lastPeriodMode && moonPhase == lastMoonPhase) return;

  lastPeriodMode = periodMode;
  lastMoonPhase = moonPhase;
  tft.fillRect(132, 2, 26, 23, ST77XX_BLACK);

  if (periodMode == 0) {
    tft.fillCircle(145, 11, 5, ST77XX_YELLOW);
    tft.drawLine(145, 3, 145, 5, ST77XX_YELLOW);
    tft.drawLine(145, 17, 145, 19, ST77XX_YELLOW);
    tft.drawLine(137, 11, 139, 11, ST77XX_YELLOW);
    tft.drawLine(151, 11, 153, 11, ST77XX_YELLOW);
  } else if (periodMode == 1) {
    drawSunset(145, 13);
  } else {
    drawMoonPhaseIcon(145, 11, moonPhase);
  }
}

void drawSmallSun(int x, int y) {
  tft.fillCircle(x, y, 7, ST77XX_YELLOW);
  tft.drawLine(x, y - 13, x, y - 10, ST77XX_YELLOW);
  tft.drawLine(x, y + 10, x, y + 13, ST77XX_YELLOW);
  tft.drawLine(x - 13, y, x - 10, y, ST77XX_YELLOW);
  tft.drawLine(x + 10, y, x + 13, y, ST77XX_YELLOW);
}

void drawSmallCloud(int x, int y) {
  tft.fillCircle(x + 7, y + 11, 6, CLOUD);
  tft.fillCircle(x + 18, y + 8, 8, CLOUD);
  tft.fillCircle(x + 29, y + 11, 6, CLOUD);
  tft.fillRoundRect(x + 4, y + 11, 32, 10, 5, CLOUD);
}

void drawSmallRain(int x, int y) {
  for (int i = 0; i < 3; i++) {
    int rx = x + i * 9;
    tft.drawLine(rx, y, rx - 3, y + 8, ST77XX_CYAN);
    tft.drawLine(rx + 1, y, rx - 2, y + 8, ST77XX_CYAN);
  }
}

void drawSmallLightning(int x, int y) {
  tft.fillTriangle(x, y, x + 9, y, x + 2, y + 13, ST77XX_YELLOW);
  tft.fillTriangle(x + 2, y + 10, x + 12, y + 10, x - 3, y + 26, ST77XX_YELLOW);
}

void drawSmallMoon(int x, int y) {
  tft.fillCircle(x, y, 9, ST77XX_YELLOW);
  tft.fillCircle(x + 5, y - 3, 9, ST77XX_BLACK);
}

// Mini RoboEyes-style eyes (top-left corner of the clock screen),
// replacing the old blue face. Two cyan rounded rects that collapse to a
// thin bar when blinking, mimicking the RoboEyes look.
#define MINI_EYE_W      8
#define MINI_EYE_H      11
#define MINI_EYE_R      3
#define MINI_EYE_LX     8
#define MINI_EYE_RX     22
#define MINI_EYE_Y      5
#define MINI_EYE_COLOR  ST77XX_CYAN

void drawMiniZappEyes(bool openEyes) {
  // erase only the eye region to keep the blink flicker-free
  tft.fillRect(MINI_EYE_LX, MINI_EYE_Y,
               (MINI_EYE_RX + MINI_EYE_W) - MINI_EYE_LX, MINI_EYE_H,
               ST77XX_BLACK);

  if (openEyes) {
    tft.fillRoundRect(MINI_EYE_LX, MINI_EYE_Y, MINI_EYE_W, MINI_EYE_H,
                      MINI_EYE_R, MINI_EYE_COLOR);
    tft.fillRoundRect(MINI_EYE_RX, MINI_EYE_Y, MINI_EYE_W, MINI_EYE_H,
                      MINI_EYE_R, MINI_EYE_COLOR);
  } else {
    int by = MINI_EYE_Y + (MINI_EYE_H / 2) - 1;
    tft.fillRoundRect(MINI_EYE_LX, by, MINI_EYE_W, 3, 1, MINI_EYE_COLOR);
    tft.fillRoundRect(MINI_EYE_RX, by, MINI_EYE_W, 3, 1, MINI_EYE_COLOR);
  }
}

void drawMiniZappFace(bool openEyes) {
  tft.fillRect(4, 1, 31, 20, ST77XX_BLACK);  // clear the old mini-face area
  drawMiniZappEyes(openEyes);
}

void updateMiniZappFace() {
  if (!clockMode || alarmSoundOn) return;

  unsigned long now = millis();

  if (miniFaceEyesOpen && now - lastMiniFaceBlink >= 2800) {
    drawMiniZappEyes(false);
    miniFaceEyesOpen = false;
    miniFaceBlinkStarted = now;
  }

  if (!miniFaceEyesOpen && now - miniFaceBlinkStarted >= 160) {
    drawMiniZappEyes(true);
    miniFaceEyesOpen = true;
    lastMiniFaceBlink = now;
  }
}

void clearWeatherArea() {
  tft.fillRect(6, 78, 148, 48, ST77XX_BLACK);
}

void drawWeatherInfo() {
  clearWeatherArea();
  const char* label = "Clima";

  if (weatherCode == 0 || weatherCode == 1) {
    if (isDay == 1) {
      drawSmallSun(30, 102);
      label = "Sol";
    } else {
      drawSmallMoon(30, 102);
      label = "Noite";
    }
  } else if (weatherCode == 2) {
    drawSmallSun(23, 96);
    drawSmallCloud(23, 94);
    label = "Parcial";
  } else if (weatherCode == 3) {
    drawSmallCloud(22, 92);
    label = "Nublado";
  } else if (weatherCode == 45 || weatherCode == 48) {
    drawSmallCloud(22, 88);
    tft.drawFastHLine(17, 114, 45, ST77XX_WHITE);
    tft.drawFastHLine(13, 120, 54, ST77XX_WHITE);
    label = "Neblina";
  } else if ((weatherCode >= 51 && weatherCode <= 67) || (weatherCode >= 80 && weatherCode <= 82)) {
    drawSmallCloud(22, 86);
    drawSmallRain(30, 112);
    label = "Chuva";
  } else if (weatherCode >= 95) {
    drawSmallCloud(22, 86);
    drawSmallLightning(40, 106);
    label = "Tempestade";
  }

  tft.setTextSize(1);
  tft.setTextColor(ST77XX_WHITE, ST77XX_BLACK);
  tft.setCursor(78, 80);
  tft.print(label);

  char tempText[12];
  snprintf(tempText, sizeof(tempText), "%.1fC", temperature);
  tft.setTextSize(2);
  tft.setTextColor(ST77XX_YELLOW, ST77XX_BLACK);
  tft.setCursor(78, 94);
  tft.print(tempText);
}

void showClockScreen() {
  tft.fillScreen(ST77XX_BLACK);
  centerText("Zapp", 2, 2, ST77XX_CYAN);
  drawMiniZappFace(true);
  miniFaceEyesOpen = true;
  lastMiniFaceBlink = millis();
  lastPeriodMode = -1;
  lastMoonPhase = -1;

  tft.drawRoundRect(4, 22, 152, 38, 7, ST77XX_BLUE);
  tft.drawRoundRect(4, 70, 152, 56, 7, ST77XX_BLUE);
  tft.setTextSize(3);
  tft.setTextColor(ST77XX_GREEN, ST77XX_BLACK);
  tft.setCursor(8, 31);
  tft.print("--:--:--");
  centerText("--/--/----", 62, 1, ST77XX_WHITE);
  centerText("Fortaleza", 72, 1, ST77XX_CYAN);

  if (!hasWeatherData && fetchWeather()) {
    lastWeatherUpdate = millis();
  }

  if (hasWeatherData) {
    drawWeatherInfo();
  } else {
    showWeatherErrorIfNeeded();
  }
}

void showAlarmOnScreen() {
  tft.fillScreen(ST77XX_BLACK);
  centerText("DESPERTADOR", 28, 1, ST77XX_RED);
  centerText("05:00", 48, 3, ST77XX_YELLOW);
  centerText("Passe a mao", 88, 2, ST77XX_CYAN);
  centerText("no sensor", 112, 1, ST77XX_WHITE);
}

void pauseWakePage(unsigned long waitMs) {
  delay(waitMs);
  tft.fillScreen(ST77XX_BLACK);
  delay(350);
}

void showWakeOneBig(const char* text, uint16_t color) {
  tft.fillScreen(ST77XX_BLACK);
  centerText(text, 48, 3, color);
  pauseWakePage(2200);
}

void showWakeTwoLines(const char* line1, const char* line2, uint16_t color1, uint16_t color2) {
  tft.fillScreen(ST77XX_BLACK);
  centerText(line1, 34, 2, color1);
  centerText(line2, 64, 2, color2);
  pauseWakePage(2400);
}

void showWakeThreeLines(const char* line1, const char* line2, const char* line3) {
  tft.fillScreen(ST77XX_BLACK);
  centerText(line1, 22, 2, ST77XX_YELLOW);
  centerText(line2, 54, 2, ST77XX_CYAN);
  centerText(line3, 86, 2, ST77XX_GREEN);
  pauseWakePage(3000);
}

void showMondayWakeMessages() {
  showWakeOneBig("Oi Davi", ST77XX_CYAN);
  showWakeOneBig("Estude", ST77XX_GREEN);
}

void showTuesdayThursdayWakeMessages() {
  showWakeOneBig("Oi Davi", ST77XX_CYAN);
  showWakeTwoLines("Temos muita", "coisa hoje:", ST77XX_WHITE, ST77XX_CYAN);
  showWakeThreeLines("Judo", "Natacao", "Ingles");
}

void showWednesdayWakeMessages() {
  showWakeOneBig("Oi Davi", ST77XX_CYAN);
  showWakeTwoLines("Hoje temos", "pouca coisa:", ST77XX_WHITE, ST77XX_CYAN);
  showWakeTwoLines("So temos", "Eucaristia", ST77XX_GREEN, ST77XX_YELLOW);
}

void showFridayWakeMessages() {
  showWakeOneBig("Oi Davi", ST77XX_CYAN);
  showWakeOneBig("Estude", ST77XX_GREEN);
}

void showSaturdayWakeMessages() {
  showWakeOneBig("Oi Davi", ST77XX_CYAN);
  showWakeTwoLines("Seu dia", "de folga!", ST77XX_GREEN, ST77XX_CYAN);
}

void showSundayWakeMessages() {
  showWakeOneBig("Oi Davi", ST77XX_CYAN);
  showWakeTwoLines("Voce se", "arrume!!!", ST77XX_GREEN, ST77XX_CYAN);
}

void showWakeUpMessages() {
  struct tm timeinfo;

  if (!getLocalTime(&timeinfo, 1000)) {
    showWakeOneBig("Oi Davi", ST77XX_CYAN);
    showWakeTwoLines("Bom dia", "Davi", ST77XX_WHITE, ST77XX_YELLOW);
    return;
  }

  if (timeinfo.tm_wday == 0) {
    showSundayWakeMessages();
  } else if (timeinfo.tm_wday == 1) {
    showMondayWakeMessages();
  } else if (timeinfo.tm_wday == 2 || timeinfo.tm_wday == 4) {
    showTuesdayThursdayWakeMessages();
  } else if (timeinfo.tm_wday == 3) {
    showWednesdayWakeMessages();
  } else if (timeinfo.tm_wday == 5) {
    showFridayWakeMessages();
  } else if (timeinfo.tm_wday == 6) {
    showSaturdayWakeMessages();
  } else {
    showWakeOneBig("Oi Davi", ST77XX_CYAN);
  }
}

void drawHeart(int x, int y, uint16_t color) {
  tft.fillCircle(x - 3, y - 2, 4, color);
  tft.fillCircle(x + 3, y - 2, 4, color);
  tft.fillTriangle(x - 8, y, x + 8, y, x, y + 10, color);
}

void drawPettingFace() {
  drawRobotBase();
  tft.fillRoundRect(38, 30, 84, 28, 6, ROBOT_BLUE);
  tft.drawLine(46, 46, 59, 38, ST77XX_WHITE);
  tft.drawLine(59, 38, 72, 46, ST77XX_WHITE);
  tft.drawLine(88, 46, 101, 38, ST77XX_WHITE);
  tft.drawLine(101, 38, 114, 46, ST77XX_WHITE);
  drawHeart(35, 106, CHEEK);
  drawHeart(125, 106, CHEEK);
  centerText("Carinho", 104, 2, ST77XX_CYAN);
}

void drawTalkingFace(const char* text) {
  drawRobotBase();
  drawOpenEyes();
  tft.fillRoundRect(68, 66, 24, 14, 5, ST77XX_BLACK);
  centerText(text, 104, 2, ST77XX_CYAN);
}

const char* getWeatherLabelFromCode(int code, int dayValue) {
  if (code == 0 || code == 1) return dayValue == 1 ? "ensolarado" : "limpo";
  if (code == 2) return "parcial";
  if (code == 3) return "nublado";
  if (code == 45 || code == 48) return "com neblina";
  if ((code >= 51 && code <= 67) || (code >= 80 && code <= 82)) return "chuvoso";
  if (code >= 95) return "tempestade";
  return "diferente";
}

const char* getWeatherTalkLabel() {
  return getWeatherLabelFromCode(weatherCode, isDay);
}

const char* getMoonPhaseLabel(int phase) {
  if (phase == 0) return "Nova";
  if (phase == 1) return "Crescente";
  if (phase == 2) return "Quarto cres.";
  if (phase == 3) return "Gibosa cres.";
  if (phase == 4) return "Cheia";
  if (phase == 5) return "Gibosa ming.";
  if (phase == 6) return "Quarto ming.";
  return "Minguante";
}

const char* getTemperatureTalkLabel() {
  if (temperature >= 30) return "quente";
  if (temperature >= 25) return "agradavel";
  if (temperature >= 20) return "fresquinho";
  return "frio";
}

void showTalkWeather() {
  if (!hasWeatherData) {
    fetchWeather();
  }

  if (!hasWeatherData) {
    showWakeTwoLines("Nao achei", "o clima", ST77XX_WHITE, ST77XX_YELLOW);
    return;
  }

  char tempText[14];
  snprintf(tempText, sizeof(tempText), "%.1fC", temperature);
  showWakeTwoLines("Hoje esta", getWeatherTalkLabel(), ST77XX_WHITE, ST77XX_CYAN);
  showWakeTwoLines(tempText, getTemperatureTalkLabel(), ST77XX_YELLOW, ST77XX_GREEN);
}

void showTalkEvents(int weekDay) {
  if (weekDay == 0) {
    showWakeTwoLines("Hoje voce", "se arruma!", ST77XX_WHITE, ST77XX_CYAN);
  } else if (weekDay == 1 || weekDay == 5) {
    showWakeTwoLines("Voce tem", "estudo", ST77XX_WHITE, ST77XX_GREEN);
  } else if (weekDay == 2 || weekDay == 4) {
    showWakeTwoLines("Voce tem", "hoje:", ST77XX_WHITE, ST77XX_CYAN);
    showWakeThreeLines("Judo", "Natacao", "Ingles");
  } else if (weekDay == 3) {
    showWakeTwoLines("Voce tem", "Eucaristia", ST77XX_WHITE, ST77XX_YELLOW);
  } else if (weekDay == 6) {
    showWakeTwoLines("Hoje e", "folga!", ST77XX_GREEN, ST77XX_CYAN);
  }
}

void showPettingMode() {
  drawPettingFace();
  delay(1800);
  showClockScreen();
}

const char* CONV_LABELS[] = {"Exit", "time", "information", "word", "face", "kart", "teste"};
const int MENU_COUNT = 7;

const char* getConversationOptionLabel(int option) {
  return CONV_LABELS[option];
}

void drawConversationOption(int option, int y) {
  bool selected = option == conversationOption;
  uint16_t bg = selected ? ST77XX_CYAN : ST77XX_BLACK;
  uint16_t fg = selected ? ST77XX_BLACK : ST77XX_WHITE;

  tft.fillRoundRect(16, y - 2, 128, 13, 3, bg);
  tft.setTextSize(1);
  tft.setTextColor(fg, bg);
  tft.setCursor(24, y);
  tft.print(option + 1);
  tft.print(" ");
  tft.print(getConversationOptionLabel(option));
}

void showConversationScreen() {
  tft.fillScreen(ST77XX_BLACK);
  centerText("Quer o que?", 4, 2, ST77XX_CYAN);
  tft.drawRoundRect(6, 24, 148, 102, 5, ST77XX_BLUE);
  for (int i = 0; i < MENU_COUNT; i++) drawConversationOption(i, 28 + i * 14);
}

// Muda a opção redesenhando só as 2 linhas afetadas (sem repintar a tela toda).
void moveConversationOption(int delta) {
  int prev = conversationOption;
  conversationOption = (conversationOption + delta + MENU_COUNT) % MENU_COUNT;
  if (conversationOption == prev) return;
  drawConversationOption(prev, 28 + prev * 14);
  drawConversationOption(conversationOption, 28 + conversationOption * 14);
}

void finishConversationAction() {
  if (conversationMode) {
    showConversationScreen();
  } else {
    showClockScreen();
  }
}

void showZappGreeting() {
  drawTalkingFace("Oi Davi");
  delay(2200);
  finishConversationAction();
}

void showDateInfo() {
  struct tm timeinfo;

  if (!getLocalTime(&timeinfo, 1000)) {
    showWakeTwoLines("Nao achei", "a data", ST77XX_WHITE, ST77XX_YELLOW);
    finishConversationAction();
    return;
  }

  char data[11];
  strftime(data, sizeof(data), "%d/%m/%Y", &timeinfo);
  showWakeTwoLines("Data", data, ST77XX_WHITE, ST77XX_CYAN);
  finishConversationAction();
}

void showScheduleOnly(int weekDay) {
  showTalkEvents(weekDay);
}

const char* getSpecialEventLabel(struct tm timeinfo);

void showSpecialEventOnly(struct tm timeinfo) {
  const char* eventLabel = getSpecialEventLabel(timeinfo);

  if (eventLabel[0] == '\0') {
    showWakeTwoLines("Sem evento", "especial", ST77XX_WHITE, ST77XX_CYAN);
  } else {
    showWakeTwoLines("Hoje e", eventLabel, ST77XX_WHITE, ST77XX_CYAN);
  }
}

void showInformationButtonInfo() {
  struct tm timeinfo;

  if (getLocalTime(&timeinfo, 1000)) {
    showWakeOneBig("information", ST77XX_CYAN);
    showScheduleOnly(timeinfo.tm_wday);
    showSpecialEventOnly(timeinfo);
  } else {
    showWakeTwoLines("Nao achei", "a agenda", ST77XX_WHITE, ST77XX_YELLOW);
  }

  finishConversationAction();
}

void showTimeButtonInfo() {
  showWakeOneBig("time", ST77XX_CYAN);

  if (!hasWeatherData || !hasTomorrowWeatherData) {
    fetchWeather();
  }

  showTalkWeather();

  if (hasTomorrowWeatherData) {
    char maxText[16];
    char minText[16];
    snprintf(maxText, sizeof(maxText), "Max %.1fC", tomorrowTempMax);
    snprintf(minText, sizeof(minText), "Min %.1fC", tomorrowTempMin);
    showWakeTwoLines("Amanha", getWeatherLabelFromCode(tomorrowWeatherCode, 1), ST77XX_WHITE, ST77XX_CYAN);
    showWakeTwoLines(maxText, minText, ST77XX_YELLOW, ST77XX_GREEN);
  } else {
    showWakeTwoLines("Amanha", "sem dados", ST77XX_WHITE, ST77XX_YELLOW);
  }

  finishConversationAction();
}

void getEasterDate(int year, int &month, int &day) {
  int a = year % 19;
  int b = year / 100;
  int c = year % 100;
  int d = b / 4;
  int e = b % 4;
  int f = (b + 8) / 25;
  int g = (b - f + 1) / 3;
  int h = (19 * a + b - d - g + 15) % 30;
  int i = c / 4;
  int k = c % 4;
  int l = (32 + 2 * e + 2 * i - h - k) % 7;
  int m = (a + 11 * h + 22 * l) / 451;

  month = (h + l - 7 * m + 114) / 31;
  day = ((h + l - 7 * m + 114) % 31) + 1;
}

const char* getSpecialEventLabel(struct tm timeinfo) {
  int year = timeinfo.tm_year + 1900;
  int month = timeinfo.tm_mon + 1;
  int day = timeinfo.tm_mday;
  int easterMonth;
  int easterDay;
  getEasterDate(year, easterMonth, easterDay);

  if (month == easterMonth && day == easterDay) return "Pascoa";
  if (month == 5 && timeinfo.tm_wday == 0 && day >= 8 && day <= 14) return "Dia das maes";
  if (month == 8 && timeinfo.tm_wday == 0 && day >= 8 && day <= 14) return "Dia dos pais";
  if (month == 12 && day == 25) return "Natal";
  if (month == 1 && day == 1) return "Ano novo";
  if (month == 10 && day == 12) return "Dia criancas";
  if (month == 6 && day == 24) return "Sao Joao";
  if (month == 9 && day == 7) return "Independencia";
  if (month == 11 && day == 2) return "Finados";
  if (month == 11 && day == 15) return "Republica";
  return "";
}

void showSpecialEventsButtonInfo() {
  struct tm timeinfo;

  if (!getLocalTime(&timeinfo, 1000)) {
    showWakeTwoLines("Nao achei", "a data", ST77XX_WHITE, ST77XX_YELLOW);
    finishConversationAction();
    return;
  }

  showSpecialEventOnly(timeinfo);
  finishConversationAction();
}

void showWordButtonInfo() {
  struct tm timeinfo;

  showWakeOneBig("word", ST77XX_CYAN);

  if (!getLocalTime(&timeinfo, 1000)) {
    showWakeTwoLines("Sem hora", "online", ST77XX_WHITE, ST77XX_YELLOW);
    finishConversationAction();
    return;
  }

  if (!hasWeatherData) {
    fetchWeather();
  }

  char hora[6];
  char tempText[14];
  strftime(hora, sizeof(hora), "%H:%M", &timeinfo);
  snprintf(tempText, sizeof(tempText), "%.1fC", temperature);

  int phase = getMoonPhase(timeinfo);
  showWakeTwoLines("Lua", getMoonPhaseLabel(phase), ST77XX_WHITE, ST77XX_CYAN);
  showWakeTwoLines("Hora", hora, ST77XX_WHITE, ST77XX_GREEN);
  showWakeTwoLines("Temp", tempText, ST77XX_WHITE, ST77XX_YELLOW);
  showWakeTwoLines("Tempo", getWeatherTalkLabel(), ST77XX_WHITE, ST77XX_CYAN);
  finishConversationAction();
}

void showZappFaceFrame(const char* label, int faceMode) {
  drawRobotBase();

  if (faceMode == 0) {
    drawOpenEyes();
  } else if (faceMode == 1) {
    drawClosedEyes();
  } else if (faceMode == 2) {
    drawOpenEyes();
    drawSurprisedMouth();
  } else if (faceMode == 3) {
    drawHappyEyes();
    drawTongueMouth();
  } else if (faceMode == 4) {
    drawClosedEyes();
    drawKissMouth();
  } else if (faceMode == 5) {
    drawSleepyEyes();
  } else {
    drawHappyEyes();
  }

  centerText(label, 104, 2, ST77XX_CYAN);
}

void showFacesButtonInfo() {
  showWakeOneBig("face", ST77XX_CYAN);
  showZappFaceFrame("Feliz", 0);
  delay(1200);
  showZappFaceFrame("Piscando", 1);
  delay(900);
  showZappFaceFrame("Surpreso", 2);
  delay(1200);
  showZappFaceFrame("Lingua", 3);
  delay(1200);
  showZappFaceFrame("Beijo", 4);
  delay(1200);
  showZappFaceFrame("Sono", 5);
  delay(1200);
  finishConversationAction();
}

void exitConversationMode();

void runSelectedConversationOption() {
  if (conversationOption == 0) {
    showWakeOneBig("Exit", ST77XX_CYAN);
    exitConversationMode();
  } else if (conversationOption == 1) {
    showTimeButtonInfo();
  } else if (conversationOption == 2) {
    showInformationButtonInfo();
  } else if (conversationOption == 3) {
    showWordButtonInfo();
  } else if (conversationOption == 4) {
    showFacesButtonInfo();
  } else if (conversationOption == 5) {
    enterKartMode();
  } else {
    motorsSelfTest();
    finishConversationAction();
  }
}

void enterConversationMode() {
  conversationMode = true;
  conversationOption = 0;
  drawTalkingFace("Oi Davi");
  delay(1800);
  showWakeTwoLines("Quer", "o que?", ST77XX_WHITE, ST77XX_CYAN);
  showConversationScreen();
}

void exitConversationMode() {
  conversationMode = false;
  showClockScreen();
}

void toggleConversationModeFromSensor() {
  if (conversationMode) {
    exitConversationMode();
  } else {
    enterConversationMode();
  }
}

void startAlarm() {
  roboEyesFaceMode = false;
  brightnessIndex = 3;
  applyBrightness();
  alarmSoundOn = true;
  buzzerState = true;
  digitalWrite(BUZZER_PIN, HIGH);
  lastBuzzerToggle = millis();
  showAlarmOnScreen();
}

void stopAlarm() {
  alarmSoundOn = false;
  buzzerState = false;
  digitalWrite(BUZZER_PIN, LOW);
  showWakeUpMessages();
  showClockScreen();
}

void applyBrightness() {
  analogWrite(TFT_LED_PIN, brightnessLevels[brightnessIndex]);
}

void cycleBrightness() {
  brightnessIndex++;
  if (brightnessIndex >= 4) brightnessIndex = 0;
  applyBrightness();
}

void enterRoboEyesFaceMode() {
  roboEyesFaceMode = true;
  tft.fillScreen(ST77XX_BLACK);
  roboEyes.setDisplayColors(ST77XX_BLACK, ST77XX_CYAN);
  roboEyes.setConfiguration(40, 30, 7, ST77XX_CYAN);
  roboEyes.setAutoblinker(false);
  roboEyes.setIdleMode(false);
  roboEyes.open();
  snapRoboEyes(HAPPY, DEFAULT);
  lastRoboEyesFaceChange = millis();
}

void exitRoboEyesFaceMode() {
  roboEyesFaceMode = false;
  showClockScreen();
}

void toggleRoboEyesFaceMode() {
  if (roboEyesFaceMode) {
    exitRoboEyesFaceMode();
  } else if (clockMode) {
    enterRoboEyesFaceMode();
  }
}

void updateRoboEyesFaceMode() {
  roboEyes.update();

  unsigned long now = millis();
  if (now - lastRoboEyesFaceChange < 900) return;

  static int faceStep = 0;
  faceStep++;
  if (faceStep > 4) faceStep = 0;

  if (faceStep == 0) {
    snapRoboEyes(HAPPY, DEFAULT);
    snapRoboBlink();
  } else if (faceStep == 1) {
    snapRoboEyes(DEFAULT, W);
  } else if (faceStep == 2) {
    snapRoboEyes(HAPPY, E);
  } else if (faceStep == 3) {
    snapRoboEyes(TIRED, DEFAULT);
  } else {
    snapRoboEyes(HAPPY, DEFAULT);
  }

  lastRoboEyesFaceChange = now;
}

bool isScheduledAlarmTime(struct tm timeinfo) {
  int hour = timeinfo.tm_hour;
  int minute = timeinfo.tm_min;

  if (minute != 0) return false;

  // tm_wday: domingo=0, segunda=1, terca=2, quarta=3, quinta=4, sexta=5, sabado=6
  if (timeinfo.tm_wday == 0) {
    return hour == 18;
  }

  if (timeinfo.tm_wday == 1 || timeinfo.tm_wday == 5) {
    return hour == 5 || hour == 18;
  }

  if (timeinfo.tm_wday == 2 || timeinfo.tm_wday == 4) {
    return hour == 5 || hour == 14 || hour == 15 || hour == 18;
  }

  return false;
}

void checkAlarm(struct tm timeinfo) {
  int alarmCode = (timeinfo.tm_yday * 1440) + (timeinfo.tm_hour * 60) + timeinfo.tm_min;

  if (isScheduledAlarmTime(timeinfo) && alarmCode != lastAlarmCode) {
    lastAlarmCode = alarmCode;
    startAlarm();
  }
}

void checkStopSensor() {
  bool sensorActive = digitalRead(STOP_SENSOR_PIN) == SENSOR_ACTIVE;
  unsigned long now = millis();

  if (sensorActive && !sensorWasActive) {
    sensorHoldStart = now;
    sensorHoldTriggered = false;
  }

  if (sensorActive &&
      !sensorHoldTriggered &&
      sensorHoldStart > 0 &&
      now - sensorHoldStart >= 5000UL &&
      now - lastSensorAction >= 700UL) {
    sensorHoldTriggered = true;
    lastSensorAction = now;

    if (alarmSoundOn) {
      stopAlarm();
    } else {
      toggleRoboEyesFaceMode();
    }
  }

  if (!sensorActive && sensorWasActive) {
    unsigned long pressTime = now - sensorHoldStart;

    if (!sensorHoldTriggered &&
        pressTime >= 50UL &&
        now - lastSensorAction >= 600UL) {
      if (alarmSoundOn) {
        stopAlarm();
      } else if (clockMode && !roboEyesFaceMode) {
        cycleBrightness();
      }

      lastSensorAction = now;
    }

    sensorHoldStart = 0;
    sensorHoldTriggered = false;
  }

  sensorWasActive = sensorActive;
}

void checkConversationSensor() {
  if (!clockMode || alarmSoundOn) {
    conversationSensorWasActive = false;
    conversationHoldTriggered = false;
    conversationSensorStart = 0;
    return;
  }

  bool sensorActive = digitalRead(CONVERSATION_SENSOR_PIN) == CONVERSATION_SENSOR_ACTIVE;
  unsigned long now = millis();

  if (sensorActive && !conversationSensorWasActive) {
    conversationSensorStart = now;
    conversationHoldTriggered = false;
  }

  unsigned long holdTime = conversationMode ? 2500UL : 10000UL;

  if (sensorActive &&
      !conversationHoldTriggered &&
      conversationSensorStart > 0 &&
      now - conversationSensorStart >= holdTime &&
      now - lastConversationSensorAction >= 700UL) {
    conversationHoldTriggered = true;
    lastConversationSensorAction = now;

    if (conversationMode) {
      runSelectedConversationOption();
    } else {
      enterConversationMode();
    }
    return;
  }

  if (!sensorActive && conversationSensorWasActive) {
    unsigned long releaseTime = now - conversationSensorStart;

    if (conversationMode &&
        !conversationHoldTriggered &&
        releaseTime >= 50UL &&
        releaseTime <= 2200UL &&
        now - lastConversationSensorAction >= 350UL) {
      moveConversationOption(1);
      lastConversationSensorAction = now;
    }

    conversationSensorStart = 0;
    conversationHoldTriggered = false;
  }

  conversationSensorWasActive = sensorActive;
}

void updateBuzzer() {
  if (!alarmSoundOn) {
    digitalWrite(BUZZER_PIN, LOW);
    return;
  }

  unsigned long now = millis();
  if (now - lastBuzzerToggle >= 250) {
    buzzerState = !buzzerState;
    digitalWrite(BUZZER_PIN, buzzerState ? HIGH : LOW);
    lastBuzzerToggle = now;
  }
}

void showWeatherErrorIfNeeded() {
  if (!hasWeatherData) {
    clearWeatherArea();
    centerText("Sem clima", 94, 1, ST77XX_RED);
  }
}

void updateClock() {
  unsigned long now = millis();
  if (now - lastClockUpdate < 1000) return;
  lastClockUpdate = now;

  // indicador de controle conectado (canto superior esquerdo)
  tft.fillRect(2, 1, 32, 9, ST77XX_BLACK);
  if (gamepad && gamepad->isConnected()) {
    tft.setTextSize(1);
    tft.setTextColor(ST77XX_CYAN, ST77XX_BLACK);
    tft.setCursor(2, 1);
    tft.print("CTRL");
  }

  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) {
    tft.setTextSize(2);
    tft.setTextColor(ST77XX_RED, ST77XX_BLACK);
    tft.setCursor(30, 34);
    tft.print("Sem hora");
    return;
  }

  checkAlarm(timeinfo);
  if (alarmSoundOn) return;

  char hora[9];
  char data[11];
  strftime(hora, sizeof(hora), "%H:%M:%S", &timeinfo);
  strftime(data, sizeof(data), "%d/%m/%Y", &timeinfo);

  tft.setTextSize(3);
  tft.setTextColor(ST77XX_GREEN, ST77XX_BLACK);
  tft.setCursor(8, 31);
  tft.print(hora);

  tft.setTextSize(1);
  tft.setTextColor(ST77XX_WHITE, ST77XX_BLACK);
  tft.setCursor(50, 62);
  tft.print(data);

  drawPeriodIcon(timeinfo);
}

void updateWeatherIfNeeded() {
  unsigned long now = millis();
  unsigned long weatherInterval = hasWeatherData ? 10UL * 60UL * 1000UL : 30UL * 1000UL;

  if (!alarmSoundOn && now - lastWeatherUpdate >= weatherInterval) {
    if (fetchWeather()) {
      drawWeatherInfo();
    }
    lastWeatherUpdate = now;
  }
}

// ── Controle dos motores (PWM via analogWrite, 0..255) ──────────────────────
// Cada motor da L298N tem 2 entradas (IN1/IN2 ou IN3/IN4). PWM numa e LOW na
// outra = anda num sentido; inverte = anda no outro. As duas em 0 = solto;
// as duas no máx = freio. (Funciona porque os jumpers ENA/ENB ficam colocados.)
void driveMotor(int in1, int in2, int speed) {
  speed = constrain(speed, -255, 255);
  if (speed >= 0) {
    analogWrite(in1, speed);
    analogWrite(in2, 0);
  } else {
    analogWrite(in1, 0);
    analogWrite(in2, -speed);
  }
}

// left/right: -255 (ré total) .. 0 (parado) .. +255 (frente total)
void drive(int left, int right) {
  driveMotor(MOTOR_L_IN1, MOTOR_L_IN2, left);
  driveMotor(MOTOR_R_IN1, MOTOR_R_IN2, right);
}

void motorsStop()            { drive(0, 0); }
void motorsForward(int s)    { drive(s, s); }
void motorsBackward(int s)   { drive(-s, -s); }
void motorsTurnLeft(int s)   { drive(-s, s); }   // gira no próprio eixo
void motorsTurnRight(int s)  { drive(s, -s); }

void motorsBegin() {
  pinMode(MOTOR_L_IN1, OUTPUT);
  pinMode(MOTOR_L_IN2, OUTPUT);
  pinMode(MOTOR_R_IN1, OUTPUT);
  pinMode(MOTOR_R_IN2, OUTPUT);
  motorsStop();
}

// Teste um motor de cada vez: esquerdo p/ frente 2 s, para; depois o direito.
// Use ~180 (não 255) pra começar devagar e ver se cada roda gira no sentido certo.
// Se um motor girar ao contrário, troque os DOIS fios dele na ponte (ou os pinos
// INx no código).
// Um passo do teste: mostra nome + sentido na tela e aciona os motores.
void motorsTestStep(const char *nome, uint16_t cor, const char *dir, int left, int right) {
  tft.fillRect(0, 38, 160, 60, ST77XX_BLACK);
  centerText(nome, 44, 2, cor);
  centerText(dir, 72, 2, ST77XX_GREEN);
  drive(left, right);
  delay(2500);
  motorsStop();
  delay(1000);
}

void motorsSelfTest() {
  tft.fillScreen(ST77XX_BLACK);
  centerText("TESTE MOTORES", 8, 1, ST77XX_WHITE);

  motorsTestStep("ESQUERDO", ST77XX_CYAN,   "frente", 180, 0);
  motorsTestStep("DIREITO",  ST77XX_YELLOW, "frente", 0, 180);
  motorsTestStep("OS DOIS",  ST77XX_GREEN,  "frente", 180, 180);

  tft.fillRect(0, 38, 160, 60, ST77XX_BLACK);
  centerText("FIM DO TESTE", 56, 2, ST77XX_WHITE);
  delay(1200);
}

// ── Gamepad (Bluepad32) ─────────────────────────────────────────────────────
void onGamepadConnected(ControllerPtr ctl) {
  if (gamepad == nullptr) gamepad = ctl;
}

void onGamepadDisconnected(ControllerPtr ctl) {
  if (gamepad == ctl) {
    gamepad = nullptr;
    motorsStop();
  }
}

// ── Modo Kart: dirige pelo analógico DIREITO; ombros L/R = trim ─────────────
void drawKartScreen() {
  tft.fillScreen(ST77XX_BLACK);
  centerText("MODO KART", 6, 2, ST77XX_GREEN);
  centerText("analog direito", 28, 1, ST77XX_WHITE);
  centerText("L / R = trim", 40, 1, ST77XX_CYAN);
  centerText("B sai", 52, 1, ST77XX_WHITE);
}

void drawKartStatus() {
  tft.fillRect(0, 66, 160, 20, ST77XX_BLACK);
  if (!gamepad || !gamepad->isConnected()) {
    centerText("pareie o controle", 70, 1, ST77XX_YELLOW);
    return;
  }
  char buf[16];
  snprintf(buf, sizeof(buf), "TRIM %+d", motorTrim);
  centerText(buf, 68, 2, ST77XX_WHITE);
}

void enterKartMode() {
  kartMode = true;
  conversationMode = false;
  motorsStop();
  drawKartScreen();
  drawKartStatus();
}

void exitKartMode() {
  kartMode = false;
  motorsStop();
  showClockScreen();
}

void updateKartMode() {
  bool connected = gamepad && gamepad->isConnected() && gamepad->isGamepad();
  static bool prevConnected = false;
  if (connected != prevConnected) { drawKartStatus(); prevConnected = connected; }
  if (!connected) { motorsStop(); return; }

  // botão B sai do modo kart (só na borda de aperto)
  bool exitNow = gamepad->b();
  if (exitNow && !prevKartExit) { prevKartExit = exitNow; exitKartMode(); return; }
  prevKartExit = exitNow;

  // trim com os ombros L / R (só no momento do aperto)
  bool l = gamepad->l1(), r = gamepad->r1();
  if (l && !prevTrimL && motorTrim > -TRIM_MAX) { motorTrim--; drawKartStatus(); }
  if (r && !prevTrimR && motorTrim <  TRIM_MAX) { motorTrim++; drawKartStatus(); }
  prevTrimL = l; prevTrimR = r;

  // analógico DIREITO: RY = frente/ré (cima = frente), RX = direção
  int rx = gamepad->axisRX();   // -512 (esq)  .. +511 (dir)
  int ry = gamepad->axisRY();   // -512 (cima) .. +511 (baixo)
  int dy = (abs(ry) < KART_DEADZONE) ? 0 : ry;
  int dx = (abs(rx) < KART_DEADZONE) ? 0 : rx;

  int throttle = map(-dy, -512, 512, -255, 255);
  int turn     = map(dx,  -512, 512, -255, 255);

  int left  = constrain(throttle + turn, -255, 255);
  int right = constrain(throttle - turn, -255, 255);

  // trim: corrige se andar torto. +trim tira potência da DIREITA; -trim da ESQUERDA.
  if (motorTrim > 0) right = right * (TRIM_MAX - motorTrim) / TRIM_MAX;
  if (motorTrim < 0) left  = left  * (TRIM_MAX + motorTrim) / TRIM_MAX;

  drive(left, right);

  // DIAGNÓSTICO ao vivo (temporário): mostra o que o analógico direito manda.
  static unsigned long lastDbg = 0;
  if (millis() - lastDbg > 150) {
    lastDbg = millis();
    tft.fillRect(0, 92, 160, 34, ST77XX_BLACK);
    char buf[28];
    snprintf(buf, sizeof(buf), "RX %d  RY %d", rx, ry);
    centerText(buf, 96, 1, ST77XX_WHITE);
    snprintf(buf, sizeof(buf), "L %d  R %d", left, right);
    centerText(buf, 110, 1, ST77XX_CYAN);
  }
}

// Navegacao do menu pelo controle: analogico ESQUERDO move, A escolhe, B sai.
void handleGamepadUI() {
  if (!gamepad || !gamepad->isConnected() || !gamepad->isGamepad()) return;

  bool a = gamepad->a();
  bool b = gamepad->b();
  uint8_t dp = gamepad->dpad();     // bits: cima=0x01, baixo=0x02, dir=0x04, esq=0x08
  int ly = gamepad->axisY();        // analogico esquerdo (vertical)
  bool navDown = (dp & 0x02) || ly > 300;   // d-pad baixo OU analogico p/ baixo
  bool navUp   = (dp & 0x01) || ly < -300;  // d-pad cima  OU analogico p/ cima

  if (!conversationMode) {
    // no relogio: A abre o menu
    if (a && !prevMenuA && clockMode && !roboEyesFaceMode) enterConversationMode();
  } else {
    if (navDown && !prevMenuNavDown) moveConversationOption(1);
    else if (navUp && !prevMenuNavUp) moveConversationOption(-1);
    if (a && !prevMenuA) runSelectedConversationOption();
    else if (b && !prevMenuB) exitConversationMode();
  }

  prevMenuA = a;
  prevMenuB = b;
  prevMenuNavUp = navUp;
  prevMenuNavDown = navDown;
}

void setup() {
  Serial.begin(115200);
  motorsBegin();

  pinMode(TFT_LED_PIN, OUTPUT);
  applyBrightness();
  tft.initR(INITR_BLACKTAB);
  tft.setRotation(1);

  pinMode(STOP_SENSOR_PIN, INPUT_PULLUP);
  pinMode(CONVERSATION_SENSOR_PIN, INPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  intro();
  connectWiFiAndTime();

  tft.fillScreen(ST77XX_BLACK);
  roboEyes.begin(160, 128, 100);
  roboEyes.setDisplayColors(ST77XX_BLACK, ST77XX_CYAN);
  roboEyes.setConfiguration(40, 30, 7, ST77XX_CYAN);
  roboEyes.setAutoblinker(false);
  roboEyes.setIdleMode(false);
  roboEyes.open();
  snapRoboEyes(HAPPY, DEFAULT);

  // Gamepad Bluetooth (Bluepad32). Pareie segurando SYNC ate os LEDs varrerem.
  BP32.setup(&onGamepadConnected, &onGamepadDisconnected);
  BP32.forgetBluetoothKeys();
  BP32.enableVirtualDevice(false);

  eyesOpen = true;
  robotStartTime = millis();
  lastBlinkTime = millis();

  clockMode = true;     // vai direto pro relogio (sem a fase de olhos no inicio)
  showClockScreen();
}

void loop() {
  BP32.update();
  updateBuzzer();

  if (kartMode) {
    updateKartMode();
    return;
  }

  checkStopSensor();
  handleGamepadUI();             // abre/navega o menu pelo controle

  if (roboEyesFaceMode) {
    updateRoboEyesFaceMode();
    return;
  }

  checkConversationSensor();     // navega o menu (toque = proximo, segura = escolhe)
  if (conversationMode) return;  // no menu, nao redesenha o relogio por cima

  updateClock();
  updateMiniZappFace();
  updateWeatherIfNeeded();
}
