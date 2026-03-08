"""
Tests for modules/export_manager.py
Covers: ExportManager for JSON, Markdown, PDF, DOCX export
"""

import pytest
import sys
import json
from unittest.mock import MagicMock, patch
from pathlib import Path
from datetime import datetime


# Reset module cache
@pytest.fixture(autouse=True)
def reset_modules():
    """Reset module cache before each test."""
    modules_to_reset = [k for k in sys.modules.keys() if 'export_manager' in k]
    for mod in modules_to_reset:
        del sys.modules[mod]
    yield


@pytest.fixture
def sample_conversation():
    """Sample conversation dict for testing."""
    return {
        'id': 'conv1',
        'title': 'Test Conversation',
        'created_at': datetime.now().isoformat(),
        'messages': [
            {'role': 'user', 'content': 'Hello', 'timestamp': datetime.now().isoformat()},
            {'role': 'assistant', 'content': 'Hi there!', 'timestamp': datetime.now().isoformat()}
        ]
    }


class TestExportManagerInit:
    """Tests for ExportManager initialization."""
    
    def test_init_default(self, tmp_path):
        """Test default initialization."""
        from modules import export_manager as em
        manager = em.ExportManager(export_dir=str(tmp_path / "exports"))
        assert manager.export_dir.exists()
    
    def test_init_creates_directory(self, tmp_path):
        """Test that init creates export directory."""
        from modules import export_manager as em
        export_path = tmp_path / "new_exports"
        manager = em.ExportManager(export_dir=str(export_path))
        assert export_path.exists()


class TestExportJSON:
    """Tests for JSON export."""
    
    def test_export_json(self, tmp_path, sample_conversation):
        """Test exporting to JSON."""
        from modules import export_manager as em
        manager = em.ExportManager(export_dir=str(tmp_path))
        result = manager.export_conversation(sample_conversation, format="json")
        assert result is not None
        assert result.endswith('.json')
        assert Path(result).exists()
    
    def test_export_json_content(self, tmp_path, sample_conversation):
        """Test JSON export content."""
        from modules import export_manager as em
        manager = em.ExportManager(export_dir=str(tmp_path))
        result = manager.export_conversation(sample_conversation, format="json")
        
        with open(result, 'r') as f:
            data = json.load(f)
        assert data['title'] == 'Test Conversation'
        assert len(data['messages']) == 2


class TestExportMarkdown:
    """Tests for Markdown export."""
    
    def test_export_markdown(self, tmp_path, sample_conversation):
        """Test exporting to Markdown."""
        from modules import export_manager as em
        manager = em.ExportManager(export_dir=str(tmp_path))
        result = manager.export_conversation(sample_conversation, format="markdown")
        assert result is not None
        assert result.endswith('.md')
    
    def test_export_md_alias(self, tmp_path, sample_conversation):
        """Test 'md' format alias."""
        from modules import export_manager as em
        manager = em.ExportManager(export_dir=str(tmp_path))
        result = manager.export_conversation(sample_conversation, format="md")
        assert result is not None
        assert result.endswith('.md')
    
    def test_markdown_content(self, tmp_path, sample_conversation):
        """Test Markdown content structure."""
        from modules import export_manager as em
        manager = em.ExportManager(export_dir=str(tmp_path))
        result = manager.export_conversation(sample_conversation, format="markdown")
        
        with open(result, 'r') as f:
            content = f.read()
        assert 'Test Conversation' in content


class TestExportPDF:
    """Tests for PDF export."""
    
    def test_export_pdf_when_available(self, tmp_path, sample_conversation):
        """Test PDF export when reportlab is available."""
        from modules import export_manager as em
        
        if not em.REPORTLAB_OK:
            pytest.skip("reportlab not installed")
        
        manager = em.ExportManager(export_dir=str(tmp_path))
        result = manager.export_conversation(sample_conversation, format="pdf")
        assert result is None or result.endswith('.pdf')
    
    def test_export_pdf_unavailable(self, tmp_path, sample_conversation):
        """Test PDF export when reportlab not available."""
        from modules import export_manager as em
        
        if em.REPORTLAB_OK:
            pytest.skip("reportlab is installed")
        
        manager = em.ExportManager(export_dir=str(tmp_path))
        result = manager.export_conversation(sample_conversation, format="pdf")
        # Should return None when not available
        assert result is None


class TestExportDOCX:
    """Tests for DOCX export."""
    
    def test_export_docx_when_available(self, tmp_path, sample_conversation):
        """Test DOCX export when python-docx is available."""
        from modules import export_manager as em
        
        if not em.DOCX_OK:
            pytest.skip("python-docx not installed")
        
        manager = em.ExportManager(export_dir=str(tmp_path))
        result = manager.export_conversation(sample_conversation, format="docx")
        assert result is None or result.endswith('.docx')
    
    def test_export_docx_unavailable(self, tmp_path, sample_conversation):
        """Test DOCX export when python-docx not available."""
        from modules import export_manager as em
        
        if em.DOCX_OK:
            pytest.skip("python-docx is installed")
        
        manager = em.ExportManager(export_dir=str(tmp_path))
        result = manager.export_conversation(sample_conversation, format="docx")
        assert result is None


class TestExportInvalidFormat:
    """Tests for invalid format handling."""
    
    def test_export_invalid_format(self, tmp_path, sample_conversation):
        """Test export with invalid format."""
        from modules import export_manager as em
        manager = em.ExportManager(export_dir=str(tmp_path))
        result = manager.export_conversation(sample_conversation, format="invalid")
        assert result is None


class TestExportCustomFilename:
    """Tests for custom filename."""
    
    def test_export_custom_filename(self, tmp_path, sample_conversation):
        """Test export with custom filename."""
        from modules import export_manager as em
        manager = em.ExportManager(export_dir=str(tmp_path))
        result = manager.export_conversation(
            sample_conversation, 
            format="json",
            filename="my_custom_export"
        )
        assert "my_custom_export" in result


class TestExportEmptyConversation:
    """Tests for edge cases."""
    
    def test_export_empty_messages(self, tmp_path):
        """Test exporting conversation with no messages."""
        from modules import export_manager as em
        empty_conv = {
            'title': 'Empty Chat',
            'messages': []
        }
        manager = em.ExportManager(export_dir=str(tmp_path))
        result = manager.export_conversation(empty_conv, format="json")
        assert result is not None
    
    def test_export_unicode_title(self, tmp_path):
        """Test exporting with unicode in title."""
        from modules import export_manager as em
        conv = {
            'title': 'Chat 日本語 emoji 🎉',
            'messages': [{'role': 'user', 'content': 'Hello 世界'}]
        }
        manager = em.ExportManager(export_dir=str(tmp_path))
        result = manager.export_conversation(conv, format="json")
        assert result is not None
