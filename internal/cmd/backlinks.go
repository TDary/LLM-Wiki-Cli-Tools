package cmd

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"

	"wiki-tools/internal/wiki"
)

func init() { Register("backlinks", backlinksCmd) }

func backlinksCmd(args []string) {
	format := "table"
	pretty := false
	page := ""
	wikiPath := ""

	for i := 0; i < len(args); i++ {
		switch args[i] {
		case "-h", "--help":
			fmt.Println("用法: wiki-tools backlinks <page> [WIKI_PATH] [--format table|json] [--pretty]")
			os.Exit(0)
		case "--format":
			i++; if i < len(args) { format = args[i] }
		case "--pretty":
			pretty = true
		default:
			if !strings.HasPrefix(args[i], "-") {
				if page == "" {
					page = args[i]
				} else if wikiPath == "" {
					wikiPath = args[i]
				}
			}
		}
	}

	if page == "" {
		fmt.Fprintln(os.Stderr, "❌ 请指定目标页面")
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

	if strings.HasSuffix(page, ".md") {
		page = page[:len(page)-3]
	}
	targetStem := strings.ToLower(strings.ReplaceAll(strings.TrimSpace(page), " ", "-"))

	backlinks := wiki.BuildBacklinkMap(p)
	refs := backlinks[targetStem]

	if format == "json" {
		meta := wiki.ReadSchemaMeta(p)
		output := map[string]interface{}{
			"wiki":      meta,
			"page":      page,
			"total":     len(refs),
			"backlinks": refs,
		}
		enc := json.NewEncoder(os.Stdout)
		if pretty {
			enc.SetIndent("", "  ")
		}
		enc.Encode(output)
		return
	}

	fmt.Printf("\n🔗 反向链接: [[%s]]\n", page)
	fmt.Printf("   被引用次数: %d\n\n", len(refs))
	if len(refs) == 0 {
		fmt.Println("   没有找到引用此页面的文档。")
	} else {
		for _, ref := range refs {
			fmt.Printf("  📄 %s\n", ref.SourceTitle)
			fmt.Printf("     %s  (L%d)\n", ref.SourceFile, ref.Line)
			content := ref.LineContent
			if len(content) > 80 {
				content = content[:77] + "..."
			}
			fmt.Printf("     %s\n\n", content)
		}
	}
}
