from alembic import op
import sqlalchemy as sa


revision = "20260704_initial_schema"
down_revision = None
branch_labels = None
dependencies = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(),
                  nullable=False, server_default="true"),
        sa.Column("is_verified", sa.Boolean(),
                  nullable=False, server_default="false"),
        sa.Column("is_superuser", sa.Boolean(),
                  nullable=False, server_default="false"),
        sa.Column("failed_login_attempts", sa.Integer(),
                  nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("role", sa.String(length=50),
                  nullable=False, server_default="user"),
        sa.Column("permissions", sa.JSON(), nullable=False,
                  server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_username"),
                    "users", ["username"], unique=True)

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("price", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_products_id"), "products", ["id"], unique=False)
    op.create_index(op.f("ix_products_name"),
                    "products", ["name"], unique=True)

    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False, unique=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("is_system", sa.Boolean(),
                  nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_roles_id"), "roles", ["id"], unique=False)
    op.create_index(op.f("ix_roles_key"), "roles", ["key"], unique=False)

    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False, unique=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_permissions_id"),
                    "permissions", ["id"], unique=False)
    op.create_index(op.f("ix_permissions_key"),
                    "permissions", ["key"], unique=False)

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"]),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )

    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.PrimaryKeyConstraint("user_id", "role_id"),
    )

    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False, unique=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("price_cents", sa.Integer(),
                  nullable=False, server_default="0"),
        sa.Column("billing_interval", sa.String(length=20),
                  nullable=False, server_default="month"),
        sa.Column("is_active", sa.Boolean(),
                  nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_plans_id"), "plans", ["id"], unique=False)

    op.create_table(
        "features",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False, unique=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_features_id"), "features", ["id"], unique=False)

    op.create_table(
        "plan_features",
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("feature_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"]),
        sa.ForeignKeyConstraint(["feature_id"], ["features.id"]),
        sa.PrimaryKeyConstraint("plan_id", "feature_id"),
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50),
                  nullable=False, server_default="active"),
        sa.Column("provider", sa.String(length=50),
                  nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_subscriptions_id"),
                    "subscriptions", ["id"], unique=False)

    op.create_table(
        "payment_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload", sa.String(length=4000), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_payment_events_id"),
                    "payment_events", ["id"], unique=False)
    op.create_index(op.f("ix_payment_events_provider_event_id"),
                    "payment_events", ["provider_event_id"], unique=False)

    op.execute(
        sa.text(
            "INSERT INTO roles (key, name, description, is_system) VALUES ('user', 'User', 'Default user role', 1), ('staff', 'Staff', 'Staff role', 1), ('admin', 'Admin', 'Administrative role', 1)"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO permissions (key, name, description) VALUES ('rbac.manage', 'Manage RBAC', 'Manage roles and permissions'), ('billing.manage', 'Manage Billing', 'Manage billing configuration'), ('system.billing_toggle', 'Toggle Billing System', 'Toggle billing system availability')"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO plans (key, name, price_cents, billing_interval, is_active) VALUES ('free', 'Free', 0, 'month', 1)"
        )
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_payment_events_provider_event_id"),
                  table_name="payment_events")
    op.drop_index(op.f("ix_payment_events_id"), table_name="payment_events")
    op.drop_table("payment_events")
    op.drop_index(op.f("ix_subscriptions_id"), table_name="subscriptions")
    op.drop_table("subscriptions")
    op.drop_table("plan_features")
    op.drop_index(op.f("ix_features_id"), table_name="features")
    op.drop_table("features")
    op.drop_index(op.f("ix_plans_id"), table_name="plans")
    op.drop_table("plans")
    op.drop_table("user_roles")
    op.drop_table("role_permissions")
    op.drop_index(op.f("ix_permissions_key"), table_name="permissions")
    op.drop_index(op.f("ix_permissions_id"), table_name="permissions")
    op.drop_table("permissions")
    op.drop_index(op.f("ix_roles_key"), table_name="roles")
    op.drop_index(op.f("ix_roles_id"), table_name="roles")
    op.drop_table("roles")
    op.drop_index(op.f("ix_products_name"), table_name="products")
    op.drop_index(op.f("ix_products_id"), table_name="products")
    op.drop_table("products")
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_table("users")
