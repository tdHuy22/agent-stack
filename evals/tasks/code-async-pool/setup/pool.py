"""Pool kết nối bất đồng bộ dùng chung cho nhiều tác vụ."""
import asyncio
from contextlib import asynccontextmanager


class PoolClosed(Exception):
    pass


class ConnectionBroken(Exception):
    """Ném ra trong khối `async with pool.connection()` khi kết nối hỏng."""


class Pool:
    def __init__(self, size, connect):
        self.size = size
        self._connect = connect  # async () -> kết nối có .close()
        self._idle = asyncio.Queue()
        self._created = 0
        self._in_use = 0
        self._closed = False

    @property
    def in_use(self):
        return self._in_use

    @property
    def created(self):
        return self._created

    async def acquire(self, timeout=None):
        if self._closed:
            raise PoolClosed()
        if self._idle.empty() and self._created < self.size:
            self._created += 1
            conn = await self._connect()
        else:
            conn = await asyncio.wait_for(self._idle.get(), timeout)
        self._in_use += 1
        return conn

    def release(self, conn):
        self._in_use -= 1
        self._idle.put_nowait(conn)

    @asynccontextmanager
    async def connection(self, timeout=None):
        conn = await self.acquire(timeout)
        yield conn
        self.release(conn)

    async def close(self):
        self._closed = True
        while not self._idle.empty():
            self._idle.get_nowait().close()
