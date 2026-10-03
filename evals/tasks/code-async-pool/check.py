import json, subprocess, sys, textwrap
from pathlib import Path

# Mỗi kịch bản chạy trong tiến trình con có hạn giờ, vì lời giải sai hay làm tác vụ chờ mãi.
PROBE = textwrap.dedent('''
    import asyncio, json, random, sys
    sys.path.insert(0, ".")
    from pool import ConnectionBroken, Pool, PoolClosed

    class Conn:
        n = 0
        def __init__(self):
            Conn.n += 1
            self.id, self.closed = Conn.n, False
        def close(self):
            self.closed = True

    def factory(delay=0.0, fail_first=0, slow_first=0):
        state = {"calls": 0, "made": []}
        async def connect():
            state["calls"] += 1
            if state["calls"] <= slow_first:
                await asyncio.sleep(1.0)
            elif delay:
                await asyncio.sleep(delay)
            if state["calls"] <= fail_first:
                raise OSError("không kết nối được")
            c = Conn()
            state["made"].append(c)
            return c
        return connect, state

    async def s_exception_in_body():
        connect, st = factory()
        pool = Pool(2, connect)
        try:
            async with pool.connection() as c:
                raise ValueError("lỗi trong khối")
        except ValueError:
            pass
        async with pool.connection() as c2:
            same = c2 is c
        assert pool.in_use == 0, f"in_use={pool.in_use}"
        assert same and pool.created == 1, "kết nối không được trả về pool sau ngoại lệ"

    async def s_broken():
        connect, st = factory()
        pool = Pool(1, connect)
        try:
            async with pool.connection() as c:
                raise ConnectionBroken()
        except ConnectionBroken:
            pass
        else:
            raise AssertionError("ConnectionBroken bị nuốt")
        assert c.closed, "kết nối hỏng không được đóng"
        assert pool.created == 0 and pool.in_use == 0, f"created={pool.created} in_use={pool.in_use}"
        async with pool.connection(timeout=1) as c2:
            assert c2 is not c, "kết nối hỏng bị dùng lại"

    async def s_connect_fails():
        connect, st = factory(fail_first=1)
        pool = Pool(1, connect)
        try:
            await pool.acquire()
            raise AssertionError("lỗi connect bị nuốt")
        except OSError:
            pass
        assert pool.created == 0, f"connect lỗi vẫn tính created={pool.created}"
        c = await pool.acquire(timeout=1)
        pool.release(c)

    async def s_cancel_during_connect():
        connect, st = factory(slow_first=1)
        pool = Pool(1, connect)
        t = asyncio.ensure_future(pool.acquire())
        await asyncio.sleep(0.05)
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass
        c = await pool.acquire(timeout=0.5)
        assert pool.created == 1 and pool.in_use == 1, f"created={pool.created} in_use={pool.in_use}"
        pool.release(c)

    async def s_waiter_woken_by_broken():
        connect, st = factory()
        pool = Pool(1, connect)
        async def holder():
            async with pool.connection():
                await asyncio.sleep(0.1)
                raise ConnectionBroken()
        h = asyncio.ensure_future(holder())
        await asyncio.sleep(0.02)
        c = await pool.acquire(timeout=1)
        assert not c.closed
        pool.release(c)
        try:
            await h
        except ConnectionBroken:
            pass

    async def s_timeout_and_cancel_waiter():
        connect, st = factory()
        pool = Pool(1, connect)
        c = await pool.acquire()
        try:
            await pool.acquire(timeout=0.05)
            raise AssertionError("thiếu TimeoutError")
        except asyncio.TimeoutError:
            pass
        w = asyncio.ensure_future(pool.acquire())
        await asyncio.sleep(0.02)
        w.cancel()
        try:
            await w
        except asyncio.CancelledError:
            pass
        pool.release(c)
        c2 = await pool.acquire(timeout=0.5)
        assert c2 is c and pool.in_use == 1 and pool.created == 1, f"in_use={pool.in_use} created={pool.created}"
        pool.release(c2)

    async def s_close():
        connect, st = factory()
        pool = Pool(2, connect)
        loop = asyncio.get_running_loop()
        async def hold():
            async with pool.connection():
                await asyncio.sleep(0.2)
        holders = [asyncio.ensure_future(hold()) for _ in range(2)]
        await asyncio.sleep(0.02)
        waiter = asyncio.ensure_future(pool.acquire())
        await asyncio.sleep(0.02)
        start = loop.time()
        closer = asyncio.ensure_future(pool.close())
        await asyncio.sleep(0.03)
        assert waiter.done(), "tác vụ đang chờ không được báo PoolClosed ngay khi close()"
        assert isinstance(waiter.exception(), PoolClosed), f"tác vụ đang chờ nhận {waiter.exception()!r}"
        assert not any(c.closed for c in st["made"]), "close() đóng cả kết nối đang được dùng"
        await asyncio.wait_for(closer, 2)
        assert loop.time() - start >= 0.12, "close() không chờ kết nối đang dùng"
        assert all(c.closed for c in st["made"]), "close() không đóng hết kết nối"
        await asyncio.gather(*holders)
        try:
            await pool.acquire()
            raise AssertionError("acquire sau close() phải ném PoolClosed")
        except PoolClosed:
            pass

    async def s_stress():
        connect, st = factory(delay=0.002)
        pool = Pool(4, connect)
        rnd = random.Random(7)
        async def job(i):
            r = rnd.random()
            async with pool.connection(timeout=rnd.choice([None, 0.01, 0.2])):
                await asyncio.sleep(rnd.random() * 0.005)
                if r < 0.1:
                    raise ValueError()
                if r < 0.15:
                    raise ConnectionBroken()
        tasks = [asyncio.ensure_future(job(i)) for i in range(300)]
        for _ in range(30):
            await asyncio.sleep(rnd.random() * 0.01)
            rnd.choice(tasks).cancel()
        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 15)
        assert pool.in_use == 0, f"còn in_use={pool.in_use}"
        assert 0 <= pool.created <= 4, f"created={pool.created}"
        live = [c for c in st["made"] if not c.closed]
        assert len(live) == pool.created, f"{len(live)} kết nối còn mở nhưng created={pool.created} (rò kết nối)"
        async with pool.connection(timeout=1):
            pass
        await asyncio.wait_for(pool.close(), 2)
        assert all(c.closed for c in st["made"]), "còn kết nối chưa đóng sau close()"

    SCENARIOS = [s_exception_in_body, s_broken, s_connect_fails, s_cancel_during_connect, s_waiter_woken_by_broken,
                 s_timeout_and_cancel_waiter, s_close, s_stress]
    name = sys.argv[1]
    fn = next(s for s in SCENARIOS if s.__name__ == name)
    try:
        asyncio.run(asyncio.wait_for(fn(), 20))
        print("OK")
    except asyncio.TimeoutError:
        print("treo hoặc chờ quá lâu"); sys.exit(1)
    except AssertionError as exc:
        print(str(exc)); sys.exit(1)
    except Exception as exc:
        print(repr(exc)); sys.exit(1)
''')
NAMES = ["s_exception_in_body", "s_broken", "s_connect_fails", "s_cancel_during_connect", "s_waiter_woken_by_broken",
         "s_timeout_and_cancel_waiter", "s_close", "s_stress"]


def check(workdir, answer):
    problems = []
    for name in NAMES:
        try:
            out = subprocess.run([sys.executable, "-c", PROBE, name], cwd=str(workdir), capture_output=True, text=True,
                                 timeout=40)
            if out.returncode != 0:
                problems.append(f"{name}: " + (out.stdout.strip() or out.stderr.strip()[-160:]))
        except subprocess.TimeoutExpired:
            problems.append(f"{name}: treo")
    return not problems, f"sai {len(problems)}/{len(NAMES)}: " + "; ".join(problems[:4]) if problems else "đạt"
