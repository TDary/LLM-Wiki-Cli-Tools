package cmd

import (
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strings"

	"wiki-tools/internal/wiki"
)

func init() { Register("tags", tagsCmd) }

type TagInfo struct {
	Tag       string   `json:"tag"`
	Count     int      `json:"count"`
	Documents []string `json:"documents"`
}

func tagsCmd(args []string) {
	format := "table"
	pretty := false
	sortBy := "count"
	wikiPath := ""

	for i := 0; i < len(args); i++ {
		switch args[i] {
		case "-h", "--help":
			fmt.Println("用法: wiki-tools tags [WIKI_PATH] [--format table|json] [--pretty] [--sort count|name]")
			os.Exit(0)
		case "--format":
			i++; if i < len(args) { format = args[i] }
		case "--pretty":
			pretty = true
		case "--sort":
			i++; if i < len(args) { sortBy = args[i] }
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

	// Build tag index
	tagMap := make(map[string]*TagInfo)
	for _, d := range docs {
		if d.Category == "raw" {
			continue
		}
		for _, t := range d.Tags {
			t = strings.TrimSpace(t)
			if t == "" {
				continue
			}
			if _, ok := tagMap[t]; !ok {
				tagMap[t] = &TagInfo{Tag: t}
			}
			tagMap[t].Count++
			tagMap[t].Documents = append(tagMap[t].Documents, d.File)
		}
	}

	var tags []TagInfo
	for _, info := range tagMap {
		tags = append(tags, *info)
	}

	// Sort
	switch sortBy {
	case "name":
		sort.Slice(tags, func(i, j int) bool {
			return strings.ToLower(tags[i].Tag) < strings.ToLower(tags[j].Tag)
		})
	default: // count
		sort.Slice(tags, func(i, j int) bool {
			if tags[i].Count != tags[j].Count {
				return tags[i].Count > tags[j].Count
			}
			return strings.ToLower(tags[i].Tag) < strings.ToLower(tags[j].Tag)
		})
	}

	meta := wiki.ReadSchemaMeta(p)

	if format == "json" {
		output := map[string]interface{}{
			"wiki":    meta,
			"total":   len(tags),
			"tags":    tags,
		}
		enc := json.NewEncoder(os.Stdout)
		if pretty {
			enc.SetIndent("", "  ")
		}
		enc.Encode(output)
		return
	}

	fmt.Printf("\n🏷️  %s — 标签列表\n", meta.Name)
	fmt.Printf("   共 %d 个标签\n\n", len(tags))

	if len(tags) == 0 {
		fmt.Println("   没有找到标签。")
		return
	}

	for _, t := range tags {
		example := ""
		if len(t.Documents) > 0 {
			example = t.Documents[0]
			if len(t.Documents) > 1 {
				example += fmt.Sprintf(" 等 %d 篇", len(t.Documents))
			}
		}
		fmt.Printf("   %-20s  %3d 次  %s\n", t.Tag, t.Count, example)
	}
}
