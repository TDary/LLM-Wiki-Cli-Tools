"""wiki-core — Local wiki management core package."""

VERSION = "1.4.0"

DIRS = ["raw", "normalized", "entities", "concepts", "relations", "queries", "drafts"]

CATEGORY_LABELS = {
    "raw": "原始资料",
    "normalized": "规范化资料",
    "entities": "实体",
    "concepts": "概念",
    "relations": "关系",
    "queries": "查询",
    "drafts": "草稿",
}

SYSTEM_FILES = {"readme.md", "log.md", "schema.md"}

HEALTH_WEIGHT_DEFAULTS = {
    "orphan": 3, "broken_link": 5, "no_tag": 1,
    "low_link": 2, "empty_doc": 2, "self_link": 1,
}
