# AI 应用项目

电子信息科学与技术本科在读（2027 届），自学 Python 一年。这里是两个从零写起、都跑过真实数据的 AI 应用项目：一个 LLM 应用，一个可被 Agent 直接调用的 Skill。

| 目录 | 项目 | 技术栈 | 关键结果 |
|---|---|---|---|
| [AI穷游攻略生成器](./AI穷游攻略生成器) | 采集高德 POI，GLM 分批生成门票与攻略，Flask 渲染结果页 | Python / Flask / 高德 API / GLM-4-Flash | 5 城 192 景点，40 批调用成功率 100%，成本 0 元 |
| [考研择校分析Skill](./考研择校分析Skill) | 把考研择校 AI 分析封装为标准 Agent Skill，5780 条本地录取数据 | Python / requests / GLM-4-Flash / Agent Skill | ±10 分三档分桶，模型输出代码级校验兜底 |

## 想快速看什么

- 大模型调用怎么做容错 → [AI穷游攻略生成器/README.md](./AI穷游攻略生成器/README.md)（三级容错：重试 → 字段校验 → 整批降级）
- 模型输出怎么校验 → [考研择校分析Skill/README.md](./考研择校分析Skill/README.md)（推荐项必须来自对应分档，否则剔除补齐）
- Skill 长什么样 → [SKILL.md](./考研择校分析Skill/SKILL.md)（触发条件 + 使用步骤 + 注意事项）
- 核心脚本 → [data_collect.py](./AI穷游攻略生成器/data_collect.py) / [analyze.py](./考研择校分析Skill/scripts/analyze.py)

## 说明

- 两个项目的 API Key 均从环境变量读取（`gaode_API` / `GLM_API`），代码中不含密钥。
- 数据与采集类项目在另一个仓库：[maileji21/maileji.io](https://github.com/maileji21/maileji.io)

## 联系方式

- 邮箱：2634464770@qq.com
- GitHub：[@maileji21](https://github.com/maileji21)
