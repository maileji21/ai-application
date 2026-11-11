"""AI 穷游攻略生成器：高德 POI 采集 + 智谱 GLM-4-Flash 分批生成攻略

流程：输入城市 → 高德 POI 搜索（6 类景点）→ 清洗去重 → 分批调 LLM 补门票与攻略
      → 合并结果 → 输出质量报告（成功率/覆盖率/token/成本）并落盘 {城市}_run_stats.json

运行前先设置环境变量：
    gaode_API  高德开放平台 key
    GLM_API    智谱开放平台 key（GLM-4-Flash 免费模型）
"""
import os
import csv
import json
import sys
import requests
from datetime import datetime

# ---------- 配置 ----------
gaode_API_KEY = os.getenv("gaode_API", "")   # 高德开放平台 key，用于 POI 搜索
llm_API_KEY   = os.getenv("GLM_API", "")     # 智谱开放平台 key，用于生成攻略

gaode_url = "https://restapi.amap.com/v3/place/text"
llm_url   = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
LLM_MODEL = "glm-4-flash"

# token 单价（元/百万 token）。GLM-4-Flash 免费，单价为 0
# 初版曾用硅基流动 Qwen2.5-7B（0.35 元/百万 token），同 token 量约 ¥0.008/城市，
# 后为控制成本迁移至免费模型
PRICE_IN  = 0
PRICE_OUT = 0

BATCH_SIZE = 5     # 每批景点数：小模型单次输出有限，一批太多会被截断
MAX_RETRY  = 2     # 单批最大重试次数：同一 prompt 连续失败多为非偶发，无限重试只是浪费
MIN_YIELD  = 0.6   # 一批输出中有效条目最低占比，低于则判定整批失败

DEFAULT_TYPES = ['古镇', '公园', '博物馆', '寺庙', '海洋馆', '文创园']

# ---------- 采集质量统计 ----------
STATS = {"requests": 0, "retries": 0, "batch_ok": 0, "batch_fail": 0,
         "spots": 0, "spots_with_guide": 0, "tok_in": 0, "tok_out": 0}

def reset_stats():
    """清空统计计数器，跑多城市时每个城市开头调用一次"""
    for k in STATS:
        STATS[k] = 0


def call_llm_batch(names, prompt):
    """批量请求一批景点：失败重试 → 字段校验 → 仍不合格返回 None，由上层降级"""
    for attempt in range(MAX_RETRY + 1):
        if attempt:
            STATS["retries"] += 1
        STATS["requests"] += 1
        try:
            resp = requests.post(
                llm_url,
                headers={"Authorization": f"Bearer {llm_API_KEY}"},
                json={"model": LLM_MODEL,
                      "messages": [{"role": "user", "content": prompt}],
                      "max_tokens": 4000,     # 显式给足，防止输出中途截断导致 JSON 不完整
                      "temperature": 0.3},    # 要求固定 JSON 输出，压低随机性
                timeout=120,
            )
            if resp.status_code != 200:
                print(f"    [重试{attempt}] 状态码 {resp.status_code}")
                continue
            data = resp.json()
            usage = data.get("usage") or {}
            STATS["tok_in"]  += usage.get("prompt_tokens", 0)
            STATS["tok_out"] += usage.get("completion_tokens", 0)

            # 剥离代码围栏后解析 JSON；单条缺"景点/攻略"字段视为无效
            content = (data["choices"][0]["message"]["content"].strip()
                       .removeprefix("```json").removesuffix("```").strip())
            items = json.loads(content)["结果"]
            good = [it for it in items if it.get("景点") and it.get("攻略")]
            if len(good) >= max(1, int(len(names) * MIN_YIELD)):
                return good
            print(f"    [重试{attempt}] 只解析出 {len(good)}/{len(names)} 条")
        except Exception as e:
            print(f"    [重试{attempt}] 异常 {e.__class__.__name__}")
    return None


def search_pois(keyword, city):
    """高德 POI 搜索：按景点类型和城市取第一页（8 条），失败返回空列表"""
    params = {
        'key': gaode_API_KEY,
        'keywords': keyword,
        'city': city,
        'citylimit': 'true',   # 限制搜索范围为输入的城市
        'offset': '8',         # 每页 8 条
        'page': '1',
    }
    try:
        res = requests.get(gaode_url, params=params, timeout=15).json()
    except (requests.RequestException, ValueError) as e:
        print(f'    [高德] {keyword} 请求失败：{e.__class__.__name__}')
        return []
    return res.get('pois', []) if res.get('status') == '1' else []


def clean_collect(city, black_lst=None, types_lst=None):
    """按类型搜索景点并清洗：黑名单过滤、名称去重、字段规整"""
    all_data = []
    seen = set()                       # 景点名前缀去重，避免同一景区的多个入口重复入库
    black_lst = black_lst or []
    types_lst = types_lst or DEFAULT_TYPES

    for typ in types_lst:
        print(f'正在搜索{typ}的景点信息...')
        for poi in search_pois(typ, city):
            name = poi.get('name', '')
            if any(word in name for word in black_lst):
                continue
            clean_name = name.split('-')[0]
            if clean_name in seen:
                continue
            seen.add(clean_name)
            all_data.append({
                '景点': name,
                '类型': typ,
                '城市': city,
                '地址': poi.get('address', ''),
                '区域': poi.get('adname', ''),
                '电话': poi.get('tel') or '',     # 高德无电话时返回空列表，统一置空字符串
                '经纬度': poi.get('location', ''),
                '门票': '',
                '攻略': ''})
        print(f'{typ}的景点信息已搜索完成')

    print(f'共查询到 {len(all_data)} 个景点')
    return all_data


def AI_collect(spots, city):
    """分批调用 LLM 补全门票与攻略，三级容错（重试→校验→降级）保证单批失败不中断整体"""
    info = {}
    batches = [spots[i:i + BATCH_SIZE] for i in range(0, len(spots), BATCH_SIZE)]
    total = len(batches)
    print(f'[AI] {LLM_MODEL} 正在分{total}批分析{len(spots)}个景点......')

    for idx, batch in enumerate(batches, 1):
        names = [spot['景点'] for spot in batch]
        prompt = (
            f'你是穷游专家。给下面{city}的小众景点逐个补充信息：\n'
            f'{json.dumps(names, ensure_ascii=False)}\n'
            '门票写参考价(如"免费"/"10元")。'
            '攻略写150-250字，包含：亮点值得看什么、门票和预约注意事项、什么时候人最少'
            '公交地铁怎么坐最省钱、附近便宜的美食。景点名照抄。\n'
            '只输出json，格式：{"结果":[{"景点":"...","门票":"...","攻略":"..."}]}'
        )
        print(f'  → 第{idx}/{total}批 ({len(batch)}个景点)...')

        items = call_llm_batch(names, prompt)
        if items is None:                       # 三级容错最后一级：降级，字段留空
            STATS['batch_fail'] += 1
            print('    [降级] 该批跳过，字段留空')
            continue
        STATS['batch_ok'] += 1
        info.update({it['景点']: it for it in items})
        print(f'    ✓ 本批解析出 {len(items)} 个景点')

    for spot in spots:
        extra = info.get(spot['景点'], {})
        spot['门票'] = extra.get('门票', spot['门票'])
        spot['攻略'] = extra.get('攻略', spot['攻略'])

    STATS['spots'] = len(spots)
    STATS['spots_with_guide'] = sum(1 for s in spots if s['攻略'])
    report(city)
    save_csv(spots, city)
    return spots


CSV_FIELDS = ['景点', '类型', '城市', '地址', '区域', '电话', '经纬度', '门票', '攻略']

def save_csv(spots, city):
    """攻略结果落盘 csv；utf-8-sig 保证 Excel 直接打开不乱码"""
    filename = f'{city}_景点.csv'
    with open(filename, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(spots)
    print(f'  已保存 {filename}（{len(spots)} 条）')


def report(city):
    """打印并落盘本城市的采集质量指标"""
    s = STATS
    cost = s['tok_in'] * PRICE_IN + s['tok_out'] * PRICE_OUT
    batches = s['batch_ok'] + s['batch_fail']
    ok_rate = s['batch_ok'] / batches if batches else 0
    cover = s['spots_with_guide'] / s['spots'] if s['spots'] else 0

    print('\n' + '=' * 46)
    print(f'[{city}] 采集 {s["spots"]} 个景点')
    print(f'  请求 {s["requests"]} 次 / 重试 {s["retries"]} 次')
    print(f'  批次成功率 {ok_rate:.1%}  失败 {s["batch_fail"]} 批已降级')
    print(f'  攻略覆盖率 {cover:.1%}（{s["spots_with_guide"]}/{s["spots"]}）')
    print(f'  token in {s["tok_in"]} / out {s["tok_out"]}')
    print(f'  单城市成本 ¥{cost:.4f}')
    print('=' * 46)

    with open(f'{city}_run_stats.json', 'w', encoding='utf-8') as f:
        json.dump({**s, 'city': city, 'cost': round(cost, 4),
                   'ok_rate': round(ok_rate, 4), 'cover': round(cover, 4),
                   'ts': datetime.now().isoformat(timespec='seconds')},
                  f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    reset_stats()
    # 支持命令行参数（便于批量/自动化），无参数时退回交互输入
    # 用法：python data_collect.py 杭州 ["不想去的词 空格隔开"] ["类型 空格隔开"]
    if len(sys.argv) > 1:
        city = sys.argv[1].strip()
        black_lst = sys.argv[2].split() if len(sys.argv) > 2 else []
        types_lst = sys.argv[3].split() if len(sys.argv) > 3 else []
    else:
        city = input('城市：').strip() or '杭州'
        black_lst = [i for i in input('不想去（空格隔开）：').split(' ') if i]
        types_lst = [j for j in input('景点类型（空格隔开）：').split(' ') if j]
    spots = clean_collect(city, black_lst, types_lst)
    AI_collect(spots, city)
