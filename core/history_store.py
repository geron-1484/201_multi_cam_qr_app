import sqlite3
import os
import csv
from datetime import datetime

DB_PATH = os.path.join("data", "history.db")

class HistoryStore:
    def __init__(self, db_path: str = DB_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init_schema()

    def _init_schema(self):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS qr_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    camera_type TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_ts ON qr_history(ts)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_cam ON qr_history(camera_id)")
            conn.commit()

    def add_record(self, ts: str, camera_id: str, camera_type: str, payload: str):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO qr_history (ts, camera_id, camera_type, payload) VALUES (?, ?, ?, ?)",
                (ts, str(camera_id), camera_type, payload),
            )
            conn.commit()

    def query(self, ts_from: str = None, ts_to: str = None, camera_id: str = None, keyword: str = None, limit: int = 500):
        query = "SELECT ts, camera_id, camera_type, payload FROM qr_history WHERE 1=1"
        params = []
        if ts_from:
            query += " AND ts >= ?"
            params.append(ts_from)
        if ts_to:
            query += " AND ts <= ?"
            params.append(ts_to)
        if camera_id:
            query += " AND camera_id = ?"
            params.append(str(camera_id))
        if keyword:
            query += " AND payload LIKE ?"
            params.append(f"%{keyword}%")
        query += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(query, params)
            return c.fetchall()

    def export_csv(self, path: str, rows):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["ts", "camera_id", "camera_type", "payload"])
            writer.writerows(rows)

def now_iso():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
