// RoboEyesController — olhos RoboEyes na tela TFT controlados por um controle
// Bluetooth de Nintendo Switch (clone), via Bluepad32.
//
//   - Analogico ESQUERDO  -> os olhos olham naquela direcao (8 direcoes + centro).
//   - Botao A -> feliz | B -> bravo | X -> cansado | Y -> normal.
//   - Botao L (ombro esq) -> animacao de rir | R (ombro dir) -> confuso.
//
// Os olhos ficam vivos (com piscada automatica) desde que liga; o controle so
// muda pra onde olham e a feicao. Sem WiFi/relogio — e um sketch de demonstracao.
//
// REQUISITOS:
//   - Core "ESP32 + Bluepad32" instalado.
//   - Compilar/enviar com FQBN: esp32-bluepad32:esp32:esp32
//
// PAREAMENTO: com o controle desligado, segure o SYNC ate os 4 LEDs varrerem.

#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>
#include <SPI.h>

#define ROBOEYES_TFT_MODE
#include <TFT_RoboEyes.h>

#include <Bluepad32.h>

// --- Pinos do TFT (iguais aos do Zapp) ---
#define TFT_CS    27
#define TFT_DC    16
#define TFT_RST   17
#define TFT_SCLK  18
#define TFT_MOSI  23
#define TFT_LED_PIN 13  // backlight

Adafruit_ST7735 tft = Adafruit_ST7735(TFT_CS, TFT_DC, TFT_MOSI, TFT_SCLK, TFT_RST);
TFTRoboEyes<Adafruit_ST7735> roboEyes(tft);

ControllerPtr myController = nullptr;

// Zona morta do analogico (eixo vai de ~-512 a +511)
const int DEADZONE = 200;

// Estado anterior dos botoes, pra detectar so o momento do aperto (borda de subida)
bool prevA = false, prevB = false, prevX = false, prevY = false;
bool prevL1 = false, prevR1 = false;

void onConnectedController(ControllerPtr ctl) {
  if (myController == nullptr) {
    myController = ctl;
    ControllerProperties p = ctl->getProperties();
    Serial.printf(">>> Controle CONECTADO: %s VID=0x%04x PID=0x%04x\n",
                  ctl->getModelName().c_str(), p.vendor_id, p.product_id);
    // pisca feliz pra dar feedback de que conectou
    roboEyes.setMood(HAPPY);
    roboEyes.blink();
  }
}

void onDisconnectedController(ControllerPtr ctl) {
  if (myController == ctl) {
    Serial.println(">>> Controle DESCONECTADO");
    myController = nullptr;
    roboEyes.setMood(DEFAULT);
    roboEyes.setPosition(DEFAULT);
  }
}

// Mapeia o analogico esquerdo para uma das 8 direcoes (ou centro).
// A propria RoboEyes faz o easing, entao o movimento sai suave.
void handleStick(ControllerPtr ctl) {
  int x = ctl->axisX();
  int y = ctl->axisY();

  bool right = x > DEADZONE;
  bool left = x < -DEADZONE;
  bool down = y > DEADZONE;   // no controle, Y+ e pra baixo
  bool up = y < -DEADZONE;

  unsigned char pos;
  if (up && right) pos = NE;
  else if (up && left) pos = NW;
  else if (down && right) pos = SE;
  else if (down && left) pos = SW;
  else if (up) pos = N;
  else if (down) pos = S;
  else if (right) pos = E;
  else if (left) pos = W;
  else pos = DEFAULT;  // centro

  roboEyes.setPosition(pos);
}

// Botoes mudam a feicao (so no momento do aperto).
void handleButtons(ControllerPtr ctl) {
  bool a = ctl->a(), b = ctl->b(), x = ctl->x(), y = ctl->y();
  bool l1 = ctl->l1(), r1 = ctl->r1();

  if (a && !prevA) roboEyes.setMood(HAPPY);    // A -> feliz
  if (b && !prevB) roboEyes.setMood(ANGRY);    // B -> bravo
  if (x && !prevX) roboEyes.setMood(TIRED);    // X -> cansado
  if (y && !prevY) roboEyes.setMood(DEFAULT);  // Y -> normal
  if (l1 && !prevL1) roboEyes.anim_laugh();    // L -> rir
  if (r1 && !prevR1) roboEyes.anim_confused(); // R -> confuso

  prevA = a; prevB = b; prevX = x; prevY = y; prevL1 = l1; prevR1 = r1;
}

void setup() {
  Serial.begin(115200);

  pinMode(TFT_LED_PIN, OUTPUT);
  digitalWrite(TFT_LED_PIN, HIGH);  // liga o backlight

  tft.initR(INITR_BLACKTAB);
  tft.setRotation(1);
  tft.fillScreen(ST77XX_BLACK);

  // Olhos RoboEyes em tela cheia (mesmos parametros do Zapp)
  roboEyes.begin(160, 128, 100);
  roboEyes.setDisplayColors(ST77XX_BLACK, ST77XX_CYAN);
  roboEyes.setConfiguration(40, 30, 8, ST77XX_CYAN);
  roboEyes.setAutoblinker(true, 3, 2);  // piscada natural a cada ~3-5s
  roboEyes.setIdleMode(false);          // a posicao quem manda e o analogico
  roboEyes.open();

  Serial.printf("Bluepad32: %s\n", BP32.firmwareVersion());
  BP32.setup(&onConnectedController, &onDisconnectedController);
  BP32.forgetBluetoothKeys();
  BP32.enableVirtualDevice(false);

  Serial.println("Pronto. Pareie o controle (segure SYNC ate os LEDs varrerem).");
}

void loop() {
  BP32.update();

  if (myController && myController->isConnected() && myController->isGamepad()) {
    handleStick(myController);
    handleButtons(myController);
  }

  roboEyes.update();  // desenha/anima (auto-limitado pelo framerate)
}
