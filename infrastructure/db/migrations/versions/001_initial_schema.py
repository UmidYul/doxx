from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def _store_table(name: str) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("price", sa.Numeric(15, 2), nullable=True),
        sa.Column("in_stock", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column(
            "characteristics",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("images", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column(
            "parsed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("raw_html", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url"),
    )


def upgrade() -> None:
    for table in (
        "mediapark_products",
        "olx_products",
        "texnomart_products",
        "makro_products",
        "uzum_products",
    ):
        _store_table(table)

    op.create_table(
        "parse_cache",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=True),
        sa.Column("last_price", sa.Numeric(15, 2), nullable=True),
        sa.Column("last_in_stock", sa.Boolean(), nullable=True),
        sa.Column("last_parsed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("crm_listing_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("crm_product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url"),
    )
    op.create_index("idx_cache_source", "parse_cache", ["source_name", "source_id"], unique=False)
    op.create_index("idx_cache_url", "parse_cache", ["url"], unique=False)

    op.create_table(
        "parse_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("items_parsed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("items_changed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("items_new", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "errors",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'running'")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "parse_queue",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column(
            "scheduled_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_queue_schedule", "parse_queue", ["status", "scheduled_at"], unique=False)

    op.create_table(
        "pending_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_pending_status", "pending_events", ["status", "retry_count"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_pending_status", table_name="pending_events")
    op.drop_table("pending_events")

    op.drop_index("idx_queue_schedule", table_name="parse_queue")
    op.drop_table("parse_queue")

    op.drop_table("parse_logs")

    op.drop_index("idx_cache_url", table_name="parse_cache")
    op.drop_index("idx_cache_source", table_name="parse_cache")
    op.drop_table("parse_cache")

    for table in (
        "uzum_products",
        "makro_products",
        "texnomart_products",
        "olx_products",
        "mediapark_products",
    ):
        op.drop_table(table)
