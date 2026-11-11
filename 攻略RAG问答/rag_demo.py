"""最小 RAG demo：旅游攻略知识库问答
流程：文档加载 → 分块 → 向量化（embedding-3，2048 维）→ 余弦检索 top-k → 拼 prompt → LLM 生成（带引用）

用法：
  python rag_demo.py --ask "杭州有哪些免费景点"
  python rag_demo.py --ask "去上海豫园怎么坐车" --topk 5
  python rag_demo.py --rebuild            # 重建向量索引
"""
import argparse, csv, json, os, re, sys, time
from pathlib import Path

import numpy as np
import requests

EMB_API = 'https://open.bigmodel.cn/api/paas/v4/embeddings'
CHAT_API = 'https://open.bigmodel.cn/api/paas/v4/chat/completions'
EMB_MODEL = 'embedding-3'
CHAT_MODEL = 'glm-4-flash'

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / 'data'
CACHE_FILE = BASE / 'index_cache.npz'

CHUNK_SIZE = 300       # 每块字符数
CHUNK_OVERLAP = 50     # 相邻块重叠，防语义被切断
EMB_BATCH = 16


def _key():
    k = os.getenv('GLM_API', '')
    if not k:
        sys.exit('未设置 GLM_API 环境变量')
    return k


def load_docs():
    """读 data/ 下所有景点 csv，拼成文档（一个景点一篇）"""
    files = sorted(DATA_DIR.glob('*_景点.csv'))
    if not files:
        sys.exit(f'{DATA_DIR} 下没有 *_景点.csv，请先把攻略数据放进去')
    docs = []
    for f in files:
        with open(f, 'r', encoding='utf-8-sig') as fp:
            for row in csv.DictReader(fp):
                guide = (row.get('攻略') or '').strip()
                if not guide:
                    continue
                docs.append({
                    'spot': row.get('景点', ''),
                    'city': row.get('城市', ''),
                    'type': row.get('类型', ''),
                    'addr': row.get('地址', ''),
                    'ticket': row.get('门票', ''),
                    'guide': guide,
                })
    return docs


def chunk_docs(docs):
    """按 300 字切块，50 字重叠；每块带上景点名与门票，保证块本身可独立回答"""
    chunks = []
    for d in docs:
        text = d['guide']
        start = 0
        while start < len(text):
            piece = text[start:start + CHUNK_SIZE]
            chunks.append({
                'text': f"景点：{d['spot']}（{d['city']}·{d['type']}）\n地址：{d['addr']}\n门票：{d['ticket']}\n攻略：{piece}",
                'spot': d['spot'],
                'city': d['city'],
            })
            if start + CHUNK_SIZE >= len(text):
                break
            start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def embed(texts):
    """批量向量化，返回 (n, 2048) float32"""
    out = []
    key = _key()
    for i in range(0, len(texts), EMB_BATCH):
        batch = texts[i:i + EMB_BATCH]
        r = requests.post(EMB_API, headers={'Authorization': 'Bearer ' + key,
                                            'Content-Type': 'application/json'},
                          json={'model': EMB_MODEL, 'input': batch}, timeout=60)
        if r.status_code != 200:
            sys.exit(f'embedding 接口返回 {r.status_code}：{r.text[:200]}')
        data = r.json().get('data')
        if not data:
            sys.exit('embedding 接口未返回数据：' + str(r.json())[:200])
        out.extend(item['embedding'] for item in data)
        if len(texts) > 1:   # 单条查询（如评测）不打印进度
            print(f'  向量化 {min(i + EMB_BATCH, len(texts))}/{len(texts)}', end='\r')
    if len(texts) > 1:
        print()
    return np.array(out, dtype=np.float32)


def build_index(rebuild=False):
    """分块 + 向量化，结果缓存到 npz（有缓存且不强制重建时直接读）"""
    if CACHE_FILE.exists() and not rebuild:
        z = np.load(CACHE_FILE, allow_pickle=True)
        return z['vectors'], json.loads(str(z['chunks']))
    docs = load_docs()
    chunks = chunk_docs(docs)
    print(f'文档 {len(docs)} 篇 → 分块 {len(chunks)} 块，开始向量化……')
    t0 = time.time()
    vectors = embed([c['text'] for c in chunks])
    np.savez(CACHE_FILE, vectors=vectors, chunks=json.dumps(chunks, ensure_ascii=False))
    print(f'索引完成，耗时 {time.time() - t0:.1f}s，向量维度 {vectors.shape[1]}')
    return vectors, chunks


def retrieve(question, vectors, chunks, topk=3):
    """余弦相似度检索（向量已归一化，点积即余弦）"""
    q = embed([question])[0]
    q = q / (np.linalg.norm(q) + 1e-9)
    mat = vectors / (np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-9)
    scores = mat @ q
    idx = np.argsort(-scores)[:topk]
    return [(float(scores[i]), chunks[i]) for i in idx]


def answer(question, hits):
    """拼 prompt，强制只依据资料回答并标引用编号"""
    context = '\n\n'.join(f'【{n}】{h[1]["text"]}' for n, h in enumerate(hits, 1))
    prompt = (
        '你是旅游攻略助手。只能根据下面的资料回答问题，不要编造资料里没有的信息。\n'
        '每句回答结尾只标注一个最相关的资料编号，格式如【1】；不要列多个编号。'
        '资料不足以回答时直接说“资料中没有相关信息”。\n\n'
        f'资料：\n{context}\n\n'
        f'问题：{question}\n'
        '回答（简洁，不超过150字）：'
    )
    key = _key()
    r = requests.post(CHAT_API, headers={'Authorization': 'Bearer ' + key,
                                         'Content-Type': 'application/json'},
                      json={'model': CHAT_MODEL,
                            'messages': [{'role': 'user', 'content': prompt}],
                            'max_tokens': 500, 'temperature': 0.3}, timeout=60)
    if r.status_code != 200:
        sys.exit(f'对话接口返回 {r.status_code}：{r.text[:200]}')
    choices = r.json().get('choices')
    if not choices:
        sys.exit('对话接口未返回内容：' + str(r.json())[:200])
    return choices[0]['message']['content'].strip()


def main():
    ap = argparse.ArgumentParser(description='旅游攻略 RAG 问答')
    ap.add_argument('--ask', help='要问的问题')
    ap.add_argument('--topk', type=int, default=3, help='检索条数，默认 3')
    ap.add_argument('--min-score', type=float, default=0.40,
                    help='相似度阈值，低于则直接判定语料里没有（实测语料外问题约 0.34-0.36）')
    ap.add_argument('--rebuild', action='store_true', help='强制重建索引')
    args = ap.parse_args()

    vectors, chunks = build_index(args.rebuild)
    if not args.ask:
        print(f'索引就绪：{len(chunks)} 块。用 --ask "问题" 提问。')
        return

    t0 = time.time()
    hits = retrieve(args.ask, vectors, chunks, args.topk)
    print(f'\n问题：{args.ask}')
    print(f'检索 {len(hits)} 条（{time.time() - t0:.2f}s）：')
    for n, (score, c) in enumerate(hits, 1):
        print(f'  【{n}】{c["spot"]}（{c["city"]}） 相似度 {score:.3f}')

    if hits[0][0] < args.min_score:
        print(f'\n最高相似度 {hits[0][0]:.3f} < 阈值 {args.min_score}：'
              f'语料中没有相关内容，不调用大模型，直接拒答。')
        return

    print('\n回答：')
    ans = answer(args.ask, hits)
    print(ans)
    cited = sorted({int(x) for x in re.findall(r'【(\d+)】', ans) if 1 <= int(x) <= len(hits)})
    if cited:
        print('\n引用来源：' + '、'.join(f'【{i}】{hits[i - 1][1]["spot"]}' for i in cited))
    else:
        print('\n未标注引用，检索到：' + '、'.join(c['spot'] for _, c in hits))


if __name__ == '__main__':
    main()
