---
summary: "CLI reference for `lada docs` (search the live docs index)"
read_when:
  - You want to search the live LADA docs from the terminal
title: "docs"
---

# `lada docs`

Search the live docs index.

Arguments:

- `[query...]`: search terms to send to the live docs index

Examples:

```bash
lada docs
lada docs browser existing-session
lada docs sandbox allowHostControl
lada docs gateway token secretref
```

Notes:

- With no query, `lada docs` opens the live docs search entrypoint.
- Multi-word queries are passed through as one search request.

