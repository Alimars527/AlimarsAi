#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "outputs" / "task_runs"


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def safe_slug(text: str) -> str:
    keep = []
    for ch in text.strip():
        if ch.isalnum() or ch in {"-", "_"}:
            keep.append(ch)
        elif ch in {" ", "/", ":", "."}:
            keep.append("_")
    out = "".join(keep).strip("_")
    return out or "task"


def scan_json_mtimes(outputs_root: Path) -> Dict[str, float]:
    mtimes: Dict[str, float] = {}
    if not outputs_root.exists():
        return mtimes
    for path in outputs_root.rglob("*.json"):
        try:
            mtimes[str(path)] = path.stat().st_mtime
        except OSError:
            continue
    return mtimes


def find_updated_jsons(before: Dict[str, float], outputs_root: Path) -> List[Path]:
    changed: List[Tuple[float, Path]] = []
    after = scan_json_mtimes(outputs_root)
    for raw_path, mtime in after.items():
        old = before.get(raw_path)
        if old is None or mtime > old:
            changed.append((mtime, Path(raw_path)))
    changed.sort(key=lambda item: item[0], reverse=True)
    return [path for _, path in changed]


def pick_summary_files(paths: List[Path]) -> List[Path]:
    summaries = [p for p in paths if p.name.endswith("summary.json")]
    if summaries:
        return summaries
    return [p for p in paths if p.name.endswith("progress.json")][:3]


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def build_summary_lines(summary_paths: List[Path]) -> List[str]:
    lines: List[str] = []
    for path in summary_paths[:3]:
        payload = read_json(path)
        if not isinstance(payload, dict):
            lines.append(f"- {path.name}")
            continue
        total_return = payload.get("total_return_pct")
        trade_count = payload.get("trade_count")
        win_rate = payload.get("win_rate_pct")
        final_equity = payload.get("final_equity")
        bits = [path.name]
        if total_return is not None:
            bits.append(f"收益={total_return}%")
        if trade_count is not None:
            bits.append(f"交易数={trade_count}")
        if win_rate is not None:
            bits.append(f"胜率={win_rate}%")
        if final_equity is not None:
            bits.append(f"期末权益={final_equity}")
        lines.append("- " + " | ".join(str(x) for x in bits))
    return lines


def run_and_tee(command: List[str], log_path: Path, cwd: Path) -> int:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(cwd) if not existing else f"{cwd}{os.pathsep}{existing}"
    with log_path.open("w", encoding="utf-8") as log_fh:
        proc = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            log_fh.write(line)
            log_fh.flush()
        return proc.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description="运行量化任务并在结束时输出可读摘要，便于 Hermes 后台完成后主动通知。")
    parser.add_argument("--label", help="任务标签，默认取命令名")
    parser.add_argument("--outputs-root", default=str(ROOT / "outputs"), help="输出目录根路径，默认项目 outputs/")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="实际要执行的命令，示例：-- python3 scripts/xxx.py")
    args = parser.parse_args()

    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("用法错误：请在 -- 后面提供要执行的命令。", file=sys.stderr)
        return 2

    outputs_root = Path(args.outputs_root).resolve()
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    label = args.label or Path(command[0]).stem
    slug = safe_slug(label)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = DEFAULT_OUTPUT_DIR / f"{ts}_{slug}"
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "run.log"
    meta_path = run_dir / "run_meta.json"

    before = scan_json_mtimes(outputs_root)
    started_at = now_text()

    meta = {
        "label": label,
        "command": command,
        "started_at": started_at,
        "cwd": str(ROOT),
        "log_path": str(log_path),
        "status": "running",
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[TASK] {label}")
    print(f"[START] {started_at}")
    print(f"[CMD] {' '.join(command)}")
    print(f"[LOG] {log_path}")

    return_code = run_and_tee(command, log_path=log_path, cwd=ROOT)

    ended_at = now_text()
    updated_jsons = find_updated_jsons(before, outputs_root)
    summary_paths = pick_summary_files(updated_jsons)

    meta.update(
        {
            "ended_at": ended_at,
            "return_code": return_code,
            "status": "completed" if return_code == 0 else "failed",
            "updated_jsons": [str(p) for p in updated_jsons[:20]],
            "summary_paths": [str(p) for p in summary_paths],
        }
    )
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n===== TASK RESULT =====")
    print(f"任务：{label}")
    print(f"状态：{'完成' if return_code == 0 else '失败'}")
    print(f"开始：{started_at}")
    print(f"结束：{ended_at}")
    print(f"日志：{log_path}")
    print(f"运行元数据：{meta_path}")

    if summary_paths:
        print("结果摘要：")
        for line in build_summary_lines(summary_paths):
            print(line)
    else:
        print("结果摘要：未识别到新的 summary/progress json，请检查日志。")

    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
