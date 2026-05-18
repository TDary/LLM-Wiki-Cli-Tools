//go:build !localonly

package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"wiki-tools/internal/git"
	"wiki-tools/internal/wiki"
)

func init() {
	bootstrapGitFn = bootstrapGitFlow
	dryRunGitFn = dryRunGitFlow
}

func dryRunGitFlow(cfg bootstrapConfig) {
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

func bootstrapGitFlow(cfg bootstrapConfig) {
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
