from __future__ import annotations

from typing import Any

from config.settings import settings
from domain.crm_lifecycle import CrmIdentityContext


def should_use_catalog_precheck(_identity: CrmIdentityContext) -> bool:
    """Opt-in only; never part of default product_found safety path."""
    return bool(settings.PARSER_USE_CATALOG_FIND_PRECHECK)


def build_catalog_find_query(identity: CrmIdentityContext) -> dict[str, Any]:
    """Build GET ``/api/parser/catalog/find`` query params / JSON body fragment.

    Priority: external_ids → barcode → title fuzzy (CRM applies brand+title server-side).
    """
    q: dict[str, Any] = {
        "external_ids": dict(identity.external_ids or {}),
        "barcode": identity.barcode,
        "source_name": identity.source_name,
        "source_url": identity.source_url,
        "entity_key": identity.entity_key,
    }
    return {k: v for k, v in q.items() if v is not None and v != {}}
