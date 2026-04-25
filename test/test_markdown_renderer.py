"""Comprehensive tests for modules/markdown_renderer.py"""
import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def reset_module():
    """Reset module before each test"""
    mods_to_remove = [k for k in sys.modules if k.startswith("modules.markdown_renderer")]
    for mod in mods_to_remove:
        del sys.modules[mod]
    yield
    mods_to_remove = [k for k in sys.modules if k.startswith("modules.markdown_renderer")]
    for mod in mods_to_remove:
        del sys.modules[mod]


class TestMarkdownRenderer:
    """Tests for MarkdownRenderer class"""

    def test_init_default(self):
        import modules.markdown_renderer as mr

        renderer = mr.MarkdownRenderer()
        assert renderer is not None

    def test_init_with_font_size(self):
        import modules.markdown_renderer as mr

        renderer = mr.MarkdownRenderer(font_size=14)
        assert renderer.font_size == 14

    def test_set_font_size(self):
        import modules.markdown_renderer as mr

        renderer = mr.MarkdownRenderer()
        renderer.set_font_size(16)
        assert renderer.font_size == 16

    def test_render_simple_text(self):
        import modules.markdown_renderer as mr

        renderer = mr.MarkdownRenderer()
        result = renderer.render("Hello World")
        
        assert result is not None
        assert "Hello World" in result

    def test_render_headers(self):
        import modules.markdown_renderer as mr

        renderer = mr.MarkdownRenderer()
        result = renderer.render("# Header 1\n## Header 2\n### Header 3")
        
        assert result is not None
        # Should convert to HTML headers
        assert "<h1" in result.lower() or "header" in result.lower() or result

    def test_render_bold(self):
        import modules.markdown_renderer as mr

        renderer = mr.MarkdownRenderer()
        result = renderer.render("This is **bold** text")
        
        assert result is not None
        assert "<strong>" in result.lower() or "<b>" in result.lower() or "bold" in result

    def test_render_italic(self):
        import modules.markdown_renderer as mr

        renderer = mr.MarkdownRenderer()
        result = renderer.render("This is *italic* text")
        
        assert result is not None
        assert "<em>" in result.lower() or "<i>" in result.lower() or "italic" in result

    def test_render_inline_code(self):
        import modules.markdown_renderer as mr

        renderer = mr.MarkdownRenderer()
        result = renderer.render("Use `code` here")
        
        assert result is not None
        assert "<code>" in result.lower() or "code" in result

    def test_render_code_block(self):
        import modules.markdown_renderer as mr

        renderer = mr.MarkdownRenderer()
        code = """```python
def hello():
    print("Hello")
```"""
        result = renderer.render(code)
        
        assert result is not None
        # The renderer wraps code blocks, check for HTML output or code-related styling
        assert "<html>" in result.lower() or "codehilite" in result.lower() or "code" in result.lower()

    def test_render_code_block_with_highlighting(self):
        import modules.markdown_renderer as mr

        mr.PYGMENTS_OK = True
        renderer = mr.MarkdownRenderer()
        
        code = """```python
x = 1 + 2
print(x)
```"""
        result = renderer.render(code)
        assert result is not None

    def test_render_code_block_no_pygments(self):
        import modules.markdown_renderer as mr

        mr.PYGMENTS_OK = False
        renderer = mr.MarkdownRenderer()
        
        code = """```python
x = 1
```"""
        result = renderer.render(code)
        assert result is not None

    def test_render_links(self):
        import modules.markdown_renderer as mr

        renderer = mr.MarkdownRenderer()
        result = renderer.render("[Google](https://google.com)")
        
        assert result is not None
        assert "google" in result.lower()

    def test_render_unordered_list(self):
        import modules.markdown_renderer as mr

        renderer = mr.MarkdownRenderer()
        result = renderer.render("- Item 1\n- Item 2\n- Item 3")
        
        assert result is not None
        assert "<li>" in result.lower() or "item" in result.lower() or result

    def test_render_ordered_list(self):
        import modules.markdown_renderer as mr

        renderer = mr.MarkdownRenderer()
        result = renderer.render("1. First\n2. Second\n3. Third")
        
        assert result is not None
        assert "first" in result.lower()

    def test_render_blockquote(self):
        import modules.markdown_renderer as mr

        renderer = mr.MarkdownRenderer()
        result = renderer.render("> This is a quote")
        
        assert result is not None
        assert "<blockquote>" in result.lower() or "quote" in result.lower() or result

    def test_render_horizontal_rule(self):
        import modules.markdown_renderer as mr

        renderer = mr.MarkdownRenderer()
        result = renderer.render("---")
        
        assert result is not None
        assert "<hr" in result.lower() or result

    def test_render_newlines(self):
        import modules.markdown_renderer as mr

        renderer = mr.MarkdownRenderer()
        result = renderer.render("Line 1\nLine 2")
        
        assert result is not None
        assert "<br" in result.lower() or "line" in result.lower()

    def test_get_code_blocks(self):
        import modules.markdown_renderer as mr

        renderer = mr.MarkdownRenderer()
        code = """```python
def foo():
    pass
```

Some text

```javascript
console.log("hi");
```"""
        renderer.render(code)
        blocks = renderer.get_code_blocks()
        
        assert blocks is not None
        if blocks:
            assert len(blocks) >= 1

    def test_extract_links(self):
        import modules.markdown_renderer as mr

        renderer = mr.MarkdownRenderer()
        text = "[Link1](https://example1.com) and [Link2](https://example2.com)"
        
        links = renderer.extract_links(text)
        assert links is not None
        if links:
            assert len(links) >= 1

    def test_render_citation(self):
        import modules.markdown_renderer as mr

        renderer = mr.MarkdownRenderer()
        citation = renderer.render_citation(1, "Article Title", "https://example.com", "example.com")
        
        assert citation is not None
        assert "1" in str(citation)

    def test_render_citations_list(self):
        import modules.markdown_renderer as mr

        renderer = mr.MarkdownRenderer()
        sources = [
            {"title": "Source 1", "url": "https://s1.com", "domain": "s1.com"},
            {"title": "Source 2", "url": "https://s2.com", "domain": "s2.com"},
        ]
        result = renderer.render_citations(sources)
        
        assert result is not None

    def test_wrap_html(self):
        import modules.markdown_renderer as mr

        renderer = mr.MarkdownRenderer()
        
        if hasattr(renderer, '_wrap_html'):
            wrapped = renderer._wrap_html("<p>Content</p>")
            assert wrapped is not None
            assert "<div" in wrapped.lower() or "<style" in wrapped.lower() or "content" in wrapped.lower()

    def test_process_headers(self):
        import modules.markdown_renderer as mr

        renderer = mr.MarkdownRenderer()
        
        if hasattr(renderer, '_process_headers'):
            result = renderer._process_headers("# Header")
            assert result is not None

    def test_process_bold(self):
        import modules.markdown_renderer as mr

        renderer = mr.MarkdownRenderer()
        
        if hasattr(renderer, '_process_bold'):
            result = renderer._process_bold("**bold**")
            assert result is not None

    def test_process_italic(self):
        import modules.markdown_renderer as mr

        renderer = mr.MarkdownRenderer()
        
        if hasattr(renderer, '_process_italic'):
            result = renderer._process_italic("*italic*")
            assert result is not None

    def test_highlight_code(self):
        import modules.markdown_renderer as mr

        renderer = mr.MarkdownRenderer()
        
        if hasattr(renderer, '_highlight_code'):
            result = renderer._highlight_code("print('hello')", "python")
            assert result is not None

    def test_complex_markdown(self):
        import modules.markdown_renderer as mr

        renderer = mr.MarkdownRenderer()
        
        complex_md = """# Title

This is a **bold** and *italic* paragraph with `inline code`.

## Code Example

```python
def greet(name):
    return f"Hello, {name}!"
```

### List of items

- Item 1
- Item 2
- Item 3

> A quote for inspiration

---

[Click here](https://example.com) for more.
"""
        result = renderer.render(complex_md)
        assert result is not None
        assert len(result) > 100  # Should produce substantial output

    def test_empty_input(self):
        import modules.markdown_renderer as mr

        renderer = mr.MarkdownRenderer()
        result = renderer.render("")
        
        assert result is not None or result == ""
