from __future__ import annotations
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Load .env for local runs (no-op in prod)
try:
    from dotenv import load_dotenv  # python-dotenv
    load_dotenv()
except Exception:
    pass

# ── Alembic Config object ───────────────────────────────────────────────────────────────────
config = context.config

# Inject DB URL from env into alembic.ini’s sqlalchemy.url
db_url = os.getenv("DATABASE_URL", "sqlite:///./savannah.db")
config.set_main_option("sqlalchemy.url", db_url)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Import your models’ metadata ────────────────────────
# Adjust ONE of these imports to match your app.
# Option A: app.database defines Base = declarative_base(); metadata = Base.metadata
try:
    from app.database import Base as _Base
    target_metadata = _Base.metadata
except Exception:
    # Option B: app.models defines Base
    from app.models import Base as _Base  # type: ignore
    target_metadata = _Base.metadata

# ── Offline & Online migration runners ───────────────────

def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,     # detect column type changes
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
