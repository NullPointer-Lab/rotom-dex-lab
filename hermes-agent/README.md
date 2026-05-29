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

## Limitação conhecida — imagens

O canal `hermes -z` não tem entrada multimodal nativa, então o agente **ainda não
enxerga fotos** por aqui. Quando uma imagem é anexada, o shim responde de forma
honesta ("ainda não consigo enxergar fotos") em vez de fingir. Para visão de
verdade, é preciso um canal multimodal (ex.: `hermes proxy` com um provedor com
visão autenticado, ou um endpoint compatível com OpenAI) — a UI e a validação de
imagem já estão prontas para isso.
