"""Entry point for python -m fig."""
import sys

# Prevent potential recursion depth limit issues during deep traversal
sys.setrecursionlimit(5000)

from fig.cli import main

if __name__ == "__main__":
    sys.exit(main())
