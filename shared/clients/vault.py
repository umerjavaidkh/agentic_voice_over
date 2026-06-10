# shared/clients/vault.py

import json
import os


class AzureKeyVaultClient:
    """Azure Key Vault client for tenant FSM credentials.

    Production implementation uses ManagedIdentityCredential + SecretClient.
    See docs/09_Security_Compliance.Plan.md section 2.
    """

    def __init__(self, vault_url: str | None = None):
        self.vault_url = vault_url or os.getenv("AZURE_KEY_VAULT_URL", "")

    async def get_secret(self, name: str) -> str:
        raise NotImplementedError("AzureKeyVaultClient.get_secret is not implemented in dev stub")

    async def get_tenant_config(self, tenant_id: str) -> dict:
        raw = await self.get_secret(f"tenant-config-{tenant_id}")
        return json.loads(raw)
