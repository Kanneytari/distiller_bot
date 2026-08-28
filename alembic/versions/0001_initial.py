"""Initial schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255)),
        sa.Column("first_name", sa.String(length=255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    op.create_table(
        "equipment",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("equipment_type", sa.String(length=50), nullable=False),
        sa.Column("capacity_l", sa.Numeric(10, 3)),
        sa.Column("power_kw", sa.Numeric(10, 3)),
        sa.Column("properties", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_equipment_user_id", "equipment", ["user_id"])

    op.create_table(
        "recipes",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("owner_user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("category", sa.String(length=100)),
        sa.Column("base_volume_l", sa.Numeric(10, 3)),
        sa.Column("is_draft", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_recipes_owner_user_id", "recipes", ["owner_user_id"])
    op.create_index("ix_recipes_category", "recipes", ["category"])

    op.create_table(
        "recipe_ingredients",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("recipe_id", sa.BigInteger(), sa.ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Numeric(12, 3)),
        sa.Column("unit", sa.String(length=50)),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_recipe_ingredients_recipe_id", "recipe_ingredients", ["recipe_id"])

    op.create_table(
        "recipe_steps",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("recipe_id", sa.BigInteger(), sa.ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=255)),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_recipe_steps_recipe_id", "recipe_steps", ["recipe_id"])

    op.create_table(
        "saved_recipes",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("recipe_id", sa.BigInteger(), sa.ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "drinks",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("recipe_id", sa.BigInteger(), sa.ForeignKey("recipes.id", ondelete="SET NULL")),
        sa.Column("current_stage", sa.String(length=100)),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_drinks_user_id", "drinks", ["user_id"])
    op.create_index("ix_drinks_recipe_id", "drinks", ["recipe_id"])
    op.create_index("ix_drinks_status", "drinks", ["status"])
    op.create_index("ix_drinks_user_status", "drinks", ["user_id", "status"])

    op.create_table(
        "drink_equipment",
        sa.Column("drink_id", sa.BigInteger(), sa.ForeignKey("drinks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("equipment_id", sa.BigInteger(), sa.ForeignKey("equipment.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.String(length=50)),
    )

    op.create_table(
        "measurements",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("drink_id", sa.BigInteger(), sa.ForeignKey("drinks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("measurement_type", sa.String(length=50), nullable=False),
        sa.Column("value", sa.Numeric(14, 4), nullable=False),
        sa.Column("unit", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=255)),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_measurements_drink_id", "measurements", ["drink_id"])
    op.create_index("ix_measurements_drink_measured", "measurements", ["drink_id", "measured_at"])

    op.create_table(
        "drink_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("drink_id", sa.BigInteger(), sa.ForeignKey("drinks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255)),
        sa.Column("text", sa.Text()),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_drink_events_drink_id", "drink_events", ["drink_id"])
    op.create_index("ix_drink_events_created_at", "drink_events", ["created_at"])
    op.create_index("ix_drink_events_drink_created", "drink_events", ["drink_id", "created_at"])

    op.create_table(
        "reminders",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("drink_id", sa.BigInteger(), sa.ForeignKey("drinks.id", ondelete="CASCADE")),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("remind_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_reminders_user_id", "reminders", ["user_id"])
    op.create_index("ix_reminders_drink_id", "reminders", ["drink_id"])
    op.create_index("ix_reminders_remind_at", "reminders", ["remind_at"])
    op.create_index("ix_reminders_status", "reminders", ["status"])
    op.create_index("ix_reminders_status_remind_at", "reminders", ["status", "remind_at"])


def downgrade() -> None:
    op.drop_table("reminders")
    op.drop_table("drink_events")
    op.drop_table("measurements")
    op.drop_table("drink_equipment")
    op.drop_table("drinks")
    op.drop_table("saved_recipes")
    op.drop_table("recipe_steps")
    op.drop_table("recipe_ingredients")
    op.drop_table("recipes")
    op.drop_table("equipment")
    op.drop_table("users")
