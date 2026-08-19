"""Single source of truth for platform token storage and retrieval.

Every token is encrypted (Fernet) before it is written and decrypted only
here when read. No other module touches the platform_connections table for
token operations.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.database import get_supabase
from app.schemas.connections import ConnectionResult, PlatformConnection
from app.services.token_encryption import decrypt_token, encrypt_token

TABLE = "platform_connections"
LOG_TABLE = "platform_connection_logs"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat()


def _row_to_connection(row: dict) -> PlatformConnection:
    """Map a DB row to a PlatformConnection with tokens DECRYPTED."""
    return PlatformConnection(
        id=row.get("id"),
        platform=row["platform"],
        status=row.get("status") or "disconnected",
        account_name=row.get("account_name"),
        account_id=row.get("account_id"),
        access_token=decrypt_token(row.get("access_token")),
        refresh_token=decrypt_token(row.get("refresh_token")),
        token_expires_at=row.get("token_expires_at"),
        scope=row.get("scope"),
        metadata=row.get("metadata") or {},
        last_used_at=row.get("last_used_at"),
        last_error=row.get("last_error"),
        connected_at=row.get("connected_at"),
    )


def save_connection(platform: str, result: ConnectionResult) -> PlatformConnection:
    """Upsert a connection from an auth result. Encrypts tokens, marks the
    connection connected, and clears any prior error."""
    supabase = get_supabase()
    payload = {
        "platform": platform,
        "status": "connected",
        "account_name": result.account_name,
        "account_id": result.account_id,
        "access_token": encrypt_token(result.access_token),
        "refresh_token": encrypt_token(result.refresh_token),
        "token_expires_at": _iso(result.token_expires_at),
        "scope": result.scope,
        "metadata": result.metadata or {},
        "last_error": None,
        "connected_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    supabase.table(TABLE).upsert(payload, on_conflict="platform").execute()
    return get_connection(platform)  # type: ignore[return-value]


def get_connection(platform: str) -> PlatformConnection | None:
    supabase = get_supabase()
    rows = (
        supabase.table(TABLE).select("*").eq("platform", platform).limit(1).execute()
    ).data
    if not rows:
        return None
    return _row_to_connection(rows[0])


def get_all_connections() -> list[PlatformConnection]:
    supabase = get_supabase()
    rows = supabase.table(TABLE).select("*").execute().data or []
    return [_row_to_connection(r) for r in rows]


def update_tokens(platform: str, new_tokens: ConnectionResult) -> None:
    """Update only the token-related fields after a refresh. Re-encrypts."""
    supabase = get_supabase()
    fields: dict = {
        "access_token": encrypt_token(new_tokens.access_token),
        "token_expires_at": _iso(new_tokens.token_expires_at),
        "status": "connected",
        "last_error": None,
        "updated_at": _now_iso(),
    }
    if new_tokens.refresh_token:
        fields["refresh_token"] = encrypt_token(new_tokens.refresh_token)
    if new_tokens.scope:
        fields["scope"] = new_tokens.scope
    supabase.table(TABLE).update(fields).eq("platform", platform).execute()


def mark_used(platform: str) -> None:
    get_supabase().table(TABLE).update({"last_used_at": _now_iso()}).eq(
        "platform", platform
    ).execute()


def mark_error(platform: str, error_message: str) -> None:
    get_supabase().table(TABLE).update(
        {"status": "error", "last_error": (error_message or "")[:2000], "updated_at": _now_iso()}
    ).eq("platform", platform).execute()


def mark_expired(platform: str) -> None:
    get_supabase().table(TABLE).update(
        {"status": "expired", "updated_at": _now_iso()}
    ).eq("platform", platform).execute()


def mark_disconnected(platform: str) -> None:
    """Clear all tokens and set status disconnected."""
    get_supabase().table(TABLE).update(
        {
            "status": "disconnected",
            "access_token": None,
            "refresh_token": None,
            "token_expires_at": None,
            "scope": None,
            "account_name": None,
            "account_id": None,
            "connected_at": None,
            "updated_at": _now_iso(),
        }
    ).eq("platform", platform).execute()


def log_event(platform: str, event: str, message: str = "", metadata: dict | None = None) -> None:
    """Append to platform_connection_logs. Never raises."""
    try:
        get_supabase().table(LOG_TABLE).insert(
            {
                "platform": platform,
                "event": event,
                "message": (message or "")[:2000],
                "metadata": metadata or {},
            }
        ).execute()
    except Exception:
        pass


def get_logs(platform: str | None = None, limit: int = 50) -> list[dict]:
    supabase = get_supabase()
    query = supabase.table(LOG_TABLE).select("*")
    if platform:
        query = query.eq("platform", platform)
    return query.order("created_at", desc=True).limit(limit).execute().data or []
