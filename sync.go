package main

import (
	"flag"
	"fmt"
	"os"
	"strings"

	"wiki-tools/internal/git"
)

type syncParams struct {
	repoPath                      string
	committerName, committerEmail string
	targetBranch, commitMsg       string
	dryRun, forcePush, rebase     bool
}

func syncCmd(args []string) {
	for _, a := range args {
		switch a {
		case "-h", "--help":
			printSyncHelp()
			os.Exit(0)
		case "--version":
			fmt.Println("wiki-tools v" + version)
			os.Exit(0)
		}
	}

	flags := flag.NewFlagSet("sync", flag.ExitOnError)
	rebase := flags.Bool("rebase", false, "推送前先 git pull --rebase")
	dryRun := flags.Bool("dry-run", false, "只检查不执行")
	name := flags.String("name", "", "提交者名字")
	email := flags.String("email", "", "提交者邮箱")
	branch := flags.String("branch", "", "推送目标分支")
	message := flags.String("message", "", "commit message 模板，支持 {timestamp} 占位符")
	forcePush := flags.Bool("force-push", false, "推送失败时尝试 --force-with-lease")
	flags.Usage = printSyncHelp
	flags.Parse(args)

	repoPath := "."
	if flags.NArg() > 0 {
		repoPath = flags.Arg(0)
	}

	var err error
	if repoPath, err = absPath(repoPath); err != nil {
		fmt.Fprintf(os.Stderr, "❌ git-auto-sync: 路径不存在或无权限 → %s\n", repoPath)
		os.Exit(3)
	}

	committerName := firstNonEmpty(*name, os.Getenv("GIT_SYNC_NAME"), "AI Assistant")
	committerEmail := firstNonEmpty(*email, os.Getenv("GIT_SYNC_EMAIL"), "ai@local")
	targetBranch := firstNonEmpty(*branch, os.Getenv("GIT_SYNC_BRANCH"), "")
	commitMsg := firstNonEmpty(*message, os.Getenv("GIT_SYNC_MESSAGE"), "")
	isDryRun := *dryRun || os.Getenv("GIT_SYNC_DRY_RUN") == "1"
	isForcePush := *forcePush || os.Getenv("GIT_SYNC_FORCE_PUSH") == "1"
	doRebase := *rebase

	if err := runSync(syncParams{
		repoPath:       repoPath,
		committerName:  committerName,
		committerEmail: committerEmail,
		targetBranch:   targetBranch,
		commitMsg:      commitMsg,
		dryRun:         isDryRun,
		forcePush:      isForcePush,
		rebase:         doRebase,
	}); err != nil {
		fmt.Fprintf(os.Stderr, "%v\n", err)
		if strings.Contains(err.Error(), "不是 Git 仓库") {
			os.Exit(1)
		}
		if strings.Contains(err.Error(), "推送失败") {
			os.Exit(2)
		}
		os.Exit(3)
	}
}

func runSync(p syncParams) error {
	if !git.IsRepo(p.repoPath) {
		return fmt.Errorf("❌ git-auto-sync: 不是 Git 仓库 → %s", p.repoPath)
	}

	status, err := git.StatusPorcelain(p.repoPath)
	if err != nil {
		return fmt.Errorf("❌ git-auto-sync: git status 失败: %w", err)
	}
	if status == "" {
		fmt.Printf("ℹ️  git-auto-sync: 无修改 [%s] — 跳过\n", p.repoPath)
		return nil
	}

	if p.dryRun {
		fmt.Printf("🔍 git-auto-sync: DRY RUN [%s]\n", p.repoPath)
		fmt.Println("   待提交文件：")
		for _, line := range strings.Split(status, "\n") {
			fmt.Printf("   %s\n", line)
		}
		branch := p.targetBranch
		if branch == "" {
			b, _ := git.CurrentBranch(p.repoPath)
			branch = b
		}
		msg := buildCommitMsg(p.commitMsg)
		fmt.Printf("   commit message: %s\n", msg)
		fmt.Printf("   branch: %s\n", branch)
		fmt.Printf("   author: %s <%s>\n", p.committerName, p.committerEmail)
		return nil
	}

	if err := git.SetConfig(p.repoPath, "user.name", p.committerName); err != nil {
		return fmt.Errorf("❌ git-auto-sync: 配置 user.name 失败: %w", err)
	}
	if err := git.SetConfig(p.repoPath, "user.email", p.committerEmail); err != nil {
		return fmt.Errorf("❌ git-auto-sync: 配置 user.email 失败: %w", err)
	}

	if err := git.Add(p.repoPath); err != nil {
		return fmt.Errorf("❌ git-auto-sync: git add 失败: %w", err)
	}

	msg := buildCommitMsg(p.commitMsg)
	committed, err := git.Commit(p.repoPath, msg)
	if err != nil {
		return fmt.Errorf("❌ git-auto-sync: git commit 失败: %w", err)
	}
	if !committed {
		fmt.Printf("⚠️  git-auto-sync: 提交无变化 [%s]\n", p.repoPath)
		return nil
	}

	shortHash, err := git.ShortHash(p.repoPath)
	if err != nil {
		shortHash = "?"
	}

	branch := p.targetBranch
	if branch == "" {
		branch, err = git.CurrentBranch(p.repoPath)
		if err != nil {
			return fmt.Errorf("❌ git-auto-sync: 无法确定当前分支: %w", err)
		}
	}
	currentBranch, _ := git.CurrentBranch(p.repoPath)
	if branch != currentBranch && currentBranch != "" {
		return fmt.Errorf("❌ git-auto-sync: 当前分支 (%s) ≠ 目标分支 (%s)，请先切换分支", currentBranch, branch)
	}

	if p.rebase {
		if err := git.PullRebase(p.repoPath, branch); err != nil {
			fmt.Printf("   ℹ️  pull --rebase 失败，继续尝试推送...\n")
		}
	}

	if err := git.Push(p.repoPath, branch); err != nil {
		if p.forcePush {
			fmt.Println("⚠️  git-auto-sync: 普通推送失败，尝试 --force-with-lease...")
			if err2 := git.PushForceLease(p.repoPath, branch); err2 != nil {
				return fmt.Errorf("❌ git-auto-sync: 推送失败 [%s]: %w", p.repoPath, err2)
			}
			fmt.Printf("✅ git-auto-sync: %s → origin/%s (force-with-lease) [%s]\n", shortHash, branch, p.repoPath)
			return nil
		}
		return fmt.Errorf("❌ git-auto-sync: 推送失败 [%s]: %w", p.repoPath, err)
	}

	fmt.Printf("✅ git-auto-sync: %s → origin/%s [%s]\n", shortHash, branch, p.repoPath)
	return nil
}

func printSyncHelp() {
	fmt.Println("用法: wiki-tools sync [PATH] [OPTIONS]")
	fmt.Println()
	fmt.Println("  无参数时同步当前目录。")
	fmt.Println()
	fmt.Println("选项:")
	fmt.Println("  --rebase      推送前先 git pull --rebase")
	fmt.Println("  --dry-run     只检查不执行")
	fmt.Println("  --name        提交者名字（env: GIT_SYNC_NAME）")
	fmt.Println("  --email       提交者邮箱（env: GIT_SYNC_EMAIL）")
	fmt.Println("  --branch      推送目标分支（env: GIT_SYNC_BRANCH）")
	fmt.Println("  --message     commit message 模板，支持 {timestamp}")
	fmt.Println("  --force-push  推送失败时尝试 --force-with-lease")
	fmt.Println("  -h, --help    显示帮助")
	fmt.Println()
	fmt.Println("环境变量（flag 优先级更高）:")
	fmt.Println("  GIT_SYNC_NAME, GIT_SYNC_EMAIL, GIT_SYNC_BRANCH")
	fmt.Println("  GIT_SYNC_MESSAGE, GIT_SYNC_DRY_RUN, GIT_SYNC_FORCE_PUSH")
	fmt.Println()
	fmt.Println("退出码:")
	fmt.Println("  0 — 成功 或 无修改")
	fmt.Println("  1 — 不是 Git 仓库")
	fmt.Println("  2 — 推送失败")
	fmt.Println("  3 — 路径错误")
}

func buildCommitMsg(template string) string {
	ts := timestamp()
	if template == "" {
		return "auto sync: " + ts
	}
	return strings.ReplaceAll(template, "{timestamp}", ts)
}
