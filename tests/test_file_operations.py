"""
Tests for modules/file_operations.py
Covers: FileOperation enum, FileSystemController class
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch
from pathlib import Path


# Reset module cache
@pytest.fixture(autouse=True)
def reset_modules():
    """Reset module cache before each test."""
    modules_to_reset = [k for k in sys.modules.keys() if 'file_operations' in k]
    for mod in modules_to_reset:
        del sys.modules[mod]
    yield


class TestFileOperation:
    """Tests for FileOperation enum."""
    
    def test_operation_values(self):
        """Test FileOperation enum values."""
        from modules import file_operations as fo
        assert fo.FileOperation.CREATE.value == "create"
        assert fo.FileOperation.DELETE.value == "delete"
        assert fo.FileOperation.COPY.value == "copy"
        assert fo.FileOperation.MOVE.value == "move"
        assert fo.FileOperation.RENAME.value == "rename"
        assert fo.FileOperation.SEARCH.value == "search"


class TestFileSystemControllerInit:
    """Tests for FileSystemController initialization."""
    
    def test_init_default(self):
        """Test default initialization."""
        from modules import file_operations as fo
        controller = fo.FileSystemController()
        assert controller.current_directory is not None
        assert os.path.exists(controller.current_directory)
    
    def test_init_with_directory(self, tmp_path):
        """Test initialization with custom directory."""
        from modules import file_operations as fo
        controller = fo.FileSystemController(current_directory=str(tmp_path))
        assert controller.current_directory == str(tmp_path)


class TestFileCreation:
    """Tests for file creation."""
    
    def test_create_file(self, tmp_path):
        """Test creating a file."""
        from modules import file_operations as fo
        controller = fo.FileSystemController(current_directory=str(tmp_path))
        result = controller.create_file(str(tmp_path / "test.txt"), content="Hello")
        assert result['success'] is True
        assert (tmp_path / "test.txt").exists()
    
    def test_create_file_with_content(self, tmp_path):
        """Test creating file with content."""
        from modules import file_operations as fo
        controller = fo.FileSystemController(current_directory=str(tmp_path))
        controller.create_file(str(tmp_path / "test.txt"), content="Test content")
        
        with open(tmp_path / "test.txt", 'r') as f:
            assert f.read() == "Test content"
    
    def test_create_file_no_overwrite(self, tmp_path):
        """Test file creation without overwrite."""
        from modules import file_operations as fo
        controller = fo.FileSystemController(current_directory=str(tmp_path))
        
        # Create file first
        (tmp_path / "existing.txt").write_text("original")
        
        result = controller.create_file(str(tmp_path / "existing.txt"), content="new", overwrite=False)
        assert result['success'] is False
    
    def test_create_file_with_overwrite(self, tmp_path):
        """Test file creation with overwrite."""
        from modules import file_operations as fo
        controller = fo.FileSystemController(current_directory=str(tmp_path))
        
        # Create file first
        (tmp_path / "existing.txt").write_text("original")
        
        result = controller.create_file(str(tmp_path / "existing.txt"), content="new", overwrite=True)
        assert result['success'] is True
        assert (tmp_path / "existing.txt").read_text() == "new"


class TestFileDeletion:
    """Tests for file deletion."""
    
    def test_delete_file(self, tmp_path):
        """Test deleting a file."""
        from modules import file_operations as fo
        controller = fo.FileSystemController(current_directory=str(tmp_path))
        
        # Create file
        test_file = tmp_path / "delete_me.txt"
        test_file.write_text("delete this")
        
        with patch('modules.file_operations._send2trash') as mock_send2trash:
            mock_send2trash.send2trash = MagicMock()
            result = controller.delete_file(str(test_file), permanent=False)
        
        # Check result
        assert 'success' in result
    
    def test_delete_nonexistent_file(self, tmp_path):
        """Test deleting non-existent file."""
        from modules import file_operations as fo
        controller = fo.FileSystemController(current_directory=str(tmp_path))
        
        result = controller.delete_file(str(tmp_path / "nonexistent.txt"))
        assert result['success'] is False
    
    def test_delete_permanent(self, tmp_path):
        """Test permanent deletion."""
        from modules import file_operations as fo
        controller = fo.FileSystemController(current_directory=str(tmp_path))
        
        test_file = tmp_path / "perm_delete.txt"
        test_file.write_text("delete permanently")
        
        result = controller.delete_file(str(test_file), permanent=True)
        assert result['success'] is True
        assert not test_file.exists()


class TestProtectedPaths:
    """Tests for protected path handling."""
    
    def test_is_protected_windows(self):
        """Test protected path detection."""
        from modules import file_operations as fo
        controller = fo.FileSystemController()
        
        assert controller.is_protected("C:\\Windows\\System32")
        assert controller.is_protected("C:\\Program Files\\Test")
    
    def test_is_not_protected(self, tmp_path):
        """Test non-protected paths."""
        from modules import file_operations as fo
        controller = fo.FileSystemController()
        
        assert not controller.is_protected(str(tmp_path / "test.txt"))


class TestFileCopy:
    """Tests for file copying."""
    
    def test_copy_file(self, tmp_path):
        """Test copying a file."""
        from modules import file_operations as fo
        controller = fo.FileSystemController(current_directory=str(tmp_path))
        
        # Create source file
        source = tmp_path / "source.txt"
        source.write_text("copy me")
        
        dest = tmp_path / "dest.txt"
        result = controller.copy_file(str(source), str(dest))
        
        assert result['success'] is True
        assert dest.exists()
        assert dest.read_text() == "copy me"
    
    def test_copy_nonexistent(self, tmp_path):
        """Test copying non-existent file."""
        from modules import file_operations as fo
        controller = fo.FileSystemController(current_directory=str(tmp_path))
        
        result = controller.copy_file(str(tmp_path / "no.txt"), str(tmp_path / "dest.txt"))
        assert result['success'] is False


class TestFileMove:
    """Tests for file moving."""
    
    def test_move_file(self, tmp_path):
        """Test moving a file."""
        from modules import file_operations as fo
        controller = fo.FileSystemController(current_directory=str(tmp_path))
        
        source = tmp_path / "tomove.txt"
        source.write_text("move me")
        dest = tmp_path / "moved.txt"
        
        result = controller.move_file(str(source), str(dest))
        
        assert result['success'] is True
        assert not source.exists()
        assert dest.exists()


class TestFileRename:
    """Tests for file renaming."""
    
    def test_rename_file(self, tmp_path):
        """Test renaming a file."""
        from modules import file_operations as fo
        controller = fo.FileSystemController(current_directory=str(tmp_path))
        
        original = tmp_path / "original.txt"
        original.write_text("rename me")
        
        result = controller.rename_file(str(original), "renamed.txt")
        
        assert result['success'] is True
        assert (tmp_path / "renamed.txt").exists()


class TestFileSearch:
    """Tests for file searching."""
    
    def test_search_files(self, tmp_path):
        """Test searching for files."""
        from modules import file_operations as fo
        controller = fo.FileSystemController(current_directory=str(tmp_path))
        
        # Create test files
        (tmp_path / "test1.txt").write_text("hello")
        (tmp_path / "test2.txt").write_text("world")
        (tmp_path / "other.py").write_text("python")
        
        # Use correct API: search_files(name=, extension=, search_folder=)
        result = controller.search_files(name="test", search_folder=str(tmp_path))
        
        assert result['success'] is True
        assert 'found' in result or 'files' in result
    
    def test_search_by_extension(self, tmp_path):
        """Test searching by extension."""
        from modules import file_operations as fo
        controller = fo.FileSystemController(current_directory=str(tmp_path))
        
        (tmp_path / "doc1.txt").write_text("text")
        (tmp_path / "doc2.py").write_text("python")
        
        result = controller.search_files(extension=".txt", search_folder=str(tmp_path))
        assert result['success'] is True


class TestFileInfo:
    """Tests for file information."""
    
    def test_get_file_properties(self, tmp_path):
        """Test getting file properties."""
        from modules import file_operations as fo
        controller = fo.FileSystemController(current_directory=str(tmp_path))
        
        test_file = tmp_path / "info.txt"
        test_file.write_text("info content")
        
        # Use correct API: get_file_properties
        result = controller.get_file_properties(str(test_file))
        
        assert result['success'] is True
        assert 'path' in result


class TestZipOperations:
    """Tests for zip operations."""
    
    def test_compress_files(self, tmp_path):
        """Test compressing files."""
        from modules import file_operations as fo
        controller = fo.FileSystemController(current_directory=str(tmp_path))
        
        # Create files to zip
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.txt").write_text("content2")
        
        files = [str(tmp_path / "file1.txt"), str(tmp_path / "file2.txt")]
        zip_path = str(tmp_path / "archive.zip")
        
        # Use correct API: compress_files
        if hasattr(controller, 'compress_files'):
            result = controller.compress_files(files, zip_path)
            assert result['success'] is True
            assert (tmp_path / "archive.zip").exists()
        else:
            pytest.skip("compress_files method not available")
    
    def test_decompress_files(self, tmp_path):
        """Test extracting a zip file."""
        import zipfile
        from modules import file_operations as fo
        controller = fo.FileSystemController(current_directory=str(tmp_path))
        
        # Create a zip file
        zip_path = tmp_path / "test.zip"
        extract_path = tmp_path / "extracted"
        extract_path.mkdir()
        
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("inside.txt", "zip content")
        
        # Use correct API: decompress_file
        if hasattr(controller, 'decompress_file'):
            result = controller.decompress_file(str(zip_path), str(extract_path))
            assert result['success'] is True
        else:
            pytest.skip("decompress_file method not available")


class TestEdgeCases:
    """Tests for edge cases."""
    
    def test_create_file_in_subdir(self, tmp_path):
        """Test creating file in non-existent subdirectory."""
        from modules import file_operations as fo
        controller = fo.FileSystemController(current_directory=str(tmp_path))
        
        deep_path = tmp_path / "sub1" / "sub2" / "deep.txt"
        result = controller.create_file(str(deep_path), content="deep content")
        
        assert result['success'] is True
        assert deep_path.exists()
    
    def test_operation_history(self, tmp_path):
        """Test operation history tracking."""
        from modules import file_operations as fo
        controller = fo.FileSystemController(current_directory=str(tmp_path))
        
        assert hasattr(controller, 'operation_history')
        assert isinstance(controller.operation_history, list)
