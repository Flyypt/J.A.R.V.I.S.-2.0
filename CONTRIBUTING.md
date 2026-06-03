# Contributing to J.A.R.V.I.S.

Thanks for your interest! This project is intentionally **single-file** — that's the core philosophy. Keep it simple, keep it self-contained.

## Quick Start

1. **Fork** the repo
2. **Branch**: `git checkout -b feature/your-feature-name`
3. **Test**: `python -m py_compile jarvis.py` — must pass with zero errors
4. **Commit**: Clear, descriptive messages
5. **PR**: Submit with a description of what changed and why

## Guidelines

- **Single file unless necessary**: The entire app lives in `jarvis.py`. If you're adding a feature, it should fit there.
- **No breaking changes**: Don't break existing tool schemas or UI contracts.
- **Cross-platform**: Windows is primary, but Linux/macOS fallbacks are appreciated.
- **Graceful degradation**: Optional dependencies (numpy, pynput) should fail silently.
- **Security first**: Any new tool that modifies the system goes through the approval system.

## Code Style

- PEP 8-ish (we're pragmatic, not strict)
- Type hints for function signatures
- Docstrings for all tool methods
- Keep the Tony Stark vibe in UI strings

## Questions?

Open an issue. Tag it `[QUESTION]` or `[FEATURE REQUEST]`.
