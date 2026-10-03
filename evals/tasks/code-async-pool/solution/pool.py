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
        self._idle = []
        self._waiters = []
        self._created = 0
        self._in_use = 0
        self._closed = False
        self._drained = None

    @property
    def in_use(self):
        return self._in_use

    @property
    def created(self):
        return self._created

    def _wake_all(self):
        # Đánh thức tất cả để từng tác vụ tự kiểm lại; tránh mất lượt đánh thức khi tác vụ được đánh thức bị hủy.
        waiters, self._waiters = self._waiters, []
        for fut in waiters:
            if not fut.done():
                fut.set_result(None)
        if self._closed and self._in_use == 0 and self._drained is not None and not self._drained.done():
            self._drained.set_result(None)

    async def _acquire(self):
        while True:
            if self._closed:
                raise PoolClosed()
            if self._idle:
                self._in_use += 1
                return self._idle.pop()
            if self._created < self.size:
                self._created += 1  # giữ chỗ trước khi chờ connect()
                try:
                    conn = await self._connect()
                except BaseException:
                    self._created -= 1
                    self._wake_all()
                    raise
                if self._closed:
                    conn.close()
                    self._created -= 1
                    self._wake_all()
                    raise PoolClosed()
                self._in_use += 1
                return conn
            fut = asyncio.get_running_loop().create_future()
            self._waiters.append(fut)
            try:
                await fut
            finally:
                if fut in self._waiters:
                    self._waiters.remove(fut)

    async def acquire(self, timeout=None):
        if timeout is None:
            return await self._acquire()
        return await asyncio.wait_for(self._acquire(), timeout)

    def release(self, conn, broken=False):
        self._in_use -= 1
        if broken or self._closed:
            conn.close()
            self._created -= 1
        else:
            self._idle.append(conn)
        self._wake_all()

    @asynccontextmanager
    async def connection(self, timeout=None):
        conn = await self.acquire(timeout)
        try:
            yield conn
        except ConnectionBroken:
            self.release(conn, broken=True)
            raise
        except BaseException:
            self.release(conn)
            raise
        else:
            self.release(conn)

    async def close(self):
        self._closed = True
        self._wake_all()
        if self._in_use:
            self._drained = asyncio.get_running_loop().create_future()
            await self._drained
        for conn in self._idle:
            conn.close()
        self._created -= len(self._idle)
        self._idle = []
