"""
Unit Tests for Error Sanitizer Module

Tests error categorization, sensitive data redaction, HTTP status codes, and sanitization.
"""

import pytest
from modules.error_sanitizer import (
    redact_sensitive_data,
    categorize_error,
    ErrorCategory,
    get_user_friendly_message,
    sanitize_error,
    safe_error_response,
    SafeErrorResponse,
    log_error_with_context,
    ErrorSeverity
)


class TestSensitiveDataRedaction:
    """Test redaction of sensitive data patterns"""
    
    def test_redact_openai_api_key(self):
        """Test OpenAI API key redaction"""
        text = "My API key is sk-1234567890abcdef1234567890abcdef1234567890abcdef"
        redacted = redact_sensitive_data(text)
        
        assert "sk-1234567890" not in redacted
        assert "[API_KEY_REDACTED]" in redacted
    
    def test_redact_groq_api_key(self):
        """Test Groq API key redaction"""
        text = "Using key: gsk_1234567890abcdefghijklmnopqrstuvwxyz1234567890AB"
        redacted = redact_sensitive_data(text)
        
        assert "gsk_" not in redacted
        assert "[API_KEY_REDACTED]" in redacted
    
    def test_redact_bearer_token(self):
        """Test Bearer token redaction"""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        redacted = redact_sensitive_data(text)
        
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in redacted
        assert "Bearer [TOKEN_REDACTED]" in redacted
    
    def test_redact_windows_file_path(self):
        """Test Windows file path redaction"""
        text = r"Error in file C:\\Users\\john.doe\\Documents\\config.json"
        redacted = redact_sensitive_data(text)
        
        assert "john.doe" not in redacted
        assert "[USER]" in redacted
    
    def test_redact_unix_file_path(self):
        """Test Unix file path redaction"""
        text = "Config at /home/alice/config.yaml"
        redacted = redact_sensitive_data(text)
        
        assert "alice" not in redacted
        assert "/home/[USER]" in redacted
    
    def test_redact_internal_ip(self):
        """Test internal IP redaction"""
        text = "Connected to 192.168.1.100 and 10.0.0.50"
        redacted = redact_sensitive_data(text)
        
        assert "192.168.1.100" not in redacted
        assert "10.0.0.50" not in redacted
        assert "[INTERNAL_IP]" in redacted
    
    def test_redact_password_in_config(self):
        """Test password redaction in config"""
        text = 'password="mySecretPass123"'
        redacted = redact_sensitive_data(text)
        
        assert "mySecretPass123" not in redacted
        assert "[PASSWORD_REDACTED]" in redacted
    
    def test_redact_password_in_url(self):
        """Test password in URL redaction"""
        text = "mysql://user:secretPass@localhost:3306/db"
        redacted = redact_sensitive_data(text)
        
        assert "secretPass" not in redacted
        assert "[PASSWORD_REDACTED]" in redacted
    
    def test_no_redaction_needed(self):
        """Test text with no sensitive data"""
        text = "This is a normal error message"
        redacted = redact_sensitive_data(text)
        
        assert redacted == text


class TestErrorCategorization:
    """Test error categorization and HTTP status code mapping"""
    
    def test_authentication_error(self):
        """Test authentication error categorization"""
        error = ValueError("authentication failed")
        category, code = categorize_error(error)
        
        assert category == ErrorCategory.AUTHENTICATION
        assert code == 401
    
    def test_authorization_error(self):
        """Test authorization error categorization"""
        error = PermissionError("permission denied")
        category, code = categorize_error(error)
        
        assert category == ErrorCategory.AUTHORIZATION
        assert code == 403
    
    def test_not_found_error(self):
        """Test not found error categorization"""
        error = FileNotFoundError("file not found")
        category, code = categorize_error(error)
        
        assert category == ErrorCategory.NOT_FOUND
        assert code == 404
    
    def test_validation_error(self):
        """Test validation error categorization"""
        error = ValueError("invalid input")
        category, code = categorize_error(error)
        
        assert category == ErrorCategory.VALIDATION
        assert code == 400
    
    def test_conflict_error(self):
        """Test conflict error categorization"""
        error = RuntimeError("already exists")
        category, code = categorize_error(error)
        
        assert category == ErrorCategory.CONFLICT
        assert code == 409
    
    def test_rate_limit_error(self):
        """Test rate limit error categorization"""
        error = Exception("rate limit exceeded")
        category, code = categorize_error(error)
        
        assert category == ErrorCategory.RATE_LIMIT
        assert code == 429
    
    def test_timeout_error(self):
        """Test timeout error categorization"""
        error = TimeoutError("request timed out")
        category, code = categorize_error(error)
        
        assert category == ErrorCategory.TIMEOUT
        assert code == 504
    
    def test_unavailable_error(self):
        """Test unavailable error categorization"""
        error = ConnectionError("service unavailable")
        category, code = categorize_error(error)
        
        assert category == ErrorCategory.UNAVAILABLE
        assert code == 503
    
    def test_generic_server_error(self):
        """Test generic server error categorization"""
        error = RuntimeError("something went wrong")
        category, code = categorize_error(error)
        
        assert category == ErrorCategory.SERVER_ERROR
        assert code == 500


class TestUserFriendlyMessages:
    """Test user-friendly error message generation"""
    
    def test_validation_message(self):
        """Test validation error message"""
        msg = get_user_friendly_message(ErrorCategory.VALIDATION)
        
        assert "invalid" in msg.lower()
        assert "input" in msg.lower()
    
    def test_authentication_message(self):
        """Test authentication error message"""
        msg = get_user_friendly_message(ErrorCategory.AUTHENTICATION)
        
        assert "authentication" in msg.lower() or "credentials" in msg.lower()
    
    def test_not_found_message(self):
        """Test not found error message"""
        msg = get_user_friendly_message(ErrorCategory.NOT_FOUND)
        
        assert "not found" in msg.lower()
    
    def test_rate_limit_message(self):
        """Test rate limit error message"""
        msg = get_user_friendly_message(ErrorCategory.RATE_LIMIT)
        
        assert "too many" in msg.lower() or "slow down" in msg.lower()


class TestSanitizeError:
    """Test error sanitization"""
    
    def test_sanitize_removes_internal_details(self):
        """Test that internal error details are removed"""
        error = ValueError("Database connection failed at C:\\Users\\admin\\app.py:123")
        result = sanitize_error(error, operation="query_database")
        
        assert result["success"] is False
        assert "app.py" not in result["error"]
        assert "admin" not in result["error"]
        assert result["status_code"] == 500
    
    def test_sanitize_includes_category(self):
        """Test that category is included"""
        error = ValueError("invalid input")
        result = sanitize_error(error, operation="test", include_category=True)
        
        assert "error_category" in result
        assert result["error_category"] == "validation"
    
    def test_sanitize_excludes_category(self):
        """Test that category can be excluded"""
        error = ValueError("invalid input")
        result = sanitize_error(error, operation="test", include_category=False)
        
        assert "error_category" not in result
    
    def test_safe_error_response_structure(self):
        """Test safe_error_response structure"""
        error = Exception("test error")
        result = safe_error_response(error, operation="test")
        
        assert "success" in result
        assert "error" in result
        assert "status_code" in result
        assert result["success"] is False


class TestSafeErrorResponseException:
    """Test SafeErrorResponse exception class"""
    
    def test_create_safe_error_response(self):
        """Test creating SafeErrorResponse"""
        error = SafeErrorResponse("Invalid model ID", status_code=400, category=ErrorCategory.VALIDATION)
        
        assert str(error) == "Invalid model ID"
        assert error.status_code == 400
        assert error.category == ErrorCategory.VALIDATION
    
    def test_to_dict(self):
        """Test converting SafeErrorResponse to dict"""
        error = SafeErrorResponse("Not found", status_code=404)
        result = error.to_dict()
        
        assert result["success"] is False
        assert result["error"] == "Not found"
        assert result["status_code"] == 404
        assert "error_category" in result


class TestLogErrorWithContext:
    """Test error logging with context"""
    
    def test_log_error_redacts_context(self, caplog):
        """Test that context is redacted in logs"""
        error = ValueError("test error")
        context = {
            "api_key": "sk-1234567890abcdefghijklmnopqrstuvwxyz1234567890AB",
            "user_id": "user_123"
        }
        
        log_error_with_context(error, context, severity=ErrorSeverity.MEDIUM)
        
        # Check that API key is redacted
        assert "sk-1234567890abcdefghijklmnopqrstuvwxyz1234567890AB" not in caplog.text
        assert "[API_KEY_REDACTED]" in caplog.text or "user_123" in caplog.text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
