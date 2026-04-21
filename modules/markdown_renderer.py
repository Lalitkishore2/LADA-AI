"""
LADA v7.0 - Markdown Renderer
Convert markdown to styled HTML for ChatGPT-style message display
"""

import re
import html
from typing import List, Dict, Tuple, Optional

# Try to import optional dependencies
try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name, guess_lexer, TextLexer
    from pygments.formatters import HtmlFormatter
    from pygments.util import ClassNotFound
    PYGMENTS_OK = True
except ImportError:
    PYGMENTS_OK = False
    print("[MarkdownRenderer] Pygments not installed - code highlighting disabled")

try:
    import markdown as md
    MARKDOWN_OK = True
except ImportError:
    MARKDOWN_OK = False
    print("[MarkdownRenderer] markdown not installed - basic parsing only")


class MarkdownRenderer:
    """
    Render markdown text to styled HTML for PyQt5 display.
    Supports: bold, italic, code, code blocks, lists, links, headers.
    """
    
    # Dark theme colors matching LADA
    COLORS = {
        'bg': '#212121',
        'text': '#ececec',
        'code_bg': '#1e1e1e',
        'code_text': '#d4d4d4',
        'link': '#10a37f',
        'header': '#ffffff',
        'border': '#3a3a3a',
        'inline_code_bg': '#2d2d2d',
    }
    
    # Pygments dark theme style
    CODE_STYLE = """
    .codehilite {
        background: #1e1e1e;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
        overflow-x: auto;
        font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
        font-size: 13px;
        line-height: 1.5;
    }
    .codehilite pre {
        margin: 0;
        padding: 0;
        white-space: pre-wrap;
        word-wrap: break-word;
    }
    /* Monokai-inspired colors */
    .codehilite .k { color: #f92672; }  /* Keyword */
    .codehilite .kn { color: #f92672; } /* Keyword.Namespace */
    .codehilite .kd { color: #66d9ef; } /* Keyword.Declaration */
    .codehilite .n { color: #f8f8f2; }  /* Name */
    .codehilite .nn { color: #a6e22e; } /* Name.Namespace */
    .codehilite .nf { color: #a6e22e; } /* Name.Function */
    .codehilite .nc { color: #a6e22e; } /* Name.Class */
    .codehilite .s { color: #e6db74; }  /* String */
    .codehilite .s1 { color: #e6db74; } /* String.Single */
    .codehilite .s2 { color: #e6db74; } /* String.Double */
    .codehilite .c { color: #75715e; }  /* Comment */
    .codehilite .c1 { color: #75715e; } /* Comment.Single */
    .codehilite .cm { color: #75715e; } /* Comment.Multiline */
    .codehilite .o { color: #f92672; }  /* Operator */
    .codehilite .p { color: #f8f8f2; }  /* Punctuation */
    .codehilite .mi { color: #ae81ff; } /* Number.Integer */
    .codehilite .mf { color: #ae81ff; } /* Number.Float */
    .codehilite .nb { color: #66d9ef; } /* Name.Builtin */
    .codehilite .bp { color: #f8f8f2; } /* Name.Builtin.Pseudo */
    """
    
    def __init__(self, font_size: int = 18):
        """Initialize the markdown renderer."""
        self.code_blocks: List[Dict] = []
        self.font_size = font_size  # Configurable font size
    
    def set_font_size(self, size: int):
        """Update the base font size."""
        self.font_size = size
    
    def render(self, text: str) -> str:
        """
        Convert markdown text to styled HTML.
        
        Args:
            text: Markdown-formatted text
            
        Returns:
            HTML string ready for QTextBrowser
        """
        if not text:
            return ""
        
        # Reset code blocks
        self.code_blocks = []
        
        # Escape HTML first to prevent XSS
        # But preserve markdown syntax
        
        # Extract and process code blocks first (before escaping)
        text, code_placeholders = self._extract_code_blocks(text)
        
        # Escape remaining HTML
        text = html.escape(text)
        
        # Process markdown elements
        text = self._process_headers(text)
        text = self._process_bold(text)
        text = self._process_italic(text)
        text = self._process_inline_code(text)
        text = self._process_links(text)
        text = self._process_lists(text)
        text = self._process_blockquotes(text)
        text = self._process_horizontal_rules(text)
        
        # Restore code blocks with syntax highlighting
        text = self._restore_code_blocks(text, code_placeholders)
        
        # Convert newlines to <br> (but not in code blocks)
        text = self._process_newlines(text)
        
        # Wrap in styled container
        html_output = self._wrap_html(text)
        
        return html_output
    
    def _extract_code_blocks(self, text: str) -> Tuple[str, Dict[str, Dict]]:
        """Extract code blocks and replace with placeholders."""
        placeholders = {}
        placeholder_count = 0
        
        # Match ```language\ncode\n```
        pattern = r'```(\w+)?\n(.*?)\n```'
        
        def replace_block(match):
            nonlocal placeholder_count
            language = match.group(1) or 'text'
            code = match.group(2)
            
            placeholder = f"__CODE_BLOCK_{placeholder_count}__"
            placeholders[placeholder] = {
                'language': language,
                'code': code
            }
            self.code_blocks.append({
                'language': language,
                'code': code,
                'index': placeholder_count
            })
            placeholder_count += 1
            return placeholder
        
        text = re.sub(pattern, replace_block, text, flags=re.DOTALL)
        return text, placeholders
    
    def _restore_code_blocks(self, text: str, placeholders: Dict[str, Dict]) -> str:
        """Restore code blocks with syntax highlighting."""
        for placeholder, data in placeholders.items():
            highlighted = self._highlight_code(data['code'], data['language'])
            text = text.replace(placeholder, highlighted)
        return text
    
    def _highlight_code(self, code: str, language: str) -> str:
        """Apply syntax highlighting to code."""
        if PYGMENTS_OK:
            try:
                lexer = get_lexer_by_name(language, stripall=True)
            except ClassNotFound:
                try:
                    lexer = guess_lexer(code)
                except ClassNotFound:
                    lexer = TextLexer()
            
            formatter = HtmlFormatter(
                cssclass='codehilite',
                nowrap=False,
                noclasses=False
            )
            highlighted = highlight(code, lexer, formatter)
            
            # Add language label and copy button
            lang_label = f'<div style="color: #888; font-size: 11px; margin-bottom: 4px;">{language}</div>'
            return f'<div class="code-container">{lang_label}{highlighted}</div>'
        else:
            # Fallback: simple pre block
            escaped_code = html.escape(code)
            return f'''<div class="code-container">
                <div style="color: #888; font-size: 11px; margin-bottom: 4px;">{language}</div>
                <pre style="background: #1e1e1e; padding: 12px; border-radius: 8px; 
                     color: #d4d4d4; font-family: Consolas, monospace; overflow-x: auto;">
{escaped_code}</pre>
            </div>'''
    
    def _process_headers(self, text: str) -> str:
        """Convert # headers to HTML."""
        # H3
        text = re.sub(r'^### (.+)$', r'<h3 style="color: #fff; margin: 16px 0 8px 0; font-size: 16px;">\1</h3>', text, flags=re.MULTILINE)
        # H2
        text = re.sub(r'^## (.+)$', r'<h2 style="color: #fff; margin: 20px 0 10px 0; font-size: 18px;">\1</h2>', text, flags=re.MULTILINE)
        # H1
        text = re.sub(r'^# (.+)$', r'<h1 style="color: #fff; margin: 24px 0 12px 0; font-size: 22px;">\1</h1>', text, flags=re.MULTILINE)
        return text
    
    def _process_bold(self, text: str) -> str:
        """Convert **bold** to HTML."""
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong style="color: #fff;">\1</strong>', text)
        text = re.sub(r'__(.+?)__', r'<strong style="color: #fff;">\1</strong>', text)
        return text
    
    def _process_italic(self, text: str) -> str:
        """Convert *italic* to HTML."""
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        text = re.sub(r'_(.+?)_', r'<em>\1</em>', text)
        return text
    
    def _process_inline_code(self, text: str) -> str:
        """Convert `code` to HTML."""
        text = re.sub(
            r'`([^`]+)`',
            r'<code style="background: #2d2d2d; padding: 2px 6px; border-radius: 4px; font-family: Consolas, monospace; font-size: 13px;">\1</code>',
            text
        )
        return text
    
    def _process_links(self, text: str) -> str:
        """Convert [text](url) to HTML links."""
        text = re.sub(
            r'\[([^\]]+)\]\(([^)]+)\)',
            r'<a href="\2" style="color: #10a37f; text-decoration: none;">\1</a>',
            text
        )
        return text
    
    def _process_lists(self, text: str) -> str:
        """Convert - item or 1. item to HTML lists."""
        lines = text.split('\n')
        result = []
        in_ul = False
        in_ol = False
        
        for line in lines:
            # Unordered list
            ul_match = re.match(r'^[\s]*[-*]\s+(.+)$', line)
            # Ordered list
            ol_match = re.match(r'^[\s]*(\d+)\.\s+(.+)$', line)
            
            if ul_match:
                if not in_ul:
                    result.append('<ul style="margin: 8px 0; padding-left: 24px;">')
                    in_ul = True
                result.append(f'<li style="margin: 4px 0;">{ul_match.group(1)}</li>')
            elif ol_match:
                if not in_ol:
                    result.append('<ol style="margin: 8px 0; padding-left: 24px;">')
                    in_ol = True
                result.append(f'<li style="margin: 4px 0;">{ol_match.group(2)}</li>')
            else:
                if in_ul:
                    result.append('</ul>')
                    in_ul = False
                if in_ol:
                    result.append('</ol>')
                    in_ol = False
                result.append(line)
        
        # Close any open lists
        if in_ul:
            result.append('</ul>')
        if in_ol:
            result.append('</ol>')
        
        return '\n'.join(result)
    
    def _process_blockquotes(self, text: str) -> str:
        """Convert > quotes to HTML."""
        text = re.sub(
            r'^&gt;\s*(.+)$',
            r'<blockquote style="border-left: 3px solid #10a37f; padding-left: 12px; margin: 8px 0; color: #aaa;">\1</blockquote>',
            text,
            flags=re.MULTILINE
        )
        return text
    
    def _process_horizontal_rules(self, text: str) -> str:
        """Convert --- to horizontal rules."""
        text = re.sub(
            r'^-{3,}$',
            r'<hr style="border: none; border-top: 1px solid #3a3a3a; margin: 16px 0;">',
            text,
            flags=re.MULTILINE
        )
        return text
    
    def _process_newlines(self, text: str) -> str:
        """Convert newlines to <br> except in pre/code blocks."""
        # Split by code blocks, process non-code parts
        parts = re.split(r'(<div class="code-container">.*?</div>)', text, flags=re.DOTALL)
        
        result = []
        for part in parts:
            if part.startswith('<div class="code-container">'):
                result.append(part)
            else:
                # Convert double newlines to paragraphs
                part = re.sub(r'\n\n+', '</p><p>', part)
                # Convert single newlines to <br>
                part = re.sub(r'\n', '<br>', part)
                result.append(part)
        
        return ''.join(result)
    
    def _wrap_html(self, content: str) -> str:
        """Wrap content in styled HTML container with configurable font size."""
        # Calculate scaled font sizes
        h1_size = int(self.font_size * 1.6)  # ~29px at 18px base
        h2_size = int(self.font_size * 1.35)  # ~24px at 18px base
        h3_size = int(self.font_size * 1.15)  # ~21px at 18px base
        
        return f'''
        <html>
        <head>
        <style>
            body {{
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: {self.font_size}px;
                line-height: 1.7;
                color: {self.COLORS['text']};
                background: transparent;
                margin: 0;
                padding: 0;
                word-wrap: break-word;
                overflow-wrap: break-word;
                white-space: normal;
            }}
            p {{
                margin: 12px 0;
                word-wrap: break-word;
                overflow-wrap: break-word;
            }}
            h1 {{
                font-size: {h1_size}px;
                margin: 16px 0 12px 0;
                font-weight: 600;
            }}
            h2 {{
                font-size: {h2_size}px;
                margin: 14px 0 10px 0;
                font-weight: 600;
            }}
            h3 {{
                font-size: {h3_size}px;
                margin: 12px 0 8px 0;
                font-weight: 600;
            }}
            ul, ol {{
                margin: 10px 0;
                padding-left: 24px;
            }}
            li {{
                margin: 6px 0;
            }}
            a {{
                color: {self.COLORS['link']};
            }}
            a:hover {{
                text-decoration: underline;
            }}
            {self.CODE_STYLE}
        </style>
        </head>
        <body>
        <p>{content}</p>
        </body>
        </html>
        '''
    
    def get_code_blocks(self) -> List[Dict]:
        """Get extracted code blocks from last render."""
        return self.code_blocks
    
    def extract_links(self, text: str) -> List[Dict]:
        """Extract all links from markdown text."""
        pattern = r'\[([^\]]+)\]\(([^)]+)\)'
        matches = re.findall(pattern, text)
        return [{'text': m[0], 'url': m[1]} for m in matches]
    
    def render_citation(self, index: int, title: str, url: str, domain: str) -> str:
        """Render a citation link like Perplexity [1] Title (domain.com)."""
        return f'''<span style="display: inline-block; margin: 4px 8px 4px 0;">
            <a href="{url}" style="color: #10a37f; text-decoration: none;">
                <span style="background: #2d2d2d; padding: 2px 6px; border-radius: 4px; margin-right: 4px;">[{index}]</span>
                {title}
            </a>
            <span style="color: #888; font-size: 12px;">({domain})</span>
        </span>'''
    
    def render_citations(self, sources: List[Dict]) -> str:
        """Render a list of citation sources."""
        if not sources:
            return ""
        
        citations_html = '<div style="margin-top: 16px; padding-top: 12px; border-top: 1px solid #3a3a3a;"><strong style="color: #888; font-size: 12px;">Sources:</strong><br>'
        
        for i, source in enumerate(sources, 1):
            title = source.get('title', source.get('url', 'Source'))
            url = source.get('url', '#')
            domain = source.get('domain', '')
            if not domain and url:
                try:
                    from urllib.parse import urlparse
                    domain = urlparse(url).netloc
                except Exception as e:
                    domain = ''
            
            citations_html += self.render_citation(i, title, url, domain) + '<br>'
        
        citations_html += '</div>'
        return citations_html


# ============================================================
# EXAMPLE USAGE
# ============================================================
if __name__ == "__main__":
    print("🚀 Testing MarkdownRenderer...")
    
    renderer = MarkdownRenderer()
    
    # Test markdown
    test_text = """# Hello World

This is **bold** and *italic* text.

Here's some `inline code` and a [link](https://google.com).

## Code Example

```python
def hello():
    print("Hello, LADA!")
    return 42
```

- Item one
- Item two
- Item three

1. First
2. Second
3. Third

> This is a quote

---

That's all!
"""
    
    html_output = renderer.render(test_text)
    print(f"\n📝 Input length: {len(test_text)} chars")
    print(f"📄 Output length: {len(html_output)} chars")
    print(f"📦 Code blocks found: {len(renderer.get_code_blocks())}")
    
    # Show code blocks
    for block in renderer.get_code_blocks():
        print(f"   - {block['language']}: {len(block['code'])} chars")
    
    # Test citations
    sources = [
        {'title': 'Python Docs', 'url': 'https://python.org', 'domain': 'python.org'},
        {'title': 'Stack Overflow', 'url': 'https://stackoverflow.com/q/123', 'domain': 'stackoverflow.com'},
    ]
    citations = renderer.render_citations(sources)
    print(f"\n📚 Citations HTML: {len(citations)} chars")
    
    print("\n✅ MarkdownRenderer test complete!")
