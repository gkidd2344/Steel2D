from __future__ import annotations
import asyncio
import struct
import json
import threading
import queue
import time
from typing import Optional

from network.protocol import encode_msg


class GameClient:
    def __init__(self, host: str, port: int, ui_queue: queue.Queue,
                 player_uuid: str, alias: str, avatar_b64: Optional[str]):
        self.host = host
        self.port = port
        self.ui_queue = ui_queue
        self.player_uuid = player_uuid
        self.alias = alias
        self.avatar_b64 = avatar_b64

        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._connected = threading.Event()
        self._stopped = False
        self._latency_ms: float = 0.0

    @property
    def latency_ms(self) -> float:
        return self._latency_ms

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def wait_connected(self, timeout: float = 10.0) -> bool:
        return self._connected.wait(timeout)

    def stop(self) -> None:
        self._stopped = True
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._do_stop)

    def _do_stop(self) -> None:
        if self._writer:
            try:
                self._writer.close()
            except Exception:
                pass

    def send(self, msg: dict) -> None:
        if self._loop and not self._loop.is_closed() and self._writer:
            asyncio.run_coroutine_threadsafe(self._async_send(msg), self._loop)

    async def _async_send(self, msg: dict) -> None:
        if self._writer:
            try:
                data = encode_msg(msg)
                self._writer.write(data)
                await self._writer.drain()
            except Exception:
                pass

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._connect())
        except Exception as e:
            self.ui_queue.put(("CONNECTION_FAILED", {"reason": str(e)}))
        finally:
            self._loop.close()

    async def _connect(self) -> None:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=10.0,
            )
        except Exception as e:
            self.ui_queue.put(("CONNECTION_FAILED", {"reason": str(e)}))
            return

        self._writer = writer
        await self._async_send({
            "type": "HELLO",
            "uuid": self.player_uuid,
            "alias": self.alias,
            "avatar_b64": self.avatar_b64,
        })

        while not self._stopped:
            try:
                header = await asyncio.wait_for(reader.readexactly(4), timeout=20.0)
                length = struct.unpack("<I", header)[0]
                if length > 10_000_000:
                    break
                body = await reader.readexactly(length)
                msg = json.loads(body.decode("utf-8"))
            except (asyncio.TimeoutError, asyncio.IncompleteReadError,
                    ConnectionResetError, OSError, json.JSONDecodeError):
                break

            t = msg.get("type", "")

            if t == "WELCOME":
                self._connected.set()
                self.ui_queue.put(("WELCOME", msg))
            elif t == "REJECT":
                self.ui_queue.put(("REJECT", msg))
                break
            elif t == "PONG":
                ts = msg.get("ts", time.time())
                self._latency_ms = (time.time() - ts) * 1000
                self.ui_queue.put(("PONG", msg))
            else:
                self.ui_queue.put((t, msg))

        self.ui_queue.put(("DISCONNECTED", {}))

    def start_ping_loop(self) -> None:
        if self._loop and not self._loop.is_closed():
            asyncio.run_coroutine_threadsafe(self._ping_loop(), self._loop)

    async def _ping_loop(self) -> None:
        while not self._stopped:
            await asyncio.sleep(5)
            await self._async_send({"type": "PING", "ts": time.time()})
