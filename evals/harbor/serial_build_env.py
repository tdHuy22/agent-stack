"""Môi trường Docker của Harbor dựng image lần lượt: cả job chỉ một lệnh `docker compose build` chạy một lúc.

Ca 07/11/2026 trên tuf: containerd và dockerd sập 4 lần trong 35 phút khi 3 lượt dựng image song song, và 19/21 lỗi của
SWE-rebench rơi đúng lúc dựng. Không giữ sẵn image được (25 image nền SWE-rebench nặng khoảng 41 GB nén, ổ chỉ còn 15 GB),
nên dựng trong job nhưng không cho hai lần dựng chồng nhau. Lượt khác vẫn chạy agent và chấm điểm song song như cũ.

Harbor nạp lớp này qua `environment.import_path` của cấu hình job (harbor_bench.py SERIAL_ENV). Giờ chờ tới lượt dựng tính
vào hạn dựng môi trường của Harbor, nên cấu hình nới hệ số hạn dựng. Bốn cấu hình dùng chung một môi trường nên phép so
vẫn công bằng; thời gian agent làm bài không đổi.

File này chạy trong venv của Harbor trên TUF (import harbor), như agent_stack_agents.py; test thay mô-đun harbor bằng bản giả.
API Harbor dùng (đã đọc ở 0.25.0): DockerEnvironment._run_docker_compose_command(command, check, timeout_sec, ...), gọi với
["build"] không kèm hạn trong start(); task_env_config.build_timeout_sec (mặc định 600).
"""
from __future__ import annotations

import asyncio

from harbor.environments.docker.docker import DockerEnvironment

BUILD_TIMEOUT_FACTOR = 2.0     # hạn của chính lệnh dựng = hệ số × build_timeout_sec của việc; hạn cả bước dựng là ×4


class SerialBuildDockerEnvironment(DockerEnvironment):
    _serial_build_lock: asyncio.Lock | None = None    # dùng chung mọi lượt trong job; tạo lười trong vòng lặp của job

    @classmethod
    def _build_lock(cls) -> asyncio.Lock:
        if SerialBuildDockerEnvironment._serial_build_lock is None:
            SerialBuildDockerEnvironment._serial_build_lock = asyncio.Lock()
        return SerialBuildDockerEnvironment._serial_build_lock

    async def _run_docker_compose_command(self, command, *args, **kwargs):
        if not command or command[0] != "build":
            return await super()._run_docker_compose_command(command, *args, **kwargs)
        # Hạn riêng cho chính lệnh dựng, gấp đôi hạn dựng của việc (bằng hạn cũ trước khi dựng lần lượt). Dựng treo
        # (containerd chết giữa chừng) thì Harbor tự dừng tiến trình con và báo RuntimeError (được thử lại), nhả khóa sớm.
        # Không có hạn này thì khóa bị giữ tới khi lượt hết hạn ×4, và asyncio hủy lượt mà không dừng `docker compose build`
        # (Harbor 0.25.0 chỉ dừng tiến trình khi chính lệnh hết hạn), nên lần dựng sau chồng lên lần dựng cũ còn chạy ngầm.
        if len(args) < 2 and kwargs.get("timeout_sec") is None:
            base = getattr(getattr(self, "task_env_config", None), "build_timeout_sec", None) or 600
            kwargs["timeout_sec"] = int(BUILD_TIMEOUT_FACTOR * base)
        async with self._build_lock():
            return await super()._run_docker_compose_command(command, *args, **kwargs)
