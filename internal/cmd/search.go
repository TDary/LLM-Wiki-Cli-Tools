package cmd

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"

	"wiki-tools/internal/wiki"
)

func init() { Register("search", searchCmd) }

func searchCmd(args []string) {
	format := "table"
	noRaw := false
	pretty := false
	regex := false
	keyword := ""
	wikiPath := ""

	for i := 0; i < len(args); i++ {
		switch args[i] {
		case "-h", "--help":
			fmt.Println("用法: wiki-tools search <keyword> [WIKI_PATH] [--format table|json] [--no-raw] [--regex] [--pretty]")
			os.Exit(0)
		case "--format":
			i++; if i < len(args) { format = args[i] }
		case "--no-raw":
			noRaw = true
		case "--pretty":
			pretty = true
		case "--regex":
			regex = true
		default:
			if !strings.HasPrefix(args[i], "-") {
				if keyword == "" {
					keyword = args[i]
				} else if wikiPath == "" {
					wikiPath = args[i]
				}
			}
		}
	}

	if keyword == "" {
		fmt.Fprintln(os.Stderr, "❌ 请指定搜索关键词")
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

	docs := wiki.CollectDocuments(p)
	if noRaw {
		var filtered []wiki.Doc
		for _, d := range docs {
			if d.Category != "raw" {
				filtered = append(filtered, d)
			}
		}
		docs = filtered
	}

	var results []wiki.SearchResult
	if regex {
		results, err = wiki.SearchDocumentsRegex(docs, keyword)
		if err != nil {
			fmt.Fprintf(os.Stderr, "❌ %v\n", err)
			os.Exit(1)
		}
	} else {
		results = wiki.SearchDocuments(docs, keyword)
	}

	if format == "json" {
		meta := wiki.ReadSchemaMeta(p)
		output := map[string]interface{}{
			"wiki":    meta,
			"keyword": keyword,
			"total":   len(results),
			"results": results,
		}
		enc := json.NewEncoder(os.Stdout)
		if pretty {
			enc.SetIndent("", "  ")
		}
		enc.Encode(output)
		return
	}

	fmt.Printf("\n🔍 搜索: \"%s\"\n", keyword)
	fmt.Printf("   匹配文档: %d 篇\n\n", len(results))
	for _, r := range results {
		fmt.Printf("  📄 %s\n", r.Title)
		fmt.Printf("     %s  (%s)\n", r.File, r.Category)
		limit := 5
		if len(r.Matches) < limit {
			limit = len(r.Matches)
		}
		for _, m := range r.Matches[:limit] {
			prefix := fmt.Sprintf("L%d", m.Line)
			if m.Line == 0 {
				prefix = "标题"
			}
			content := m.Content
			if len(content) > 80 {
				content = content[:77] + "..."
			}
			fmt.Printf("     %s: %s\n", prefix, content)
		}
		if len(r.Matches) > 5 {
			fmt.Printf("     ... 共 %d 处匹配\n", r.MatchCount)
		}
		fmt.Println()
	}
}
