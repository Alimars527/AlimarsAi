import re
from datetime import datetime
from .config import load_holdings, save_holdings


def parse_cn_holding_text(text: str):
    text = text.strip()
    add_match = re.search(r'(新增|买入)\s*([\u4e00-\u9fa5A-Za-z0-9]+)[（(]?([0-9]{6}\.(?:SH|SZ)|[0-9]{6})?[)）]?\s*.*?成本\s*([0-9.]+)\s*.*?([0-9]+)\s*手', text)
    del_match = re.search(r'(清仓|删除|移除)\s*([\u4e00-\u9fa5A-Za-z0-9]+)?[（(]?([0-9]{6}\.(?:SH|SZ)|[0-9]{6})[)）]?', text)
    upd_match = re.search(r'(更新|修改)\s*([\u4e00-\u9fa5A-Za-z0-9]+)[（(]?([0-9]{6}\.(?:SH|SZ)|[0-9]{6})?[)）]?\s*.*?成本\s*([0-9.]+)\s*.*?([0-9]+)\s*手', text)
    if add_match:
        _, name, code, cost, qty = add_match.groups()
        return {'action': 'upsert', 'name': name, 'code': code or '', 'cost': float(cost), 'quantity': int(qty)}
    if upd_match:
        _, name, code, cost, qty = upd_match.groups()
        return {'action': 'upsert', 'name': name, 'code': code or '', 'cost': float(cost), 'quantity': int(qty)}
    if del_match:
        _, name, code = del_match.groups()
        return {'action': 'remove', 'name': name or '', 'code': code}
    return None


def normalize_code(code: str):
    if not code:
        return code
    return code if code.endswith('.SH') or code.endswith('.SZ') else (f'{code}.SH' if code.startswith('6') else f'{code}.SZ')


def apply_holding_instruction(text: str):
    parsed = parse_cn_holding_text(text)
    if not parsed:
        return {'ok': False, 'message': '未识别到持仓变更指令'}

    data = load_holdings()
    holdings = data.get('holdings', [])

    if parsed['action'] == 'upsert':
        code = normalize_code(parsed['code']) if parsed['code'] else None
        found = False
        for h in holdings:
            if (code and h['code'] == code) or h['name'] == parsed['name']:
                h['name'] = parsed['name']
                if code:
                    h['code'] = code
                h['cost'] = parsed['cost']
                h['quantity'] = parsed['quantity']
                found = True
                break
        if not found:
            holdings.append({
                'code': code,
                'name': parsed['name'],
                'cost': parsed['cost'],
                'quantity': parsed['quantity'],
            })
        data['holdings'] = holdings
        data['updated_at'] = datetime.now().isoformat()
        save_holdings(data)
        return {'ok': True, 'message': f"已更新持仓：{parsed['name']}"}

    if parsed['action'] == 'remove':
        code = normalize_code(parsed['code']) if parsed['code'] else None
        before = len(holdings)
        holdings = [h for h in holdings if not ((code and h['code'] == code) or (parsed['name'] and h['name'] == parsed['name']))]
        data['holdings'] = holdings
        data['updated_at'] = datetime.now().isoformat()
        save_holdings(data)
        return {'ok': True, 'message': '已删除持仓' if len(holdings) < before else '未找到对应持仓'}

    return {'ok': False, 'message': '未知动作'}
