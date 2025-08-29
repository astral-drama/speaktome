#!/usr/bin/env python3

"""
Test Runner for SpeakToMe Desktop Client

Comprehensive test runner following server testing patterns.
Supports test categorization, parallel execution, and coverage reporting.
"""

import sys
import argparse
import subprocess
import logging
from pathlib import Path
from typing import List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add project paths
current_dir = Path(__file__).parent.parent
sys.path.insert(0, str(current_dir))
sys.path.insert(0, str(current_dir.parent))


def run_command(command: List[str], description: str) -> int:
    """Run a command and return exit code"""
    logger.info(f"Running: {description}")
    logger.debug(f"Command: {' '.join(command)}")
    
    try:
        result = subprocess.run(command, capture_output=True, text=True)
        
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        
        if result.returncode == 0:
            logger.info(f"✅ {description} - PASSED")
        else:
            logger.error(f"❌ {description} - FAILED (exit code: {result.returncode})")
        
        return result.returncode
        
    except FileNotFoundError as e:
        logger.error(f"❌ Command not found: {e}")
        return 1
    except Exception as e:
        logger.error(f"❌ Error running {description}: {e}")
        return 1


def build_pytest_command(args) -> List[str]:
    """Build pytest command based on arguments"""
    command = ["python", "-m", "pytest"]
    
    # Test selection
    if args.type:
        if args.type == "unit":
            command.extend(["-m", "unit", "tests/unit/"])
        elif args.type == "integration":
            command.extend(["-m", "integration", "tests/integration/"])
        elif args.type == "e2e":
            command.extend(["-m", "e2e", "tests/e2e/"])
        elif args.type == "functional":
            command.extend(["-m", "functional"])
        elif args.type == "pipeline":
            command.extend(["-m", "pipeline"])
        elif args.type == "events":
            command.extend(["-m", "events"])
        elif args.type == "providers":
            command.extend(["-m", "providers"])
    else:
        # Default: run all tests except slow ones
        if not args.slow:
            command.extend(["-m", "not slow"])
        command.append("tests/")
    
    # Specific file
    if args.file:
        command.append(args.file)
    
    # Keyword matching
    if args.keyword:
        command.extend(["-k", args.keyword])
    
    # Verbosity
    if args.verbose:
        command.append("-v")
    if args.verbose >= 2:
        command.append("-s")  # Don't capture output
    
    # Parallel execution
    if args.parallel and args.parallel > 1:
        command.extend(["-n", str(args.parallel)])
    
    # Coverage
    if args.coverage:
        command.extend([
            "--cov=client",
            "--cov=shared", 
            "--cov-report=html:htmlcov",
            "--cov-report=term-missing"
        ])
    
    # Additional pytest options
    if args.pytest_args:
        command.extend(args.pytest_args)
    
    # Output options
    if args.tb:
        command.extend(["--tb", args.tb])
    
    # Performance options
    if args.durations:
        command.extend(["--durations", str(args.durations)])
    
    return command


def check_dependencies():
    """Check that required dependencies are available"""
    logger.info("🔍 Checking test dependencies...")
    
    required_modules = [
        "pytest", "pytest_asyncio", "unittest.mock"
    ]
    
    missing_modules = []
    
    for module in required_modules:
        try:
            __import__(module.replace("-", "_"))
            logger.debug(f"✅ {module} - available")
        except ImportError:
            missing_modules.append(module)
            logger.error(f"❌ {module} - missing")
    
    if missing_modules:
        logger.error(f"Missing dependencies: {missing_modules}")
        logger.info("Install with: pip install -r requirements.txt")
        return False
    
    logger.info("✅ All test dependencies available")
    return True


def run_linting():
    """Run code linting"""
    commands = []
    
    # Try ruff first (if available)
    try:
        subprocess.run(["ruff", "--version"], capture_output=True, check=True)
        commands.append((
            ["ruff", "check", "client/", "shared/", "tests/"],
            "Ruff linting"
        ))
    except (FileNotFoundError, subprocess.CalledProcessError):
        logger.warning("Ruff not available, skipping linting")
    
    exit_codes = []
    for command, description in commands:
        exit_code = run_command(command, description)
        exit_codes.append(exit_code)
    
    return max(exit_codes) if exit_codes else 0


def run_type_checking():
    """Run type checking"""
    try:
        subprocess.run(["mypy", "--version"], capture_output=True, check=True)
        return run_command(
            ["mypy", "client/", "shared/", "--ignore-missing-imports"],
            "MyPy type checking"
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        logger.warning("MyPy not available, skipping type checking")
        return 0


def display_test_summary(results: List[tuple]):
    """Display test execution summary"""
    print("\n" + "="*60)
    print("📊 TEST EXECUTION SUMMARY")
    print("="*60)
    
    total_tests = len(results)
    passed_tests = sum(1 for _, exit_code in results if exit_code == 0)
    failed_tests = total_tests - passed_tests
    
    for description, exit_code in results:
        status = "PASSED" if exit_code == 0 else "FAILED"
        emoji = "✅" if exit_code == 0 else "❌"
        print(f"{emoji} {description}: {status}")
    
    print("-" * 60)
    print(f"Total: {total_tests}, Passed: {passed_tests}, Failed: {failed_tests}")
    
    if failed_tests == 0:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n💥 {failed_tests} test suite(s) failed")
        return 1


def main():
    """Main test runner entry point"""
    parser = argparse.ArgumentParser(
        description="SpeakToMe Desktop Client Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tests/run_tests.py                    # Run all tests except slow ones
  python tests/run_tests.py --type unit        # Run only unit tests
  python tests/run_tests.py --type integration # Run only integration tests
  python tests/run_tests.py --type e2e         # Run only e2e tests
  python tests/run_tests.py --coverage         # Run with coverage report
  python tests/run_tests.py --parallel 4       # Run with 4 parallel workers
  python tests/run_tests.py --slow             # Include slow tests
  python tests/run_tests.py -k "pipeline"      # Run tests matching keyword
  python tests/run_tests.py --file tests/unit/test_pipeline.py  # Run specific file
  python tests/run_tests.py --lint --typecheck # Run linting and type checking
        """
    )
    
    # Test selection
    parser.add_argument(
        "--type", 
        choices=["unit", "integration", "e2e", "functional", "pipeline", "events", "providers"],
        help="Run specific type of tests"
    )
    parser.add_argument("--file", help="Run specific test file")
    parser.add_argument("-k", "--keyword", help="Run tests matching keyword")
    parser.add_argument("--slow", action="store_true", help="Include slow tests")
    
    # Output control
    parser.add_argument("-v", "--verbose", action="count", default=0, help="Increase verbosity")
    parser.add_argument("--tb", choices=["short", "long", "line", "native", "no"], default="short", help="Traceback style")
    parser.add_argument("--durations", type=int, help="Show N slowest test durations")
    
    # Parallel execution
    parser.add_argument("--parallel", "-n", type=int, help="Number of parallel workers")
    
    # Coverage
    parser.add_argument("--coverage", action="store_true", help="Generate coverage report")
    
    # Code quality
    parser.add_argument("--lint", action="store_true", help="Run linting")
    parser.add_argument("--typecheck", action="store_true", help="Run type checking")
    parser.add_argument("--quality", action="store_true", help="Run linting and type checking")
    
    # Direct pytest arguments
    parser.add_argument("pytest_args", nargs="*", help="Additional arguments to pass to pytest")
    
    args = parser.parse_args()
    
    # Handle quality flag
    if args.quality:
        args.lint = True
        args.typecheck = True
    
    print("🧪 SpeakToMe Desktop Client Test Runner")
    print("=" * 50)
    
    # Check dependencies first
    if not check_dependencies():
        return 1
    
    results = []
    
    # Run code quality checks first
    if args.lint:
        exit_code = run_linting()
        results.append(("Code Linting", exit_code))
    
    if args.typecheck:
        exit_code = run_type_checking()
        results.append(("Type Checking", exit_code))
    
    # Run tests
    pytest_command = build_pytest_command(args)
    exit_code = run_command(pytest_command, "Test Suite")
    results.append(("Test Suite", exit_code))
    
    # Display summary
    return display_test_summary(results)


if __name__ == "__main__":
    sys.exit(main())