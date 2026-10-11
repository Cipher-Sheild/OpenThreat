"""Preserve provenance, polarity, temporal events, and add query indexes."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '002_integrity_performance'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    additions = {
        'documents': [sa.Column('content', sa.Text()), sa.Column('processing_error', sa.Text()),
                      sa.Column('embedding_status', sa.String(), server_default='PENDING'),
                      sa.Column('processing_metadata', sa.JSON())],
        'document_versions': [sa.Column('content', sa.Text())],
        'relations': [sa.Column('negated', sa.Boolean(), nullable=False, server_default=sa.false()),
                      sa.Column('source_first_seen_at', sa.DateTime()), sa.Column('source_last_seen_at', sa.DateTime()),
                      sa.Column('review_required', sa.Boolean(), nullable=False, server_default=sa.false())],
        'evidence': [sa.Column('char_start', sa.Integer()), sa.Column('char_end', sa.Integer()), sa.Column('page_number', sa.Integer())],
        'intelligence_changes': [sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id')),
                                 sa.Column('reason', sa.Text())],
    }
    for table, columns in additions.items():
        existing = {column['name'] for column in inspector.get_columns(table)}
        for column in columns:
            if column.name not in existing:
                op.add_column(table, column)
    op.alter_column('behaviors', 'entity_id', nullable=True)
    if 'temporal_events' not in inspector.get_table_names():
        op.create_table('temporal_events',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id'), nullable=False),
            sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('entities.id'), nullable=False),
            sa.Column('event', sa.Text(), nullable=False), sa.Column('time', sa.String(), nullable=False),
            sa.Column('type', sa.String(), nullable=False), sa.Column('confidence', sa.Float(), nullable=False),
            sa.Column('evidence', sa.JSON()))
    from database.models import Base
    for table in Base.metadata.sorted_tables:
        existing = {i['name'] for i in sa.inspect(op.get_bind()).get_indexes(table.name)}
        for index in table.indexes:
            if index.name not in existing:
                index.create(op.get_bind())


def downgrade():
    raise RuntimeError('This additive provenance migration must not discard stored intelligence automatically.')
