"""招生人数 Top10 看板：读本地录取数据，用 pyecharts 产出五张图。

用法：
    pip install pandas pyecharts
    python scripts/visualize.py

产出（都在 out/ 目录下）：
    招生人数Top10_Bar.html      横向柱状图
    招生人数Top10_Line.html     折线图
    招生人数Top10_Pie.html      饼图
    招生人数Top10_Pro.html      柱线组合
    招生人数Top10_Pro_Max.html  四合一页面

注：这里的"招生人数"是按「学校在当年数据中收录的专业条目数」统计的，
不是院校官方公布的招生计划数。要统计真实招生人数需要另一份数据源。
"""
from pathlib import Path

import pandas as pd
from pyecharts import options as opts
from pyecharts.charts import Bar, Line, Page, Pie

BASE = Path(__file__).resolve().parent.parent
CSV = BASE / "data" / "各院校历年数据采集.csv"
OUT = BASE / "out"
OUT.mkdir(exist_ok=True)

df = pd.read_csv(CSV)

# 取数据里最新的年份，不写死
YEAR = int(df["录取年份"].max())
new_df = df[df["录取年份"] == YEAR]

school_count = (
    new_df.groupby("学校").size()
    .sort_values(ascending=False)
    .reset_index(name="人数")
)

school_x = school_count["学校"].tolist()
school_y = school_count["人数"].tolist()

# ── 横向柱状图 ──
bar = Bar()
bar.add_xaxis(school_x)
bar.add_yaxis("招生人数", school_y, color_by="data")
bar.set_global_opts(
    title_opts=opts.TitleOpts(title="招生人数Top10"),
    xaxis_opts=opts.AxisOpts(axislabel_opts={"rotate": 0}),
)
bar.reversal_axis()
bar.render(str(OUT / "招生人数Top10_Bar.html"))

# ── 折线图 ──
line = Line()
line.add_xaxis(school_x)
line.add_yaxis("招生人数", school_y, color_by="data")
line.set_global_opts(
    title_opts=opts.TitleOpts(title="招生人数Top10"),
    xaxis_opts=opts.AxisOpts(axislabel_opts={"rotate": 30}),
)
line.render(str(OUT / "招生人数Top10_Line.html"))

# ── 饼图 ──
pie_data = list(zip(school_x, school_y))
pie = Pie()
pie.add("招生人数Top10", pie_data)
pie.set_series_opts(label_opts=opts.LabelOpts(formatter="{b}:{c} ({d}%)"))
pie.render(str(OUT / "招生人数Top10_Pie.html"))

# ── 柱线组合 ──
mix_bar = Bar()
mix_bar.add_xaxis(school_x)
mix_bar.add_yaxis("招生数量", school_y, color_by="data")

mix_line = Line()
mix_line.add_xaxis(school_x)
mix_line.add_yaxis("招生数量", school_y, color_by="data")
mix_bar.set_global_opts(
    title_opts=opts.TitleOpts(title="招生人数Top10"),
    xaxis_opts=opts.AxisOpts(axislabel_opts={"rotate": 30}),
)
mix_bar.overlap(mix_line)
mix_bar.render(str(OUT / "招生人数Top10_Pro.html"))

# ── 四合一 ──
page = Page(layout=Page.SimplePageLayout)
page.add(bar, line, pie, mix_bar)
page.render(str(OUT / "招生人数Top10_Pro_Max.html"))

print(f"已生成 5 个看板到 {OUT}")
