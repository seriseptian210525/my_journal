"""
Logging configuration module for my_journal ETL pipeline.
Provides centralized logging setup with file and console handlers.
"""

import logging
import os
from datetime import datetime
from pathlib import Path

def setup_logger(name='my_journal', log_level=logging.INFO, log_to_file=True):
    """
    Sets up a logger with both file and console handlers.
    
    Args:
        name: Logger name
        log_level: Logging level (default: INFO)
        log_to_file: Whether to log to file (default: True)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Avoid duplicate handlers if logger already configured
    if logger.handlers:
        return logger
    
    logger.setLevel(log_level)
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s | %(name)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    console_formatter = logging.Formatter(
        '%(levelname)s | %(message)s'
    )
    
    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File Handler (if enabled)
    if log_to_file:
        # Create logs directory
        base_dir = Path(__file__).resolve().parent.parent.parent
        log_dir = base_dir / 'logs'
        log_dir.mkdir(exist_ok=True)
        
        # Generate log filename with date
        log_filename = f"pipeline_{datetime.now().strftime('%Y%m%d')}.log"
        log_path = log_dir / log_filename
        
        file_handler = logging.FileHandler(log_path, encoding='utf-8')
        file_handler.setLevel(log_level)
        file_handler.setFormatter(detailed_formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name='my_journal'):
    """
    Gets or creates a logger instance.
    
    Args:
        name: Logger name
        
    Returns:
        Logger instance
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger = setup_logger(name)
    return logger
