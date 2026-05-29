#define BUZZER_PIN 25
#define STOP_SENSOR_PIN 32
#define SENSOR_ACTIVE LOW

bool buzzerOn = false;
unsigned long lastToggle = 0;

void setup() {
  Serial.begin(115200);

  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(STOP_SENSOR_PIN, INPUT_PULLUP);

  digitalWrite(BUZZER_PIN, LOW);

  Serial.println("Teste do buzzer e sensor iniciado.");
  Serial.println("O buzzer vai tocar bip bip.");
  Serial.println("Passe a mao no sensor para parar.");
}

void loop() {
  unsigned long now = millis();

  if (now - lastToggle >= 250) {
    buzzerOn = !buzzerOn;
    digitalWrite(BUZZER_PIN, buzzerOn ? HIGH : LOW);
    lastToggle = now;
  }

  int sensorValue = digitalRead(STOP_SENSOR_PIN);

  Serial.print("Sensor = ");
  if (sensorValue == LOW) {
    Serial.println("LOW");
  } else {
    Serial.println("HIGH");
  }

  if (sensorValue == SENSOR_ACTIVE) {
    digitalWrite(BUZZER_PIN, LOW);
    Serial.println("Mao detectada. Buzzer parado.");

    while (true) {
      delay(100);
    }
  }

  delay(50);
}
