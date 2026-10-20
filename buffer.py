"""
Store-and-forward buffer in SQLite.

If the Zabbix server (or proxy) is unreachable, values are stored here with
their original timestamp and sent later. Trapper items accept an explicit
clock, so the history in Zabbix ends up correct once the link is back.

Only TRANSPORT failures go into the buffer. Values the server received and
rejected ('failed' in the sender response) are configuration problems and
retrying them forever would just grow the file.
"""

import json
import sqlite3
import threading


class ValueBuffer:
    def __init__(self, path: str, max_rows: int = 500_000):
        self.path = path
        self.max_rows = int(max_rows)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS pending ("
                " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " item TEXT NOT NULL)"
            )

    def _conn(self):
        return sqlite3.connect(self.path, timeout=30)

    def count(self) -> int:
        with self._lock, self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM pending").fetchone()[0]

    def push(self, values: list) -> int:
        """Store values. Returns how many old rows were dropped to respect max_rows."""
        if not values:
            return 0
        with self._lock, self._conn() as c:
            c.executemany(
                "INSERT INTO pending(item) VALUES (?)",
                [(json.dumps(v, separators=(",", ":")),) for v in values],
            )
            n = c.execute("SELECT COUNT(*) FROM pending").fetchone()[0]
            overflow = n - self.max_rows
            if overflow > 0:
                c.execute(
                    "DELETE FROM pending WHERE id IN "
                    "(SELECT id FROM pending ORDER BY id LIMIT ?)",
                    (overflow,),
                )
                return overflow
            return 0

    def peek(self, limit: int) -> list:
        """Oldest first. Returns [(id, value_dict), ...]."""
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT id, item FROM pending ORDER BY id LIMIT ?", (limit,)
            ).fetchall()
        return [(rid, json.loads(item)) for rid, item in rows]

    def delete_upto(self, last_id: int):
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM pending WHERE id <= ?", (last_id,))
