---
name: web_search
version: 1.0.0
author: LADA
triggers: ["search for", "find", "look up", "search the web for", "google"]
tags: ["web", "search", "research"]
---

# Web Search Skill

Search the web for information using multiple search engines.

## Actions

### search_web(query)
Search the web for a query and return top results.

### search_images(query)
Search for images matching the query.

### search_news(query)
Search recent news articles.

## Examples

- "search for python tutorials" → search_web("python tutorials")
- "look up weather forecast" → search_web("weather forecast")
- "find images of cats" → search_images("cats")
- "search news about AI" → search_news("AI")
