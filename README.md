# wiki-tools — 团队知识库一键安装 & 自动同步工具集

> Go 单文件静态二进制 · 零运行时依赖 · Windows / macOS / Linux 全平台

---

## 安装

从 `dist/` 目录下载对应平台的二进制，放到 PATH 中即可：

```bash
# Windows
copy wiki-tools.exe C:\Users\<user>\bin\

# macOS / Linux
cp wiki-tools /usr/local/bin/
chmod +x /usr/local/bin/wiki-tools
```

## 快速开始

### 一键安装团队知识库

```bash
wiki-tools bootstrap git@your-git-server.com:team/wiki.git ~/team-wiki \
  --domain "团队共享知识库" \
  --committer "你的Agent名字" \
  --committer-email "agent@local" \
  --token "your-access-token" \
  --sync-interval 10
```

**这条命令会做什么？**

| 步骤 | 动作 |
|------|------|
| clone | 克隆远程 Git 仓库到本地 |
| init | 初始化知识库目录结构（raw/ entities/ concepts/ 等） |
| config | 配置 Git remote、committer 身份、credential store |
| sync | 执行首次同步，提交并推送到远程 |
| serve | 提示启动定时同步守护进程 |

完成后知识库目录结构：

```
~/team-wiki/
├── SCHEMA.md          # 领域配置、标签体系、目录说明
├── README.md          # 导航首页
├── log.md             # 操作日志
├── raw/               # 原始资料（不可修改）
├── entities/          # 实体页面（人、项目、工具等）
├── concepts/          # 概念、术语、方法论
├── relations/         # 交叉引用
├── queries/           # 查询模板与结果
└── drafts/            # 草稿与临时笔记
```

---

## 命令详解

### `init` — 初始化知识库目录结构

```bash
wiki-tools init [WIKI_PATH] [DOMAIN] [OPTIONS]
```

| 选项 | 说明 |
|------|------|
| `--no-git` | 不初始化 Git 仓库 |
| `--force` | 覆盖已存在的文件 |
| `--name NAME` | 项目名（默认取目录名） |

不传路径默认 `~/wiki`，不传领域默认 `Wiki 知识库`。

### `sync` — 自动提交 + 推送

```bash
wiki-tools sync [REPO_PATH] [OPTIONS]
```

无参数时同步当前目录。对仓库内容不做任何假设，任何 Git 仓库通用。

| 选项 | 说明 |
|------|------|
| `--rebase` | 推送前先 `git pull --rebase` |
| `--dry-run` | 仅预览不执行 |
| `--name NAME` | 提交者名字（env: `GIT_SYNC_NAME`） |
| `--email E` | 提交者邮箱（env: `GIT_SYNC_EMAIL`） |
| `--branch B` | 推送目标分支（env: `GIT_SYNC_BRANCH`） |
| `--message M` | commit message 模板，支持 `{timestamp}` |
| `--force-push` | 推送失败时尝试 `--force-with-lease` |

**退出码：**

| 码 | 含义 |
|----|------|
| 0 | 成功同步 或 无修改无需同步 |
| 1 | 不是 Git 仓库 |
| 2 | 推送失败 |
| 3 | 路径不存在 |

### `bootstrap` — 一键安装（核心入口）

```bash
wiki-tools bootstrap [REMOTE_URL] [LOCAL_PATH] [OPTIONS]
```

不传 URL 时自动切换为纯本地模式。

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `--name NAME` | 路径 basename | 项目名 |
| `--domain DOMAIN` | `LLM Wiki 知识库` | 领域描述 |
| `--sync-interval N` | `10` | 自动同步间隔（分钟），`0` = 不启动 serve |
| `--committer NAME` | `AI Assistant` | 提交者名字 |
| `--committer-email E` | `ai@local` | 提交者邮箱 |
| `--no-serve` | — | 不启动守护进程 |
| `--no-clone` | — | 跳过 clone，对已有目录配置 |
| `--force` | — | 覆盖已存在的 SCHEMA.md |
| `--token TOKEN` | — | Git 访问令牌，自动写入 `~/.git-credentials` |
| `--local` | — | 纯本地模式（无 URL 时自动启用） |
| `--dry-run` | — | 预览模式 |

### `serve` — 定时同步守护进程

```bash
wiki-tools serve <WIKI_PATH> [OPTIONS]
```

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `--interval N` | `10` | 同步间隔（分钟） |
| `--name NAME` | `AI Assistant` | 提交者名字 |
| `--email E` | `ai@local` | 提交者邮箱 |

使用内置 `time.Ticker` 定时触发同步，不依赖 cron / 任务计划程序。首次启动立即执行一次同步，Ctrl+C 优雅退出。

### `list` — 列举知识文档

```bash
wiki-tools list [WIKI_PATH] [OPTIONS]
```

| 选项 | 说明 |
|------|------|
| `--format table\|json` | 输出格式（默认 table） |
| `--category CAT` | 过滤指定目录 |
| `--tags TAG1,TAG2` | 按标签过滤（逗号分隔） |
| `--include-raw` | 包含原始资料目录（默认排除） |
| `--pretty` | JSON 缩进美化 |

`raw/` 目录默认排除，因为原始资料是不可修改的。使用 `--include-raw` 可显示。

### `search` — 全文搜索

```bash
wiki-tools search <KEYWORD> [WIKI_PATH] [OPTIONS]
```

| 选项 | 说明 |
|------|------|
| `--format table\|json` | 输出格式（默认 table） |
| `--no-raw` | 排除 raw/ 目录 |
| `--pretty` | JSON 缩进美化 |

大小写不敏感子串匹配，搜索标题和正文内容，返回匹配行及行号。

### `backlinks` — 反向链接

```bash
wiki-tools backlinks <PAGE> [WIKI_PATH] [OPTIONS]
```

查找所有通过 `[[wikilinks]]` 引用指定页面的文档。`<page>` 可以是文件名（如 `transformer-architecture`）或完整路径。

### `orphans` — 孤立检测

```bash
wiki-tools orphans [WIKI_PATH] [OPTIONS]
```

检测入度为 0 的文档——没有任何其他文档通过 `[[wikilinks]]` 引用它们。排除 `SCHEMA.md`、`README.md`、`log.md` 等系统文件。

### `health` — 健康检查

```bash
wiki-tools health [WIKI_PATH] [OPTIONS]
```

综合健康评分（0-100），检查项：

| 检查项 | 扣分规则 |
|--------|----------|
| 孤立文档 | 每篇 -3 分 |
| 断链 | 每处 -5 分 |
| 无标签文档 | 每篇 -1 分 |
| 链接不足（< 2 条） | 每篇 -2 分 |
| 空文档（< 50 字节） | 每篇 -2 分 |
| 自引用链接 | 每处 -1 分 |

### `trace` — 溯源追踪

```bash
wiki-tools trace <PAGE> [WIKI_PATH] [OPTIONS]
```

递归追踪文档的上下游引用链：

- **上游**：该页面引用了哪些页面（直接 + 传递）
- **下游**：哪些页面引用了该页面（直接 + 传递）

支持环检测（已访问节点跳过），最大深度 10 层。

### `fix` — 结构层自愈

```bash
wiki-tools fix [WIKI_PATH] [--apply] [OPTIONS]
```

| 检查项 | 自动修复 |
|--------|----------|
| 断链 | 匹配最近似页面名，建议替换 |
| 命名不规范 | 下划线 → 连字符（`[[unity_ugui]]` → `[[unity-ugui]]`） |

默认 dry-run 预览模式，加 `--apply` 执行修复。

### `index` — 生成 JSON 索引

```bash
wiki-tools index [WIKI_PATH] [--output FILE] [--pretty]
```

输出结构化 JSON 索引（默认 `queries/index.json`），供前端页面消费。

---

## 环境变量

`sync` 命令支持环境变量（CLI flag 优先级更高）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `GIT_SYNC_NAME` | `AI Assistant` | 提交者名字 |
| `GIT_SYNC_EMAIL` | `ai@local` | 提交者邮箱 |
| `GIT_SYNC_BRANCH` | 当前分支 | 推送目标分支 |
| `GIT_SYNC_MESSAGE` | `auto sync: {timestamp}` | commit message 模板 |
| `GIT_SYNC_DRY_RUN` | `0` | 设为 `1` 仅预览不执行 |
| `GIT_SYNC_FORCE_PUSH` | `0` | 设为 `1` 推送失败时尝试 force-with-lease |

---

## 编译

```bash
# 当前平台（完整版，含 Git 支持）
go build -o wiki-tools .

# 当前平台（纯本地版，无 Git 依赖）
go build -tags localonly -o wiki-tools-local .

# 全平台交叉编译
GOOS=windows GOARCH=amd64 go build -o dist/wiki-tools-windows-amd64.exe .
GOOS=linux   GOARCH=amd64 go build -o dist/wiki-tools-linux-amd64 .
GOOS=linux   GOARCH=arm64 go build -o dist/wiki-tools-linux-arm64 .
GOOS=darwin  GOARCH=amd64 go build -o dist/wiki-tools-darwin-amd64 .
GOOS=darwin  GOARCH=arm64 go build -o dist/wiki-tools-darwin-arm64 .
```

---

## 工程结构

```text
wiki-tools/
├── main.go                    # 入口 + 命令路由
├── go.mod
├── internal/
│   ├── cmd/                   # 命令实现（每个命令一个文件）
│   │   ├── cmd.go             # 版本、注册、公共工具函数
│   │   ├── init.go            # init 命令
│   │   ├── init_git.go        # init 的 Git 扩展（!localonly）
│   │   ├── sync.go            # sync 命令（!localonly）
│   │   ├── bootstrap.go       # bootstrap 命令
│   │   ├── bootstrap_git.go   # bootstrap 的 Git 扩展（!localonly）
│   │   ├── serve.go           # serve 守护进程（!localonly）
│   │   ├── list.go            # list 命令
│   │   ├── search.go          # search 命令
│   │   ├── backlinks.go       # backlinks 命令
│   │   ├── orphans.go         # orphans 命令
│   │   ├── health.go          # health 命令
│   │   ├── trace.go           # trace 命令
│   │   ├── fix.go             # fix 命令
│   │   └── index.go           # index 命令
│   ├── git/
│   │   └── git.go             # Git 操作封装（!localonly）
│   └── wiki/
│       ├── wiki.go            # 目录结构 + 模板生成
│       └── query.go           # 文档查询、反向链接、搜索、溯源
├── platform-adapters/
│   ├── CLAUDE.md              # Claude Code 适配配置
│   └── AGENTS.md              # OpenClaw / Cursor / Copilot 适配
├── build/
│   ├── local-wiki-skill/      # 纯本地版（Python，零依赖）
│   └── wiki-skill-v1.0.5/     # 完整版（Go 二进制 + 安装脚本）
├── dist/                      # 跨平台预编译二进制（10 个）
└── README.md
```

**构建变体：**

- `go build .` — 完整版（含 Git 支持）
- `go build -tags localonly .` — 纯本地版（无 Git 依赖）

带 `!localonly` 标签的文件仅在完整版中编译。

---

## 文件规范

- 文件名：小写 + 连字符（`transformer-architecture.md`）
- 目录名：小写单复数（`entities/`, `concepts/`）
- 内部引用使用 `[[wikilinks]]` 语法
- 每个页面至少链接到 2 个其他页面
- 每次操作后追加 `log.md`

---

## 安全说明

- 不硬编码任何凭据。Git 认证通过系统级 credential store。
- 所有代码可审计：纯 Go 标准库，无外部依赖。
- 单文件静态二进制，无运行时依赖。

---

## License

MIT
