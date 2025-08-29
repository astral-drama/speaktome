#!/usr/bin/env python3

"""
Test Functional Utilities

Unit tests for shared functional programming utilities including Result monads.
Focuses on mathematical laws and functional composition patterns.
"""

import asyncio
import pytest
from typing import List

from shared.functional import (
    Result, Success, Failure, 
    from_callable, from_async_callable, from_optional,
    compose, pipe, curry,
    merge_configs, validate_required_keys, validate_type
)


class TestResultMonad:
    """Test Result monad implementation and laws"""
    
    def test_result_creation(self):
        """Test basic Result creation"""
        success_result = Success(42)
        failure_result = Failure("error")
        
        assert success_result.is_success()
        assert not success_result.is_failure()
        assert success_result.value == 42
        
        assert failure_result.is_failure()
        assert not failure_result.is_success()
        assert failure_result.error == "error"
    
    def test_functor_laws(self):
        """Test functor laws: identity and composition"""
        # Identity law: fmap(id, x) = x
        result = Success(42)
        identity_mapped = result.map(lambda x: x)
        assert result == identity_mapped
        
        # Composition law: fmap(f . g, x) = fmap(f, fmap(g, x))
        f = lambda x: x * 2
        g = lambda x: x + 10
        
        # Direct composition
        composed = result.map(lambda x: f(g(x)))
        
        # Sequential mapping
        sequential = result.map(g).map(f)
        
        assert composed.value == sequential.value
    
    def test_monad_laws(self):
        """Test monad laws: left identity, right identity, associativity"""
        # Left identity: return(a) >>= f = f(a)
        value = 42
        f = lambda x: Success(x * 2)
        
        left_identity = Success(value).flat_map(f)
        direct_application = f(value)
        
        assert left_identity.value == direct_application.value
        
        # Right identity: m >>= return = m
        result = Success(42)
        right_identity = result.flat_map(lambda x: Success(x))
        
        assert result.value == right_identity.value
        
        # Associativity: (m >>= f) >>= g = m >>= (\x -> f(x) >>= g)
        g = lambda x: Success(x + 10)
        
        left_assoc = result.flat_map(f).flat_map(g)
        right_assoc = result.flat_map(lambda x: f(x).flat_map(g))
        
        assert left_assoc.value == right_assoc.value
    
    def test_map_preserves_failure(self):
        """Test that map preserves failures"""
        failure_result = Failure("error")
        mapped = failure_result.map(lambda x: x * 2)
        
        assert mapped.is_failure()
        assert mapped.error == "error"
    
    def test_flat_map_short_circuits(self):
        """Test that flat_map short-circuits on failure"""
        failure_result = Failure("error")
        mapped = failure_result.flat_map(lambda x: Success(x * 2))
        
        assert mapped.is_failure()
        assert mapped.error == "error"
    
    def test_map_error(self):
        """Test error transformation"""
        failure_result = Failure("original error")
        transformed = failure_result.map_error(lambda e: f"transformed: {e}")
        
        assert transformed.is_failure()
        assert transformed.error == "transformed: original error"
        
        # Should not affect success
        success_result = Success(42)
        unchanged = success_result.map_error(lambda e: "should not apply")
        
        assert unchanged.is_success()
        assert unchanged.value == 42
    
    def test_get_or_else(self):
        """Test default value extraction"""
        success_result = Success(42)
        failure_result = Failure("error")
        
        assert success_result.get_or_else(0) == 42
        assert failure_result.get_or_else(0) == 0
    
    def test_get_or_raise(self):
        """Test exception-based extraction"""
        success_result = Success(42)
        failure_result = Failure(ValueError("test error"))
        
        assert success_result.get_or_raise() == 42
        
        with pytest.raises(ValueError):
            failure_result.get_or_raise()


class TestResultFactoryFunctions:
    """Test Result factory functions"""
    
    def test_from_callable_success(self):
        """Test successful callable wrapping"""
        def successful_func():
            return 42
        
        result = from_callable(successful_func)
        
        assert result.is_success()
        assert result.value == 42
    
    def test_from_callable_exception(self):
        """Test exception handling in callable wrapping"""
        def failing_func():
            raise ValueError("test error")
        
        result = from_callable(failing_func)
        
        assert result.is_failure()
        assert isinstance(result.error, ValueError)
    
    @pytest.mark.asyncio
    async def test_from_async_callable_success(self):
        """Test successful async callable wrapping"""
        async def successful_async_func():
            return 42
        
        result = await from_async_callable(successful_async_func)
        
        assert result.is_success()
        assert result.value == 42
    
    @pytest.mark.asyncio
    async def test_from_async_callable_exception(self):
        """Test exception handling in async callable wrapping"""
        async def failing_async_func():
            raise ValueError("test error")
        
        result = await from_async_callable(failing_async_func)
        
        assert result.is_failure()
        assert isinstance(result.error, ValueError)
    
    def test_from_optional(self):
        """Test Optional to Result conversion"""
        # Success case
        success_result = from_optional(42)
        assert success_result.is_success()
        assert success_result.value == 42
        
        # Failure case
        failure_result = from_optional(None)
        assert failure_result.is_failure()
        assert failure_result.error == "Value is None"
        
        # Custom error message
        custom_failure = from_optional(None, "Custom error")
        assert custom_failure.is_failure()
        assert custom_failure.error == "Custom error"


class TestFunctionalUtilities:
    """Test functional programming utilities"""
    
    def test_compose(self):
        """Test function composition"""
        f = lambda x: x * 2
        g = lambda x: x + 10
        h = lambda x: x - 5
        
        # Test composition order (right to left)
        composed = compose(f, g, h)
        result = composed(10)
        
        # Should be f(g(h(10))) = f(g(5)) = f(15) = 30
        assert result == 30
    
    def test_pipe(self):
        """Test pipeline operations"""
        f = lambda x: x * 2
        g = lambda x: x + 10
        h = lambda x: x - 5
        
        # Test pipeline order (left to right)
        result = pipe(10, h, g, f)
        
        # Should be f(g(h(10))) = f(g(5)) = f(15) = 30
        assert result == 30
    
    def test_curry(self):
        """Test function currying"""
        @curry
        def add_three(a, b, c):
            return a + b + c
        
        # Test partial application
        add_one_two = add_three(1)(2)
        result = add_one_two(3)
        
        assert result == 6
        
        # Test direct application
        direct_result = add_three(1, 2, 3)
        assert direct_result == 6


class TestConfigurationUtilities:
    """Test configuration utilities"""
    
    def test_merge_configs(self):
        """Test deep configuration merging"""
        default_config = {
            "server": {"url": "localhost", "port": 8000},
            "audio": {"sample_rate": 16000, "channels": 1},
            "simple": "default_value"
        }
        
        user_config = {
            "server": {"port": 9000, "timeout": 30},
            "audio": {"channels": 2},
            "simple": "user_value"
        }
        
        merged = merge_configs(default_config, user_config)
        
        assert merged["server"]["url"] == "localhost"  # From default
        assert merged["server"]["port"] == 9000  # From user
        assert merged["server"]["timeout"] == 30  # From user
        assert merged["audio"]["sample_rate"] == 16000  # From default
        assert merged["audio"]["channels"] == 2  # From user
        assert merged["simple"] == "user_value"  # From user
    
    def test_validate_required_keys(self):
        """Test configuration key validation"""
        config = {
            "server_url": "ws://localhost:8000",
            "model": "base",
            "hotkey": "ctrl+shift+w"
        }
        
        required_keys = ["server_url", "model"]
        
        # Should succeed
        result = validate_required_keys(config, required_keys)
        assert result.is_success()
        
        # Should fail with missing keys
        incomplete_config = {"server_url": "ws://localhost:8000"}
        result = validate_required_keys(incomplete_config, required_keys)
        assert result.is_failure()
        assert "model" in result.error
    
    def test_validate_type(self):
        """Test type validation"""
        # Should succeed
        result = validate_type(42, int, "test_field")
        assert result.is_success()
        assert result.value == 42
        
        # Should fail
        result = validate_type("42", int, "test_field")
        assert result.is_failure()
        assert "test_field" in result.error
        assert "int" in result.error