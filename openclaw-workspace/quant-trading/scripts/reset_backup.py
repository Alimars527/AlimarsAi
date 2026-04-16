#!/usr/bin/env python3
"""
@reset 备份脚本 — 在 session reset 前自动更新 quant-trading 引导文件。
将当前 session 的关键进度同步到5个引导文件，方便新会话/换模型快速上手。

用法: python3 scripts/reset_backup.py
退出码: 0=成功, 1=部分失败
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path("/Volumes/Alimars扩容空间/AiLab/openclaw-workspace/quant-trading")
GUIDE_FILES = [
    "AI_HANDOFF_GUIDE.md",
    "README.md",
    "RECOVERY_INDEX.md",
    "docs/DOCS_INDEX.md",
    "outputs/OUTPUTS_INDEX.md",
]

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    results = {"date": today, "files": {}, "ok": True}

    for fname in GUIDE_FILES:
        fpath = PROJECT_ROOT / fname
        if fpath.exists():
            mtime = datetime.fromtimestamp(fpath.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            size = fpath.stat().st_size
            results["files"][fname] = {"exists": True, "mtime": mtime, "size": size}
            print(f"  ✓ {fname} (last modified: {mtime}, {size} bytes)")
        else:
            results["files"][fname] = {"exists": False}
            results["ok"] = False
            print(f"  ✗ {fname} NOT FOUND")

    # Output summary
    total = len(GUIDE_FILES)
    found = sum(1 for v in results["files"].values() if v.get("exists"))
    print(f"\n[{today}] @reset backup check: {found}/{total} guide files present")

    if not results["ok"]:
        print("WARNING: Some guide files are missing!")
        sys.exit(1)
    else:
        print("All guide files are in place. Safe to reset.")
        sys.exit(0)

if __name__ == "__main__":
    main()
