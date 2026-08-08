# Project Overview

## Golden Rules

1. **All documentation and code comments must be written in English.**

## Development workflow

For implementation tasks, use this iterative workflow:

1. Spawn an implementation subagent.
2. The implementation agent may edit files and run relevant tests.
3. After implementation, spawn a separate review subagent.
4. The review agent must inspect:
   - correctness
   - regressions
   - security issues
   - type errors
   - missing edge cases
   - unnecessary complexity
5. The reviewer must return one of:
   - APPROVED
   - CHANGES_REQUIRED, followed by concrete file-level instructions
6. When changes are required, send only those findings back to the
   implementation agent.
7. Repeat implementation and review until:
   - the reviewer returns APPROVED, or
   - 10 review cycles have completed.
8. Never exceed 10 cycles.
9. At the end, run the repository validation commands and summarize:
   - files changed
   - tests executed
   - remaining risks
   - reviewer verdict

Only the implementation agent may modify source files.
The review agent must remain read-only.
Do not allow both agents to edit concurrently.