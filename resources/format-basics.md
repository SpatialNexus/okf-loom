# OKF format basics

## Bundle

A bundle is a directory tree of `.md` files:

```text
my_bundle/
├── index.md
├── log.md
├── datasets/
│   └── sales.md
└── tables/
    ├── orders.md
    └── customers.md
```

## Concept file

```markdown
---
type: Table
title: Customer Orders
description: One row per completed customer order.
resource: https://example.com/orders
tags: [sales, orders]
timestamp: "2026-05-28T14:30:00Z"
---

# Schema

| Column | Type | Description |
|---|---|---|
| `customer_id` | STRING | FK to [customers](/tables/customers.md). |
```

## Frontmatter contract

| Key | Status | Notes |
|---|---|---|
| `type` | required | Short kind string. Consumers tolerate unknown types. |
| `title` | recommended | Human display name; filename fallback exists. |
| `description` | recommended | One-line summary for indexes/search. |
| `resource` | recommended | Canonical URI for an underlying asset. |
| `tags` | recommended | YAML list of cross-cutting labels. |
| `timestamp` | recommended | ISO 8601 modified timestamp. |

Producers may add arbitrary keys. Consumers and mutators must preserve unknown
keys round-trip.

## Link forms

| Form | Example | Guidance |
|---|---|---|
| Absolute bundle-relative | `[customers](/tables/customers.md)` | Default; stable when files move within a subdirectory. |
| Relative | `[next](./other.md)` | Fine for tightly-coupled siblings. |
| Wikilink body syntax | `[[tables/customers\|Customer]]` | Accepted migration syntax; mutators write standard Markdown links. |

Broken internal links are warnings by default for consumers because they may
point to not-yet-written knowledge. Authoring mutators fail closed on missing
targets unless forward references are explicitly allowed.
