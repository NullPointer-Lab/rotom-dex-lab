# AGENTS.md — modo de trabalho do Rotom Dex Lab

Guia para qualquer agente de IA (Codex, Claude, etc.) que for continuar este
projeto. Resume **como** trabalhamos aqui — o fluxo que vinha funcionando bem com
o Isaac — para manter a mesma fluidez numa máquina nova. Leia isto antes de mexer.

> Convenção: o Codex lê este arquivo automaticamente na raiz do repo. Mantenha-o
> curto e atualizado; quando o fluxo mudar, edite aqui.

## Contexto em 30 segundos

- **Quem usa:** o Isaac (pai, dev) e o **Davi (9 anos)**. O Davi é o usuário final.
- **O que é:** uma UI web local (FastAPI) onde o Davi conversa com o agente
  **Rotom Dex** e, de forma controlada, compila/envia sketches Arduino para o
  ESP32 dele. Detalhes de produto no [`README.md`](README.md).
- **O robô do Davi é o "Zapp":** ESP32 + tela TFT ST7735S (rosto RoboEyes,
  relógio NTP, clima de Fortaleza, despertador, sensor, kart L298N + controle
  Bluetooth). Firmware versionado em [`firmware/`](firmware/README.md).
- **Cérebro do chat:** um agente **Hermes** dedicado (profile `rotom-dex`) na
  LAN. Veja [`hermes-agent/README.md`](hermes-agent/README.md).

## Princípios de trabalho (o que mantém o fluxo bom)

1. **Evoluir, não reescrever.** Faça a **menor mudança no lugar** que resolve.
   Sem duplicação, sem código morto. O backend FastAPI seguro fica; mude só o
   necessário.
2. **Honestidade acima de tudo — nunca finja.** Se algo não funciona (ex.: visão
   por imagem ainda offline), a UI/resposta **diz a verdade** em vez de simular
   sucesso. Reporte contagem de testes de verdade; se falhou, diga que falhou,
   com a saída.
3. **Validar no hardware real antes de dizer "pronto".** Compile **e** envie pro
   ESP32 de verdade e observe o serial. Sem evidência, não afirme que funciona.
4. **Commits pequenos e frequentes, em PT-BR, no estilo conventional commits**
   (`feat:`, `fix:`, `chore:`). Cada passo coerente vira um commit. No
   vibecoding, **cada mudança do Davi é um save no git**.
5. **Rode a suíte e reporte o número.** `pytest -q` depois de mexer; diga
   "N passed". Não quebre testes existentes.
6. **Público é uma criança.** Texto pro Davi é PT-BR lúdico; erros amigáveis com
   uma dica "faça isto"; log cru escondido em "Detalhes para o papai".
   Converse com o Isaac em **português**.
7. **Hermes/Rosie é para contexto/revisão/próximos passos** — consulte, depois
   valide localmente. **Nunca mande segredo** (token/PIN/senha) pra Hermes.

## Restrições de segurança — INEGOCIÁVEIS

Estas já estão refletidas no código e nos testes. Nunca as afrouxe:

- **Nunca commitar segredos.** Credenciais Wi-Fi, tokens e PINs vão como
  **placeholders** no repo (`SUA_REDE_WIFI` / `SUA_SENHA_WIFI`). As reais ficam
  só na máquina do Davi. A pasta de trabalho `firmware/ZappRobotFinal/` (com
  creds reais) é **gitignorada** — a cópia de referência redigida é
  `firmware/ZappRobotFinal.ino`. O repo de trabalho do sketch do Davi é **git
  local só, nunca dê push**.
- **Sem shell livre pela UI.** Subprocessos usam lista de argumentos, nunca
  `shell=True`.
- **Sem chave de IA no frontend** — modelos de visão/chat rodam server-side.
- **Upload sempre exige confirmação humana** — um backend remoto não pode
  desligar isso.
- **Nunca remova o token/PIN** da LAN. Só FQBNs allowlisted. Paths validados pra
  ficar dentro do projeto.

## Rodar e testar (Linux)

A máquina nova é Linux; o launcher PowerShell (`Start-RotomDexLab.ps1`) é só pro
Windows do Davi. No Linux use o fluxo dev:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
uvicorn bridge.server:app --host 0.0.0.0 --port 8765
# UI em http://<ip-do-host>:8765 (o PIN é impresso no console)
```

Caminhos no código/config são de Windows (`C:/Users/Fulano/...`); ao rodar no
Linux, ajuste `config/projects.json` (e similares) pro caminho local — **não**
faça commit desse ajuste de caminho pessoal.

## Hermes (cérebro do chat) no Linux

O agente `rotom-dex` roda no servidor **Hermes** (Ubuntu, `192.168.31.208`, user
SSH `hermes`). One-shot: `hermes -z "<prompt>"` (não existe subcomando `ask`).
Para consultar de outra máquina:

```bash
ssh -o BatchMode=yes hermes@192.168.31.208 "bash -lc 'hermes -z \"<prompt>\"'"
```

O bridge fala com o agente via o shim HTTP em `hermes-agent/` (serviço systemd de
usuário na porta `8770`). Aponte `ROTOM_DEX_HERMES_URL` →
`http://192.168.31.208:8770/chat` e `ROTOM_DEX_HERMES_TOKEN=<token>` (o token
fica em `~/.config/rotom-agent.env` na Hermes, **fora** do git e do chat).
Regras e detalhes no `hermes-agent/README.md`.

## Onde está o quê

- `bridge/` — backend FastAPI: detecção de placa, compile/upload (arduino-cli),
  serial, chat, vibecoding (`codegen.py`), auto-heal de libs (`libfix.py`),
  visão (`vision.py`), validações (`policy.py`).
- `firmware/` — sketches do Zapp (referência redigida). Veja seu `README.md`.
- `hermes-agent/` — shim HTTP que expõe o agente Hermes pro bridge.
- `config/` — `projects.json`, `missions.json`. `rotom.local.env` é local/ignorado.
- `docs/claude-goals/` — notas de objetivo de longo prazo.
</content>
</invoke>
