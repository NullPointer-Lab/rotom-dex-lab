# Rotom Dex Lab

Interface local para o Davi conversar com o agente **Rotom Dex** e operar, de forma controlada, comandos Arduino CLI para projetos ESP32/robótica.

## Objetivo

- Abrir uma UI web local no Windows via PowerShell/BAT.
- Detectar Arduino CLI e placas/portas COM em linguagem simples.
- Se houver só uma placa conectada, selecionar automaticamente.
- Se houver mais de uma placa, mostrar uma lista para escolher.
- Compilar sketches Arduino/ESP32.
- Fazer upload com confirmação humana.
- Abrir monitor serial para depuração.
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

O launcher cria o `.venv`, instala pacotes Python, procura atualização e abre o navegador sozinho.

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

## Próximas etapas

- Conectar `/api/chat` ao perfil Hermes `rotom-dex` via API/webhook.
- Adicionar leitura/patch de arquivos com diff e confirmação.
- Persistir missões/progresso por projeto.
- Testar no Windows real do Davi com a ESP32 conectada.
