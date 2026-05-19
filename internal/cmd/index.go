package cmd

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"wiki-tools/internal/wiki"
)

func init() { Register("index", indexCmd) }

func indexCmd(args []string) {
	pretty := false
	outputPath := ""
	wikiPath := ""

	for i := 0; i < len(args); i++ {
		switch args[i] {
		case "-h", "--help":
			fmt.Println("用法: wiki-tools index [WIKI_PATH] [--output FILE] [--pretty]")
			os.Exit(0)
		case "--output":
			i++; if i < len(args) { outputPath = args[i] }
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
	meta := wiki.ReadSchemaMeta(p)

	type CategoryGroup struct {
		Category      string     `json:"category"`
		CategoryLabel string     `json:"category_label"`
		Count         int        `json:"count"`
		Documents     []wiki.Doc `json:"documents"`
	}
	byCategory := make(map[string]*CategoryGroup)
	for _, d := range docs {
		g, ok := byCategory[d.Category]
		if !ok {
			g = &CategoryGroup{Category: d.Category, CategoryLabel: d.CategoryLabel}
			byCategory[d.Category] = g
		}
		g.Count++
		g.Documents = append(g.Documents, d)
	}

	var categories []CategoryGroup
	for _, dir := range wiki.Dirs {
		if g, ok := byCategory[dir]; ok {
			categories = append(categories, *g)
		}
	}

	allTags := make(map[string]bool)
	for _, d := range docs {
		for _, t := range d.Tags {
			allTags[t] = true
		}
	}
	var tags []string
	for t := range allTags {
		tags = append(tags, t)
	}
	sort.Strings(tags)

	index := map[string]interface{}{
		"wiki":            meta,
		"generated_at":    wiki.Now(),
		"total_documents": len(docs),
		"categories":      categories,
		"tags":            tags,
	}

	if outputPath == "" {
		outputPath = filepath.Join(p, "queries", "index.json")
	}
	absOutput, _ := AbsPath(outputPath)
	parentDir := filepath.Dir(absOutput)
	os.MkdirAll(parentDir, 0755)

	f, err := os.Create(absOutput)
	if err != nil {
		fmt.Fprintf(os.Stderr, "❌ 无法创建文件: %v\n", err)
		os.Exit(1)
	}
	defer f.Close()

	enc := json.NewEncoder(f)
	if pretty {
		enc.SetIndent("", "  ")
	}
	enc.Encode(index)

	fmt.Printf("✅ 索引已生成: %s\n", absOutput)
	fmt.Printf("   文档总数: %d\n", len(docs))
	fmt.Printf("   分类数: %d\n", len(categories))
	if len(tags) > 0 {
		fmt.Printf("   标签: %s\n", strings.Join(tags, ", "))
	} else {
		fmt.Println("   标签: 无")
	}
}
