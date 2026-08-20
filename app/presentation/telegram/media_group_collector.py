"""Telegram albüm (media_group_id) dosyalarını toplar. Aynı gruptaki dosyalar ayrı
update olarak gelir ve grubun büyüklüğü önceden bilinmez — bu yüzden son dosyadan
sonra kısa bir debounce süresi beklenir; süre dolduğunda veya limit dolduğunda
otomatik tetiklenir (docs/CONCURRENCY.md)."""
from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field

# İşlenmiş grup kimlikleri sınırlı sayıda hatırlanır: amaç geç gelen bir update'i
# reddedebilmek, kalıcı bir kayıt tutmak değil. Sabit kapasite, uzun süre çalışan
# bir bot'ta belleğin sınırsız büyümesini önler.
CLOSED_GROUP_MEMORY = 128


@dataclass
class MediaGroupBuffer:
    files: list[tuple[str, bytes]] = field(default_factory=list)
    timer_task: asyncio.Task | None = None


class MediaGroupManager:
    def __init__(self):
        self._buffers: dict[tuple[int, str], MediaGroupBuffer] = {}
        # `pop` edilmiş gruplar. Yalnızca sözlükten silmek yetmez: Telegram'ın geç
        # gelen bir update'i (ör. limit dolduğu için hemen işlenen 5 dosyalık
        # albümün 6. dosyası) `setdefault` ile YENİ bir arabellek yaratır ve ayrı
        # bir batch gibi işlenirdi. Kapalı grup kaydı bunu engeller.
        self._closed: deque[tuple[int, str]] = deque(maxlen=CLOSED_GROUP_MEMORY)
        self._lock = asyncio.Lock()

    async def add_file(
        self, chat_id: int, group_id: str, filename: str, data: bytes, max_files: int
    ) -> tuple[MediaGroupBuffer, bool]:
        """Dosyayı arabelleğe ekler. (buffer, eklendi_mi) döner — limit dolmuşsa veya
        grup zaten işlenmişse False."""
        async with self._lock:
            key = (chat_id, group_id)
            if key in self._closed:
                return MediaGroupBuffer(), False
            buf = self._buffers.setdefault(key, MediaGroupBuffer())
            if len(buf.files) >= max_files:
                return buf, False
            buf.files.append((filename, data))
            return buf, True

    async def pop(self, chat_id: int, group_id: str) -> MediaGroupBuffer | None:
        """Arabelleği alır ve grubu kapatır — bu gruba sonradan dosya eklenemez."""
        async with self._lock:
            key = (chat_id, group_id)
            buf = self._buffers.pop(key, None)
            if buf is not None and key not in self._closed:
                self._closed.append(key)
            return buf
