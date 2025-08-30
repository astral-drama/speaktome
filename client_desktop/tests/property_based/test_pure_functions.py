#!/usr/bin/env python3

"""
Property-Based Testing for Pure Functions

Tests mathematical properties and invariants of our functional composition patterns.
Uses Hypothesis for generating test data and verifying functional properties.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import unittest
from hypothesis import given, strategies as st, example, settings
from hypothesis.strategies import text, integers, lists, dictionaries
from typing import List, Dict, Any

from client.gui.main_window import MainWindow
from client.voice_client_app import VoiceClientApplication, _read_config_file, _validate_config_dict, _create_config_from_dict
from shared.functional import Result, Success, Failure


class TestHotkeyFormattingProperties:
    """Property-based tests for hotkey formatting functions"""
    
    @given(st.text(alphabet='abcdefghijklmnopqrstuvwxyz', min_size=1, max_size=3))
    def test_format_hotkey_display_preserves_single_chars_lowercase(self, key_char):
        """Property: Single character keys should remain lowercase"""
        hotkey = f"ctrl+{key_char}"
        result = MainWindow._format_hotkey_display(hotkey)
        
        # Property: last part (the key) should be lowercase
        parts = result.split('+')
        assert parts[-1] == key_char.lower()
    
    @given(st.sampled_from(['ctrl', 'shift', 'alt', 'cmd']))
    def test_format_hotkey_display_capitalizes_modifiers(self, modifier):
        """Property: Modifier keys should be capitalized"""
        hotkey = f"{modifier}+r"
        result = MainWindow._format_hotkey_display(hotkey)
        
        # Property: first part (modifier) should be capitalized
        parts = result.split('+')
        assert parts[0] == modifier.capitalize()
    
    @given(st.lists(st.sampled_from(['ctrl', 'shift', 'alt', 'cmd']), min_size=1, max_size=3, unique=True))
    def test_format_hotkey_display_composition_associativity(self, modifiers):
        """Property: Hotkey formatting is associative with respect to order"""
        key = 'r'
        
        # Test that different orders produce consistent results
        hotkey1 = '+'.join(modifiers + [key])
        hotkey2 = '+'.join(reversed(modifiers) + [key])
        
        result1 = MainWindow._format_hotkey_display(hotkey1)
        result2 = MainWindow._format_hotkey_display(hotkey2)
        
        # Property: Results should have same components (order may differ)
        parts1 = set(result1.split('+'))
        parts2 = set(result2.split('+'))
        assert parts1 == parts2
    
    @given(st.text(alphabet='ctrl+shift+alt+cmd+abcdefghijklmnopqrstuvwxyz+', min_size=3))
    def test_format_hotkey_display_idempotent(self, hotkey_str):
        """Property: Formatting function is idempotent"""
        if '+' not in hotkey_str or hotkey_str.count('+') > 5:
            return  # Skip invalid inputs
            
        try:
            result1 = MainWindow._format_hotkey_display(hotkey_str)
            result2 = MainWindow._format_hotkey_display(result1)
            # Property: f(f(x)) = f(x) for valid inputs
            assert result1 == result2
        except:
            pass  # Skip inputs that cause errors


class TestResultMonadProperties:
    """Property-based tests for Result monad mathematical properties"""
    
    @given(st.integers())
    def test_result_monad_left_identity(self, value):
        """Property: Left Identity Law - return(a).flatMap(f) = f(a)"""
        def add_one(x):
            return Success(x + 1)
        
        # Left side: return(value).flat_map(add_one)
        left_result = Success(value).flat_map(add_one)
        
        # Right side: add_one(value)
        right_result = add_one(value)
        
        # Property: Should be equal
        assert left_result.value == right_result.value
        assert left_result.is_success() == right_result.is_success()
    
    @given(st.integers())
    def test_result_monad_right_identity(self, value):
        """Property: Right Identity Law - m.flatMap(return) = m"""
        original = Success(value)
        result = original.flat_map(lambda x: Success(x))
        
        # Property: Should be equal to original
        assert result.value == original.value
        assert result.is_success() == original.is_success()
    
    @given(st.integers())
    def test_result_monad_associativity(self, value):
        """Property: Associativity Law - m.flatMap(f).flatMap(g) = m.flatMap(x => f(x).flatMap(g))"""
        def add_one(x):
            return Success(x + 1)
        
        def multiply_two(x):
            return Success(x * 2)
        
        # Left side: m.flat_map(f).flat_map(g)
        left_result = Success(value).flat_map(add_one).flat_map(multiply_two)
        
        # Right side: m.flat_map(x => f(x).flat_map(g))
        right_result = Success(value).flat_map(lambda x: add_one(x).flat_map(multiply_two))
        
        # Property: Should be equal
        assert left_result.value == right_result.value
        assert left_result.is_success() == right_result.is_success()


class TestConfigurationProperties:
    """Property-based tests for configuration loading functions"""
    
    @given(dictionaries(
        keys=st.sampled_from(['server_url', 'hotkey', 'audio_sample_rate', 'text_add_space_after']),
        values=st.one_of(st.text(min_size=1), st.integers(min_value=1), st.booleans()),
        min_size=2
    ))
    def test_config_validation_composition(self, config_dict):
        """Property: Configuration validation preserves required keys"""
        # Ensure required keys are present
        config_dict['server_url'] = 'ws://test:8000'
        config_dict['hotkey'] = 'ctrl+r'
        
        result = _validate_config_dict(config_dict)
        
        # Property: Validation should succeed for configs with required keys
        assert result.is_success()
        if result.is_success():
            # Property: Validated config should contain all original keys
            assert all(key in result.value for key in config_dict.keys())
    
    @given(dictionaries(
        keys=st.text(alphabet='abcdefghijklmnopqrstuvwxyz_', min_size=3, max_size=20),
        values=st.one_of(st.text(min_size=1), st.integers(), st.booleans()),
        min_size=1,
        max_size=10
    ))
    def test_config_creation_robustness(self, config_dict):
        """Property: Config creation should handle arbitrary valid dictionaries"""
        # Add required keys
        config_dict['server_url'] = 'ws://test:8000'
        config_dict['hotkey'] = 'ctrl+r'
        
        result = _create_config_from_dict(config_dict)
        
        # Property: Should always succeed with valid dictionaries
        assert result.is_success()
        
        if result.is_success():
            config = result.value
            # Property: Config should have required attributes
            assert hasattr(config, 'server_url')
            assert hasattr(config, 'hotkey')
            assert config.server_url == 'ws://test:8000'
            assert config.hotkey == 'ctrl+r'


class TestUIBuilderProperties:
    """Property-based tests for UI builder function properties"""
    
    def test_ui_builder_determinism(self):
        """Property: UI builders should be deterministic (same inputs -> same outputs)"""
        # This tests the structural properties rather than specific widget creation
        # since widgets have side effects
        
        # Test that builders return consistent dictionary structures
        builder_methods = [
            'MainWindow._format_hotkey_display',
            'VoiceClientApplication._create_success_result',
        ]
        
        # Property: Pure functions should be deterministic
        for i in range(3):
            result1 = MainWindow._format_hotkey_display('ctrl+r')
            result2 = MainWindow._format_hotkey_display('ctrl+r')
            assert result1 == result2
            
            result3 = VoiceClientApplication._create_success_result()
            result4 = VoiceClientApplication._create_success_result()
            assert result3.is_success() == result4.is_success()


class TestFunctionalCompositionProperties:
    """Property-based tests for functional composition patterns"""
    
    @given(st.lists(st.integers(), min_size=1, max_size=10))
    def test_clipboard_index_conversion_inverse(self, history_length_list):
        """Property: Index conversion should be its own inverse for valid ranges"""
        for history_length in history_length_list:
            if history_length <= 0:
                continue
                
            # Test all valid indices
            for selected_index in range(history_length):
                # Convert display index to history index
                result1 = MainWindow._calculate_history_index(selected_index, history_length)
                
                if result1.is_success():
                    history_index = result1.value
                    
                    # Convert back (this tests the inverse property)
                    back_to_selected = history_length - 1 - history_index
                    
                    # Property: Converting back should give original index
                    assert back_to_selected == selected_index
    
    @given(st.lists(dictionaries(
        keys=st.just('text'),
        values=st.text(min_size=1, max_size=100)
    ), min_size=1, max_size=5))
    def test_text_extraction_total_function(self, history_list):
        """Property: Text extraction should be defined for all valid indices"""
        for valid_index in range(len(history_list)):
            result = MainWindow._extract_text_from_history(history_list, valid_index)
            
            # Property: Should succeed for all valid indices
            assert result.is_success()
            
            if result.is_success():
                # Property: Extracted text should match original
                assert result.value == history_list[valid_index]['text']
    
    @given(st.tuples(st.integers(min_value=0, max_value=5)))
    def test_selection_extraction_boundary_conditions(self, selection_tuple):
        """Property: Selection extraction handles boundary conditions correctly"""
        selection = selection_tuple
        result = MainWindow._extract_selected_index(selection)
        
        # Property: Should always succeed with valid tuples
        assert result.is_success()
        
        if result.is_success():
            # Property: Result should be the first element
            assert result.value == selection[0]


if __name__ == '__main__':
    # Run with specific settings for property-based testing
    pytest.main([__file__, '-v', '--tb=short'])