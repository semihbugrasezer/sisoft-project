"""Chat history + aktif kriter + pending CV kuyruğu. chat_id ile ayrıştırılır (RULES.md §9).
sqlite3 blocking olduğu için her genel metot asyncio.to_thread ile çalıştırılır."""
from __future__ import annotations

import asyncio
import json
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_history (
    chat_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS criteria (
    chat_id INTEGER PRIMARY KEY,
    criteria_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pending_files (
    chat_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    file_bytes BLOB NOT NULL,
    ts REAL NOT NULL
);
"""


class SQLiteRepo:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        self._conn.close()

    # --- chat history ----------------------------------------------------

    async def add_message(self, chat_id: int, role: str, content: str) -> None:
        async with self._lock:
            await asyncio.to_thread(self._add_message_sync, chat_id, role, content)

    def _add_message_sync(self, chat_id: int, role: str, content: str) -> None:
        self._conn.execute(
            "INSERT INTO chat_history (chat_id, role, content, ts) VALUES (?, ?, ?, ?)",
            (chat_id, role, content, time.time()),
        )
        self._conn.commit()

    async def get_recent_messages(self, chat_id: int, limit: int) -> list[dict]:
        async with self._lock:
            rows = await asyncio.to_thread(self._get_recent_messages_sync, chat_id, limit)
        return [{"role": role, "content": content} for role, content in rows]

    def _get_recent_messages_sync(self, chat_id: int, limit: int) -> list[tuple]:
        cur = self._conn.execute(
            "SELECT role, content FROM chat_history WHERE chat_id = ? ORDER BY ts DESC LIMIT ?",
            (chat_id, limit),
        )
        return list(reversed(cur.fetchall()))

    async def clear_history(self, chat_id: int) -> None:
        async with self._lock:
            await asyncio.to_thread(self._exec_sync, "DELETE FROM chat_history WHERE chat_id = ?", (chat_id,))

    # --- kriterler ---------------------------------------------------------

    async def set_criteria(self, chat_id: int, criteria: list[dict]) -> None:
        async with self._lock:
            await asyncio.to_thread(self._set_criteria_sync, chat_id, criteria)

    def _set_criteria_sync(self, chat_id: int, criteria: list[dict]) -> None:
        self._conn.execute(
            "INSERT INTO criteria (chat_id, criteria_json) VALUES (?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET criteria_json = excluded.criteria_json",
            (chat_id, json.dumps(criteria)),
        )
        self._conn.commit()

    async def get_criteria(self, chat_id: int) -> list[dict] | None:
        async with self._lock:
            row = await asyncio.to_thread(self._get_criteria_sync, chat_id)
        return json.loads(row[0]) if row else None

    def _get_criteria_sync(self, chat_id: int) -> tuple | None:
        cur = self._conn.execute("SELECT criteria_json FROM criteria WHERE chat_id = ?", (chat_id,))
        return cur.fetchone()

    async def clear_criteria(self, chat_id: int) -> None:
        async with self._lock:
            await asyncio.to_thread(self._exec_sync, "DELETE FROM criteria WHERE chat_id = ?", (chat_id,))

    # --- pending CV kuyruğu ------------------------------------------------

    async def add_pending_file(self, chat_id: int, filename: str, file_bytes: bytes) -> None:
        async with self._lock:
            await asyncio.to_thread(self._add_pending_file_sync, chat_id, filename, file_bytes)

    def _add_pending_file_sync(self, chat_id: int, filename: str, file_bytes: bytes) -> None:
        self._conn.execute(
            "INSERT INTO pending_files (chat_id, filename, file_bytes, ts) VALUES (?, ?, ?, ?)",
            (chat_id, filename, file_bytes, time.time()),
        )
        self._conn.commit()

    async def get_pending_files(self, chat_id: int) -> list[tuple[str, bytes]]:
        async with self._lock:
            rows = await asyncio.to_thread(self._get_pending_files_sync, chat_id)
        return rows

    def _get_pending_files_sync(self, chat_id: int) -> list[tuple[str, bytes]]:
        cur = self._conn.execute(
            "SELECT filename, file_bytes FROM pending_files WHERE chat_id = ? ORDER BY ts", (chat_id,)
        )
        return cur.fetchall()

    async def clear_pending_files(self, chat_id: int) -> None:
        async with self._lock:
            await asyncio.to_thread(self._exec_sync, "DELETE FROM pending_files WHERE chat_id = ?", (chat_id,))

    async def count_pending_files(self, chat_id: int) -> int:
        async with self._lock:
            row = await asyncio.to_thread(
                self._fetchone_sync, "SELECT COUNT(*) FROM pending_files WHERE chat_id = ?", (chat_id,)
            )
        return row[0]

    # --- yardımcılar ---------------------------------------------------------

    def _exec_sync(self, sql: str, params: tuple) -> None:
        self._conn.execute(sql, params)
        self._conn.commit()

    def _fetchone_sync(self, sql: str, params: tuple) -> tuple:
        return self._conn.execute(sql, params).fetchone()
