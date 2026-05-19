package cmd

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"wiki-tools/internal/wiki"
)

func init() { Register("fix", fixCmd) }

var fixWikilinkRe = regexp.MustCompile(`\[\[(.+?)\]\]`)

type Fix struct {
	Type       string `json:"type"`
	File       string `json:"file"`
	Original   string `json:"original"`
	TargetStem string `json:"target_stem"`
	Suggestion string `json:"suggestion"`
	Action     string `json:"action"`
}

func fixCmd(args []string) {
	format := "table"
	pretty := false
	apply := false
	wikiPath := ""

	for i := 0; i < len(args); i++ {
		switch args[i] {
		case "-h", "--help":
			fmt.Println("用法: wiki-tools fix [WIKI_PATH] [--apply] [--format table|json] [--pretty]")
			os.Exit(0)
		case "--format":
			i++; if i < len(args) { format = args[i] }
		case "--pretty":
			pretty = true
		case "--apply":
			apply = true
		default:
			if !strings.HasPrefix(args[i], "-") && wikiPath == "" {
				wikiPath = args[i]
			}
		}
	}

	if wikiPath == "" {
		wikiPath = "."
	}
	p, err := AbsPath(wikiPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "❌ %v\n", err)
		os.Exit(1)
	}
	wiki.RequireWiki(p)

	docs := wiki.CollectDocuments(p)
	graph := wiki.BuildLinkGraph(p)
	existingStems := make(map[string]bool)
	for stem := range graph.DocInfo {
		existingStems[stem] = true
	}

	var fixes []Fix
	seen := make(map[string]bool)

	for _, d := range docs {
		if d.Category == "raw" {
			continue
		}
		matches := fixWikilinkRe.FindAllStringSubmatch(d.Text, -1)
		for _, m := range matches {
			if len(m) < 2 {
				continue
			}
			original := m[1]
			targetStem := strings.ToLower(strings.ReplaceAll(strings.TrimSpace(original), " ", "-"))
			if !existingStems[targetStem] {
				key := "broken:" + d.File + ":" + original
				if seen[key] {
					continue
				}
				seen[key] = true
				candidates := make([]string, 0, len(existingStems))
				for s := range existingStems {
					candidates = append(candidates, s)
				}
				closest, _ := wiki.FindClosest(targetStem, candidates)
				action := fmt.Sprintf("[[%s]] → (删除或创建目标页面)", original)
				if closest != "" {
					info := graph.DocInfo[closest]
					action = fmt.Sprintf("[[%s]] → [[%s]]", original, info.Title)
				}
				fixes = append(fixes, Fix{
					Type:       "broken_link",
					File:       d.File,
					Original:   original,
					TargetStem: targetStem,
					Suggestion: closest,
					Action:     action,
				})
			}
		}
	}

	for _, d := range docs {
		if d.Category == "raw" {
			continue
		}
		matches := fixWikilinkRe.FindAllStringSubmatch(d.Text, -1)
		for _, m := range matches {
			if len(m) < 2 {
				continue
			}
			original := m[1]
			if strings.Contains(original, "_") {
				normalized := strings.ReplaceAll(original, "_", "-")
				key := "norm:" + d.File + ":" + original
				if seen[key] {
					continue
				}
				seen[key] = true
				fixes = append(fixes, Fix{
					Type:       "normalize",
					File:       d.File,
					Original:   original,
					TargetStem: strings.ToLower(strings.ReplaceAll(normalized, " ", "-")),
					Suggestion: normalized,
					Action:     fmt.Sprintf("[[%s]] → [[%s]]", original, normalized),
				})
			}
		}
	}

	if format == "json" {
		meta := wiki.ReadSchemaMeta(p)
		output := map[string]interface{}{
			"wiki":    meta,
			"total":   len(fixes),
			"dry_run": !apply,
			"fixes":   fixes,
		}
		enc := json.NewEncoder(os.Stdout)
		if pretty {
			enc.SetIndent("", "  ")
		}
		enc.Encode(output)
		return
	}

	mode := "预览"
	if apply {
		mode = "执行"
	}
	fmt.Printf("\n🔧 自愈检查 — %s模式\n", mode)
	fmt.Printf("   发现 %d 个可修复项\n\n", len(fixes))

	if len(fixes) == 0 {
		fmt.Println("   ✅ 没有发现可自动修复的结构问题。")
		return
	}

	var broken, norm []Fix
	for _, f := range fixes {
		if f.Type == "broken_link" {
			broken = append(broken, f)
		} else {
			norm = append(norm, f)
		}
	}

	if len(broken) > 0 {
		fmt.Printf("   ── 断链修复 (%d 处) ──\n", len(broken))
		for _, f := range broken {
			if apply {
				fp := filepath.Join(p, f.File)
				data, err := os.ReadFile(fp)
				if err != nil {
					continue
				}
				text := string(data)
				if f.Suggestion != "" {
					info := graph.DocInfo[f.Suggestion]
					newText := strings.ReplaceAll(text, "[["+f.Original+"]]", "[["+info.Title+"]]")
					os.WriteFile(fp, []byte(newText), 0644)
					fmt.Printf("   ✅ %s: %s\n", f.File, f.Action)
				} else {
					fmt.Printf("   ⏭️  %s: %s (需手动处理)\n", f.File, f.Action)
				}
			} else {
				status := "✅ 可修复"
				if f.Suggestion == "" {
					status = "⚠️  需手动"
				}
				fmt.Printf("   %s  %s: %s\n", status, f.File, f.Action)
			}
		}
		fmt.Println()
	}

	if len(norm) > 0 {
		fmt.Printf("   ── 命名规范化 (%d 处) ──\n", len(norm))
		for _, f := range norm {
			if apply {
				fp := filepath.Join(p, f.File)
				data, err := os.ReadFile(fp)
				if err != nil {
					continue
				}
				text := string(data)
				newText := strings.ReplaceAll(text, "[["+f.Original+"]]", "[["+f.Suggestion+"]]")
				os.WriteFile(fp, []byte(newText), 0644)
				fmt.Printf("   ✅ %s: %s\n", f.File, f.Action)
			} else {
				fmt.Printf("   ✅ 可修复  %s: %s\n", f.File, f.Action)
			}
		}
		fmt.Println()
	}

	if !apply {
		autoCount := 0
		for _, f := range fixes {
			if f.Suggestion != "" {
				autoCount++
			}
		}
		manualCount := len(fixes) - autoCount
		fmt.Printf("   💡 %d 项可自动修复，%d 项需手动处理。\n", autoCount, manualCount)
		fmt.Println("      使用 --apply 执行自动修复。")
	}
}
