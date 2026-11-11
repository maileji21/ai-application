import html

BASE_CSS = """
    * { box-sizing: border-box; }
    body { font-family: "微软雅黑", "PingFang SC", sans-serif; max-width: 800px; margin: 0 auto; padding: 40px 20px; background: linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%); min-height: 100vh; }
    h1 { text-align: center; color: #2c7be5; margin-bottom: 30px; font-size: 28px; }
    .container { background: white; padding: 40px; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); }
"""

FORM_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>穷游攻略生成器</title>
    <style>
        """ + BASE_CSS + """
        .form-row { display: flex; gap: 10px; margin-bottom: 15px; }
        input { flex: 1; padding: 12px 14px; font-size: 15px; border: 2px solid #e9ecef; border-radius: 8px; outline: none; transition: border-color 0.2s; }
        input:focus { border-color: #2c7be5; }
        label { display: block; font-size: 14px; color: #495057; margin-bottom: 6px; font-weight: 500; }
        button { padding: 12px 32px; background: #2c7be5; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; transition: background 0.2s; }
        button:hover { background: #1b6ddb; }
        #loading { display: none; text-align: center; margin-top: 20px; color: #666; font-size: 14px; }
        .tip { text-align: center; color: #868e96; font-size: 13px; margin-top: 10px; }
        .btn-row { justify-content: center; margin-top: 25px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🗺️ 穷游攻略生成器</h1>
        <form method="POST">
            <div>
                <label>📍 目标城市</label>
                <div class="form-row" style="margin-bottom:20px;">
                    <input type="text" name="city" placeholder="比如：杭州" required>
                </div>
            </div>
            <div>
                <label>🏷️ 想去的景点类型（空格隔开）</label>
                <div class="form-row">
                    <input type="text" name="popular_lst" placeholder="公园 博物馆 文创园 古镇" value="古镇 公园 博物馆 寺庙 海洋馆 文创园">
                </div>
            </div>
            <div>
                <label>🚫 不想去的景点（空格隔开，可选）</label>
                <div class="form-row">
                    <input type="text" name="black_lst" placeholder="比如：西湖 灵隐寺">
                </div>
            </div>
            <div class="form-row btn-row">
                <button type="submit">🚀 生成攻略</button>
            </div>
            <p class="tip">⚠️ 生成需要约1-2分钟（爬取高德数据+AI分批分析），请耐心等待</p>
            <div id="loading">⏳ 正在处理中，请勿关闭页面...</div>
        </form>
    </div>
    <script>
        document.querySelector('form').addEventListener('submit', () => {
            document.getElementById('loading').style.display = 'block';
        });
    </script>
</body>
</html>
"""


def _escape(s):
    return html.escape(str(s)) if s else ''


def render_result(spots, city):
    cards = ''
    for i, spot in enumerate(spots, 1):
        name = _escape(spot.get('景点', ''))
        type_ = _escape(spot.get('类型', ''))
        ticket = _escape(spot.get('门票', '未知'))
        area = _escape(spot.get('区域', ''))
        addr = _escape(spot.get('地址', ''))
        tel = _escape(spot.get('电话', ''))
        guide = _escape(spot.get('攻略', ''))
        cards += f"""
        <div class="spot-card">
            <div class="card-head">
                <span class="num">#{i}</span>
                <span class="spot-name">{name}</span>
                <span class="tag">{type_}</span>
            </div>
            <div class="card-info">
                <span class="info-item 💰">门票：{ticket}</span>
                <span class="info-item">📍 {area} {addr}</span>
                {f'<span class="info-item">📞 {tel}</span>' if tel else ''}
            </div>
            <div class="card-guide">{guide or '暂无AI攻略'}</div>
        </div>
        """
    css_block = """
        .summary { text-align: center; margin-bottom: 30px; }
        .summary h2 { color: #2c7be5; margin-bottom: 8px; }
        .summary p { color: #6c757d; font-size: 14px; }
        .spot-card { background: white; border: 1px solid #e9ecef; border-radius: 12px; padding: 20px 24px; margin-bottom: 18px; box-shadow: 0 1px 6px rgba(0,0,0,0.04); }
        .card-head { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
        .num { background: #2c7be5; color: white; border-radius: 50%; width: 28px; height: 28px; display: inline-flex; align-items: center; justify-content: center; font-size: 13px; font-weight: bold; flex-shrink: 0; }
        .spot-name { font-size: 18px; font-weight: 600; color: #212529; }
        .tag { background: #e7f1ff; color: #2c7be5; padding: 2px 10px; border-radius: 12px; font-size: 12px; margin-left: auto; }
        .card-info { display: flex; flex-wrap: wrap; gap: 14px; font-size: 13px; color: #6c757d; margin-bottom: 12px; }
        .info-item { display: inline-block; }
        .card-guide { background: #f8f9fa; border-left: 3px solid #2c7be5; padding: 12px 16px; font-size: 14px; color: #495057; line-height: 1.8; border-radius: 0 8px 8px 0; white-space: pre-wrap; }
        .back-btn { display: block; margin: 30px auto 0; padding: 10px 28px; background: #6c757d; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; }
        .back-btn:hover { background: #5a6268; }
    """
    summary = f"""
        <div class="summary">
            <h2>🗺️ {_escape(city)} 穷游攻略</h2>
            <p>共找到 {len(spots)} 个景点 · AI已为其中 {sum(1 for s in spots if s.get('攻略'))} 个生成攻略</p>
        </div>
    """
    return f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{_escape(city)} 穷游攻略</title>
    <style>
        {BASE_CSS}
        {css_block}
    </style>
</head>
<body>
    {summary}
    {cards}
    <button class="back-btn" onclick="location.href='/'">🔄 重新生成</button>
</body>
</html>
"""