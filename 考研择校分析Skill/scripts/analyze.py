"""考研择校分析：基于历年录取数据 + 大模型
用法：python analyze.py --school 重庆大学 --major 金融 --score 370 [--html 报告.html]
"""
import argparse, csv, re, sys, requests, os
from pathlib import Path

API_URL = 'https://open.bigmodel.cn/api/paas/v4/chat/completions'

DATA_FILE = Path(__file__).resolve().parent.parent / 'data' / '各院校历年数据采集.csv'

def load_rows():
    """读 csv，返回 list[dict]。文件不存在时 sys.exit 并说明"""
    if not DATA_FILE.exists():
        sys.exit(f'数据文件 {DATA_FILE} 不存在')
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return list(csv.DictReader(f))

def bucket(rows, xuexiao, zhuanye, fenshu, margin=10):
    """三步，全部来自原 ai_fenxi()：
    1. 目标院校+专业的历年分数线 → linian 文本
    2. 同专业其他学校按 ±margin 分桶 → chongci/wentuo/baodi 文本
    3. 每段超 1200 字符截断
    返回 dict"""
    linian = ''
    for r in rows:
        if xuexiao in r['学校'] and zhuanye in r['专业']:
            linian += '  ' + r['录取年份'] + '年 | 招生院系' + r['招生院系']
            linian += ' | 总分' + r['总分'] + ' | 政' + r['政治'] + ' | 外' + r['外语']
            linian += ' | 专一' + r['专业课一'] + ' | 专二' + r['专业课二'] + '\n'

    # 同专业的其他学校，按分数线与考生分差分冲刺/稳妥/保底
    # 先按"学校+专业"去重，只保留最近年份，避免同一学校占多条推荐
    latest = {}
    for r in rows:
        if zhuanye not in r['专业'] or xuexiao in r['学校']:
            continue
        key = (r['学校'], r['专业'])
        if key not in latest:
            latest[key] = r
        else:
            try:
                if int(r['录取年份']) > int(latest[key]['录取年份']):
                    latest[key] = r
            except ValueError:
                pass

    chongci = ''
    wentuo = ''
    baodi = ''
    fenshu = float(fenshu)  # 只转一次，不放循环里
    for (xx, zy), r in latest.items():
        try:
            xian = float(r['总分'])
        except ValueError:
            continue
        info = xx + ' | ' + zy + ' | ' + str(int(xian)) + '分 | ' + r['录取年份'] + '年'
        if xian > fenshu + margin:
            chongci += '  ' + info + '\n'
        elif xian >= fenshu - margin:
            wentuo += '  ' + info + '\n'
        else:
            baodi += '  ' + info + '\n'

    # 截断过长的列表（按行截断，避免截半行）
    def clip(text, limit=1200):
        out = ''
        for line in text.splitlines(keepends=True):
            if len(out) + len(line) > limit:
                out += '  ...(省略其余)\n'
                break
            out += line
        return out
    chongci = clip(chongci)
    wentuo = clip(wentuo)
    baodi = clip(baodi)
    return {'linian': linian, 'chongci': chongci, 'wentuo': wentuo, 'baodi': baodi}

def build_prompt(xuexiao, zhuanye, fenshu, buckets):
    """原 prompt 模板原样搬"""
    prompt = '你是考研数据分析专家，请用简洁的语言回答，总共不超过500字：\n\n'
    prompt += '1. 以下是"' + xuexiao + '-' + zhuanye + '"历年分数线，预测明年总分（只需给数字+一句话理由）\n'
    prompt += buckets['linian'] + '\n'
    prompt += '2. 考生' + str(int(fenshu)) + '分，匹配结果如下：\n'
    prompt += '【冲刺】\n' + buckets['chongci'] + '\n'
    prompt += '【稳妥】\n' + buckets['wentuo'] + '\n'
    prompt += '【保底】\n' + buckets['baodi'] + '\n'
    prompt += '请用以下格式输出（每项写简洁，不要展开）：\n'
    prompt += '---\n'
    prompt += '预测明年线：约XX分（须注明"此为预测值，非官方公布"，理由：一句话）\n'
    prompt += '\n'
    prompt += '冲刺推荐：2个（学校-专业，分数线，理由一句话）\n'
    prompt += '稳妥推荐：2个（同上）\n'
    prompt += '保底推荐：2个（同上）\n'
    prompt += '\n'
    prompt += '建议：1条\n'
    prompt += '\n'
    prompt += '硬性要求：冲刺推荐只能从【冲刺】列表中选，稳妥推荐只能从【稳妥】列表中选，'
    prompt += '保底推荐只能从【保底】列表中选，不得混档；同一学校只能出现在一个档位；'
    prompt += '某档列表为空时写"该档暂无匹配院校"。\n'
    return prompt

def call_llm(prompt):
    """密钥从环境变量 GLM_API 读取；
    为空 → sys.exit('未设置 GLM_API 环境变量')
    非 200 或无 choices → sys.exit 并带上服务端返回的错误信息"""
    API_KEY = os.getenv('GLM_API', '')
    if not API_KEY:
        sys.exit('未设置 GLM_API 环境变量')
    try:
        resp = requests.post(API_URL, headers={
            'Authorization': 'Bearer ' + API_KEY,
            'Content-Type': 'application/json',
        }, json={
            'model': 'glm-4-flash',
            'messages': [{'role': 'user', 'content': prompt}],
            'max_tokens': 1500,
            'temperature': 0.3,
        }, timeout=60)
    except requests.RequestException as e:
        sys.exit('请求大模型接口失败：' + str(e))
    if resp.status_code != 200:
        sys.exit(f'接口返回 {resp.status_code}：{resp.text[:300]}')
    data = resp.json()
    choices = data.get('choices')
    if not choices:
        sys.exit('接口未返回内容：' + str(data)[:300])
    return choices[0]['message']['content']

def parse_sections(text):
    """原 parse_ai_sections() 原样搬：五个正则提取
    预测明年线/冲刺/稳妥/保底/建议"""
    sections = {
        'prediction': '',
        'chongci': '',
        'wentuo': '',
        'baodi': '',
        'advice': '',
    }
    clean = text.replace('---', '').strip()

    patterns = {
        'prediction': r'预测\s*(?:明年|\d{4})\s*线\s*[：:]\s*(.+?)(?=\n\s*(?:冲刺|稳妥|保底|建议|\Z))',
        'chongci': r'冲刺推荐\s*[：:]\s*(.+?)(?=\n\s*(?:稳妥|保底|建议|\Z))',
        'wentuo': r'稳妥推荐\s*[：:]\s*(.+?)(?=\n\s*(?:保底|建议|\Z))',
        'baodi': r'保底推荐\s*[：:]\s*(.+?)(?=\n\s*(?:建议|\Z))',
        'advice': r'建议\s*[：:]\s*(.+?)$',
    }

    for key, pattern in patterns.items():
        m = re.search(pattern, clean, re.DOTALL | re.MULTILINE)
        if m:
            sections[key] = m.group(1).strip()

    return sections

def validate_recommendations(sections, buckets, rows):
    """校验模型推荐：每条推荐里识别出的学校必须出现在对应分档列表中，
    否则剔除；某档不足 2 条时用分档列表里的学校补齐。
    模型（尤其免费模型）可能混档或漏档，这里做代码级兜底。"""
    all_schools = sorted({r['学校'] for r in rows}, key=len, reverse=True)  # 长名优先匹配

    def check(section_text, bucket_text):
        valid = []
        for line in section_text.splitlines():
            line = line.strip()
            if not line:
                continue
            school = next((s for s in all_schools if s in line), None)
            if school and school in bucket_text:
                valid.append(line)
        return valid

    def fill(bucket_text, valid):
        used = {s for s in all_schools if any(s in v for v in valid)}
        if len(valid) >= 2:
            return '\n'.join(valid[:2])
        lines = [l.strip() for l in bucket_text.splitlines() if l.strip()]
        out = valid[:]
        for l in lines:
            if len(out) >= 2:
                break
            if any(s in l for s in used):  # 补齐时跳过已在推荐里的学校
                continue
            out.append(l)
        return '\n'.join(out) if out else '该档暂无匹配院校'

    for key in ('chongci', 'wentuo', 'baodi'):
        sections[key] = fill(buckets[key], check(sections[key], buckets[key]))
    return sections

def generate_html(school, major, score, sections, out_path):
    """简化版 HTML 报告，模板独立，不依赖 E 盘原文件"""
    def block(title, content):
        return f'<h2>{title}</h2><p>{content}</p>' if content else ''
    html = f"""<!DOCTYPE html>
<html lang="zh">
<head><meta charset="utf-8"><title>考研择校分析：{school} {major} {int(score)}分</title>
<style>
body {{ font-family: "Microsoft YaHei", sans-serif; max-width: 760px; margin: 30px auto; padding: 0 20px; color: #222; line-height: 1.7; }}
h1 {{ border-bottom: 2px solid #2b6cb0; padding-bottom: 8px; font-size: 22px; }}
h2 {{ color: #2b6cb0; font-size: 17px; margin-top: 26px; }}
p {{ white-space: pre-line; background: #f7f9fb; padding: 10px 14px; border-radius: 6px; }}
</style></head>
<body>
<h1>考研择校分析：{school} {major} · 预估 {int(score)} 分</h1>
{block('预测明年线', sections['prediction'])}
{block('冲刺推荐', sections['chongci'])}
{block('稳妥推荐', sections['wentuo'])}
{block('保底推荐', sections['baodi'])}
{block('备考建议', sections['advice'])}
<p style="background:none;color:#888;font-size:13px;">数据基于 5780 条历年录取记录（截至 2026 年），以院校官方最新公告为准。</p>
</body></html>"""
    Path(out_path).write_text(html, encoding='utf-8')

def main():
    ap = argparse.ArgumentParser(description='考研择校分析')
    ap.add_argument('--school', required=True, help='目标院校')
    ap.add_argument('--major', required=True, help='目标专业')
    ap.add_argument('--score', required=True, type=int, help='预估分数')
    ap.add_argument('--html', help='可选：输出 HTML 报告路径')
    args = ap.parse_args()

    rows = load_rows()  # 只读一次，bucket 复用
    buckets = bucket(rows, args.school, args.major, args.score)
    if not buckets['linian']:
        sys.exit(f'未找到该校数据：{args.school} - {args.major}')

    prompt = build_prompt(args.school, args.major, args.score, buckets)
    text = call_llm(prompt)
    sections = validate_recommendations(parse_sections(text), buckets, rows)

    # stdout 输出 Markdown
    print(f"## 预测\n{sections['prediction']}")
    print(f"\n## 冲刺推荐\n{sections['chongci']}")
    print(f"\n## 稳妥推荐\n{sections['wentuo']}")
    print(f"\n## 保底推荐\n{sections['baodi']}")
    print(f"\n## 建议\n{sections['advice']}")

    if args.html:
        generate_html(args.school, args.major, args.score, sections, args.html)
        print(f"\nHTML 报告已保存：{args.html}")

if __name__ == '__main__':
    main()
