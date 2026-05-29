# Rotom Dex Lab

Interface local para o Davi conversar com o agente **Rotom Dex** e operar, de forma controlada, comandos Arduino CLI para projetos ESP32/robótica.

## Objetivo

- Abrir uma UI web local no Windows via PowerShell/BAT.
- Detectar Arduino CLI e placas/portas COM em linguagem simples.
- Se houver só uma placa conectada, selecionar automaticamente.
- Se houver mais de uma placa, mostrar uma lista para escolher.
- Compilar sketches Arduino/ESP32.
- Fazer upload com confirmação humana.
- Abrir monitor serial para depuração, com baud selecionável, limpar tela e envio de mensagens curtas.
- Atualizar missões do Davi pela UI.
- Criar templates seguros de sketches pequenos com preview e confirmação.
- Atualizar o Rotom Dex Lab automaticamente quando o projeto estiver em Git, ou por ZIP configurado.
- Conversar com o agente Hermes dedicado do Davi, sem expor shell irrestrito.

## Arquitetura

```text
Windows do Davi
 ├─ Start-RotomDexLab.ps1 / .bat
 ├─ Update-RotomDexLab.ps1 / .bat
 ├─ UI na rede interna: http://<ip-do-windows>:8765
 └─ Bridge FastAPI
      ├─ Arduino CLI allowlisted
      ├─ Serial monitor
      └─ Chat proxy para Hermes/Rotom Dex

Homelab
 └─ Hermes profile: rotom-dex
```

## Instalação no Windows

1. Instale Python 3.11+.
2. Instale Arduino CLI.
3. Copie ou clone este diretório para:

```powershell
C:\Users\Davi\Documents\rotom-dex-lab
```

4. Edite `config/projects.json` para apontar para o sketch do Davi.
5. Execute:

```powershell
.\Start-RotomDexLab.ps1
```

Ou clique em `Start-RotomDexLab.bat`.

O launcher cria o `.venv`, instala pacotes Python, valida que `fastapi`/`uvicorn` carregam, sobe o servidor, **espera o `/api/health` responder** e só então abre o navegador já com o PIN na URL. Se o servidor não ficar saudável, ele mostra um diagnóstico em português e aponta para o log (`rotom-dex-lab.log` e `rotom-dex-lab.log.err`).

## Variáveis de ambiente

Todas são opcionais; o app funciona offline e com PIN gerado automaticamente se nenhuma for definida.

| Variável | Padrão | Para que serve |
| --- | --- | --- |
| `ROTOM_DEX_SESSION_TOKEN` | gerado a cada início | PIN/token exigido nas ações da LAN. Defina para fixar um PIN estável. |
| `ROTOM_DEX_HERMES_URL` | (vazio) | Endpoint HTTP do cérebro online (Hermes/Rotom Dex). Sem ele, o chat fica em **modo offline**. |
| `ROTOM_DEX_HERMES_TOKEN` | (vazio) | Bearer token enviado ao backend Hermes, se ele exigir. |
| `ROTOM_DEX_HERMES_TIMEOUT_SECONDS` | `20` | Tempo máximo de espera pela resposta do Hermes antes de cair no modo offline. |
| `ROTOM_DEX_FAKE_SERIAL` | (desligado) | Se `=1`, o monitor serial gera dados de **simulação** (dev), claramente rotulados na UI. |
| `ROTOM_DEX_PORT` | `8765` | Porta do servidor. |
| `ROTOM_DEX_BIND_HOST` | `0.0.0.0` | Interface de bind. Use `127.0.0.1` para restringir só a este computador. |
| `ROTOM_DEX_SKIP_UPDATE` | (desligado) | Se `=1`, pula o auto-update no início. |
| `ROTOM_DEX_UPDATE_URL` / `ROTOM_DEX_UPDATE_SHA256` | (vazio) | Atualização por ZIP em vez de Git (veja abaixo). |

## PIN/token de acesso (camada de segurança da LAN)

Como o servidor escuta em `0.0.0.0`, qualquer aparelho da rede consegue alcançá-lo. Por isso as ações (procurar placa, compilar, enviar, serial, chat) exigem um PIN:

- O `Start-RotomDexLab.ps1` gera (ou usa o `ROTOM_DEX_SESSION_TOKEN`) e abre o navegador com o PIN já embutido na URL (`http://<ip>:8765/?token=...`).
- Ao iniciar, o servidor também imprime no console/log o endereço local com o PIN, útil quando você roda o `uvicorn` direto.
- `/api/health` fica aberto (sem PIN) só para o diagnóstico de saúde.
- Sem PIN ou com PIN errado, as ações respondem `401` com uma mensagem amigável e a UI orienta a reabrir pelo atalho do papai.

Isto é uma proteção doméstica simples, não autenticação corporativa: sem contas, sem TLS, sem exposição à internet.

## Chat: online (Hermes) x offline

- **Online:** com `ROTOM_DEX_HERMES_URL` configurado, cada mensagem do Davi é enviada ao backend junto com o contexto (projeto, placa selecionada, último resultado de comando, placas detectadas). O Rotom responde com o texto do backend e sugere ações.
- **Offline / falha:** sem URL configurada, ou se o backend demorar/errar, o chat **diz claramente que está offline** e ainda sugere ações locais seguras (procurar placa, compilar, enviar, abrir serial) com base nas palavras da mensagem. Ele nunca finge que o agente real respondeu.
- Ações vindas do backend são **normalizadas e validadas** no servidor: tipos desconhecidos são descartados e a confirmação de upload nunca pode ser desligada por um backend remoto.
- O modo offline agora também pode sugerir diagnóstico do papai e templates seguros quando o Davi mencionar status, diagnóstico, sketch, exemplo ou motor.

## Diagnóstico do papai

A UI tem o botão **Diagnóstico do papai**, que chama `/api/diagnostics` e reúne em um só lugar:

- status do Arduino CLI;
- core/FQBN padrão;
- caminho do sketch configurado;
- modo serial real ou simulação;
- portas detectadas, porta selecionada e saída bruta do `arduino-cli board list`.

Use isso antes de debugar às cegas quando a placa não aparece ou o upload falha.

## Monitor serial

O monitor serial permite escolher baud rate (`115200`, `9600`, `57600`, `74880`), limpar a tela e enviar uma mensagem curta para a placa pela serial. O envio só funciona depois de abrir uma sessão serial e não expõe shell nem comandos de sistema.

## Missões e templates

- As missões vêm de `config/missions.json` e podem ser marcadas como `todo`, `doing` ou `done` pela UI.
- Templates seguros aparecem na seção **Templates seguros**. O usuário pode ver preview e criar um `.ino` pequeno na pasta do projeto, sempre com confirmação.

## Atualizações no Windows

O Davi não precisa editar código para atualizar.

Opção recomendada:

- Instalar o projeto como clone Git.
- Ao abrir `Start-RotomDexLab.bat`, o script roda `git pull --ff-only` antes de iniciar.
- Para atualizar manualmente, clicar em `Update-RotomDexLab.bat`.

Opção sem Git:

- Defina `ROTOM_DEX_UPDATE_URL` apontando para um ZIP publicado por você em HTTPS.
- Defina também `ROTOM_DEX_UPDATE_SHA256` com o SHA-256 esperado do ZIP.
- O script `Update-RotomDexLab.ps1` baixa o ZIP, confere o hash e atualiza os arquivos.
- Ele preserva arquivos locais porque copia sem apagar o que não veio no ZIP; também não sobrescreve `.venv`, `.git`, `__pycache__` nem `config/projects.json`.

Para pular atualização em um teste rápido:

```powershell
$env:ROTOM_DEX_SKIP_UPDATE = "1"
.\Start-RotomDexLab.ps1
```

## Segurança

- Por padrão, o launcher Windows sobe o servidor em `0.0.0.0` e abre a UI pelo IP real do Windows, por exemplo `http://192.168.31.x:8765`, para acesso por qualquer dispositivo da rede interna.
- Use apenas em rede doméstica confiável; a bridge expõe ações de Arduino/serial na LAN.
- Se quiser restringir temporariamente ao próprio Windows, execute com `ROTOM_DEX_BIND_HOST=127.0.0.1`.
- Não existe endpoint de shell livre.
- Subprocessos usam lista de argumentos, não `shell=True`.
- Paths são validados para permanecer dentro do diretório permitido do projeto.
- Upload exige confirmação explícita no request/UI.
- Apenas FQBNs allowlisted são aceitos.

## Desenvolvimento local Linux

```bash
cd /home/hermes/projects/rotom-dex-lab
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
uvicorn bridge.server:app --host 0.0.0.0 --port 8765
# Acesse de outro dispositivo na rede usando http://<ip-do-host>:8765
```

## Solução de problemas (Windows)

- **O navegador não abriu / "não respondeu a tempo":** o launcher já mostra as últimas linhas de erro. Abra `rotom-dex-lab.log.err` na pasta do projeto. Causas comuns: porta `8765` em uso (defina outra com `ROTOM_DEX_PORT`) ou dependências Python faltando.
- **"Token de acesso ausente ou inválido":** você abriu a UI sem `?token=...`. Feche a aba e reabra pelo atalho; ou copie a URL completa que o launcher imprimiu (com o PIN).
- **Botões de Arduino falham:** confira se o `arduino-cli` está no PATH (`arduino-cli version`). O launcher avisa quando não encontra.
- **"Falta instalar o pacote da placa (ESP32)":** rode `arduino-cli core install esp32:esp32`.
- **"A porta está ocupada":** feche o Arduino IDE ou outro monitor serial e tente de novo.
- **Quero simular sem placa:** defina `ROTOM_DEX_FAKE_SERIAL=1` antes de iniciar; a UI mostra "Modo simulação (dev)".

## Próximas etapas

- Configurar e testar um backend real em `ROTOM_DEX_HERMES_URL` para o perfil Hermes `rotom-dex`.
- Validar o fluxo completo no Windows real do Davi com a ESP32 conectada: detectar placa, compilar, enviar e ler serial.
- Evoluir missões para edição/registro de progresso pela UI, mantendo confirmação adulta para mudanças sensíveis.
- Adicionar leitura/patch de arquivos com diff e confirmação, se o Rotom for ganhar ajuda direta no código do projeto.
