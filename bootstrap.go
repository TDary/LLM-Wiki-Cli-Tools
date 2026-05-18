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
			i++; if i < len(args) { cfg.name = args[i] }
		case "--domain":
			i++; if i < len(args) { cfg.domain = args[i] }
		case "--sync-interval":
			i++; if i < len(args) { cfg.syncInterval, _ = strconv.Atoi(args[i]) }
		case "--committer":
			i++; if i < len(args) { cfg.committerName = args[i] }
		case "--committer-email":
			i++; if i < len(args) { cfg.committerEmail = args[i] }
		case "--token":
			i++; if i < len(args) { cfg.token = args[i] }
		case "--no-serve":
			cfg.noServe = true
		case "--no-clone":
			cfg.noClone = true
		case "--force":
			cfg.force = true
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
				fmt.Fprintf(os.Stderr, "❌ 未知选项: %s\n", a)
				printBootstrapHelp()
				os.Exit(1)
			}
		}
		i++
	}

	if cfg.localPath == "" && cfg.remoteURL != "" {
		repoBase := filepath.Base(cfg.remoteURL)
		repoBase = strings.TrimSuffix(repoBase, ".git")
		home, _ := os.UserHomeDir()
		cfg.localPath = filepath.Join(home, repoBase)
	}
	if cfg.localPath != "" && cfg.localPath[0] == '~' {
		home, _ := os.UserHomeDir()
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
	fmt.Println("用法: wiki-tools bootstrap <REMOTE_URL> [LOCAL_PATH] [OPTIONS]")
	fmt.Println()
	fmt.Println("选项:")
	fmt.Println("  --name NAME           项目名（默认取路径 basename）")
	fmt.Println("  --domain DOMAIN       领域描述（默认 \"LLM Wiki 知识库\"）")
	fmt.Println("  --sync-interval N     自动同步间隔（分钟，默认 10，0 = 不启动 serve）")
	fmt.Println("  --committer NAME      提交者名字（默认 \"AI Assistant\"）")
	fmt.Println("  --committer-email E   提交者邮箱（默认 \"ai@local\"）")
	fmt.Println("  --no-serve            不启动定时同步守护进程")
	fmt.Println("  --no-clone            跳过 clone")
	fmt.Println("  --force               覆盖已存在的 SCHEMA.md")
	fmt.Println("  --token TOKEN         Git 访问令牌")
	fmt.Println("  --dry-run             预览模式")
	fmt.Println("  -h, --help            显示帮助")
	fmt.Println()
	fmt.Println("示例:")
	fmt.Println("  wiki-tools bootstrap git@gitlab.com:group/wiki.git ~/team-wiki")
	fmt.Println("  wiki-tools bootstrap https://github.com/user/wiki.git --name my-wiki")
	fmt.Println("  wiki-tools bootstrap <url> ~/existing-dir --no-clone --force")
}

func dryRunBootstrap(args []string) {
	cfg := parseBootstrapArgs(args)
	fmt.Println()
	fmt.Println("🔍 DRY RUN — 预览模式，不会执行任何实际操作")
	fmt.Println()
	fmt.Println("  将执行的操作：")
	if !cfg.noClone {
		if git.IsRepo(cfg.localPath) {
			fmt.Println("    📦 Step 1: 检测到已有 Git 仓库，跳过 clone")
		} else if _, err := os.Stat(cfg.localPath); err == nil {
			fmt.Println("    📦 Step 1: 目录已存在，继续初始化")
		} else {
			fmt.Printf("    📦 Step 1: git clone %s → %s\n", cfg.remoteURL, cfg.localPath)
		}
	} else {
		fmt.Println("    📦 Step 1: --no-clone，跳过 clone")
	}
	fmt.Printf("    📂 Step 2: wiki-tools init %s \"%s\"\n", cfg.localPath, cfg.domain)
	fmt.Println("    🔧 Step 3: 配置 Git remote / committer / credential")
	fmt.Printf("    🚀 Step 4: wiki-tools sync %s\n", cfg.localPath)
	if !cfg.noServe && cfg.syncInterval > 0 {
		fmt.Printf("    ⏰ Step 5: 建议运行 wiki-tools serve %s --interval %d\n", cfg.localPath, cfg.syncInterval)
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
		fmt.Fprintln(os.Stderr, "❌ 缺少远程仓库 URL")
		printBootstrapHelp()
		os.Exit(1)
	}

	fmt.Println()
	fmt.Println("╔════════════════════════════════════════════════════════╗")
	fmt.Println("║          wiki-tools bootstrap · 一键安装知识库        ║")
	fmt.Println("╚════════════════════════════════════════════════════════╝")
	fmt.Println()
	fmt.Printf("  项目名:     %s\n", cfg.projectName)
	fmt.Printf("  领域:       %s\n", cfg.domain)
	fmt.Printf("  本地路径:   %s\n", cfg.localPath)
	fmt.Printf("  远程仓库:   %s\n", cfg.remoteURL)
	fmt.Printf("  自动同步:   %d 分钟/次\n", cfg.syncInterval)
	fmt.Printf("  提交者:     %s <%s>\n", cfg.committerName, cfg.committerEmail)
	if cfg.token != "" {
		fmt.Println("  Token:      [已提供，将自动写入 ~/.git-credentials]")
	}
	fmt.Println()

	// Step 1: Clone or verify
	if !cfg.noClone {
		if git.IsRepo(cfg.localPath) {
			fmt.Println("📦 Step 1: 检测到已有 Git 仓库，跳过 clone")
			_ = git.Fetch(cfg.localPath)
		} else if _, err := os.Stat(cfg.localPath); err == nil {
			fmt.Println("📦 Step 1: 目录已存在但非 Git 仓库")
			entries, _ := os.ReadDir(cfg.localPath)
			if len(entries) > 0 {
				fmt.Println("   ⚠️  目录非空，将保留已有内容继续初始化")
			}
		} else {
			fmt.Printf("📦 Step 1: git clone %s → %s\n", cfg.remoteURL, cfg.localPath)
			if err := git.Clone(nil, cfg.remoteURL, cfg.localPath); err != nil {
				fmt.Println("   ⚠️  clone 失败，将初始化本地仓库（可稍后手动关联远程）")
				os.MkdirAll(cfg.localPath, 0755)
				_ = git.Init(cfg.localPath)
				_ = git.RemoteAdd(cfg.localPath, cfg.remoteURL)
			} else {
				fmt.Println("   ✅ clone 成功")
			}
		}
	} else {
		fmt.Println("📦 Step 1: --no-clone 模式，跳过 clone")
		if _, err := os.Stat(cfg.localPath); os.IsNotExist(err) {
			fmt.Fprintf(os.Stderr, "❌ 路径不存在: %s\n", cfg.localPath)
			os.Exit(2)
		}
	}

	// Step 2: wiki-init
	fmt.Println()
	fmt.Println("📂 Step 2: 初始化 wiki 结构")
	if err := os.MkdirAll(cfg.localPath, 0755); err != nil {
		fmt.Fprintf(os.Stderr, "❌ 无法创建目录: %s\n", cfg.localPath)
		os.Exit(3)
	}
	if err := wiki.WriteFiles(cfg.localPath, cfg.projectName, cfg.domain, cfg.force); err != nil {
		fmt.Fprintf(os.Stderr, "❌ wiki-init 失败: %v\n", err)
		os.Exit(3)
	}
	fmt.Println()
	fmt.Printf("✅ wiki-tools init 完成: %s\n", cfg.localPath)
	fmt.Printf("   领域: %s\n", cfg.domain)
	fmt.Printf("   目录: %d 个子目录\n", len(wiki.Dirs))

	// Step 3: Git config
	fmt.Println()
	fmt.Println("🔧 Step 3: Git 配置")
	if !git.IsRepo(cfg.localPath) {
		if err := git.Init(cfg.localPath); err != nil {
			fmt.Fprintf(os.Stderr, "❌ git init 失败: %v\n", err)
			os.Exit(3)
		}
		fmt.Println("   📌 git init")
	}
	currentRemote, err := git.RemoteGetURL(cfg.localPath)
	if err != nil {
		_ = git.RemoteAdd(cfg.localPath, cfg.remoteURL)
		fmt.Println("   📌 git remote add origin")
	} else if currentRemote != cfg.remoteURL {
		_ = git.RemoteSetURL(cfg.localPath, cfg.remoteURL)
		fmt.Println("   📌 git remote set-url origin")
	}
	_ = git.SetConfig(cfg.localPath, "user.name", cfg.committerName)
	_ = git.SetConfig(cfg.localPath, "user.email", cfg.committerEmail)
	fmt.Printf("   👤 %s <%s>\n", cfg.committerName, cfg.committerEmail)

	if cfg.token != "" {
		host := extractHost(cfg.remoteURL)
		if host != "" {
			proto := "https"
			if strings.HasPrefix(cfg.remoteURL, "http://") {
				proto = "http"
			}
			writeCredential(proto, host, cfg.token)
			_ = git.SetConfigGlobal("credential.helper", "store")
			fmt.Println("   🔑 Token 已写入 ~/.git-credentials （仅本机可见）")
		} else {
			fmt.Println("   ⚠️  无法从 REMOTE_URL 提取主机名，跳过 token 配置")
		}
	} else if _, err := os.Stat(filepath.Join(os.Getenv("HOME"), ".git-credentials")); err == nil {
		_ = git.SetConfigGlobal("credential.helper", "store")
		fmt.Println("   🔑 credential.helper = store（已存在）")
	}
	fmt.Println("   ✅ Git 配置完成")

	// Step 4: Initial sync
	fmt.Println()
	fmt.Println("🚀 Step 4: 初始同步")
	defaultBranch := git.DefaultBranch(cfg.localPath)
	currentBranch, _ := git.CurrentBranch(cfg.localPath)
	pullBranch := currentBranch
	if pullBranch == "" {
		pullBranch = defaultBranch
	}
	if err := git.PullRebase(cfg.localPath, pullBranch); err != nil {
		fmt.Println("   ℹ️  无远程内容或拉取失败（首次推送时会自动处理）")
	}
	if err := runSync(syncParams{
		repoPath:       cfg.localPath,
		committerName:  cfg.committerName,
		committerEmail: cfg.committerEmail,
		targetBranch:   currentBranch,
	}); err != nil {
		fmt.Printf("   ⚠️  初始同步跳过: %v\n", err)
	}

	// Step 5: Daemon
	fmt.Println()
	if !cfg.noServe && cfg.syncInterval > 0 {
		fmt.Printf("⏰ Step 5: 定时同步守护进程（每 %d 分钟）\n", cfg.syncInterval)
		fmt.Println()
		fmt.Println("   💡 运行以下命令启动守护进程:")
		fmt.Printf("      wiki-tools serve %s --interval %d\n", cfg.localPath, cfg.syncInterval)
		fmt.Println()
		fmt.Println("   💡 或在后台运行:")
		fmt.Printf("      nohup wiki-tools serve %s --interval %d &\n", cfg.localPath, cfg.syncInterval)
	} else {
		fmt.Println("⏰ Step 5: 跳过定时同步（--no-serve 或 sync-interval=0）")
	}

	// Completion
	fmt.Println()
	fmt.Println("╔════════════════════════════════════════════════════════╗")
	fmt.Println("║                 ✅ 安装完成！                           ║")
	fmt.Println("╚════════════════════════════════════════════════════════╝")
	fmt.Println()
	fmt.Printf("  📂 知识库路径:   %s\n", cfg.localPath)
	fmt.Printf("  🌐 远程仓库:     %s\n", cfg.remoteURL)
	fmt.Printf("  📋 SCHEMA:       %s/SCHEMA.md\n", cfg.localPath)
	fmt.Println()
	fmt.Println("  命令速查：")
	fmt.Printf("    wiki-tools sync %s              # 手动同步一次\n", cfg.localPath)
	fmt.Printf("    wiki-tools init %s \"描述\"       # 重新初始化结构\n", cfg.localPath)
	fmt.Printf("    wiki-tools serve %s              # 启动定时同步\n", cfg.localPath)
	fmt.Println()
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
		content = []byte(strings.Join(newLines, "\n"))
		if len(newLines) > 0 {
			content = append(content, '\n')
		}
		os.WriteFile(credsFile, content, 0600)
	}

	f, err := os.OpenFile(credsFile, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0600)
	if err != nil {
		return
	}
	defer f.Close()
	fmt.Fprintf(f, "%s://oauth2:%s@%s\n", proto, token, host)
}
