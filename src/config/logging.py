"""
Structured logging configuration for OpenMetaMind.

Uses python-json-logger for JSON-formatted log output.
"""

import logging
import sys
from typing import Any, Dict

from pythonjsonlogger import jsonlogger

from .settings import get_settings


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """
    Custom JSON formatter with additional fields.
    
    Includes timestamp, level, logger name, message, and extra fields.
    """
    
    def add_fields(
        self,
        log_record: Dict[str, Any],
        record: logging.LogRecord,
        message_dict: Dict[str, Any]
    ) -> None:
        """Add custom fields to the log record."""
        super().add_fields(log_record, record, message_dict)
        
        # Add timestamp in ISO format
        log_record['timestamp'] = self.formatTime(record, self.datefmt)
        
        # Add level
        log_record['level'] = record.levelname
        
        # Add logger name
        log_record['logger'] = record.name
        
        # Add module and function info
        log_record['module'] = record.module
        log_record['function'] = record.funcName
        log_record['line'] = record.lineno
        
        # Add process and thread info
        log_record['process_id'] = record.process
        log_record['thread_id'] = record.thread
        
        # Remove the redundant fields that pythonjsonlogger adds
        for field in ['levelname', 'name', 'module', 'funcName', 'lineno', 'process', 'thread']:
            if field in log_record:
                del log_record[field]


def setup_logging() -> None:
    """
    Set up structured JSON logging for the application.
    
    Reads log level from settings and configures the root logger.
    """
    settings = get_settings()
    
    # Create JSON formatter
    formatter = CustomJsonFormatter(
        fmt='%(timestamp)s %(level)s %(name)s %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S%z'
    )
    
    # Configure root logger
    root_logger = logging.getLogger()
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add stdout handler with JSON formatting
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    root_logger.addHandler(stdout_handler)
    
    # Set log level from settings
    root_logger.setLevel(getattr(logging, settings.log_level, logging.INFO))
    
    # Reduce noise from third-party libraries
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('slack').setLevel(logging.WARNING)
    logging.getLogger('langchain').setLevel(logging.WARNING)
    logging.getLogger('langgraph').setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the given name.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


class LogContext:
    """
    Context manager for adding extra context to log messages.
    
    Usage:
        with LogContext(request_id="123", user_id="456"):
            logger.info("Processing request")  # Logs with extra fields
    """
    
    def __init__(self, **context: Any):
        """Initialize with key-value pairs to add to log context."""
        self.context = context
        self._old_factory = None
    
    def __enter__(self) -> 'LogContext':
        """Enter context and add extra fields to log records."""
        self._old_factory = logging.getLogRecordFactory()
        
        record_dict = self.context
        
        def record_factory(*args, **kwargs):
            record = self._old_factory(*args, **kwargs)
            for key, value in record_dict.items():
                setattr(record, key, value)
            return record
        
        logging.setLogRecordFactory(record_factory)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context and restore original record factory."""
        if self._old_factory:
            logging.setLogRecordFactory(self._old_factory)