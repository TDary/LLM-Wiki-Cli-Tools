package wiki

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"
)

var wikilinkRe = regexp.MustCompile(`\[\[(.+?)\]\]`)

// CategoryLabels maps directory names to Chinese labels.
var CategoryLabels = map[string]string{
	"raw":       "原始资料",
	"entities":  "实体",
	"concepts":  "概念",
	"relations": "关系",
	"queries":   "查询",
	"drafts":    "草稿",
}

// Doc represents a wiki document's metadata.
type Doc struct {
	Title         string   `json:"title"`
	File          string   `json:"file"`
	AbsolutePath  string   `json:"absolute_path"`
	Category      string   `json:"category"`
	CategoryLabel string   `json:"category_label"`
	Size          int64    `json:"size"`
	Modified      string   `json:"modified"`
	Tags          []string `json:"tags"`
	LinksCount    int      `json:"links_count"`
	Text          string   `json:"-"`
}

// SchemaMeta holds basic metadata from SCHEMA.md.
type SchemaMeta struct {
	Name      string `json:"name"`
	Domain    string `json:"domain"`
	CreatedAt string `json:"created_at,omitempty"`
}

// ReadSchemaMeta reads basic metadata from SCHEMA.md.
func ReadSchemaMeta(wikiPath string) SchemaMeta {
	meta := SchemaMeta{Name: filepath.Base(wikiPath), Domain: "Wiki 知识库"}
	schemaPath := filepath.Join(wikiPath, "SCHEMA.md")
	data, err := os.ReadFile(schemaPath)
	if err != nil {
		return meta
	}
	for _, line := range strings.Split(string(data), "\n") {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "| **名称** |") {
			parts := splitTable(trimmed)
			if len(parts) >= 2 {
				meta.Name = parts[1]
			}
		} else if strings.HasPrefix(trimmed, "| **领域** |") {
			parts := splitTable(trimmed)
			if len(parts) >= 2 {
				meta.Domain = parts[1]
			}
		} else if strings.HasPrefix(trimmed, "| **创建时间** |") {
			parts := splitTable(trimmed)
			if len(parts) >= 2 {
				meta.CreatedAt = parts[1]
			}
		}
	}
	return meta
}

func splitTable(row string) []string {
	var parts []string
	for _, p := range strings.Split(row, "|") {
		p = strings.TrimSpace(p)
		if p != "" {
			parts = append(parts, p)
		}
	}
	return parts
}

// ExtractFrontmatter parses YAML-style frontmatter from text.
func ExtractFrontmatter(text string) (title string, tags []string) {
	lines := strings.Split(text, "\n")
	if len(lines) == 0 || strings.TrimSpace(lines[0]) != "---" {
		return
	}
	for i := 1; i < len(lines); i++ {
		line := strings.TrimSpace(lines[i])
		if line == "---" {
			break
		}
		if idx := strings.Index(line, ":"); idx > 0 {
			key := strings.TrimSpace(line[:idx])
			val := strings.TrimSpace(line[idx+1:])
			val = strings.Trim(val, `"'`)
			switch key {
			case "title":
				title = val
			case "tags":
				val = strings.Trim(val, "[]")
				for _, t := range strings.Split(val, ",") {
					t = strings.TrimSpace(t)
					if t != "" {
						tags = append(tags, t)
					}
				}
			}
		}
	}
	return
}

// ExtractTitle extracts title from first # heading, falling back to filename.
func ExtractTitle(text, stem string) string {
	for _, line := range strings.Split(text, "\n") {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "# ") && !strings.HasPrefix(trimmed, "## ") {
			return strings.TrimPrefix(trimmed, "# ")
		}
	}
	return strings.Title(strings.ReplaceAll(stem, "-", " "))
}

// CollectDocuments walks all category dirs and collects document metadata.
func CollectDocuments(wikiPath string) []Doc {
	var docs []Doc
	for _, d := range Dirs {
		dirPath := filepath.Join(wikiPath, d)
		entries, err := os.ReadDir(dirPath)
		if err != nil {
			continue
		}
		sort.Slice(entries, func(i, j int) bool { return entries[i].Name() < entries[j].Name() })
		for _, e := range entries {
			if e.IsDir() || !strings.HasSuffix(e.Name(), ".md") {
				continue
			}
			fp := filepath.Join(dirPath, e.Name())
			info, err := e.Info()
			if err != nil {
				continue
			}
			data, err := os.ReadFile(fp)
			if err != nil {
				continue
			}
			text := string(data)
			title, tags := ExtractFrontmatter(text)
			stem := strings.TrimSuffix(e.Name(), ".md")
			if title == "" {
				title = ExtractTitle(text, stem)
			}
			relFile := filepath.Join(d, e.Name())
			absPath, _ := filepath.Abs(fp)
			docs = append(docs, Doc{
				Title:         title,
				File:          relFile,
				AbsolutePath:  absPath,
				Category:      d,
				CategoryLabel: CategoryLabels[d],
				Size:          info.Size(),
				Modified:      info.ModTime().Format("2006-01-02 15:04:05"),
				Tags:          tags,
				LinksCount:    len(wikilinkRe.FindAllString(text, -1)),
				Text:          text,
			})
		}
	}
	return docs
}

// BacklinkEntry represents a single backlink reference.
type BacklinkEntry struct {
	SourceTitle string `json:"source_title"`
	SourceFile  string `json:"source_file"`
	Line        int    `json:"line"`
	LineContent string `json:"line_content"`
}

// BuildBacklinkMap builds {target_stem: [source_entries]} from all wikilinks.
func BuildBacklinkMap(wikiPath string) map[string][]BacklinkEntry {
	backlinks := make(map[string][]BacklinkEntry)
	for _, d := range Dirs {
		dirPath := filepath.Join(wikiPath, d)
		entries, err := os.ReadDir(dirPath)
		if err != nil {
			continue
		}
		for _, e := range entries {
			if e.IsDir() || !strings.HasSuffix(e.Name(), ".md") {
				continue
			}
			fp := filepath.Join(dirPath, e.Name())
			data, err := os.ReadFile(fp)
			if err != nil {
				continue
			}
			text := string(data)
			title, _ := ExtractFrontmatter(text)
			stem := strings.TrimSuffix(e.Name(), ".md")
			if title == "" {
				title = ExtractTitle(text, stem)
			}
			relFile := filepath.Join(d, e.Name())
			lines := strings.Split(text, "\n")
			matches := wikilinkRe.FindAllStringSubmatch(text, -1)
			for _, m := range matches {
				if len(m) < 2 {
					continue
				}
				target := strings.ToLower(strings.ReplaceAll(strings.TrimSpace(m[1]), " ", "-"))
				linkPattern := "[[" + m[1] + "]]"
				for lineNo, line := range lines {
					if strings.Contains(line, linkPattern) {
						backlinks[target] = append(backlinks[target], BacklinkEntry{
							SourceTitle: title,
							SourceFile:  relFile,
							Line:        lineNo + 1,
							LineContent: strings.TrimSpace(line),
						})
					}
				}
			}
		}
	}
	return backlinks
}

// SearchResult represents a search match in a document.
type SearchResult struct {
	Doc
	Matches    []Match `json:"matches"`
	MatchCount int     `json:"match_count"`
}

// Match represents a single line match.
type Match struct {
	Line    int    `json:"line"`
	Content string `json:"content"`
}

// SearchDocuments searches docs by keyword (case-insensitive).
func SearchDocuments(docs []Doc, keyword string) []SearchResult {
	var results []SearchResult
	kw := strings.ToLower(keyword)
	for _, doc := range docs {
		var matches []Match
		if strings.Contains(strings.ToLower(doc.Title), kw) {
			matches = append(matches, Match{Line: 0, Content: doc.Title})
		}
		for lineNo, line := range strings.Split(doc.Text, "\n") {
			if strings.Contains(strings.ToLower(line), kw) {
				matches = append(matches, Match{Line: lineNo + 1, Content: strings.TrimSpace(line)})
			}
		}
		if len(matches) > 0 {
			results = append(results, SearchResult{
				Doc:        doc,
				Matches:    matches,
				MatchCount: len(matches),
			})
		}
	}
	return results
}

// LinkGraph holds outbound links and doc info.
type LinkGraph struct {
	Outbound map[string][]string      // stem -> [target_stems]
	DocInfo  map[string]LinkGraphInfo  // stem -> info
}

// LinkGraphInfo holds basic doc info for the link graph.
type LinkGraphInfo struct {
	Title    string `json:"title"`
	File     string `json:"file"`
	Category string `json:"category"`
}

// BuildLinkGraph builds a bidirectional link graph.
func BuildLinkGraph(wikiPath string) LinkGraph {
	g := LinkGraph{
		Outbound: make(map[string][]string),
		DocInfo:  make(map[string]LinkGraphInfo),
	}
	for _, d := range Dirs {
		dirPath := filepath.Join(wikiPath, d)
		entries, err := os.ReadDir(dirPath)
		if err != nil {
			continue
		}
		for _, e := range entries {
			if e.IsDir() || !strings.HasSuffix(e.Name(), ".md") {
				continue
			}
			fp := filepath.Join(dirPath, e.Name())
			data, err := os.ReadFile(fp)
			if err != nil {
				continue
			}
			text := string(data)
			stem := strings.ToLower(strings.TrimSuffix(e.Name(), ".md"))
			title, _ := ExtractFrontmatter(text)
			if title == "" {
				title = ExtractTitle(text, stem)
			}
			relFile := filepath.Join(d, e.Name())
			g.DocInfo[stem] = LinkGraphInfo{Title: title, File: relFile, Category: d}
			matches := wikilinkRe.FindAllStringSubmatch(text, -1)
			var targets []string
			for _, m := range matches {
				if len(m) >= 2 {
					targets = append(targets, strings.ToLower(strings.ReplaceAll(strings.TrimSpace(m[1]), " ", "-")))
				}
			}
			g.Outbound[stem] = targets
		}
	}
	return g
}

// TraceResult holds a single trace entry.
type TraceResult struct {
	Stem  string `json:"stem"`
	Depth int    `json:"depth"`
}

// TraceUpstream recursively traces what a page links to.
func TraceUpstream(stem string, outbound map[string][]string, visited map[string]bool, depth int) []TraceResult {
	if depth > 10 || visited[stem] {
		return nil
	}
	visited[stem] = true
	var results []TraceResult
	for _, target := range outbound[stem] {
		results = append(results, TraceResult{Stem: target, Depth: depth})
		results = append(results, TraceUpstream(target, outbound, visited, depth+1)...)
	}
	return results
}

// TraceDownstream recursively traces what links to a page.
func TraceDownstream(stem string, inbound map[string][]string, visited map[string]bool, depth int) []TraceResult {
	if depth > 10 || visited[stem] {
		return nil
	}
	visited[stem] = true
	var results []TraceResult
	for _, source := range inbound[stem] {
		results = append(results, TraceResult{Stem: source, Depth: depth})
		results = append(results, TraceDownstream(source, inbound, visited, depth+1)...)
	}
	return results
}

// FindClosest finds the closest matching stem using character overlap.
func FindClosest(target string, candidates []string) (string, float64) {
	best := ""
	bestScore := -1.0
	targetChars := make(map[rune]bool)
	for _, c := range target {
		targetChars[c] = true
	}
	for _, c := range candidates {
		cChars := make(map[rune]bool)
		for _, ch := range c {
			cChars[ch] = true
		}
		intersect := 0
		for ch := range targetChars {
			if cChars[ch] {
				intersect++
			}
		}
		union := len(targetChars) + len(cChars) - intersect
		if union == 0 {
			continue
		}
		overlap := float64(intersect) / float64(union)
		prefix := 0
		for i := 0; i < len(target) && i < len(c); i++ {
			if target[i] == c[i] {
				prefix++
			} else {
				break
			}
		}
		score := overlap + float64(prefix)*0.1
		if score > bestScore {
			bestScore = score
			best = c
		}
	}
	if bestScore > 0.3 {
		return best, bestScore
	}
	return "", 0
}

// Now returns current timestamp.
func Now() string {
	return time.Now().Format("2006-01-02 15:04:05")
}

// RequireWiki exits if path is not a valid wiki.
func RequireWiki(wikiPath string) {
	if !FileExists(filepath.Join(wikiPath, "SCHEMA.md")) {
		fmt.Fprintf(os.Stderr, "❌ 未找到 SCHEMA.md: %s 不是一个 wiki 目录\n", wikiPath)
		os.Exit(1)
	}
}

// SystemFiles are files to exclude from analysis.
var SystemFiles = map[string]bool{
	"readme.md": true,
	"log.md":    true,
	"schema.md": true,
}

// StripInternal removes _text-like fields (not needed for Go, but kept for API parity).
func StripInternal(docs []Doc) []Doc {
	return docs
}
