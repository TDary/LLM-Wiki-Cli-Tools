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

示例：

```bash
# Git 协作模式（传远程仓库 URL）
wiki-tools bootstrap git@your-server.com:team/wiki.git ~/team-wiki

# 纯本地模式（不传 URL 自动启用）
wiki-tools bootstrap ~/my-wiki --domain "个人知识库"
```

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

### `init` — 初始化知识库目录结构

```bash
wiki-tools init <WIKI_PATH> <DOMAIN> [OPTIONS]
```

| 选项 | 说明 |
|------|------|
| `--no-git` | 不初始化 Git 仓库 |
| `--force` | 覆盖已存在的文件 |
| `--name NAME` | 项目名（默认取目录名） |

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

## 从旧版 Bash 脚本迁移

| Bash 版 | Go 版 |
|---|---|
| `git-auto-sync <path>` | `wiki-tools sync [path]` |
| `wiki-init <path> <domain>` | `wiki-tools init <path> <domain>` |
| `wiki-bootstrap <url> [path]` | `wiki-tools bootstrap <url> [path]` |
| cron / crontab 定时同步 | `wiki-tools serve <path> --interval N` |

---

## 编译

```bash
# 当前平台
go build -o wiki-tools .

# 全平台
GOOS=windows GOARCH=amd64 go build -o wiki-tools.exe .
GOOS=linux   GOARCH=amd64 go build -o dist/wiki-tools-linux .
GOOS=darwin  GOARCH=amd64 go build -o dist/wiki-tools-darwin-amd64 .
GOOS=darwin  GOARCH=arm64 go build -o dist/wiki-tools-darwin-arm64 .
```

---

## 工程结构

```text
wiki-cli-tools/
├── main.go                    # 入口 + 命令路由
├── go.mod
├── init.go                    # init 命令
├── sync.go                    # sync 命令 + 同步核心逻辑
├── bootstrap.go               # bootstrap 命令
├── serve.go                   # serve 守护进程
├── internal/
│   ├── git/
│   │   └── git.go             # Git 操作封装
│   └── wiki/
│       └── wiki.go            # Wiki 内容生成器
├── platform-adapters/
│   ├── CLAUDE.md              # Claude Code 适配配置
│   └── AGENTS.md              # OpenClaw / Cursor / Copilot 适配
├── dist/                      # 跨平台预编译二进制
└── README.md
```

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
