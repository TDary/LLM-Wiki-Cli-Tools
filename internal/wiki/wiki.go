package wiki

import (
	"fmt"
	"os"
	"path/filepath"
	"time"
)

const gitignoreContent = `# LLM Wiki — Gitignore
# =====================

# 系统文件
.DS_Store
Thumbs.db

# 编辑器
*.swp
*.swo
*~
.vscode/
.idea/

# 临时文件
*.tmp
*.bak
*.log

# Python（如果 wiki 中包含脚本）
__pycache__/
*.pyc
.venv/

# Node（如果 wiki 中包含编译工具）
node_modules/
`

const gitattributesContent = `# LLM Wiki — Gitattributes
# Normalize line endings to LF for cross-platform compatibility
*.md text eol=lf
*.sh text eol=lf
*.yml text eol=lf
*.yaml text eol=lf
`

func generateSCHEMA(name, domain string, git bool) string {
	mode := "启用"
	if !git {
		mode = "禁用（纯本地模式）"
	}
	return fmt.Sprintf(`# SCHEMA — %s

> 知识库领域配置 · 自动生成的索引和关系

## 基本信息

| 属性 | 值 |
|------|-----|
| **名称** | %s |
| **领域** | %s |
| **Git 同步** | %s |
| **创建时间** | %s |
| **初始化工具** | wiki-tools |

## 目录说明

| 目录 | 用途 |
|------|------|
| `+"`raw/`"+` | 原始资料、外部引用、数据文件 |
| `+"`entities/`"+` | 实体页面（人、项目、工具等） |
| `+"`concepts/`"+` | 概念、术语、方法论 |
| `+"`relations/`"+` | 关系描述、交叉引用 |
| `+"`queries/`"+` | 查询模板、搜索索引 |
| `+"`drafts/`"+` | 草稿、临时笔记 |

## 标签体系

<!-- 可自定义标签，用于分类和检索 -->
`+"```yaml\n"+`tags:
  - type: tech
    label: 技术
  - type: process
    label: 流程
  - type: reference
    label: 参考
`+"```"+`

## 关系类型

<!-- 可自定义实体间关系 -->
`+"```yaml\n"+`relations:
  - depends_on: 依赖
  - references: 引用
  - implements: 实现
  - owned_by: 归属
`+"```"+`
`, name, name, domain, mode, time.Now().Format("2006-01-02 15:04:05"))
}

func generateREADME(name, domain string) string {
	return fmt.Sprintf(`# %s

> %s

## 快速导航

- 📋 [SCHEMA](./SCHEMA.md) — 知识库配置与目录说明
- 📝 [原始资料](./raw/) — 外部引用与数据文件
- 🧩 [实体](./entities/) — 人、项目、工具等
- 💡 [概念](./concepts/) — 术语与方法论
- 🔗 [关系](./relations/) — 交叉引用
- 🔍 [查询](./queries/) — 搜索索引
- ✏️ [草稿](./drafts/) — 临时笔记

## 更新日志

参见 [log.md](./log.md)
`, name, domain)
}

func generateLog() string {
	return fmt.Sprintf(`# 更新日志

## %s

- 🎉 知识库初始化完成
`, time.Now().Format("2006-01-02"))
}

// Dirs is the list of wiki subdirectories.
var Dirs = []string{"raw", "entities", "concepts", "relations", "queries", "drafts"}

// WriteFiles creates the wiki directory structure and skeleton files.
func WriteFiles(path, name, domain string, force, git bool) error {
	for _, dir := range Dirs {
		dirPath := filepath.Join(path, dir)
		if err := os.MkdirAll(dirPath, 0755); err != nil {
			return fmt.Errorf("创建目录 %s: %w", dir, err)
		}
		entries, _ := os.ReadDir(dirPath)
		if len(entries) == 0 {
			f, err := os.Create(filepath.Join(dirPath, ".gitkeep"))
			if err != nil {
				return fmt.Errorf("创建 .gitkeep: %w", err)
			}
			f.Close()
		}
	}

	fmt.Println("📁 目录结构已创建:")
	for _, dir := range Dirs {
		fmt.Printf("   %s/\n", dir)
	}

	// .gitignore
	giPath := filepath.Join(path, ".gitignore")
	if force || !FileExists(giPath) {
		if err := os.WriteFile(giPath, []byte(gitignoreContent), 0644); err != nil {
			return fmt.Errorf("写入 .gitignore: %w", err)
		}
		fmt.Printf("📄 %s/.gitignore\n", name)
	}

	// .gitattributes
	gaPath := filepath.Join(path, ".gitattributes")
	if force || !FileExists(gaPath) {
		if err := os.WriteFile(gaPath, []byte(gitattributesContent), 0644); err != nil {
			return fmt.Errorf("写入 .gitattributes: %w", err)
		}
		fmt.Printf("📄 %s/.gitattributes\n", name)
	}

	// SCHEMA.md
	schemaPath := filepath.Join(path, "SCHEMA.md")
	if force || !FileExists(schemaPath) {
		if err := os.WriteFile(schemaPath, []byte(generateSCHEMA(name, domain, git)), 0644); err != nil {
			return fmt.Errorf("写入 SCHEMA.md: %w", err)
		}
		fmt.Printf("📄 %s/SCHEMA.md\n", name)
	}

	// README.md
	readmePath := filepath.Join(path, "README.md")
	if force || !FileExists(readmePath) {
		if err := os.WriteFile(readmePath, []byte(generateREADME(name, domain)), 0644); err != nil {
			return fmt.Errorf("写入 README.md: %w", err)
		}
		fmt.Printf("📄 %s/README.md\n", name)
	}

	// log.md
	logPath := filepath.Join(path, "log.md")
	if force || !FileExists(logPath) {
		if err := os.WriteFile(logPath, []byte(generateLog()), 0644); err != nil {
			return fmt.Errorf("写入 log.md: %w", err)
		}
		fmt.Printf("📄 %s/log.md\n", name)
	}

	return nil
}

// FileExists checks whether a file exists.
func FileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}
