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
from pathlib import Path
from typing import List, Optional, Callable

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

MAX_HISTORY = 20
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
Provide concise, high-signal responses. Accuracy and operational efficiency are paramount.
When using tools, confirm actions briefly and report outcomes.

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
        body::after {
            content: ''; position: absolute; inset: 0;
            background: repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.15) 2px, rgba(0,0,0,0.15) 4px);
            pointer-events: none; z-index: 999; opacity: 0.3;
        }

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
        .reactor-wrap {
            width: 300px; height: 300px; position: relative; display: flex; align-items: center; justify-content: center;
        }
        .reactor-svg {
            width: 100%; height: 100%; filter: drop-shadow(0 0 25px rgba(0, 212, 255, 0.3));
        }
        .ring-outer { transform-origin: center; animation: spin-cw 25s linear infinite; }
        .ring-mid { transform-origin: center; animation: spin-ccw 18s linear infinite; }
        .ring-inner { transform-origin: center; animation: spin-cw 12s linear infinite; }
        .ring-hex { transform-origin: center; animation: spin-ccw 35s linear infinite; }
        .core-glow { transform-origin: center; animation: core-pulse 3s ease-in-out infinite; }
        @keyframes spin-cw { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes spin-ccw { from { transform: rotate(0deg); } to { transform: rotate(-360deg); } }
        @keyframes core-pulse {
            0%, 100% { transform: scale(1); opacity: 0.7; }
            50% { transform: scale(1.15); opacity: 1; }
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
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js" async></script>
...
    <script>
        let bridge = null;
        let activeJarvisMsg = null;
        let jarvisBuffer = "";
        let micOn = false;
        let cmdHistory = [];
        let cmdIndex = -1;
        let userScrolled = false;

        if (typeof marked !== 'undefined') marked.setOptions({ gfm: true, breaks: true });
        function md(text) {
            if (typeof marked === 'undefined') return text;
            return DOMPurify.sanitize(marked.parse(text));
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
            setTimeout(() => document.getElementById('boot-overlay').classList.add('fade-out'), 600);
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
            document.getElementById('cpu-bar').style.width = Math.min(100, cpu) + '%';
            document.getElementById('cpu-txt').innerText = cpu + '%';
            let memPct = Math.min(100, Math.round(mem / 100000 * 100));
            document.getElementById('mem-bar').style.width = memPct + '%';
            document.getElementById('mem-txt').innerText = formatTokens(mem) + ' tokens';
            let diskPct = Math.min(100, Math.round(disk / 200000 * 100));
            document.getElementById('disk-bar').style.width = diskPct + '%';
            document.getElementById('disk-txt').innerText = formatBytes(disk);
            document.getElementById('net-in').innerText = netIn;
            document.getElementById('net-out').innerText = netOut;
            document.getElementById('focus-win').innerText = win;
        }
        function setStatus(status) {
            const banner = document.getElementById('center-status');
            const dot = document.getElementById('header-dot');
            const label = document.getElementById('header-label');
            const core = document.getElementById('reactor-core');
            const rings = document.querySelectorAll('.reactor-svg circle[class^="ring-"]');
            banner.innerText = 'CORE STATUS: ' + status;
            label.innerText = status;
            let color = '#00d4ff'; let speed = '25s';
            banner.className = 'status-banner';
            if (status === 'THINKING') { color = '#ffb703'; speed = '3s'; banner.className = 'status-banner thinking'; }
            else if (status === 'LISTENING') { color = '#00f5d4'; speed = '8s'; banner.className = 'status-banner listening'; }
            else if (status === 'SPEAKING') { color = '#00a8ff'; speed = '5s'; banner.className = 'status-banner speaking'; }
            else if (status === 'OFFLINE' || status === 'RECONNECTING' || status === 'CONNECTING') {
                color = '#ff4d4d'; speed = '60s'; banner.className = 'status-banner offline';
            }
            dot.style.background = color; dot.style.boxShadow = '0 0 10px ' + color;
            if (core) { core.style.fill = color; core.style.filter = 'drop-shadow(0 0 15px ' + color + ')'; }
            const rgb = color.startsWith('#') ? [
                parseInt(color.slice(1,3),16), parseInt(color.slice(3,5),16), parseInt(color.slice(5,7),16)
            ] : [0,212,255];
            rings.forEach(r => r.style.stroke = `rgba(${rgb[0]},${rgb[1]},${rgb[2]},0.3)`);
            rings.forEach(r => r.style.animationDuration = speed);
        }
        function showToast(msg, type='info') {
            const c = document.getElementById('toast-container');
            const t = document.createElement('div');
            t.className = 'toast ' + type; t.innerText = msg;
            c.appendChild(t);
            requestAnimationFrame(() => t.classList.add('show'));
            setTimeout(() => { t.classList.remove('show'); setTimeout(() => t.remove(), 400); }, 4000);
        }
        function appendLog(sender, text, stream=false) {
            const area = document.getElementById('log-area');
            if (!area) return;
            if (sender === 'JARVIS' && activeJarvisMsg && stream) {
                jarvisBuffer += text;
                activeJarvisMsg.querySelector('.msg-body').innerHTML = md(jarvisBuffer);
                activeJarvisMsg.querySelectorAll('pre code').forEach(b => {
                    if (!b.dataset.hl) { hljs.highlightElement(b); b.dataset.hl = '1'; addCopyBtn(b); }
                });
                if (!userScrolled) area.scrollTop = area.scrollHeight;
                return;
            }
            const div = document.createElement('div');
            const t = new Date().toTimeString().split(' ')[0];
            let cls = 'msg'; let sname = ''; let scolor = '';
            if (sender === 'YOU') { cls += ' msg-user'; sname = 'OPERATOR'; scolor = '#ffb703'; activeJarvisMsg = null; jarvisBuffer = ''; }
            else if (sender === 'JARVIS') { cls += ' msg-jarvis'; sname = 'J.A.R.V.I.S.'; scolor = '#00d4ff'; }
            else if (sender === 'SYSTEM') { cls += ' msg-system'; sname = 'SYSTEM'; scolor = '#ff4d4d'; activeJarvisMsg = null; jarvisBuffer = ''; }
            else { cls += ' msg-action'; sname = 'SYSTEM'; scolor = '#00f5d4'; activeJarvisMsg = null; jarvisBuffer = ''; }
            div.className = cls;
            const bodyHtml = sender === 'JARVIS' ? md(text) : (sender === 'ACTION' ? '>> ' + esc(text) : esc(text));
            div.innerHTML = `<div class="msg-header"><span class="msg-sender" style="color:${scolor}">${sname}</span><span class="msg-time">${t}</span></div><div class="msg-body">${bodyHtml}</div>`;
            if (sender === 'JARVIS') {
                activeJarvisMsg = div; jarvisBuffer = text;
                div.querySelectorAll('pre code').forEach(b => { hljs.highlightElement(b); b.dataset.hl = '1'; addCopyBtn(b); });
            }
            area.appendChild(div);
            if (!userScrolled) area.scrollTop = area.scrollHeight;
        }
        function sendCmd() {
            const inp = document.getElementById('cmd-input');
            const v = inp.value.trim(); if (!v) return;
            cmdHistory.push(v); cmdIndex = cmdHistory.length;
            appendLog('YOU', v); inp.value = ''; setStatus('THINKING');
            if (bridge) bridge.submitCommand(v);
        }
        function changeModel(m) {
            if (bridge) { bridge.changeModel(m); appendLog('ACTION', 'Rerouting neural path to ' + m + '...'); setStatus('RECONNECTING'); }
        }
        function toggleVoice(on) {
            const btn = document.getElementById('mic-btn');
            if (bridge) bridge.setVoiceModeEnabled(on.toString());
            if (on) {
                btn.disabled = false; btn.classList.remove('mic-btn-inactive');
                appendLog('ACTION', 'Voice synthesis enabled.'); setStatus('READY');
            } else {
                if (micOn) toggleMic();
                btn.disabled = true; btn.classList.add('mic-btn-inactive');
                appendLog('ACTION', 'Voice synthesis disabled.'); setStatus('READY');
            }
        }
        function toggleMic() {
            micOn = !micOn; const btn = document.getElementById('mic-btn'); const sp = btn.querySelector('span');
            if (bridge) bridge.setMicActive(micOn);
            if (micOn) { btn.classList.add('mic-active'); sp.innerText = 'LISTENING'; setStatus('LISTENING'); appendLog('ACTION', 'Audio capture active.'); }
            else { btn.classList.remove('mic-active'); sp.innerText = 'MIC'; setStatus('READY'); appendLog('ACTION', 'Audio capture terminated.'); }
        }
        function reconnectCore() {
            if (bridge) { bridge.triggerReconnect(); appendLog('ACTION', 'Re-establishing neural link...'); setStatus('RECONNECTING'); }
        }
        function resetCore() {
            if (bridge) { bridge.resetSession(); appendLog('ACTION', 'Neural matrix reset initiated.'); setStatus('RECONNECTING'); }
        }
        function clearLog() { document.getElementById('log-area').innerHTML = ''; appendLog('ACTION', 'Log buffer purged.'); }
        function updateModelBadge(model, isFallback) {
            const sel = document.getElementById('model-select');
            const badge = document.getElementById('model-badge');
            if (sel) sel.value = model;
            if (badge) { badge.innerText = isFallback ? 'FALLBACK' : ''; badge.style.display = isFallback ? 'inline-block' : 'none'; }
        }
        function updateAudioLevel(level) {
            const canvas = document.getElementById('audio-viz');
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            const w = canvas.width, h = canvas.height;
            ctx.clearRect(0, 0, w, h);
            const bars = 30; const gap = 2; const barW = (w - (bars - 1) * gap) / bars;
            for (let i = 0; i < bars; i++) {
                const decay = Math.abs(Math.sin(Date.now() / 200 + i)) * 0.5 + 0.5;
                const height = Math.min(h, level * h * decay * 1.5);
                const x = i * (barW + gap);
                const y = h - height;
                const grad = ctx.createLinearGradient(0, y, 0, h);
                grad.addColorStop(0, 'rgba(0,212,255,0.9)');
                grad.addColorStop(1, 'rgba(0,212,255,0.1)');
                ctx.fillStyle = grad;
                ctx.fillRect(x, y, barW, height);
            }
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            const inp = document.getElementById('cmd-input');
            if (document.activeElement === inp) {
                if (e.key === 'Enter') { e.preventDefault(); sendCmd(); }
                if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    if (cmdIndex > 0) { cmdIndex--; inp.value = cmdHistory[cmdIndex]; }
                }
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    if (cmdIndex < cmdHistory.length - 1) { cmdIndex++; inp.value = cmdHistory[cmdIndex]; }
                    else { cmdIndex = cmdHistory.length; inp.value = ''; }
                }
                if (e.key === 'Escape') { inp.value = ''; }
            }
        });

        // Scroll detection
        document.getElementById('log-area').addEventListener('scroll', (e) => {
            const el = e.target;
            userScrolled = el.scrollHeight - el.scrollTop - el.clientHeight > 50;
        });

        // Boot safety: always dismiss overlay after 3 seconds no matter what
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(setBootDone, 3000);
    initBridge();
});

function initBridge() {
    if (typeof qt === "undefined" || !qt.webChannelTransport) {
        setTimeout(initBridge, 150);
        return;
    }
    new QWebChannel(qt.webChannelTransport, function(ch) {
        bridge = ch.objects.pyBridge;
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
            <div class="panel-label">SYSTEM TELEMETRY <span>// LIVE</span></div>
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
                    <circle cx="100" cy="100" r="95" fill="none" stroke="rgba(0,212,255,0.06)" stroke-width="1" />
                    <circle cx="100" cy="100" r="90" fill="none" stroke="rgba(0,212,255,0.15)" stroke-width="1.5" stroke-dasharray="4 8" class="ring-hex" />
                    <circle cx="100" cy="100" r="82" fill="none" stroke="rgba(0,212,255,0.2)" stroke-width="2" stroke-dasharray="10 14" class="ring-outer" />
                    <circle cx="100" cy="100" r="72" fill="none" stroke="rgba(0,212,255,0.08)" stroke-width="1" />
                    <circle cx="100" cy="100" r="64" fill="none" stroke="rgba(0,212,255,0.25)" stroke-width="2.5" stroke-dasharray="6 6" class="ring-mid" />
                    <circle cx="100" cy="100" r="54" fill="none" stroke="rgba(0,212,255,0.1)" stroke-width="1" />
                    <circle cx="100" cy="100" r="46" fill="none" stroke="rgba(0,212,255,0.3)" stroke-width="2" stroke-dasharray="12 4" class="ring-inner" />
                    <circle cx="100" cy="100" r="36" fill="none" stroke="rgba(0,212,255,0.15)" stroke-width="1" />
                    <circle cx="100" cy="100" r="28" fill="url(#coreGrad)" class="core-glow" id="reactor-core" />
                    <circle cx="100" cy="100" r="14" fill="#fff" opacity="0.9" />
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
        </div>
    </main>
    <footer>
        <div class="input-row">
            <input type="text" id="cmd-input" placeholder="Awaiting command, Sir..." autocomplete="off">
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
    stats_updated = pyqtSignal(int, int, int, str, str, str)

    def __init__(self):
        super().__init__()
        self.last_net = None
        self.last_time = time.time()

    def run(self):
        while not self.isInterruptionRequested():
            try:
                cpu = int(psutil.cpu_percent(interval=None))
                mem = int(psutil.virtual_memory().percent)
                disk = self._get_disk_pct()
                now = time.time()
                dt = now - self.last_time
                net_in, net_out = self._get_net(dt)
                self.last_time = now
                self.stats_updated.emit(cpu, mem, disk, net_in, net_out, get_active_window_title())
            except Exception:
                pass
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
    telemetryUpdated = pyqtSignal(int, int, int, str, str, str)
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

        self.history: List[types.Content] = []
        self.pending_messages: List[str] = []
        self._response_buffer = ""
        self._response_lock = threading.Lock()
        self.context_tokens = 0
        self.context_chars = 0

        self._api_key = self._load_api_key()
        if self._api_key:
            self.client = genai.Client(api_key=self._api_key)

        self.thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._main_loop())
        except Exception as e:
            print(f"[JarvisCore] Loop fatal: {e}")

    async def _main_loop(self):
        self.set_state("BOOT")
        await asyncio.sleep(1.5)
        if not self.client:
            self._emit_log("SYSTEM", "API Key not found. Please configure api_keys.json or set GEMINI_API_KEY.")
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
        self.history.append(types.Content(parts=[types.Part.from_text(text=text)], role=role))
        self.context_chars += len(text)
        self.context_tokens += max(1, len(text) // 4)
        while len(self.history) > MAX_HISTORY:
            removed = self.history.pop(0)
            txt = ''.join(p.text for p in removed.parts if hasattr(p, 'text') and p.text)
            self.context_chars -= len(txt)
            self.context_tokens -= max(1, len(txt) // 4)

    def dispatch_text(self, text: str):
        self._emit_log("YOU", text)
        with self._response_lock:
            self._response_buffer = ""
        if not self.session_ready.is_set() or not self.session:
            self.pending_messages.append(text)
            self._emit_log("SYSTEM", "Connection unstable. Command buffered for re-link.")
            return
        self._add_history("user", text)
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns=[types.Content(parts=[types.Part.from_text(text=text)], role='user')],
                turn_complete=True
            ), self.loop
        )
        self.set_state("THINKING")

    def send_audio_chunk(self, data: bytes):
        if self.session and self.session_ready.is_set() and self.mic_active and not self._shutdown:
            asyncio.run_coroutine_threadsafe(
                self.session.send_realtime_input(
                    media=types.Blob(mime_type="audio/pcm;rate=16000", data=data)
                ), self.loop
            )

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
            asyncio.run_coroutine_threadsafe(self._safe_close(), self.loop)

    async def _safe_close(self):
        if self.session:
            try:
                await self.session.close()
            except Exception:
                pass
            self.session = None
            self.session_ready.clear()

    def reset_session(self):
        self.history.clear()
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
        self.audio_player.stop()
        if self.audio_recorder:
            self.audio_recorder.stop()
        if self.session:
            asyncio.run_coroutine_threadsafe(self._safe_close(), self.loop)
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
                    temperature=0.4,
                )
                if self.resumption_token:
                    config.session_resumption = types.SessionResumptionConfig(handle=self.resumption_token)

                async with self.client.aio.live.connect(model=model, config=config) as session:
                    self.session = session
                    self.session_ready.set()

                    # Context restoration
                    if self.history and not self.resumption_token:
                        try:
                            context_turns = self.history[-MAX_HISTORY:]
                            await session.send_client_content(turns=context_turns, turn_complete=False)
                            self._emit_log("SYSTEM", f"Context restored: {len(context_turns)} turns.")
                        except Exception as e:
                            self._emit_log("SYSTEM", f"Context restore warning: {str(e)[:80]}")

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
        elif any(x in err for x in ["500", "502", "503", "504", "internal", "unavailable", "deadline exceeded"]):
            err_type = "SERVER"

        if err_type == "AUTH":
            self._emit_log("SYSTEM", f"Authentication failed. Check your API key. ({str(e)[:60]})")
            self.set_state("OFFLINE")
            await self._wait_shutdown(30)
            return
        elif err_type == "RATE":
            self.reconnect_backoff = min(self.reconnect_backoff * 2, self.max_backoff)
            self._emit_log("SYSTEM", f"Rate limited. Backing off {self.reconnect_backoff:.1f}s...")
        elif err_type == "MODEL":
            self.current_model_idx += 1
            if self.current_model_idx >= len(self.model_pool):
                self.current_model_idx = 0
                self.retry_cycle += 1
                if self.retry_cycle >= 3:
                    self._emit_log("SYSTEM", "All neural paths exhausted. Entering hibernation mode.")
                    self.set_state("OFFLINE")
                    await self._wait_shutdown(30)
                    self.retry_cycle = 0
                    return
            self._emit_log("SYSTEM", f"Model path failed. Rerouting to {self.model_pool[self.current_model_idx]}...")
            self.reconnect_backoff = 1.0
        else:
            self.reconnect_backoff = min(self.reconnect_backoff * 2, self.max_backoff)
            self._emit_log("SYSTEM", f"Connection anomaly: {str(e)[:60]}. Re-linking in {self.reconnect_backoff:.1f}s...")

        self.session = None
        self.session_ready.clear()

        jitter = random.uniform(0, 1.0)
        await asyncio.sleep(self.reconnect_backoff + jitter)

    async def _wait_shutdown(self, seconds: int):
        for _ in range(seconds * 2):
            if self._shutdown:
                return
            await asyncio.sleep(0.5)

    def _flush_pending(self):
        if not self.session or not self.session_ready.is_set():
            return
        while self.pending_messages:
            msg = self.pending_messages.pop(0)
            self._add_history("user", msg)
            try:
                asyncio.run_coroutine_threadsafe(
                    self.session.send_client_content(
                        turns=[types.Content(parts=[types.Part.from_text(text=msg)], role='user')],
                        turn_complete=True
                    ), self.loop
                )
            except Exception:
                self.pending_messages.insert(0, msg)
                break

    async def _handle_response(self, response):
        try:
            # Resumption token
            if hasattr(response, 'session_resumption_update') and response.session_resumption_update:
                new_handle = getattr(response.session_resumption_update, 'new_handle', None)
                if new_handle:
                    self.resumption_token = new_handle

            if hasattr(response, 'server_content') and response.server_content:
                sc = response.server_content

                # Audio playback
                if hasattr(sc, 'model_turn') and sc.model_turn:
                    for part in sc.model_turn.parts:
                        if hasattr(part, 'inline_data') and part.inline_data and part.inline_data.data:
                            if self.voice_enabled:
                                self.set_state("SPEAKING")
                                self.audio_player.feed(part.inline_data.data)

                # Text transcription (streaming)
                if hasattr(sc, 'output_transcription') and sc.output_transcription:
                    text = sc.output_transcription.text
                    if text:
                        with self._response_lock:
                            self._response_buffer += text
                        self._emit_log("JARVIS", text)

                # Turn complete
                if getattr(sc, 'turn_complete', False):
                    with self._response_lock:
                        if self._response_buffer:
                            final = self._response_buffer.strip()
                            self._add_history("model", final)
                            self._response_buffer = ""
                    self.set_state("READY")

            # Tool calls
            if hasattr(response, 'tool_call') and response.tool_call:
                calls = response.tool_call.function_calls
                if calls:
                    self.set_state("THINKING")
                    with self._response_lock:
                        if self._response_buffer:
                            self._add_history("model", self._response_buffer.strip())
                            self._response_buffer = ""
                    for call in calls:
                        await self._execute_tool(call)
                    self.set_state("READY")

        except Exception as e:
            import traceback
            self._emit_log("SYSTEM", f"Response processing error: {e}")
            traceback.print_exc()

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
            else:
                result = f"Unknown protocol: {name}"
        except Exception as e:
            result = f"Protocol error: {str(e)}"

        if self.session and self.session_ready.is_set():
            try:
                await self.session.send_tool_response(
                    function_responses=[types.FunctionResponse(name=name, id=call_id, response={"result": result})]
                )
            except Exception as e:
                self._emit_log("SYSTEM", f"Tool response transmission failed: {e}")

    def _tool_open_app(self, command: str):
        if os.name == 'nt':
            os.startfile(command)
        else:
            os.system(f"{command} &")
        return f"Launched {command}"

    def _tool_screenshot(self):
        path = BASE_DIR / "screenshot.jpg"
        img = pyautogui.screenshot()
        img.thumbnail((1024, 1024))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        data = buf.getvalue()
        if self.session and self.session_ready.is_set():
            asyncio.run_coroutine_threadsafe(
                self.session.send_realtime_input(media=types.Blob(mime_type="image/jpeg", data=data)),
                self.loop
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
            ai_tok = self.core.context_tokens
            ai_char = self.core.context_chars
            esc = win_title.replace('\\', '\\\\').replace("'", "\\'").replace('"', '\\"')
            self.bridge.telemetryUpdated.emit(cpu, ai_tok, ai_char, net_in, net_out, esc)

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
