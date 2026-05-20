package cmd

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
	"time"

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

	// Read configurable weights
	healthConfig := wiki.ReadHealthConfig(p)
	w := healthConfig.Weights

	var userDocs []wiki.Doc
	for _, d := range docs {
		if d.Category == "raw" {
			continue
		}
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
	type SelfLink struct {
		File  string `json:"file"`
		Title string `json:"title"`
		Line  int    `json:"line"`
		Link  string `json:"link"`
	}
	var brokenLinks []BrokenLink
	var selfLinks []SelfLink

	// Single pass: detect broken links and self-links with one line split per doc
	for _, d := range userDocs {
		selfStem := strings.ToLower(strings.TrimSuffix(filepath.Base(d.File), ".md"))
		lines := strings.Split(d.Text, "\n")

		// Broken links
		matches := healthWikilinkRe.FindAllStringSubmatch(d.Text, -1)
		for _, m := range matches {
			if len(m) < 2 {
				continue
			}
			target := strings.ToLower(strings.ReplaceAll(strings.TrimSpace(m[1]), " ", "-"))
			if !existingStems[target] {
				for lineNo, line := range lines {
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

		// Self-links
		for lineNo, line := range lines {
			lineMatches := healthWikilinkRe.FindAllStringSubmatch(line, -1)
			for _, m := range lineMatches {
				if len(m) < 2 {
					continue
				}
				target := strings.ToLower(strings.ReplaceAll(strings.TrimSpace(m[1]), " ", "-"))
				if target == selfStem {
					selfLinks = append(selfLinks, SelfLink{
						File:  d.File,
						Title: d.Title,
						Line:  lineNo + 1,
						Link:  m[1],
					})
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

	var emptyDocs []wiki.Doc
	for _, d := range userDocs {
		if len(strings.TrimSpace(d.Text)) < 50 {
			emptyDocs = append(emptyDocs, d)
		}
	}

	// Run custom checks
	type CustomCheckResult struct {
		Name        string   `json:"name"`
		Description string   `json:"description"`
		Weight      int      `json:"weight"`
		Issues      []string `json:"issues"`
		Count       int      `json:"count"`
	}
	customChecks := wiki.ReadCustomChecks(p)
	var customResults []CustomCheckResult
	customDeduction := 0

	for _, check := range customChecks {
		result := CustomCheckResult{
			Name:        check.Name,
			Description: check.Description,
			Weight:      check.Weight,
		}

		if check.Command != "" {
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			var cmd *exec.Cmd
			if runtime.GOOS == "windows" {
				cmd = exec.CommandContext(ctx, "cmd", "/c", check.Command)
			} else {
				cmd = exec.CommandContext(ctx, "sh", "-c", check.Command)
			}
			cmd.Dir = p
			var stdout, stderr bytes.Buffer
			cmd.Stdout = &stdout
			cmd.Stderr = &stderr
			err := cmd.Run()
			cancel()

			if err != nil && ctx.Err() == context.DeadlineExceeded {
				result.Issues = []string{"命令超时（5 秒）"}
				result.Count = 1
			} else if stdout.Len() > 0 {
				lines := strings.Split(strings.TrimSpace(stdout.String()), "\n")
				for _, line := range lines {
					line = strings.TrimSpace(line)
					if line != "" {
						result.Issues = append(result.Issues, line)
					}
				}
				result.Count = len(result.Issues)
			}

			if result.Count > 0 {
				customDeduction += result.Count * check.Weight
			}
		}

		customResults = append(customResults, result)
	}

	// Calculate score with configurable weights and sum of weights
	total := len(userDocs)
	if total == 0 {
		total = 1
	}
	sumWeights := w["orphan"] + w["broken_link"] + w["no_tag"] + w["low_link"] + w["empty_doc"] + w["self_link"]
	if sumWeights == 0 {
		sumWeights = 6
	}
	deductions := len(orphans)*w["orphan"] + len(brokenLinks)*w["broken_link"] + len(noTags)*w["no_tag"] + len(lowLinks)*w["low_link"] + len(emptyDocs)*w["empty_doc"] + len(selfLinks)*w["self_link"]
	score := 100 - (deductions+customDeduction)*100/(total*sumWeights)
	if score < 0 {
		score = 0
	}
	if score > 100 {
		score = 100
	}

	meta := wiki.ReadSchemaMeta(p)

	if format == "json" {
		output := map[string]interface{}{
			"wiki":            meta,
			"score":           score,
			"total_documents": len(userDocs),
			"weights":         w,
			"checks": map[string]interface{}{
				"orphans":      map[string]interface{}{"count": len(orphans), "items": orphans},
				"broken_links": map[string]interface{}{"count": len(brokenLinks), "items": brokenLinks},
				"no_tags":      map[string]interface{}{"count": len(noTags), "items": noTags},
				"low_links":    map[string]interface{}{"count": len(lowLinks), "items": lowLinks},
				"empty_docs":   map[string]interface{}{"count": len(emptyDocs), "items": emptyDocs},
				"self_links":   map[string]interface{}{"count": len(selfLinks), "items": selfLinks},
				"custom":       customResults,
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

	fmt.Printf("\n🏥 %s — 知识库健康报告\n", meta.Name)
	fmt.Printf("   文档总数: %d\n\n", len(userDocs))
	fmt.Printf("   %s 孤立文档:     %d 篇 (权重 %d)\n", statusIcon(len(orphans), 5), len(orphans), w["orphan"])
	fmt.Printf("   %s 断链:         %d 处 (权重 %d)\n", statusIcon(len(brokenLinks), 0), len(brokenLinks), w["broken_link"])
	fmt.Printf("   %s 无标签文档:   %d 篇 (权重 %d)\n", statusIcon(len(noTags), 5), len(noTags), w["no_tag"])
	fmt.Printf("   %s 链接不足:     %d 篇 (< 2 条链接, 权重 %d)\n", statusIcon(len(lowLinks), 5), len(lowLinks), w["low_link"])
	fmt.Printf("   %s 空文档:       %d 篇 (< 50 字节, 权重 %d)\n", statusIcon(len(emptyDocs), 3), len(emptyDocs), w["empty_doc"])
	fmt.Printf("   %s 自引用:       %d 处 (权重 %d)\n", statusIcon(len(selfLinks), 0), len(selfLinks), w["self_link"])

	for _, cr := range customResults {
		icon := "✅"
		if cr.Count > 0 {
			icon = "⚠️"
		}
		fmt.Printf("   %s %-14s %d 处 (权重 %d)\n", icon, cr.Name+":", cr.Count, cr.Weight)
	}

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

	if len(emptyDocs) > 0 {
		fmt.Printf("\n   ── 空文档 ──\n")
		limit := 10
		if len(emptyDocs) < limit {
			limit = len(emptyDocs)
		}
		for _, d := range emptyDocs[:limit] {
			fmt.Printf("   📄 %s  (%s, %d 字节)\n", d.Title, d.File, len(d.Text))
		}
		if len(emptyDocs) > 10 {
			fmt.Printf("   ... 共 %d 篇空文档\n", len(emptyDocs))
		}
	}

	if len(selfLinks) > 0 {
		fmt.Printf("\n   ── 自引用 ──\n")
		limit := 10
		if len(selfLinks) < limit {
			limit = len(selfLinks)
		}
		for _, sl := range selfLinks[:limit] {
			fmt.Printf("   🔄 %s (L%d): [[%s]] → 自身\n", sl.File, sl.Line, sl.Link)
		}
		if len(selfLinks) > 10 {
			fmt.Printf("   ... 共 %d 处自引用\n", len(selfLinks))
		}
	}

	// Show custom check details
	for _, cr := range customResults {
		if cr.Count > 0 {
			fmt.Printf("\n   ── %s ──\n", cr.Name)
			limit := 10
			if len(cr.Issues) < limit {
				limit = len(cr.Issues)
			}
			for _, issue := range cr.Issues[:limit] {
				fmt.Printf("   ⚠️  %s\n", issue)
			}
			if len(cr.Issues) > 10 {
				fmt.Printf("   ... 共 %d 处\n", len(cr.Issues))
			}
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
	if len(emptyDocs) > 0 {
		issues = append(issues, "补充空文档内容或删除无用占位页")
	}
	if len(selfLinks) > 0 {
		issues = append(issues, "移除自引用链接（页面不应链接到自身）")
	}
	for _, cr := range customResults {
		if cr.Count > 0 {
			issues = append(issues, cr.Name+": "+cr.Description)
		}
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
