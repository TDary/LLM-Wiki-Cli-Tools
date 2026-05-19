package cmd

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"

	"wiki-tools/internal/wiki"
)

func init() { Register("trace", traceCmd) }

func traceCmd(args []string) {
	format := "table"
	pretty := false
	page := ""
	wikiPath := ""

	for i := 0; i < len(args); i++ {
		switch args[i] {
		case "-h", "--help":
			fmt.Println("用法: wiki-tools trace <page> [WIKI_PATH] [--format table|json] [--pretty]")
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

	graph := wiki.BuildLinkGraph(p)

	inbound := make(map[string][]string)
	for source, targets := range graph.Outbound {
		for _, t := range targets {
			inbound[t] = append(inbound[t], source)
		}
	}

	doc, ok := graph.DocInfo[targetStem]
	if !ok {
		fmt.Fprintf(os.Stderr, "❌ 未找到页面: %s\n", page)
		os.Exit(1)
	}

	upstream := wiki.TraceUpstream(targetStem, graph.Outbound, make(map[string]bool), 1)
	downstream := wiki.TraceDownstream(targetStem, inbound, make(map[string]bool), 1)

	if format == "json" {
		meta := wiki.ReadSchemaMeta(p)
		type EnrichedTrace struct {
			wiki.TraceResult
			Title    string `json:"title"`
			File     string `json:"file"`
			Category string `json:"category"`
		}
		enrich := func(items []wiki.TraceResult) []EnrichedTrace {
			var result []EnrichedTrace
			for _, item := range items {
				info := graph.DocInfo[item.Stem]
				result = append(result, EnrichedTrace{
					TraceResult: item,
					Title:       info.Title,
					File:        info.File,
					Category:    info.Category,
				})
			}
			return result
		}
		output := map[string]interface{}{
			"wiki":       meta,
			"page":       page,
			"document":   doc,
			"upstream":   enrich(upstream),
			"downstream": enrich(downstream),
		}
		enc := json.NewEncoder(os.Stdout)
		if pretty {
			enc.SetIndent("", "  ")
		}
		enc.Encode(output)
		return
	}

	fmt.Printf("\n🔍 溯源: [[%s]]\n", page)
	fmt.Printf("   %s  (%s)\n\n", doc.Title, doc.File)

	fmt.Println("   ── 上游（该页面引用了）──")
	if len(upstream) == 0 {
		fmt.Println("   无上游引用。")
	} else {
		seen := make(map[string]bool)
		for _, item := range upstream {
			if seen[item.Stem] {
				continue
			}
			seen[item.Stem] = true
			info, ok := graph.DocInfo[item.Stem]
			indent := "   " + strings.Repeat("  ", item.Depth)
			marker := "←"
			if item.Depth > 1 {
				marker = "←" + strings.Repeat("─", item.Depth)
			}
			if ok {
				fmt.Printf(" %s%s [[%s]]  (%s)\n", indent, marker, info.Title, info.File)
			} else {
				fmt.Printf(" %s%s [[%s]]  (⚠️ 不存在)\n", indent, marker, item.Stem)
			}
		}
	}

	fmt.Println("\n   ── 下游（哪些页面引用了该页面）──")
	if len(downstream) == 0 {
		fmt.Println("   无下游引用。")
	} else {
		seen := make(map[string]bool)
		for _, item := range downstream {
			if seen[item.Stem] {
				continue
			}
			seen[item.Stem] = true
			info := graph.DocInfo[item.Stem]
			indent := "   " + strings.Repeat("  ", item.Depth)
			marker := "→"
			if item.Depth > 1 {
				marker = "→" + strings.Repeat("─", item.Depth)
			}
			fmt.Printf(" %s%s [[%s]]  (%s)\n", indent, marker, info.Title, info.File)
		}
	}

	upstreamSet := make(map[string]bool)
	for _, u := range upstream {
		upstreamSet[u.Stem] = true
	}
	downstreamSet := make(map[string]bool)
	for _, d := range downstream {
		downstreamSet[d.Stem] = true
	}
	fmt.Printf("\n   上游引用: %d 个\n", len(upstreamSet))
	fmt.Printf("   下游被引: %d 个\n", len(downstreamSet))
}
