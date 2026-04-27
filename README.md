# Reverse 1999 Word Cloud

一个用于搜集公开网页中《重返未来：1999》相关讨论，并生成中文词云的项目。

项目目标不是“无限制爬全网”，而是用可维护、可审计的数据源列表持续采集公开内容，清洗后输出可发布的词云页面。默认结果会生成到 `docs/`，方便启用 GitHub Pages。

## 功能

- 从 `data/sources.json` 中配置的网页或 RSS 源采集文本
- 对中文内容进行清洗、停用词过滤和分词
- 输出词频数据：`docs/wordcloud.json`
- 输出静态展示页：`docs/index.html`
- 支持 GitHub Actions 定时刷新

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item data\sources.example.json data\sources.json
python src\collect.py
python src\analyze.py
```

然后打开 `docs/index.html` 查看词云。

## 数据源配置

复制示例文件：

```powershell
Copy-Item data\sources.example.json data\sources.json
```

`data/sources.json` 的格式：

```json
[
  {
    "name": "example",
    "type": "page",
    "url": "https://example.com/search?q=重返未来1999"
  }
]
```

支持类型：

- `page`：普通网页
- `rss`：RSS/Atom 订阅源

请优先使用官方、媒体、社区搜索页、RSS 或明确允许抓取的数据接口，并遵守目标站点的 robots.txt、服务条款和访问频率限制。

## 生成物

- `data/raw/`：采集到的原始文本，默认不提交
- `data/metadata.jsonl`：采集元数据，默认不提交
- `docs/wordcloud.json`：词云词频数据
- `docs/wordcloud.svg`：静态词云图
- `docs/index.html`：GitHub Pages 展示页

## GitHub Pages

仓库推送后，在 GitHub 仓库设置里：

1. 打开 **Settings** → **Pages**
2. Source 选择 **Deploy from a branch**
3. Branch 选择 `main`，目录选择 `/docs`

## 许可证

MIT
