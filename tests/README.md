# SpeakToMe System Tests

This directory contains comprehensive tests for the SpeakToMe voice-to-text system, focusing on integration and end-to-end testing with targeted unit tests for critical components.

## Test Philosophy

Our testing strategy emphasizes:

- **Integration Tests**: Test complete workflows and component interactions
- **End-to-End Tests**: Test the full system from user input to final output
- **Selective Unit Tests**: Focus on critical functional components (Result monad, core business logic)
- **Real Component Testing**: Use actual implementations with test doubles only where necessary

## Test Structure

```
tests/
├── conftest.py                    # Shared fixtures and configuration
├── test_utils.py                  # Test utilities and mock implementations
├── run_tests.py                   # Test runner script
│
├── unit/                          # Focused unit tests
│   └── test_result_monad.py       # Result monad functionality
│
├── integration/                   # Integration tests
│   ├── test_audio_pipeline.py     # Pipeline integration
│   ├── test_event_system.py       # Event system integration
│   ├── test_plugin_system.py      # Plugin system integration
│   ├── test_websocket_manager.py  # WebSocket connection management
│   ├── test_file_validation.py    # File validation workflows
│   └── test_dependency_container.py # DI container integration
│
└── e2e/                           # End-to-end tests
    ├── test_complete_transcription_flow.py  # Full transcription workflows
    ├── test_websocket_realtime.py           # Real-time transcription
    ├── test_http_file_upload.py             # HTTP file upload flow
    └── test_plugin_integration.py           # Plugin integration in workflows
```

## Running Tests

### Quick Start

```bash
# Run all tests
python tests/run_tests.py

# Run only integration tests
python tests/run_tests.py --type integration

# Run with coverage
python tests/run_tests.py --coverage

# Run specific test file
python tests/run_tests.py --file tests/integration/test_audio_pipeline.py
```

### Test Types

```bash
# Unit tests only (fast, focused)
python tests/run_tests.py --type unit

# Integration tests (moderate speed, component interaction)
python tests/run_tests.py --type integration

# End-to-end tests (slower, full system)
python tests/run_tests.py --type e2e

# All tests including slow ones
python tests/run_tests.py --slow
```

### Advanced Options

```bash
# Verbose output with parallel execution
python tests/run_tests.py -v --parallel 4

# Run tests matching keyword
python tests/run_tests.py -k "pipeline"

# Run tests with specific marker
python tests/run_tests.py -m "websocket"

# Run with coverage report
python tests/run_tests.py --coverage --type integration
```

### Using pytest directly

```bash
# Basic pytest usage
pytest tests/

# With markers
pytest -m integration tests/

# With coverage
pytest --cov=server tests/

# Specific test
pytest tests/integration/test_audio_pipeline.py::TestAudioPipelineIntegration::test_complete_pipeline_processing
```

## Test Fixtures

### Key Fixtures (from `conftest.py`)

- `test_container`: Dependency injection container with test services
- `test_event_bus`: Event bus for testing event flows
- `websocket_manager`: WebSocket connection manager
- `test_audio_files`: Generated test audio files in various formats
- `test_server_components`: Integrated server components
- `test_plugins`: Loaded plugin system for testing

### Test Utilities (from `test_utils.py`)

- `TestTranscriptionProvider`: Mock transcription service with realistic behavior
- `TestWebSocketClient`: Simulated WebSocket client for integration testing
- `TestFileUploader`: Mock file uploader for HTTP endpoint testing
- `create_test_wav_data()`: Generate realistic WAV audio data
- `wait_for_condition()`: Async condition waiting utility
- `assert_result_success/failure()`: Result monad assertion helpers

## Test Categories

### Integration Tests

Test component interactions and workflows:

- **Audio Pipeline**: Complete pipeline processing with all stages
- **Event System**: Event publishing, handling, and middleware
- **Plugin System**: Plugin loading, configuration, and lifecycle
- **WebSocket Manager**: Connection management and message handling
- **File Validation**: Validation pipeline with various file types
- **Dependency Container**: Service resolution and lifecycle management

### End-to-End Tests

Test complete user workflows:

- **HTTP Upload Flow**: File upload → validation → transcription → result
- **WebSocket Real-time**: Connect → configure → stream audio → receive transcription
- **Plugin Integration**: Plugins participating in complete workflows
- **Error Handling**: Error scenarios throughout the complete flow
- **Concurrent Processing**: Multiple simultaneous transcription requests

### Unit Tests

Focused tests for critical functional components:

- **Result Monad**: Functor/monad laws, error handling, composition
- **Core Business Logic**: Critical algorithms and transformations
- **Utility Functions**: Pure functions and data transformations

## Test Data

### Audio Files

Tests use generated audio data:
- WAV files with various durations and sample rates
- MP3 files for format conversion testing
- Invalid files for error handling testing
- Large files for performance testing

### Mock Services

- `TestTranscriptionProvider`: Realistic transcription simulation
- Configurable processing delays for performance testing
- Error injection capabilities for failure testing
- Request/response tracking for verification

## Configuration

### pytest.ini

```ini
[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
markers =
    unit: Unit tests
    integration: Integration tests
    e2e: End-to-end tests
    slow: Slow running tests
    plugin: Plugin system tests
    pipeline: Audio pipeline tests
    events: Event system tests
    websocket: WebSocket tests
addopts = --strict-markers --strict-config
```

### Test Environment

Tests automatically set up a clean test environment:
- Temporary directories for test files
- Isolated dependency containers
- Clean event bus instances
- Mock external dependencies

## Best Practices

### Writing Tests

1. **Use descriptive test names** that explain the scenario
2. **Test the happy path first**, then edge cases and errors
3. **Use fixtures for shared setup** rather than repeating code
4. **Test behavior, not implementation** - focus on inputs/outputs
5. **Use realistic test data** that represents actual usage

### Integration Testing

1. **Test component boundaries** where data flows between modules
2. **Use real implementations** where possible, mocks only when necessary
3. **Verify side effects** (events published, files created, etc.)
4. **Test error propagation** across component boundaries
5. **Include timing and concurrency** scenarios

### End-to-End Testing

1. **Test complete user journeys** from start to finish
2. **Include realistic data volumes** and processing times
3. **Test system behavior under load** (multiple concurrent requests)
4. **Verify system state** after operations complete
5. **Test failure recovery** and graceful degradation

## Continuous Integration

Tests are designed to run reliably in CI environments:

- **Deterministic test data** - no random failures
- **Proper cleanup** - no test pollution between runs
- **Configurable timeouts** - adjust for CI system performance
- **Parallel execution safe** - tests don't interfere with each other
- **Clear failure reporting** - easy to diagnose CI failures

## Debugging Tests

### Common Issues

1. **Async test timeouts**: Increase timeout values or check for proper awaiting
2. **Event processing delays**: Use `wait_for_condition()` instead of fixed delays
3. **Resource cleanup**: Ensure fixtures properly clean up resources
4. **Test isolation**: Check for shared state between tests

### Debugging Tools

```bash
# Run single test with full output
pytest -v -s tests/integration/test_audio_pipeline.py::test_specific_test

# Run with pdb debugging
pytest --pdb tests/integration/test_audio_pipeline.py

# Print test setup/teardown
pytest --setup-show tests/integration/test_audio_pipeline.py
```

## Contributing Tests

When adding new functionality:

1. **Add integration tests** for new component interactions
2. **Add e2e tests** for new user-facing features
3. **Update fixtures** if new test dependencies are needed
4. **Add appropriate markers** for test categorization
5. **Update this README** if new test patterns are introduced

The test suite should provide confidence that the system works correctly while being maintainable and fast enough for regular development use.