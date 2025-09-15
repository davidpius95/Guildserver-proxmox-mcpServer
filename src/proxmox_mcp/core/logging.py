"""
Logging configuration for the Proxmox MCP server.

This module handles logging setup and configuration:
- File and console logging handlers
- Log level management
- Format customization
- Handler lifecycle management

The logging system supports:
- Configurable log levels
- File-based logging with path resolution
- Console logging for errors
- Custom format strings
- Multiple handler management
"""
import logging
import os
import sys
import tempfile
from typing import Optional
from ..config.models import LoggingConfig

def setup_logging(config: LoggingConfig) -> logging.Logger:
    """Configure and initialize logging system.

    Sets up a comprehensive logging system with:
    - File logging (if configured):
      * Handles relative/absolute paths
      * Uses configured log level
      * Applies custom format
    
    - Console logging:
      * Always enabled for errors
      * Ensures critical issues are visible
    
    - Handler Management:
      * Removes existing handlers
      * Configures new handlers
      * Sets up formatters
    
    Args:
        config: Logging configuration containing:
               - Log level (e.g., "INFO", "DEBUG")
               - Format string
               - Optional log file path

    Returns:
        Configured logger instance for "proxmox-mcp"
        with appropriate handlers and formatting

    Example config:
        {
            "level": "INFO",
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "file": "/path/to/log/file.log"  # Optional
        }
    """
    # Determine log file via env override and make it writable when possible
    disable_file_log = os.getenv("PROXMOX_MCP_DISABLE_FILE_LOG", "").lower() in {"1", "true", "yes"}
    log_file = os.getenv("PROXMOX_MCP_LOG_FILE", config.file or "")
    if log_file:
        # If relative, resolve against a writable base directory
        if not os.path.isabs(log_file):
            base_dir = os.getcwd() or "/"
            # Avoid root or non-writable directories
            if base_dir == "/" or not os.access(base_dir, os.W_OK):
                home_dir = os.path.expanduser("~")
                if home_dir and os.access(home_dir, os.W_OK):
                    base_dir = home_dir
                else:
                    base_dir = tempfile.gettempdir()
            log_file = os.path.join(base_dir, log_file)
        
    # Create handlers
    handlers = []
    
    if log_file and not disable_file_log:
        try:
            file_handler = logging.FileHandler(log_file)
        except Exception:
            # Fallback to temp directory
            try:
                safe_path = os.path.join(tempfile.gettempdir(), os.path.basename(log_file))
                file_handler = logging.FileHandler(safe_path)
            except Exception as e:
                print(f"Warning: file logging disabled ({e})", file=sys.stderr)
                file_handler = None
        if file_handler:
            file_handler.setLevel(getattr(logging, config.level.upper()))
            handlers.append(file_handler)
    
    # Console handler for errors only to stderr (to not corrupt MCP stdout)
    console_handler = logging.StreamHandler(stream=os.sys.stderr)
    console_handler.setLevel(logging.ERROR)
    handlers.append(console_handler)
    
    # Configure formatters
    formatter = logging.Formatter(config.format)
    for handler in handlers:
        handler.setFormatter(formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.level.upper()))
    
    # Remove any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add new handlers
    for handler in handlers:
        root_logger.addHandler(handler)
    
    # Create and return server logger
    logger = logging.getLogger("proxmox-mcp")
    return logger
