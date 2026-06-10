# services/dispatch-adapter/adapters/service_titan_auth.py

from datetime import datetime, timedelta

import httpx


class ServiceTitanAuth:
    TOKEN_URL = "https://auth.servicetitan.io/connect/token"

    def __init__(self, client_id: str, client_secret: str, tenant_id: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.st_tenant_id = tenant_id
        self._token: str | None = None
        self._expires_at: datetime | None = None

    async def get_token(self) -> str:
        if self._token and datetime.utcnow() < self._expires_at:
            return self._token

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data["access_token"]
            self._expires_at = datetime.utcnow() + timedelta(seconds=data["expires_in"] - 60)
            return self._token
