# wiki-cli-tools — 团队知识库一键安装 & 自动同步工具集

> 纯 Bash · 零依赖 · 跨 AI 平台（Hermes / Claude / OpenClaw）· 仓库无关

---

## 📦 产物清单

```
wiki-cli-tools/
├── README.md                       # 👈 你正在看的文件
├── bin/
│   ├── git-auto-sync               # 通用 Git 自动提交+推送脚本
│   ├── wiki-init                   # 知识库目录结构初始化
│   └── wiki-bootstrap              # 一键安装（核心入口）
├── platform-adapters/
│   ├── CLAUDE.md                   # Claude Code 适配配置
│   └── AGENTS.md                   # OpenClaw / Cursor / Copilot 适配
└── examples/
    └── sync-team-wiki.sh           # 旧脚本迁移示例（薄封装）
```

---

## 🚀 快速开始

### 安装

```bash
# 复制 CLI 工具到 PATH
cp bin/* ~/.local/bin/
chmod +x ~/.local/bin/git-auto-sync ~/.local/bin/wiki-init ~/.local/bin/wiki-bootstrap

# 确保 ~/.local/bin 在 PATH 中
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### 一键安装团队知识库

```bash
wiki-bootstrap git@your-git-server.com:team/wiki.git ~/team-wiki \
  --name "team-wiki" \
  --domain "团队共享知识库" \
  --committer "你的Agent名字" \
  --committer-email "agent@local" \
  --token "your-access-token" \
  --sync-interval 10
```

**这条命令会做什么？**

| 步骤 | 动作 |
|------|------|
| ① clone | 克隆远程 Git 仓库到本地 `~/team-wiki/` |
| ② init | 初始化知识库目录结构（raw/ entities/ concepts/ 等） |
| ③ config | 配置 Git remote、committer 身份、credential store |
| ④ sync | 执行首次 git-auto-sync，提交并推送到远程 |
| ⑤ cron | 注册定时同步任务（默认每 10 分钟） |

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

## 🔧 CLI 工具详解

### `git-auto-sync` — 通用 Git 自动提交 + 推送

```bash
git-auto-sync [REPO_PATH]
```

**功能：** 检测 Git 变更 → 自动 `git add .` → commit → push。对仓库内容不做任何假设，任何 Git 仓库通用。

**环境变量：**

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `GIT_SYNC_NAME` | `AI Assistant` | 提交者名字 |
| `GIT_SYNC_EMAIL` | `ai@local` | 提交者邮箱 |
| `GIT_SYNC_BRANCH` | 当前分支 | 推送目标分支 |
| `GIT_SYNC_MESSAGE` | `auto sync: {timestamp}` | commit message 模板 |
| `GIT_SYNC_DRY_RUN` | `0` | 设为 `1` 仅预览不执行 |
| `GIT_SYNC_FORCE_PUSH` | `0` | 设为 `1` 推送失败时尝试 force-with-lease |

**示例：**

```bash
# 基础用法
git-auto-sync ~/team-wiki

# 自定义身份
GIT_SYNC_NAME="你的Agent" GIT_SYNC_EMAIL="agent@local" git-auto-sync ~/team-wiki

# 预览模式（不实际提交）
GIT_SYNC_DRY_RUN=1 git-auto-sync ~/team-wiki

# 自定义 commit message
GIT_SYNC_MESSAGE="chore: daily auto-sync at {timestamp}" git-auto-sync ~/project

# 应用到任意 Git 仓库
git-auto-sync ~/my-project
git-auto-sync ~/notes
```

**退出码：**

| 码 | 含义 |
|----|------|
| 0 | 成功同步 或 无修改无需同步 |
| 1 | 不是 Git 仓库 |
| 2 | 推送失败 |
| 3 | 路径不存在 |

---

### `wiki-init` — 初始化知识库目录结构

```bash
wiki-init <WIKI_PATH> <DOMAIN> [OPTIONS]
```

**功能：** 创建标准化的 LLM Wiki 目录结构和骨架文件（SCHEMA.md / README.md / log.md / .gitignore）。

**选项：**

| 选项 | 说明 |
|------|------|
| `--no-git` | 不初始化 Git 仓库 |
| `--force` | 覆盖已存在的 SCHEMA.md 等文件 |
| `--name NAME` | 项目名（默认取目录名） |

**示例：**

```bash
# 初始化团队知识库
wiki-init ~/team-wiki "团队共享知识库"

# 初始化个人知识库（不创建 Git）
wiki-init ~/my-wiki "个人知识库" --name my-wiki --no-git

# 强制重建结构
wiki-init ~/wiki "实验项目" --force
```

---

### `wiki-bootstrap` — 一键安装（核心入口）

```bash
wiki-bootstrap <REMOTE_URL> [LOCAL_PATH] [OPTIONS]
```

**功能：** 编排 clone + init + config + sync + cron 五个步骤，一条命令完成知识库从零到自动同步的全流程。

**选项：**

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `--name NAME` | 路径 basename | 项目名 |
| `--domain DOMAIN` | `LLM Wiki 知识库` | 领域描述 |
| `--sync-interval N` | `10` | 自动同步间隔（分钟），`0` = 不注册 |
| `--committer NAME` | `AI Assistant` | 提交者名字 |
| `--committer-email E` | `ai@local` | 提交者邮箱 |
| `--no-cron` | — | 不注册定时同步 |
| `--no-clone` | — | 跳过 clone，对已有目录配置 |
| `--force` | — | 覆盖已存在的 SCHEMA.md |
| `--token TOKEN` | — | Git 访问令牌，自动写入 `~/.git-credentials` |

**示例：**

```bash
# 最简用法（路径自动推断为 ~/仓库名）
wiki-bootstrap git@github.com:user/docs.git

# GitLab 团队 wiki
wiki-bootstrap git@gitlab.com:team/wiki.git ~/team-wiki

# 自定义同步间隔（30 分钟）
wiki-bootstrap https://gitee.com/org/repo.git ~/repo --sync-interval 30

# 纯手动模式（不注册 cron）
wiki-bootstrap git@gitlab.com:team/docs.git ~/docs --no-cron

# 已有本地目录，只补配置
wiki-bootstrap git@github.com:user/wiki.git ~/existing-dir --no-clone --force

# 带访问令牌（自动写入 ~/.git-credentials）
wiki-bootstrap https://gitlab.com/team/wiki.git ~/team-wiki --token "glpat-xxxx"
```

---

## 🌐 跨平台适配

### 三层架构

```
┌─────────────────────────────────────────────────┐
│  平台适配层                                       │
│  CLAUDE.md  ·  AGENTS.md  ·  hermes skills       │
│  （每个文件只有几十行，告诉 agent 如何调用 CLI）      │
├─────────────────────────────────────────────────┤
│  通用 CLI 工具层                                  │
│  git-auto-sync  ·  wiki-init  ·  wiki-bootstrap   │
│  （纯 Bash，安装在 ~/.local/bin/，零平台依赖）       │
├─────────────────────────────────────────────────┤
│  知识库本体                                       │
│  ~/team-wiki/ — 纯 Markdown，平台无关              │
└─────────────────────────────────────────────────┘
```

### 适配文件用法

**Claude Code：** 将 `CLAUDE.md` 放入知识库根目录，Claude 自动读取。

**OpenClaw / Cursor / Copilot：** 将 `AGENTS.md` 放入知识库根目录。

**Hermes Agent：** 无需额外配置，`git-auto-sync` 已内置在系统 skill 中。

适配文件内容极其简单，核心只有三行：

```markdown
## CLI Tools
- `git-auto-sync <path>` — 自动同步
- `wiki-init <path> <domain>` — 初始化
- `wiki-bootstrap <url> [path]` — 一键安装
```

**换平台成本 = 只换最上层一个几十行的配置文件。**

---

## 📋 文件规范

### 命名

- 文件名：小写 + 连字符（`transformer-architecture.md`）
- 目录名：小写单复数（`entities/`, `concepts/`）

### 引用

- 内部引用使用 `[[wikilinks]]` 语法
- 每个页面至少链接到 2 个其他页面

### 日志

- 每次操作后追加 `log.md`
- 格式：`- 🏷️ 操作描述 [时间]`

---

## 🔒 安全说明

- **不硬编码任何凭据。** Git 认证通过系统级 credential store，不在脚本内存储。
- 身份信息通过环境变量传入，默认值均为通用占位符。
- 所有脚本可审计：纯 Bash，无二进制，无混淆。

---

## ❓ 常见问题

**Q: 能用其他 Git 托管平台吗？**

A: 可以。GitHub / GitLab / Gitee / Gitea / 自建 Git 服务器，只要支持 `git clone` + `git push` 即可。

**Q: 换 AI 平台（Hermes → Claude）需要重新配置吗？**

A: 不需要。底层 CLI 和知识库数据完全不变，只需把 `CLAUDE.md` 或 `AGENTS.md` 放进仓库根目录。

**Q: 怎么停用定时同步？**

```bash
# 查看所有 cron
crontab -l

# 删除对应行（以 wiki-sync-cron 开头的脚本）
crontab -l | grep -v "wiki-sync-cron" | crontab -
```

**Q: 能同时管理多个知识库吗？**

```bash
wiki-bootstrap git@github.com:team/docs.git ~/docs --sync-interval 10
wiki-bootstrap git@github.com:me/notes.git ~/notes --sync-interval 30
# 两个仓库独立运行，互不干扰
```

---

## 📄 License

MIT — 随便用，随便改。