from alembic import op
import sqlalchemy as sa


revision = "20260707_add_missing_user_columns"
down_revision = "20260704_initial_schema"
branch_labels = None
dependencies = None


def upgrade() -> None:
    # --- columns the ORM model requires that the original migration never created ---
    op.add_column(
        "users",
        sa.Column("is_verified", sa.Boolean(),
                  nullable=False, server_default="false"),
    )
    op.add_column(
        "users",
        sa.Column("failed_login_attempts", sa.Integer(),
                  nullable=False, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )

    # --- created_at/updated_at were typed as VARCHAR(50) instead of a real timestamp ---
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("users", recreate="always") as batch_op:
            batch_op.alter_column(
                "created_at",
                existing_type=sa.String(length=50),
                type_=sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            )
            batch_op.alter_column(
                "updated_at",
                existing_type=sa.String(length=50),
                type_=sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            )
        with op.batch_alter_table("products", recreate="always") as batch_op:
            batch_op.alter_column(
                "created_at",
                existing_type=sa.String(length=50),
                type_=sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            )
            batch_op.alter_column(
                "updated_at",
                existing_type=sa.String(length=50),
                type_=sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            )
    else:
        op.alter_column(
            "users", "created_at",
            type_=sa.DateTime(timezone=True),
            postgresql_using="created_at::timestamptz",
            server_default=sa.text("now()"),
            nullable=False,
        )
        op.alter_column(
            "users", "updated_at",
            type_=sa.DateTime(timezone=True),
            postgresql_using="updated_at::timestamptz",
            server_default=sa.text("now()"),
            nullable=False,
        )
        op.alter_column(
            "products", "created_at",
            type_=sa.DateTime(timezone=True),
            postgresql_using="created_at::timestamptz",
            server_default=sa.text("now()"),
            nullable=False,
        )
        op.alter_column(
            "products", "updated_at",
            type_=sa.DateTime(timezone=True),
            postgresql_using="updated_at::timestamptz",
            server_default=sa.text("now()"),
            nullable=False,
        )


def downgrade() -> None:
    op.alter_column("products", "updated_at",
                    type_=sa.String(length=50), nullable=True)
    op.alter_column("products", "created_at",
                    type_=sa.String(length=50), nullable=True)
    op.alter_column("users", "updated_at",
                    type_=sa.String(length=50), nullable=True)
    op.alter_column("users", "created_at",
                    type_=sa.String(length=50), nullable=True)
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_attempts")
    op.drop_column("users", "is_verified")
