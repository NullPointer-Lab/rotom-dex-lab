from __future__ import annotations

import os
import secrets

TOKEN_MISSING_MESSAGE = (
    "Token de acesso ausente ou inválido. Abra o Rotom Dex Lab pelo atalho do papai."
)


class SessionAuth:
    """Lightweight LAN session token.

    This is a home-network safety layer, not enterprise auth. A token is read
    from ROTOM_DEX_SESSION_TOKEN or generated on startup. Action endpoints
    require it; the initial page load gets the token from the opened URL.
    """

    def __init__(self, token: str | None = None):
        provided = token if token is not None else os.environ.get("ROTOM_DEX_SESSION_TOKEN")
        self.token = provided.strip() if provided and provided.strip() else secrets.token_urlsafe(16)

    def check(self, provided: str | None) -> bool:
        if not provided:
            return False
        return secrets.compare_digest(provided, self.token)
