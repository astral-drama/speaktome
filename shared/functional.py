#!/usr/bin/env python3

"""
Shared Functional Programming Utilities

This module provides common functional programming patterns used across
both the SpeakToMe server and client components, ensuring consistent
error handling and data transformation patterns.
"""

from typing import TypeVar, Generic, Callable, Union, Any, Optional, Awaitable
from abc import ABC, abstractmethod
import asyncio
import logging
import functools

logger = logging.getLogger(__name__)

T = TypeVar('T')
U = TypeVar('U')
E = TypeVar('E')


class Result(Generic[T, E], ABC):
    """
    Result monad for functional error handling
    
    Provides a composable way to handle operations that may fail without
    using exceptions. Consistent with server-side Result implementation.
    """
    
    @abstractmethod
    def is_success(self) -> bool:
        """Check if this is a success result"""
        pass
    
    @abstractmethod
    def is_failure(self) -> bool:
        """Check if this is a failure result"""
        pass
    
    @abstractmethod
    def map(self, func: Callable[[T], U]) -> 'Result[U, E]':
        """Transform the success value if present"""
        pass
    
    @abstractmethod
    def flat_map(self, func: Callable[[T], 'Result[U, E]']) -> 'Result[U, E]':
        """Chain operations that return Results"""
        pass
    
    @abstractmethod
    def map_error(self, func: Callable[[E], U]) -> 'Result[T, U]':
        """Transform the error value if present"""
        pass
    
    @abstractmethod
    def get_or_else(self, default: T) -> T:
        """Get the success value or return default"""
        pass
    
    @abstractmethod
    def get_or_raise(self) -> T:
        """Get the success value or raise the error"""
        pass


class Success(Result[T, E]):
    """Successful result containing a value"""
    
    def __init__(self, value: T):
        self._value = value
    
    def is_success(self) -> bool:
        return True
    
    def is_failure(self) -> bool:
        return False
    
    def map(self, func: Callable[[T], U]) -> Result[U, E]:
        try:
            return Success(func(self._value))
        except Exception as e:
            return Failure(e)
    
    def flat_map(self, func: Callable[[T], Result[U, E]]) -> Result[U, E]:
        try:
            return func(self._value)
        except Exception as e:
            return Failure(e)
    
    def map_error(self, func: Callable[[E], U]) -> Result[T, U]:
        return Success(self._value)
    
    def get_or_else(self, default: T) -> T:
        return self._value
    
    def get_or_raise(self) -> T:
        return self._value
    
    @property
    def value(self) -> T:
        return self._value
    
    def __repr__(self) -> str:
        return f"Success({self._value})"
    
    def __eq__(self, other) -> bool:
        return isinstance(other, Success) and self._value == other._value


class Failure(Result[T, E]):
    """Failed result containing an error"""
    
    def __init__(self, error: E):
        self._error = error
    
    def is_success(self) -> bool:
        return False
    
    def is_failure(self) -> bool:
        return True
    
    def map(self, func: Callable[[T], U]) -> Result[U, E]:
        return Failure(self._error)
    
    def flat_map(self, func: Callable[[T], Result[U, E]]) -> Result[U, E]:
        return Failure(self._error)
    
    def map_error(self, func: Callable[[E], U]) -> Result[T, U]:
        try:
            return Failure(func(self._error))
        except Exception as e:
            return Failure(e)
    
    def get_or_else(self, default: T) -> T:
        return default
    
    def get_or_raise(self) -> T:
        if isinstance(self._error, Exception):
            raise self._error
        else:
            raise RuntimeError(f"Operation failed: {self._error}")
    
    @property
    def error(self) -> E:
        return self._error
    
    def __repr__(self) -> str:
        return f"Failure({self._error})"
    
    def __eq__(self, other) -> bool:
        return isinstance(other, Failure) and self._error == other._error


# Factory functions
def success(value: T) -> Result[T, Any]:
    """Create a Success result"""
    return Success(value)


def failure(error: E) -> Result[Any, E]:
    """Create a Failure result"""
    return Failure(error)


def from_callable(func: Callable[[], T]) -> Result[T, Exception]:
    """Execute a function and wrap result in Result"""
    try:
        return Success(func())
    except Exception as e:
        logger.debug(f"Function call failed: {e}")
        return Failure(e)


async def from_async_callable(func: Callable[[], Awaitable[T]]) -> Result[T, Exception]:
    """Execute an async function and wrap result in Result"""
    try:
        result = await func()
        return Success(result)
    except Exception as e:
        logger.debug(f"Async function call failed: {e}")
        return Failure(e)


def from_optional(value: Optional[T], error_msg: str = "Value is None") -> Result[T, str]:
    """Convert Optional to Result"""
    if value is None:
        return Failure(error_msg)
    else:
        return Success(value)


# Async Result utilities
class AsyncResult(Generic[T, E]):
    """Async wrapper for Result operations"""
    
    def __init__(self, result_future: Awaitable[Result[T, E]]):
        self._result_future = result_future
    
    async def map(self, func: Callable[[T], U]) -> 'AsyncResult[U, E]':
        """Map over async result"""
        result = await self._result_future
        return AsyncResult(asyncio.coroutine(lambda: result.map(func))())
    
    async def flat_map(self, func: Callable[[T], Awaitable[Result[U, E]]]) -> 'AsyncResult[U, E]':
        """Chain async operations"""
        result = await self._result_future
        if result.is_success():
            return AsyncResult(func(result.value))
        else:
            return AsyncResult(asyncio.coroutine(lambda: Failure(result.error))())
    
    async def get(self) -> Result[T, E]:
        """Get the final result"""
        return await self._result_future


# Functional utilities
def compose(*functions):
    """Compose functions right to left"""
    def _compose(f, g):
        return lambda x: f(g(x))
    
    return functools.reduce(_compose, functions, lambda x: x)


def pipe(value, *functions):
    """Pipe value through functions left to right"""
    result = value
    for func in functions:
        result = func(result)
    return result


def curry(func):
    """Curry a function for partial application"""
    @functools.wraps(func)
    def curried(*args, **kwargs):
        if len(args) + len(kwargs) >= func.__code__.co_argcount:
            return func(*args, **kwargs)
        return lambda *more_args, **more_kwargs: curried(*(args + more_args), **kwargs, **more_kwargs)
    return curried


# Logging utilities aligned with server patterns
def setup_logging(level: str = "INFO", format_string: Optional[str] = None) -> None:
    """
    Setup logging with server-consistent format
    
    Uses the same logging pattern as the server for consistency.
    """
    if format_string is None:
        format_string = '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
    
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=format_string,
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    logger.info(f"Logging configured at {level} level")


# Configuration utilities
def merge_configs(default: dict, user: dict) -> dict:
    """
    Merge configurations with deep update
    
    Consistent with server configuration merging patterns.
    """
    result = default.copy()
    
    for key, value in user.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
    
    return result


# Validation utilities
def validate_required_keys(config: dict, required_keys: list) -> Result[dict, str]:
    """Validate required configuration keys"""
    missing_keys = [key for key in required_keys if key not in config]
    
    if missing_keys:
        return failure(f"Missing required configuration keys: {missing_keys}")
    
    return success(config)


def validate_type(value: Any, expected_type: type, field_name: str) -> Result[Any, str]:
    """Validate value type"""
    if not isinstance(value, expected_type):
        return failure(f"Field '{field_name}' must be {expected_type.__name__}, got {type(value).__name__}")
    
    return success(value)