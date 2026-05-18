package main

import (
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func serveCmd(args []string) {
	flags := flag.NewFlagSet("serve", flag.ExitOnError)
	interval := flags.Int("interval", 10, "同步间隔（分钟）")
	name := flags.String("name", "", "提交者名字")
	email := flags.String("email", "", "提交者邮箱")
	flags.Usage = func() {
		fmt.Println("用法: wiki-tools serve <WIKI_PATH> [OPTIONS]")
		fmt.Println()
		fmt.Println("  启动定时同步守护进程。")
		fmt.Println()
		fmt.Println("选项:")
		flags.PrintDefaults()
		fmt.Println()
		fmt.Println("示例:")
		fmt.Println("  wiki-tools serve ~/team-wiki")
		fmt.Println("  wiki-tools serve ~/team-wiki --interval 30")
	}
	flags.Parse(args)

	if flags.NArg() < 1 {
		fmt.Fprintln(os.Stderr, "❌ 缺少 WIKI_PATH 参数")
		flags.Usage()
		os.Exit(1)
	}

	wikiPath := flags.Arg(0)
	if wikiPath[0] == '~' {
		home, _ := os.UserHomeDir()
		wikiPath = home + wikiPath[1:]
	}

	wikiPath, err := absPath(wikiPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "❌ 路径解析失败: %v\n", err)
		os.Exit(3)
	}

	if !isGitRepo(wikiPath) {
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

	// 首次立即同步
	fmt.Printf("[%s] 执行首次同步...\n", timestamp())
	if err := runSync(syncParams{
		repoPath:       wikiPath,
		committerName:  committerName,
		committerEmail: committerEmail,
		dryRun:         false,
		forcePush:      false,
		rebase:         false,
	}); err != nil {
		fmt.Printf("   ⚠️  同步出错: %v\n", err)
	}

	// 定时器
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
				dryRun:         false,
				forcePush:      false,
				rebase:         false,
			}); err != nil {
				fmt.Printf("   ⚠️  同步出错: %v\n", err)
			}
		case sig := <-sigCh:
			fmt.Printf("\n[%s] 收到 %v 信号，正在停止守护进程...\n", timestamp(), sig)
			return
		}
	}
}
