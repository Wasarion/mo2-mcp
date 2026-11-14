# Working on mo2-mcp

This is Wasarion's (Mercury71) learning project: a small MCP server plugin for Mod Organizer 2. He is learning GitHub and Python through it, so changes must be easy for him to follow.

## Rules for Claude sessions

- **Never push to `main` and never merge a pull request.** Work on a branch, open a PR, and stop. Wasarion reviews and merges every PR himself.
- One topic per PR. The PR body explains in plain words what changed, why, and how it was tested, and says what was *not* tested on a live MO2.
- Run both checks before pushing and report the result in the PR:
  ```
  pyright
  QT_QPA_PLATFORM=offscreen python tests/test_e2e.py
  ```
- New tools need a test in `tests/test_e2e.py` (extend the fake organizer as needed).
- Plugin code may only use the Python standard library plus what MO2 ships (`mobase`, PyQt6).
- Every `mobase` call runs on MO2's GUI thread (`main_thread=True`, or `self.invoke(...)` from a worker-thread tool). Tools that change MO2 state set `writes=True`.
- Log with f-strings: MO2's log handler does not apply `%` formatting.
- Never commit `mo2_mcp/connection.json` or `mo2_mcp/tools.json` (they hold the user's token), and never put personal paths, usernames or email addresses in the repo.
- Code borrowed from other GPL projects is credited in the module docstring, the README and the PR.
