"""
Local SQLite database for offline development
Replaces MongoDB when it's not available
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Any, Dict
import sqlite3
from threading import Lock

DB_FILE = Path(__file__).parent / "katto_local.db"
DB_LOCK = Lock()


class LocalCollection:
    """Mock MongoDB collection using SQLite"""
    
    def __init__(self, collection_name: str):
        self.name = collection_name
        self._init_table()
    
    def _init_table(self):
        """Create table if it doesn't exist"""
        with DB_LOCK:
            conn = sqlite3.connect(DB_FILE)
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.name} (
                    _id TEXT PRIMARY KEY,
                    data TEXT NOT NULL
                )
            """)
            conn.commit()
            conn.close()
    
    def _get_id(self, doc: dict) -> str:
        """Generate or return document ID"""
        if "_id" not in doc:
            import uuid
            doc["_id"] = str(uuid.uuid4())
        return doc["_id"]
    
    async def find_one(self, query: dict) -> Optional[dict]:
        """Find first document matching query"""
        with DB_LOCK:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            
            cursor.execute(f"SELECT data FROM {self.name}")
            rows = cursor.fetchall()
            conn.close()
            
            for row in rows:
                doc = json.loads(row[0])
                if self._matches_query(doc, query):
                    return doc
            return None
    
    async def find(self, query: dict):
        """Find all documents matching query"""
        with DB_LOCK:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            
            cursor.execute(f"SELECT data FROM {self.name}")
            rows = cursor.fetchall()
            conn.close()
            
            results = []
            for row in rows:
                doc = json.loads(row[0])
                if self._matches_query(doc, query):
                    results.append(doc)
            
            return FindCursor(results)
    
    async def insert_one(self, doc: dict) -> dict:
        """Insert a single document"""
        doc_id = self._get_id(doc)
        doc["inserted_at"] = datetime.utcnow().isoformat()
        
        with DB_LOCK:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            
            cursor.execute(
                f"INSERT OR REPLACE INTO {self.name} (_id, data) VALUES (?, ?)",
                (doc_id, json.dumps(doc))
            )
            conn.commit()
            conn.close()
        
        return {"inserted_id": doc_id}
    
    async def update_one(self, query: dict, update: dict) -> dict:
        """Update first document matching query"""
        with DB_LOCK:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            
            cursor.execute(f"SELECT _id, data FROM {self.name}")
            rows = cursor.fetchall()
            
            modified = 0
            for row_id, row_data in rows:
                doc = json.loads(row_data)
                if self._matches_query(doc, query):
                    if "$set" in update:
                        doc.update(update["$set"])
                    else:
                        doc.update(update)
                    
                    cursor.execute(
                        f"UPDATE {self.name} SET data = ? WHERE _id = ?",
                        (json.dumps(doc), row_id)
                    )
                    modified += 1
                    break
            
            conn.commit()
            conn.close()
        
        return {"modified_count": modified}
    
    async def delete_one(self, query: dict) -> dict:
        """Delete first document matching query"""
        with DB_LOCK:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            
            cursor.execute(f"SELECT _id, data FROM {self.name}")
            rows = cursor.fetchall()
            
            deleted = 0
            for row_id, row_data in rows:
                doc = json.loads(row_data)
                if self._matches_query(doc, query):
                    cursor.execute(f"DELETE FROM {self.name} WHERE _id = ?", (row_id,))
                    deleted += 1
                    break
            
            conn.commit()
            conn.close()
        
        return {"deleted_count": deleted}
    
    def _matches_query(self, doc: dict, query: dict) -> bool:
        """Check if document matches query"""
        for key, value in query.items():
            if key == "$or":
                # Handle $or operator
                if not any(self._matches_query(doc, {k: v for k, v in cond.items()}) for cond in value):
                    return False
            else:
                if key not in doc:
                    return False
                if isinstance(value, dict):
                    # Handle operators like $set, etc.
                    continue
                if doc[key] != value:
                    return False
        return True


class FindCursor:
    """Mock MongoDB cursor"""
    
    def __init__(self, results: list):
        self.results = results
        self.index = 0
        self._limit = None
        self._sort_field = None
        self._sort_order = 1
    
    def sort(self, field: str, direction: int):
        """Sort results"""
        self._sort_field = field
        self._sort_order = direction
        self.results.sort(
            key=lambda x: x.get(field, ""),
            reverse=(direction == -1)
        )
        return self
    
    def limit(self, count: int):
        """Limit results"""
        self._limit = count
        return self
    
    async def to_list(self, length: Optional[int] = None):
        """Convert to list"""
        if length is not None:
            return self.results[:length]
        if self._limit is not None:
            return self.results[:self._limit]
        return self.results


def init_local_db():
    """Initialize local database collections"""
    return {
        "profiles": LocalCollection("profiles"),
        "users": LocalCollection("users"),
        "messages": LocalCollection("messages"),
        "friends": LocalCollection("friends"),
    }
