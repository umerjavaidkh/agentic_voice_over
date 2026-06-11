# services/voice-gateway/call_finisher.py

import os
from datetime import datetime, timezone

import httpx
from azure.identity.aio import ManagedIdentityCredential
from azure.storage.blob import ContentSettings
from azure.storage.blob.aio import BlobServiceClient

from shared.clients.db import DatabasePool

STORAGE_ACCOUNT_URL = os.getenv("AZURE_STORAGE_ACCOUNT_URL")
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
# e.g. "https://voiceagentstore.blob.core.windows.net"


def date_path() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year}/{now.month:02d}/{now.day:02d}"


def create_blob_service_client() -> BlobServiceClient:
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
    if connection_string:
        return BlobServiceClient.from_connection_string(connection_string)
    credential = ManagedIdentityCredential()
    return BlobServiceClient(
        account_url=STORAGE_ACCOUNT_URL,
        credential=credential,
    )


async def download_twilio_recording(
    recording_url: str,
    account_sid: str,
    auth_token: str,
) -> bytes:
    url = recording_url if recording_url.endswith(".mp3") else f"{recording_url}.mp3"
    async with httpx.AsyncClient() as client:
        response = await client.get(url, auth=(account_sid, auth_token))
        response.raise_for_status()
        return response.content


async def finalize_call(
    call_sid: str,
    tenant_id: str,
    recording_bytes: bytes,
    db: DatabasePool,
):
    blob_service = create_blob_service_client()

    blob_name = f"{tenant_id}/{date_path()}/{call_sid}.mp3"
    container_client = blob_service.get_container_client("recordings")

    await container_client.upload_blob(
        name=blob_name,
        data=recording_bytes,
        content_settings=ContentSettings(content_type="audio/mpeg"),
        metadata={
            "call_sid": call_sid,
            "tenant_id": tenant_id,
        },
        overwrite=False,
    )

    # Update call record with blob path
    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE calls SET recording_blob_path=$1 WHERE call_sid=$2",
            blob_name,
            call_sid,
        )
    await blob_service.close()
