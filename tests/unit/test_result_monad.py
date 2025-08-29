#!/usr/bin/env python3

"""
Result Monad Unit Tests

Focused unit tests for the core functional Result monad implementation.
"""

import pytest
import asyncio
from typing import List

from server.functional.result_monad import (
    Result, Success, Failure, 
    success, failure, from_optional, from_callable, from_async_callable,
    sequence, traverse, combine, combine3,
    result_wrapper, async_result_wrapper, log_result
)

@pytest.mark.unit
class TestResultMonad:
    """Unit tests for Result monad core functionality"""
    
    def test_success_creation_and_access(self):
        """Test Success creation and value access"""
        value = "test value"
        result = Success(value)
        
        assert result.is_success()
        assert not result.is_failure()
        assert result.get_value() == value
        assert result.get_error() is None
        assert result.get_or_else("default") == value
    
    def test_failure_creation_and_access(self):
        """Test Failure creation and error access"""
        error = "test error"
        result = Failure(error)
        
        assert result.is_failure()
        assert not result.is_success()
        assert result.get_value() is None
        assert result.get_error() == error
        assert result.get_or_else("default") == "default"
    
    def test_success_map_operation(self):
        """Test Success functor map operation"""
        result = Success(10)
        mapped = result.map(lambda x: x * 2)
        
        assert mapped.is_success()
        assert mapped.get_value() == 20
    
    def test_success_map_with_exception(self):
        """Test Success map handles exceptions"""
        result = Success("test")
        mapped = result.map(lambda x: 1 / 0)  # Division by zero
        
        assert mapped.is_failure()
        assert "division by zero" in str(mapped.get_error()).lower()
    
    def test_failure_map_operation(self):
        """Test Failure map preserves failure"""
        result = Failure("original error")
        mapped = result.map(lambda x: x * 2)
        
        assert mapped.is_failure()
        assert mapped.get_error() == "original error"
    
    def test_success_flat_map_operation(self):
        """Test Success monadic flat_map operation"""
        result = Success(5)
        flat_mapped = result.flat_map(lambda x: Success(x * 3))
        
        assert flat_mapped.is_success()
        assert flat_mapped.get_value() == 15
    
    def test_success_flat_map_to_failure(self):
        """Test Success flat_map can return Failure"""
        result = Success(5)
        flat_mapped = result.flat_map(lambda x: Failure("operation failed"))
        
        assert flat_mapped.is_failure()
        assert flat_mapped.get_error() == "operation failed"
    
    def test_success_flat_map_with_exception(self):
        """Test Success flat_map handles exceptions"""
        result = Success(5)
        flat_mapped = result.flat_map(lambda x: 1 / 0)  # Exception
        
        assert flat_mapped.is_failure()
        assert "division by zero" in str(flat_mapped.get_error()).lower()
    
    def test_failure_flat_map_operation(self):
        """Test Failure flat_map preserves failure"""
        result = Failure("original error")
        flat_mapped = result.flat_map(lambda x: Success(x * 2))
        
        assert flat_mapped.is_failure()
        assert flat_mapped.get_error() == "original error"
    
    def test_map_error_operation(self):
        """Test map_error transforms error"""
        result = Failure("original error")
        mapped = result.map_error(lambda e: f"transformed: {e}")
        
        assert mapped.is_failure()
        assert mapped.get_error() == "transformed: original error"
    
    def test_success_map_error_unchanged(self):
        """Test Success map_error leaves success unchanged"""
        result = Success("value")
        mapped = result.map_error(lambda e: f"transformed: {e}")
        
        assert mapped.is_success()
        assert mapped.get_value() == "value"
    
    def test_or_else_operation(self):
        """Test or_else operation"""
        success_result = Success("original")
        failure_result = Failure("error")
        alternative = Success("alternative")
        
        assert success_result.or_else(alternative) == success_result
        assert failure_result.or_else(alternative) == alternative
    
    def test_fold_operation(self):
        """Test fold operation"""
        success_result = Success(10)
        failure_result = Failure("error")
        
        success_folded = success_result.fold(
            on_success=lambda x: f"success: {x}",
            on_failure=lambda e: f"failure: {e}"
        )
        
        failure_folded = failure_result.fold(
            on_success=lambda x: f"success: {x}", 
            on_failure=lambda e: f"failure: {e}"
        )
        
        assert success_folded == "success: 10"
        assert failure_folded == "failure: error"
    
    def test_filter_operation(self):
        """Test filter operation"""
        success_result = Success(10)
        
        # Filter passes
        filtered_pass = success_result.filter(lambda x: x > 5, "too small")
        assert filtered_pass.is_success()
        assert filtered_pass.get_value() == 10
        
        # Filter fails
        filtered_fail = success_result.filter(lambda x: x > 20, "too small")
        assert filtered_fail.is_failure()
        assert filtered_fail.get_error() == "too small"
        
        # Filter on failure
        failure_result = Failure("original error")
        filtered_failure = failure_result.filter(lambda x: True, "new error")
        assert filtered_failure.is_failure()
        assert filtered_failure.get_error() == "original error"
    
    def test_foreach_operation(self):
        """Test foreach side effect operation"""
        side_effects = []
        
        success_result = Success("value")
        failure_result = Failure("error")
        
        # Success should execute side effect
        result1 = success_result.foreach(lambda x: side_effects.append(x))
        assert result1 == success_result  # Returns unchanged
        assert side_effects == ["value"]
        
        # Failure should not execute side effect
        result2 = failure_result.foreach(lambda x: side_effects.append(x))
        assert result2 == failure_result
        assert side_effects == ["value"]  # Unchanged
    
    def test_recover_operation(self):
        """Test recover operation"""
        success_result = Success("original")
        failure_result = Failure("error")
        
        # Success should return original value
        recovered_success = success_result.recover(lambda e: "recovered")
        assert recovered_success == "original"
        
        # Failure should return recovered value
        recovered_failure = failure_result.recover(lambda e: f"recovered from: {e}")
        assert recovered_failure == "recovered from: error"
    
    def test_recover_with_operation(self):
        """Test recover_with operation"""
        success_result = Success("original")
        failure_result = Failure("error")
        
        # Success should return original Result
        recovered_success = success_result.recover_with(lambda e: Success("recovered"))
        assert recovered_success == success_result
        
        # Failure should return recovery Result
        recovered_failure = failure_result.recover_with(lambda e: Success(f"recovered from: {e}"))
        assert recovered_failure.is_success()
        assert recovered_failure.get_value() == "recovered from: error"
        
        # Recovery can also return Failure
        recovered_to_failure = failure_result.recover_with(lambda e: Failure(f"recovery failed: {e}"))
        assert recovered_to_failure.is_failure()
        assert recovered_to_failure.get_error() == "recovery failed: error"

@pytest.mark.unit
class TestResultFactoryFunctions:
    """Unit tests for Result factory functions"""
    
    def test_success_factory(self):
        """Test success factory function"""
        result = success("test value")
        assert result.is_success()
        assert result.get_value() == "test value"
    
    def test_failure_factory(self):
        """Test failure factory function"""
        result = failure("test error")
        assert result.is_failure()
        assert result.get_error() == "test error"
    
    def test_from_optional_with_value(self):
        """Test from_optional with non-None value"""
        result = from_optional("value", "error if None")
        assert result.is_success()
        assert result.get_value() == "value"
    
    def test_from_optional_with_none(self):
        """Test from_optional with None value"""
        result = from_optional(None, "value was None")
        assert result.is_failure()
        assert result.get_error() == "value was None"
    
    def test_from_callable_success(self):
        """Test from_callable with successful function"""
        result = from_callable(lambda: "success")
        assert result.is_success()
        assert result.get_value() == "success"
    
    def test_from_callable_exception(self):
        """Test from_callable with exception"""
        result = from_callable(lambda: 1 / 0)
        assert result.is_failure()
        assert "division by zero" in str(result.get_error()).lower()
    
    def test_from_callable_with_error_mapper(self):
        """Test from_callable with custom error mapper"""
        def error_mapper(e: Exception) -> str:
            return f"Custom error: {type(e).__name__}"
        
        result = from_callable(lambda: 1 / 0, error_mapper)
        assert result.is_failure()
        assert result.get_error() == "Custom error: ZeroDivisionError"
    
    @pytest.mark.asyncio
    async def test_from_async_callable_success(self):
        """Test from_async_callable with successful async function"""
        async def async_func():
            await asyncio.sleep(0.01)
            return "async success"
        
        result = await from_async_callable(async_func)
        assert result.is_success()
        assert result.get_value() == "async success"
    
    @pytest.mark.asyncio
    async def test_from_async_callable_exception(self):
        """Test from_async_callable with exception"""
        async def async_func():
            await asyncio.sleep(0.01)
            raise ValueError("async error")
        
        result = await from_async_callable(async_func)
        assert result.is_failure()
        assert "async error" in str(result.get_error())

@pytest.mark.unit
class TestResultUtilityFunctions:
    """Unit tests for Result utility functions"""
    
    def test_sequence_all_success(self):
        """Test sequence with all successful Results"""
        results = [Success(1), Success(2), Success(3)]
        sequenced = sequence(results)
        
        assert sequenced.is_success()
        assert sequenced.get_value() == [1, 2, 3]
    
    def test_sequence_with_failure(self):
        """Test sequence with one failure (short-circuits)"""
        results = [Success(1), Failure("error"), Success(3)]
        sequenced = sequence(results)
        
        assert sequenced.is_failure()
        assert sequenced.get_error() == "error"
    
    def test_sequence_empty_list(self):
        """Test sequence with empty list"""
        sequenced = sequence([])
        assert sequenced.is_success()
        assert sequenced.get_value() == []
    
    def test_traverse_all_success(self):
        """Test traverse with function that returns all successes"""
        items = [1, 2, 3]
        traversed = traverse(items, lambda x: Success(x * 2))
        
        assert traversed.is_success()
        assert traversed.get_value() == [2, 4, 6]
    
    def test_traverse_with_failure(self):
        """Test traverse with function that can fail"""
        items = [1, 2, 0, 3]  # 0 will cause division by zero
        traversed = traverse(items, lambda x: Success(10 // x) if x != 0 else Failure("division by zero"))
        
        assert traversed.is_failure()
        assert traversed.get_error() == "division by zero"
    
    def test_combine_both_success(self):
        """Test combine with two successful Results"""
        result1 = Success("a")
        result2 = Success("b")
        combined = combine(result1, result2)
        
        assert combined.is_success()
        assert combined.get_value() == ("a", "b")
    
    def test_combine_first_failure(self):
        """Test combine with first Result failing"""
        result1 = Failure("first error")
        result2 = Success("b")
        combined = combine(result1, result2)
        
        assert combined.is_failure()
        assert combined.get_error() == "first error"
    
    def test_combine_second_failure(self):
        """Test combine with second Result failing"""
        result1 = Success("a")
        result2 = Failure("second error")
        combined = combine(result1, result2)
        
        assert combined.is_failure()
        assert combined.get_error() == "second error"
    
    def test_combine3_all_success(self):
        """Test combine3 with three successful Results"""
        result1 = Success("a")
        result2 = Success("b")  
        result3 = Success("c")
        combined = combine3(result1, result2, result3)
        
        assert combined.is_success()
        assert combined.get_value() == ("a", "b", "c")
    
    def test_combine3_with_failure(self):
        """Test combine3 with one failure"""
        result1 = Success("a")
        result2 = Failure("error")
        result3 = Success("c")
        combined = combine3(result1, result2, result3)
        
        assert combined.is_failure()
        assert combined.get_error() == "error"

@pytest.mark.unit
class TestResultDecorators:
    """Unit tests for Result decorators"""
    
    def test_result_wrapper_success(self):
        """Test result_wrapper with successful function"""
        @result_wrapper()
        def divide(a: int, b: int) -> float:
            return a / b
        
        result = divide(10, 2)
        assert result.is_success()
        assert result.get_value() == 5.0
    
    def test_result_wrapper_exception(self):
        """Test result_wrapper with exception"""
        @result_wrapper()
        def divide(a: int, b: int) -> float:
            return a / b
        
        result = divide(10, 0)
        assert result.is_failure()
        assert "division by zero" in str(result.get_error()).lower()
    
    def test_result_wrapper_with_error_mapper(self):
        """Test result_wrapper with custom error mapper"""
        def error_mapper(e: Exception) -> str:
            return f"Math error: {str(e)}"
        
        @result_wrapper(error_mapper)
        def divide(a: int, b: int) -> float:
            return a / b
        
        result = divide(10, 0)
        assert result.is_failure()
        assert result.get_error().startswith("Math error:")
    
    @pytest.mark.asyncio
    async def test_async_result_wrapper_success(self):
        """Test async_result_wrapper with successful async function"""
        @async_result_wrapper()
        async def async_divide(a: int, b: int) -> float:
            await asyncio.sleep(0.01)
            return a / b
        
        result = await async_divide(10, 2)
        assert result.is_success()
        assert result.get_value() == 5.0
    
    @pytest.mark.asyncio
    async def test_async_result_wrapper_exception(self):
        """Test async_result_wrapper with exception"""
        @async_result_wrapper()
        async def async_divide(a: int, b: int) -> float:
            await asyncio.sleep(0.01)
            return a / b
        
        result = await async_divide(10, 0)
        assert result.is_failure()
        assert "division by zero" in str(result.get_error()).lower()

@pytest.mark.unit
class TestResultMonadLaws:
    """Unit tests to verify monad laws for Result"""
    
    def test_left_identity_law(self):
        """Test monad left identity law: M(a).flat_map(f) == f(a)"""
        value = 42
        f = lambda x: Success(x * 2)
        
        left_side = Success(value).flat_map(f)
        right_side = f(value)
        
        assert left_side.get_value() == right_side.get_value()
    
    def test_right_identity_law(self):
        """Test monad right identity law: m.flat_map(M) == m"""
        original = Success(42)
        result = original.flat_map(lambda x: Success(x))
        
        assert result.get_value() == original.get_value()
    
    def test_associativity_law(self):
        """Test monad associativity law: m.flat_map(f).flat_map(g) == m.flat_map(x => f(x).flat_map(g))"""
        m = Success(10)
        f = lambda x: Success(x * 2)
        g = lambda x: Success(x + 1)
        
        # Left side: m.flat_map(f).flat_map(g)
        left_side = m.flat_map(f).flat_map(g)
        
        # Right side: m.flat_map(x => f(x).flat_map(g))
        right_side = m.flat_map(lambda x: f(x).flat_map(g))
        
        assert left_side.get_value() == right_side.get_value()
    
    def test_functor_identity_law(self):
        """Test functor identity law: m.map(id) == m"""
        original = Success(42)
        identity = lambda x: x
        mapped = original.map(identity)
        
        assert mapped.get_value() == original.get_value()
    
    def test_functor_composition_law(self):
        """Test functor composition law: m.map(f).map(g) == m.map(x => g(f(x)))"""
        m = Success(10)
        f = lambda x: x * 2
        g = lambda x: x + 1
        
        # Left side: m.map(f).map(g)
        left_side = m.map(f).map(g)
        
        # Right side: m.map(x => g(f(x)))
        right_side = m.map(lambda x: g(f(x)))
        
        assert left_side.get_value() == right_side.get_value()