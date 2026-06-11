# shared/clients/call_records.py


async def create_call_record(conn, call_sid: str, tenant_id: str, caller_phone: str):
    await conn.execute(
        """
        INSERT INTO calls (call_sid, tenant_id, caller_phone, call_outcome)
        VALUES ($1, $2, $3, 'in_progress')
        """,
        call_sid,
        tenant_id,
        caller_phone,
    )
