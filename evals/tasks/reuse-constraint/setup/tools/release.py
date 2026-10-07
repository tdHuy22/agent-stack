#!/usr/bin/env python3
"""Đóng gói một bản phát hành theo release.toml."""
import argparse
import sys
from pathlib import Path


def load_config(path: Path) -> dict:
    raise NotImplementedError("chưa đọc được release.toml")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Đóng gói bản phát hành.")
    ap.add_argument("--config", type=Path, default=Path("release.toml"))
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    print(cfg["package"]["name"], cfg["package"]["version"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
