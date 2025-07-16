"""
Centralized logging configuration for the AI Cold Calling System
"""
import logging
import logging.handlers
import os
from datetime import datetime
from pathlib import Path

# Create logs directory if it doesn't exist
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

def setup_logger(name: str, level: str = "INFO") -> logging.Logger:
    """Setup logger with file and console handlers"""
    
    logger = logging.getLogger(name)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # Set level
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
    )
    
    simple_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)
    logger.addHandler(console_handler)
    
    # File handler for all logs
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "ai_cold_caller.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    logger.addHandler(file_handler)
    
    # Error file handler
    error_handler = logging.handlers.RotatingFileHandler(
        log_dir / "errors.log",
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed_formatter)
    logger.addHandler(error_handler)
    
    # Call-specific handler
    if 'call' in name.lower() or 'twilio' in name.lower():
        call_handler = logging.handlers.RotatingFileHandler(
            log_dir / "calls.log",
            maxBytes=20 * 1024 * 1024,  # 20MB
            backupCount=10
        )
        call_handler.setLevel(logging.INFO)
        call_handler.setFormatter(detailed_formatter)
        logger.addHandler(call_handler)
    
    return logger

def get_logger(name: str) -> logging.Logger:
    """Get or create a logger"""
    return setup_logger(name)

# Export
__all__ = ['setup_logger', 'get_logger']