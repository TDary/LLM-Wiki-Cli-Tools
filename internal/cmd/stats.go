package cmd

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"wiki-tools/internal/wiki"
)

func init() { Register("stats", statsCmd) }

func statsCmd(args []string) {
	format := "table"
	pretty := false
	wikiPath := ""

	for i := 0; i < len(args); i++ {
		switch args[i] {
		case "-h", "--help":
			fmt.Println("用法: wiki-tools stats [WIKI_PATH] [--format table|json] [--pretty]")
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

	// Category breakdown
	catCount := make(map[string]int)
	for _, d := range docs {
		catCount[d.Category]++
	}

	// Tag stats
	tagCount := make(map[string]int)
	totalTags := 0
	for _, d := range docs {
		for _, t := range d.Tags {
			t = strings.TrimSpace(t)
			if t != "" {
				tagCount[t]++
				totalTags++
			}
		}
	}

	// Link density
	totalLinks := 0
	for _, d := range docs {
		totalLinks += d.LinksCount
	}
	linkDensity := 0.0
	if len(docs) > 0 {
		linkDensity = float64(totalLinks) / float64(len(docs))
	}

	// Orphan count
	orphanCount := 0
	for _, d := range docs {
		if d.Category == "raw" {
			continue
		}
		stem := strings.ToLower(strings.TrimSuffix(filepath.Base(d.File), ".md"))
		if wiki.SystemFiles[stem] {
			continue
		}
		if refs, ok := backlinks[stem]; !ok || len(refs) == 0 {
			orphanCount++
		}
	}

	// Total size
	var totalSize int64
	var latestMod string
	for _, d := range docs {
		totalSize += d.Size
		if d.Modified > latestMod {
			latestMod = d.Modified
		}
	}

	// Unique tags
	uniqueTags := len(tagCount)

	if format == "json" {
		meta := wiki.ReadSchemaMeta(p)
		catBreakdown := make(map[string]interface{})
		for cat, count := range catCount {
			catBreakdown[cat] = map[string]interface{}{
				"label": wiki.CategoryLabels[cat],
				"count": count,
			}
		}
		output := map[string]interface{}{
			"wiki":              meta,
			"total_documents":   len(docs),
			"categories":        catBreakdown,
			"unique_tags":       uniqueTags,
			"total_tag_uses":    totalTags,
			"link_density":      linkDensity,
			"orphan_count":      orphanCount,
			"total_size_bytes":  totalSize,
			"latest_modified":   latestMod,
		}
		enc := json.NewEncoder(os.Stdout)
		if pretty {
			enc.SetIndent("", "  ")
		}
		enc.Encode(output)
		return
	}

	meta := wiki.ReadSchemaMeta(p)
	fmt.Printf("\n📊 %s — 知识库统计\n", meta.Name)
	fmt.Printf("\n   文档总数: %d\n", len(docs))
	for _, cat := range wiki.Dirs {
		if count, ok := catCount[cat]; ok && count > 0 {
			fmt.Printf("     %-12s %d 篇\n", wiki.CategoryLabels[cat]+"/", count)
		}
	}

	fmt.Printf("\n   标签统计:\n")
	fmt.Printf("     唯一标签: %d\n", uniqueTags)
	fmt.Printf("     标签使用: %d 次\n", totalTags)

	fmt.Printf("\n   链接密度: %.1f 条/文档\n", linkDensity)
	fmt.Printf("   孤立文档: %d 篇", orphanCount)
	if len(docs) > 0 {
		fmt.Printf(" (%.0f%%)", float64(orphanCount)*100/float64(len(docs)))
	}
	fmt.Println()

	fmt.Printf("   总文件大小: %d 字节", totalSize)
	if totalSize > 1024*1024 {
		fmt.Printf(" (%.1f MB)", float64(totalSize)/1024/1024)
	} else if totalSize > 1024 {
		fmt.Printf(" (%.1f KB)", float64(totalSize)/1024)
	}
	fmt.Println()

	if latestMod != "" {
		fmt.Printf("   最近修改: %s\n", latestMod)
	}
}
