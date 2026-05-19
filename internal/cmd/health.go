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

func init() { Register("health", healthCmd) }

var healthWikilinkRe = regexp.MustCompile(`\[\[(.+?)\]\]`)

func healthCmd(args []string) {
	format := "table"
	pretty := false
	wikiPath := ""

	for i := 0; i < len(args); i++ {
		switch args[i] {
		case "-h", "--help":
			fmt.Println("用法: wiki-tools health [WIKI_PATH] [--format table|json] [--pretty]")
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

	var userDocs []wiki.Doc
	for _, d := range docs {
		stem := strings.ToLower(strings.TrimSuffix(filepath.Base(d.File), ".md"))
		if !wiki.SystemFiles[stem] {
			userDocs = append(userDocs, d)
		}
	}

	existingStems := make(map[string]bool)
	for _, d := range docs {
		stem := strings.ToLower(strings.TrimSuffix(filepath.Base(d.File), ".md"))
		existingStems[stem] = true
	}

	var orphans []wiki.Doc
	for _, d := range userDocs {
		stem := strings.ToLower(strings.TrimSuffix(filepath.Base(d.File), ".md"))
		if refs, ok := backlinks[stem]; !ok || len(refs) == 0 {
			orphans = append(orphans, d)
		}
	}

	type BrokenLink struct {
		SourceFile  string `json:"source_file"`
		SourceTitle string `json:"source_title"`
		Target      string `json:"target"`
		Line        int    `json:"line"`
	}
	var brokenLinks []BrokenLink
	for _, d := range userDocs {
		matches := healthWikilinkRe.FindAllStringSubmatch(d.Text, -1)
		for _, m := range matches {
			if len(m) < 2 {
				continue
			}
			target := strings.ToLower(strings.ReplaceAll(strings.TrimSpace(m[1]), " ", "-"))
			if !existingStems[target] {
				for lineNo, line := range strings.Split(d.Text, "\n") {
					if strings.Contains(line, "[["+m[1]+"]]") {
						brokenLinks = append(brokenLinks, BrokenLink{
							SourceFile:  d.File,
							SourceTitle: d.Title,
							Target:      m[1],
							Line:        lineNo + 1,
						})
						break
					}
				}
			}
		}
	}

	var noTags []wiki.Doc
	for _, d := range userDocs {
		if len(d.Tags) == 0 {
			noTags = append(noTags, d)
		}
	}

	var lowLinks []wiki.Doc
	for _, d := range userDocs {
		if d.LinksCount < 2 {
			lowLinks = append(lowLinks, d)
		}
	}

	total := len(userDocs)
	if total == 0 {
		total = 1
	}
	deductions := len(orphans)*3 + len(brokenLinks)*5 + len(noTags)*1 + len(lowLinks)*2
	score := 100 - deductions*100/(total*4)
	if score < 0 {
		score = 0
	}
	if score > 100 {
		score = 100
	}

	if format == "json" {
		meta := wiki.ReadSchemaMeta(p)
		output := map[string]interface{}{
			"wiki":            meta,
			"score":           score,
			"total_documents": len(userDocs),
			"checks": map[string]interface{}{
				"orphans":      map[string]interface{}{"count": len(orphans), "items": orphans},
				"broken_links": map[string]interface{}{"count": len(brokenLinks), "items": brokenLinks},
				"no_tags":      map[string]interface{}{"count": len(noTags), "items": noTags},
				"low_links":    map[string]interface{}{"count": len(lowLinks), "items": lowLinks},
			},
		}
		enc := json.NewEncoder(os.Stdout)
		if pretty {
			enc.SetIndent("", "  ")
		}
		enc.Encode(output)
		return
	}

	statusIcon := func(count, threshold int) string {
		if count == 0 {
			return "✅"
		} else if count <= threshold {
			return "⚠️"
		}
		return "❌"
	}

	meta := wiki.ReadSchemaMeta(p)
	fmt.Printf("\n🏥 %s — 知识库健康报告\n", meta.Name)
	fmt.Printf("   文档总数: %d\n\n", len(userDocs))
	fmt.Printf("   %s 孤立文档:     %d 篇\n", statusIcon(len(orphans), 5), len(orphans))
	fmt.Printf("   %s 断链:         %d 处\n", statusIcon(len(brokenLinks), 0), len(brokenLinks))
	fmt.Printf("   %s 无标签文档:   %d 篇\n", statusIcon(len(noTags), 5), len(noTags))
	fmt.Printf("   %s 链接不足:     %d 篇 (< 2 条链接)\n", statusIcon(len(lowLinks), 5), len(lowLinks))
	fmt.Printf("\n   健康评分: %d/100\n", score)

	if len(brokenLinks) > 0 {
		fmt.Printf("\n   ── 断链详情 ──\n")
		limit := 10
		if len(brokenLinks) < limit {
			limit = len(brokenLinks)
		}
		for _, bl := range brokenLinks[:limit] {
			fmt.Printf("   ❌ %s (L%d): [[%s]] → 不存在\n", bl.SourceFile, bl.Line, bl.Target)
		}
		if len(brokenLinks) > 10 {
			fmt.Printf("   ... 共 %d 处断链\n", len(brokenLinks))
		}
	}

	if len(orphans) > 0 {
		fmt.Printf("\n   ── 孤立文档 ──\n")
		limit := 10
		if len(orphans) < limit {
			limit = len(orphans)
		}
		for _, d := range orphans[:limit] {
			fmt.Printf("   📄 %s  (%s)\n", d.Title, d.File)
		}
		if len(orphans) > 10 {
			fmt.Printf("   ... 共 %d 篇孤立文档\n", len(orphans))
		}
	}

	var issues []string
	if len(brokenLinks) > 0 {
		issues = append(issues, "修复断链（目标页面不存在）")
	}
	if len(orphans) > 0 {
		issues = append(issues, "为孤立文档添加 [[wikilinks]]")
	}
	if len(noTags) > 0 {
		issues = append(issues, "给无标签文档添加 frontmatter tags")
	}
	if len(lowLinks) > 0 {
		issues = append(issues, "为链接不足的文档补充交叉引用（建议 >= 2 条）")
	}

	if len(issues) > 0 {
		fmt.Println("\n   💡 建议:")
		for i, issue := range issues {
			fmt.Printf("      %d. %s\n", i+1, issue)
		}
	} else {
		fmt.Println("\n   🎉 知识库状态良好，没有发现明显问题。")
	}
}
