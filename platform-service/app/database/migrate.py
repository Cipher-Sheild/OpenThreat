"""Upgrade fresh or legacy local databases without deleting existing records."""
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from database.database import engine


def upgrade_database():
    root = Path(__file__).resolve().parent.parent
    config = Config(str(root / 'alembic.ini'))
    config.set_main_option('script_location', str(root / 'database' / 'migrations'))
    tables = set(inspect(engine).get_table_names())
    if 'documents' in tables and 'alembic_version' not in tables:
        required = {'sources', 'documents', 'document_versions', 'entities', 'entity_aliases', 'relations', 'behaviors', 'evidence', 'intelligence_changes'}
        if not required <= tables:
            raise RuntimeError('Database has a partial legacy schema; automatic upgrade stopped to preserve data.')
        command.stamp(config, '001_initial_schema')
    command.upgrade(config, 'head')
