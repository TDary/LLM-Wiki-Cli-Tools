package cmd

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"

	"wiki-tools/internal/wiki"
)

func init() { Register("list", listCmd) }

func listCmd(args []string) {
	format := "table"
	category := ""
	tags := ""
	includeRaw := false
	pretty := false
	wikiPath := ""

	for i := 0; i < len(args); i++ {
		switch args[i] {
		case "-h", "--help":
			printListHelp()
			os.Exit(0)
		case "--format":
			i++; if i < len(args) { format = args[i] }
		case "--category":
			i++; if i < len(args) { category = args[i] }
		case "--tags":
			i++; if i < len(args) { tags = args[i] }
		case "--include-raw":
			includeRaw = true
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

	if category != "" {
		var filtered []wiki.Doc
		for _, d := range docs {
			if d.Category == category {
				filtered = append(filtered, d)
			}
		}
		docs = filtered
	} else if !includeRaw {
		var filtered []wiki.Doc
		for _, d := range docs {
			if d.Category != "raw" {
				filtered = append(filtered, d)
			}
		}
		docs = filtered
	}

	if tags != "" {
		filterTags := make(map[string]bool)
		for _, t := range strings.Split(tags, ",") {
			t = strings.TrimSpace(strings.ToLower(t))
			if t != "" {
				filterTags[t] = true
			}
		}
		var filtered []wiki.Doc
		for _, d := range docs {
			match := false
			for _, t := range d.Tags {
				if filterTags[strings.ToLower(t)] {
					match = true
					break
				}
			}
			if match {
				filtered = append(filtered, d)
			}
		}
		docs = filtered
	}

	if format == "json" {
		meta := wiki.ReadSchemaMeta(p)
		output := map[string]interface{}{
			"wiki":      meta,
			"total":     len(docs),
			"documents": docs,
		}
		enc := json.NewEncoder(os.Stdout)
		if pretty {
			enc.SetIndent("", "  ")
		}
		enc.Encode(output)
		return
	}

	meta := wiki.ReadSchemaMeta(p)
	fmt.Printf("\n📚 %s — %s\n", meta.Name, meta.Domain)
	fmt.Printf("   共 %d 篇文档\n\n", len(docs))

	currentCat := ""
	for _, d := range docs {
		if d.Category != currentCat {
			currentCat = d.Category
			fmt.Printf("  [%s] (%s/)\n", d.CategoryLabel, d.Category)
		}
		tagsStr := ""
		if len(d.Tags) > 0 {
			tagsStr = " [" + strings.Join(d.Tags, ", ") + "]"
		}
		linksStr := ""
		if d.LinksCount > 0 {
			linksStr = fmt.Sprintf("  🔗%d", d.LinksCount)
		}
		readonly := ""
		if d.Category == "raw" {
			readonly = "  🔒只读"
		}
		fmt.Printf("    %s\n", d.Title)
		fmt.Printf("    ├─ %s  (%dB, %s)%s%s%s\n\n", d.File, d.Size, d.Modified, tagsStr, linksStr, readonly)
	}
}

func printListHelp() {
	fmt.Println("用法: wiki-tools list [WIKI_PATH] [OPTIONS]")
	fmt.Println()
	fmt.Println("选项:")
	fmt.Println("  --format table|json   输出格式（默认: table）")
	fmt.Println("  --category CAT        过滤指定目录")
	fmt.Println("  --tags TAG1,TAG2      按标签过滤（逗号分隔）")
	fmt.Println("  --include-raw         包含原始资料目录（默认排除）")
	fmt.Println("  --pretty              JSON 缩进美化")
	fmt.Println("  -h, --help            显示帮助")
}
