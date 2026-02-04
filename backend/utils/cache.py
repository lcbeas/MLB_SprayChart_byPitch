"""
Caching utilities for data fetching
"""

import os
import json
import pickle
import hashlib
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable, Optional

import pandas as pd

from config import Config


def get_cache_path(key: str, extension: str = 'pkl') -> str:
    """Generate a file path for a cache key."""
    os.makedirs(Config.CACHE_DIR, exist_ok=True)
    return os.path.join(Config.CACHE_DIR, f"{key}.{extension}")


def generate_cache_key(*args, **kwargs) -> str:
    """Generate a unique cache key from function arguments."""
    key_data = json.dumps({'args': args, 'kwargs': kwargs}, sort_keys=True, default=str)
    return hashlib.md5(key_data.encode()).hexdigest()


def cached_data(hours: int = 24):
    """
    Decorator to cache function results to disk.

    Args:
        hours: Number of hours before cache expires

    Returns:
        Decorated function with caching
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Generate cache key from function name and arguments
            cache_key = f"{func.__module__}_{func.__name__}_{generate_cache_key(*args[1:], **kwargs)}"
            cache_path = get_cache_path(cache_key)

            # Check if cached data exists and is valid
            if os.path.exists(cache_path):
                modified_time = datetime.fromtimestamp(os.path.getmtime(cache_path))
                if datetime.now() - modified_time < timedelta(hours=hours):
                    try:
                        with open(cache_path, 'rb') as f:
                            return pickle.load(f)
                    except Exception as e:
                        print(f"Cache read error: {e}")

            # Fetch fresh data
            result = func(*args, **kwargs)

            # Save to cache
            try:
                with open(cache_path, 'wb') as f:
                    pickle.dump(result, f)
            except Exception as e:
                print(f"Cache write error: {e}")

            return result
        return wrapper
    return decorator


def clear_cache(pattern: Optional[str] = None) -> int:
    """
    Clear cached data files.

    Args:
        pattern: Optional pattern to match (clears all if None)

    Returns:
        Number of files deleted
    """
    deleted = 0
    if os.path.exists(Config.CACHE_DIR):
        for filename in os.listdir(Config.CACHE_DIR):
            if pattern is None or pattern in filename:
                try:
                    os.remove(os.path.join(Config.CACHE_DIR, filename))
                    deleted += 1
                except Exception as e:
                    print(f"Error deleting {filename}: {e}")
    return deleted
