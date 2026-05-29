# Claude Code Goal — Make Rotom Dex Lab Genuinely Useful

> Goal document created from a product/codebase review with Claude Code. Use this as the single prompt for a Claude Code implementation run.

## Context

Project: `rotom-dex-lab`

Rotom Dex Lab is intended to be a local Windows web interface for Davi to use with ESP32/Arduino projects. It currently exposes a FastAPI bridge, a child-facing web UI, Arduino CLI wrappers, serial monitor endpoints, and a placeholder chat area.

The current product is not good enough: the Rotom chat does not really respond or do anything useful, the serial monitor is fake, the suggested chat actions are dead buttons, and the Windows boot path is fragile. The goal is not to add superficial polish; the goal is to make the program honestly useful, reliable, safe, and fun for a child using ESP32/Arduino.

## Mission

Transform Rotom Dex Lab into a working child-friendly Arduino/ESP32 assistant:

- Chat must either call a real configurable AI/Hermes backend or clearly say it is offline.
- Chat suggestions must execute real safe actions instead of showing placeholder alerts.
- Serial monitor must read real serial data via pyserial, with fake data only behind an explicit dev flag.
- Arduino actions must be robust, understandable, and translated into friendly Portuguese.
- Windows startup must be reliable and must not open the browser before the server is healthy.
- LAN-exposed actions must require a simple session token/PIN.
- The UI must feel like a guided mission console for Davi, not a JSON/debug panel.
- All new behavior must be covered by tests and verified with `pytest -q`.

## Product Principles

1. Honesty first: never fake hardware behavior without clearly marking dev/offline mode.
2. Child-first UX: explain errors in short friendly PT-BR and always suggest the next safe action.
3. Safe agency: chat can act, but risky actions such as upload require explicit human confirmation.
4. Useful before fancy: one real working loop is better than many decorative sections.
5. Narrow bridge: no arbitrary shell, no unrestricted filesystem, no unsafe LAN endpoints.
6. Incremental delivery: keep the repo green after each phase.

## Required Implementation Scope

### Phase 1 — Replace fake/stub behavior with honest behavior

#### Serial monitor

Modify `bridge/serial_monitor.py` so that:

- `SerialManager.open()` opens a real `serial.Serial` connection using the requested validated port and baud.
- WebSocket streaming reads real lines/bytes from the serial port.
- Closing a session closes the serial port cleanly.
- Port errors are converted into clear API/WebSocket messages in PT-BR.
- Fake serial output exists only if `ROTOM_DEX_FAKE_SERIAL=1` is set, and the UI labels it as simulation/dev mode.
- Add tests using mocks/fakes for `serial.Serial`; do not require hardware in CI.

#### Hermes/AI chat client

Modify `bridge/hermes_client.py` and `/api/chat` so that:

- Chat integration is configurable by environment variables, for example:
  - `ROTOM_DEX_HERMES_URL`
  - `ROTOM_DEX_HERMES_TOKEN`
  - optionally `ROTOM_DEX_HERMES_TIMEOUT_SECONDS`
- If the backend is configured, send the user message plus project/device context to it.
- If the backend is not configured or unreachable, return an explicit offline response such as:
  - `Estou offline agora, mas ainda consigo usar os botões para procurar placa, compilar, enviar e abrir serial.`
- Do not pretend the real Rotom agent answered when it did not.
- Add tests with mocked HTTP responses and failure cases.

#### Suggested actions

Modify `web/app.js` so suggested actions returned by chat are executable:

- `arduino.board_list` calls `/api/arduino/board-choices` and updates the board UI.
- `arduino.compile` calls `/api/arduino/compile` and appends a friendly chat/status result.
- `arduino.upload` asks confirmation and then calls `/api/arduino/upload` using the currently selected port.
- Invalid/missing port should lead to a friendly message, not an alert-only dead end.
- Keep dangerous actions confirmation-gated.

### Phase 2 — Make chat an actual safe command loop

Define a small internal action contract shared between backend and frontend. Suggested action objects should have a stable shape, for example:

```json
{
  "type": "arduino.compile",
  "label": "Testar o código agora",
  "requiresConfirmation": false,
  "params": {}
}
```

Implement backend-side normalization/validation for action types so arbitrary action names from an AI backend cannot trigger unexpected behavior.

For `/api/chat`, enrich context with:

- configured project id/name/sketch/default FQBN;
- current selected port if provided by frontend;
- last Arduino command result if provided by frontend;
- current board choices if known.

The agent should be able to guide a flow like:

1. User: `Rotom, testa meu projeto`.
2. Rotom suggests compile.
3. User clicks suggested action.
4. UI runs compile.
5. UI shows translated result and stores it as last result.
6. User can ask `o que deu errado?` and the backend gets the previous stderr/stdout context.

### Phase 3 — Robust Windows startup

Modify `Start-RotomDexLab.ps1` so that:

- It always runs the server using the `.venv` Python after creating/installing the venv.
- It validates that `fastapi` and `uvicorn` are importable in the chosen Python before launching.
- It starts the server in a way that logs errors to a visible local log file.
- It polls `/api/health` before opening the browser.
- If health never succeeds, it shows a friendly PT-BR diagnostic and points to the log.
- It does not blindly open the browser after a fixed `Sleep 2`.

Update README with the new startup behavior and troubleshooting steps.

### Phase 4 — Arduino CLI friendliness

Improve Arduino CLI UX:

- Detect whether the configured core/package for the default FQBN is installed.
- Translate common Arduino CLI errors into friendly messages:
  - Arduino CLI missing;
  - board/core package missing;
  - invalid FQBN;
  - port not found;
  - access denied / port busy;
  - compile error in sketch.
- Do not hide technical output; keep raw output inside “Detalhes para o papai”.
- Child-facing text should say what happened and what to try next.

Add tests for error translation.

### Phase 5 — Basic LAN safety

Because the app binds to `0.0.0.0` for LAN use, add a simple local session token/PIN:

- Generate a token on startup if `ROTOM_DEX_SESSION_TOKEN` is not provided.
- Serve the UI with the token embedded in the opened URL or in server-side config accessible only to the initial page load.
- Require the token for action endpoints:
  - compile;
  - upload;
  - serial open/close;
  - chat if it can trigger tool actions;
  - any future write/action endpoint.
- `/api/health` may remain open.
- Return 401/403 with friendly messages when token is missing/invalid.
- Restrict CORS appropriately if CORS is added.

Do not add heavyweight auth, user accounts, TLS, or internet exposure. This is a LAN/home safety layer, not enterprise auth.

### Phase 6 — Mission console polish

Make the UI genuinely pleasant:

- The main page should show a clear next step:
  - connect board;
  - choose/confirm board;
  - compile;
  - upload;
  - open serial;
  - ask Rotom for help.
- Debug JSON should stay behind “Detalhes para o papai”.
- Chat should show action result cards, not only raw JSON/status text.
- Mission list should not be hardcoded forever. Add a simple JSON-backed mission/progress API if small enough; otherwise make the hardcoded list visually secondary and document the follow-up.
- Avoid large frontend frameworks unless absolutely necessary. Keep it simple.

## Tests Required

Add or update tests so `pytest -q` covers:

- serial manager real-mode behavior with mocked `serial.Serial`;
- fake serial mode only when env flag is set;
- Hermes client configured success, unconfigured offline, timeout/error fallback;
- suggested action contract/normalization;
- API endpoints for auth/token-gated actions;
- Arduino CLI error translation;
- Windows launcher behavior where practical via script/static tests, or at least add explicit tests for any Python helpers factored out.

Do not require real ESP32 hardware for automated tests.

## Acceptance Criteria

The work is complete only when all of these are true:

1. `pytest -q` passes.
2. Chat does not return the same canned response for everything when a backend is configured.
3. If backend config is missing, chat clearly says it is offline and still guides the user to local actions.
4. Clicking suggested actions actually calls the corresponding local API and updates the UI.
5. Serial monitor reads from a real serial object in normal mode; fake stream is opt-in only.
6. Upload still requires explicit confirmation.
7. Action endpoints reject missing/invalid LAN token.
8. Windows launcher uses `.venv` Python and waits for `/api/health` before opening the browser.
9. Common Arduino CLI failures are shown in friendly PT-BR with technical detail hidden under parent/debug details.
10. README documents setup, env vars, offline mode, token/PIN, and troubleshooting.

## Out of Scope

Do not implement these in this iteration:

- Bluetooth joystick firmware.
- Motor control firmware.
- Full robot autonomy.
- Internet-exposed deployment.
- Enterprise auth/TLS/account management.
- Broad Windows shell access.
- Arbitrary file editing from the child-facing UI.
- Rewriting the frontend into React/Vue/etc. unless there is a very strong reason.

## Implementation Guidance

- Keep changes surgical and incremental.
- Prefer small helper functions with tests over large rewrites.
- Preserve current safety policies: argument-list subprocesses, FQBN allowlist, project-root path validation, upload confirmation.
- Make failures visible and understandable.
- Commit in logical chunks if performing a full implementation.
- Before finalizing, run:

```bash
pytest -q
git diff --check
```

## Final Response Expected From Claude Code

At the end, report:

- files changed;
- what now works that did not work before;
- any required environment variables;
- exact commands run and results;
- what still requires real Windows/ESP32 validation;
- any security trade-offs left for Isaac to decide.
