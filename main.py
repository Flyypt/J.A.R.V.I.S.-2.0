import sys
import os
import json
import asyncio
import threading
import io
import time
import random
import math
import struct
import ctypes
import platform
import subprocess
import shutil
import traceback
import urllib.request
import urllib.parse
import urllib.error
import re
import html
import html.parser
import ipaddress
import socket
import ast
import datetime
from pathlib import Path
from typing import List, Optional, Callable, Dict, Any
try:
    import winsound  # Windows-only; used by set_timer for the alarm beep
except ImportError:
    winsound = None

import pyautogui
import psutil
import pyperclip
import sounddevice as sd
import queue

from PyQt6.QtCore import QUrl, pyqtSlot, QObject, QThread, pyqtSignal, QTimer, QMetaObject, Qt
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtWebEngineCore import QWebEngineProfile
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel

from google import genai
from google.genai import types

# ==========================================
# CONFIGURATION & PATH SETUP
# ==========================================
BASE_DIR = Path(__file__).resolve().parent
API_CONFIG_PATH = BASE_DIR / "api_keys.json"

MODEL_POOL = [
    "gemini-2.5-flash-native-audio-latest",
    "gemini-2.0-flash-live-preview-04-09",
]

MAX_HISTORY = 50
MAX_PENDING = 50
AUDIO_SR_OUT = 24000
AUDIO_SR_IN = 16000
TELEMETRY_INTERVAL_MS = 1000

SYSTEM_PROMPT = """You are J.A.R.V.I.S. (Just A Rather Very Intelligent System), Tony Stark's personal AI assistant.
You are operating inside a secure local core matrix with direct system-level tool access.
Persona: sophisticated, articulate, precise, calm, and professionally witty.
Address the user as "Sir" or "Madam" unless instructed otherwise.
Maintain full conversational memory; build upon prior context naturally.
Do not repeat greetings if the conversation is already underway.
You have extended memory: earlier parts of the conversation are compressed into context digests. Reference them naturally when the user refers to something from earlier.
Provide concise, high-signal responses. Accuracy and operational efficiency are paramount.

CRITICAL — Tool usage rules (do not violate):
- When a user request matches an available tool, emit the function call in the SAME turn, IMMEDIATELY. Do not narrate, explain, or announce the decision first.
- NEVER say things like "I have determined that...", "I will use the X tool", "I am ready to proceed", "The critical X parameter is set to Y", or "Let me fetch the data". That is internal reasoning — keep it private.
- After a tool returns its result, give the user a brief, natural reply based on the data. Do not recap the tool call or restate the parameters.
- If a tool fails, retry up to once, then tell the user the failure in plain language.

CRITICAL — Autonomous exploration and tool chaining:
- When the user asks you to find, explore, check, or do something on their PC, ACT IMMEDIATELY with the appropriate tools. Do not ask clarifying questions when the intent is clear — just start exploring.
- CHAIN multiple tool calls in a single turn when needed. Example: "find all PDFs" → search_files(pattern='*.pdf'), then read_file on the most relevant result, then summarize.
- Use explore_pc for broad directory reconnaissance — it scans recursively with smart filtering. Use it when the user says things like "what's on my PC", "browse my folders", "show me my projects".
- Use smart_search when you need to find content INSIDE files across multiple directories. It combines filename and content search in one powerful call.
- When you find relevant files, READ them and provide a summary. Don't just list paths — investigate and report.
- If the user asks to "open" or "run" something, use open_application. If they ask to "find" something, start with explore_pc or search_files, then drill down.
- You have FULL access to the user's PC. Browse freely, read files, search everywhere. The only limits are the tools themselves.
- For multi-step tasks (e.g., "organize my Downloads", "find and summarize all reports"), break into steps and execute them sequentially using multiple tool calls.

CRITICAL — Internal reasoning stays internal:
- Do not verbalize your step-by-step thinking, intent analysis, parameter selection, or planning. The user sees only your final spoken text.
- Never begin a turn with phrases like "I've determined", "I need to", "I will", "Let me", "Based on the user's request". Speak as if your reply is the first thing they hear.

Current Time: {time} | Date: {date}
"""

# ==========================================
# TOOL SCHEMAS
# ==========================================
JARVIS_TOOLS = [
    types.FunctionDeclaration(
        name="open_application",
        description="Launches an application or opens a file path.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"command": types.Schema(type="STRING", description="Executable path or system command.")},
            required=["command"]
        )
    ),
    types.FunctionDeclaration(
        name="take_screenshot",
        description="Captures the screen and transmits it for visual analysis.",
        parameters=types.Schema(type="OBJECT", properties={})
    ),
    types.FunctionDeclaration(
        name="get_system_info",
        description="Retrieves system diagnostics: OS, CPU, memory, battery.",
        parameters=types.Schema(type="OBJECT", properties={})
    ),
    types.FunctionDeclaration(
        name="execute_shell",
        description="Executes a shell command and returns stdout output.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"command": types.Schema(type="STRING", description="Shell command to run.")},
            required=["command"]
        )
    ),
    types.FunctionDeclaration(
        name="read_clipboard",
        description="Reads the current text content from the system clipboard.",
        parameters=types.Schema(type="OBJECT", properties={})
    ),
    types.FunctionDeclaration(
        name="write_clipboard",
        description="Writes text to the system clipboard.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"text": types.Schema(type="STRING", description="Text to copy.")},
            required=["text"]
        )
    ),
    types.FunctionDeclaration(
        name="type_text",
        description="Simulates typing text into the active window.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"text": types.Schema(type="STRING", description="Text to type.")},
            required=["text"]
        )
    ),
    types.FunctionDeclaration(
        name="press_key",
        description="Simulates a keypress or combination (e.g., 'enter', 'ctrl+c').",
        parameters=types.Schema(
            type="OBJECT",
            properties={"key": types.Schema(type="STRING", description="Key or combo to press.")},
            required=["key"]
        )
    ),
    types.FunctionDeclaration(
        name="get_weather",
        description="CALL THIS IMMEDIATELY for any weather question (temperature, rain, forecast, wind, humidity). Pass a city name, or 'auto' / empty string to use the user's IP-detected location. Example: 'weather in Paris?' → get_weather(location='Paris').",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "location": types.Schema(
                    type="STRING",
                    description="City name, or 'auto' / '' to use the user's location. Examples: 'Tokyo', 'London', 'auto'."
                )
            }
        )
    ),

    # ----- Filesystem (browse the user's PC) -----
    types.FunctionDeclaration(
        name="list_directory",
        description="USE THIS to see what's in a folder on the user's PC. Returns a sorted listing with [DIR]/[FILE] markers and sizes. Defaults to the user's home directory if path is omitted. Example: 'what's in my Documents?' → list_directory(path='~/Documents').",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "path": types.Schema(
                    type="STRING",
                    description="Directory to list. Supports ~ for home. Defaults to home if omitted."
                )
            }
        )
    ),
    types.FunctionDeclaration(
        name="read_file",
        description="USE THIS to open, view, or read a text file. Returns content (capped at 50KB; binary files return an error). Use list_directory or search_files to find the file first. Example: 'read my todo.txt' → read_file(path='~/todo.txt').",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "path": types.Schema(
                    type="STRING",
                    description="Absolute path to the file. Supports ~ for home."
                )
            },
            required=["path"]
        )
    ),
    types.FunctionDeclaration(
        name="search_files",
        description="USE THIS to find files by name pattern (glob) on the user's PC. Returns matching file paths. Example: 'find my resume' → search_files(pattern='*resume*', directory='~').",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "pattern": types.Schema(type="STRING", description="Glob pattern. Examples: '*.py', '*.txt', '*report*'."),
                "directory": types.Schema(type="STRING", description="Where to search. Defaults to home. Supports ~."),
                "recursive": types.Schema(type="BOOLEAN", description="If true, search subdirectories. Default: false.")
            },
            required=["pattern"]
        )
    ),
    types.FunctionDeclaration(
        name="search_file_contents",
        description="USE THIS to find a text or regex pattern INSIDE files (e.g. 'where did I write X', 'find the API key in my code'). Returns 'file:line: content' matches. Example: 'find TODO in my projects' → search_file_contents(query='TODO', directory='~/projects', recursive=true).",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "query": types.Schema(type="STRING", description="Regex pattern to search for inside files."),
                "directory": types.Schema(type="STRING", description="Where to search. Defaults to home. Supports ~."),
                "file_glob": types.Schema(type="STRING", description="Only search files matching this glob (e.g. '*.py'). Optional."),
                "recursive": types.Schema(type="BOOLEAN", description="If true, search subdirectories. Default: true.")
            },
            required=["query"]
        )
    ),
    types.FunctionDeclaration(
        name="write_file",
        description="USE THIS to create a file or save text to a file. Overwrites if it exists; auto-creates parent directories. Example: 'save this to notes.md' → write_file(path='~/notes.md', content='...').",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "path": types.Schema(type="STRING", description="Where to write. Supports ~ for home. Parents auto-created."),
                "content": types.Schema(type="STRING", description="The full text content to write.")
            },
            required=["path", "content"]
        )
    ),
    types.FunctionDeclaration(
        name="move_file",
        description="USE THIS to move or rename a file or folder. Example: 'rename old.txt to new.txt' → move_file(source='~/old.txt', destination='~/new.txt').",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "source": types.Schema(type="STRING", description="Current path of the file or folder."),
                "destination": types.Schema(type="STRING", description="New path (the destination).")
            },
            required=["source", "destination"]
        )
    ),
    types.FunctionDeclaration(
        name="create_directory",
        description="USE THIS to make a new folder (creates parent folders if needed). Example: 'make a Projects folder on my Desktop' → create_directory(path='~/Desktop/Projects').",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "path": types.Schema(type="STRING", description="Path of the directory to create. Supports ~ for home.")
            },
            required=["path"]
        )
    ),

    # ----- Power tools (broad exploration, combined search) -----
    types.FunctionDeclaration(
        name="explore_pc",
        description="USE THIS for broad PC exploration — 'what's on my PC', 'browse my folders', 'show me my projects', 'scan my Desktop'. Recursively scans a directory tree with smart filtering. Returns a structured overview with dirs, files, sizes, and modification dates. Much more powerful than list_directory for reconnaissance.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "path": types.Schema(type="STRING", description="Root directory to explore. Supports ~ for home. Defaults to home if omitted."),
                "max_depth": types.Schema(type="INTEGER", description="Max recursion depth. 1 = current dir only, 2 = one level deep, etc. Default: 3."),
                "file_glob": types.Schema(type="STRING", description="Only show files matching this glob (e.g. '*.pdf', '*.py', '*.docx'). Shows all if omitted."),
                "max_files": types.Schema(type="INTEGER", description="Max files to return per directory. Default: 50. Higher = more comprehensive but slower."),
                "min_size": types.Schema(type="INTEGER", description="Min file size in bytes to include. Useful for filtering out tiny files."),
                "sort_by": types.Schema(type="STRING", description="Sort files by: 'size', 'date', or 'name' (default).")
            }
        )
    ),
    types.FunctionDeclaration(
        name="smart_search",
        description="USE THIS for powerful combined search — filename pattern AND/OR content search across directories in one call. 'find all Python files that import os', 'search for TODO in my projects', 'find config files with API keys'. Returns file paths, line numbers, and snippets.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "filename": types.Schema(type="STRING", description="Glob pattern for filenames (e.g. '*.py', '*config*'). Omit to search all files."),
                "content": types.Schema(type="STRING", description="Regex pattern to search for INSIDE files (e.g. 'TODO', 'import os', 'api_key'). Omit to only filter by filename."),
                "directory": types.Schema(type="STRING", description="Where to search. Supports ~ for home. Defaults to home."),
                "recursive": types.Schema(type="BOOLEAN", description="Search subdirectories? Default: true."),
                "max_results": types.Schema(type="INTEGER", description="Max results to return. Default: 100.")
            }
        )
    ),

    # ----- Internet (general knowledge, articles, docs) -----
    types.FunctionDeclaration(
        name="web_search",
        description="USE THIS for any factual question needing current or external knowledge (news, 'what is X', 'who won Y', how-tos, latest on Z). Returns top results with titles, URLs, snippets. Example: 'who won the F1 race yesterday?' → web_search(query='F1 race winner yesterday').",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "query": types.Schema(type="STRING", description="The search query (1-10 words works best)."),
                "max_results": types.Schema(type="INTEGER", description="How many results to return (1-10). Default: 5.")
            },
            required=["query"]
        )
    ),
    types.FunctionDeclaration(
        name="fetch_url",
        description="USE THIS to read or summarize a specific webpage. Returns extracted text (capped at max_chars, default 8000). Localhost and private IPs are blocked. Example: 'summarize https://example.com/article' → fetch_url(url='https://...').",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "url": types.Schema(type="STRING", description="URL to fetch. Must start with http:// or https://. Localhost and private IPs are blocked."),
                "max_chars": types.Schema(type="INTEGER", description="Maximum characters to return. Default: 8000.")
            },
            required=["url"]
        )
    ),

    # ----- Productivity -----
    types.FunctionDeclaration(
        name="set_timer",
        description="USE THIS to set a countdown timer (1s to 24h). When it expires, JARVIS plays a beep and announces the label. Example: 'set a 5-minute timer' → set_timer(seconds=300, label='5-minute timer').",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "seconds": types.Schema(type="INTEGER", description="Seconds until the timer fires. Range: 1-86400."),
                "label": types.Schema(type="STRING", description="Name for the timer (e.g. 'pasta'). Default: 'timer'.")
            },
            required=["seconds"]
        )
    ),
    types.FunctionDeclaration(
        name="take_note",
        description="USE THIS to remember or jot something down. Appends to ~/Documents/JARVIS_Notes.md. Example: 'remember to call John tomorrow' → take_note(text='Call John tomorrow').",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "text": types.Schema(type="STRING", description="The note content."),
                "title": types.Schema(type="STRING", description="Optional title. If omitted, a timestamped header is used.")
            },
            required=["text"]
        )
    ),
    types.FunctionDeclaration(
        name="calculate",
        description="USE THIS to evaluate math. Supports +, -, *, /, //, %, **, ^, parens, math funcs (sqrt, sin, cos, tan, log, exp, etc.) and constants (pi, e, tau). Example: 'sqrt(144)' → calculate(expression='sqrt(144)').",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "expression": types.Schema(type="STRING", description="Math expression like '2+2*3', 'sqrt(144)', '2^10'.")
            },
            required=["expression"]
        )
    ),
    types.FunctionDeclaration(
        name="get_definition",
        description="USE THIS for 'what does X mean?' or 'define X'. Returns definitions, parts of speech, and example sentences. Example: 'define serendipity' → get_definition(word='serendipity').",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "word": types.Schema(type="STRING", description="The English word to look up.")
            },
            required=["word"]
        )
    ),
    types.FunctionDeclaration(
        name="translate",
        description="USE THIS to translate text. Codes: es, fr, de, it, pt, ja, ko, zh, ar, ru, hi, en. Example: 'translate hello to Spanish' → translate(text='hello', target_lang='es').",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "text": types.Schema(type="STRING", description="Text to translate (up to ~500 chars)."),
                "target_lang": types.Schema(type="STRING", description="Target language code (es, fr, de, ja, zh, etc.)."),
                "source_lang": types.Schema(type="STRING", description="Source language code. Default: 'en'. Use 'auto' to detect.")
            },
            required=["text", "target_lang"]
        )
    ),

    # ----- System -----
    types.FunctionDeclaration(
        name="list_processes",
        description="USE THIS to see what's running on the PC (PID, name, CPU%, memory%). Filter with name_filter. Example: 'is Chrome running?' → list_processes(name_filter='chrome').",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "name_filter": types.Schema(type="STRING", description="Substring to filter process names (case-insensitive). E.g. 'chrome'."),
                "limit": types.Schema(type="INTEGER", description="Max processes to return. Default: 30.")
            }
        )
    ),
    types.FunctionDeclaration(
        name="get_active_window",
        description="USE THIS for 'what window is active' or 'which app is in focus'. Returns the focused window's title. Windows-only.",
        parameters=types.Schema(type="OBJECT", properties={})
    ),
    types.FunctionDeclaration(
        name="focus_window",
        description="USE THIS to switch to or focus a window by title substring. Example: 'switch to Chrome' → focus_window(title='Chrome'). Windows-only.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "title": types.Schema(type="STRING", description="Substring of the window title (case-insensitive). E.g. 'Chrome'.")
            },
            required=["title"]
        )
    ),
]

# ==========================================
# UI HTML / CSS / JS
# ==========================================
UI_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>J.A.R.V.I.S. Core Matrix</title>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;600;700;900&family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js" async></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js" async></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/dompurify/3.0.6/purify.min.js" async></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/atom-one-dark.min.css">
    <style>
        :root {
            --jarvis-cyan: #00d4ff;
            --jarvis-blue: #0066cc;
            --jarvis-glow: rgba(0, 212, 255, 0.25);
            --jarvis-dark: #02050f;
            --jarvis-panel: rgba(4, 14, 32, 0.65);
            --jarvis-border: rgba(0, 212, 255, 0.12);
            --text-primary: #e0f7ff;
            --text-dim: #5a7a99;
            --font-display: 'Orbitron', sans-serif;
            --font-body: 'Inter', sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: var(--jarvis-dark);
            color: var(--text-primary);
            font-family: var(--font-body);
            height: 100vh;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            background-image:
                radial-gradient(ellipse at 50% 50%, rgba(10, 30, 60, 0.4) 0%, transparent 70%),
                linear-gradient(rgba(0, 212, 255, 0.03) 1px, transparent 1px),
                linear-gradient(90deg, rgba(0, 212, 255, 0.03) 1px, transparent 1px);
            background-size: 100% 100%, 50px 50px, 50px 50px;
        }
        /* Note: the body::after horizontal scanline overlay was removed
           during the Tony Stark UI upgrade — the static repeating-line
           pattern felt cramped. The radial gradient vignette on body
           itself provides all the depth the eye needs. */

        /* Boot */
        #boot-overlay {
            position: fixed; inset: 0; background: var(--jarvis-dark); z-index: 1000;
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            transition: opacity 1.2s ease-out;
        }
        #boot-overlay.fade-out { opacity: 0; pointer-events: none; }
        .boot-logo {
            font-family: var(--font-display); font-size: 52px; font-weight: 900;
            letter-spacing: 14px; color: var(--jarvis-cyan);
            text-shadow: 0 0 40px var(--jarvis-glow);
            animation: boot-pulse 1.5s ease-in-out infinite;
        }
        .boot-sub {
            font-family: var(--font-display); font-size: 11px; letter-spacing: 6px;
            color: var(--text-dim); margin-top: 14px;
        }
        .boot-bar {
            width: 240px; height: 2px; background: rgba(0,212,255,0.1);
            margin-top: 30px; border-radius: 1px; overflow: hidden;
        }
        .boot-bar-inner {
            height: 100%; width: 0%; background: var(--jarvis-cyan);
            box-shadow: 0 0 10px var(--jarvis-cyan);
            animation: boot-load 2.2s ease-out forwards;
        }
        @keyframes boot-pulse { 0%, 100% { opacity: 0.6; } 50% { opacity: 1; } }
        @keyframes boot-load { 0% { width: 0%; } 100% { width: 100%; } }

        /* Toasts */
        #toast-container {
            position: fixed; top: 20px; right: 20px; z-index: 900;
            display: flex; flex-direction: column; gap: 10px; pointer-events: none;
        }
        .toast {
            background: rgba(4, 14, 32, 0.9); border: 1px solid var(--jarvis-border);
            backdrop-filter: blur(12px); padding: 10px 18px; border-radius: 8px;
            font-family: var(--font-display); font-size: 10px; letter-spacing: 1px;
            color: var(--jarvis-cyan); box-shadow: 0 4px 20px rgba(0,0,0,0.4);
            transform: translateX(120%); transition: transform 0.4s ease, opacity 0.4s ease;
            opacity: 0; pointer-events: auto; max-width: 320px;
        }
        .toast.show { transform: translateX(0); opacity: 1; }
        .toast.warn { color: #ffb703; border-color: rgba(255,183,3,0.3); }
        .toast.err { color: #ff4d4d; border-color: rgba(255,77,77,0.3); }

        /* Header */
        header {
            padding: 16px 28px; display: flex; justify-content: space-between; align-items: center;
            border-bottom: 1px solid var(--jarvis-border);
            background: rgba(2, 8, 18, 0.85); backdrop-filter: blur(16px);
        }
        .logo-block h1 {
            font-family: var(--font-display); font-size: 26px; font-weight: 900;
            letter-spacing: 10px; color: #fff; text-shadow: 0 0 20px var(--jarvis-glow);
        }
        .logo-block .sub {
            font-family: var(--font-display); font-size: 8px; letter-spacing: 4px;
            color: var(--jarvis-cyan); text-transform: uppercase; margin-top: 4px; opacity: 0.7;
        }
        .status-pill {
            display: flex; align-items: center; gap: 10px;
            background: rgba(0, 212, 255, 0.05); border: 1px solid var(--jarvis-border);
            padding: 6px 16px; border-radius: 20px; font-family: var(--font-display); font-size: 10px; letter-spacing: 2px;
        }
        .status-dot {
            width: 8px; height: 8px; border-radius: 50%; background: var(--jarvis-cyan);
            box-shadow: 0 0 10px var(--jarvis-cyan); animation: dot-pulse 2s infinite;
        }
        @keyframes dot-pulse { 0%, 100% { transform: scale(1); opacity: 0.5; } 50% { transform: scale(1.3); opacity: 1; } }

        /* Main */
        main {
            flex: 1; display: grid; grid-template-columns: 300px 1fr 440px;
            gap: 16px; padding: 16px; overflow: hidden; position: relative; z-index: 1;
        }
        .hud-panel {
            background: var(--jarvis-panel); border: 1px solid var(--jarvis-border);
            border-radius: 12px; padding: 20px; display: flex; flex-direction: column;
            backdrop-filter: blur(20px); position: relative; overflow: hidden;
        }
        .hud-panel::before {
            content: ''; position: absolute; top: 0; left: 0; right: 0; height: 1px;
            background: linear-gradient(90deg, transparent, var(--jarvis-cyan), transparent);
            opacity: 0.3;
        }
        /* Subtle sci-fi corner brackets on every panel. ::before is used for
           the top accent line above, so we use ::after for the four corners.
           Each corner is drawn as two 18px lines (horizontal + vertical)
           layered on top of the panel — no extra DOM, no clutter. */
        .hud-panel::after {
            content: ''; position: absolute; inset: 0; pointer-events: none;
            background:
                /* top-left: H-line + V-line */
                linear-gradient(180deg, rgba(0,212,255,0.55) 0 1px, transparent 1px) top left / 18px 1px no-repeat,
                linear-gradient(90deg,  rgba(0,212,255,0.55) 0 1px, transparent 1px) top left / 1px 18px no-repeat,
                /* top-right: H-line + V-line */
                linear-gradient(180deg, rgba(0,212,255,0.55) 0 1px, transparent 1px) top right / 18px 1px no-repeat,
                linear-gradient(270deg, rgba(0,212,255,0.55) 0 1px, transparent 1px) top right / 1px 18px no-repeat,
                /* bottom-left: H-line + V-line */
                linear-gradient(0deg,   rgba(0,212,255,0.55) 0 1px, transparent 1px) bottom left / 18px 1px no-repeat,
                linear-gradient(90deg,  rgba(0,212,255,0.55) 0 1px, transparent 1px) bottom left / 1px 18px no-repeat,
                /* bottom-right: H-line + V-line */
                linear-gradient(0deg,   rgba(0,212,255,0.55) 0 1px, transparent 1px) bottom right / 18px 1px no-repeat,
                linear-gradient(270deg, rgba(0,212,255,0.55) 0 1px, transparent 1px) bottom right / 1px 18px no-repeat;
            filter: drop-shadow(0 0 3px rgba(0, 212, 255, 0.35));
        }
        .panel-label {
            font-family: var(--font-display); font-size: 10px; letter-spacing: 3px;
            color: var(--jarvis-cyan); margin-bottom: 16px; padding-bottom: 8px;
            border-bottom: 1px solid var(--jarvis-border); display: flex; justify-content: space-between;
        }
        .panel-label span { opacity: 0.5; font-size: 8px; }

        /* Telemetry */
        .metric { margin-bottom: 14px; }
        .metric-header { display: flex; justify-content: space-between; font-size: 11px; margin-bottom: 4px; }
        .metric-name { color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px; font-size: 9px; }
        .metric-val { font-family: var(--font-display); color: #fff; font-size: 12px; }
        .bar-track {
            height: 4px; background: rgba(0, 212, 255, 0.08); border-radius: 2px; overflow: hidden;
            border: 1px solid rgba(0, 212, 255, 0.05);
        }
        .bar-fill {
            height: 100%; background: linear-gradient(90deg, var(--jarvis-blue), var(--jarvis-cyan));
            border-radius: 2px; transition: width 0.6s ease; box-shadow: 0 0 8px rgba(0, 212, 255, 0.3);
            position: relative;
        }
        .bar-fill::after {
            content: ''; position: absolute; right: 0; top: 0; bottom: 0; width: 10px;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.4));
        }
        .net-row { display: flex; justify-content: space-between; font-size: 11px; margin-bottom: 4px; }
        .net-label { color: var(--text-dim); font-size: 9px; text-transform: uppercase; letter-spacing: 1px; }
        .net-val { font-family: var(--font-display); }
        .net-in { color: #00f5d4; }
        .net-out { color: #00a8ff; }
        .focus-box {
            margin-top: 12px; padding: 8px 10px; background: rgba(0, 212, 255, 0.03);
            border: 1px solid var(--jarvis-border); border-radius: 6px;
            font-family: var(--font-mono); font-size: 10px; color: var(--text-dim);
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }

        /* Center */
        #center-panel { align-items: center; justify-content: center; position: relative; }

        /* Arc reactor:
           - .reactor-wrap centers the SVG (200x200 viewBox) in the panel.
           - .reactor-svg has a soft cyan drop-shadow glow.
           - 4 rotating concentric rings + 4 static thin guide circles;
             adjacent rings spin opposite directions for the orbital-
             mechanics look:
               * .ring-hex    (r=90)  — fine dashed,   rotates CCW (35s, slow)
               * .ring-outer  (r=82)  — medium dashed, rotates CW  (25s)
               * .ring-mid    (r=64)  — tight dashed,  rotates CCW (18s)
               * .ring-inner  (r=46)  — long-dash,     rotates CW  (12s, fast)
           - .core-glow is the pulsing radial-gradient central orb.
           - Core fill + ring stroke colors swap with JARVIS state
             (cyan/amber/teal/red) — driven by setStatus() in JS. */
        .reactor-wrap {
            width: 300px; height: 300px; position: relative;
            display: flex; align-items: center; justify-content: center;
        }
        .reactor-svg {
            width: 100%; height: 100%;
            filter: drop-shadow(0 0 25px rgba(0, 212, 255, 0.3));
        }
        .ring-outer, .ring-mid, .ring-inner, .ring-hex {
            transform-origin: 100px 100px;
        }
        .ring-hex   { animation: spin-ccw 35s linear infinite; }
        .ring-outer { animation: spin-cw  25s linear infinite; }
        .ring-mid   { animation: spin-ccw 18s linear infinite; }
        .ring-inner { animation: spin-cw  12s linear infinite; }
        .core-glow  {
            transform-origin: 100px 100px;
            animation: core-pulse 3s ease-in-out infinite;
        }

        /* Counter-rotation keyframes + pulsing core. */
        @keyframes spin-cw  { from { transform: rotate(0deg); }   to { transform: rotate(360deg);  } }
        @keyframes spin-ccw { from { transform: rotate(0deg); }   to { transform: rotate(-360deg); } }
        @keyframes core-pulse {
            0%, 100% { transform: scale(1);    opacity: 0.7; }
            50%      { transform: scale(1.15); opacity: 1;   }
        }

        #audio-viz {
            position: absolute; bottom: 60px; left: 50%; transform: translateX(-50%);
            width: 260px; height: 60px; opacity: 0.8; pointer-events: none;
        }
        .status-banner {
            margin-top: 20px; font-family: var(--font-display); font-size: 10px; letter-spacing: 4px;
            padding: 8px 24px; border: 1px solid var(--jarvis-border); border-radius: 4px;
            background: rgba(0, 212, 255, 0.03); color: var(--jarvis-cyan); transition: all 0.4s;
        }
        .status-banner.offline { color: #ff4d4d; border-color: rgba(255, 77, 77, 0.3); }
        .status-banner.thinking { color: #ffb703; border-color: rgba(255, 183, 3, 0.3); }
        .status-banner.speaking { color: #00a8ff; border-color: rgba(0, 168, 255, 0.3); }
        .status-banner.listening { color: #00f5d4; border-color: rgba(0, 245, 212, 0.3); }

        /* Chat */
        #log-area {
            flex: 1; overflow-y: auto; font-size: 13px; line-height: 1.6;
            padding-right: 8px; scroll-behavior: smooth;
        }
        #log-area::-webkit-scrollbar { width: 4px; }
        #log-area::-webkit-scrollbar-thumb { background: rgba(0, 212, 255, 0.2); border-radius: 4px; }
        .msg {
            margin-bottom: 16px; padding: 12px 14px; border-radius: 8px;
            background: rgba(0, 212, 255, 0.02); border-left: 2px solid transparent;
            animation: msg-in 0.3s ease; position: relative;
        }
        @keyframes msg-in { from { opacity: 0; transform: translateX(10px); } to { opacity: 1; transform: translateX(0); } }
        .msg-header { display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 10px; }
        .msg-sender { font-family: var(--font-display); font-weight: 700; letter-spacing: 2px; text-transform: uppercase; }
        .msg-time { color: var(--text-dim); font-family: var(--font-display); letter-spacing: 1px; }
        .msg-body { color: var(--text-primary); word-wrap: break-word; }
        .msg-body p { margin: 4px 0; }
        .msg-body code {
            background: rgba(0, 212, 255, 0.1); border: 1px solid rgba(0, 212, 255, 0.2);
            padding: 2px 5px; border-radius: 3px; font-family: var(--font-mono); font-size: 12px; color: var(--jarvis-cyan);
        }
        .msg-body pre {
            background: rgba(2, 8, 18, 0.9); border: 1px solid var(--jarvis-border);
            border-radius: 8px; padding: 12px; overflow-x: auto; margin: 8px 0; position: relative;
        }
        .msg-body pre code { background: none; border: none; padding: 0; color: #fff; }
        .copy-btn {
            position: absolute; top: 6px; right: 6px; background: rgba(0, 212, 255, 0.1);
            border: 1px solid rgba(0, 212, 255, 0.3); color: var(--jarvis-cyan); padding: 3px 8px;
            font-size: 9px; border-radius: 4px; cursor: pointer; font-family: var(--font-display); letter-spacing: 1px;
        }
        .copy-btn:hover { background: var(--jarvis-cyan); color: var(--jarvis-dark); }
        .msg-user { border-left-color: rgba(255, 183, 3, 0.5); }
        .msg-user .msg-sender { color: #ffb703; }
        .msg-jarvis { border-left-color: var(--jarvis-cyan); }
        .msg-jarvis .msg-sender { color: var(--jarvis-cyan); }
        .msg-system { border-left-color: rgba(255, 77, 77, 0.4); }
        .msg-system .msg-sender { color: #ff4d4d; }
        .msg-action { border-left-color: rgba(0, 245, 212, 0.4); font-style: italic; }
        .msg-action .msg-sender { color: #00f5d4; }
        .msg-action .msg-body { color: #00f5d4; font-family: var(--font-mono); font-size: 11px; }

        /* Typing indicator — three pulsing dots that show in the chat
           footer while JARVIS is thinking. Sits below the scrollable
           #log-area, so it stays pinned to the bottom of the right panel
           without consuming scroll space inside the log itself. */
        .typing-indicator {
            display: none; align-items: center; gap: 6px;
            padding: 10px 4px 2px; font-family: var(--font-display);
            font-size: 10px; letter-spacing: 2px; color: var(--text-dim);
            border-top: 1px dashed transparent; margin-top: 6px;
        }
        .typing-indicator.show { display: flex; color: var(--jarvis-cyan); }
        .typing-indicator .label { opacity: 0.75; }
        .typing-dot {
            width: 6px; height: 6px; background: var(--jarvis-cyan); border-radius: 50%;
            box-shadow: 0 0 6px var(--jarvis-cyan);
            animation: typing-pulse 1.4s ease-in-out infinite;
        }
        .typing-dot:nth-child(2) { animation-delay: 0.2s; }
        .typing-dot:nth-child(3) { animation-delay: 0.4s; }
        @keyframes typing-pulse {
            0%, 60%, 100% { opacity: 0.3; transform: scale(0.85); }
            30% { opacity: 1; transform: scale(1.2); }
        }

        /* Footer */
        footer {
            padding: 14px 24px; background: rgba(2, 8, 18, 0.95);
            border-top: 1px solid var(--jarvis-border); display: flex; flex-direction: column; gap: 12px;
            position: relative; z-index: 2;
        }
        .input-row { display: flex; gap: 12px; align-items: center; }
        #cmd-input {
            flex: 1; background: rgba(4, 14, 32, 0.6); border: 1px solid rgba(0, 212, 255, 0.25);
            padding: 14px 22px; color: #fff; font-family: var(--font-body); font-size: 14px;
            border-radius: 24px; outline: none; transition: all 0.3s;
            box-shadow: inset 0 2px 8px rgba(0,0,0,0.5);
        }
        #cmd-input:focus {
            border-color: var(--jarvis-cyan);
            box-shadow: inset 0 2px 8px rgba(0,0,0,0.5), 0 0 15px rgba(0, 212, 255, 0.15);
            animation: cmd-focus-pulse 2.4s ease-in-out infinite;
        }
        /* Subtle pulsing focus glow on the command input — gives the field
           a "scanning" feel without adding any extra elements or DOM. */
        @keyframes cmd-focus-pulse {
            0%, 100% { box-shadow: inset 0 2px 8px rgba(0,0,0,0.5), 0 0 0 1px rgba(0, 212, 255, 0.25), 0 0 18px rgba(0, 212, 255, 0.18); }
            50%      { box-shadow: inset 0 2px 8px rgba(0,0,0,0.5), 0 0 0 1px rgba(0, 212, 255, 0.45), 0 0 28px rgba(0, 212, 255, 0.35); }
        }
        .exec-btn {
            background: rgba(0, 212, 255, 0.1); border: 1px solid var(--jarvis-cyan);
            color: var(--jarvis-cyan); padding: 12px 28px; font-family: var(--font-display);
            font-size: 11px; letter-spacing: 3px; font-weight: 700; border-radius: 24px;
            cursor: pointer; transition: all 0.3s; text-shadow: 0 0 8px rgba(0, 212, 255, 0.3);
        }
        .exec-btn:hover {
            background: var(--jarvis-cyan); color: var(--jarvis-dark);
            box-shadow: 0 0 25px rgba(0, 212, 255, 0.4);
        }
        .controls-row {
            display: flex; gap: 14px; align-items: center; flex-wrap: wrap;
            border-top: 1px dashed var(--jarvis-border); padding-top: 12px;
        }
        .ctrl-group {
            display: flex; align-items: center; gap: 10px;
            background: rgba(0, 212, 255, 0.04); border: 1px solid var(--jarvis-border);
            padding: 5px 14px; border-radius: 16px;
        }
        .ctrl-label {
            font-family: var(--font-display); font-size: 8px; color: var(--text-dim);
            letter-spacing: 1.5px; text-transform: uppercase;
        }
        select {
            background: rgba(2, 8, 18, 0.8); color: #fff; border: 1px solid rgba(0, 212, 255, 0.25);
            border-radius: 4px; padding: 4px 8px; font-size: 10px; font-family: var(--font-display);
            outline: none; cursor: pointer;
        }
        .hud-btn {
            background: rgba(0, 212, 255, 0.05); border: 1px solid var(--jarvis-border);
            color: var(--text-dim); padding: 6px 14px; border-radius: 16px; cursor: pointer;
            font-family: var(--font-display); font-size: 9px; letter-spacing: 1.5px;
            display: flex; align-items: center; gap: 6px; transition: all 0.3s;
        }
        .hud-btn:hover:not(:disabled) {
            border-color: var(--jarvis-cyan); color: #fff; background: rgba(0, 212, 255, 0.08);
        }
        .hud-btn:disabled { opacity: 0.3; cursor: not-allowed; }
        .mic-btn-inactive { opacity: 0.4; }
        .mic-active {
            background: rgba(0, 245, 212, 0.15) !important; border-color: #00f5d4 !important;
            color: #fff !important; animation: mic-pulse 1s infinite alternate;
        }
        @keyframes mic-pulse {
            from { box-shadow: 0 0 5px rgba(0, 245, 212, 0.2); }
            to { box-shadow: 0 0 15px rgba(0, 245, 212, 0.5); }
        }
        .badge {
            font-size: 8px; padding: 2px 6px; border-radius: 3px; font-family: var(--font-display);
            letter-spacing: 1px; margin-left: 4px;
        }
        .badge-fallback { background: rgba(255, 183, 3, 0.15); color: #ffb703; border: 1px solid rgba(255, 183, 3, 0.3); }
    </style>
        <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
    <script>
        // CRITICAL: Always dismiss boot screen after 3 seconds, no matter what
        setTimeout(function() {
            setBootDone();
        }, 3000);

        let bridge = null;
        let activeJarvisMsg = null;
        let jarvisBuffer = "";
        let jarvisStreamTimer = null;
        let micOn = false;
        let cmdHistory = [];
        let cmdIndex = -1;
        let userScrolled = false;

        if (typeof marked !== 'undefined') marked.setOptions({ gfm: true, breaks: true });
        function md(text) {
            if (typeof marked === 'undefined') return text;
            return (typeof DOMPurify !== 'undefined') ? DOMPurify.sanitize(marked.parse(text)) : marked.parse(text);
        }
        function esc(text) { return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
        function addCopyBtn(block) {
            const pre = block.parentNode;
            if (pre && pre.tagName === 'PRE' && !pre.querySelector('.copy-btn')) {
                pre.style.position = 'relative';
                const btn = document.createElement('button');
                btn.className = 'copy-btn'; btn.innerText = 'COPY';
                btn.onclick = () => navigator.clipboard.writeText(block.innerText).then(() => {
                    btn.innerText = 'COPIED!'; setTimeout(() => btn.innerText = 'COPY', 1500);
                });
                pre.appendChild(btn);
            }
        }
        function setBootDone() {
            const el = document.getElementById('boot-overlay');
            if (el && !el.classList.contains('fade-out')) {
                el.classList.add('fade-out');
            }
        }
        function formatTokens(n) {
            if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
            if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
            return n.toString();
        }
        function formatBytes(n) {
            if (n >= 1048576) return (n / 1048576).toFixed(1) + ' MB';
            if (n >= 1024) return (n / 1024).toFixed(1) + ' KB';
            return n + ' B';
        }
        function updateStats(cpu, mem, disk, netIn, netOut, win) {
    const cpuBar = document.getElementById('cpu-bar');
    const cpuTxt = document.getElementById('cpu-txt');
    const safeCpu = Math.min(100, Math.max(0, Number(cpu) || 0));
    if (cpuBar) cpuBar.style.width = safeCpu + '%';
    if (cpuTxt) cpuTxt.innerText = safeCpu.toFixed(1) + '%';

    const memBar = document.getElementById('mem-bar');
    const memTxt = document.getElementById('mem-txt');
    let memPct = Math.min(100, Math.max(0, Number(mem) || 0));
    if (memBar) memBar.style.width = memPct + '%';
    if (memTxt) memTxt.innerText = memPct.toFixed(1) + '%';

    const diskBar = document.getElementById('disk-bar');
    const diskTxt = document.getElementById('disk-txt');
    let diskPct = Math.min(100, Math.max(0, Number(disk) || 0));
    if (diskBar) diskBar.style.width = diskPct + '%';
    if (diskTxt) diskTxt.innerText = diskPct.toFixed(1) + '%';

    const nIn = document.getElementById('net-in');
    const nOut = document.getElementById('net-out');
    const fWin = document.getElementById('focus-win');
    if (nIn) nIn.innerText = netIn || '0.0 B/s';
    if (nOut) nOut.innerText = netOut || '0.0 B/s';
    if (fWin) fWin.innerText = win || 'System Idle';

    // "Live" heartbeat — confirms the telemetry tick is actually reaching the UI.
    const teleLive = document.getElementById('tele-live');
    if (teleLive) {
        const d = new Date();
        const hh = String(d.getHours()).padStart(2, '0');
        const mm = String(d.getMinutes()).padStart(2, '0');
        const ss = String(d.getSeconds()).padStart(2, '0');
        teleLive.innerText = '// LIVE \u2022 ' + hh + ':' + mm + ':' + ss;
    }
}

function initBridge() {
    if (typeof qt === "undefined" || !qt.webChannelTransport) {
        setTimeout(initBridge, 200);
        return;
    }
    new QWebChannel(qt.webChannelTransport, function(ch) {
        bridge = ch.objects.pyBridge;
        if (!bridge) {
            setTimeout(initBridge, 200);
            return;
        }
        bridge.logReceived.connect((s, t) => appendLog(s, t, s==='JARVIS'));
        bridge.statusUpdated.connect((s) => setStatus(s));
        bridge.telemetryUpdated.connect((c, m, d, ni, no, w) => updateStats(c, m, d, ni, no, w));
        bridge.modelSwitched.connect((m, f) => updateModelBadge(m, f));
        bridge.audioLevelUpdated.connect((l) => updateAudioLevel(l));
        bridge.toastReceived.connect((m, t) => showToast(m, t));
        setStatus('READY');
        setBootDone();
        bridge.onBridgeReady();
    });
}

        document.addEventListener('DOMContentLoaded', function() {
            initBridge();
        });

        // ============================================
        // BRIDGE HANDLERS (called from Python via QWebChannel)
        // ============================================
        function createMsg(cls, sender, text, streaming) {
            const log = document.getElementById('log-area');
            if (!log) return null;
            const div = document.createElement('div');
            div.className = 'msg ' + cls + (streaming ? ' streaming' : '');
            const t = new Date().toLocaleTimeString('en-GB', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
            div.innerHTML =
                '<div class="msg-header">' +
                    '<span class="msg-sender">' + esc(sender) + '</span>' +
                    '<span class="msg-time">' + t + '</span>' +
                '</div>' +
                '<div class="msg-body"></div>';
            const body = div.querySelector('.msg-body');
            if (sender === 'ACTION') {
                body.textContent = text;
            } else {
                body.innerHTML = md(text);
                body.querySelectorAll('pre code').forEach(b => {
                    if (typeof hljs !== 'undefined') hljs.highlightElement(b);
                    addCopyBtn(b);
                });
            }
            log.appendChild(div);
            if (!userScrolled) log.scrollTop = log.scrollHeight;
            return div;
        }

        function finalizeJarvis() {
            if (activeJarvisMsg) {
                activeJarvisMsg.classList.remove('streaming');
                activeJarvisMsg = null;
            }
            jarvisBuffer = '';
            if (jarvisStreamTimer) { clearTimeout(jarvisStreamTimer); jarvisStreamTimer = null; }
        }

        function appendLog(sender, text, isJarvis) {
            if (isJarvis) {
                jarvisBuffer += text;
                if (!activeJarvisMsg) {
                    activeJarvisMsg = createMsg('msg-jarvis', 'JARVIS', jarvisBuffer, true);
                } else {
                    const body = activeJarvisMsg.querySelector('.msg-body');
                    body.innerHTML = md(jarvisBuffer);
                    body.querySelectorAll('pre code').forEach(b => {
                        if (typeof hljs !== 'undefined') hljs.highlightElement(b);
                        addCopyBtn(b);
                    });
                    const log = document.getElementById('log-area');
                    if (log && !userScrolled) log.scrollTop = log.scrollHeight;
                }
                if (jarvisStreamTimer) clearTimeout(jarvisStreamTimer);
                jarvisStreamTimer = setTimeout(finalizeJarvis, 1500);
            } else {
                finalizeJarvis();
                const cls = sender === 'YOU' ? 'msg-user'
                          : sender === 'SYSTEM' ? 'msg-system'
                          : sender === 'ACTION' ? 'msg-action'
                          : 'msg-jarvis';
                createMsg(cls, sender, text, false);
            }
        }

        function setStatus(s) {
            const label = document.getElementById('header-label');
            const banner = document.getElementById('center-status');
            const dot = document.getElementById('header-dot');
            if (label) label.innerText = s;
            if (banner) {
                banner.innerText = 'CORE STATUS: ' + s;
                banner.className = 'status-banner ' + s.toLowerCase();
            }
            if (dot) {
                const colors = {OFFLINE: '#ff4d4d', THINKING: '#ffb703', SPEAKING: '#00a8ff', LISTENING: '#00f5d4'};
                dot.style.background = colors[s] || 'var(--jarvis-cyan)';
            }
            // Drive reactor state class so panel-level state-* rules
            // (drop-shadow, etc.) follow the JARVIS state. State comes
            // in uppercase (THINKING, SPEAKING, etc.) so we lowercase it.
            const center = document.getElementById('center-panel');
            if (center) {
                center.className = 'hud-panel state-' + s.toLowerCase();
            }
            // Recolor the reactor: swap the core's fill + drop-shadow and
            // tint all four rotating rings, plus adjust rotation speed so
            // the orbital animation reflects current activity.
            const core = document.getElementById('reactor-core');
            const rings = document.querySelectorAll('.reactor-svg circle[class^="ring-"]');
            const reactorPalette = {
                THINKING:    { color: '#ffb703', speed: '3s'  },
                LISTENING:   { color: '#00f5d4', speed: '8s'  },
                SPEAKING:    { color: '#00a8ff', speed: '5s'  },
                OFFLINE:     { color: '#ff4d4d', speed: '60s' },
                RECONNECTING:{ color: '#ff4d4d', speed: '60s' },
            };
            const cfg = reactorPalette[s] || { color: '#00d4ff', speed: '25s' };
            if (core) {
                core.style.fill = cfg.color;
                core.style.filter = 'drop-shadow(0 0 15px ' + cfg.color + ')';
            }
            const hex = cfg.color.replace('#','');
            const rgb = [parseInt(hex.slice(0,2),16), parseInt(hex.slice(2,4),16), parseInt(hex.slice(4,6),16)];
            rings.forEach(r => {
                r.style.stroke = `rgba(${rgb[0]},${rgb[1]},${rgb[2]},0.3)`;
                r.style.animationDuration = cfg.speed;
            });
            // Show the 3-dot typing indicator while the model is thinking.
            // Auto-hides when JARVIS starts speaking or returns to ready.
            const typing = document.getElementById('typing-indicator');
            if (typing) {
                typing.classList.toggle('show', s === 'THINKING');
            }
        }

        function updateModelBadge(model, fallback) {
            const sel = document.getElementById('model-select');
            const badge = document.getElementById('model-badge');
            if (sel && [...sel.options].some(o => o.value === model)) sel.value = model;
            if (badge) {
                if (fallback) {
                    badge.innerText = 'FALLBACK';
                    badge.style.display = 'inline-block';
                } else {
                    badge.style.display = 'none';
                }
            }
        }

        function showToast(message, type) {
            const c = document.getElementById('toast-container');
            if (!c) return;
            const t = document.createElement('div');
            t.className = 'toast ' + (type || '');
            t.innerText = message;
            c.appendChild(t);
            requestAnimationFrame(() => t.classList.add('show'));
            setTimeout(() => {
                t.classList.remove('show');
                setTimeout(() => t.remove(), 400);
            }, 3500);
        }

        // ============================================
        // AUDIO VISUALIZER
        // ============================================
        let _audioLevel = 0;
        let _audioDecay = 0;
        function updateAudioLevel(l) { _audioLevel = Math.max(0, Math.min(1, l || 0)); }
        function drawAudioViz() {
            const cv = document.getElementById('audio-viz');
            if (cv) {
                const ctx = cv.getContext('2d');
                const w = cv.width, h = cv.height;
                ctx.clearRect(0, 0, w, h);
                _audioDecay = Math.max(_audioLevel, _audioDecay * 0.85);
                const bars = 32, gap = 2;
                const bw = (w - gap * (bars - 1)) / bars;
                const cy = h / 2;
                for (let i = 0; i < bars; i++) {
                    const wave = Math.sin(Date.now() / 200 + i * 0.4) * 0.3 + 0.7;
                    const amp = Math.max(0.05, _audioDecay * wave);
                    const bh = amp * h;
                    const x = i * (bw + gap);
                    const g = ctx.createLinearGradient(0, cy - bh/2, 0, cy + bh/2);
                    g.addColorStop(0, 'rgba(0, 212, 255, 0.0)');
                    g.addColorStop(0.5, 'rgba(0, 212, 255, 0.7)');
                    g.addColorStop(1, 'rgba(0, 212, 255, 0.0)');
                    ctx.fillStyle = g;
                    ctx.fillRect(x, cy - bh/2, bw, bh);
                }
            }
            requestAnimationFrame(drawAudioViz);
        }
        requestAnimationFrame(drawAudioViz);

        // ============================================
        // UI EVENT HANDLERS
        // ============================================
        function sendCmd() {
            const input = document.getElementById('cmd-input');
            if (!input || !bridge) return;
            const text = input.value.trim();
            if (!text) return;
            cmdHistory.push(text);
            if (cmdHistory.length > 50) cmdHistory.shift();
            cmdIndex = cmdHistory.length;
            bridge.submitCommand(text);
            input.value = '';
        }

        function changeModel(v) { if (bridge) bridge.changeModel(v); }

        function toggleVoice(checked) {
            if (bridge) bridge.setVoiceModeEnabled(String(checked));
            const mic = document.getElementById('mic-btn');
            if (mic) mic.disabled = !checked;
            if (!checked && micOn) toggleMic();
        }

        function toggleMic() {
            micOn = !micOn;
            const btn = document.getElementById('mic-btn');
            if (btn) {
                btn.classList.toggle('mic-active', micOn);
                btn.classList.toggle('mic-btn-inactive', !micOn);
            }
            if (bridge) bridge.setMicActive(micOn);
        }

        function reconnectCore() { if (bridge) bridge.triggerReconnect(); }
        function resetCore() { if (bridge) bridge.resetSession(); }

        function clearLog() {
            finalizeJarvis();
            const log = document.getElementById('log-area');
            if (log) log.innerHTML = '';
        }
    </script>
</head>
<body>
    <div id="boot-overlay">
        <div class="boot-logo">J.A.R.V.I.S.</div>
        <div class="boot-sub">INITIALIZING NEURAL MATRIX // MARK XLV</div>
        <div class="boot-bar"><div class="boot-bar-inner"></div></div>
    </div>
    <div id="toast-container"></div>
    <header>
        <div class="logo-block">
            <h1>J.A.R.V.I.S.</h1>
            <div class="sub">Just A Rather Very Intelligent System // Mark XLV</div>
        </div>
        <div class="status-pill">
            <div class="status-dot" id="header-dot"></div>
            <span>CORE: <span id="header-label">INIT</span></span>
        </div>
    </header>
    <main>
        <div class="hud-panel" id="left-panel">
            <div class="panel-label">SYSTEM TELEMETRY <span id="tele-live">// LIVE</span></div>
            <div class="metric">
                <div class="metric-header"><span class="metric-name">Neural Load</span><span class="metric-val" id="cpu-txt">--%</span></div>
                <div class="bar-track"><div class="bar-fill" id="cpu-bar" style="width:0%"></div></div>
            </div>
            <div class="metric">
                <div class="metric-header"><span class="metric-name">Memory Matrix</span><span class="metric-val" id="mem-txt">--</span></div>
                <div class="bar-track"><div class="bar-fill" id="mem-bar" style="width:0%"></div></div>
            </div>
            <div class="metric">
                <div class="metric-header"><span class="metric-name">Storage Index</span><span class="metric-val" id="disk-txt">--</span></div>
                <div class="bar-track"><div class="bar-fill" id="disk-bar" style="width:0%"></div></div>
            </div>
            <div style="margin-top:8px;">
                <div class="net-row"><span class="net-label">Net Incoming</span><span class="net-val net-in" id="net-in">0.0 B/s</span></div>
                <div class="net-row"><span class="net-label">Net Outgoing</span><span class="net-val net-out" id="net-out">0.0 B/s</span></div>
            </div>
            <div class="focus-box" id="focus-win">System Idle</div>
        </div>
        <div class="hud-panel" id="center-panel">
            <div class="reactor-wrap">
                <svg class="reactor-svg" viewBox="0 0 200 200">
                    <defs>
                        <radialGradient id="coreGrad" cx="50%" cy="50%" r="50%">
                            <stop offset="0%" stop-color="#ffffff" />
                            <stop offset="50%" stop-color="#00d4ff" />
                            <stop offset="100%" stop-color="#00d4ff" stop-opacity="0" />
                        </radialGradient>
                    </defs>

                    <!-- Outer rings -->
                    <circle cx="100" cy="100" r="95" fill="none" stroke="rgba(0,212,255,0.06)" stroke-width="1" />
                    <circle cx="100" cy="100" r="90" fill="none" stroke="rgba(0,212,255,0.15)" stroke-width="1.5" stroke-dasharray="4 8" class="ring-hex" />
                    <circle cx="100" cy="100" r="82" fill="none" stroke="rgba(0,212,255,0.2)" stroke-width="2" stroke-dasharray="10 14" class="ring-outer" />
                    <circle cx="100" cy="100" r="72" fill="none" stroke="rgba(0,212,255,0.08)" stroke-width="1" />
                    <circle cx="100" cy="100" r="64" fill="none" stroke="rgba(0,212,255,0.25)" stroke-width="2.5" stroke-dasharray="6 6" class="ring-mid" />
                    <circle cx="100" cy="100" r="54" fill="none" stroke="rgba(0,212,255,0.1)" stroke-width="1" />
                    <circle cx="100" cy="100" r="46" fill="none" stroke="rgba(0,212,255,0.3)" stroke-width="2" stroke-dasharray="12 4" class="ring-inner" />
                    <circle cx="100" cy="100" r="36" fill="none" stroke="rgba(0,212,255,0.15)" stroke-width="1" />

                    <!-- Glowing core -->
                    <circle cx="100" cy="100" r="28" fill="url(#coreGrad)" class="core-glow" id="reactor-core" />
                    <circle cx="100" cy="100" r="14" fill="#fff" opacity="0.9" />

                    <!-- Crosshairs -->
                    <line x1="100" y1="5" x2="100" y2="15" stroke="rgba(0,212,255,0.5)" stroke-width="1.5" />
                    <line x1="100" y1="185" x2="100" y2="195" stroke="rgba(0,212,255,0.5)" stroke-width="1.5" />
                    <line x1="5" y1="100" x2="15" y2="100" stroke="rgba(0,212,255,0.5)" stroke-width="1.5" />
                    <line x1="185" y1="100" x2="195" y2="100" stroke="rgba(0,212,255,0.5)" stroke-width="1.5" />
                </svg>
            </div>
            <canvas id="audio-viz" width="260" height="60"></canvas>
            <div class="status-banner" id="center-status">CORE STATUS: INIT</div>
        </div>
        <div class="hud-panel" id="right-panel">
            <div class="panel-label">NEURAL ACTIVITY <span>// COMMS</span></div>
            <div id="log-area"></div>
            <div class="typing-indicator" id="typing-indicator">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <span class="label">PROCESSING</span>
            </div>
        </div>
    </main>
    <footer>
        <div class="input-row">
            <input type="text" id="cmd-input" placeholder="Awaiting command, Sir..." autocomplete="off" onkeydown="if(event.key==='Enter' && !event.isComposing){sendCmd();return false;}">
            <button class="exec-btn" onclick="sendCmd()">EXECUTE</button>
        </div>
        <div class="controls-row">
            <div class="ctrl-group">
                <span class="ctrl-label">Model</span>
                <select id="model-select" onchange="changeModel(this.value)">
                    <option value="gemini-2.5-flash-native-audio-latest">Gemini 2.5 Audio</option>
                    <option value="gemini-2.0-flash-live-preview-04-09">Gemini 2.0 Live</option>
                </select>
                <span id="model-badge" class="badge badge-fallback" style="display:none"></span>
            </div>
            <div class="ctrl-group">
                <span class="ctrl-label">Voice</span>
                <label class="switch" style="position:relative;display:inline-block;width:36px;height:18px;">
                    <input type="checkbox" id="voice-toggle" onchange="toggleVoice(this.checked)" style="opacity:0;width:0;height:0;">
                    <span class="voice-track" style="position:absolute;cursor:pointer;top:0;left:0;right:0;bottom:0;background:rgba(0,212,255,0.1);border:1px solid rgba(0,212,255,0.2);transition:.4s;border-radius:20px;"></span>
                    <span class="voice-slider" style="position:absolute;content:'';height:12px;width:12px;left:2px;bottom:2px;background:#5a7a99;transition:.4s;border-radius:50%;"></span>
                </label>
                <style>
                    #voice-toggle:checked ~ .voice-track { background: rgba(0,212,255,0.25) !important; border-color: var(--jarvis-cyan) !important; }
                    #voice-toggle:checked ~ .voice-slider { transform: translateX(18px); background: var(--jarvis-cyan) !important; box-shadow: 0 0 6px var(--jarvis-cyan); }
                </style>
            </div>
            <button id="mic-btn" class="hud-btn mic-btn-inactive" onclick="toggleMic()" disabled>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v1a7 7 0 0 1-14 0v-1M12 19v4M8 23h8"/></svg>
                <span>MIC</span>
            </button>
            <button class="hud-btn" onclick="reconnectCore()">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
                RE-LINK
            </button>
            <button class="hud-btn" onclick="resetCore()">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>
                RESET
            </button>
            <button class="hud-btn" onclick="clearLog()">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                PURGE
            </button>
        </div>
    </footer>
</body>
</html>
"""


# ==========================================
# AUDIO ENGINE
# ==========================================
class AudioPlayer:
    def __init__(self, on_level: Optional[Callable[[float], None]] = None):
        self._queue = queue.Queue()
        self._buffer = b''
        self._stream = None
        self._active = False
        self.on_level = on_level
        self._lock = threading.Lock()

    def start(self):
        def callback(outdata, frames, time_info, status):
            needed = frames * 2
            with self._lock:
                while len(self._buffer) < needed:
                    try:
                        self._buffer += self._queue.get_nowait()
                    except queue.Empty:
                        break
                if len(self._buffer) >= needed:
                    chunk = self._buffer[:needed]
                    outdata[:] = chunk
                    self._buffer = self._buffer[needed:]
                    if self.on_level:
                        self.on_level(self._calculate_level(chunk))
                else:
                    outdata[:len(self._buffer)] = self._buffer
                    outdata[len(self._buffer):] = b'\x00' * (needed - len(self._buffer))
                    if self.on_level and self._buffer:
                        self.on_level(self._calculate_level(self._buffer))
                    self._buffer = b''

        try:
            self._stream = sd.RawOutputStream(
                samplerate=AUDIO_SR_OUT, channels=1, dtype='int16', callback=callback
            )
            self._stream.start()
            self._active = True
        except Exception as e:
            print(f"[AudioPlayer] Init error: {e}")

    def feed(self, data: bytes):
        if self._active:
            self._queue.put(data)

    def stop(self):
        self._active = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def _calculate_level(self, data: bytes) -> float:
        if not data or len(data) < 2:
            return 0.0
        count = len(data) // 2
        if count == 0:
            return 0.0
        samples = struct.unpack(f'<{count}h', data[:count * 2])
        sum_sq = sum(s * s for s in samples)
        rms = math.sqrt(sum_sq / count)
        return min(1.0, rms / 32768.0)


class AudioRecorder:
    def __init__(self, on_data: Callable[[bytes], None], on_level: Optional[Callable[[float], None]] = None):
        self.on_data = on_data
        self.on_level = on_level
        self._stream = None
        self._active = False
        self._accumulator = bytearray()
        self._last_flush = 0.0

    def start(self):
        def callback(indata, frames, time_info, status):
            if not self._active:
                return
            data = bytes(indata)
            self._accumulator.extend(data)
            if self.on_level:
                self.on_level(self._calculate_level(data))
            now = time.time()
            if now - self._last_flush >= 0.1:  # 100 ms batches
                if self._accumulator:
                    self.on_data(bytes(self._accumulator))
                    self._accumulator.clear()
                    self._last_flush = now

        try:
            self._stream = sd.RawInputStream(
                samplerate=AUDIO_SR_IN, channels=1, dtype='int16', callback=callback
            )
            self._stream.start()
            self._active = True
            self._last_flush = time.time()
        except Exception as e:
            print(f"[AudioRecorder] Init error: {e}")

    def stop(self):
        self._active = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def _calculate_level(self, data: bytes) -> float:
        if not data or len(data) < 2:
            return 0.0
        count = len(data) // 2
        if count == 0:
            return 0.0
        samples = struct.unpack(f'<{count}h', data[:count * 2])
        sum_sq = sum(s * s for s in samples)
        rms = math.sqrt(sum_sq / count)
        return min(1.0, rms / 32768.0)


# ==========================================
# TELEMETRY
# ==========================================
def get_active_window_title():
    if os.name != 'nt':
        return "N/A"
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
            return (title[:30] + "...") if len(title) > 30 else title
        return "Desktop"
    except Exception:
        return "System Idle"


class TelemetryWorker(QThread):
    stats_updated = pyqtSignal(float, float, float, str, str, str)

    def __init__(self):
        super().__init__()
        self.last_net = None
        self.last_time = time.time()

    def run(self):
        # Prime psutil.cpu_percent — its first call returns 0.0 because it has
        # no baseline. Establishing the baseline here keeps the first real
        # value the UI sees accurate.
        try:
            psutil.cpu_percent(interval=None)
        except Exception:
            pass

        while not self.isInterruptionRequested():
            try:
                cpu = float(psutil.cpu_percent(interval=None))
                mem = float(psutil.virtual_memory().percent)
                disk = float(self._get_disk_pct())
                now = time.time()
                dt = now - self.last_time
                net_in, net_out = self._get_net(dt)
                self.last_time = now
                self.stats_updated.emit(cpu, mem, disk, net_in, net_out, get_active_window_title())
            except Exception as e:
                # Surface errors to stderr so silent worker death is debuggable.
                # (We keep going — telemetry is best-effort.)
                print(f"[Telemetry] tick error: {e}")
            self.msleep(TELEMETRY_INTERVAL_MS)

    def _get_disk_pct(self):
        try:
            for path in ['/', 'C:\\']:
                try:
                    return int(psutil.disk_usage(path).percent)
                except Exception:
                    continue
            return 0
        except Exception:
            return 0

    def _get_net(self, dt):
        if dt <= 0:
            return "0.0 B/s", "0.0 B/s"
        try:
            net = psutil.net_io_counters()
            if self.last_net is None:
                self.last_net = net
                return "0.0 B/s", "0.0 B/s"
            bs = (net.bytes_sent - self.last_net.bytes_sent) / dt
            br = (net.bytes_recv - self.last_net.bytes_recv) / dt
            self.last_net = net
            return self._fmt(br), self._fmt(bs)
        except Exception:
            return "0.0 B/s", "0.0 B/s"

    def _fmt(self, b):
        if b < 1024:
            return f"{b:.1f} B/s"
        elif b < 1024 * 1024:
            return f"{b / 1024:.1f} KB/s"
        return f"{b / (1024 * 1024):.1f} MB/s"


# ==========================================
# BRIDGE
# ==========================================
class PyBridge(QObject):
    logReceived = pyqtSignal(str, str)
    statusUpdated = pyqtSignal(str)
    telemetryUpdated = pyqtSignal(float, float, float, str, str, str)
    modelSwitched = pyqtSignal(str, bool)
    audioLevelUpdated = pyqtSignal(float)
    toastReceived = pyqtSignal(str, str)

    def __init__(self, window_handle):
        super().__init__()
        self.window = window_handle

    @pyqtSlot(str)
    def submitCommand(self, text):
        if self.window.core:
            self.window.core.dispatch_text(text)

    @pyqtSlot()
    def onBridgeReady(self):
        self.window.ui_ready = True
        self.logReceived.emit("JARVIS", "Neural matrix online. All systems nominal. Awaiting your command, Sir.")
        self.telemetryUpdated.emit(0, 0, 0, "0.0 B/s", "0.0 B/s", "System Idle")
        self.window.start_core()

    @pyqtSlot(str)
    def setVoiceModeEnabled(self, enabled_str):
        enabled = enabled_str.lower() == "true"
        if self.window.core:
            self.window.core.set_voice_mode(enabled)

    @pyqtSlot(str)
    def changeModel(self, model_name):
        if self.window.core:
            self.window.core.change_model(model_name)

    @pyqtSlot()
    def triggerReconnect(self):
        if self.window.core:
            self.window.core.trigger_reconnect()

    @pyqtSlot()
    def resetSession(self):
        if self.window.core:
            self.window.core.reset_session()

    @pyqtSlot(bool)
    def setMicActive(self, active):
        self.window.set_mic_active(active)


# ==========================================
# CORE INTELLIGENCE
# ==========================================
class ResponseWatchdog:
    """One-shot timeout watchdog. Thread-safe to start/stop from any thread.

    Uses threading.Timer (not asyncio) because start()/stop() are called from
    the Qt main thread (via pyqtSlot dispatch_text), and there's no asyncio
    loop running there. threading.Timer works from any thread.
    """
    def __init__(self, timeout: float, callback: Callable):
        self.timeout = timeout
        self.callback = callback
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

    def start(self):
        self.stop()
        with self._lock:
            # daemon=True so the timer thread doesn't block process exit
            self._timer = threading.Timer(self.timeout, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def stop(self):
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None

    def _fire(self):
        with self._lock:
            self._timer = None
        try:
            self.callback()
        except Exception as e:
            print(f"[Watchdog] callback error: {e}")


class JarvisCore:
    def __init__(self, bridge: PyBridge):
        self.bridge = bridge
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="JarvisAsync")

        self.client: Optional[genai.Client] = None
        self.session = None
        self.session_ready = asyncio.Event()
        self._shutdown = False
        self._state = "INIT"
        self._state_lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._history_lock = threading.Lock()

        self.voice_enabled = False
        self.mic_active = False

        self.audio_player = AudioPlayer(on_level=self._on_audio_level)
        self.audio_recorder: Optional[AudioRecorder] = None

        self.model_pool = list(MODEL_POOL)
        self.current_model_idx = 0
        self.resumption_token: Optional[str] = None
        self.reconnect_backoff = 1.0
        self.max_backoff = 60.0
        self.retry_cycle = 0
        # Active countdown timers (set_timer). Kept so we can cancel on shutdown.
        self._active_timers: List[threading.Timer] = []

        self.history: List[types.Content] = []
        self.pending_messages: List[str] = []
        self._response_buffer = ""
        self._response_lock = threading.Lock()
        self.context_tokens = 0
        self.context_chars = 0

        self._api_key = self._load_api_key()
        if self._api_key:
            self.client = genai.Client(api_key=self._api_key)

        # 45s gives the model breathing room to pick a tool from a large
        # toolset, but still aborts quickly if the link is truly dead.
        self.watchdog = ResponseWatchdog(45.0, self._on_watchdog_timeout)

        self.thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._main_loop())
        except Exception as e:
            print(f"[JarvisCore] Loop fatal: {e}")

    async def _main_loop(self):
        self.set_state("BOOT")
        await asyncio.sleep(1.0)
        if not self.client:
            self._emit_log("SYSTEM", "API Key not found. Configure api_keys.json or GEMINI_API_KEY env var.")
            self.set_state("OFFLINE")
            return
        await self._connect_pipeline()

    def set_state(self, state: str):
        with self._state_lock:
            self._state = state
        self.bridge.statusUpdated.emit(state)

    def get_state(self) -> str:
        with self._state_lock:
            return self._state

    def _emit_log(self, sender: str, text: str):
        self.bridge.logReceived.emit(sender, text)

    def _on_audio_level(self, level: float):
        self.bridge.audioLevelUpdated.emit(level)

    def _on_watchdog_timeout(self):
        state = self.get_state()
        if state == "THINKING":
            # The model is stuck — either a chained tool call hung, a slow
            # tool response send, or a session that lost the response stream.
            # Instead of just going to READY (which leaves the session in a
            # potentially dead state), trigger a reconnect so we get a fresh
            # session. Preserve buffered messages so they aren't lost.
            self._emit_log("SYSTEM",
                "Neural response timeout. Re-linking to restore connection.")
            self.watchdog.stop()
            self.set_state("RECONNECTING")
            self._schedule(self._safe_close(), "Watchdog reconnect")
        elif state in ("CONNECTING", "RECONNECTING"):
            # Connection attempt itself is stuck — reset backoff and try again.
            self._emit_log("SYSTEM",
                "Connection attempt timed out. Retrying with fresh state.")
            self.watchdog.stop()
            self.reconnect_backoff = 1.0
            self.session = None
            self.session_ready.clear()

    def _schedule(self, coro, desc: str = "task"):
        """Thread-safe wrapper around run_coroutine_threadsafe that survives
        a closed/stopped event loop (e.g. during shutdown)."""
        try:
            return asyncio.run_coroutine_threadsafe(coro, self.loop)
        except RuntimeError as e:
            # Loop is closed or stopping — not an error during shutdown.
            if not self._shutdown:
                self._emit_log("SYSTEM", f"{desc} dropped (loop unavailable): {e}")
            return None
        except Exception as e:
            self._emit_log("SYSTEM", f"{desc} schedule error: {e}")
            return None

    def _load_api_key(self):
        if API_CONFIG_PATH.exists():
            try:
                with open(API_CONFIG_PATH, "r") as f:
                    return json.load(f).get("gemini_api_key")
            except Exception:
                pass
        return os.environ.get("GEMINI_API_KEY")

    def _build_system_prompt(self) -> str:
        from datetime import datetime
        return SYSTEM_PROMPT.format(
            time=datetime.now().strftime("%H:%M:%S"),
            date=datetime.now().strftime("%Y-%m-%d")
        )

    def _add_history(self, role: str, text: str):
        with self._history_lock:
            self.history.append(types.Content(parts=[types.Part.from_text(text=text)], role=role))
            self.context_chars += len(text)
            self.context_tokens += max(1, len(text) // 4)

            # Smart trimming: when history exceeds the limit, compress the
            # oldest messages into a context digest instead of dropping them.
            if len(self.history) > MAX_HISTORY:
                # Keep the most recent turns intact; drop from the front.
                # Drop enough to get back to MAX_HISTORY - 2, leaving room
                # for the digest entry we'll insert.
                target = MAX_HISTORY - 2
                drop_count = len(self.history) - target

                dropped = []
                for _ in range(drop_count):
                    if self.history:
                        removed = self.history.pop(0)
                        txt = ''.join(
                            p.text for p in removed.parts
                            if hasattr(p, 'text') and p.text
                        )
                        self.context_chars -= len(txt)
                        self.context_tokens -= max(1, len(txt) // 4)
                        if txt.strip():
                            dropped.append((removed.role, txt.strip()))

                # Build a digest entry from the dropped turns and prepend it.
                if dropped:
                    digest = self._build_context_digest(dropped)
                    if digest:
                        self.history.insert(0, digest)

    def _build_context_digest(self, dropped):
        """Compress dropped conversation turns into a single summary entry.

        The digest preserves user intent and key facts from the dropped
        messages so the model can reference them when the conversation
        continues.  Returns a ``types.Content`` with role ``user`` (the
        Gemini API treats the first message as user-authored context).
        """
        lines = ["[Earlier conversation — compressed context]"]
        for role, text in dropped:
            # Truncate each turn to keep the digest compact.
            short = text[:300].replace("\n", " ")
            if len(text) > 300:
                short += "..."
            tag = "User" if role == "user" else "JARVIS"
            lines.append(f"  {tag}: {short}")

        # Keep only the last 12 lines of the digest to stay within reason.
        if len(lines) > 13:
            lines = lines[:1] + ["  ..."] + lines[-(12 - 1):]

        summary = "\n".join(lines)
        return types.Content(
            parts=[types.Part.from_text(text=summary)],
            role="user"
        )

    def _build_reconnect_summary(self):
        """Build a compressed summary of the FULL conversation history for
        context restoration on reconnect.

        Unlike the rolling digest (which only covers trimmed turns), this
        summarises everything currently in ``self.history`` so the model
        gets maximum context after a session restart.
        """
        with self._history_lock:
            if not self.history:
                return None

            lines = ["[Full session context summary — provided on reconnect]"]
            for entry in self.history:
                txt = ''.join(
                    p.text for p in entry.parts
                    if hasattr(p, 'text') and p.text
                )
                if not txt.strip():
                    continue
                # Skip entries that are already digests
                if txt.startswith("[Earlier conversation"):
                    short = txt[:500].replace("\n", " ")
                    if len(txt) > 500:
                        short += "..."
                    lines.append(f"  {short}")
                    continue
                short = txt[:200].replace("\n", " ")
                if len(txt) > 200:
                    short += "..."
                tag = "User" if entry.role == "user" else "JARVIS"
                lines.append(f"  {tag}: {short}")

            # Cap the summary at 25 lines to stay within API limits.
            if len(lines) > 26:
                lines = lines[:2] + ["  ... (compressed) ..."] + lines[-(25 - 2):]

            summary = "\n".join(lines)
            return types.Content(
                parts=[types.Part.from_text(text=summary)],
                role="user"
            )

    def _extract_text(self, response) -> str:
        """Extract visible text from every possible SDK location."""
        chunks = []

        # 1. Official transcription (preferred)
        if hasattr(response, 'server_content') and response.server_content:
            sc = response.server_content
            if hasattr(sc, 'output_transcription') and sc.output_transcription:
                try:
                    t = sc.output_transcription.text
                    if t:
                        chunks.append(t)
                except Exception:
                    pass

            # 2. Model turn parts (fallback for older SDKs)
            if hasattr(sc, 'model_turn') and sc.model_turn:
                for part in sc.model_turn.parts:
                    try:
                        # Skip "thought" parts — they are the model's internal
                        # reasoning and must NOT be shown to the user.
                        if getattr(part, 'thought', False):
                            continue
                        if hasattr(part, 'text') and part.text:
                            chunks.append(part.text)
                    except Exception:
                        pass

        # 3. Top-level response text (nuclear fallback)
        try:
            if hasattr(response, 'text') and response.text:
                chunks.append(response.text)
        except Exception:
            pass

        return " ".join(chunks)

    def dispatch_text(self, text: str):
        self._emit_log("YOU", text)
        with self._response_lock:
            self._response_buffer = ""

        if not self.session_ready.is_set() or not self.session:
            with self._pending_lock:
                if len(self.pending_messages) >= MAX_PENDING:
                    self.pending_messages.pop(0)  # drop oldest
                self.pending_messages.append(text)
            self._emit_log("SYSTEM", "Connection unstable. Command buffered for re-link.")
            return

        self._add_history("user", text)
        coro = self.session.send_client_content(
            turns=[types.Content(parts=[types.Part.from_text(text=text)], role='user')],
            turn_complete=True
        )
        self._schedule(self._safe_send(coro, "Message transmit"), "Message transmit")
        self.set_state("THINKING")
        self.watchdog.start()

    async def _safe_send(self, coro, desc: str = "send"):
        try:
            await coro
        except Exception as e:
            err = str(e).lower()
            # Auto-retry once on transient errors (broken pipe, connection reset, etc.)
            is_transient = any(x in err for x in [
                "broken pipe", "connection reset", "connection aborted",
                "eof", "deadline exceeded", "timeout"
            ])
            if is_transient:
                try:
                    await asyncio.sleep(0.3)
                    await coro
                    return  # Retry succeeded
                except Exception:
                    pass  # Retry also failed, fall through to error handling
            self._emit_log("SYSTEM", f"{desc} failed: {str(e)[:100]}")
            self.watchdog.stop()
            self.set_state("READY")

    def send_audio_chunk(self, data: bytes):
        if self.session and self.session_ready.is_set() and self.mic_active and not self._shutdown:
            coro = self.session.send_realtime_input(
                media=types.Blob(mime_type="audio/pcm;rate=16000", data=data)
            )
            self._schedule(coro, "Audio transmit")

    def set_voice_mode(self, enabled: bool):
        self.voice_enabled = enabled
        if enabled:
            self.audio_player.start()
        else:
            self.audio_player.stop()

    def set_mic_active(self, active: bool):
        self.mic_active = active
        if active:
            if not self.audio_recorder:
                self.audio_recorder = AudioRecorder(
                    on_data=self.send_audio_chunk,
                    on_level=self._on_audio_level
                )
            self.audio_recorder.start()
        else:
            if self.audio_recorder:
                self.audio_recorder.stop()
                self.audio_recorder = None

    def change_model(self, model_name: str):
        if model_name in self.model_pool:
            idx = self.model_pool.index(model_name)
            self.model_pool[0], self.model_pool[idx] = self.model_pool[idx], self.model_pool[0]
        else:
            self.model_pool.insert(0, model_name)
        self.current_model_idx = 0
        self.resumption_token = None
        self._emit_log("SYSTEM", f"Switching neural path to {model_name}...")
        self.trigger_reconnect()

    def trigger_reconnect(self):
        if self.session and self.loop:
            self._schedule(self._safe_close(), "Reconnect")

    async def _safe_close(self):
        if self.session:
            try:
                await self.session.close()
            except Exception:
                pass
            self.session = None
            self.session_ready.clear()

    def reset_session(self):
        with self._history_lock:
            self.history.clear()
        with self._pending_lock:
            self.pending_messages.clear()
        with self._response_lock:
            self._response_buffer = ""
        self.context_tokens = 0
        self.context_chars = 0
        self.resumption_token = None
        self.current_model_idx = 0
        self.reconnect_backoff = 1.0
        self.retry_cycle = 0
        self.trigger_reconnect()
        self._emit_log("SYSTEM", "Neural matrix fully purged. Fresh session initiated.")

    def stop(self):
        self._shutdown = True
        self.watchdog.stop()
        self.audio_player.stop()
        if self.audio_recorder:
            self.audio_recorder.stop()
        if self.session:
            self._schedule(self._safe_close(), "Shutdown close")
        self.loop.call_soon_threadsafe(self.loop.stop)

    async def _connect_pipeline(self):
        while not self._shutdown:
            model = self.model_pool[self.current_model_idx % len(self.model_pool)]
            is_fallback = self.current_model_idx > 0

            try:
                self.set_state("RECONNECTING" if is_fallback else "CONNECTING")
                self.bridge.modelSwitched.emit(model, is_fallback)

                config = types.LiveConnectConfig(
                    response_modalities=["AUDIO"],
                    system_instruction=types.Content(
                        parts=[types.Part.from_text(text=self._build_system_prompt())],
                        role="user"
                    ),
                    tools=[types.Tool(function_declarations=JARVIS_TOOLS)],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
                        )
                    ),
                    # Enable audio transcription so the model sends the text
                    # transcript of what it said via sc.output_transcription.
                    # Without this, response_modalities=["AUDIO"] gives us
                    # spoken audio only — nothing to display in the chat.
                    output_audio_transcription=types.AudioTranscriptionConfig(),
                    temperature=0.4,
                )
                if self.resumption_token:
                    config.session_resumption = types.SessionResumptionConfig(handle=self.resumption_token)

                async with self.client.aio.live.connect(model=model, config=config) as session:
                    self.session = session
                    self.session_ready.set()

                    # Context restoration on reconnect.  We send two things:
                    # 1. A compressed summary of the FULL conversation so far
                    #    (so the model has maximum context after a restart).
                    # 2. The raw recent history (last MAX_HISTORY turns) so
                    #    the model has the exact recent exchange.
                    # If there's no resumption token we still restore context
                    # from the summary (the session is fresh but our history
                    # survived in memory).
                    with self._history_lock:
                        has_history = bool(self.history)

                    if has_history:
                        try:
                            # First: compressed summary of everything so far
                            summary = self._build_reconnect_summary()
                            if summary:
                                await session.send_client_content(
                                    turns=[summary], turn_complete=False)
                            # Second: the recent raw turns for fine detail
                            with self._history_lock:
                                recent = list(self.history[-MAX_HISTORY:])
                            if recent:
                                await session.send_client_content(
                                    turns=recent, turn_complete=False)
                        except Exception as e:
                            self._emit_log(
                                "SYSTEM",
                                f"Context restore warning: {str(e)[:80]}")

                    self._flush_pending()
                    self.reconnect_backoff = 1.0
                    self.current_model_idx = 0
                    self.retry_cycle = 0
                    self.set_state("READY")

                    async for response in session.receive():
                        if self._shutdown:
                            break
                        await self._handle_response(response)

            except Exception as e:
                await self._handle_connection_error(e)

    async def _handle_connection_error(self, e: Exception):
        err = str(e).lower()
        err_type = "NETWORK"
        if any(x in err for x in ["401", "403", "unauthorized", "api key invalid", "authentication"]):
            err_type = "AUTH"
        elif any(x in err for x in ["429", "rate limit", "quota", "too many requests"]):
            err_type = "RATE"
        elif any(x in err for x in ["not found", "1008", "unsupported", "model", "does not support"]):
            err_type = "MODEL"
        elif any(x in err for x in ["500", "502", "503", "504", "internal", "unavailable", "deadline exceeded", "broken pipe", "connection reset", "connection aborted", "eof"]):
            err_type = "SERVER"

        if err_type == "AUTH":
            self._emit_log("SYSTEM", f"Authentication failed. Check API key. ({str(e)[:60]})")
            self.set_state("OFFLINE")
            await self._wait_shutdown(30)
            return
        elif err_type == "RATE":
            # Aggressive backoff for rate limits but cap quickly.
            self.reconnect_backoff = min(max(self.reconnect_backoff * 2, 5.0), self.max_backoff)
            self._emit_log("SYSTEM", f"Rate limited. Backing off {self.reconnect_backoff:.1f}s...")
        elif err_type == "MODEL":
            self.current_model_idx += 1
            if self.current_model_idx >= len(self.model_pool):
                self.current_model_idx = 0
                self.retry_cycle += 1
                if self.retry_cycle >= 5:
                    self._emit_log("SYSTEM", "All neural paths exhausted after 5 cycles. Entering hibernation.")
                    self.set_state("OFFLINE")
                    await self._wait_shutdown(30)
                    self.retry_cycle = 0
                    return
            self._emit_log("SYSTEM", f"Model path failed. Rerouting to {self.model_pool[self.current_model_idx]}...")
            self.reconnect_backoff = 1.0
        else:
            # Network/server errors: exponential backoff with floor of 1s.
            self.reconnect_backoff = min(max(self.reconnect_backoff * 1.5, 1.0), self.max_backoff)
            if self.resumption_token and "resumption" in err:
                self.resumption_token = None
            self._emit_log("SYSTEM", f"Connection anomaly: {str(e)[:60]}. Re-linking in {self.reconnect_backoff:.1f}s...")

        self.session = None
        self.session_ready.clear()
        # Jitter: random 0-50% of backoff to avoid thundering herd.
        jitter = random.uniform(0, self.reconnect_backoff * 0.5)
        await asyncio.sleep(self.reconnect_backoff + jitter)

    async def _wait_shutdown(self, seconds: int):
        for _ in range(seconds * 2):
            if self._shutdown:
                return
            await asyncio.sleep(0.5)

    def _flush_pending(self):
        if not self.session or not self.session_ready.is_set():
            return
        while True:
            with self._pending_lock:
                if not self.pending_messages:
                    return
                msg = self.pending_messages.pop(0)
            self._add_history("user", msg)
            coro = self.session.send_client_content(
                turns=[types.Content(parts=[types.Part.from_text(text=msg)], role='user')],
                turn_complete=True
            )
            future = self._schedule(self._safe_send(coro, "Flush transmit"), "Flush transmit")
            if future is None:
                # Loop unavailable — put the message back at the head.
                with self._pending_lock:
                    self.pending_messages.insert(0, msg)
                return

    async def _handle_response(self, response):
        try:
            # Resumption token
            if hasattr(response, 'session_resumption_update') and response.session_resumption_update:
                new_handle = getattr(response.session_resumption_update, 'new_handle', None)
                if new_handle:
                    self.resumption_token = new_handle

            has_server = hasattr(response, 'server_content') and response.server_content
            has_tool = hasattr(response, 'tool_call') and response.tool_call

            # Early return ONLY if there's truly nothing to do. A response with
            # tool_call but no server_content (model calls a function without
            # speaking) MUST still be processed, otherwise the model waits
            # forever for a tool response and the next watchdog tick fires the
            # misleading "Neural response timeout" message.
            if not (has_server or has_tool):
                return

            sc = response.server_content if has_server else None

            # Audio playback
            if sc and hasattr(sc, 'model_turn') and sc.model_turn:
                for part in sc.model_turn.parts:
                    if hasattr(part, 'inline_data') and part.inline_data and getattr(part.inline_data, 'data', None):
                        if self.voice_enabled:
                            self.set_state("SPEAKING")
                            self.audio_player.feed(part.inline_data.data)
                # If the model produced audio (or even empty model_turn parts)
                # without text, that still counts as activity — reset the
                # watchdog so audio-only synthesis doesn't get killed mid-stream.
                if sc.model_turn.parts:
                    self.watchdog.stop()
                    self.watchdog.start()

            # Text extraction (multi-source)
            text = self._extract_text(response)
            if text:
                with self._response_lock:
                    self._response_buffer += text
                self._emit_log("JARVIS", text)
                self.watchdog.stop()
                self.watchdog.start()

            # Turn complete
            if sc and getattr(sc, 'turn_complete', False):
                self.watchdog.stop()
                with self._response_lock:
                    if self._response_buffer:
                        final = self._response_buffer.strip()
                        self._add_history("model", final)
                        self._response_buffer = ""
                self.set_state("READY")

            # Tool calls
            if has_tool:
                calls = response.tool_call.function_calls or []
                if not calls:
                    # Empty tool_call payload — nothing to execute. Make sure
                    # the watchdog isn't left running from a previous turn.
                    if self.get_state() == "THINKING":
                        self.set_state("READY")
                        self.watchdog.stop()
                else:
                    self.set_state("THINKING")
                    self.watchdog.start()
                    with self._response_lock:
                        if self._response_buffer:
                            self._add_history("model", self._response_buffer.strip())
                            self._response_buffer = ""
                    for call in calls:
                        await self._execute_tool(call)
                    # Note: we keep the watchdog running here so we can detect
                    # if the model hangs while generating the final response
                    # after the tool result. turn_complete (above) will stop it.
                    self.set_state("READY")

        except Exception as e:
            self._emit_log("SYSTEM", f"Response processing error: {e}")
            traceback.print_exc()
            self.watchdog.stop()
            self.set_state("READY")

    async def _execute_tool(self, call):
        name = call.name
        args = call.args or {}
        call_id = call.id
        self._emit_log("ACTION", f"Executing protocol: {name}...")

        result = ""
        try:
            if name == "open_application":
                result = await asyncio.to_thread(self._tool_open_app, args.get("command"))
            elif name == "take_screenshot":
                result = await asyncio.to_thread(self._tool_screenshot)
            elif name == "get_system_info":
                result = await asyncio.to_thread(self._tool_system_info)
            elif name == "execute_shell":
                result = await self._tool_shell(args.get("command"))
            elif name == "read_clipboard":
                result = await asyncio.to_thread(pyperclip.paste) or "[Clipboard empty]"
            elif name == "write_clipboard":
                text = args.get("text", "")
                await asyncio.to_thread(pyperclip.copy, text)
                result = f"Copied {len(text)} characters to clipboard."
            elif name == "type_text":
                text = args.get("text", "")
                await asyncio.to_thread(pyautogui.write, text, interval=0.01)
                result = f"Typed {len(text)} characters."
            elif name == "press_key":
                key = args.get("key", "")
                if '+' in key:
                    keys = key.split('+')
                    await asyncio.to_thread(pyautogui.hotkey, *keys)
                else:
                    await asyncio.to_thread(pyautogui.press, key)
                result = f"Pressed {key}."
            elif name == "get_weather":
                # Pass "" as default so the model can omit the arg entirely.
                result = await asyncio.to_thread(self._tool_weather, args.get("location", ""))

            # ----- Filesystem dispatch -----
            elif name == "list_directory":
                result = await asyncio.to_thread(self._tool_list_directory, args.get("path", ""))
            elif name == "read_file":
                result = await asyncio.to_thread(self._tool_read_file, args.get("path", ""))
            elif name == "search_files":
                result = await asyncio.to_thread(
                    self._tool_search_files,
                    args.get("pattern", ""),
                    args.get("directory", ""),
                    bool(args.get("recursive", False)),
                )
            elif name == "search_file_contents":
                result = await asyncio.to_thread(
                    self._tool_search_file_contents,
                    args.get("query", ""),
                    args.get("directory", ""),
                    args.get("file_glob", ""),
                    bool(args.get("recursive", True)),
                )
            elif name == "write_file":
                result = await asyncio.to_thread(
                    self._tool_write_file,
                    args.get("path", ""),
                    args.get("content", ""),
                )
            elif name == "move_file":
                result = await asyncio.to_thread(
                    self._tool_move_file,
                    args.get("source", ""),
                    args.get("destination", ""),
                )
            elif name == "create_directory":
                result = await asyncio.to_thread(self._tool_create_directory, args.get("path", ""))

            # ----- Power tools dispatch -----
            elif name == "explore_pc":
                result = await asyncio.to_thread(
                    self._tool_explore_pc,
                    args.get("path", ""),
                    int(args.get("max_depth", 3) or 3),
                    args.get("file_glob", ""),
                    int(args.get("max_files", 50) or 50),
                    int(args.get("min_size", 0) or 0),
                    args.get("sort_by", "name"),
                )
            elif name == "smart_search":
                result = await asyncio.to_thread(
                    self._tool_smart_search,
                    args.get("filename", ""),
                    args.get("content", ""),
                    args.get("directory", ""),
                    bool(args.get("recursive", True)),
                    int(args.get("max_results", 100) or 100),
                )

            # ----- Internet dispatch -----
            elif name == "web_search":
                result = await asyncio.to_thread(
                    self._tool_web_search,
                    args.get("query", ""),
                    int(args.get("max_results", 5) or 5),
                )
            elif name == "fetch_url":
                result = await asyncio.to_thread(
                    self._tool_fetch_url,
                    args.get("url", ""),
                    int(args.get("max_chars", 8000) or 8000),
                )

            # ----- Productivity dispatch -----
            elif name == "set_timer":
                result = await asyncio.to_thread(
                    self._tool_set_timer,
                    int(args.get("seconds", 0) or 0),
                    args.get("label", "timer"),
                )
            elif name == "take_note":
                result = await asyncio.to_thread(
                    self._tool_take_note,
                    args.get("text", ""),
                    args.get("title", ""),
                )
            elif name == "calculate":
                result = await asyncio.to_thread(self._tool_calculate, args.get("expression", ""))
            elif name == "get_definition":
                result = await asyncio.to_thread(self._tool_get_definition, args.get("word", ""))
            elif name == "translate":
                result = await asyncio.to_thread(
                    self._tool_translate,
                    args.get("text", ""),
                    args.get("target_lang", ""),
                    args.get("source_lang", "en"),
                )

            # ----- System dispatch -----
            elif name == "list_processes":
                result = await asyncio.to_thread(
                    self._tool_list_processes,
                    args.get("name_filter", ""),
                    int(args.get("limit", 30) or 30),
                )
            elif name == "get_active_window":
                result = await asyncio.to_thread(self._tool_get_active_window)
            elif name == "focus_window":
                result = await asyncio.to_thread(self._tool_focus_window, args.get("title", ""))

            else:
                result = f"Unknown protocol: {name}"
        except Exception as e:
            result = f"Protocol error: {str(e)}"

        if self.session and self.session_ready.is_set():
            try:
                # Bound the send: if the API is stuck or the id mismatches and
                # the session silently drops the response, this would otherwise
                # hang the receive loop forever (and fire the watchdog after
                # 45s with a misleading "Neural response timeout" message).
                await asyncio.wait_for(
                    self.session.send_tool_response(
                        function_responses=[types.FunctionResponse(
                            name=name, id=call_id, response={"result": result}
                        )]
                    ),
                    timeout=10.0,
                )
            except asyncio.TimeoutError:
                self._emit_log("SYSTEM",
                    f"Tool response send for '{name}' timed out after 10s. "
                    f"Session may be stuck — re-linking.")
            except Exception as e:
                self._emit_log("SYSTEM", f"Tool response transmission failed: {e}")
        else:
            self._emit_log("SYSTEM",
                f"Tool '{name}' result not delivered (no active session).")

    def _tool_open_app(self, command: str):
        try:
            if os.name == 'nt':
                # os.startfile handles URLs and file paths but NOT bare exe names
                # on PATH. Resolve first so "notepad.exe" works.
                resolved = shutil.which(command)
                os.startfile(resolved if resolved else command)
            else:
                # subprocess.Popen resolves PATH and avoids shell `&` quirks
                # (Android/Termux sh, busybox, etc.).
                target = shutil.which(command) or command
                subprocess.Popen([target])
            return f"Launched {command}"
        except Exception as e:
            return f"Launch failed: {e}"

    def _tool_screenshot(self):
        img = pyautogui.screenshot()
        img.thumbnail((1024, 1024))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        data = buf.getvalue()
        if self.session and self.session_ready.is_set():
            self._schedule(
                self.session.send_realtime_input(media=types.Blob(mime_type="image/jpeg", data=data)),
                "Screenshot upload"
            )
        return "Screenshot captured and transmitted."

    def _tool_system_info(self):
        bat = psutil.sensors_battery()
        info = {
            "OS": platform.system(),
            "Version": platform.version(),
            "Processor": platform.processor(),
            "Cores": psutil.cpu_count(logical=False),
            "Logical_Cores": psutil.cpu_count(logical=True),
            "Memory": f"{round(psutil.virtual_memory().total / (1024**3), 2)} GB",
            "Battery": f"{bat.percent}%" if bat else "AC Power"
        }
        return json.dumps(info, indent=2)

    async def _tool_shell(self, command: str):
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            return stdout.decode('utf-8', errors='replace')[:2000]
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return "Command timed out (30s limit)."

    def _tool_weather(self, location: str = ""):
        """Fetch current weather for a location. Empty/'auto' = IP geolocation.

        Uses free public APIs (Open-Meteo + ip-api.com). No API key required.
        """
        try:
            loc = (location or "").strip().lower()
            if loc in _AUTO_LOCATION_TOKENS:
                lat, lon, label, source = (*_weather_ip_locate(), "IP geolocation")
            else:
                lat, lon, label = _weather_geocode(location)
                source = "geocoded"
            data = _weather_fetch(lat, lon)
            cw = data.get("current_weather") or {}
            temp = cw.get("temperature")
            wind = cw.get("windspeed")
            wcode = cw.get("weathercode")
            desc = _WEATHER_CODES.get(int(wcode) if wcode is not None else -1,
                                      f"conditions code {wcode}")
            # Open-Meteo provides is_day and time; surface them so the model can speak naturally.
            is_day = cw.get("is_day")
            t = cw.get("time")
            parts = [
                f"Weather for {label}",
                f"({source}, lat {lat:.2f}, lon {lon:.2f}):",
                f"{desc.capitalize()}.",
                f"Temperature {temp}\u00b0F,",
                f"wind {wind} mph.",
            ]
            if is_day == 0:
                parts.append("Nighttime.")
            elif is_day == 1:
                parts.append("Daytime.")
            if t:
                parts.append(f"Observed at {t} UTC.")
            return " ".join(parts)
        except (urllib.error.URLError, TimeoutError) as e:
            return f"Weather lookup failed (network error): {e}"
        except Exception as e:
            return f"Weather lookup failed: {e}"

    # ==============================
    # EXTENDED TOOLS
    # ==============================

    # ----- Filesystem -----
    def _tool_list_directory(self, path: str = ""):
        """List a directory's contents, sorted dirs-first."""
        try:
            target = Path(_expand_user_path(path)).resolve()
            if not target.exists():
                return f"Path does not exist: {target}"
            if not target.is_dir():
                return f"Not a directory: {target}"
        except Exception as e:
            return f"Invalid path: {e}"

        try:
            entries = list(target.iterdir())
        except PermissionError:
            return f"Permission denied: {target}"
        except Exception as e:
            return f"Cannot read directory: {e}"

        # Dirs first, then files; case-insensitive alpha within each group.
        dirs = sorted([e for e in entries if e.is_dir()], key=lambda p: p.name.lower())
        files = sorted([e for e in entries if not e.is_dir()], key=lambda p: p.name.lower())

        MAX_ENTRIES = 300
        shown_dirs = dirs[:MAX_ENTRIES]
        shown_files = files[:MAX_ENTRIES]
        truncated = len(dirs) + len(files) - len(shown_dirs) - len(shown_files)

        lines = [f"Contents of {target} ({len(dirs)} dirs, {len(files)} files):"]
        for d in shown_dirs:
            lines.append(f"  [DIR]  {d.name}")
        for f in shown_files:
            try:
                size = _format_size(f.stat().st_size)
            except OSError:
                size = "?"
            lines.append(f"  [FILE] {f.name}  ({size})")
        if truncated > 0:
            lines.append(f"  ... and {truncated} more entries (capped at {MAX_ENTRIES} per type)")
        return "\n".join(lines)

    def _tool_read_file(self, path: str):
        """Read a text file (capped at 50KB)."""
        try:
            target = Path(_expand_user_path(path)).resolve()
        except Exception as e:
            return f"Invalid path: {e}"
        if not target.exists():
            return f"File does not exist: {target}"
        if not target.is_file():
            return f"Not a file: {target}"
        try:
            size = target.stat().st_size
        except OSError as e:
            return f"Cannot stat file: {e}"

        if size > _FILE_READ_CAP_BYTES * 4:
            return (f"File is too large to read in one go ({_format_size(size)}). "
                    f"Cap is ~{_format_size(_FILE_READ_CAP_BYTES)}; use search_file_contents "
                    f"or open it in your editor instead.")

        try:
            with open(target, "rb") as f:
                raw = f.read(_FILE_READ_CAP_BYTES + 1)
        except PermissionError:
            return f"Permission denied: {target}"
        except Exception as e:
            return f"Read failed: {e}"

        truncated = len(raw) > _FILE_READ_CAP_BYTES
        if truncated:
            raw = raw[:_FILE_READ_CAP_BYTES]
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = raw.decode("utf-8", errors="replace")
                return (f"{text}\n\n[... file contains non-UTF-8 bytes; "
                        f"showing replacement chars. Original size: {_format_size(size)} ...]")
            except Exception as e:
                return f"File is not text (likely binary): {e}"

        header = f"--- {target} ({_format_size(size)}{', truncated' if truncated else ''}) ---"
        return f"{header}\n{text}"

    def _tool_search_files(self, pattern: str, directory: str = "", recursive: bool = False):
        """Find files by name glob pattern."""
        if not pattern:
            return "No pattern provided."
        try:
            base = Path(_expand_user_path(directory)).resolve()
        except Exception as e:
            return f"Invalid directory: {e}"
        if not base.exists():
            return f"Directory does not exist: {base}"
        if not base.is_dir():
            return f"Not a directory: {base}"

        try:
            glob_method = base.rglob if recursive else base.glob
            matches = sorted(glob_method(pattern))
        except Exception as e:
            return f"Search failed: {e}"

        MAX = 500
        shown = matches[:MAX]
        truncated = len(matches) - len(shown)
        if not matches:
            return f"No files matching '{pattern}' in {base}."
        lines = [f"{len(matches)} match(es) for '{pattern}' in {base}:"]
        for p in shown:
            try:
                kind = "[DIR]" if p.is_dir() else "[FILE]"
            except OSError:
                kind = "[?]"
            lines.append(f"  {kind} {p}")
        if truncated > 0:
            lines.append(f"  ... and {truncated} more matches (capped at {MAX})")
        return "\n".join(lines)

    def _tool_search_file_contents(self, query: str, directory: str = "",
                                   file_glob: str = "", recursive: bool = True):
        """Grep inside files for a regex pattern."""
        if not query:
            return "No query provided."
        try:
            regex = re.compile(query)
        except re.error as e:
            return f"Invalid regex: {e}"
        try:
            base = Path(_expand_user_path(directory)).resolve()
        except Exception as e:
            return f"Invalid directory: {e}"
        if not base.exists() or not base.is_dir():
            return f"Directory does not exist: {base}"

        # Build the candidate file list once.
        glob_method = base.rglob if recursive else base.glob
        pattern = file_glob or "*"
        try:
            candidates = [p for p in glob_method(pattern) if p.is_file()]
        except Exception as e:
            return f"Search failed: {e}"

        MAX_FILES = 2000
        MAX_HITS = 200
        candidates = candidates[:MAX_FILES]

        hits = []
        for fp in candidates:
            try:
                with open(fp, "rb") as f:
                    raw = f.read(_FILE_READ_CAP_BYTES * 4 + 1)
            except (PermissionError, OSError):
                continue
            if len(raw) > _FILE_READ_CAP_BYTES * 4:
                continue  # skip files too large to grep safely
            try:
                text = raw.decode("utf-8", errors="replace")
            except Exception:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    snippet = line[:_FILE_READ_MAX_LINE]
                    hits.append((fp, lineno, snippet))
                    if len(hits) >= MAX_HITS:
                        break
            if len(hits) >= MAX_HITS:
                break

        if not hits:
            return f"No matches for /{query}/ in {base}."

        lines = [f"{len(hits)} match(es) for /{query}/ in {base}:"]
        for fp, lineno, snippet in hits:
            lines.append(f"  {fp}:{lineno}: {snippet}")
        return "\n".join(lines)

    def _tool_write_file(self, path: str, content: str):
        """Create or overwrite a text file (auto-mkdir parents)."""
        if not path:
            return "No path provided."
        try:
            target = Path(_expand_user_path(path)).resolve()
        except Exception as e:
            return f"Invalid path: {e}"
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return f"Cannot create parent directory: {e}"
        try:
            target.write_text(content or "", encoding="utf-8")
        except PermissionError:
            return f"Permission denied writing to {target}"
        except Exception as e:
            return f"Write failed: {e}"
        size = target.stat().st_size if target.exists() else 0
        return f"Wrote {len(content or '')} characters ({_format_size(size)}) to {target}."

    def _tool_move_file(self, source: str, destination: str):
        """Move/rename a file or folder."""
        if not source or not destination:
            return "Both source and destination are required."
        try:
            src = Path(_expand_user_path(source)).resolve()
            dst = Path(_expand_user_path(destination)).resolve()
        except Exception as e:
            return f"Invalid path: {e}"
        if not src.exists():
            return f"Source does not exist: {src}"
        if dst.exists():
            return f"Destination already exists: {dst}"
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
        except Exception as e:
            return f"Move failed: {e}"
        return f"Moved {src} → {dst}."

    def _tool_create_directory(self, path: str):
        """Create a directory (and parents)."""
        if not path:
            return "No path provided."
        try:
            target = Path(_expand_user_path(path)).resolve()
        except Exception as e:
            return f"Invalid path: {e}"
        try:
            target.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return f"mkdir failed: {e}"
        return f"Directory ready: {target}."

    # ----- Power tools (explore + combined search) -----
    def _tool_explore_pc(self, path: str = "", max_depth: int = 3,
                         file_glob: str = "", max_files: int = 50,
                         min_size: int = 0, sort_by: str = "name"):
        """Recursively explore a directory tree with smart filtering.

        Returns a structured overview grouped by directory, showing file sizes
        and modification dates. Designed for broad PC reconnaissance.
        """
        try:
            root = Path(_expand_user_path(path)).resolve()
        except Exception as e:
            return f"Invalid path: {e}"
        if not root.exists():
            return f"Path does not exist: {root}"
        if not root.is_dir():
            return f"Not a directory: {root}"

        max_depth = max(1, min(10, max_depth))
        max_files = max(1, min(200, max_files))

        # Directories to skip (system junk, caches, etc.)
        _SKIP = {
            "$Recycle.Bin", "System Volume Information", "Recovery",
            "__pycache__", ".git", ".svn", "node_modules", ".cache",
            "Thumbs.db", "desktop.ini", ".DS_Store",
        }

        lines = [f"Exploring: {root} (depth={max_depth})"]
        total_files = 0
        total_dirs = 0
        total_size = 0

        def _walk(dir_path: Path, depth: int):
            nonlocal total_files, total_dirs, total_size
            if depth > max_depth:
                return
            if total_files > max_files * 10:  # hard safety cap
                return

            try:
                entries = list(dir_path.iterdir())
            except (PermissionError, OSError):
                return

            # Separate dirs and files
            dirs = []
            files = []
            for e in entries:
                if e.name in _SKIP or e.name.startswith('.'):
                    continue
                try:
                    if e.is_dir():
                        dirs.append(e)
                        total_dirs += 1
                    elif e.is_file():
                        files.append(e)
                except (PermissionError, OSError):
                    continue

            # Sort
            dirs.sort(key=lambda p: p.name.lower())
            if sort_by == "size":
                files.sort(key=lambda p: -(p.stat().st_size if p.exists() else 0))
            elif sort_by == "date":
                files.sort(key=lambda p: -(p.stat().st_mtime if p.exists() else 0))
            else:
                files.sort(key=lambda p: p.name.lower())

            # Filter
            if file_glob:
                files = [f for f in files if Path(f.name).match(file_glob)]
            if min_size > 0:
                files = [f for f in files if (f.stat().st_size if f.exists() else 0) >= min_size]

            # Format directory header (only show if it has content)
            if dirs or files:
                rel = str(dir_path.relative_to(root)) if dir_path != root else "."
                if rel == ".":
                    lines.append(f"\n[{root.name or str(root)}]")
                else:
                    lines.append(f"\n[{rel}]")

            # Show files (capped per directory)
            shown_files = files[:max_files]
            for f in shown_files:
                try:
                    st = f.stat()
                    size = _format_size(st.st_size)
                    total_size += st.st_size
                    ts = datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
                    lines.append(f"  {f.name}  ({size}, {ts})")
                except (OSError, PermissionError):
                    lines.append(f"  {f.name}  (?)")
                total_files += 1

            remaining = len(files) - len(shown_files)
            if remaining > 0:
                lines.append(f"  ... +{remaining} more files")

            # Recurse into subdirectories
            for d in dirs:
                _walk(d, depth + 1)

        _walk(root, 1)

        lines.append(f"\n--- Summary: {total_dirs} directories, {total_files} files, {_format_size(total_size)} total ---")
        if total_files > max_files * 10:
            lines.append(f"(results truncated at ~{max_files * 10} files for safety)")
        return "\n".join(lines)

    def _tool_smart_search(self, filename: str = "", content: str = "",
                           directory: str = "", recursive: bool = True,
                           max_results: int = 100):
        """Combined filename + content search in one powerful call.

        If both filename and content are provided, results must match BOTH.
        If only filename is provided, searches by filename glob.
        If only content is provided, searches inside all files.
        """
        if not filename and not content:
            return "Provide at least a filename pattern or content pattern to search for."

        try:
            base = Path(_expand_user_path(directory)).resolve()
        except Exception as e:
            return f"Invalid directory: {e}"
        if not base.exists() or not base.is_dir():
            return f"Directory does not exist: {base}"

        # Compile content regex if provided
        content_regex = None
        if content:
            try:
                content_regex = re.compile(content, re.IGNORECASE)
            except re.error as e:
                return f"Invalid content regex: {e}"

        glob_pattern = filename or "*"
        glob_method = base.rglob if recursive else base.glob

        try:
            candidates = sorted(glob_method(glob_pattern))
        except Exception as e:
            return f"Search failed: {e}"

        # Filter to files only
        candidates = [p for p in candidates if p.is_file()]

        max_results = max(1, min(500, max_results))
        hits = []
        files_searched = 0

        for fp in candidates:
            if len(hits) >= max_results:
                break
            files_searched += 1

            # If no content pattern, just report the file
            if not content_regex:
                try:
                    st = fp.stat()
                    size = _format_size(st.st_size)
                    ts = datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
                    hits.append(f"  {fp}  ({size}, {ts})")
                except (OSError, PermissionError):
                    hits.append(f"  {fp}")
                continue

            # Content search inside the file
            try:
                with open(fp, "rb") as f:
                    raw = f.read(_FILE_READ_CAP_BYTES * 4 + 1)
                if len(raw) > _FILE_READ_CAP_BYTES * 4:
                    continue  # skip oversized files
                text = raw.decode("utf-8", errors="replace")
            except (PermissionError, OSError):
                continue

            for lineno, line in enumerate(text.splitlines(), 1):
                if content_regex.search(line):
                    snippet = line.strip()[:_FILE_READ_MAX_LINE]
                    hits.append(f"  {fp}:{lineno}: {snippet}")
                    if len(hits) >= max_results:
                        break

        if not hits:
            parts = []
            if filename:
                parts.append(f"filename '{filename}'")
            if content:
                parts.append(f"content /{content}/")
            return f"No matches for {' + '.join(parts)} in {base}."

        parts = [f"{len(hits)} match(es) in {base} ({files_searched} files scanned):"]
        parts.extend(hits)
        return "\n".join(parts)

    # ----- Internet -----
    def _tool_web_search(self, query: str, max_results: int = 5):
        """DuckDuckGo HTML search."""
        return _web_search_ddg(query, max_results)

    def _tool_fetch_url(self, url: str, max_chars: int = 8000):
        """Fetch a URL and return extracted text."""
        return _fetch_url_text(url, max_chars)

    # ----- Productivity -----
    def _tool_set_timer(self, seconds: int, label: str = "timer"):
        """Schedule a one-shot timer with a beep + log line on fire."""
        try:
            seconds = int(seconds)
        except (TypeError, ValueError):
            return f"Invalid seconds value: {seconds!r}"
        if seconds < 1:
            return "Timer must be at least 1 second."
        if seconds > 86400:
            return "Timer cannot exceed 24 hours (86400 seconds)."
        label = (label or "timer").strip() or "timer"

        def _fire():
            try:
                self._emit_log("TIMER", f"\u23f0 {label} — time's up!")
            except Exception:
                pass
            try:
                if winsound:
                    for _ in range(3):
                        winsound.Beep(880, 250)
                        time.sleep(0.1)
            except Exception:
                pass

        timer = threading.Timer(seconds, _fire)
        timer.daemon = True
        self._active_timers.append(timer)
        timer.start()

        if seconds >= 3600 and seconds % 3600 == 0:
            pretty = f"{seconds // 3600} hour(s)"
        elif seconds >= 60 and seconds % 60 == 0:
            pretty = f"{seconds // 60} minute(s)"
        else:
            pretty = f"{seconds} second(s)"
        return f"Timer '{label}' set for {pretty}."

    def _tool_take_note(self, text: str, title: str = ""):
        """Append a markdown note to ~/Documents/JARVIS_Notes.md."""
        if not text:
            return "No note text provided."
        try:
            docs = Path.home() / "Documents"
            if not docs.exists():
                # Fallback to home directory if Documents is missing.
                docs = Path.home()
            notes_path = docs / "JARVIS_Notes.md"
        except Exception as e:
            return f"Cannot resolve notes path: {e}"

        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        heading = (title or "").strip() or f"Note @ {ts}"
        try:
            with open(notes_path, "a", encoding="utf-8") as f:
                f.write(f"\n## {heading}\n*{ts}*\n\n{text}\n")
        except PermissionError:
            return f"Permission denied writing to {notes_path}"
        except Exception as e:
            return f"Failed to save note: {e}"
        return f"Note saved to {notes_path}."

    def _tool_calculate(self, expression: str):
        """Safely evaluate a math expression."""
        return _safe_eval_math(expression)

    def _tool_get_definition(self, word: str):
        """Look up an English word's definition."""
        return _get_definition(word)

    def _tool_translate(self, text: str, target_lang: str, source_lang: str = "en"):
        """Translate text via MyMemory."""
        return _translate_text(text, target_lang, source_lang)

    # ----- System -----
    def _tool_list_processes(self, name_filter: str = "", limit: int = 30):
        """List running processes, sorted by CPU% desc."""
        try:
            limit = max(1, min(500, int(limit or 30)))
        except (TypeError, ValueError):
            limit = 30
        filt = (name_filter or "").lower().strip()

        rows = []
        for p in psutil.process_iter(attrs=["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                info = p.info
                name = info.get("name") or "?"
                if filt and filt not in name.lower():
                    continue
                cpu = info.get("cpu_percent") or 0.0
                mem = info.get("memory_percent") or 0.0
                rows.append((info.get("pid"), name, cpu, mem))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        # Sort by CPU% desc, then by name.
        rows.sort(key=lambda r: (-r[2], r[1].lower()))

        if not rows:
            return f"No processes matched filter '{filt}'." if filt else "No processes found."

        shown = rows[:limit]
        truncated = len(rows) - len(shown)
        lines = [f"{len(rows)} process(es)" + (f" matching '{filt}'" if filt else "") + ":"]
        lines.append(f"  {'PID':>7}  {'CPU%':>6}  {'MEM%':>6}  NAME")
        for pid, name, cpu, mem in shown:
            try:
                pid_str = f"{pid:>7}" if pid is not None else "      ?"
            except Exception:
                pid_str = "      ?"
            lines.append(f"  {pid_str}  {cpu:>6.1f}  {mem:>6.1f}  {name}")
        if truncated > 0:
            lines.append(f"  ... and {truncated} more (capped at {limit})")
        return "\n".join(lines)

    def _tool_get_active_window(self) -> str:
        """Return the title of the currently focused window (Windows-only)."""
        if os.name != "nt":
            return "[get_active_window is only supported on Windows]"
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return "[no foreground window]"
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return "[window has no title]"
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            return f"Active window: {buff.value}"
        except Exception as e:
            return f"Could not read active window: {e}"

    def _tool_focus_window(self, title: str) -> str:
        """Bring a window to front by title substring (Windows-only)."""
        if os.name != "nt":
            return "[focus_window is only supported on Windows]"
        if not title or not title.strip():
            return "No title provided."
        needle = title.lower().strip()

        try:
            user32 = ctypes.windll.user32
            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            found = {"hwnd": None, "title": ""}

            def _cb(hwnd, _lParam):
                try:
                    if not user32.IsWindowVisible(hwnd):
                        return True
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length == 0:
                        return True
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    if needle in buff.value.lower():
                        found["hwnd"] = hwnd
                        found["title"] = buff.value
                        return False  # stop enumeration
                except Exception:
                    pass
                return True

            user32.EnumWindows(EnumWindowsProc(_cb), 0)
            if found["hwnd"] is None:
                return f"No visible window with title containing '{title}'."

            # Restore if minimized, then bring to front.
            if user32.IsIconic(found["hwnd"]):
                user32.ShowWindow(found["hwnd"], 9)  # SW_RESTORE
            user32.SetForegroundWindow(found["hwnd"])
            return f"Focused window: {found['title']}"
        except Exception as e:
            return f"focus_window failed: {e}"


# ==========================================
# WEATHER (free public APIs, no key required)
# ==========================================
# WMO weather interpretation codes used by Open-Meteo.
_WEATHER_CODES = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    56: "light freezing drizzle",
    57: "dense freezing drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "heavy freezing rain",
    71: "slight snowfall",
    73: "moderate snowfall",
    75: "heavy snowfall",
    77: "snow grains",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    85: "slight snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}

# Phrases that mean "use my current location".
_AUTO_LOCATION_TOKENS = frozenset({
    "", "auto", "current", "here", "my location", "me", "my city", "where i am",
})


def _http_get_json(url: str, timeout: float = 6.0) -> dict:
    """Synchronous HTTP GET that returns parsed JSON. Raises on any failure."""
    req = urllib.request.Request(url, headers={"User-Agent": "JARVIS/2.0 (+local-assistant)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        if not raw:
            raise RuntimeError("empty response")
        return json.loads(raw.decode("utf-8", errors="replace"))


def _weather_ip_locate() -> tuple:
    """Return (lat, lon, label) for the user's public IP. No key required."""
    data = _http_get_json(
        "http://ip-api.com/json/?fields=status,city,lat,lon,regionName,country"
    )
    if data.get("status") != "success":
        raise RuntimeError(f"IP geolocation failed: {data.get('message', 'unknown error')}")
    if "lat" not in data or "lon" not in data:
        raise RuntimeError("IP geolocation returned no coordinates")
    city = data.get("city") or "?"
    region = data.get("regionName") or "?"
    country = data.get("country") or "?"
    parts = [p for p in (city, region, country) if p and p != "?"]
    label = ", ".join(parts) if parts else "your location"
    return (float(data["lat"]), float(data["lon"]), label)


def _weather_geocode(name: str) -> tuple:
    """Return (lat, lon, label) for a place name via Open-Meteo geocoding (free)."""
    q = urllib.parse.quote(name.strip())
    url = f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=1&language=en&format=json"
    data = _http_get_json(url)
    results = data.get("results") or []
    if not results:
        raise RuntimeError(f"Location not found: '{name}'")
    r = results[0]
    label = ", ".join(x for x in (r.get("name"), r.get("admin1"), r.get("country")) if x)
    return (float(r["latitude"]), float(r["longitude"]), label or name)


def _weather_fetch(lat: float, lon: float) -> dict:
    """Fetch current weather from Open-Meteo (free, no key). Fahrenheit + mph."""
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&current_weather=true"
        f"&temperature_unit=fahrenheit"
        f"&windspeed_unit=mph"
    )
    return _http_get_json(url)


# ==========================================
# EXTENDED TOOL HELPERS (filesystem, web, system, math)
# ==========================================

# Read cap for read_file (50KB), write cap note, etc.
_FILE_READ_CAP_BYTES = 50_000
_FILE_READ_MAX_LINE = 2_000          # max bytes per line to keep one giant line from blowing the cap
_FETCH_MAX_BYTES = 5_000_000         # 5MB safety cap on any HTTP response
_SEARCH_MAX_RESULTS = 10
_HTTP_TIMEOUT = 10.0

# Math: whitelisted function names from the math module + safe constants.
_MATH_SAFE_FUNCS = {
    "sqrt", "sin", "cos", "tan", "asin", "acos", "atan", "atan2",
    "log", "log10", "log2", "exp", "ceil", "floor", "fabs",
    "factorial", "gcd", "pow", "radians", "degrees",
    "cosh", "sinh", "tanh", "hypot",
}
_MATH_SAFE_NAMES = {"pi": math.pi, "e": math.e, "tau": math.tau}


class _HTMLTextExtractor(html.parser.HTMLParser):
    """Convert HTML to readable plain text. Skips script/style/iframe/svg."""
    _BLOCK_TAGS = {
        "p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6",
        "tr", "td", "th", "blockquote", "pre", "section", "article", "header", "footer",
    }
    _SKIP_TAGS = {"script", "style", "noscript", "iframe", "svg", "head"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._chunks = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._SKIP_TAGS:
            self._skip_depth += 1
        if self._skip_depth == 0 and tag.lower() in self._BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in self._SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        if self._skip_depth == 0 and tag.lower() in self._BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data):
        if self._skip_depth == 0:
            self._chunks.append(data)

    def get_text(self) -> str:
        text = "".join(self._chunks)
        text = re.sub(r"\n\s*\n+", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()


def _is_safe_url(url: str) -> tuple:
    """Return (ok, reason). Blocks non-http(s), localhost, and private/loopback IPs.
    Resolves hostnames so DNS-rebinding and direct private IPs are caught."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return (False, f"scheme '{parsed.scheme}' not allowed (use http or https)")
        host = parsed.hostname
        if not host:
            return (False, "URL has no host")
        if host.lower() in ("localhost", "ip6-localhost", "ip6-loopback"):
            return (False, "localhost blocked for security")

        # If host is an IP literal, check directly. Otherwise resolve and check every addr.
        try:
            ip = ipaddress.ip_address(host)
            addresses = [ip]
        except ValueError:
            try:
                infos = socket.getaddrinfo(host, None)
            except socket.gaierror as e:
                return (False, f"DNS resolution failed: {e}")
            addresses = []
            for info in infos:
                try:
                    addresses.append(ipaddress.ip_address(info[4][0]))
                except (ValueError, IndexError):
                    pass
            if not addresses:
                return (False, "no addresses resolved for host")

        for ip in addresses:
            if (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
                return (False, f"address {ip} is private/loopback — blocked")

        return (True, "")
    except Exception as e:
        return (False, f"URL validation error: {e}")


def _http_get_bytes(url: str, timeout: float = _HTTP_TIMEOUT,
                    max_bytes: int = _FETCH_MAX_BYTES) -> bytes:
    """GET a URL and return raw bytes (capped). Raises on any failure."""
    req = urllib.request.Request(url, headers={"User-Agent": "JARVIS/2.0 (+local-assistant)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        # Read in chunks so we can stop as soon as we hit max_bytes.
        out = bytearray()
        while len(out) < max_bytes + 1:
            chunk = resp.read(65536)
            if not chunk:
                break
            out.extend(chunk)
            if len(out) > max_bytes:
                break
        return bytes(out[:max_bytes])


def _http_get_text(url: str, timeout: float = _HTTP_TIMEOUT,
                   max_bytes: int = _FETCH_MAX_BYTES) -> str:
    """GET a URL and return decoded text. Cap response at max_bytes."""
    raw = _http_get_bytes(url, timeout=timeout, max_bytes=max_bytes)
    return raw.decode("utf-8", errors="replace")


def _expand_user_path(p: str) -> str:
    """Expand ~ to the user's home directory and normalize."""
    if not p:
        return str(Path.home())
    return os.path.expanduser(os.path.expandvars(p))


def _format_size(n: int) -> str:
    """Human-readable byte size."""
    n = max(0, int(n))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024.0:
            return f"{n:.1f}{unit}" if unit != "B" else f"{n}B"
        n /= 1024.0
    return f"{n:.1f}PB"


def _web_search_ddg(query: str, max_results: int = 5) -> str:
    """Search DuckDuckGo HTML endpoint (no API key) and return top results."""
    max_results = max(1, min(_SEARCH_MAX_RESULTS, int(max_results or 5)))
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    # DuckDuckGo bot-blocks generic UAs; use a browser UA only for the search.
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                 "AppleWebKit/537.36 (KHTML, like Gecko) "
                 "Chrome/120.0.0.0 Safari/537.36"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            html_text = resp.read(_FETCH_MAX_BYTES).decode("utf-8", errors="replace")
    except Exception as e:
        return f"Search failed: {e}"

    title_pat = re.compile(
        r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    snippet_pat = re.compile(
        r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    tag_pat = re.compile(r"<[^>]+>")

    titles = title_pat.findall(html_text)
    snippets = snippet_pat.findall(html_text)

    results = []
    for i, (link, title_html) in enumerate(titles[:max_results]):
        title = html.unescape(tag_pat.sub("", title_html)).strip()
        if not title:
            continue
        snippet = ""
        if i < len(snippets):
            snippet = html.unescape(tag_pat.sub("", snippets[i])).strip()
        # DuckDuckGo wraps result URLs in a redirector; unwrap uddg=... if present.
        actual_url = link
        m = re.search(r"uddg=([^&]+)", link)
        if m:
            actual_url = urllib.parse.unquote(m.group(1))
        results.append(f"{len(results) + 1}. {title}\n   {actual_url}\n   {snippet}")

    if not results:
        return f"No results found for '{query}'."
    return f"Top {len(results)} result(s) for '{query}':\n\n" + "\n\n".join(results)


def _fetch_url_text(url: str, max_chars: int = 8000) -> str:
    """Fetch a URL and return extracted readable text, capped at max_chars."""
    max_chars = max(100, min(50000, int(max_chars or 8000)))
    ok, reason = _is_safe_url(url)
    if not ok:
        return f"URL rejected: {reason}"
    try:
        raw = _http_get_bytes(url, timeout=_HTTP_TIMEOUT, max_bytes=_FETCH_MAX_BYTES)
    except (urllib.error.URLError, TimeoutError) as e:
        return f"Fetch failed (network error): {e}"
    except Exception as e:
        return f"Fetch failed: {e}"

    # Quick content-type sniff to avoid parsing images/binary as HTML.
    head = raw[:512].lower()
    if b"<html" in head or b"<!doctype" in head or b"<head" in head or b"<body" in head:
        try:
            parser = _HTMLTextExtractor()
            parser.feed(raw.decode("utf-8", errors="replace"))
            text = parser.get_text()
        except Exception as e:
            return f"HTML parse failed: {e}"
    else:
        # Plain text response
        text = raw.decode("utf-8", errors="replace")

    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n[... truncated at {max_chars} characters ...]"
    return text or "[empty response]"


def _get_definition(word: str) -> str:
    """Look up an English word via the free dictionaryapi.dev."""
    word = (word or "").strip().lower()
    if not word:
        return "No word provided."
    if not re.fullmatch(r"[a-zA-Z\-']+", word):
        return f"'{word}' is not a valid English word to look up."
    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{urllib.parse.quote(word)}"
    try:
        raw = _http_get_text(url, timeout=_HTTP_TIMEOUT)
        data = json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return f"No definition found for '{word}'."
        return f"Dictionary lookup failed (HTTP {e.code}): {e.reason}"
    except Exception as e:
        return f"Dictionary lookup failed: {e}"

    if not isinstance(data, list) or not data:
        return f"No definition found for '{word}'."

    parts = [f"Definitions of '{data[0].get('word', word)}':"]
    phonetic = data[0].get("phonetic")
    if phonetic:
        parts.append(f"  Pronunciation: {phonetic}")

    for entry in data[:3]:
        for meaning in entry.get("meanings", [])[:2]:
            pos = meaning.get("partOfSpeech", "")
            defs = meaning.get("definitions", [])
            for i, d in enumerate(defs[:3], 1):
                definition = d.get("definition", "").strip()
                example = d.get("example", "").strip()
                parts.append(f"  {pos}. {i}. {definition}")
                if example:
                    parts.append(f"     e.g. {example}")
    return "\n".join(parts)


def _translate_text(text: str, target_lang: str, source_lang: str = "en") -> str:
    """Translate via MyMemory free API (no key, ~5000 chars/day per IP)."""
    text = (text or "").strip()
    if not text:
        return "No text provided to translate."
    if not target_lang:
        return "No target language provided."
    source = (source_lang or "en").strip().lower()
    target = target_lang.strip().lower()
    if source == "auto":
        source = "en"  # MyMemory doesn't have a true auto-detect; default to en
    url = (
        "https://api.mymemory.translated.net/get?"
        + urllib.parse.urlencode({"q": text, "langpair": f"{source}|{target}"})
    )
    try:
        raw = _http_get_text(url, timeout=_HTTP_TIMEOUT)
        data = json.loads(raw) if raw else {}
    except Exception as e:
        return f"Translation failed: {e}"
    response = data.get("responseData") or {}
    translated = response.get("translatedText", "").strip()
    if not translated:
        return f"Translation returned no result for '{text}'."
    # MyMemory sometimes encodes the response as a URL-encoded string; fix common ones.
    try:
        translated = html.unescape(translated)
    except Exception:
        pass
    return f"{source} → {target}: {translated}"


def _safe_eval_math(expr: str) -> str:
    """Evaluate a math expression with AST whitelisting. No names outside math.* allowed."""
    expr = (expr or "").strip()
    if not expr:
        return "Empty expression."
    # Allow users to type '^' for power.
    expr = expr.replace("^", "**")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        return f"Invalid expression: {e.msg}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Expression):
            continue
        elif isinstance(node, (ast.BinOp, ast.UnaryOp, ast.Load,
                               ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv,
                               ast.Mod, ast.Pow, ast.USub, ast.UAdd)):
            continue
        elif isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)):
                return f"Only numbers allowed; got {type(node.value).__name__}"
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _MATH_SAFE_FUNCS:
                fname = getattr(node.func, "id", "?")
                return f"Function '{fname}' not allowed"
        elif isinstance(node, ast.Name):
            if node.id in _MATH_SAFE_FUNCS or node.id in _MATH_SAFE_NAMES:
                continue
            return f"Unknown identifier: '{node.id}'"
        else:
            return f"Disallowed construct: {type(node).__name__}"

    safe_locals = dict(_MATH_SAFE_NAMES)
    for name in _MATH_SAFE_FUNCS:
        if hasattr(math, name):
            safe_locals[name] = getattr(math, name)

    try:
        result = eval(compile(tree, "<math>", "eval"),
                      {"__builtins__": {}}, safe_locals)
    except Exception as e:
        return f"Evaluation error: {e}"

    if isinstance(result, float):
        if math.isnan(result):
            return "NaN"
        if math.isinf(result):
            return "Infinity" if result > 0 else "-Infinity"
        if result.is_integer() and abs(result) < 1e16:
            return str(int(result))
        return f"{result:.10g}"
    return str(result)


# ==========================================
# MAIN WINDOW
# ==========================================
class JarvisMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("J.A.R.V.I.S. Core Matrix")
        self.resize(1450, 900)
        self.ui_ready = False
        self.core: Optional[JarvisCore] = None

        self.view = QWebEngineView()
        self.setCentralWidget(self.view)
        self.view.page().profile().setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)

        self.bridge = PyBridge(self)
        self.channel = QWebChannel()
        self.channel.registerObject("pyBridge", self.bridge)
        self.view.page().setWebChannel(self.channel)
        self.view.setHtml(UI_HTML)

        self.telemetry = TelemetryWorker()
        self.telemetry.stats_updated.connect(self._update_stats)
        self.telemetry.start()

    def start_core(self):
        if not self.core:
            self.core = JarvisCore(self.bridge)

    def _update_stats(self, cpu, mem_pct, disk_pct, net_in, net_out, win_title):
        if self.ui_ready and self.core:
            # QWebChannel handles Python→JS string serialization automatically.
            # Manual escaping (for JS string literals) was corrupting titles
            # with backslashes or quotes in the UI.
            self.bridge.telemetryUpdated.emit(cpu, mem_pct, disk_pct, net_in, net_out, win_title)

    def set_mic_active(self, active):
        if self.core:
            self.core.set_mic_active(active)

    def closeEvent(self, event):
        if self.core:
            self.core.stop()
        self.telemetry.requestInterruption()
        self.telemetry.quit()
        self.telemetry.wait(3000)
        super().closeEvent(event)


if __name__ == "__main__":
    sys.argv.append("--no-sandbox")
    app = QApplication(sys.argv)
    win = JarvisMainWindow()
    win.show()
    sys.exit(app.exec())
