# /end Workflow

This workflow summarizes the session when the user types /end.

## Summary Process
1.  **Summarize Done:** List all tasks completed during the session.
2.  **Summarize Pending:** List tasks that were started but not finished.
3.  **Next Steps:** Suggest the immediate next actions for the next session.
4.  **Save:** Write the summary to SESSION_SUMMARY.md in the root directory.

## Current State
The agent should search for GEMINI_*_TASKS.md files to update progress before ending.
