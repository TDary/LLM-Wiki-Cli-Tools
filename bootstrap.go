package main

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"

	"wiki-tools/internal/git"
	"wiki-tools/internal/wiki"
)

type bootstrapConfig struct {
	remoteURL, localPath          string
	name, domain                  string
	syncInterval                  int
	committerName, committerEmail string
	noServe, noClone, force       bool
	token, projectName            string
	local                         bool
}

func argErr(msg string) {
	fmt.Fprintf(os.Stderr, "❌ %s\n", msg)
	printBootstrapHelp()
	os.Exit(1)
}

func parseBootstrapArgs(args []string) bootstrapConfig {
	cfg := bootstrapConfig{
		domain:         "LLM Wiki 知识库",
		syncInterval:   10,
		committerName:  "AI Assistant",
		committerEmail: "ai@local",
	}

	i := 0
	for i < len(args) {
		a := args[i]
		switch a {
		case "--name":
			i++; if i < len(args) { cfg.name = args[i] } else { argErr("--name requires a value") }
		case "--domain":
			i++; if i < len(args) { cfg.domain = args[i] } else { argErr("--domain requires a value") }
		case "--sync-interval":
			i++
			if i < len(args) {
				v, err := strconv.Atoi(args[i])
				if err != nil {
					fmt.Fprintf(os.Stderr, "❌ --sync-interval must be a number: %s\n", args[i])
					os.Exit(1)
				}
				cfg.syncInterval = v
			} else {
				argErr("--sync-interval requires a value")
			}
		case "--committer":
			i++; if i < len(args) { cfg.committerName = args[i] } else { argErr("--committer requires a value") }
		case "--committer-email":
			i++; if i < len(args) { cfg.committerEmail = args[i] } else { argErr("--committer-email requires a value") }
		case "--token":
			i++; if i < len(args) { cfg.token = args[i] } else { argErr("--token requires a value") }
		case "--no-serve":
			cfg.noServe = true
		case "--no-clone":
			cfg.noClone = true
		case "--force":
			cfg.force = true
		case "--local":
			cfg.local = true
		case "--dry-run", "-h", "--help", "--version":
			// handled before this function
		default:
			if !strings.HasPrefix(a, "-") {
				if cfg.remoteURL == "" {
					cfg.remoteURL = a
				} else if cfg.localPath == "" {
					cfg.localPath = a
				}
			} else {
				fmt.Fprintf(os.Stderr, "❌ unknown option: %s\n", a)
				printBootstrapHelp()
				os.Exit(1)
			}
		}
		i++
	}

	// Auto-detect: if remoteURL doesn't look like a Git URL,
	// treat it as a local path (local mode).
	if cfg.remoteURL != "" && !isGitURL(cfg.remoteURL) && cfg.localPath == "" {
		cfg.localPath = cfg.remoteURL
		cfg.remoteURL = ""
	}

	if cfg.localPath == "" && cfg.remoteURL != "" {
		repoBase := filepath.Base(cfg.remoteURL)
		repoBase = strings.TrimSuffix(repoBase, ".git")
		home, _ := os.UserHomeDir()
		cfg.localPath = filepath.Join(home, repoBase)
	}
	if cfg.localPath != "" && cfg.localPath[0] == '~' {
		home, err := os.UserHomeDir()
		if err != nil {
			fmt.Fprintf(os.Stderr, "❌ unable to determine home directory: %v\n", err)
			os.Exit(1)
		}
		cfg.localPath = filepath.Join(home, cfg.localPath[1:])
	}
	if cfg.localPath != "" {
		cfg.localPath, _ = filepath.Abs(cfg.localPath)
	}

	cfg.projectName = cfg.name
	if cfg.projectName == "" && cfg.localPath != "" {
		cfg.projectName = filepath.Base(cfg.localPath)
	}

	return cfg
}

func printBootstrapHelp() {
	fmt.Println("用法: wiki-tools bootstrap [REMOTE_URL] [LOCAL_PATH] [OPTIONS]")
	fmt.Println()
	fmt.Println("选项:")
	fmt.Println("  --name NAME           项目名（默认取路径 basename）")
	fmt.Println("  --domain DOMAIN       领域描述（默认 \"LLM Wiki 知识库\"）")
	fmt.Println("  --sync-interval N     自动同步间隔（分钟，默认 10，0 = 不启动 serve）")
	fmt.Println("  --committer NAME      提交者名字（默认 \"AI Assistant\"）")
	fmt.Println("  --committer-email E   提交者邮箱（默认 \"ai@local\"）")
	fmt.Println("  --no-serve            不启动定时同步守护进程")
	fmt.Println("  --no-clone            跳过 clone")
	fmt.Println("  --force               覆盖已存在的所有生成文件")
	fmt.Println("  --token TOKEN         Git 访问令牌")
	fmt.Println("  --local               纯本地模式（无 URL 时自动启用）")
	fmt.Println("  --dry-run             预览模式")
	fmt.Println("  -h, --help            显示帮助")
	fmt.Println("  --version             显示版本")
	fmt.Println()
	fmt.Println("示例:")
	fmt.Println("  wiki-tools bootstrap git@gitlab.com:group/wiki.git ~/team-wiki")
	fmt.Println("  wiki-tools bootstrap https://github.com/user/wiki.git --name my-wiki")
	fmt.Println("  wiki-tools bootstrap <url> ~/existing-dir --no-clone --force")
	fmt.Println("  wiki-tools bootstrap ~/my-wiki --domain \"我的知识库\"")
	fmt.Println("  wiki-tools bootstrap --local ~/my-wiki --domain \"我的知识库\"")
}

func dryRunBootstrap(args []string) {
	cfg := parseBootstrapArgs(args)
	if cfg.remoteURL == "" {
		cfg.local = true
	}
	fmt.Println()
	fmt.Println("DRY RUN — preview mode, no actions will be executed")
	fmt.Println()

	if cfg.local {
		fmt.Println("  Planned actions (local mode):")
		fmt.Printf("    Create directory structure: %s\n", cfg.localPath)
		fmt.Printf("    wiki-tools init %s \"%s\"\n", cfg.localPath, cfg.domain)
		fmt.Println("    Skip all Git operations (clone / sync / serve)")
		fmt.Println()
		return
	}

	fmt.Println("  Planned actions:")
	if !cfg.noClone {
		if git.IsRepo(cfg.localPath) {
			fmt.Println("    Step 1: Git repo exists, skip clone")
		} else if _, err := os.Stat(cfg.localPath); err == nil {
			fmt.Println("    Step 1: directory exists, proceed to init")
		} else {
			fmt.Printf("    Step 1: git clone %s -> %s\n", cfg.remoteURL, cfg.localPath)
		}
	} else {
		fmt.Println("    Step 1: --no-clone, skip clone")
	}
	fmt.Printf("    Step 2: wiki-tools init %s \"%s\"\n", cfg.localPath, cfg.domain)
	fmt.Println("    Step 3: configure Git remote / committer / credential")
	fmt.Printf("    Step 4: wiki-tools sync %s\n", cfg.localPath)
	if !cfg.noServe && cfg.syncInterval > 0 {
		fmt.Printf("    Step 5: suggest running wiki-tools serve %s --interval %d\n", cfg.localPath, cfg.syncInterval)
	}
	fmt.Println()
}

func bootstrapCmd(args []string) {
	for _, a := range args {
		switch a {
		case "-h", "--help":
			printBootstrapHelp()
			os.Exit(0)
		case "--version":
			fmt.Println("wiki-tools v" + version)
			os.Exit(0)
		case "--dry-run":
			dryRunBootstrap(args)
			return
		}
	}

	cfg := parseBootstrapArgs(args)

	if cfg.remoteURL == "" {
		cfg.local = true
	}

	if cfg.local {
		if cfg.localPath == "" {
			fmt.Fprintln(os.Stderr, "missing local path")
			printBootstrapHelp()
			os.Exit(1)
		}

		fmt.Println()
		fmt.Println("╔════════════════════════════════════════════════════════╗")
		fmt.Println("║     wiki-tools bootstrap · local mode deployment      ║")
		fmt.Println("╚════════════════════════════════════════════════════════╝")
		fmt.Println()
		fmt.Printf("  project:     %s\n", cfg.projectName)
		fmt.Printf("  domain:      %s\n", cfg.domain)
		fmt.Printf("  local path:  %s\n", cfg.localPath)
		fmt.Println("  mode:        local (no Git)")
		fmt.Println()

		if err := os.MkdirAll(cfg.localPath, 0755); err != nil {
			fmt.Fprintf(os.Stderr, "cannot create directory: %s\n", cfg.localPath)
			os.Exit(3)
		}
		if err := wiki.WriteFiles(cfg.localPath, cfg.projectName, cfg.domain, cfg.force, !cfg.local); err != nil {
			fmt.Fprintf(os.Stderr, "wiki-init failed: %v\n", err)
			os.Exit(3)
		}

		fmt.Printf("wiki-tools init completed: %s\n", cfg.localPath)
		fmt.Printf("   domain: %s\n", cfg.domain)
		fmt.Printf("   dirs: %d subdirectories\n", len(wiki.Dirs))
		fmt.Println()
		fmt.Println("╔════════════════════════════════════════════════════════╗")
		fmt.Println("║              local deployment complete!                ║")
		fmt.Println("╚════════════════════════════════════════════════════════╝")
		fmt.Println()
		fmt.Printf("  wiki path:  %s\n", cfg.localPath)
		fmt.Printf("  SCHEMA:     %s/SCHEMA.md\n", cfg.localPath)
		fmt.Println()
		fmt.Println("  No Git needed — read/write files directly.")
		fmt.Println()
		return
	}

	fmt.Println()
	fmt.Println("╔════════════════════════════════════════════════════════╗")
	fmt.Println("║          wiki-tools bootstrap · one-click setup       ║")
	fmt.Println("╚════════════════════════════════════════════════════════╝")
	fmt.Println()
	fmt.Printf("  project:     %s\n", cfg.projectName)
	fmt.Printf("  domain:      %s\n", cfg.domain)
	fmt.Printf("  local path:  %s\n", cfg.localPath)
	fmt.Printf("  remote:      %s\n", cfg.remoteURL)
	fmt.Printf("  auto sync:   every %d min\n", cfg.syncInterval)
	fmt.Printf("  committer:   %s <%s>\n", cfg.committerName, cfg.committerEmail)
	if cfg.token != "" {
		fmt.Println("  token:       [provided, will write to ~/.git-credentials]")
	}
	fmt.Println()

	// Step 1: Clone or verify
	if !cfg.noClone {
		if git.IsRepo(cfg.localPath) {
			fmt.Println("Step 1: Git repo exists, skip clone")
			_ = git.Fetch(cfg.localPath)
		} else if _, err := os.Stat(cfg.localPath); err == nil {
			fmt.Println("Step 1: directory exists but not a Git repo")
			entries, _ := os.ReadDir(cfg.localPath)
			if len(entries) > 0 {
				fmt.Println("   directory not empty, will keep existing content")
			}
		} else {
			fmt.Printf("Step 1: git clone %s -> %s\n", cfg.remoteURL, cfg.localPath)
			if err := git.Clone(nil, cfg.remoteURL, cfg.localPath); err != nil {
				fmt.Println("   clone failed, initializing local repo (you can add remote later)")
				os.MkdirAll(cfg.localPath, 0755)
				_ = git.Init(cfg.localPath)
				_ = git.RemoteAdd(cfg.localPath, cfg.remoteURL)
			} else {
				fmt.Println("   clone succeeded")
			}
		}
	} else {
		fmt.Println("Step 1: --no-clone mode, skip clone")
		if _, err := os.Stat(cfg.localPath); os.IsNotExist(err) {
			fmt.Fprintf(os.Stderr, "path does not exist: %s\n", cfg.localPath)
			os.Exit(2)
		}
	}

	// Step 2: wiki-init
	fmt.Println()
	fmt.Println("Step 2: initialize wiki structure")
	if err := os.MkdirAll(cfg.localPath, 0755); err != nil {
		fmt.Fprintf(os.Stderr, "cannot create directory: %s\n", cfg.localPath)
		os.Exit(3)
	}
	if err := wiki.WriteFiles(cfg.localPath, cfg.projectName, cfg.domain, cfg.force, !cfg.local); err != nil {
		fmt.Fprintf(os.Stderr, "wiki-init failed: %v\n", err)
		os.Exit(3)
	}
	fmt.Println()
	fmt.Printf("wiki-tools init completed: %s\n", cfg.localPath)
	fmt.Printf("   domain: %s\n", cfg.domain)
	fmt.Printf("   dirs: %d subdirectories\n", len(wiki.Dirs))

	// Step 3: Git config
	fmt.Println()
	fmt.Println("Step 3: Git config")
	if !git.IsRepo(cfg.localPath) {
		if err := git.Init(cfg.localPath); err != nil {
			fmt.Fprintf(os.Stderr, "git init failed: %v\n", err)
			os.Exit(3)
		}
		fmt.Println("   git init")
	}
	currentRemote, err := git.RemoteGetURL(cfg.localPath)
	if err != nil {
		_ = git.RemoteAdd(cfg.localPath, cfg.remoteURL)
		fmt.Println("   git remote add origin")
	} else if currentRemote != cfg.remoteURL {
		_ = git.RemoteSetURL(cfg.localPath, cfg.remoteURL)
		fmt.Println("   git remote set-url origin")
	}
	_ = git.SetConfig(cfg.localPath, "user.name", cfg.committerName)
	_ = git.SetConfig(cfg.localPath, "user.email", cfg.committerEmail)
	fmt.Printf("   %s <%s>\n", cfg.committerName, cfg.committerEmail)

	if cfg.token != "" {
		host := extractHost(cfg.remoteURL)
		if host != "" {
			proto := "https"
			if strings.HasPrefix(cfg.remoteURL, "http://") {
				proto = "http"
			}
			writeCredential(proto, host, cfg.token)
			_ = git.SetConfigGlobal("credential.helper", "store")
			fmt.Println("   token written to ~/.git-credentials")
		} else {
			fmt.Println("   could not extract host from URL, skip token config")
		}
	} else if home, err := os.UserHomeDir(); err == nil {
		if _, err := os.Stat(filepath.Join(home, ".git-credentials")); err == nil {
			_ = git.SetConfigGlobal("credential.helper", "store")
			fmt.Println("   credential.helper = store (exists)")
		}
	}
	fmt.Println("   Git config completed")

	// Step 4: Initial sync
	fmt.Println()
	fmt.Println("Step 4: initial sync")
	defaultBranch := git.DefaultBranch(cfg.localPath)
	currentBranch, _ := git.CurrentBranch(cfg.localPath)
	pullBranch := currentBranch
	if pullBranch == "" {
		pullBranch = defaultBranch
	}
	if err := git.PullRebase(cfg.localPath, pullBranch); err != nil {
		fmt.Println("   no remote content or pull failed (will auto-push on first sync)")
	}
	if err := runSync(syncParams{
		repoPath:       cfg.localPath,
		committerName:  cfg.committerName,
		committerEmail: cfg.committerEmail,
		targetBranch:   currentBranch,
	}); err != nil {
		fmt.Printf("   initial sync skipped: %v\n", err)
	}

	// Step 5: Daemon
	fmt.Println()
	if !cfg.noServe && cfg.syncInterval > 0 {
		fmt.Printf("Step 5: periodic sync daemon (every %d min)\n", cfg.syncInterval)
		fmt.Println()
		fmt.Println("   start daemon:")
		fmt.Printf("      wiki-tools serve %s --interval %d\n", cfg.localPath, cfg.syncInterval)
		fmt.Println()
		fmt.Println("   or in background:")
		fmt.Printf("      nohup wiki-tools serve %s --interval %d &\n", cfg.localPath, cfg.syncInterval)
	} else {
		fmt.Println("Step 5: skip periodic sync (--no-serve or sync-interval=0)")
	}

	// Completion
	fmt.Println()
	fmt.Println("╔════════════════════════════════════════════════════════╗")
	fmt.Println("║                 setup complete!                        ║")
	fmt.Println("╚════════════════════════════════════════════════════════╝")
	fmt.Println()
	fmt.Printf("  wiki path:    %s\n", cfg.localPath)
	fmt.Printf("  remote:       %s\n", cfg.remoteURL)
	fmt.Printf("  SCHEMA:       %s/SCHEMA.md\n", cfg.localPath)
	fmt.Println()
	fmt.Println("  quick reference:")
	fmt.Printf("    wiki-tools sync %s              # manual sync\n", cfg.localPath)
	fmt.Printf("    wiki-tools init %s \"desc\"       # re-init structure\n", cfg.localPath)
	fmt.Printf("    wiki-tools serve %s              # start daemon\n", cfg.localPath)
	fmt.Println()
}

func isGitURL(s string) bool {
	return strings.HasPrefix(s, "git@") ||
		strings.HasPrefix(s, "https://") ||
		strings.HasPrefix(s, "http://") ||
		strings.HasPrefix(s, "ssh://") ||
		strings.HasSuffix(s, ".git")
}

var hostRegex = regexp.MustCompile(`(?:https?://|@)([^:/@]+)`)

func extractHost(url string) string {
	matches := hostRegex.FindStringSubmatch(url)
	if len(matches) >= 2 {
		return matches[1]
	}
	return ""
}

func writeCredential(proto, host, token string) {
	home, _ := os.UserHomeDir()
	credsFile := filepath.Join(home, ".git-credentials")
	os.MkdirAll(home, 0700)

	if content, err := os.ReadFile(credsFile); err == nil {
		var newLines []string
		prefix := proto + "://"
		scanner := bufio.NewScanner(strings.NewReader(string(content)))
		for scanner.Scan() {
			line := scanner.Text()
			if !strings.Contains(line, prefix) || !strings.Contains(line, "@"+host) {
				newLines = append(newLines, line)
			}
		}
		f, err := os.Create(credsFile)
		if err != nil {
			return
		}
		for _, line := range newLines {
			fmt.Fprintln(f, line)
		}
		f.Close()
	}

	f, err := os.OpenFile(credsFile, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0600)
	if err != nil {
		return
	}
	defer f.Close()
	fmt.Fprintf(f, "%s://oauth2:%s@%s\n", proto, token, host)
}
