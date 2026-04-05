from pathlib import Path
from datetime import datetime
import json

ROOT = Path('/Users/alimars/.openclaw/workspace/quant-trading')
OUT_MD = ROOT / 'outputs' / 'PROGRESS.md'
OUT_JSON = ROOT / 'outputs' / 'progress.json'

def update(current_task: str, phase: str, status: str, current_status: str, completed, in_progress, latest_conclusion: str):
    ts = datetime.now().astimezone().isoformat()
    md = []
    md.append('# 进度看板')
    md.append('')
    md.append(f'- 更新时间：{ts}')
    md.append(f'- 当前主任务：{current_task}')
    md.append(f'- 当前阶段：{phase}')
    md.append(f'- 当前状态：{current_status}')
    md.append('')
    md.append('## 已完成')
    for item in completed:
        md.append(f'- [x] {item}')
    md.append('')
    md.append('## 当前正在做')
    for item in in_progress:
        md.append(f'- [ ] {item}')
    md.append('')
    md.append('## 最近结论')
    md.append(f'- {latest_conclusion}')
    OUT_MD.write_text('\n'.join(md), encoding='utf-8')
    OUT_JSON.write_text(json.dumps({
        'updated_at': ts,
        'current_task': current_task,
        'phase': phase,
        'status': status,
        'current_status': current_status,
        'completed': completed,
        'in_progress': in_progress,
        'latest_conclusion': latest_conclusion,
    }, ensure_ascii=False, indent=2), encoding='utf-8')

if __name__ == '__main__':
    print('Use update() from other scripts or quick ad-hoc calls.')
