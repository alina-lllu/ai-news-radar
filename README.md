# ai-news-radar

每日自动抓取 AI 相关新闻，聚合多源 RSS，可选 LLM 摘要，输出日报供人工筛选后发布到 juya-ai-daily。

## 工作流

```
每日定时（北京 6:00）
    ↓
从 15+ RSS 源抓取 AI 新闻
    ↓
去重 & 过滤（关键词匹配）
    ↓
[可选] LLM 精选摘要（8-15 条）
    ↓
输出 Markdown 日报 + 发布为 Issue
    ↓
人工浏览筛选 → 编辑为早报 → 发布到 juya-ai-daily
```

## 新闻源

覆盖国内外主要 AI 媒体，详见 `sources/feeds.yaml`：
- 国际：TechCrunch、The Verge、Ars Technica、MIT Technology Review、VentureBeat
- 官方：OpenAI Blog、Google AI Blog
- 开源：Hugging Face Blog
- 社区：Hacker News（AI 相关）
- 中文：机器之心、量子位、36氪
- 学术：arXiv cs.AI、arXiv cs.CL

## 快速开始

### 本地运行

```bash
pip install -r requirements.txt

# 基础模式：抓取并输出 Markdown
python radar.py

# LLM 摘要模式（需配置环境变量）
export LLM_API_KEY=your-key
export LLM_API_BASE_URL=https://api.openai.com/v1
export LLM_MODEL=gpt-4o-mini
python radar.py --summarize

# 发布为 GitHub Issue
export G_T=your-github-token
python radar.py --summarize --publish --repo alina-lllu/ai-news-radar
```

### GitHub Actions 自动运行

部署到 GitHub 后，需配置以下 Secrets：
- `G_T`：GitHub Personal Access Token
- `LLM_API_KEY`：LLM API 密钥
- `LLM_API_BASE_URL`：LLM API 地址
- `LLM_MODEL`：模型名称

Actions 每天北京时间 6:00 自动运行，结果发布为 Issue 并存档到 `output/`。

## 命令参数

| 参数 | 说明 |
| :--- | :--- |
| `--summarize` | 启用 LLM 摘要精选 |
| `--publish` | 发布为 GitHub Issue |
| `--repo OWNER/REPO` | 指定发布目标仓库 |
| `--hours N` | 抓取最近 N 小时的新闻（默认 48） |

## 与 juya-ai-daily 的协作

1. ai-news-radar 每天自动抓取并生成新闻聚合
2. 你浏览 Issue 或 `output/` 中的日报
3. 从中筛选有价值的内容，编辑整理成早报
4. 发布到 juya-ai-daily 的 Issue → 自动生成 RSS 和站点
