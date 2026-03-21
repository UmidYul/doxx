from __future__ import annotations


class DBError(RuntimeError):
    """Raised when a Supabase/PostgREST operation fails after logging."""
