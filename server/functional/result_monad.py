#!/usr/bin/env python3

"""
Result Monad Implementation

A functional programming abstraction for handling computations that may fail.
Provides composable error handling following category theory principles.
"""

from typing import TypeVar, Generic, Union, Callable, Optional, Any, Awaitable
from abc import ABC, abstractmethod
from dataclasses import dataclass
import logging
import traceback

logger = logging.getLogger(__name__)

T = TypeVar('T')
U = TypeVar('U') 
E = TypeVar('E')
F = TypeVar('F')

class Result(Generic[T, E], ABC):
    """Abstract base class for Result monad."""
    
    @abstractmethod
    def map(self, func: Callable[[T], U]) -> 'Result[U, E]':
        """Functor map: applies function to success value, preserves failure."""
        pass
    
    @abstractmethod
    def flat_map(self, func: Callable[[T], 'Result[U, E]']) -> 'Result[U, E]':
        """Monadic bind: composes Result-returning functions."""
        pass
    
    @abstractmethod
    def map_error(self, func: Callable[[E], F]) -> 'Result[T, F]':
        """Maps over the error type."""
        pass
    
    @abstractmethod
    def is_success(self) -> bool:
        """Returns True if this is a Success."""
        pass
    
    @abstractmethod
    def is_failure(self) -> bool:
        """Returns True if this is a Failure."""
        pass
    
    @abstractmethod
    def get_value(self) -> Optional[T]:
        """Returns the success value if present, None otherwise."""
        pass
    
    @abstractmethod
    def get_error(self) -> Optional[E]:
        """Returns the error if present, None otherwise."""
        pass
    
    def get_or_else(self, default: T) -> T:
        """Returns the success value or the provided default."""
        return self.get_value() if self.is_success() else default
    
    def or_else(self, alternative: 'Result[T, E]') -> 'Result[T, E]':
        """Returns this Result if success, otherwise returns alternative."""
        return self if self.is_success() else alternative
    
    def fold(self, on_success: Callable[[T], U], on_failure: Callable[[E], U]) -> U:
        """Applies one of two functions based on success/failure."""
        if self.is_success():
            return on_success(self.get_value())
        else:
            return on_failure(self.get_error())
    
    def filter(self, predicate: Callable[[T], bool], error: E) -> 'Result[T, E]':
        """Returns this Result if success and predicate passes, otherwise Failure."""
        if self.is_success() and predicate(self.get_value()):
            return self
        elif self.is_success():
            return Failure(error)
        else:
            return self
    
    def foreach(self, action: Callable[[T], Any]) -> 'Result[T, E]':
        """Performs side effect on success value, returns unchanged Result."""
        if self.is_success():
            action(self.get_value())
        return self
    
    def recover(self, recovery_func: Callable[[E], T]) -> T:
        """Recovers from failure by applying recovery function."""
        if self.is_failure():
            return recovery_func(self.get_error())
        return self.get_value()
    
    def recover_with(self, recovery_func: Callable[[E], 'Result[T, E]']) -> 'Result[T, E]':
        """Recovers from failure with another Result."""
        if self.is_failure():
            return recovery_func(self.get_error())
        return self

@dataclass(frozen=True)
class Success(Result[T, E]):
    """Represents a successful computation result."""
    value: T
    
    def map(self, func: Callable[[T], U]) -> Result[U, E]:
        try:
            return Success(func(self.value))
        except Exception as e:
            logger.debug(f"Exception in Success.map: {e}")
            return Failure(e)
    
    def flat_map(self, func: Callable[[T], Result[U, E]]) -> Result[U, E]:
        try:
            return func(self.value)
        except Exception as e:
            logger.debug(f"Exception in Success.flat_map: {e}")
            return Failure(e)
    
    def map_error(self, func: Callable[[E], F]) -> Result[T, F]:
        return Success(self.value)
    
    def is_success(self) -> bool:
        return True
    
    def is_failure(self) -> bool:
        return False
    
    def get_value(self) -> Optional[T]:
        return self.value
    
    def get_error(self) -> Optional[E]:
        return None
    
    def __str__(self) -> str:
        return f"Success({self.value})"
    
    def __repr__(self) -> str:
        return f"Success({repr(self.value)})"

@dataclass(frozen=True)
class Failure(Result[T, E]):
    """Represents a failed computation result."""
    error: E
    
    def map(self, func: Callable[[T], U]) -> Result[U, E]:
        return Failure(self.error)
    
    def flat_map(self, func: Callable[[T], Result[U, E]]) -> Result[U, E]:
        return Failure(self.error)
    
    def map_error(self, func: Callable[[E], F]) -> Result[T, F]:
        try:
            return Failure(func(self.error))
        except Exception as e:
            logger.debug(f"Exception in Failure.map_error: {e}")
            return Failure(e)
    
    def is_success(self) -> bool:
        return False
    
    def is_failure(self) -> bool:
        return True
    
    def get_value(self) -> Optional[T]:
        return None
    
    def get_error(self) -> Optional[E]:
        return self.error
    
    def __str__(self) -> str:
        return f"Failure({self.error})"
    
    def __repr__(self) -> str:
        return f"Failure({repr(self.error)})"

# Async Result for handling async computations
class AsyncResult(Generic[T, E]):
    """Async version of Result monad for handling async computations."""
    
    def __init__(self, result_future: Awaitable[Result[T, E]]):
        self._future = result_future
    
    async def map(self, func: Callable[[T], U]) -> 'AsyncResult[U, E]':
        result = await self._future
        return AsyncResult(self._wrap_result(result.map(func)))
    
    async def flat_map(self, func: Callable[[T], 'AsyncResult[U, E]']) -> 'AsyncResult[U, E]':
        result = await self._future
        if result.is_success():
            return await func(result.get_value())
        else:
            return AsyncResult(self._wrap_result(Failure(result.get_error())))
    
    async def map_error(self, func: Callable[[E], F]) -> 'AsyncResult[T, F]':
        result = await self._future
        return AsyncResult(self._wrap_result(result.map_error(func)))
    
    async def get(self) -> Result[T, E]:
        """Awaits and returns the underlying Result."""
        return await self._future
    
    async def get_value(self) -> Optional[T]:
        result = await self._future
        return result.get_value()
    
    async def get_error(self) -> Optional[E]:
        result = await self._future
        return result.get_error()
    
    async def is_success(self) -> bool:
        result = await self._future
        return result.is_success()
    
    async def is_failure(self) -> bool:
        result = await self._future
        return result.is_failure()
    
    async def foreach(self, action: Callable[[T], Any]) -> 'AsyncResult[T, E]':
        result = await self._future
        result.foreach(action)
        return self
    
    @staticmethod
    async def _wrap_result(result: Result[T, E]) -> Result[T, E]:
        return result

# Factory functions for creating Results
def success(value: T) -> Result[T, Any]:
    """Creates a Success Result."""
    return Success(value)

def failure(error: E) -> Result[Any, E]:
    """Creates a Failure Result."""
    return Failure(error)

def from_optional(value: Optional[T], error: E) -> Result[T, E]:
    """Creates Result from Optional value."""
    if value is not None:
        return Success(value)
    else:
        return Failure(error)

def from_callable(func: Callable[[], T], error_mapper: Callable[[Exception], E] = None) -> Result[T, E]:
    """Creates Result from callable that might raise exception."""
    try:
        return Success(func())
    except Exception as e:
        if error_mapper:
            return Failure(error_mapper(e))
        else:
            return Failure(e)

async def from_async_callable(
    func: Callable[[], Awaitable[T]], 
    error_mapper: Callable[[Exception], E] = None
) -> Result[T, E]:
    """Creates Result from async callable that might raise exception."""
    try:
        value = await func()
        return Success(value)
    except Exception as e:
        if error_mapper:
            return Failure(error_mapper(e))
        else:
            return Failure(e)

# Utility functions for working with Results
def sequence(results: list[Result[T, E]]) -> Result[list[T], E]:
    """Converts list of Results to Result of list. Fails if any Result fails."""
    values = []
    for result in results:
        if result.is_success():
            values.append(result.get_value())
        else:
            return Failure(result.get_error())
    return Success(values)

def traverse(items: list[T], func: Callable[[T], Result[U, E]]) -> Result[list[U], E]:
    """Maps function over list and sequences the results."""
    results = [func(item) for item in items]
    return sequence(results)

def combine(result1: Result[T, E], result2: Result[U, E]) -> Result[tuple[T, U], E]:
    """Combines two Results into a Result of tuple."""
    if result1.is_success() and result2.is_success():
        return Success((result1.get_value(), result2.get_value()))
    elif result1.is_failure():
        return Failure(result1.get_error())
    else:
        return Failure(result2.get_error())

def combine3(
    result1: Result[T, E], 
    result2: Result[U, E], 
    result3: Result[Any, E]
) -> Result[tuple[T, U, Any], E]:
    """Combines three Results into a Result of tuple."""
    combined = combine(result1, result2)
    if combined.is_success() and result3.is_success():
        t, u = combined.get_value()
        return Success((t, u, result3.get_value()))
    elif combined.is_failure():
        return Failure(combined.get_error())
    else:
        return Failure(result3.get_error())

# Decorator for automatically wrapping functions in Result
def result_wrapper(error_mapper: Callable[[Exception], E] = None):
    """Decorator that wraps function results in Result monad."""
    def decorator(func: Callable[..., T]) -> Callable[..., Result[T, E]]:
        def wrapper(*args, **kwargs) -> Result[T, E]:
            try:
                result = func(*args, **kwargs)
                return Success(result)
            except Exception as e:
                if error_mapper:
                    return Failure(error_mapper(e))
                else:
                    return Failure(e)
        return wrapper
    return decorator

def async_result_wrapper(error_mapper: Callable[[Exception], E] = None):
    """Decorator that wraps async function results in Result monad."""
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[Result[T, E]]]:
        async def wrapper(*args, **kwargs) -> Result[T, E]:
            try:
                result = await func(*args, **kwargs)
                return Success(result)
            except Exception as e:
                if error_mapper:
                    return Failure(error_mapper(e))
                else:
                    return Failure(e)
        return wrapper
    return decorator

# Helper for logging Results
def log_result(result: Result[T, E], success_msg: str = "Operation succeeded", 
               error_msg: str = "Operation failed") -> Result[T, E]:
    """Logs the Result and returns it unchanged."""
    if result.is_success():
        logger.info(f"{success_msg}: {result.get_value()}")
    else:
        logger.error(f"{error_msg}: {result.get_error()}")
    return result