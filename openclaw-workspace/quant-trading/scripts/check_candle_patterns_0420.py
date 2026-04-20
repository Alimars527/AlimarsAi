"""4/20候选票蜡烛图二次确认"""
import tushare as ts
pro = ts.pro_api('be0e395aeb600a02110bcac4fca37a8d5b792afe8f13507040357d23')

targets = [
    ("600602.SH", "云赛智联", "软件服务/AI"),
    ("002539.SZ", "云图控股", "农药化肥/支线2"),
    ("000553.SZ", "安道麦A", "农药化肥/支线2"),
    ("002271.SZ", "东方雨虹", "建材"),
    ("600299.SH", "安迪苏", "饲料"),
    ("000065.SZ", "北方国际", "建筑工程"),
    ("603588.SH", "高能环境", "环境保护(已持仓)"),
    ("000951.SZ", "中国重汽", "汽车整车"),
]

for code, name, note in targets:
    df = pro.daily(ts_code=code, start_date='20260407', end_date='20260420')
    df = df.sort_values('trade_date').tail(10)
    print(f"\n=== {code} {name} ({note}) ===")
    prev_close = None
    prev_o = prev_c = None
    for _, r in df.iterrows():
        o, h, l, c = r['open'], r['high'], r['low'], r['close']
        vol = r['vol']
        pct = r.get('pct_chg', 0)
        
        body = abs(c - o)
        upper = h - max(c, o)
        lower = min(c, o) - l
        total_range = h - l if h != l else 0.01
        
        shape = ""
        if c > o:
            shape = "阳线"
        elif c < o:
            shape = "阴线"
        else:
            shape = "平盘"
        
        # 十字星
        if body / total_range < 0.1:
            shape = "十字星"
        # 锤子线: 实体小, 下影线>=2倍实体, 上影线小
        elif lower >= 2 * body and upper <= body * 0.3 and body > 0:
            shape = "锤子线"
        # 射击之星
        elif upper >= 2 * body and lower <= body * 0.3 and body > 0:
            shape = "射击之星"
        # 大阳/大阴
        elif body / total_range > 0.7:
            if c > o:
                shape = "大阳线"
            else:
                shape = "大阴线"
        
        # 看涨吞没/看跌吞没
        engulf = ""
        if prev_o is not None and prev_c is not None:
            if c > o and prev_c < prev_o and c > prev_o and o < prev_c:
                engulf = " [看涨吞没]"
            elif c < o and prev_c > prev_o and o > prev_c and c < prev_o:
                engulf = " [看跌吞没]"
        
        # 启明星(简化: 前阴+小实体+阳)
        star = ""
        if prev_o is not None and prev_c is not None:
            prev_body = abs(prev_c - prev_o)
            if prev_c < prev_o and body / total_range < 0.3 and c > o and c > (prev_o + prev_c) / 2:
                star = " [启明星]"
        
        print(f"  {r['trade_date']} O:{o:.2f} H:{h:.2f} L:{l:.2f} C:{c:.2f} Vol:{vol:.0f} Pct:{pct:.2f}% {shape}{engulf}{star}")
        
        prev_o = o
        prev_c = c
