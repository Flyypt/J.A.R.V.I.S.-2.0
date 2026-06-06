[CONTRIBUTING.md](https://github.com/user-attachments/files/28669147/CONTRIBUTING.md)
# Contributing to J.A.R.V.I.S. 2.0

Thank you for your interest in contributing to J.A.R.V.I.S.! This document outlines the process and guidelines for contributing to this project.

## Table of Contents

- [Project Philosophy](#project-philosophy)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [How to Contribute](#how-to-contribute)
- [Coding Standards](#coding-standards)
- [Single-File Architecture](#single-file-architecture)
- [Testing Your Changes](#testing-your-changes)
- [Pull Request Process](#pull-request-process)
- [Issue Reporting](#issue-reporting)
- [Community Guidelines](#community-guidelines)

---

## Project Philosophy

J.A.R.V.I.S. is designed to be a **single-file, self-contained, system-level AI assistant**. Every design decision prioritizes:

1. **Simplicity** — One file. No build steps. No microservices.
2. **Privacy** — Local execution. No telemetry. No cloud dependencies beyond the LLM API.
3. **Power** — Full system control with sensible safety guardrails.
4. **Aesthetics** — Sci-fi HUD that feels like Tony Stark's helmet display.

If your contribution aligns with these principles, it is welcome.

---

## Getting Started

### Prerequisites

- Python 3.10 or higher
- Git
- A Gemini API key (for testing live features)

### Fork and Clone

```bash
# Fork the repo on GitHub, then:
git clone https://github.com/YOUR_USERNAME/J.A.R.V.I.S.-2.0.git
cd J.A.R.V.I.S.-2.0
```

---

## Development Setup

### 1. Create a Virtual Environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Add Your API Key

Create `api_keys.json` in the project root:

```json
{
  "gemini_api_key": "YOUR_TEST_KEY_HERE"
}
```

> **Never commit `api_keys.json`**. It is already in `.gitignore`.

### 4. Verify the Build

```bash
python -m py_compile jarvis.py
```

If this returns no output, the syntax is valid.

---

## How to Contribute

### Types of Contributions We Welcome

- 🐛 **Bug fixes** — Fix crashes, race conditions, or platform-specific issues
- ✨ **New tools** — Add functions to the tool registry (see guidelines below)
- 🎨 **UI improvements** — Better CSS, new animations, accessibility fixes
- 📝 **Documentation** — README updates, code comments, tutorials
- 🔊 **Audio enhancements** — Better VAD, noise suppression, new audio backends
- 🖥️ **Platform support** — Linux/macOS-specific window control, system integration

### Types of Contributions We Are Cautious About

- ❌ **Splitting the single file** — Unless there is an *extraordinary* technical reason
- ❌ **Adding heavy dependencies** — Each new dependency must justify its weight
- ❌ **Cloud/telemetry integrations** — This is a local-first project
- ❌ **Removing safety features** — The approval system and sandboxes are non-negotiable

---

## Coding Standards

### Python Style

- Follow **PEP 8** with these project-specific exceptions:
  - Line length: **100 characters** (not 79)
  - Use **double quotes** for strings unless single quotes prevent escaping
- Use **type hints** for new function signatures where practical
- Add **docstrings** for new tools following this format:


```python
def my_new_tool(param: str) -> dict:
    """
    Brief description of what the tool does.

    Args:
        param: Description of the parameter.

    Returns:
        A dictionary with standardized keys:
        - content: Human-readable result
        - error: Error message if failed, else None
    """
```

### JavaScript / CSS (HUD)

- Use **2-space indentation** for HTML/CSS/JS inside the PyQt6 WebView
- Prefer **CSS variables** for colors to maintain the cyan theme
- Comment complex SVG animations

---

## Single-File Architecture

This is the **#1 rule**: `jarvis.py` must remain a single, self-contained file that can be copied anywhere and run with `python jarvis.py`.

### What This Means

| ✅ Do | ❌ Don't |
|-------|----------|
| Add new Python functions/classes inside `jarvis.py` | Create `utils.py`, `audio.py`, `tools.py` |
| Embed HTML/CSS/JS as Python strings or heredocs | Add `templates/index.html`, `static/style.css` |
| Use standard library + `requirements.txt` deps only | Add build steps, webpack, or compilation |
| Load external resources via CDN in the WebView | Bundle local `.js` files that must travel with the script |

### When Splitting Is Allowed

The only acceptable exceptions are:

1. **Binary assets** — Images, fonts, or audio files in an `assets/` folder
2. **Documentation** — `README.md`, `CONTRIBUTING.md`, `LICENSE`
3. **Config templates** — `requirements.txt`, `.gitignore`
4. **Legal/compliance** — Third-party license notices

If you believe a feature *requires* splitting the file, open an **Issue** first to discuss.

---

## Testing Your Changes

### Minimum Checklist Before Submitting

```bash
# 1. Syntax check
python -m py_compile jarvis.py

# 2. Run without errors (no API key needed for UI load test)
python jarvis.py
# Verify: Window opens, arc reactor animates, telemetry updates

# 3. Test with API key (full integration)
# - Send a text command
# - Enable voice and test audio I/O
# - Trigger a dangerous tool and verify the approval modal appears

# 4. Platform test (if applicable)
# - If you modified window control: test on Windows, Linux, *and* macOS
# - If you modified audio: test with multiple device indices
```

### What to Test

| Area | Test Case |
|------|-----------|
| **Startup** | Clean launch with no `jarvis_config.json` |
| **Config** | Settings persist and reload correctly |
| **Tools** | New tools return valid JSON, handle errors gracefully |
| **Safety** | Dangerous tools trigger approval modal |
| **Audio** | No crackling, correct sample rates, volume scaling works |
| **UI** | No JavaScript console errors, responsive layout |
| **Tray** | Minimize to tray, restore, global hotkey |

---

## Pull Request Process

### 1. Branch Naming

```bash
git checkout -b feature/short-description   # New features
git checkout -b fix/bug-description       # Bug fixes
git checkout -b docs/what-you-updated     # Documentation
git checkout -b tool/tool-name            # New tool additions
```

### 2. Commit Messages

Use clear, descriptive commit messages:

```
feat: add focus_window support for macOS
fix: resolve audio crackling on 48kHz devices
docs: update Linux installation steps
tool: add get_battery_status for laptops
refactor: simplify telemetry worker thread logic
```

### 3. PR Description Template

When opening a Pull Request, please include:

```markdown
## Summary
One-line description of the change.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] New tool
- [ ] Documentation
- [ ] Refactor

## Testing
Describe what you tested and on which platform(s).

## Screenshots (if UI changed)
Attach before/after images.

## Checklist
- [ ] `python -m py_compile jarvis.py` passes
- [ ] I tested this on my local machine
- [ ] I did not split the single file (or I discussed it in an Issue first)
- [ ] New tools follow the docstring format
- [ ] Dangerous tools still trigger approval modals
```

### 4. Review Process

- Maintainers will review within **48–72 hours**
- Address feedback with additional commits
- Once approved, a maintainer will squash-merge

---

## Issue Reporting

### Before Opening an Issue

1. Search existing issues (open and closed)
2. Check the Troubleshooting section in the README
3. Verify you are on the latest commit: `git pull origin main`

### Bug Report Template

```markdown
**Describe the bug**
A clear, concise description.

**To Reproduce**
Steps to reproduce:
1. Launch with `python jarvis.py`
2. Click '...'
3. See error

**Expected behavior**
What should have happened.

**Screenshots / Logs**
Paste relevant `jarvis.log` output (redact API keys).

**Environment:**
- OS: [e.g. Windows 11, Ubuntu 22.04]
- Python version: [e.g. 3.11.4]
- PyQt6 version: [e.g. 6.5.2]
- Audio backend: [e.g. WASAPI, PulseAudio, CoreAudio]

**Additional context**
Anything else.
```

### Feature Request Template

```markdown
**Is your feature request related to a problem?**
A clear description.

**Describe the solution**
What you want to happen.

**Describe alternatives**
Other approaches you considered.

**Does this require splitting the single file?**
Yes / No / Unsure
```

---

## Community Guidelines

### Code of Conduct

This project adheres to a standard open-source code of conduct:

- **Be respectful** — No harassment, discrimination, or trolling
- **Be constructive** — Critique ideas, not people
- **Be patient** — Maintainers are volunteers
- **Be clear** — Provide context and reproducible steps

### Attribution

Contributors will be added to the **Acknowledgments** section in the README after their first merged PR.

---

## Questions?

- Open a **Discussion** on GitHub for general questions
- Open an **Issue** for bugs or feature requests
- For security vulnerabilities, please email the maintainer directly instead of opening a public issue

---

> *"I have indeed been uploaded, sir. We're online and ready."*

Thank you for helping make J.A.R.V.I.S. better!
