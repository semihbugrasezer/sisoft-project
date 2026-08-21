"""Chat history + aktif kriter + pending CV kuyruğu. chat_id ile ayrıştırılır.
sqlite3 blocking olduğu için her genel metot asyncio.to_thread ile çalıştırılır.

Tek `sqlite3.Connection` tüm thread'ler arasında paylaşılıyor (`check_same_thread=False`);
bu, `self._lock`'u performans detayı değil doğruluk gereği yapar — paylaşılan bir
connection'a eşzamanlı çoklu thread'den erişim sqlite3'te tanımsız davranış/`database is
locked` riski taşır. Lock kaldırılmaz; WAL modu okuma/yazma çakışmasını azaltır."""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

# Modele gönderilen sohbet geçmişi bu kadar mesajla sınırlı (~son 20 tur) — context
# window taşmasını ve LLM_TIMEOUT'a yaklaşmayı önler (bkz. README "Bilinen sınırlamalar").
CHAT_HISTORY_LIMIT = 40

SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_history_chat ON chat_history(chat_id, id);
CREATE TABLE IF NOT EXISTS chat_summary (
    chat_id INTEGER PRIMARY KEY,
    summary TEXT NOT NULL,
    last_summarized_id INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS criteria (
    chat_id INTEGER PRIMARY KEY,
    criteria_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pending_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    file_bytes BLOB NOT NULL,
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pending_files_chat ON pending_files(chat_id, id);
"""


class SQLiteRepo:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
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

    async def get_messages(self, chat_id: int) -> list[dict]:
        async with self._lock:
            rows = await asyncio.to_thread(self._get_messages_sync, chat_id)
        return [{"role": role, "content": content} for role, content in rows]

    def _get_messages_sync(self, chat_id: int) -> list[tuple]:
        """Son CHAT_HISTORY_LIMIT mesajı kronolojik sırada döner.

        `ORDER BY id`: aynı `time.time()` tick'ine denk gelen user/assistant çifti
        `ts` ile sıralandığında ters okunabiliyordu (rowid monotonik, ts değil).
        """
        cur = self._conn.execute(
            "SELECT role, content FROM chat_history WHERE chat_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (chat_id, CHAT_HISTORY_LIMIT),
        )
        return list(reversed(cur.fetchall()))

    async def clear_history(self, chat_id: int) -> None:
        async with self._lock:
            await asyncio.to_thread(self._clear_history_sync, chat_id)

    def _clear_history_sync(self, chat_id: int) -> None:
        self._conn.execute("DELETE FROM chat_history WHERE chat_id = ?", (chat_id,))
        self._conn.execute("DELETE FROM chat_summary WHERE chat_id = ?", (chat_id,))
        self._conn.commit()

    async def purge_expired_chat_history(self, max_age_seconds: float) -> int:
        """Eski mesajları ve bu mesajları içerebilecek özetleri açılışta temizler."""
        cutoff = time.time() - max_age_seconds
        async with self._lock:
            deleted = await asyncio.to_thread(self._purge_expired_chat_history_sync, cutoff)
        if deleted:
            logger.info("%d adet süresi geçmiş sohbet mesajı silindi", deleted)
        return deleted

    def _purge_expired_chat_history_sync(self, cutoff: float) -> int:
        with self._conn:
            self._conn.execute(
                "DELETE FROM chat_summary WHERE chat_id IN ("
                "SELECT DISTINCT chat_id FROM chat_history WHERE ts < ?)",
                (cutoff,),
            )
            cursor = self._conn.execute("DELETE FROM chat_history WHERE ts < ?", (cutoff,))
        return cursor.rowcount

    # --- rolling summary (bağlam penceresi dışına taşan geçmiş) ------------

    async def get_summary(self, chat_id: int) -> str | None:
        async with self._lock:
            row = await asyncio.to_thread(
                self._fetchone_sync, "SELECT summary FROM chat_summary WHERE chat_id = ?", (chat_id,)
            )
        return row[0] if row else None

    async def get_unsummarized_overflow(self, chat_id: int, limit: int) -> list[dict]:
        """Bağlam penceresinin (son `limit` mesaj) DIŞINDA kalan ve henüz özetlenmemiş
        mesajları döner. Bunlar özete katlanır, böylece eski bağlam tamamen kaybolmaz."""
        async with self._lock:
            rows = await asyncio.to_thread(self._get_unsummarized_overflow_sync, chat_id, limit)
        return [{"id": row[0], "role": row[1], "content": row[2]} for row in rows]

    def _get_unsummarized_overflow_sync(self, chat_id: int, limit: int) -> list[tuple]:
        cur = self._conn.execute(
            "SELECT id, role, content FROM chat_history "
            "WHERE chat_id = ? "
            "  AND id > COALESCE((SELECT last_summarized_id FROM chat_summary WHERE chat_id = ?), 0) "
            "  AND id NOT IN ("
            "      SELECT id FROM chat_history WHERE chat_id = ? ORDER BY id DESC LIMIT ?"
            "  ) "
            "ORDER BY id",
            (chat_id, chat_id, chat_id, limit),
        )
        return cur.fetchall()

    async def set_summary(self, chat_id: int, summary: str, last_summarized_id: int) -> None:
        async with self._lock:
            await asyncio.to_thread(
                self._set_summary_sync, chat_id, summary, last_summarized_id
            )

    def _set_summary_sync(self, chat_id: int, summary: str, last_summarized_id: int) -> None:
        self._conn.execute(
            "INSERT INTO chat_summary (chat_id, summary, last_summarized_id) VALUES (?, ?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET "
            "  summary = excluded.summary, last_summarized_id = excluded.last_summarized_id",
            (chat_id, summary, last_summarized_id),
        )
        self._conn.commit()

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

    async def try_add_pending_file(
        self, chat_id: int, filename: str, file_bytes: bytes, limit: int
    ) -> bool:
        """count+insert'i tek lock altında atomik yapar — `concurrent_updates(8)` ile
        aynı sohbete eşzamanlı gelen iki dosya, ayrı ayrı count_pending_files() +
        add_pending_file() çağrısı yapılsaydı ikisi de limiti geçmeden önce aynı
        sayıyı okuyup limiti aşabilirdi (TOCTOU race). False dönerse dosya eklenmedi."""
        async with self._lock:
            return await asyncio.to_thread(
                self._try_add_pending_file_sync, chat_id, filename, file_bytes, limit
            )

    def _try_add_pending_file_sync(
        self, chat_id: int, filename: str, file_bytes: bytes, limit: int
    ) -> bool:
        count = self._conn.execute(
            "SELECT COUNT(*) FROM pending_files WHERE chat_id = ?", (chat_id,)
        ).fetchone()[0]
        if count >= limit:
            return False
        self._conn.execute(
            "INSERT INTO pending_files (chat_id, filename, file_bytes, ts) VALUES (?, ?, ?, ?)",
            (chat_id, filename, file_bytes, time.time()),
        )
        self._conn.commit()
        return True

    async def get_pending_files(self, chat_id: int) -> list[tuple[str, bytes]]:
        async with self._lock:
            rows = await asyncio.to_thread(self._get_pending_files_sync, chat_id)
        return rows

    def _get_pending_files_sync(self, chat_id: int) -> list[tuple[str, bytes]]:
        cur = self._conn.execute(
            "SELECT filename, file_bytes FROM pending_files WHERE chat_id = ? ORDER BY ts", (chat_id,)
        )
        return cur.fetchall()

    async def take_pending_files(self, chat_id: int) -> list[tuple[str, bytes]]:
        """Bekleyen dosyaları tek kritik bölümde alıp kuyruktan çıkarır.

        Aynı sohbetten iki `/analyze` çağrısı aynı snapshot'ı işleyemez; analiz
        başladıktan sonra yüklenen yeni dosyalar da sonraki kuyrukta kalır.
        """
        async with self._lock:
            return await asyncio.to_thread(self._take_pending_files_sync, chat_id)

    def _take_pending_files_sync(self, chat_id: int) -> list[tuple[str, bytes]]:
        with self._conn:
            rows = self._get_pending_files_sync(chat_id)
            self._conn.execute("DELETE FROM pending_files WHERE chat_id = ?", (chat_id,))
        return rows

    async def clear_pending_files(self, chat_id: int) -> None:
        async with self._lock:
            await asyncio.to_thread(self._exec_sync, "DELETE FROM pending_files WHERE chat_id = ?", (chat_id,))

    async def purge_expired_pending_files(self, max_age_seconds: float) -> int:
        """Verilen yaştan eski bekleyen CV'leri siler ve silinen sayısını döner.

        Neden gerekli: `/analyze` akışı `try/finally` ile temizlik yapar ama kullanıcı
        `/batch` ile dosya yükleyip hiç `/analyze` veya `/cancel` yazmazsa dosyalar
        süresiz kalırdı; süreç sert şekilde sonlanırsa `finally` de çalışmaz. CV'ler
        kişisel veridir — süresiz saklanmamalı (bkz. SECURITY.md)."""
        cutoff = time.time() - max_age_seconds
        async with self._lock:
            deleted = await asyncio.to_thread(self._purge_expired_pending_files_sync, cutoff)
        if deleted:
            logger.info("%d adet süresi geçmiş bekleyen CV silindi", deleted)
        return deleted

    def _purge_expired_pending_files_sync(self, cutoff: float) -> int:
        cursor = self._conn.execute("DELETE FROM pending_files WHERE ts < ?", (cutoff,))
        self._conn.commit()
        return cursor.rowcount

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
