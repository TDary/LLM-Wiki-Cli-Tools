//go:build !localonly

package cmd

import (
	"errors"
	"flag"
	"fmt"
	"os"
	"strings"

	"wiki-tools/internal/git"
)

func init() { Register("sync", syncCmd) }

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
			fmt.Println("wiki-tools v" + Version)
			os.Exit(0)
		}
	}

	flags := flag.NewFlagSet("sync", flag.ExitOnError)
	rebase := flags.Bool("rebase", false, "push before pull --rebase")
	dryRun := flags.Bool("dry-run", false, "preview only")
	name := flags.String("name", "", "committer name")
	email := flags.String("email", "", "committer email")
	branch := flags.String("branch", "", "target branch")
	message := flags.String("message", "", "commit message template, {timestamp} placeholder supported")
	forcePush := flags.Bool("force-push", false, "try force-with-lease on push failure")
	flags.Usage = printSyncHelp
	flags.Parse(args)

	repoPath := "."
	if flags.NArg() > 0 {
		repoPath = flags.Arg(0)
	}

	var err error
	if repoPath, err = AbsPath(repoPath); err != nil {
		fmt.Fprintf(os.Stderr, "git-auto-sync: path error: %s\n", repoPath)
		os.Exit(3)
	}

	committerName := FirstNonEmpty(*name, os.Getenv("GIT_SYNC_NAME"), "AI Assistant")
	committerEmail := FirstNonEmpty(*email, os.Getenv("GIT_SYNC_EMAIL"), "ai@local")
	targetBranch := FirstNonEmpty(*branch, os.Getenv("GIT_SYNC_BRANCH"), "")
	commitMsg := FirstNonEmpty(*message, os.Getenv("GIT_SYNC_MESSAGE"), "")
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
		if errors.Is(err, git.ErrNotARepo) {
			os.Exit(1)
		}
		if errors.Is(err, git.ErrPushFailed) {
			os.Exit(2)
		}
		os.Exit(3)
	}
}

func runSync(p syncParams) error {
	if !git.IsRepo(p.repoPath) {
		return fmt.Errorf("%w: %s", git.ErrNotARepo, p.repoPath)
	}

	status, err := git.StatusPorcelain(p.repoPath)
	if err != nil {
		return fmt.Errorf("git-auto-sync: git status failed: %w", err)
	}
	if status == "" {
		fmt.Printf("git-auto-sync: no changes [%s] - skipping\n", p.repoPath)
		return nil
	}

	if p.dryRun {
		fmt.Printf("git-auto-sync: DRY RUN [%s]\n", p.repoPath)
		fmt.Println("   pending files:")
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
		return fmt.Errorf("git-auto-sync: set user.name failed: %w", err)
	}
	if err := git.SetConfig(p.repoPath, "user.email", p.committerEmail); err != nil {
		return fmt.Errorf("git-auto-sync: set user.email failed: %w", err)
	}

	if err := git.Add(p.repoPath); err != nil {
		return fmt.Errorf("git-auto-sync: git add failed: %w", err)
	}

	msg := buildCommitMsg(p.commitMsg)
	committed, err := git.Commit(p.repoPath, msg)
	if err != nil {
		return fmt.Errorf("git-auto-sync: git commit failed: %w", err)
	}
	if !committed {
		fmt.Printf("git-auto-sync: commit had no effect [%s]\n", p.repoPath)
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
			return fmt.Errorf("git-auto-sync: cannot determine current branch: %w", err)
		}
	} else {
		// Verify current branch matches target
		currentBranch, _ := git.CurrentBranch(p.repoPath)
		if currentBranch != "" && branch != currentBranch {
			return fmt.Errorf("git-auto-sync: current branch (%s) != target branch (%s), switch branch first", currentBranch, branch)
		}
	}

	if p.rebase {
		if err := git.PullRebase(p.repoPath, branch); err != nil {
			fmt.Printf("   pull --rebase failed, continuing to push...\n")
		}
	}

	if err := git.Push(p.repoPath, branch); err != nil {
		if p.forcePush {
			fmt.Println("git-auto-sync: push failed, trying --force-with-lease...")
			if err2 := git.PushForceLease(p.repoPath, branch); err2 != nil {
				return fmt.Errorf("%w: %s: %w", git.ErrPushFailed, p.repoPath, err2)
			}
			fmt.Printf("git-auto-sync: %s -> origin/%s (force-with-lease) [%s]\n", shortHash, branch, p.repoPath)
			return nil
		}
		return fmt.Errorf("%w: %s: %w", git.ErrPushFailed, p.repoPath, err)
	}

	fmt.Printf("git-auto-sync: %s -> origin/%s [%s]\n", shortHash, branch, p.repoPath)
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
	fmt.Println("  --version     显示版本")
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
	ts := Timestamp()
	if template == "" {
		return "auto sync: " + ts
	}
	return strings.ReplaceAll(template, "{timestamp}", ts)
}
