# Rotom Dex — ponte para o agente Hermes

Davi conversa, na UI do Rotom Dex Lab, com um **agente Hermes dedicado** (o profile
`rotom-dex`) hospedado no servidor Hermes (mesmo da Rosie). O Hermes não expõe um
endpoint HTTP síncrono de "pergunte ao agente e receba a resposta" (o `proxy` é
passagem de modelo cru, o `webhook` é assíncrono, o `acp` é stdio para editores),
então este diretório traz um **shim HTTP minúsculo e sem dependências**:

- `rotom_agent_server.py` — serviço stdlib que expõe, na LAN:
  - `GET /health` → `{"ok": true, "profile": "rotom-dex"}`
  - `POST /chat` (Bearer token) → `{"reply": ..., "suggestedActions": [...], "offline": bool}`
  - Roda `hermes -z --profile rotom-dex --continue rotom-web` (memória de conversa por sessão).
  - **Não** passa `--accept-hooks`: o portão de aprovação do agente continua ligado.
  - Imagem anexada é salva em arquivo temporário, passada ao agente e apagada. Nada é logado.
- `rotom-agent.service` — unit systemd de usuário (auto-restart, sobe no boot com linger).

## Instalar no Hermes

```bash
# 1. copie o shim
mkdir -p ~/rotom-agent
# (copie rotom_agent_server.py para ~/rotom-agent/)

# 2. gere um token e o arquivo de ambiente (não comite isso)
python3 - <<'PY'
import secrets, pathlib
p = pathlib.Path.home()/".config"/"rotom-agent.env"
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(
    "ROTOM_AGENT_TOKEN=%s\nROTOM_AGENT_PORT=8770\n"
    "ROTOM_AGENT_PROFILE=rotom-dex\nROTOM_AGENT_SESSION=rotom-web\n" % secrets.token_urlsafe(24)
)
p.chmod(0o600)
print("token gerado em", p)
PY

# 3. instale o serviço de usuário
mkdir -p ~/.config/systemd/user
cp rotom-agent.service ~/.config/systemd/user/
export XDG_RUNTIME_DIR=/run/user/$(id -u)
systemctl --user daemon-reload
systemctl --user enable --now rotom-agent.service
loginctl enable-linger "$USER"   # sobe no boot mesmo sem login

# 4. teste
TOKEN=$(grep ^ROTOM_AGENT_TOKEN= ~/.config/rotom-agent.env | cut -d= -f2)
curl -s localhost:8770/health
curl -s -X POST localhost:8770/chat -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"message":"oi"}'
```

## Configurar o bridge (Windows do Davi)

No `config/rotom.local.env` (gitignored) do projeto, ou nas variáveis de ambiente do usuário:

```
ROTOM_DEX_HERMES_URL=http://192.168.31.208:8770/chat
ROTOM_DEX_HERMES_TOKEN=<o ROTOM_AGENT_TOKEN do Hermes>
ROTOM_DEX_HERMES_TIMEOUT_SECONDS=120
```

O chat de **texto** passa a ser respondido pelo agente `rotom-dex`. A mesma config
serve para o chat com **imagem** (o bridge reusa `ROTOM_DEX_HERMES_URL`/`TOKEN`).

## Variáveis do shim

| Variável | Padrão | Para que serve |
| --- | --- | --- |
| `ROTOM_AGENT_TOKEN` | (obrigatória) | Bearer token exigido no `/chat`. |
| `ROTOM_AGENT_HOST` | `0.0.0.0` | Interface de bind. Use `127.0.0.1` para só localhost + túnel. |
| `ROTOM_AGENT_PORT` | `8770` | Porta do shim. |
| `ROTOM_AGENT_PROFILE` | `rotom-dex` | Profile Hermes a invocar. |
| `ROTOM_AGENT_SESSION` | `rotom-web` | Sessão de conversa (memória). |
| `ROTOM_AGENT_TIMEOUT` | `150` | Timeout por requisição ao agente, em segundos. |
| `HERMES_BIN` | `~/.local/bin/hermes` | Caminho do CLI hermes. |

## Ligar a visão (chat com imagem)

O canal `hermes -z` não tem entrada multimodal, então **texto vai pelo agente** e
**imagem vai pelo `hermes proxy`** (endpoint compatível com OpenAI, com um modelo
de visão). Enquanto `ROTOM_AGENT_VISION_MODEL` estiver vazio, uma foto anexada
recebe uma resposta honesta ("ainda não consigo enxergar fotos") — nunca fingimos.

Para ligar de verdade (no Hermes):

```bash
# 1. Autentique um provedor com visão (xAI Grok tem visão). Fluxo OAuth interativo.
hermes login --provider xai-oauth

# 2. Suba o proxy OpenAI-compat (fica em 127.0.0.1:8645 por padrão).
#    Deixe rodando (nohup/serviço) — ele só escuta em localhost; quem fica exposto
#    na LAN é só o shim (com token). NÃO use --host 0.0.0.0 no proxy.
nohup hermes proxy start --provider xai >~/rotom-agent/proxy.log 2>&1 &

# 3. Descubra o nome do modelo de visão disponível e ligue no shim:
curl -s localhost:8645/v1/models   # veja o id do modelo de visão (ex.: grok-...-vision)
#    edite ~/.config/rotom-agent.env e defina:
#      ROTOM_AGENT_VISION_MODEL=<id-do-modelo-de-visao>
export XDG_RUNTIME_DIR=/run/user/$(id -u)
systemctl --user restart rotom-agent

# 4. Confira: GET /health deve mostrar "vision": true
```

Não é preciso mexer no bridge do Windows: a imagem continua indo para o mesmo
`/chat`; o shim é que decide entre agente (texto) e proxy de visão (imagem).
