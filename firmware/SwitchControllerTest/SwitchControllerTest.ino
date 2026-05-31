// SwitchControllerTest — teste MINIMO de pareamento de controle Bluetooth
// (controle de Nintendo Switch / clones) com o ESP32, usando a Bluepad32.
//
// Objetivo: provar se o SEU controle clone parea e responde. Ele NAO faz nada
// alem de imprimir os botoes/analogicos no Monitor Serial (115200 baud).
// Nao tem WiFi, relogio, tela nem nada do Zapp.
//
// REQUISITOS (ver instrucoes que o Rotom passou):
//   - Core "ESP32 + Bluepad32" instalado (board manager URL da Bluepad32).
//   - Compilar/enviar com FQBN: esp32_bluepad32:esp32:esp32
//
// COMO TESTAR:
//   1. Gravar este sketch.
//   2. Abrir o Monitor Serial a 115200.
//   3. Ligar o controle em modo de pareamento (geralmente segurar o botao de
//      sync ate as luzes piscarem). O ESP32 procura controles novos sozinho.
//   4. Quando conectar, mexa nos analogicos/botoes e veja os valores no serial.

#include <Bluepad32.h>

ControllerPtr myControllers[BP32_MAX_GAMEPADS];

void onConnectedController(ControllerPtr ctl) {
  for (int i = 0; i < BP32_MAX_GAMEPADS; i++) {
    if (myControllers[i] == nullptr) {
      ControllerProperties props = ctl->getProperties();
      Serial.printf(
          ">>> Controle CONECTADO (slot %d): modelo=%s VID=0x%04x PID=0x%04x\n",
          i, ctl->getModelName().c_str(), props.vendor_id, props.product_id);
      myControllers[i] = ctl;
      return;
    }
  }
  Serial.println(">>> Controle conectou mas nao havia slot livre.");
}

void onDisconnectedController(ControllerPtr ctl) {
  for (int i = 0; i < BP32_MAX_GAMEPADS; i++) {
    if (myControllers[i] == ctl) {
      Serial.printf(">>> Controle DESCONECTADO (slot %d)\n", i);
      myControllers[i] = nullptr;
      return;
    }
  }
}

void dumpGamepad(ControllerPtr ctl) {
  Serial.printf(
      "dpad:0x%02x botoes:0x%04x misc:0x%02x | eixoL:(%5d,%5d) eixoR:(%5d,%5d) "
      "| gatilhos L:%4d R:%4d\n",
      ctl->dpad(), ctl->buttons(), ctl->miscButtons(), ctl->axisX(),
      ctl->axisY(), ctl->axisRX(), ctl->axisRY(), ctl->brake(),
      ctl->throttle());
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.printf("\nBluepad32 firmware: %s\n", BP32.firmwareVersion());
  const uint8_t *addr = BP32.localBdAddress();
  Serial.printf("Endereco BT do ESP32: %02x:%02x:%02x:%02x:%02x:%02x\n",
                addr[0], addr[1], addr[2], addr[3], addr[4], addr[5]);

  BP32.setup(&onConnectedController, &onDisconnectedController);

  // Esquece pareamentos antigos -> facilita reconectar um controle novo nos
  // testes. (Pode comentar depois que estiver tudo funcionando.)
  BP32.forgetBluetoothKeys();

  // Nao habilita "mouse/teclado virtual" -> so gamepads, mais simples.
  BP32.enableVirtualDevice(false);

  Serial.println("Pronto. Coloque o controle em modo de pareamento...");
}

void loop() {
  if (BP32.update()) {
    for (int i = 0; i < BP32_MAX_GAMEPADS; i++) {
      ControllerPtr ctl = myControllers[i];
      if (ctl && ctl->isConnected() && ctl->hasData() && ctl->isGamepad()) {
        dumpGamepad(ctl);
      }
    }
  }
  delay(150);
}
