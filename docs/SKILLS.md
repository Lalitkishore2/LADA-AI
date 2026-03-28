# LADA Skills System Guide

Skills are modular, self-contained capabilities that extend LADA's functionality. Inspired by OpenClaw's skills architecture, LADA skills are plug-and-play Python modules with metadata.

## Skill Structure

Each skill lives in its own folder under `skills/`:

```
skills/
├── web_search/
│   ├── SKILL.md          # Metadata and documentation
│   ├── skill.py          # Main implementation
│   ├── __init__.py       # Package init
│   └── requirements.txt  # Dependencies (optional)
├── gmail_reader/
│   ├── SKILL.md
│   ├── skill.py
│   └── ...
└── stock_price/
    └── ...
```

## SKILL.md Format

The `SKILL.md` file defines skill metadata using YAML frontmatter:

```markdown
---
name: Web Search
version: 1.0.0
description: Search the web using DuckDuckGo and return summarized results
author: LADA Team
tags: [search, web, research]
requires:
  - duckduckgo-search>=3.0.0
env_vars:
  - DDGS_PROXY  # Optional proxy
triggers:
  - search for {query}
  - look up {query}
  - find information about {query}
  - what is {query}
examples:
  - search for latest AI news
  - look up Python tutorials
  - find information about climate change
---

# Web Search Skill

This skill searches the web using DuckDuckGo's API and returns
summarized results. No API key required.

## Usage

Just ask LADA to search for anything:
- "Search for best restaurants nearby"
- "Look up Python async tutorials"

## Configuration

Set `DDGS_PROXY` in your `.env` if you need to use a proxy.
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Human-readable skill name |
| `version` | string | Semantic version (1.0.0) |
| `description` | string | Brief description |
| `triggers` | list | Voice/text patterns that activate skill |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `author` | string | Skill author |
| `tags` | list | Categorization tags |
| `requires` | list | Python dependencies |
| `env_vars` | list | Required/optional environment variables |
| `examples` | list | Example usage phrases |

## skill.py Implementation

```python
"""
LADA Skill: Web Search
"""

from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Optional: import dependencies
try:
    from duckduckgo_search import DDGS
    DDGS_OK = True
except ImportError:
    DDGS_OK = False


def execute(query: str, max_results: int = 5) -> str:
    """
    Execute the skill with given parameters.
    
    This is the main entry point called by LADA.
    
    Args:
        query: Search query from user
        max_results: Maximum results to return
        
    Returns:
        Formatted response string
    """
    if not DDGS_OK:
        return "Web search requires duckduckgo-search. Install with: pip install duckduckgo-search"
    
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append(f"• {r['title']}: {r['body'][:200]}...")
        
        if results:
            return f"Search results for '{query}':\n\n" + "\n\n".join(results)
        return f"No results found for '{query}'"
        
    except Exception as e:
        logger.error(f"Search failed: {e}")
        return f"Search failed: {e}"


def get_info() -> dict:
    """
    Return skill capabilities and status.
    
    Called by LADA to inspect skill without executing.
    """
    return {
        "available": DDGS_OK,
        "features": ["text_search", "news_search"],
        "rate_limit": "100 requests/hour"
    }
```

### Required Functions

| Function | Signature | Description |
|----------|-----------|-------------|
| `execute` | `execute(**kwargs) -> str` | Main skill logic |

### Optional Functions

| Function | Signature | Description |
|----------|-----------|-------------|
| `get_info` | `get_info() -> dict` | Skill capabilities |
| `setup` | `setup() -> bool` | One-time initialization |
| `cleanup` | `cleanup() -> None` | Resource cleanup |

## Installing Skills

### From Local Folder

```bash
# Copy skill to skills directory
cp -r my_skill/ skills/
```

LADA auto-discovers skills on startup.

### From GitHub

```bash
# Clone into skills folder
cd skills
git clone https://github.com/username/lada-skill-name.git skill_name
```

### From OpenClaw/VoltAgent (Compatible)

LADA can use OpenClaw-compatible skills:

```bash
# Clone OpenClaw skill
cd skills
git clone https://github.com/voltAgent/awesome-openclaw-skills.git openclaw_skills

# Skills are in subfolders
ls openclaw_skills/
# browser_use/  code_execution/  web_search/  ...
```

## Skill Loading

LADA loads skills automatically via `integrations/openclaw_skills.py`:

```python
from integrations.openclaw_skills import SkillLoader

loader = SkillLoader()
loader.discover_skills()  # Scans skills/ directory

# Get all available skills
skills = loader.list_skills()
# [{'name': 'Web Search', 'triggers': [...], ...}, ...]

# Execute skill by name
result = loader.execute_skill("web_search", query="AI news")

# Execute by trigger match
result = loader.execute_by_trigger("search for Python tutorials")
```

## Trigger Pattern Matching

Triggers use pattern syntax with placeholders:

```yaml
triggers:
  - search for {query}      # Captures "query" parameter
  - {action} the {target}   # Multiple captures
  - remind me to {task} at {time}
```

Matching examples:
- "search for AI news" → `{query: "AI news"}`
- "open the browser" → `{action: "open", target: "browser"}`
- "remind me to call mom at 5pm" → `{task: "call mom", time: "5pm"}`

## Configuration

### Environment Variables

Skills can read environment variables:

```python
import os

PROXY = os.getenv("DDGS_PROXY", "")
API_KEY = os.getenv("MY_SKILL_API_KEY")
```

### Skill Settings

Skills can have user-configurable settings via `config/skill_settings.json`:

```json
{
  "web_search": {
    "max_results": 10,
    "safe_search": true
  },
  "stock_price": {
    "currency": "USD",
    "refresh_interval": 60
  }
}
```

Access in skill:

```python
import json
from pathlib import Path

def load_settings():
    config_path = Path("config/skill_settings.json")
    if config_path.exists():
        settings = json.loads(config_path.read_text())
        return settings.get("web_search", {})
    return {}
```

## Creating a New Skill

### 1. Create Skill Folder

```bash
mkdir -p skills/my_skill
```

### 2. Create SKILL.md

```bash
cat > skills/my_skill/SKILL.md << 'EOF'
---
name: My Skill
version: 1.0.0
description: Does something useful
triggers:
  - do my thing with {input}
---

# My Skill

Description here.
EOF
```

### 3. Create skill.py

```bash
cat > skills/my_skill/skill.py << 'EOF'
def execute(input: str) -> str:
    return f"Processed: {input}"
EOF
```

### 4. Create __init__.py

```bash
echo "from .skill import execute" > skills/my_skill/__init__.py
```

### 5. Test

```python
from skills.my_skill import execute
print(execute("test input"))
```

## Skill Categories

| Category | Examples |
|----------|----------|
| **Search** | Web search, news, academic papers |
| **Productivity** | Calendar, email, reminders |
| **Development** | Code execution, Git, deployment |
| **Media** | YouTube, Spotify, image generation |
| **Smart Home** | Lights, thermostat, cameras |
| **Finance** | Stock prices, crypto, budgeting |
| **Health** | Fitness tracking, medication reminders |
| **Robot** | MoltBot control, 3D printing |

## Best Practices

### 1. Graceful Degradation

```python
try:
    from some_library import feature
    FEATURE_OK = True
except ImportError:
    FEATURE_OK = False

def execute(query):
    if not FEATURE_OK:
        return "This skill requires 'some_library'. Install with: pip install some_library"
    # ... rest of implementation
```

### 2. Error Handling

```python
def execute(query):
    try:
        result = do_something(query)
        return format_result(result)
    except ConnectionError:
        return "Network error. Please check your internet connection."
    except Exception as e:
        logger.exception("Skill execution failed")
        return f"Error: {e}"
```

### 3. Rate Limiting

```python
import time

_last_call = 0
_min_interval = 1.0  # seconds

def execute(query):
    global _last_call
    now = time.time()
    if now - _last_call < _min_interval:
        time.sleep(_min_interval - (now - _last_call))
    _last_call = time.time()
    # ... rest of implementation
```

### 4. Caching

```python
from functools import lru_cache

@lru_cache(maxsize=100)
def expensive_operation(query):
    # Cached for repeated queries
    return fetch_data(query)
```

## OpenClaw Compatibility

LADA's skill system is compatible with OpenClaw skills. Key differences:

| Feature | LADA | OpenClaw |
|---------|------|----------|
| Metadata file | `SKILL.md` | `SKILL.md` |
| Entry point | `execute()` | `run()` or `execute()` |
| Config location | `config/` | `~/.openclaw/` |
| Gateway | Optional | Required |

To use OpenClaw skills in LADA:

1. Clone the skill repository
2. If entry point is `run()`, add alias:
   ```python
   # In __init__.py
   from .skill import run as execute
   ```
3. Skill should work with LADA's loader

## Related Files

- `integrations/openclaw_skills.py` - Skill loader
- `skills/web_search/` - Example skill
- `config/skill_settings.json` - Skill configuration
- `modules/voice_nlu.py` - Trigger matching
