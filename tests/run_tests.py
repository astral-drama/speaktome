#!/usr/bin/env python3

"""
Test Runner Script

Provides easy way to run different test suites with proper configuration.
"""

import sys
import subprocess
import argparse
from pathlib import Path

def run_command(cmd: list[str]) -> int:
    """Run command and return exit code"""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode

def main():
    parser = argparse.ArgumentParser(description="Run Whisper system tests")
    
    parser.add_argument(
        "--type", 
        choices=["unit", "integration", "e2e", "all"],
        default="all",
        help="Type of tests to run"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    
    parser.add_argument(
        "--coverage",
        action="store_true", 
        help="Run with coverage reporting"
    )
    
    parser.add_argument(
        "--parallel", "-n",
        type=int,
        default=1,
        help="Number of parallel test workers"
    )
    
    parser.add_argument(
        "--marker", "-m",
        help="Run tests with specific marker"
    )
    
    parser.add_argument(
        "--keyword", "-k",
        help="Run tests matching keyword"
    )
    
    parser.add_argument(
        "--file",
        help="Run specific test file"
    )
    
    parser.add_argument(
        "--slow",
        action="store_true",
        help="Include slow tests"
    )
    
    args = parser.parse_args()
    
    # Base pytest command
    cmd = ["python", "-m", "pytest"]
    
    # Add test directory or specific file
    if args.file:
        cmd.append(args.file)
    else:
        test_dir = Path(__file__).parent
        cmd.append(str(test_dir))
    
    # Add test type markers
    if args.type != "all":
        cmd.extend(["-m", args.type])
    elif args.marker:
        cmd.extend(["-m", args.marker])
    
    # Add keyword filter
    if args.keyword:
        cmd.extend(["-k", args.keyword])
    
    # Verbose output
    if args.verbose:
        cmd.append("-v")
    else:
        cmd.append("--tb=short")  # Short traceback format
    
    # Coverage
    if args.coverage:
        cmd.extend([
            "--cov=server",
            "--cov-report=html",
            "--cov-report=term-missing"
        ])
    
    # Parallel execution
    if args.parallel > 1:
        cmd.extend(["-n", str(args.parallel)])
    
    # Include slow tests
    if not args.slow:
        if args.marker:
            cmd.extend(["and", "not", "slow"])
        else:
            cmd.extend(["-m", "not slow"])
    
    # Additional pytest options
    cmd.extend([
        "--strict-markers",  # Require markers to be defined
        "--strict-config",   # Strict config parsing
        "--color=yes"        # Colored output
    ])
    
    # Show test summary
    cmd.append("-ra")
    
    exit_code = run_command(cmd)
    
    if args.coverage and exit_code == 0:
        print("\n" + "="*50)
        print("Coverage report generated in htmlcov/index.html")
        print("="*50)
    
    return exit_code

if __name__ == "__main__":
    sys.exit(main())