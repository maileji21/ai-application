"""检索质量评测：人工标注问题集 → 看正确答案是否落在 top-k 里
用法：python eval_retrieval.py [--topk 3]
不调用大模型，只测检索层（快、可重复）。
"""
import argparse, json, sys
from pathlib import Path

from rag_demo import build_index, retrieve, BASE

QFILE = BASE / 'eval_questions.json'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--topk', type=int, default=3)
    args = ap.parse_args()

    questions = json.loads(QFILE.read_text(encoding='utf-8'))
    vectors, chunks = build_index()
    print(f'语料 {len(chunks)} 块，评测 {len(questions)} 题，top-{args.topk}\n')

    hit1 = hitk = 0
    for n, item in enumerate(questions, 1):
        hits = retrieve(item['q'], vectors, chunks, args.topk)
        spots = [c['spot'] for _, c in hits]
        rank = next((i + 1 for i, s in enumerate(spots)
                     if any(e in s or s in e for e in item['expect'])), None)
        hit1 += 1 if rank == 1 else 0
        hitk += 1 if rank else 0
        flag = f'top{rank}' if rank else 'MISS'
        print(f'[{n:2d}] {flag:6s} {item["q"]}')
        print(f'      检索：{" / ".join(spots)}')

    print(f'\nRecall@1 = {hit1}/{len(questions)} = {hit1 / len(questions):.1%}')
    print(f'Recall@{args.topk} = {hitk}/{len(questions)} = {hitk / len(questions):.1%}')


if __name__ == '__main__':
    main()
