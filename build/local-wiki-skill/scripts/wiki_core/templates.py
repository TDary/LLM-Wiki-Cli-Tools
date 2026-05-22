"""Template generators for wiki files."""

from .helpers import now, today


def template_schema(name: str, domain: str) -> str:
    return f"""# SCHEMA — {name}

> 知识库领域配置 · 自动生成的索引和关系

## 基本信息

| 属性 | 值 |
|------|-----|
| **名称** | {name} |
| **领域** | {domain} |
| **Git 同步** | 禁用（纯本地模式） |
| **创建时间** | {now()} |
| **初始化工具** | wiki-tools |

## 目录说明

| 目录 | 用途 |
|------|------|
| `raw/` | 原始资料、外部引用、数据文件 |
| `entities/` | 实体页面（人、项目、工具等） |
| `concepts/` | 概念、术语、方法论 |
| `relations/` | 关系描述、交叉引用 |
| `queries/` | 查询模板、搜索索引 |
| `drafts/` | 草稿、临时笔记 |

## 标签体系

```yaml
tags:
  - type: tech
    label: 技术
  - type: process
    label: 流程
  - type: reference
    label: 参考
```

## 关系类型

```yaml
relations:
  - depends_on: 依赖
  - references: 引用
  - implements: 实现
  - owned_by: 归属
```
"""


def template_readme(name: str, domain: str) -> str:
    return f"""# {name}

> {domain}

## 快速导航

- [SCHEMA](./SCHEMA.md) — 知识库配置与目录说明
- [原始资料](./raw/) — 外部引用与数据文件
- [实体](./entities/) — 人、项目、工具等
- [概念](./concepts/) — 术语与方法论
- [关系](./relations/) — 交叉引用
- [查询](./queries/) — 搜索索引
- [草稿](./drafts/) — 临时笔记

## 更新日志

参见 [log.md](./log.md)
"""


def template_log() -> str:
    return f"""# 更新日志

## {today()}

- 🎉 知识库初始化完成
"""


def template_wiki_page(title: str, category: str, tags: list[str], source: str) -> str:
    """Generate a wiki page template with frontmatter."""
    type_map = {
        "entities": "entity",
        "concepts": "concept",
        "relations": "comparison",
        "queries": "query",
        "drafts": "summary",
    }
    page_type = type_map.get(category, "summary")
    tags_str = ", ".join(tags) if tags else ""
    return f"""---
title: {title}
created: {today()}
updated: {today()}
type: {page_type}
tags: [{tags_str}]
sources: [{source}]
---

# {title}

## Overview

> TODO: Add content summary

## Key Points

- TODO: Add key points

## Related

- TODO: Add [[wikilinks]] to related pages
"""
