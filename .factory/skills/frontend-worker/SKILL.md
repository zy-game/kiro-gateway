---
name: frontend-worker
description: Implements frontend HTML/CSS/JavaScript changes with manual testing
---

# Frontend Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Use this worker for features that involve:
- HTML/CSS changes in static files
- JavaScript functionality in web UI
- Login/authentication flows
- Admin dashboard features
- Client-side validation and error handling
- UI/UX improvements

## Work Procedure

### 1. Understand the Current Implementation

1. Read the relevant HTML/CSS/JS files
2. Understand the current user flow
3. Identify what needs to change
4. Check for any existing patterns to follow

### 2. Implement Changes

1. Make minimal changes to achieve the feature goal
2. Follow existing code style and patterns
3. Add comments for complex logic
4. Ensure backward compatibility where possible

### 3. Manual Testing (CRITICAL)

Frontend changes MUST be tested manually in a real browser. Automated tests are not sufficient.

**Testing checklist**:

1. **Start the server** (if not running):
   ```bash
   cd E:\kiro-gateway
   py main.py
   ```

2. **Test in browser**:
   - Open http://localhost:8000 in Chrome/Firefox/Edge
   - Test the specific feature you implemented
   - Test related features to ensure no regressions
   - Test error cases (invalid input, network errors, etc.)
   - Check browser console for JavaScript errors
   - Check Network tab for failed requests

3. **Test different scenarios**:
   - Happy path (everything works)
   - Error path (invalid input, server errors)
   - Edge cases (empty data, very long input, special characters)
   - Browser refresh behavior
   - Back/forward navigation

4. **Document every test** in `verification.interactiveChecks`:
   - What you did (clicked button, entered text, etc.)
   - What you observed (page loaded, error shown, etc.)
   - Include screenshots or detailed descriptions

### 4. Code Review

Before completing:

1. Check for console.log statements (remove or comment out)
2. Verify no hardcoded values that should be configurable
3. Check for proper error handling
4. Ensure responsive design (if applicable)

### 5. Clean Up

- Stop the server if you started it
- Remove any test data created
- Clear browser cache if needed for testing

## Example Handoff

```json
{
  "salientSummary": "Modified login.html to add 100ms delay before redirect, fixing the cookie timing issue; tested in Chrome, Firefox, and Edge - login now works without manual refresh in all browsers.",
  "whatWasImplemented": "Added await new Promise(resolve => setTimeout(resolve, 100)) before window.location.href = '/admin' in login.html handleLogin() function. This ensures the session_token cookie is fully set in the browser before redirecting to the admin page. The delay is imperceptible to users but prevents the race condition where subsequent API calls don't see the cookie.",
  "whatWasLeftUndone": "",
  "verification": {
    "commandsRun": [
      {
        "command": "py main.py",
        "exitCode": 0,
        "observation": "Server started successfully on localhost:8000, no errors in startup logs"
      }
    ],
    "interactiveChecks": [
      {
        "action": "Chrome: Opened http://localhost:8000/login, entered username 'admin' and password 'admin123', clicked Login button",
        "observed": "Login successful, redirected to /admin page immediately, dashboard loaded with account stats (3 accounts, 2 tokens), no manual refresh needed. Checked Network tab: /auth/login returned 200 with Set-Cookie header, /auth/me returned 200 (cookie present), /admin/accounts returned 200."
      },
      {
        "action": "Firefox: Repeated same login test",
        "observed": "Login successful, admin page loaded immediately without refresh. Dashboard displayed correctly with all data. No JavaScript errors in console."
      },
      {
        "action": "Edge: Repeated same login test",
        "observed": "Login successful, admin page loaded immediately. All features working correctly. No console errors."
      },
      {
        "action": "Chrome: Tested logout and re-login",
        "observed": "Logout redirected to /login correctly. Re-login worked immediately without refresh. Cookie cleared on logout, set correctly on login."
      },
      {
        "action": "Chrome: Tested invalid credentials",
        "observed": "Error message displayed correctly: 'Invalid username or password'. No redirect occurred. Login button re-enabled after error."
      },
      {
        "action": "Chrome: Checked browser DevTools Application tab",
        "observed": "session_token cookie present after login with correct attributes: HttpOnly, SameSite=Lax, Path=/. Cookie persists across page navigation."
      }
    ]
  },
  "tests": {
    "added": []
  },
  "discoveredIssues": []
}
```

## When to Return to Orchestrator

Return to orchestrator when:

- **Backend API missing**: Feature requires a backend endpoint that doesn't exist
- **Breaking changes needed**: Changes would break existing functionality significantly
- **Design decisions needed**: Multiple implementation approaches, need guidance
- **Browser compatibility issues**: Feature doesn't work in required browsers and no workaround found
- **Security concerns**: Implementation might introduce security vulnerabilities
- **Performance issues**: Implementation causes significant performance degradation

Do NOT return for:
- Minor CSS issues (fix them)
- JavaScript syntax errors (debug and fix)
- Missing documentation (write it)
- Browser console warnings (fix them)
