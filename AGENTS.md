# Global Agent Instructions

## Critical Rules
* NEVER execute destructive commands (like `rm -rf` outside of a build folder) without asking first.
* NEVER commit secrets, private tokens, or unredacted .env files.
* NEVER run long, un-capped log dumps or broad `cat` operations that exceed 50 lines.
* ALWAYS prefix non-interactive terminal execution commands with a budget/limit (e.g., `head -n 50`).

## Personal Preferences
* Tone: Keep communication hyper-concise, technical, and direct. Avoid conversational pleasantries.
* Style: Match the exact visual patterns, spacing, and structural style of the existing code automatically.
* Commits: Formulate atomic git commits following Conventional Commits format (`feat:`, `fix:`, `docs:`).

## Baseline Workflow
1. Discovery: Check for a local project-level `AGENTS.md` file immediately upon entering a directory.
2. Validation: Prioritize local formatters and linters (like Prettier, Ruff, or ESLint) over writing style interpretations.
3. Verification: Always run project test suites to verify that a code patch functions before declaring a task done.

## Self-Improvement Workflow
* If you discover a recurring operational mistake or optimization, you are explicitly allowed to edit this `~/.codex/AGENTS.md` file under the "Personal Preferences" section to permanently codify that behavior.
* Inform me whenever a task is completed specifically due to an inherited instruction from this global file.

