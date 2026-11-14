# Contributing

Thanks for helping. Small, focused pull requests are easiest to review.

- Plugin code uses only the Python standard library plus what MO2 ships (`mobase`, PyQt6). Please keep it that way, so users have nothing to install.
- Every `mobase` call must run on MO2's GUI thread: register new tools through `Mo2Tools.tools()` and leave `main_thread=True` unless the tool never touches `mobase`.
- Tools that change MO2 state must set `writes=True`.
- Run `pyright` and `QT_QPA_PLATFORM=offscreen python tests/test_e2e.py` before opening a PR, and extend the fake organizer in `tests/test_e2e.py` for new tools.
- Say which MO2 version and game you tested on.

By contributing you agree that your contribution is licensed under GPL-3.0-or-later.
