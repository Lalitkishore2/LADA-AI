---
summary: "Understand and use Focus Modes to tailor search domains and AI response formatting"
read_when:
  - You want the AI to strictly search academic papers or code repositories
  - You need to limit AI noise and focus on a specific task
title: "Focus Modes"
---

# Focus Modes

Focus Modes are a feature that allows LADA to tailor search sources, AI systemic behavior, constraints, and output formatting based strictly on the query context. 

The Focus Mode Manager automatically alters what domains LADA prefers to query (e.g. searching StackOverflow specifically for `code` mode) and adds distinct role-prompting additions to the underlying model interaction.

## Available Modes

LADA comes with multiple built-in Focus Modes:

- **GENERAL (`G`)**: The default behavior. General search across duckduckgo and wikipedia.
- **ACADEMIC (`A`)**: Enforces scholarly, peer-reviewed authoritative sources. Prioritizes `scholar.google.com`, `arxiv.org`, `nature.com`. Requires academic formatting and paper DOIs.
- **CODE (`<>`)**: Enforces programming workflows, working code examples, and technical solutions. Directly queries `stackoverflow.com`, `github.com`, and `docs.python.org`.
- **WRITING (`W`)**: Focuses on clear engaging prose. Assists with grammar, style, tone manipulation, and audience tailoring.
- **MATH (`M`)**: Strict mathematical evaluation mode. Uses clear notation, verifies calculations, and outputs LaTeX-friendly logic.
- **NEWS (`N`)**: Focuses purely on analyzing the latest current events, checking `reuters.com`, `apnews.com`, etc. Analyzes perspectives and explicitly distinguishes fact from opinion context.

## How it works

The `FocusModeManager` intercepts the query phase during AI inference:
1. **Auto-Detection**: The system continuously analyzes the raw input prompt for semantic markers (e.g., words like `calculate`, `integral`, or `function`, `API`) to seamlessly swap modes.
2. **Search Keyword Injection**: When a mode is triggered, background tools silently inject required keywords to maximize relevant hits. (e.g. Academic mode appends "research paper study" implicitly).
3. **Format Injection**: Hardcodes style instructions directly into the overarching system prompt just-in-time, enforcing that models adhere to the selected strict formatting style.
