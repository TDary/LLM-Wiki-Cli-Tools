//go:build !localonly

package main

import (
	"fmt"
	"os"

	"wiki-tools/internal/git"
)

func init() {
	gitInitFn = initGitRepo
}

func initGitRepo(wikiPath string) {
	if git.IsRepo(wikiPath) {
		return
	}
	if err := git.Init(wikiPath); err != nil {
		fmt.Fprintf(os.Stderr, "❌ git init failed: %v\n", err)
		os.Exit(2)
	}
	if err := git.Add(wikiPath); err != nil {
		fmt.Fprintf(os.Stderr, "❌ git add failed: %v\n", err)
		os.Exit(2)
	}
	committed, err := git.Commit(wikiPath, "Initial commit via wiki-tools")
	if err != nil {
		fmt.Fprintf(os.Stderr, "❌ git commit failed: %v\n", err)
		os.Exit(2)
	}
	if committed {
		fmt.Println("\n🔧 Git repository initialized")
	}
}
