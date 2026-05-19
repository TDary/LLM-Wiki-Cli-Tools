package cmd

import (
	"fmt"
	"os"
	"path/filepath"
	"time"
)

// Version is the tool version.
const Version = "1.1.0"

// Commands maps command names to handlers.
var Commands = map[string]func([]string){}

// Register adds a command handler.
func Register(name string, handler func([]string)) {
	Commands[name] = handler
}

// AbsPath resolves a path, expanding ~ and making it absolute.
func AbsPath(p string) (string, error) {
	if p == "" || p == "." {
		return os.Getwd()
	}
	if p[0] == '~' {
		home, err := os.UserHomeDir()
		if err != nil {
			return "", err
		}
		p = filepath.Join(home, p[1:])
	}
	return filepath.Abs(p)
}

// FirstNonEmpty returns the first non-empty string.
func FirstNonEmpty(values ...string) string {
	for _, v := range values {
		if v != "" {
			return v
		}
	}
	return ""
}

// Timestamp returns the current timestamp string.
func Timestamp() string {
	return time.Now().Format("2006-01-02 15:04:05")
}

// PrintUsage prints the global help text.
func PrintUsage() {
	fmt.Printf(`wiki-tools v%s — 本地知识库管理工具集

用法:
  wiki-tools <command> [args...]

命令:
  init        初始化 wiki 目录结构
  sync        自动 commit + push
  bootstrap   一键安装（clone + init + config + sync）
  serve       启动定时同步守护进程
  list        列举所有知识文档
  search      全文搜索文档
  backlinks   查看页面的反向链接
  orphans     检测孤立文档
  health      知识库健康检查
  trace       溯源追踪文档上下游引用链
  fix         结构层自愈检查与修复
  index       生成结构化 JSON 索引
  rename      重命名文档并更新所有引用
  tags        列出所有标签及使用统计
  stats       知识库统计概览

全局选项:
  -h, --help     显示帮助
  -v, --version  显示版本

示例:
  wiki-tools init ~/team-wiki "团队共享知识库"
  wiki-tools list ~/team-wiki --tags Unity,performance
  wiki-tools search "关键词" ~/team-wiki
  wiki-tools search "pattern" ~/team-wiki --regex
  wiki-tools backlinks unity-ugui ~/team-wiki
  wiki-tools health ~/team-wiki
  wiki-tools fix ~/team-wiki --apply
  wiki-tools fix ~/team-wiki --apply --interactive
  wiki-tools trace draw-call-optimization ~/team-wiki
  wiki-tools index ~/team-wiki --pretty
  wiki-tools rename old-page new-page ~/team-wiki --dry-run
  wiki-tools tags ~/team-wiki --sort count
  wiki-tools stats ~/team-wiki

获取子命令帮助:
  wiki-tools <command> --help
`, Version)
}
