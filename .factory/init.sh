#!/bin/bash
# Initialization script for Kiro Gateway mission

# This mission doesn't require special initialization.
# The Python environment and dependencies are already set up.

echo "Kiro Gateway mission environment ready"
echo "Python: $(py --version)"
echo "Pytest: $(py -m pytest --version)"
echo "Working directory: $(pwd)"

# Check if server is running
if netstat -ano | findstr ":8000" > /dev/null 2>&1; then
    echo "Server is running on port 8000"
else
    echo "Server is not running. Start with: py main.py"
fi

# Check database
if [ -f "data/accounts.db" ]; then
    echo "Database exists: data/accounts.db"
else
    echo "Warning: Database not found at data/accounts.db"
fi

exit 0
