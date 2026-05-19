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

func init() { Register("rename", renameCmd) }

var renameWikilinkRe = regexp.MustCompile(`\[\[(.+?)\]\]`)

// titleCase capitalizes the first letter of each word (replaces deprecated strings.Title).
func titleCase(s string) string {
	words := strings.Split(s, " ")
	for i, w := range words {
		if len(w) > 0 {
			words[i] = strings.ToUpper(w[:1]) + w[1:]
		}
	}
	return strings.Join(words, " ")
}

func renameCmd(args []string) {
	format := "table"
	pretty := false
	dryRun := true // default to preview mode
	oldName := ""
	newName := ""
	wikiPath := ""

	for i := 0; i < len(args); i++ {
		switch args[i] {
		case "-h", "--help":
			fmt.Println("用法: wiki-tools rename <old-name> <new-name> [WIKI_PATH] [--dry-run] [--apply] [--format table|json] [--pretty]")
			os.Exit(0)
		case "--format":
			i++; if i < len(args) { format = args[i] }
		case "--pretty":
			pretty = true
		case "--dry-run":
			dryRun = true
		case "--apply":
			dryRun = false
		default:
			if !strings.HasPrefix(args[i], "-") {
				if oldName == "" {
					oldName = args[i]
				} else if newName == "" {
					newName = args[i]
				} else if wikiPath == "" {
					wikiPath = args[i]
				}
			}
		}
	}

	if oldName == "" || newName == "" {
		fmt.Fprintln(os.Stderr, "❌ 请指定旧名称和新名称")
		os.Exit(1)
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

	// Normalize stems
	oldStem := strings.ToLower(strings.ReplaceAll(strings.TrimSpace(oldName), " ", "-"))
	newStem := strings.ToLower(strings.ReplaceAll(strings.TrimSpace(newName), " ", "-"))

	// Find the source file
	docs := wiki.CollectDocuments(p)
	var sourceDoc *wiki.Doc
	for _, d := range docs {
		stem := strings.ToLower(strings.TrimSuffix(filepath.Base(d.File), ".md"))
		if stem == oldStem {
			doc := d
			sourceDoc = &doc
			break
		}
	}
	if sourceDoc == nil {
		fmt.Fprintf(os.Stderr, "❌ 未找到文档: %s\n", oldName)
		os.Exit(1)
	}

	// Determine old title and new title
	oldTitle := sourceDoc.Title
	newTitle := titleCase(strings.ReplaceAll(newStem, "-", " "))

	// Find all references to old name
	type RenameAction struct {
		Type     string `json:"type"`
		File     string `json:"file"`
		Original string `json:"original"`
		New      string `json:"new"`
	}
	var actions []RenameAction

	// 1. Rename file action
	relOld := sourceDoc.File
	relNew := filepath.Join(filepath.Dir(relOld), newStem+".md")
	actions = append(actions, RenameAction{
		Type:     "rename_file",
		File:     relOld,
		Original: relOld,
		New:      relNew,
	})

	// 2. Scan all docs for wikilink references
	for _, d := range docs {
		matches := renameWikilinkRe.FindAllStringSubmatch(d.Text, -1)
		for _, m := range matches {
			if len(m) < 2 {
				continue
			}
			linkTarget := strings.ToLower(strings.ReplaceAll(strings.TrimSpace(m[1]), " ", "-"))
			if linkTarget == oldStem {
				actions = append(actions, RenameAction{
					Type:     "update_link",
					File:     d.File,
					Original: "[[" + m[1] + "]]",
					New:      "[[" + newTitle + "]]",
				})
			}
		}
	}

	// 3. Update internal heading if it matches old title
	for _, line := range strings.Split(sourceDoc.Text, "\n") {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "# ") && !strings.HasPrefix(trimmed, "## ") {
			heading := strings.TrimPrefix(trimmed, "# ")
			if heading == oldTitle {
				actions = append(actions, RenameAction{
					Type:     "update_heading",
					File:     relOld,
					Original: "# " + oldTitle,
					New:      "# " + newTitle,
				})
			}
		}
	}

	if format == "json" {
		meta := wiki.ReadSchemaMeta(p)
		output := map[string]interface{}{
			"wiki":    meta,
			"old":     oldName,
			"new":     newName,
			"dry_run": dryRun,
			"total":   len(actions),
			"actions": actions,
		}
		enc := json.NewEncoder(os.Stdout)
		if pretty {
			enc.SetIndent("", "  ")
		}
		enc.Encode(output)
		return
	}

	fmt.Printf("\n📝 重命名: [[%s]] → [[%s]]\n", oldTitle, newTitle)
	fmt.Printf("   影响 %d 处\n\n", len(actions))

	if len(actions) == 0 {
		fmt.Println("   ✅ 无需修改。")
		return
	}

	for _, a := range actions {
		fmt.Printf("   %s: %s → %s\n", a.Type, a.Original, a.New)
	}

	if !dryRun {
		// Actually perform the rename
		// 1. Update links in all files FIRST (before renaming source file)
		filesToUpdate := make(map[string]bool)
		for _, a := range actions {
			if a.Type == "update_link" || a.Type == "update_heading" {
				filesToUpdate[a.File] = true
			}
		}

		for f := range filesToUpdate {
			fp := filepath.Join(p, f)
			data, err := os.ReadFile(fp)
			if err != nil {
				continue
			}
			text := string(data)
			for _, a := range actions {
				if a.File == f {
					text = strings.ReplaceAll(text, a.Original, a.New)
				}
			}
			os.WriteFile(fp, []byte(text), 0644)
			fmt.Printf("   ✅ 已更新: %s\n", f)
		}

		// 2. Rename file AFTER content updates
		oldPath := filepath.Join(p, relOld)
		newPath := filepath.Join(p, relNew)
		if err := os.Rename(oldPath, newPath); err != nil {
			fmt.Fprintf(os.Stderr, "\n❌ 重命名文件失败: %v\n", err)
			os.Exit(1)
		}
		fmt.Printf("\n   ✅ 文件已重命名: %s → %s\n", relOld, relNew)
		fmt.Printf("\n   重命名完成！\n")
	} else {
		fmt.Printf("\n   💡 使用 --apply 执行重命名。\n")
	}
}
