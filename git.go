package main

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

const gitTimeout = 120 * time.Second

func gitCmd(ctx context.Context, dir string, args ...string) (string, error) {
	if ctx == nil {
		ctx = context.Background()
	}
	ctx, cancel := context.WithTimeout(ctx, gitTimeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, "git", args...)
	cmd.Dir = dir
	cmd.Env = append(os.Environ(),
		"GIT_TERMINAL_PROMPT=0",
		"GCM_INTERACTIVE=never",
	)

	out, err := cmd.Output()
	if err != nil {
		if ctx.Err() == context.DeadlineExceeded {
			return "", fmt.Errorf("git %s: timed out after %v", args[0], gitTimeout)
		}
		return "", fmt.Errorf("git %s: %w\n%s", strings.Join(args, " "), err, out)
	}
	return strings.TrimSpace(string(out)), nil
}

func gitCmdStderr(dir string, args ...string) (string, string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), gitTimeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, "git", args...)
	cmd.Dir = dir
	cmd.Env = append(os.Environ(),
		"GIT_TERMINAL_PROMPT=0",
		"GCM_INTERACTIVE=never",
	)

	var stdout, stderr strings.Builder
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	err := cmd.Run()
	if ctx.Err() == context.DeadlineExceeded {
		return "", stderr.String(), fmt.Errorf("git %s: timed out", args[0])
	}
	return strings.TrimSpace(stdout.String()), strings.TrimSpace(stderr.String()), err
}

func isGitRepo(path string) bool {
	info, err := os.Stat(filepath.Join(path, ".git"))
	if err != nil {
		return false
	}
	return info.IsDir()
}

func gitClone(ctx context.Context, url, path string) error {
	_, err := gitCmd(ctx, filepath.Dir(path), "clone", url, path)
	return err
}

func gitInit(path string) error {
	_, err := gitCmd(context.Background(), path, "init")
	return err
}

func gitAdd(path string) error {
	_, err := gitCmd(context.Background(), path, "add", ".")
	return err
}

func gitCommit(path, message string) (bool, error) {
	out, err := gitCmd(context.Background(), path, "commit", "-m", message)
	if err != nil {
		// "nothing to commit" is not an error
		if strings.Contains(err.Error(), "nothing to commit") {
			return false, nil
		}
		return false, err
	}
	_ = out
	return true, nil
}

func gitPush(path, branch string) error {
	_, err := gitCmd(context.Background(), path, "push", "origin", branch)
	return err
}

func gitPushForceLease(path, branch string) error {
	_, err := gitCmd(context.Background(), path, "push", "--force-with-lease", "origin", branch)
	return err
}

func gitPullRebase(path, branch string) error {
	_, err := gitCmd(context.Background(), path, "pull", "--rebase", "origin", branch)
	return err
}

func gitFetch(path string) error {
	_, err := gitCmd(context.Background(), path, "fetch", "origin")
	return err
}

func gitStatusPorcelain(path string) (string, error) {
	out, err := gitCmd(context.Background(), path, "status", "--porcelain")
	if err != nil {
		return "", err
	}
	return out, nil
}

func gitCurrentBranch(path string) (string, error) {
	out, err := gitCmd(context.Background(), path, "rev-parse", "--abbrev-ref", "HEAD")
	if err != nil {
		return "", err
	}
	if out == "" || out == "HEAD" {
		// Empty repo: HEAD not yet created. Use default branch config.
		return gitDefaultBranch(path), nil
	}
	return out, nil
}

func gitDefaultBranch(path string) string {
	out, err := gitCmd(context.Background(), path, "config", "--default", "main", "--get", "init.defaultBranch")
	if err != nil || out == "" {
		return "main"
	}
	return out
}

func gitShortHash(path string) (string, error) {
	out, err := gitCmd(context.Background(), path, "rev-parse", "--short", "HEAD")
	if err != nil {
		return "", err
	}
	return out, nil
}

func gitRemoteGetURL(path string) (string, error) {
	out, err := gitCmd(context.Background(), path, "remote", "get-url", "origin")
	if err != nil {
		return "", err
	}
	return out, nil
}

func gitRemoteAdd(path, url string) error {
	// Ignore error if remote already exists
	out, err := gitCmd(context.Background(), path, "remote", "add", "origin", url)
	if err != nil && !strings.Contains(err.Error(), "already exists") {
		return err
	}
	_ = out
	return nil
}

func gitRemoteSetURL(path, url string) error {
	_, err := gitCmd(context.Background(), path, "remote", "set-url", "origin", url)
	return err
}

func gitSetConfig(path, key, value string) error {
	_, err := gitCmd(context.Background(), path, "config", key, value)
	return err
}

func gitSetConfigGlobal(key, value string) error {
	cmd := exec.Command("git", "config", "--global", key, value)
	cmd.Env = append(os.Environ(), "GIT_TERMINAL_PROMPT=0")
	_, err := cmd.Output()
	return err
}
