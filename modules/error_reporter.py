"""
LADA v7.0 - Error Reporter
Crash reporting and error analytics with Sentry integration
"""

import sys
import traceback
import logging
from datetime import datetime
from pathlib import Path
import json

# Try to import sentry_sdk once at module level
try:
    import sentry_sdk  # type: ignore
    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False
    sentry_sdk = None


class ErrorReporter:
    """
    Error reporting and analytics system
    Can integrate with Sentry or log errors locally
    """
    
    def __init__(self, dsn=None, environment="production"):
        """
        Initialize error reporter
        
        Args:
            dsn: Sentry DSN (optional)
            environment: Environment name (production/development/test)
        """
        self.environment = environment
        self.sentry_enabled = False
        self.error_log_file = Path("logs/errors.json")
        self.error_log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Try to initialize Sentry if DSN provided
        if dsn and SENTRY_AVAILABLE:
            try:
                sentry_sdk.init(
                    dsn=dsn,
                    environment=environment,
                    traces_sample_rate=1.0,
                    profiles_sample_rate=1.0,
                )
                self.sentry_enabled = True
                logging.info("Sentry error reporting enabled")
            except Exception as e:
                logging.warning(f"Failed to initialize Sentry: {e}. Using local error logging.")
        elif dsn and not SENTRY_AVAILABLE:
            logging.warning("Sentry SDK not installed. Using local error logging.")
        
        # Setup exception handler
        sys.excepthook = self._exception_handler
    
    def capture_exception(self, exception, context=None):
        """
        Capture and report an exception
        
        Args:
            exception: The exception object
            context: Additional context dict
        """
        error_data = {
            'timestamp': datetime.now().isoformat(),
            'type': type(exception).__name__,
            'message': str(exception),
            'traceback': traceback.format_exc(),
            'context': context or {},
            'environment': self.environment
        }
        
        # Log locally
        self._log_error_locally(error_data)
        
        # Send to Sentry if enabled
        if self.sentry_enabled and SENTRY_AVAILABLE:
            try:
                with sentry_sdk.push_scope() as scope:
                    if context:
                        for key, value in context.items():
                            scope.set_context(key, value)
                    sentry_sdk.capture_exception(exception)
            except Exception as e:
                logging.error(f"Failed to send error to Sentry: {e}")
        
        return error_data
    
    def capture_message(self, message, level="info", context=None):
        """
        Capture a log message
        
        Args:
            message: Message string
            level: Log level (info/warning/error)
            context: Additional context
        """
        log_data = {
            'timestamp': datetime.now().isoformat(),
            'level': level,
            'message': message,
            'context': context or {}
        }
        
        # Log locally
        self._log_error_locally(log_data)
        
        # Send to Sentry if enabled
        if self.sentry_enabled and SENTRY_AVAILABLE:
            try:
                with sentry_sdk.push_scope() as scope:
                    if context:
                        for key, value in context.items():
                            scope.set_tag(key, value)
                    sentry_sdk.capture_message(message, level=level)
            except Exception as e:
                logging.error(f"Failed to send message to Sentry: {e}")
    
    def add_breadcrumb(self, message, category="default", level="info", data=None):
        """
        Add breadcrumb for debugging
        
        Args:
            message: Breadcrumb message
            category: Category (e.g., "navigation", "query", "action")
            level: Severity level
            data: Additional data dict
        """
        breadcrumb = {
            'timestamp': datetime.now().isoformat(),
            'message': message,
            'category': category,
            'level': level,
            'data': data or {}
        }
        
        if self.sentry_enabled and SENTRY_AVAILABLE:
            try:
                sentry_sdk.add_breadcrumb(
                    message=message,
                    category=category,
                    level=level,
                    data=data
                )
            except Exception as e:
                logging.error(f"Failed to add breadcrumb: {e}")
        
        # Also log locally
        self._log_breadcrumb(breadcrumb)
    
    def set_user(self, user_id, email=None, username=None):
        """
        Set user context for error reports
        
        Args:
            user_id: User identifier
            email: User email
            username: Username
        """
        if self.sentry_enabled and SENTRY_AVAILABLE:
            try:
                sentry_sdk.set_user({
                    "id": user_id,
                    "email": email,
                    "username": username
                })
            except Exception as e:
                logging.error(f"Failed to set user context: {e}")
    
    def set_context(self, key, value):
        """
        Set custom context
        
        Args:
            key: Context key
            value: Context value (dict or any serializable)
        """
        if self.sentry_enabled and SENTRY_AVAILABLE:
            try:
                sentry_sdk.set_context(key, value)
            except Exception as e:
                logging.error(f"Failed to set context: {e}")
    
    def _exception_handler(self, exc_type, exc_value, exc_traceback):
        """Custom exception handler"""
        # Don't report KeyboardInterrupt
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        
        # Capture exception
        self.capture_exception(exc_value)
        
        # Call default handler
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
    
    def _log_error_locally(self, error_data):
        """Log error to local JSON file"""
        try:
            # Read existing errors
            errors = []
            if self.error_log_file.exists():
                with open(self.error_log_file, 'r', encoding='utf-8') as f:
                    errors = json.load(f)
            
            # Add new error
            errors.append(error_data)
            
            # Keep last 1000 errors
            errors = errors[-1000:]
            
            # Save back
            with open(self.error_log_file, 'w', encoding='utf-8') as f:
                json.dump(errors, f, indent=2)
                
        except Exception as e:
            logging.error(f"Failed to log error locally: {e}")
    
    def _log_breadcrumb(self, breadcrumb):
        """Log breadcrumb locally"""
        breadcrumb_file = Path("logs/breadcrumbs.json")
        breadcrumb_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            breadcrumbs = []
            if breadcrumb_file.exists():
                with open(breadcrumb_file, 'r', encoding='utf-8') as f:
                    breadcrumbs = json.load(f)
            
            breadcrumbs.append(breadcrumb)
            breadcrumbs = breadcrumbs[-500:]  # Keep last 500
            
            with open(breadcrumb_file, 'w', encoding='utf-8') as f:
                json.dump(breadcrumbs, f, indent=2)
                
        except Exception as e:
            logging.error(f"Failed to log breadcrumb: {e}")
    
    def get_error_stats(self):
        """Get error statistics"""
        try:
            if not self.error_log_file.exists():
                return {'total': 0, 'by_type': {}}
            
            with open(self.error_log_file, 'r', encoding='utf-8') as f:
                errors = json.load(f)
            
            # Count by type
            by_type = {}
            for error in errors:
                error_type = error.get('type', 'Unknown')
                by_type[error_type] = by_type.get(error_type, 0) + 1
            
            return {
                'total': len(errors),
                'by_type': by_type,
                'recent': errors[-10:]  # Last 10 errors
            }
            
        except Exception as e:
            logging.error(f"Failed to get error stats: {e}")
            return {'total': 0, 'by_type': {}}


# Global error reporter instance
_error_reporter = None


def init_error_reporter(dsn=None, environment="production"):
    """Initialize global error reporter"""
    global _error_reporter
    _error_reporter = ErrorReporter(dsn=dsn, environment=environment)
    return _error_reporter


def get_error_reporter():
    """Get global error reporter instance"""
    global _error_reporter
    if _error_reporter is None:
        _error_reporter = ErrorReporter()
    return _error_reporter


def capture_exception(exception, context=None):
    """Shorthand for capturing exception"""
    return get_error_reporter().capture_exception(exception, context)


def capture_message(message, level="info", context=None):
    """Shorthand for capturing message"""
    return get_error_reporter().capture_message(message, level, context)


def add_breadcrumb(message, category="default", level="info", data=None):
    """Shorthand for adding breadcrumb"""
    return get_error_reporter().add_breadcrumb(message, category, level, data)


if __name__ == '__main__':
    # Test error reporter
    reporter = ErrorReporter()
    
    # Test capturing exception
    try:
        raise ValueError("Test error")
    except Exception as e:
        reporter.capture_exception(e, context={'test': True})
    
    # Test breadcrumbs
    reporter.add_breadcrumb("User opened app", category="navigation")
    reporter.add_breadcrumb("User sent query", category="query", data={'text': 'test'})
    
    # Get stats
    stats = reporter.get_error_stats()
    print(f"Error stats: {stats}")
