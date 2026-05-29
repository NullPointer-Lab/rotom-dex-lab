#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>
#include <SPI.h>

#define ROBOEYES_TFT_MODE
#include <TFT_RoboEyes.h>

// Tela ST7735S do Zapp
#define TFT_CS    27
#define TFT_DC    16
#define TFT_RST   17
#define TFT_SCLK  18
#define TFT_MOSI  23
#define TFT_LED   13

// L298N
#define MOTOR_A_IN1 14
#define MOTOR_A_IN2 26
#define MOTOR_B_IN3 33
#define MOTOR_B_IN4 21

Adafruit_ST7735 tft = Adafruit_ST7735(TFT_CS, TFT_DC, TFT_MOSI, TFT_SCLK, TFT_RST);
TFTRoboEyes<Adafruit_ST7735> eyes(tft);

void stopMotors() {
  digitalWrite(MOTOR_A_IN1, LOW);
  digitalWrite(MOTOR_A_IN2, LOW);
  digitalWrite(MOTOR_B_IN3, LOW);
  digitalWrite(MOTOR_B_IN4, LOW);
}

void forward() {
  digitalWrite(MOTOR_A_IN1, HIGH);
  digitalWrite(MOTOR_A_IN2, LOW);
  digitalWrite(MOTOR_B_IN3, HIGH);
  digitalWrite(MOTOR_B_IN4, LOW);
}

void backward() {
  digitalWrite(MOTOR_A_IN1, LOW);
  digitalWrite(MOTOR_A_IN2, HIGH);
  digitalWrite(MOTOR_B_IN3, LOW);
  digitalWrite(MOTOR_B_IN4, HIGH);
}

void turnLeft() {
  digitalWrite(MOTOR_A_IN1, LOW);
  digitalWrite(MOTOR_A_IN2, HIGH);
  digitalWrite(MOTOR_B_IN3, HIGH);
  digitalWrite(MOTOR_B_IN4, LOW);
}

void turnRight() {
  digitalWrite(MOTOR_A_IN1, HIGH);
  digitalWrite(MOTOR_A_IN2, LOW);
  digitalWrite(MOTOR_B_IN3, LOW);
  digitalWrite(MOTOR_B_IN4, HIGH);
}

void showLabel(const char *text, uint16_t color) {
  tft.fillRect(0, 108, 160, 20, ST77XX_BLACK);
  tft.setTextColor(color);
  tft.setTextSize(2);

  int16_t x1, y1;
  uint16_t w, h;
  tft.getTextBounds(text, 0, 0, &x1, &y1, &w, &h);
  tft.setCursor((160 - w) / 2, 110);
  tft.print(text);
}

void runFor(unsigned long durationMs) {
  unsigned long start = millis();
  while (millis() - start < durationMs) {
    eyes.update();
    delay(5);
  }
}

void doMove(const char *label, uint16_t color, unsigned char mood, void (*moveFn)(), unsigned long durationMs) {
  eyes.setMood(mood);
  showLabel(label, color);
  moveFn();
  runFor(durationMs);
  stopMotors();
  eyes.blink();
  showLabel("PAROU", ST77XX_WHITE);
  runFor(800);
}

void setup() {
  pinMode(TFT_LED, OUTPUT);
  digitalWrite(TFT_LED, HIGH);

  pinMode(MOTOR_A_IN1, OUTPUT);
  pinMode(MOTOR_A_IN2, OUTPUT);
  pinMode(MOTOR_B_IN3, OUTPUT);
  pinMode(MOTOR_B_IN4, OUTPUT);
  stopMotors();

  tft.initR(INITR_BLACKTAB);
  tft.setRotation(1);
  tft.fillScreen(ST77XX_BLACK);

  eyes.begin(160, 128, 50);
  eyes.setDisplayColors(ST77XX_BLACK, ST77XX_CYAN);
  eyes.setConfiguration(56, 48, 10, ST77XX_CYAN);
  eyes.setAutoblinker(true, 3, 2);
  eyes.setIdleMode(true, 2, 1);
  eyes.setMood(HAPPY);
  eyes.open();

  showLabel("ZAPP KART", ST77XX_CYAN);
  runFor(2500);
}

void loop() {
  doMove("FRENTE", ST77XX_GREEN, HAPPY, forward, 1800);
  doMove("TRAS", ST77XX_YELLOW, TIRED, backward, 1800);
  doMove("ESQUERDA", ST77XX_CYAN, DEFAULT, turnLeft, 1300);
  doMove("DIREITA", ST77XX_CYAN, DEFAULT, turnRight, 1300);

  eyes.setMood(HAPPY);
  showLabel("PARADO", ST77XX_WHITE);
  stopMotors();
  runFor(3000);
}
