#!/usr/bin/env python3
"""统一跑 v1-v4 回撤止损变体，串行执行，每跑完一个保存结果"""
import subprocess, json, sys, shutil
from pathlib import Path

ROOT = Path("/Volumes/Alimars扩容空间/AiLab/openclaw-workspace/quant-trading")
OUT = ROOT / "outputs"

scripts = [
    ("v1_high_m3", "最高价-3%"),
    ("v2_close_m3", "收盘价-3%"),
    ("v3_low_m2", "最低价-2%"),
    ("v4_low_m4", "最低价-4%"),
]

results = {}
for tag, label in scripts:
    print(f"\n{'='*50}", flush=True)
    print(f"Running {tag} ({label})...", flush=True)
    print(f"{'='*50}", flush=True)
    
    proc = subprocess.run(
        ["python3", "-u", f"scripts/run_5w_tpsl_trail_{tag}.py"],
        capture_output=True, text=True, timeout=600,
        cwd=str(ROOT)
    )
    
    # 读summary文件（VERSION_TAG=combo_v4b_with_tpsl）
    summary_path = OUT / "sim_replay_20230101_combo_v4b_with_tpsl_summary.json"
    if summary_path.exists():
        with open(summary_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # 备份为带tag的文件名
        backup_path = OUT / f"sim_replay_20230101_trail_{tag}_summary.json"
        shutil.copy2(summary_path, backup_path)
        
        results[tag] = {
            "label": label,
            "total_return_pct": data.get("total_return_pct"),
            "final_equity": data.get("final_equity"),
            "trade_count": data.get("trade_count"),
            "win_rate_pct": data.get("win_rate_pct"),
            "max_drawdown_pct": data.get("max_drawdown_pct"),
            "cagr_pct": data.get("cagr_pct"),
            "yearly_breakdown": data.get("yearly_breakdown", {}),
            "exit_stats": data.get("exit_stats", {}),
            "tp_sl_counts": data.get("tp_sl_counts", {}),
        }
        print(f"  Result: {data.get('total_return_pct')}% / {data.get('trade_count')}笔 / 胜率{data.get('win_rate_pct')}% / 回撤{data.get('max_drawdown_pct')}% / CAGR {data.get('cagr_pct')}%", flush=True)
    else:
        results[tag] = {"label": label, "error": "no summary file"}
        print(f"  ERROR: no summary file found", flush=True)

print("\n\n" + "="*60, flush=True)
print("ALL RESULTS SUMMARY", flush=True)
print("="*60, flush=True)
for tag, r in results.items():
    if "error" not in r:
        print(f"{tag} ({r['label']}): +{r['total_return_pct']}% / {r['trade_count']}笔 / 胜率{r['win_rate_pct']}% / 回撤{r['max_drawdown_pct']}% / CAGR {r['cagr_pct']}%", flush=True)
    else:
        print(f"{tag} ({r.get('label','')}): ERROR - {r.get('error')}", flush=True)

print("\n" + json.dumps(results, ensure_ascii=False, indent=2), flush=True)
