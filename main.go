package main

import (
	"fmt"
	"os"
	"path/filepath"
	"time"
)

const version = "0.2.0"

var commands = map[string]func([]string){}

func main() {
	if len(os.Args) < 2 {
		printUsage()
		os.Exit(0)
	}

	cmd := os.Args[1]

	switch cmd {
	case "-h", "--help":
		printUsage()
		os.Exit(0)
	case "-v", "--version":
		fmt.Printf("wiki-tools v%s\n", version)
		os.Exit(0)
	}

	handler, ok := commands[cmd]
	if !ok {
		fmt.Fprintf(os.Stderr, "❌ 未知命令: %s\n\n", cmd)
		printUsage()
		os.Exit(1)
	}
	handler(os.Args[2:])
}

func printUsage() {
	fmt.Printf(`wiki-tools v%s — 团队知识库一键安装 & 自动同步工具集

用法:
  wiki-tools <command> [args...]

命令:
  init       初始化 wiki 目录结构
  sync       自动 commit + push
  bootstrap  一键安装（clone + init + config + sync）
  serve      启动定时同步守护进程

全局选项:
  -h, --help     显示帮助
  -v, --version  显示版本

示例:
  wiki-tools init ~/team-wiki "团队共享知识库"
  wiki-tools sync ~/team-wiki
  wiki-tools sync ~/team-wiki --rebase --dry-run
  wiki-tools bootstrap git@gitlab.com:group/wiki.git ~/team-wiki
  wiki-tools bootstrap <url> --dry-run
  wiki-tools serve ~/team-wiki --interval 10

获取子命令帮助:
  wiki-tools <command> --help
`, version)
}

// helpers

func firstNonEmpty(values ...string) string {
	for _, v := range values {
		if v != "" {
			return v
		}
	}
	return ""
}

func timestamp() string {
	return time.Now().Format("2006-01-02 15:04:05")
}

func absPath(p string) (string, error) {
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
