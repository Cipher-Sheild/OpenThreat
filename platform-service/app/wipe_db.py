import sys
import os
sys.path.append('platform-service/app')
from database.database import SessionLocal
from database.models import Source, Document, DocumentVersion, Entity, EntityAlias, Relation, Behavior, Evidence, IntelligenceChange, TemporalEvent

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Permanently delete platform intelligence. Back up PostgreSQL first.")
    parser.add_argument("--confirm-delete-all-intelligence", action="store_true")
    args = parser.parse_args()
    if not args.confirm_delete_all_intelligence:
        parser.error("Explicit --confirm-delete-all-intelligence is required.")
    db = SessionLocal()
    try:
        # Delete child tables first to respect foreign keys
        db.query(Evidence).delete()
        db.query(IntelligenceChange).delete()
        db.query(TemporalEvent).delete()
        db.query(Behavior).delete()
        db.query(Relation).delete()
        db.query(EntityAlias).delete()
        db.query(Entity).delete()
        db.query(DocumentVersion).delete()
        db.query(Document).delete()
        # Keeping Sources intact
        db.commit()
        print('Database wiped successfully (kept sources).')
    except Exception as e:
        db.rollback()
        print('Error:', e)
    finally:
        db.close()

if __name__ == "__main__":
    main()
