# Reverse 1999 Word Cloud

一个面向《重返未来：1999 / Reverse: 1999》的公开文本词云项目。它用可审计的数据源清单采集公开网页或 RSS 内容，经过中文分词、专用词典修正和停用词过滤后，生成可部署到 GitHub Pages 的词云仪表盘。

项目不追求“绕过平台限制爬全网”。更成熟、也更可持续的路径是：先建立稳定、合规、可复现的数据源池，再逐步扩展平台覆盖和分析维度。

## 当前能力

- 配置式采集公开网页或 RSS/Atom
- 输出结构化 JSONL 语料到 `data/corpus/`
- 内置《重返未来：1999》角色、系统、玩法词典
- 生成总词频、按来源词频、按平台词频
- 输出 GitHub Pages 仪表盘数据：`docs/data.json`
- 保留兼容词云数据：`docs/wordcloud.json`
- 输出静态 SVG：`docs/wordcloud.svg`
- GitHub Actions 可定时刷新

## 项目结构

```text
.
├── data/
│   ├── lexicon_zh.txt          # 游戏专用词典
│   ├── sample_corpus/          # 无真实采集数据时的演示语料
│   ├── sources.example.json    # 数据源配置示例
│   └── stopwords_zh.txt        # 停用词
├── docs/
│   ├── index.html              # GitHub Pages 仪表盘
│   ├── data.json               # 仪表盘主数据
│   ├── wordcloud.json          # 兼容词频数组
│   └── wordcloud.svg           # 静态词云
└── src/
    ├── collect.py              # 采集公开来源
    └── analyze.py              # 清洗、分词、统计、生成页面数据
```

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python src\analyze.py --sample-only
```

没有真实语料时，`analyze.py` 会读取 `data/sample_corpus/` 生成演示版词云。

## 配置真实数据源

复制示例文件：

```powershell
Copy-Item data\sources.example.json data\sources.json
```

配置格式：

```json
[
  {
    "name": "official-homepage",
    "type": "page",
    "url": "https://re.bluepoch.com/",
    "platform": "official",
    "tags": ["official", "homepage"],
    "enabled": true,
    "selector": "main"
  }
]
```

字段说明：

- `name`：来源名称
- `type`：`page` 或 `rss`
- `url`：公开可访问 URL
- `platform`：平台名，用于分组
- `tags`：来源标签
- `enabled`：是否采集
- `selector`：可选 CSS selector，用于只提取正文区域

运行采集和分析：

```powershell
python src\collect.py --delay 2
python src\analyze.py --limit 160
```

如果你只想刷新演示页：

```powershell
python src\analyze.py --sample-only --limit 160
```

## 数据源策略

优先级建议：

1. 官方公告、新闻页、官网页面
2. 媒体文章、评测、Wiki 页面
3. 支持 RSS/Atom 的社区或搜索结果
4. 明确允许公开访问和合理抓取的平台页面
5. 需要登录、验证码、绕过反爬或接口逆向的平台暂不纳入

关键词建议：

- 中文：`重返未来1999`、`重返未来`、`1999手游`
- 英文：`Reverse 1999`、`Reverse: 1999`
- 角色：维尔汀、十四行诗、槲寄生、苏芙比、红弩箭、星锑、牙仙、曲娘、伊索尔德、露西等
- 系统：心相、洞悉、共鸣、荒原、鬃毛邮报、深眠域、人工梦游等

## 合规边界

- 只采集公开内容
- 不绕过登录、验证码、付费墙或反爬限制
- 遵守 robots.txt、平台服务条款和合理访问频率
- 默认不提交原始采集数据，仓库只发布聚合统计结果
- 不把用户个人信息作为分析目标

## GitHub Pages

在仓库设置中启用：

1. 打开 **Settings** → **Pages**
2. Source 选择 **Deploy from a branch**
3. Branch 选择 `main`
4. Directory 选择 `/docs`

## 后续路线

- 增加真实公开数据源清单
- 增加角色别名和版本活动词典
- 加入按时间窗口的词频趋势
- 加入平台对比和角色热度榜
- 增加情绪词和战斗/剧情主题分类
- 将 `data/sources.json` 改为可在 GitHub Actions Secret 中注入

## License

MIT
