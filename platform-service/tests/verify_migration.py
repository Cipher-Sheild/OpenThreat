"""Validate first installation against a uniquely named disposable PostgreSQL database."""
import os, sys, uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
from sqlalchemy import create_engine, text, inspect
from core.config import settings
admin=create_engine(settings.DATABASE_URL,isolation_level="AUTOCOMMIT")
name="openthreat_test_"+uuid.uuid4().hex
with admin.connect() as connection:
    connection.execute(text('CREATE DATABASE "'+name+'"'))
try:
    url=admin.url.set(database=name).render_as_string(hide_password=False)
    os.environ["DATABASE_URL"]=url
    from database.migrate import upgrade_database
    from database.database import engine
    upgrade_database();upgrade_database()
    inspector=inspect(engine)
    assert "temporal_events" in inspector.get_table_names()
    assert {"content","processing_error","embedding_status"}<={c["name"] for c in inspector.get_columns("documents")}
    assert next(c for c in inspector.get_columns("behaviors") if c["name"]=="entity_id")["nullable"]
    engine.dispose()
    print("Fresh PostgreSQL migration and repeat startup passed.")
finally:
    with admin.connect() as connection:
        connection.execute(text('DROP DATABASE "'+name+'" WITH (FORCE)'))
    admin.dispose()
