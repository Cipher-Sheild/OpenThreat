"""Initial Schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-09-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table('sources',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('source_type', sa.String(), nullable=False),
    sa.Column('url', sa.String(), nullable=True),
    sa.Column('reliability', sa.Float(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('documents',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('source_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('content_hash', sa.String(), nullable=False),
    sa.Column('url', sa.String(), nullable=True),
    sa.Column('external_id', sa.String(), nullable=True),
    sa.Column('published_at', sa.DateTime(), nullable=True),
    sa.Column('first_seen_at', sa.DateTime(), nullable=True),
    sa.Column('processing_status', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['source_id'], ['sources.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('document_versions',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('version_hash', sa.String(), nullable=False),
    sa.Column('processed_at', sa.DateTime(), nullable=True),
    sa.Column('raw_content_path', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('entities',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('canonical_name', sa.String(), nullable=False),
    sa.Column('type', sa.String(), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('first_seen_at', sa.DateTime(), nullable=True),
    sa.Column('last_seen_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('entity_aliases',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('alias', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('relations',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('subject_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('relation_type', sa.String(), nullable=False),
    sa.Column('object_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('first_seen_at', sa.DateTime(), nullable=True),
    sa.Column('last_seen_at', sa.DateTime(), nullable=True),
    sa.Column('status', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['object_id'], ['entities.id'], ),
    sa.ForeignKeyConstraint(['subject_id'], ['entities.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('behaviors',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('description', sa.String(), nullable=False),
    sa.Column('mitre_attack_id', sa.String(), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
    sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('evidence',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('relation_id', postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column('behavior_id', postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column('snippet', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['behavior_id'], ['behaviors.id'], ),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
    sa.ForeignKeyConstraint(['relation_id'], ['relations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('intelligence_changes',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('entity_type', sa.String(), nullable=False),
    sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('change_type', sa.String(), nullable=False),
    sa.Column('timestamp', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )

def downgrade() -> None:
    op.drop_table('intelligence_changes')
    op.drop_table('evidence')
    op.drop_table('behaviors')
    op.drop_table('relations')
    op.drop_table('entity_aliases')
    op.drop_table('entities')
    op.drop_table('document_versions')
    op.drop_table('documents')
    op.drop_table('sources')
