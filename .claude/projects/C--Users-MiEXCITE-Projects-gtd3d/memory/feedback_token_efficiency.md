---
name: Token efficiency rules
description: Avoid wasting tokens on exploration, open-ended prompts, and large file reads — use targeted grep+read instead
type: feedback
---

Never use Explore agents on large files (controllers.py is 3200+ lines, body_viewer.js is 3700+ lines, main.dart is 2300+ lines). A single Explore agent burned 56k tokens reading controllers.py.

**Why:** User pays per token and values efficiency. Open-ended exploration is extremely expensive.

**How to apply:**
- Always `grep -n` for the exact function/pattern first, then `Read` only the 30-50 lines needed
- Never give Sonnet open-ended prompts like "get the tasks done" — always specify exact file, line, and what to write
- Task files (SONNET_TASKS.md, SONNET_S24_ULTRA_TASKS.md) contain exact line numbers and code snippets — follow them directly, no exploration needed
- When creating task files for Sonnet, include: exact file path, exact line numbers, code to insert, and "Do NOT" boundaries
- Prefer parallel targeted Grep+Read calls over a single Explore agent
