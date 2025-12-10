import os
import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from sqlalchemy import create_engine, inspect, text, MetaData, Table, Column, ForeignKey
from sqlalchemy.orm import Session
from ..database import SessionLocal
from ..models import Base, Course, Video, Question, Answer, VideoProgress, Transcript

# Path to store sync state
SYNC_STATE_FILE = "backend/sync_state.json"
REMOTE_PREFIX = "learning_system_"

class SyncService:
    def __init__(self, remote_url: Optional[str] = None):
        self.remote_url = remote_url
        
        # If no explicit URL, try to build from env vars
        if not self.remote_url:
            user = os.getenv("sql_user")
            pwd = os.getenv("sql_pwd")
            host = os.getenv("sql_host")
            db = os.getenv("sql_db")
            
            if user and host and db:
                self.remote_url = f"mysql+pymysql://{user}:{pwd}@{host}/{db}"
            else:
                self.remote_url = os.getenv("REMOTE_DB_URL")

        self.remote_engine = None
        self.remote_metadata = None
        
        if self.remote_url:
            try:
                self.remote_engine = create_engine(self.remote_url)
                self._prepare_remote_metadata()
            except Exception as e:
                print(f"Sync Init Error: {e}")

    def _prepare_remote_metadata(self):
        """
        Creates a new MetaData object where all tables from Base.metadata
        are cloned with the REMOTE_PREFIX and FKs are updated.
        """
        self.remote_metadata = MetaData()
        
        # We must process in dependency order or just simple iteration?
        # Metadata.sorted_tables gives dependency order.
        for original_table in Base.metadata.sorted_tables:
            new_name = f"{REMOTE_PREFIX}{original_table.name}"
            
            new_columns = []
            for col in original_table.columns:
                # Clone column args
                col_args = [col.name, col.type]
                
                # Handle Foreign Keys
                # If FK points to 'courses.id', we want 'learning_system_courses.id'
                new_fks = []
                for fk in col.foreign_keys:
                    # fk.target_fullname is usually 'tablename.colname'
                    target_table, target_col = fk.target_fullname.split('.')
                    new_target = f"{REMOTE_PREFIX}{target_table}.{target_col}"
                    new_fks.append(ForeignKey(new_target))
                
                # Reconstruct column keyword args
                kwargs = {
                    'primary_key': col.primary_key,
                    'nullable': col.nullable,
                    'unique': col.unique,
                    'index': col.index,
                    'default': col.default
                }
                
                new_columns.append(Column(*col_args, *new_fks, **kwargs))
                
            # Create new Table in remote_metadata
            Table(new_name, self.remote_metadata, *new_columns)

    def _get_state(self) -> Dict:
        if os.path.exists(SYNC_STATE_FILE):
            try:
                with open(SYNC_STATE_FILE, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {"last_sync": None}

    def _save_state(self, state: Dict):
        with open(SYNC_STATE_FILE, 'w') as f:
            json.dump(state, f)

    def can_sync(self, force: bool = False) -> Dict:
        if not self.remote_url:
            return {"allowed": False, "reason": "No REMOTE_DB_URL configured."}

        try:
            with self.remote_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as e:
            return {"allowed": False, "reason": f"Remote DB unreachable: {str(e)}"}

        if force:
            return {"allowed": True, "reason": "Force sync requested."}

        state = self._get_state()
        last_sync = state.get("last_sync")
        if last_sync:
            last_time = datetime.fromisoformat(last_sync)
            if datetime.now() - last_time < timedelta(hours=6):
                return {"allowed": False, "reason": f"Last sync was less than 6 hours ago ({last_sync})."}
        
        return {"allowed": True, "reason": "Ready to sync."}

    def _calculate_checksum(self, row: Base) -> str:
        data_str = ""
        inst = inspect(row)
        for attr in inst.mapper.column_attrs:
            val = getattr(row, attr.key)
            data_str += str(val)
        return hashlib.sha256(data_str.encode('utf-8')).hexdigest()

    def _calculate_row_checksum(self, row_dict: Dict, table: Table) -> str:
        """Calc checksum from a dictionary (for remote verification)."""
        # We need to sort by column order to match internal logic
        data_str = ""
        # This naive implementation assumes keys match column names and order might vary
        # Better to rely on sorted columns
        # For simplicity, we assume we just check integrity by attempting update
        # But to be consistent with _calculate_checksum(Base), we need strict ordering.
        # Let's Skip CHECKING remote checksum for now and rely on Upsert (Update if PK exists)
        return ""

    def _sync_table_core(self, model_class, remote_table_name, local_db: Session) -> Dict:
        """
        Syncs using Core SQL.
        """
        local_rows = local_db.query(model_class).all()
        remote_table = self.remote_metadata.tables[remote_table_name]
        
        synced = 0
        updated = 0
        
        with self.remote_engine.connect() as conn:
            for row in local_rows:
                # Prepare data dict
                row_data = {c.name: getattr(row, c.name) for c in row.__table__.columns}
                
                # Check if exists
                stmt = remote_table.select().where(remote_table.c.id == row.id)
                existing = conn.execute(stmt).first()
                
                if not existing:
                    # Insert
                    ins = remote_table.insert().values(**row_data)
                    conn.execute(ins)
                    synced += 1
                else:
                    # Update (Blind update for now, or check fields)
                    # We accept the cost of update to ensure consistency
                    upd = remote_table.update().where(remote_table.c.id == row.id).values(**row_data)
                    conn.execute(upd)
                    updated += 1
            
            conn.commit()
        
        return {"synced": synced, "updated": updated, "total": len(local_rows)}

    def run_sync(self, force: bool = False, reset: bool = False) -> Dict:
        check = self.can_sync(force)
        if not check['allowed']:
            return {"status": "skipped", "message": check['reason']}

        if reset:
            try:
                self.remote_metadata.drop_all(bind=self.remote_engine)
            except Exception as e:
                print(f"Warning dropping tables: {e}")

        # Create Tables with PREFIX
        self.remote_metadata.create_all(bind=self.remote_engine)
        
        local_db = SessionLocal()
        results = {}
        
        try:
            # Sync in order. 
            # Note: _prepare_remote_metadata uses sorted_tables, but we need to map Model -> RemoteTable
            
            # Map Models to their original table names explicitly to find the prefixed version
            mapping = [
                (Course, "courses"),
                (Video, "videos"),
                (Transcript, "transcripts"),
                (Question, "questions"),
                (Answer, "answers"),
                (VideoProgress, "video_progress")
            ]
            
            for model_cls, orig_name in mapping:
                remote_name = f"{REMOTE_PREFIX}{orig_name}"
                results[model_cls.__name__] = self._sync_table_core(model_cls, remote_name, local_db)
            
            self._save_state({"last_sync": datetime.now().isoformat()})
            return {"status": "success", "details": results}

        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            local_db.close()
