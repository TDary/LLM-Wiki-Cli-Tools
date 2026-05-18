//go:build !localonly

package main

import (
	"flag"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"wiki-tools/internal/git"
)

func init() { commands["serve"] = serveCmd }

func serveCmd(args []string) {
	for _, a := range args {
		switch a {
		case "-h", "--help":
			printServeHelp()
			os.Exit(0)
		case "--version":
			fmt.Println("wiki-tools v" + version)
			os.Exit(0)
		}
	}

	flags := flag.NewFlagSet("serve", flag.ExitOnError)
	interval := flags.Int("interval", 10, "同步间隔（分钟）")
	name := flags.String("name", "", "提交者名字")
	email := flags.String("email", "", "提交者邮箱")
	flags.Usage = printServeHelp
	flags.Parse(args)

	if flags.NArg() < 1 {
		fmt.Fprintln(os.Stderr, "❌ 缺少 WIKI_PATH 参数")
		flags.Usage()
		os.Exit(1)
	}

	wikiPath := flags.Arg(0)
	if wikiPath[0] == '~' {
		home, err := os.UserHomeDir()
		if err != nil {
			fmt.Fprintf(os.Stderr, "cannot determine home directory: %v\n", err)
			os.Exit(1)
		}
		wikiPath = filepath.Join(home, wikiPath[1:])
	}

	var err error
	wikiPath, err = absPath(wikiPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "❌ 路径解析失败: %v\n", err)
		os.Exit(3)
	}

	if *interval <= 0 {
		fmt.Fprintln(os.Stderr, "❌ --interval 必须大于 0")
		os.Exit(1)
	}

	if !git.IsRepo(wikiPath) {
		fmt.Fprintf(os.Stderr, "❌ 不是 Git 仓库: %s\n", wikiPath)
		os.Exit(1)
	}

	committerName := firstNonEmpty(*name, os.Getenv("GIT_SYNC_NAME"), "AI Assistant")
	committerEmail := firstNonEmpty(*email, os.Getenv("GIT_SYNC_EMAIL"), "ai@local")

	duration := time.Duration(*interval) * time.Minute
	fmt.Printf("⏰ 定时同步守护进程已启动\n")
	fmt.Printf("   Wiki:     %s\n", wikiPath)
	fmt.Printf("   间隔:     每 %d 分钟\n", *interval)
	fmt.Printf("   提交者:   %s <%s>\n", committerName, committerEmail)
	fmt.Printf("   按 Ctrl+C 停止\n")
	fmt.Println()

	fmt.Printf("[%s] 执行首次同步...\n", timestamp())
	if err := runSync(syncParams{
		repoPath:       wikiPath,
		committerName:  committerName,
		committerEmail: committerEmail,
	}); err != nil {
		fmt.Printf("   ⚠️  同步出错: %v\n", err)
	}

	ticker := time.NewTicker(duration)
	defer ticker.Stop()

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	for {
		select {
		case <-ticker.C:
			fmt.Printf("[%s] 执行定时同步...\n", timestamp())
			if err := runSync(syncParams{
				repoPath:       wikiPath,
				committerName:  committerName,
				committerEmail: committerEmail,
			}); err != nil {
				fmt.Printf("   ⚠️  同步出错: %v\n", err)
			}
		case sig := <-sigCh:
			fmt.Printf("\n[%s] 收到 %v 信号，正在停止守护进程...\n", timestamp(), sig)
			return
		}
	}
}

func printServeHelp() {
	fmt.Println("用法: wiki-tools serve <WIKI_PATH> [OPTIONS]")
	fmt.Println()
	fmt.Println("  启动定时同步守护进程。选项可放在路径前后。")
	fmt.Println()
	fmt.Println("选项:")
	fmt.Println("  --interval N  同步间隔（分钟，默认 10）")
	fmt.Println("  --name NAME   提交者名字（默认 \"AI Assistant\"）")
	fmt.Println("  --email E     提交者邮箱（默认 \"ai@local\"）")
	fmt.Println("  -h, --help    显示帮助")
	fmt.Println("  --version     显示版本")
	fmt.Println()
	fmt.Println("示例:")
	fmt.Println("  wiki-tools serve ~/team-wiki")
	fmt.Println("  wiki-tools serve --interval 30 ~/team-wiki")
}
