#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>
#include <SPI.h>

#define TFT_CS    27
#define TFT_DC    16
#define TFT_RST   17
#define TFT_SCLK  18
#define TFT_MOSI  23
#define TFT_LED   13

Adafruit_ST7735 tft = Adafruit_ST7735(TFT_CS, TFT_DC, TFT_MOSI, TFT_SCLK, TFT_RST);

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("TFT PIN TEST iniciando");

  pinMode(TFT_LED, OUTPUT);
  digitalWrite(TFT_LED, HIGH);

  tft.initR(INITR_BLACKTAB);
  tft.setRotation(1);

  tft.fillScreen(ST77XX_RED);
  delay(800);
  tft.fillScreen(ST77XX_GREEN);
  delay(800);
  tft.fillScreen(ST77XX_BLUE);
  delay(800);
  tft.fillScreen(ST77XX_BLACK);

  tft.setTextSize(2);
  tft.setTextColor(ST77XX_WHITE);
  tft.setCursor(8, 20);
  tft.println("Zapp OK");
  tft.setTextSize(1);
  tft.setTextColor(ST77XX_CYAN);
  tft.setCursor(8, 55);
  tft.println("CS 27 DC 16 RST 17");
  tft.setCursor(8, 70);
  tft.println("SCK 18 MOSI 23 LED 13");
  Serial.println("TFT PIN TEST desenhado");
}

void loop() {
  delay(1000);
}
