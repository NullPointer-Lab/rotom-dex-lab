# Firmware do Davi — projeto "Zapp" (ESP32)

Código que o Davi roda no ESP32. O **Zapp** (o Davi chama de "Zapp" ou "Z") é um
assistente-robô numa tela TFT ST7735S controlada por um ESP32 DevKitC-32: rosto
animado (RoboEyes), relógio por NTP, clima de Fortaleza (Open-Meteo), despertador
com buzzer, sensor de movimento e um **kart** com 2 motores DC via ponte L298N,
dirigido por um **controle Bluetooth** (analógico direito; ombros L/R ajustam o
trim) — opção "kart" no menu do Zapp.

## Sketches

| Arquivo | O que é |
| --- | --- |
| `ZappRobotFinal.ino` | **Sketch principal** — cópia usada pelo Arduino CLI para compilar/enviar. |
| `ZappAlarm.ino` | Mesmo sketch principal, versão editada no workspace. |
| `ZappAlarm_working_backup.ino` | Backup funcional anterior. |
| `KartRoboEyes.ino` | Demo antigo do kart (L298N) + RoboEyes — **superado** pelo kart integrado no `ZappRobotFinal.ino`; candidato a remoção. |
| `ZappBuzzerSensorTest.ino` | Teste simples de buzzer + sensor. |

## ⚠️ Credenciais redigidas

As credenciais de Wi-Fi foram **substituídas por placeholders** antes de versionar
(este repositório fica no GitHub). Antes de compilar, defina as suas:

```cpp
const char* ssid     = "SUA_REDE_WIFI";
const char* password = "SUA_SENHA_WIFI";
```

A cópia com as credenciais reais fica só na máquina do Davi (não versionada).

## Compilar / enviar (Arduino CLI)

O `ZappRobotFinal.ino` agora usa **Bluepad32** (controle Bluetooth), então precisa
do **core dedicado** `esp32-bluepad32` e da partição `huge_app` (o binário com
WiFi+BT não cabe na partição padrão):

```powershell
arduino-cli compile --fqbn "esp32-bluepad32:esp32:esp32:PartitionScheme=huge_app" firmware\ZappRobotFinal
arduino-cli upload -p COM9 --fqbn "esp32-bluepad32:esp32:esp32:PartitionScheme=huge_app" firmware\ZappRobotFinal
```

> Os sketches antigos sem Bluepad32 (ex.: testes de buzzer) ainda compilam com o
> core comum `esp32:esp32:esp32`.
>
> Para compilar, cada `.ino` precisa estar numa pasta com o mesmo nome do arquivo.
> A porta pode variar (já foi vista em COM5 e COM9); use o "Procurar minha placa"
> do Rotom Dex Lab para descobrir a atual (o ESP32 aparece como CH340 / 0x1A86).

Pinagem e comportamento completos do Zapp ficam documentados no conhecimento do
agente **Rotom Dex** (perfil Hermes `rotom-dex`).
