---
name: backend-worker
description: Implements backend Python code changes with TDD approach
---

# Backend Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Use this worker for features that involve:
- Python backend code (FastAPI routes, core logic, utilities)
- Database operations and SQL
- HTTP client and networking code
- Authentication and authorization logic
- API endpoint implementation
- Business logic and data processing

## Work Procedure

### 1. Write Tests First (TDD - Red Phase)

**CRITICAL**: Tests MUST be written BEFORE implementation. This is non-negotiable.

1. Read the feature requirements carefully
2. Identify what needs to be tested:
   - Unit tests for new functions/methods
   - Integration tests for API endpoints
   - Database tests for data operations
3. Write failing tests in appropriate test files:
   - `tests/unit/test_*.py` for unit tests
   - `tests/integration/test_*.py` for integration tests
4. Run tests to confirm they fail: `py -m pytest path/to/test_file.py -v`
5. Document what each test verifies in the handoff

### 2. Implement to Make Tests Pass (Green Phase)

1. Implement the minimal code needed to make tests pass
2. Follow existing code patterns and style
3. Add appropriate error handling
4. Add docstrings and comments for complex logic
5. Run tests again to confirm they pass: `py -m pytest path/to/test_file.py -v`

### 3. Manual Verification

Automated tests are necessary but not sufficient. Perform manual checks:

1. **For API endpoints**:
   - Start the server if not running
   - Use curl or httpx to test the endpoint
   - Verify response format and status codes
   - Test error cases (invalid input, missing auth, etc.)

2. **For database operations**:
   - Check the database file directly with sqlite3
   - Verify data integrity and constraints
   - Test concurrent access if relevant

3. **For core logic**:
   - Test edge cases manually
   - Verify integration with adjacent components
   - Check logs for warnings or errors

4. Document all manual verification steps in `verification.interactiveChecks`

### 4. Run Validators

Before completing the feature:

1. **Type checking**: `py -m mypy kiro/ --ignore-missing-imports` (if mypy is available)
2. **Linting**: Check code style manually (no linter configured)
3. **All tests**: `py -m pytest tests/ -v` (ensure no regressions)

### 5. Clean Up

- Remove any debug print statements
- Ensure no test runners or processes are left running
- Check for any temporary files created during testing

## Example Handoff

```json
{
  "salientSummary": "Implemented Database.get_account() and Database.list_accounts() methods with full test coverage; ran pytest (12 passing) and manually verified account retrieval via Python REPL with test database.",
  "whatWasImplemented": "Created Database class in kiro/core/database.py with connection management, get_account() method for fetching single accounts by ID, and list_accounts() method with optional type filtering. Implemented proper error handling for missing accounts (raises KeyError) and connection failures. Added comprehensive unit tests in tests/unit/test_database.py covering normal cases, edge cases (missing account, invalid ID), and filtering logic.",
  "whatWasLeftUndone": "",
  "verification": {
    "commandsRun": [
      {
        "command": "py -m pytest tests/unit/test_database.py -v",
        "exitCode": 0,
        "observation": "12 tests passed: test_get_account_success, test_get_account_not_found, test_list_accounts_all, test_list_accounts_by_type, test_list_accounts_empty, test_connection_management, test_row_factory, test_transaction_commit, test_transaction_rollback, test_concurrent_access, test_insert_account, test_update_account"
      },
      {
        "command": "py -m pytest tests/ -v",
        "exitCode": 0,
        "observation": "All 12 tests passed, no regressions in other test files"
      }
    ],
    "interactiveChecks": [
      {
        "action": "Opened Python REPL and tested Database.get_account() with test database",
        "observed": "Successfully retrieved account with id=1, returned Account object with correct type='kiro', priority=0, config dict populated. Raised KeyError for non-existent id=999 as expected."
      },
      {
        "action": "Tested Database.list_accounts() with different filters",
        "observed": "list_accounts() returned 3 accounts, list_accounts(type='kiro') returned 2 accounts, list_accounts(type='glm') returned 1 account. All returned Account objects with correct attributes."
      },
      {
        "action": "Checked database file with sqlite3 CLI",
        "observed": "Verified accounts table structure matches expectations, confirmed test data was properly inserted and cleaned up after tests"
      }
    ]
  },
  "tests": {
    "added": [
      {
        "file": "tests/unit/test_database.py",
        "cases": [
          {
            "name": "test_get_account_success",
            "verifies": "Database.get_account() returns correct Account object for valid ID"
          },
          {
            "name": "test_get_account_not_found",
            "verifies": "Database.get_account() raises KeyError for non-existent ID"
          },
          {
            "name": "test_list_accounts_all",
            "verifies": "Database.list_accounts() returns all accounts when no filter specified"
          },
          {
            "name": "test_list_accounts_by_type",
            "verifies": "Database.list_accounts(type='kiro') filters accounts by type correctly"
          },
          {
            "name": "test_list_accounts_empty",
            "verifies": "Database.list_accounts() returns empty list when no accounts match filter"
          },
          {
            "name": "test_connection_management",
            "verifies": "Database properly opens and closes connections using context manager"
          },
          {
            "name": "test_row_factory",
            "verifies": "Database uses sqlite3.Row factory for dict-like access to results"
          },
          {
            "name": "test_transaction_commit",
            "verifies": "Database.transaction() commits changes on successful completion"
          },
          {
            "name": "test_transaction_rollback",
            "verifies": "Database.transaction() rolls back changes on exception"
          },
          {
            "name": "test_concurrent_access",
            "verifies": "Database handles concurrent reads without locking issues"
          },
          {
            "name": "test_insert_account",
            "verifies": "Database.insert() creates new account and returns lastrowid"
          },
          {
            "name": "test_update_account",
            "verifies": "Database.update() modifies existing account correctly"
          }
        ]
      }
    ]
  },
  "discoveredIssues": []
}
```

## When to Return to Orchestrator

Return to orchestrator when:

- **Blocked by missing dependencies**: Feature requires another component that doesn't exist yet (e.g., need a new database table, need an API endpoint from another service)
- **Ambiguous requirements**: Requirements are unclear or contradictory, need clarification
- **Scope creep detected**: Feature is much larger than expected, should be split
- **Breaking changes required**: Implementation requires breaking existing APIs or contracts
- **External service issues**: Dependent external service is down or behaving unexpectedly
- **Test infrastructure missing**: Need test fixtures, mocks, or utilities that don't exist

Do NOT return for:
- Normal implementation challenges (figure it out)
- Minor bugs in existing code (fix them as part of the feature)
- Missing documentation (write it)
- Code style issues (fix them)
