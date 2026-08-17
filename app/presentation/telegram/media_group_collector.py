"""Telegram albüm (media_group_id) dosyalarını toplar. Aynı gruptaki dosyalar ayrı
update olarak gelir ve grubun büyüklüğü önceden bilinmez — bu yüzden son dosyadan
sonra kısa bir debounce süresi beklenir; süre dolduğunda veya limit dolduğunda
otomatik tetiklenir (README.md §5)."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class MediaGroupBuffer:
    files: list[tuple[str, bytes]] = field(default_factory=list)
    timer_task: asyncio.Task | None = None


class MediaGroupManager:
    def __init__(self):
        self._buffers: dict[tuple[int, str], MediaGroupBuffer] = {}
        self._lock = asyncio.Lock()

    async def add_file(
        self, chat_id: int, group_id: str, filename: str, data: bytes, max_files: int
    ) -> tuple[MediaGroupBuffer, bool]:
        """Dosyayı arabelleğe ekler. (buffer, eklendi_mi) döner — limit dolmuşsa False."""
        async with self._lock:
            key = (chat_id, group_id)
            buf = self._buffers.setdefault(key, MediaGroupBuffer())
            if len(buf.files) >= max_files:
                return buf, False
            buf.files.append((filename, data))
            return buf, True

    async def pop(self, chat_id: int, group_id: str) -> MediaGroupBuffer | None:
        async with self._lock:
            return self._buffers.pop((chat_id, group_id), None)
