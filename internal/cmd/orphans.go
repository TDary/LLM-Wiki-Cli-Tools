package cmd

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"wiki-tools/internal/wiki"
)

func init() { Register("orphans", orphansCmd) }

func orphansCmd(args []string) {
	format := "table"
	pretty := false
	wikiPath := ""

	for i := 0; i < len(args); i++ {
		switch args[i] {
		case "-h", "--help":
			fmt.Println("用法: wiki-tools orphans [WIKI_PATH] [--format table|json] [--pretty]")
			os.Exit(0)
		case "--format":
			i++; if i < len(args) { format = args[i] }
		case "--pretty":
			pretty = true
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
	backlinks := wiki.BuildBacklinkMap(p)

	var orphans []wiki.Doc
	for _, doc := range docs {
		if doc.Category == "raw" {
			continue
		}
		stem := strings.ToLower(strings.TrimSuffix(filepath.Base(doc.File), ".md"))
		if wiki.SystemFiles[stem] {
			continue
		}
		if refs, ok := backlinks[stem]; !ok || len(refs) == 0 {
			orphans = append(orphans, doc)
		}
	}

	if format == "json" {
		meta := wiki.ReadSchemaMeta(p)
		output := map[string]interface{}{
			"wiki":    meta,
			"total":   len(orphans),
			"orphans": orphans,
		}
		enc := json.NewEncoder(os.Stdout)
		if pretty {
			enc.SetIndent("", "  ")
		}
		enc.Encode(output)
		return
	}

	fmt.Printf("\n🏝️  孤立文档检测\n")
	fmt.Printf("   文档总数: %d\n", len(docs))
	fmt.Printf("   孤立文档: %d\n\n", len(orphans))
	if len(orphans) == 0 {
		fmt.Println("   ✅ 没有发现孤立文档，所有文档都有入站链接。")
	} else {
		for _, d := range orphans {
			fmt.Printf("  📄 %s\n", d.Title)
			fmt.Printf("     %s  (%s)\n", d.File, d.Category)
			if d.LinksCount > 0 {
				fmt.Printf("     出站链接: %d 个（但无文档链接到此页面）\n", d.LinksCount)
			} else {
				fmt.Printf("     ⚠️  无出站链接且无入站链接\n")
			}
		}
		fmt.Println()
		fmt.Println("💡 建议: 在相关文档中添加 [[wikilinks]] 指向孤立文档，或将它们合并到其他页面。")
	}
}
