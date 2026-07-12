import subprocess
import sys

from backend.database.base import Base


def test_alembic_upgrade_head_runs_cleanly_against_a_throwaway_database(tmp_path) -> None:
    """Ensures alembic upgrade head runs cleanly against a throwaway database."""
    db_path = tmp_path / "migration_check.db"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-x",
            f"sqlalchemy.url=sqlite:///{db_path}", "upgrade", "head"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_migrated_schema_has_every_column_the_orm_model_declares() -> None:
    """Ensures migrated schema has every column the orm model declares."""
    import asyncio
    from sqlalchemy import inspect
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import StaticPool
    from backend.domain.users.model import User

    async def check() -> None:
        """Supports the test suite by check."""
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        async with engine.connect() as conn:
            await conn.run_sync(Base.metadata.create_all)
            columns = await conn.run_sync(
                lambda sync_conn: {c["name"]
                                   for c in inspect(sync_conn).get_columns("users")}
            )
        model_columns = {c.name for c in User.__table__.columns}
        assert model_columns <= columns, f"Migration is missing: {model_columns - columns}"

    asyncio.run(check())


def test_alembic_head_creates_rbac_and_billing_tables(tmp_path) -> None:
    """Ensures the Alembic head includes the new RBAC and billing schema."""
    import sqlite3

    db_path = tmp_path / "rbac_billing_schema.db"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-x",
            f"sqlalchemy.url=sqlite:///{db_path}", "upgrade", "head"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

    expected = {
        "roles",
        "permissions",
        "role_permissions",
        "user_roles",
        "plans",
        "features",
        "plan_features",
        "subscriptions",
        "payment_events",
        "invoices",
        "notifications",
        "api_keys",
        "audit_log_entries",
        "webhook_endpoints",
        "webhook_deliveries",
    }
    missing = expected - tables
    assert not missing, f"Migration is missing tables: {sorted(missing)}"


def test_alembic_head_migrates_product_price_to_price_cents(tmp_path) -> None:
    import sqlite3

    db_path = tmp_path / "product_price_migration.db"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-x",
            f"sqlalchemy.url=sqlite:///{db_path}", "upgrade", "head"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    with sqlite3.connect(db_path) as conn:
        columns = {
            row[1]: row[2]
            for row in conn.execute(
                "PRAGMA table_info('products')"
            )
        }

    assert "price_cents" in columns, "Migration must include products.price_cents"
    assert "price" not in columns, "Migration must not leave a floating-point products.price column"
    assert columns["price_cents"].upper() in {"INTEGER", "INT"}


def test_alembic_head_preserves_payment_event_unique_constraint(tmp_path) -> None:
    import sqlite3

    db_path = tmp_path / "migration_constraints.db"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-x",
            f"sqlalchemy.url=sqlite:///{db_path}", "upgrade", "head"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    with sqlite3.connect(db_path) as conn:
        unique_indexes = [
            row[1]
            for row in conn.execute(
                "PRAGMA index_list('payment_events')"
            )
            if row[2] == 1
        ]

        unique_columns = []
        for index_name in unique_indexes:
            columns = [
                row[2]
                for row in conn.execute(
                    f"PRAGMA index_info('{index_name}')"
                )
            ]
            unique_columns.append(set(columns))

    assert any(
        columns == {"provider", "provider_event_id"}
        for columns in unique_columns
    ), "Migration must preserve the payment_events unique constraint"
