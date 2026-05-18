package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"wiki-tools/internal/git"
	"wiki-tools/internal/wiki"
)

type initConfig struct {
	wikiPath, domain, name string
	noGit, force           bool
}

func initCmd(args []string) {
	for _, a := range args {
		switch a {
		case "-h", "--help":
			printInitHelp()
			os.Exit(0)
		case "--version":
			fmt.Println("wiki-tools v" + version)
			os.Exit(0)
		}
	}

	cfg := parseInitArgs(args)

	if cfg.wikiPath == "" || cfg.domain == "" {
		fmt.Fprintln(os.Stderr, "❌ 缺少必要参数: WIKI_PATH 和 DOMAIN")
		printInitHelp()
		os.Exit(1)
	}

	wikiPath := cfg.wikiPath
	if wikiPath[0] == '~' {
		home, _ := os.UserHomeDir()
		wikiPath = filepath.Join(home, wikiPath[1:])
	}
	wikiPath, err := wiki.AbsPath(wikiPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "❌ 路径解析失败: %v\n", err)
		os.Exit(2)
	}

	projectName := cfg.name
	if projectName == "" {
		projectName = filepath.Base(wikiPath)
	}

	if err := os.MkdirAll(wikiPath, 0755); err != nil {
		fmt.Fprintf(os.Stderr, "❌ 无法创建目录: %s\n", wikiPath)
		os.Exit(2)
	}

	if err := wiki.WriteFiles(wikiPath, projectName, cfg.domain, cfg.force, !cfg.noGit); err != nil {
		fmt.Fprintf(os.Stderr, "❌ %v\n", err)
		os.Exit(2)
	}

	if !cfg.noGit && !git.IsRepo(wikiPath) {
		if err := git.Init(wikiPath); err != nil {
			fmt.Fprintf(os.Stderr, "❌ git init 失败: %v\n", err)
			os.Exit(2)
		}
		if err := git.Add(wikiPath); err != nil {
			fmt.Fprintf(os.Stderr, "❌ git add 失败: %v\n", err)
			os.Exit(2)
		}
		committed, err := git.Commit(wikiPath, "Initial commit: wiki-tools init bootstrap")
		if err != nil {
			fmt.Fprintf(os.Stderr, "❌ git commit 失败: %v\n", err)
			os.Exit(2)
		}
		if committed {
			fmt.Println("\n🔧 Git 仓库已初始化")
		}
	}

	fmt.Println()
	fmt.Printf("✅ wiki-tools init 完成: %s\n", wikiPath)
	fmt.Printf("   领域: %s\n", cfg.domain)
	fmt.Printf("   目录: %d 个子目录\n", len(wiki.Dirs))
	fmt.Println()
	fmt.Println("下一步：")
	fmt.Printf("   wiki-tools bootstrap <remote-url> %s    # 绑定远程仓库并配置自动同步\n", wikiPath)
	fmt.Println("   或手动: git remote add origin <url> && git push -u origin main")
}

func parseInitArgs(args []string) initConfig {
	cfg := initConfig{}
	i := 0
	for i < len(args) {
		a := args[i]
		switch a {
		case "--name":
			i++; if i < len(args) { cfg.name = args[i] }
		case "--no-git":
			cfg.noGit = true
		case "--force":
			cfg.force = true
		case "-h", "--help", "--version":
			// handled before
		default:
			if !strings.HasPrefix(a, "-") {
				if cfg.wikiPath == "" {
					cfg.wikiPath = a
				} else if cfg.domain == "" {
					cfg.domain = a
				}
			} else {
				fmt.Fprintf(os.Stderr, "❌ 未知选项: %s\n", a)
				printInitHelp()
				os.Exit(1)
			}
		}
		i++
	}
	return cfg
}

func printInitHelp() {
	fmt.Println("用法: wiki-tools init <WIKI_PATH> <DOMAIN> [OPTIONS]")
	fmt.Println()
	fmt.Println("参数:")
	fmt.Println("  WIKI_PATH    知识库本地路径（必须）")
	fmt.Println("  DOMAIN       领域名称，写入 SCHEMA.md（必须）")
	fmt.Println()
	fmt.Println("选项:")
	fmt.Println("  --no-git     不初始化 Git 仓库")
	fmt.Println("  --force      覆盖已存在的文件")
	fmt.Println("  --name NAME  项目名（默认取目录名）")
	fmt.Println("  -h, --help   显示帮助")
	fmt.Println("  --version    显示版本")
	fmt.Println()
	fmt.Println("示例:")
	fmt.Println(`  wiki-tools init ~/team-wiki "团队共享知识库"`)
	fmt.Println(`  wiki-tools init ~/my-wiki "个人知识库" --name my-wiki`)
	fmt.Println(`  wiki-tools init ~/wiki "实验项目" --force --no-git`)
}
