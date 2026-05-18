package git

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

const timeout = 120 * time.Second

func run(ctx context.Context, dir string, args ...string) (string, error) {
	if ctx == nil {
		ctx = context.Background()
	}
	ctx, cancel := context.WithTimeout(ctx, timeout)
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
			return "", fmt.Errorf("git %s: timed out after %v", args[0], timeout)
		}
		return "", fmt.Errorf("git %s: %w\n%s", strings.Join(args, " "), err, out)
	}
	return strings.TrimSpace(string(out)), nil
}

func runStderr(dir string, args ...string) (string, string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
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
	return strings.TrimSpace(stdout.String()), strings.TrimSpace(stderr.String()), err
}

// IsRepo checks if path is a git repository.
func IsRepo(path string) bool {
	info, err := os.Stat(filepath.Join(path, ".git"))
	if err != nil {
		return false
	}
	return info.IsDir()
}

// Clone clones a remote repository.
func Clone(ctx context.Context, url, path string) error {
	_, err := run(ctx, filepath.Dir(path), "clone", url, path)
	return err
}

// Init initializes a new git repository.
func Init(path string) error {
	_, err := run(context.Background(), path, "init")
	return err
}

// Add stages all files.
func Add(path string) error {
	_, err := run(context.Background(), path, "add", ".")
	return err
}

// Commit creates a commit. Returns false if nothing to commit.
func Commit(path, message string) (bool, error) {
	_, err := run(context.Background(), path, "commit", "-m", message)
	if err != nil {
		if strings.Contains(err.Error(), "nothing to commit") {
			return false, nil
		}
		return false, err
	}
	return true, nil
}

// Push pushes to origin.
func Push(path, branch string) error {
	_, err := run(context.Background(), path, "push", "origin", branch)
	return err
}

// PushForceLease force-pushes with lease.
func PushForceLease(path, branch string) error {
	_, err := run(context.Background(), path, "push", "--force-with-lease", "origin", branch)
	return err
}

// PullRebase pulls with rebase from origin.
func PullRebase(path, branch string) error {
	_, err := run(context.Background(), path, "pull", "--rebase", "origin", branch)
	return err
}

// Fetch fetches from origin.
func Fetch(path string) error {
	_, err := run(context.Background(), path, "fetch", "origin")
	return err
}

// StatusPorcelain returns git status --porcelain output.
func StatusPorcelain(path string) (string, error) {
	return run(context.Background(), path, "status", "--porcelain")
}

// CurrentBranch returns the current branch name.
func CurrentBranch(path string) (string, error) {
	out, err := run(context.Background(), path, "rev-parse", "--abbrev-ref", "HEAD")
	if err != nil {
		return "", err
	}
	if out == "" || out == "HEAD" {
		return DefaultBranch(path), nil
	}
	return out, nil
}

// DefaultBranch returns the default branch from git config.
func DefaultBranch(path string) string {
	out, err := run(context.Background(), path, "config", "--default", "main", "--get", "init.defaultBranch")
	if err != nil || out == "" {
		return "main"
	}
	return out
}

// ShortHash returns the short commit hash of HEAD.
func ShortHash(path string) (string, error) {
	return run(context.Background(), path, "rev-parse", "--short", "HEAD")
}

// RemoteGetURL returns the origin remote URL.
func RemoteGetURL(path string) (string, error) {
	return run(context.Background(), path, "remote", "get-url", "origin")
}

// RemoteAdd adds an origin remote.
func RemoteAdd(path, url string) error {
	out, err := run(context.Background(), path, "remote", "add", "origin", url)
	if err != nil && !strings.Contains(err.Error(), "already exists") {
		return err
	}
	_ = out
	return nil
}

// RemoteSetURL sets the origin remote URL.
func RemoteSetURL(path, url string) error {
	_, err := run(context.Background(), path, "remote", "set-url", "origin", url)
	return err
}

// SetConfig sets a git config value in the repo.
func SetConfig(path, key, value string) error {
	_, err := run(context.Background(), path, "config", key, value)
	return err
}

// SetConfigGlobal sets a global git config value.
func SetConfigGlobal(key, value string) error {
	cmd := exec.Command("git", "config", "--global", key, value)
	cmd.Env = append(os.Environ(), "GIT_TERMINAL_PROMPT=0")
	_, err := cmd.Output()
	return err
}
