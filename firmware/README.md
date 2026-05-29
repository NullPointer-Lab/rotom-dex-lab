# Firmware do Davi — projeto "Zapp" (ESP32)

Código que o Davi roda no ESP32. O **Zapp** (o Davi chama de "Zapp" ou "Z") é um
assistente-robô numa tela TFT ST7735S controlada por um ESP32 DevKitC-32: rosto
animado (RoboEyes), relógio por NTP, clima de Fortaleza (Open-Meteo), despertador
com buzzer, sensor de movimento e, no futuro, um kart com motores via L298N.

## Sketches

| Arquivo | O que é |
| --- | --- |
| `ZappRobotFinal.ino` | **Sketch principal** — cópia usada pelo Arduino CLI para compilar/enviar. |
| `ZappAlarm.ino` | Mesmo sketch principal, versão editada no workspace. |
| `ZappAlarm_working_backup.ino` | Backup funcional anterior. |
| `KartRoboEyes.ino` | Teste do kart (L298N) + RoboEyes. |
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

```powershell
arduino-cli compile --fqbn esp32:esp32:esp32 <pasta-do-sketch>
arduino-cli upload -p COM9 --fqbn esp32:esp32:esp32 <pasta-do-sketch>
```

> Para compilar, cada `.ino` precisa estar numa pasta com o mesmo nome do arquivo.
> A porta pode variar (já foi vista em COM5 e COM9); use o "Procurar minha placa"
> do Rotom Dex Lab para descobrir a atual (o ESP32 aparece como CH340 / 0x1A86).

Pinagem e comportamento completos do Zapp ficam documentados no conhecimento do
agente **Rotom Dex** (perfil Hermes `rotom-dex`).
