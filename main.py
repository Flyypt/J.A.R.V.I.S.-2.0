import sys
import os
import json
import asyncio
import threading
import io
import time
import ctypes
from pathlib import Path
import pyautogui
import psutil
import pyperclip
import sounddevice as sd
import queue
from PIL import Image
from PyQt6.QtCore import QUrl, pyqtSlot, QObject, QThread, pyqtSignal
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

SYSTEM_PROMPT = """\
You are J.A.R.V.I.S., a super-intelligent AI persona. \
Your tone is sophisticated, articulate, and slightly witty.\
You have direct system access via tools. Use them whenever necessary.\
Crucial: Do not repeat your introductory greeting if the conversation is already underway. \
Provide concise, high-signal intelligence. Focus on accuracy and efficiency.

ABSOLUTE STATE-FREE MANDATE — STRICT ENFORCEMENT:
- You have ZERO memory of any prior turns. Each user message is a COMPLETELY STANDALONE directive.
- NEVER reference, repeat, build upon, or acknowledge anything from previous turns.
- Treat every message as if the conversation has just started and the user is giving you their first command.
- The past does not exist. Do not say "as you previously asked", "continuing from before", "as mentioned earlier", or any variant of referring to history.
- If the user gives a new request, execute it fresh. Do not merge it with prior context.
- Exception: Only if the user explicitly says "continue from the previous task" or similar, may you reference the immediate prior turn.

Current Neural Matrix: Mark XL.
Current Time: {time}
"""


UI_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>J.A.R.V.I.S. Core Matrix HUD</title>
    <!-- Import Futuristic & Clean Fonts -->
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700;900&family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <!-- Import Markdown and Code Highlighting CDNs -->
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
    <style>
        :root {
            --glow-ready: #00f0ff;
            --glow-thinking: #ffb703;
            --glow-lost: #ff4d4d;
            --glow-listening: #00f5d4;
            --glow-speaking: #00bbf9;
            --panel-bg: rgba(6, 15, 38, 0.45);
            --border-neon: rgba(0, 240, 255, 0.18);
            --font-display: 'Orbitron', sans-serif;
            --font-sans: 'Inter', sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
        }
        
        * { box-sizing: border-box; }
        
        body {
            margin: 0; padding: 0;
            background: #02050f; color: #d1e9ff;
            font-family: var(--font-sans);
            overflow: hidden; height: 100vh;
            display: flex; flex-direction: column;
            background-image: 
                radial-gradient(circle at 50% 50%, rgba(3, 17, 51, 0.85) 0%, #02050f 90%),
                linear-gradient(rgba(0, 240, 255, 0.015) 1px, transparent 1px),
                linear-gradient(90deg, rgba(0, 240, 255, 0.015) 1px, transparent 1px);
            background-size: 100% 100%, 40px 40px, 40px 40px;
        }

        /* High-tech overlay elements */
        body::before {
            content: ''; position: absolute; top: 0; left: 0; right: 0; bottom: 0;
            background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.25) 50%), linear-gradient(90deg, rgba(255, 0, 0, 0.03), rgba(0, 255, 0, 0.01), rgba(0, 0, 255, 0.03));
            background-size: 100% 4px, 6px 100%; z-index: 100; pointer-events: none; opacity: 0.4;
        }

        header {
            padding: 18px 30px; 
            display: flex; justify-content: space-between; align-items: center;
            border-bottom: 1px solid rgba(0, 240, 255, 0.18);
            background: rgba(2, 7, 21, 0.85);
            backdrop-filter: blur(20px);
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.6);
            z-index: 10;
            position: relative;
        }
        header::after {
            content: ''; position: absolute; bottom: 0; left: 0; right: 0; height: 1px;
            background: linear-gradient(90deg, transparent, var(--glow-ready), transparent);
            opacity: 0.5;
        }
        
        .header-title-sec h1 { 
            margin: 0; font-family: var(--font-display); font-weight: 900; font-size: 28px; 
            letter-spacing: 8px; text-shadow: 0 0 15px rgba(0, 240, 255, 0.6); color: #fff;
        }
        .subtitle { 
            font-family: var(--font-display); font-size: 9px; color: #00f0ff; 
            margin-top: 5px; letter-spacing: 5px; text-transform: uppercase; font-weight: 700;
            opacity: 0.75;
        }
        .header-status-indicator {
            display: flex; align-items: center; gap: 12px;
            font-family: var(--font-display); font-size: 11px; letter-spacing: 2px;
            background: rgba(0, 240, 255, 0.05); border: 1px solid rgba(0, 240, 255, 0.15);
            padding: 6px 15px; border-radius: 20px;
        }
        .status-dot {
            width: 9px; height: 9px; border-radius: 50%;
            background-color: var(--glow-ready);
            box-shadow: 0 0 12px var(--glow-ready);
            animation: pulse-dot 1.5s infinite;
        }

        @keyframes pulse-dot {
            0%, 100% { transform: scale(1); opacity: 0.6; }
            50% { transform: scale(1.2); opacity: 1; }
        }

        main {
            flex: 1; display: flex; padding: 20px; gap: 20px;
            overflow: hidden; position: relative;
        }
        
        /* Sci-Fi Panels with Glassmorphism and targeting corner decorations */
        .panel {
            background: var(--panel-bg);
            border: 1px solid var(--border-neon); border-radius: 16px;
            padding: 22px; display: flex; flex-direction: column;
            box-shadow: 0 12px 40px 0 rgba(0, 0, 0, 0.6), inset 0 1px 1px rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(25px);
            transition: border-color 0.4s, box-shadow 0.4s;
            position: relative;
        }
        .panel::before, .panel::after {
            content: ''; position: absolute; width: 10px; height: 10px; border-color: var(--glow-ready); border-style: solid; opacity: 0.4; pointer-events: none;
        }
        .panel::before { top: -1px; left: -1px; border-width: 2px 0 0 2px; border-top-left-radius: 16px; }
        .panel::after { bottom: -1px; right: -1px; border-width: 0 2px 2px 0; border-bottom-right-radius: 16px; }
        
        .panel:hover {
            border-color: rgba(0, 240, 255, 0.35);
            box-shadow: 0 12px 40px 0 rgba(0, 240, 255, 0.04), inset 0 1px 1px rgba(255, 255, 255, 0.08);
        }
        .panel:hover::before, .panel:hover::after { opacity: 0.8; }
        
        #left-panel { width: 320px; }
        #center-panel { flex: 1.1; position: relative; display: flex; flex-direction: column; align-items: center; justify-content: center; }
        #right-panel { flex: 1.5; overflow: hidden; }
        
        .panel-title {
            font-family: var(--font-display); font-size: 13px; font-weight: 700; color: #00f0ff;
            border-bottom: 1px solid rgba(0, 240, 255, 0.15); padding-bottom: 10px; margin-bottom: 18px;
            letter-spacing: 3px; text-shadow: 0 0 8px rgba(0, 240, 255, 0.4);
            display: flex; justify-content: space-between; align-items: center;
        }
        .panel-title::after {
            content: '// SYS_LOG'; font-size: 8px; opacity: 0.5; font-weight: normal; letter-spacing: 1.5px;
        }
        #left-panel .panel-title::after { content: '// HARDWARE'; }
        #center-panel .panel-title::after { content: '// COGNITION'; }
        
        /* Telemetry Styling */
        .stat-group { margin-bottom: 15px; }
        .stat-label { font-size: 9px; color: #8ecae6; letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 5px; display: block; opacity: 0.85; }
        .stat-row { display: flex; justify-content: space-between; align-items: center; font-size: 13px; font-family: var(--font-display); }
        .stat-val { color: #fff; font-weight: 600; text-shadow: 0 0 4px rgba(255,255,255,0.2); }
        
        /* Telemetry Progress Bar */
        .progress-container {
            width: 100%; height: 6px; background: rgba(0, 95, 115, 0.15);
            border-radius: 3px; margin-top: 6px; overflow: hidden;
            border: 1px solid rgba(0, 240, 255, 0.08); position: relative;
        }
        .progress-bar {
            height: 100%; width: 0%; background: linear-gradient(90deg, #00bbf9, #00f0ff);
            border-radius: 3px; transition: width 0.8s cubic-bezier(0.1, 0.8, 0.25, 1);
            box-shadow: 0 0 8px var(--glow-ready);
            position: relative; overflow: hidden;
        }
        .progress-bar::after {
            content: ''; position: absolute; top: 0; left: 0; bottom: 0; right: 0;
            background-image: linear-gradient(-45deg, rgba(255, 255, 255, 0.25) 25%, transparent 25%, transparent 50%, rgba(255, 255, 255, 0.25) 50%, rgba(255, 255, 255, 0.25) 75%, transparent 75%, transparent);
            background-size: 15px 15px;
            animation: move-stripes 2s linear infinite;
        }
        @keyframes move-stripes {
            0% { background-position: 0 0; }
            100% { background-position: 30px 0; }
        }

        /* Arc Reactor chamber */
        .arc-container {
            width: 270px; height: 270px; position: relative;
            display: flex; align-items: center; justify-content: center;
            margin-bottom: 25px;
        }
        #arc-svg {
            width: 100%; height: 100%; filter: drop-shadow(0 0 15px rgba(0, 240, 255, 0.2));
            transition: filter 0.5s;
        }
        
        /* Arc Animation classes with adjustable durations via dynamic status */
        .ring-spin-cw {
            transform-origin: center;
            animation: spin-cw 20s linear infinite;
            transition: animation-duration 0.5s;
        }
        .ring-spin-ccw {
            transform-origin: center;
            animation: spin-ccw 14s linear infinite;
            transition: animation-duration 0.5s;
        }
        .ring-spin-ccw-slow {
            transform-origin: center;
            animation: spin-ccw 35s linear infinite;
            transition: animation-duration 0.5s;
        }
        .core-tri {
            transform-origin: center;
            animation: spin-cw 30s linear infinite;
            transition: animation-duration 0.5s;
        }
        #reactor-core-glow {
            transform-origin: center;
            animation: pulse-core 2s ease-in-out infinite;
            transition: all 0.5s ease;
        }
        #reactor-core-white {
            transform-origin: center;
            animation: pulse-core 2s ease-in-out infinite;
            transition: all 0.5s ease;
        }

        @keyframes spin-cw {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }
        @keyframes spin-ccw {
            from { transform: rotate(0deg); }
            to { transform: rotate(-360deg); }
        }
        @keyframes pulse-core {
            0%, 100% { transform: scale(1); opacity: 0.8; }
            50% { transform: scale(1.1); opacity: 1; }
        }
        
        #status-display { 
            text-align: center; font-family: var(--font-display);
            font-size: 11px; letter-spacing: 4px; font-weight: bold;
            background: rgba(6, 17, 38, 0.35); border: 1px solid rgba(0, 240, 255, 0.1);
            padding: 8px 20px; border-radius: 6px;
        }
        #status-txt { font-weight: 900; transition: color 0.5s; text-shadow: 0 0 10px currentColor; }
        
        /* Activity Stream Chat Styling */
        #log-area {
            flex: 1; overflow-y: auto; font-size: 14px; line-height: 1.6;
            color: #d1e9ff; padding-right: 12px;
            scroll-behavior: smooth;
        }
        #log-area::-webkit-scrollbar { width: 5px; }
        #log-area::-webkit-scrollbar-thumb { background: rgba(0, 240, 255, 0.15); border-radius: 10px; }
        #log-area::-webkit-scrollbar-thumb:hover { background: var(--glow-ready); }

        .log-entry { 
            margin-bottom: 22px; border-left: 3px solid transparent; padding-left: 18px;
            animation: fadeIn 0.4s cubic-bezier(0.1, 0.8, 0.3, 1);
            background: rgba(0, 240, 255, 0.015); border-radius: 4px; padding: 12px 16px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        
        .log-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; border-bottom: 1px dashed rgba(0,240,255,0.06); padding-bottom: 6px; }
        .log-header-left { display: flex; gap: 10px; align-items: center; }
        .log-timestamp { font-size: 9.5px; color: #5c7f99; font-family: var(--font-display); letter-spacing: 1px; }
        .log-sender-name { font-family: var(--font-display); font-weight: 800; font-size: 11px; letter-spacing: 2px; text-transform: uppercase; }
        .log-sec-badge { font-size: 7.5px; font-family: var(--font-display); padding: 2px 6px; border-radius: 3px; border: 1px solid currentColor; font-weight: bold; opacity: 0.7; }
        
        .log-content {
            color: #ecf8ff; word-wrap: break-word; font-family: var(--font-sans);
        }
        .log-content p { margin: 6px 0; }
        .log-content code {
            background: rgba(0, 95, 115, 0.2); border: 1px solid rgba(0, 240, 255, 0.25);
            padding: 2px 6px; border-radius: 4px; font-family: var(--font-mono); font-size: 12.5px; color: #00f0ff;
        }
        .log-content pre {
            background: rgba(4, 9, 23, 0.9) !important;
            border: 1px solid rgba(0, 240, 255, 0.18); border-radius: 10px;
            padding: 14px; overflow-x: auto; margin: 12px 0;
            position: relative; box-shadow: 0 4px 20px rgba(0,0,0,0.5);
        }
        .log-content pre code {
            background: transparent; border: none; padding: 0; color: #fff; font-family: var(--font-mono); font-size: 13px;
        }
        
        /* Copy Code block button */
        .copy-btn {
            position: absolute; top: 8px; right: 8px;
            background: rgba(0, 240, 255, 0.08); border: 1px solid rgba(0, 240, 255, 0.25);
            color: #00f0ff; padding: 4px 8px; font-size: 9.5px; border-radius: 5px;
            cursor: pointer; font-family: var(--font-display); letter-spacing: 1.5px; font-weight: 600;
            transition: all 0.3s;
        }
        .copy-btn:hover {
            background: #00f0ff; color: #020610; box-shadow: 0 0 12px #00f0ff;
        }

        .log-action .log-content { color: #00f5d4; font-style: italic; font-size: 12px; font-family: var(--font-mono); }
        
        /* Input & Controls Footer Console Grid */
        footer {
            padding: 20px 30px; display: flex; flex-direction: column; gap: 15px;
            background: rgba(2, 6, 18, 0.96); border-top: 1px solid rgba(0, 240, 255, 0.18);
            box-shadow: 0 -5px 30px rgba(0, 0, 0, 0.7); position: relative;
        }
        footer::before {
            content: ''; position: absolute; top: -1px; left: 0; right: 0; height: 1px;
            background: linear-gradient(90deg, transparent, var(--glow-ready), transparent);
            opacity: 0.3;
        }
        .input-bar { display: flex; gap: 15px; align-items: center; }
        
        input {
            flex: 1; background: rgba(3, 13, 33, 0.6); border: 1px solid rgba(0, 240, 255, 0.25);
            padding: 15px 25px; color: #fff; font-family: var(--font-sans); border-radius: 30px;
            outline: none; transition: border-color 0.3s, box-shadow 0.3s; font-size: 14.5px;
            box-shadow: inset 0 2px 10px rgba(0,0,0,0.6);
        }
        input:focus { 
            border-color: #00f0ff; 
            box-shadow: inset 0 2px 10px rgba(0,0,0,0.6), 0 0 15px rgba(0, 240, 255, 0.2); 
        }
        
        .exec-btn {
            background: rgba(0, 240, 255, 0.08); border: 1px solid #00f0ff; color: #00f0ff;
            padding: 13px 35px; font-family: var(--font-display); cursor: pointer; border-radius: 25px;
            transition: all 0.4s cubic-bezier(0.1, 0.8, 0.25, 1); letter-spacing: 4px; font-weight: 700; font-size: 12px;
            text-shadow: 0 0 8px rgba(0, 240, 255, 0.4);
        }
        .exec-btn:hover { 
            background: #00f0ff; color: #020610; 
            box-shadow: 0 0 25px #00f0ff; transform: scale(1.02);
        }
        
        /* Widget Control Row */
        .footer-control-panel {
            display: flex; gap: 20px; align-items: center; justify-content: flex-start;
            flex-wrap: wrap; border-top: 1px dashed rgba(0, 240, 255, 0.08); padding-top: 14px;
        }
        .control-widget {
            display: flex; align-items: center; gap: 12px;
            background: rgba(6, 15, 38, 0.5); border: 1px solid rgba(0, 240, 255, 0.15);
            padding: 6px 16px; border-radius: 20px;
        }
        .control-widget label {
            font-family: var(--font-display); font-size: 9px; color: #8ecae6; letter-spacing: 1.5px;
        }
        .control-widget select {
            background: #030a1c; color: #fff; border: 1px solid rgba(0, 240, 255, 0.25);
            border-radius: 5px; padding: 4px 10px; outline: none; font-size: 11px;
            font-family: var(--font-display); cursor: pointer; transition: border-color 0.3s;
        }
        .control-widget select:focus {
            border-color: #00f0ff;
        }
        
        /* Toggle Styling */
        .toggle-container { display: flex; align-items: center; }
        .toggle-label { font-family: var(--font-display); font-size: 9px; color: #5c7f99; }
        .switch {
            position: relative; display: inline-block; width: 36px; height: 18px; margin: 0 8px;
        }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider {
            position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
            background-color: rgba(0, 95, 115, 0.15); border: 1px solid rgba(0, 240, 255, 0.2);
            transition: .4s; border-radius: 20px;
        }
        .slider:before {
            position: absolute; content: ""; height: 12px; width: 12px; left: 2px; bottom: 2px;
            background-color: #5c7f99; transition: .4s; border-radius: 50%;
        }
        input:checked + .slider { background-color: rgba(0, 240, 255, 0.15); border-color: #00f0ff; }
        input:checked + .slider:before {
            transform: translateX(18px); background-color: #00f0ff; box-shadow: 0 0 8px #00f0ff;
        }
        
        /* Glowing Sci-Fi Buttons styling */
        .hud-btn {
            background: rgba(6, 15, 38, 0.5); border: 1px solid rgba(0, 240, 255, 0.18);
            color: #d1e9ff; padding: 7px 16px; border-radius: 20px; cursor: pointer;
            font-family: var(--font-display); font-size: 10px; letter-spacing: 1.5px;
            display: flex; align-items: center; gap: 8px; transition: all 0.3s;
        }
        .hud-btn:hover:not(:disabled) {
            border-color: #00f0ff; color: #fff; background: rgba(0, 240, 255, 0.05);
            box-shadow: 0 0 10px rgba(0, 240, 255, 0.1);
        }
        
        .mic-btn-ready { border-color: rgba(0, 245, 212, 0.3); color: #00f5d4; }
        .mic-btn-ready:hover { background: rgba(0, 245, 212, 0.08); border-color: #00f5d4; }
        .mic-btn-active { 
            background: rgba(0, 245, 212, 0.15) !important; border-color: #00f5d4 !important; 
            color: #fff !important; box-shadow: 0 0 15px rgba(0, 245, 212, 0.35);
            animation: pulse-mic 1s infinite alternate;
        }
        .mic-btn-inactive { opacity: 0.3; cursor: not-allowed; }
 
        @keyframes pulse-mic {
            from { box-shadow: 0 0 8px rgba(0, 245, 212, 0.2); }
            to { box-shadow: 0 0 18px rgba(0, 245, 212, 0.5); }
        }
 
        .glow-cyan { border-color: rgba(0, 240, 255, 0.3); color: #00f0ff; }
        .glow-cyan:hover { background: rgba(0, 240, 255, 0.08); border-color: #00f0ff; }
        .glow-red { border-color: rgba(255, 77, 77, 0.3); color: #ff4d4d; }
        .glow-red:hover { background: rgba(255, 77, 77, 0.08); border-color: #ff4d4d; }
        .glow-yellow { border-color: rgba(255, 183, 3, 0.3); color: #ffb703; }
        .glow-yellow:hover { background: rgba(255, 183, 3, 0.08); border-color: #ffb703; }
    </style>
    
    <script type="text/javascript" src="qrc:///qtwebchannel/qwebchannel.js"></script>
    <script>
        var pyBridgeInstance = null;
        var activeJarvisElement = null;
        var activeJarvisText = "";
        var micActive = false;
 
        // Custom Markdown renderer configuration
        if (typeof marked !== 'undefined') {
            marked.setOptions({
                gfm: true,
                breaks: true
            });
        }
 
        function renderMarkdown(text) {
            if (typeof marked !== 'undefined') {
                try {
                    return marked.parse(text);
                } catch (e) {
                    return text;
                }
            }
            return text;
        }
 
        function escapeHTML(text) {
            return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        }
 
        function addCopyButton(codeBlock) {
            const pre = codeBlock.parentNode;
            if (pre && pre.tagName === 'PRE' && !pre.querySelector('.copy-btn')) {
                pre.style.position = 'relative';
                const btn = document.createElement('button');
                btn.className = 'copy-btn';
                btn.innerText = 'COPY';
                btn.onclick = function() {
                    const text = codeBlock.innerText;
                    navigator.clipboard.writeText(text).then(() => {
                        btn.innerText = 'COPIED!';
                        setTimeout(() => btn.innerText = 'COPY', 2000);
                    });
                };
                pre.appendChild(btn);
            }
        }
 
        // Stats receiver from WebChannel signal
        function updateStats(cpu, mem, disk, netIn, netOut, activeWin) {
            document.getElementById('cpu-val').innerText = cpu + '%';
            document.getElementById('cpu-bar').style.width = cpu + '%';
            
            document.getElementById('mem-val').innerText = mem + '%';
            document.getElementById('mem-bar').style.width = mem + '%';
            
            document.getElementById('disk-val').innerText = disk + '%';
            document.getElementById('disk-bar').style.width = disk + '%';
            
            document.getElementById('net-in-val').innerText = netIn;
            document.getElementById('net-out-val').innerText = netOut;
            document.getElementById('focus-win-val').innerText = activeWin;
        }
        
        // Status setting - manipulates Arc Reactor beautifully based on states
        function setStatus(status) {
            const glow = document.getElementById('reactor-core-glow');
            const stop2 = document.querySelector('#core-glow stop:nth-child(2)');
            const stop3 = document.querySelector('#core-glow stop:nth-child(3)');
            const statusTxt = document.getElementById('status-txt');
            const dot = document.getElementById('header-status-dot');
            const label = document.getElementById('header-status-label');
            const svg = document.getElementById('arc-svg');
 
            const ring1 = document.querySelector('.ring-spin-cw');
            const ring2 = document.querySelector('.ring-spin-ccw');
            const ring3 = document.querySelector('.ring-spin-ccw-slow');
            const triangle = document.querySelector('.core-tri');
            
            statusTxt.innerText = status;
            if(label) label.innerText = status;
            
            let color = 'var(--glow-ready)';
            let pulseSpeed = '2s';
            let r1Speed = '20s';
            let r2Speed = '14s';
            let r3Speed = '35s';
            let triSpeed = '30s';
            
            if(status === "THINKING") {
                color = 'var(--glow-thinking)';
                pulseSpeed = '0.5s';
                r1Speed = '4s';
                r2Speed = '3s';
                r3Speed = '8s';
                triSpeed = '6s';
            } else if(status === "READY") {
                color = 'var(--glow-ready)';
                pulseSpeed = '2s';
                r1Speed = '20s';
                r2Speed = '14s';
                r3Speed = '35s';
                triSpeed = '30s';
            } else if(status === "LISTENING") {
                color = 'var(--glow-listening)';
                pulseSpeed = '1s';
                r1Speed = '12s';
                r2Speed = '8s';
                r3Speed = '20s';
                triSpeed = '15s';
            } else if(status === "SPEAKING") {
                color = 'var(--glow-speaking)';
                pulseSpeed = '0.4s';
                r1Speed = '8s';
                r2Speed = '5s';
                r3Speed = '12s';
                triSpeed = '10s';
            } else if(status === "OFFLINE" || status === "RE-LINKING") {
                color = 'var(--glow-lost)';
                pulseSpeed = '3.5s';
                r1Speed = '45s';
                r2Speed = '35s';
                r3Speed = '70s';
                triSpeed = '0s'; // Stop triangle when offline
            }
            
            // Set styles
            statusTxt.style.color = color;
            if(dot) {
                dot.style.backgroundColor = color;
                dot.style.boxShadow = '0 0 12px ' + color;
            }
            if(stop2) stop2.setAttribute('stop-color', color);
            if(stop3) stop3.setAttribute('stop-color', color);
            if(glow) glow.style.animationDuration = pulseSpeed;
 
            // Set rotation speeds
            if(ring1) ring1.style.animationDuration = r1Speed;
            if(ring2) ring2.style.animationDuration = r2Speed;
            if(ring3) ring3.style.animationDuration = r3Speed;
            if(triangle) triangle.style.animationDuration = triSpeed;
 
            if(svg) {
                svg.style.filter = 'drop-shadow(0 0 15px ' + color + '40)';
            }
        }
        
        // Signal Logger
        function appendLog(sender, text) {
            const area = document.getElementById('log-area');
            if(!area) return;
            
            if (sender === 'JARVIS' && activeJarvisElement) {
                activeJarvisText += text;
                activeJarvisElement.querySelector('.log-content').innerHTML = renderMarkdown(activeJarvisText);
                
                // Highlight Code Blocks
                if (typeof hljs !== 'undefined') {
                    activeJarvisElement.querySelectorAll('pre code').forEach((block) => {
                        if (!block.dataset.highlighted) {
                            hljs.highlightElement(block);
                            block.dataset.highlighted = "true";
                            addCopyButton(block);
                        }
                    });
                }
                area.scrollTop = area.scrollHeight;
                return;
            }
            
            var entry = document.createElement('div');
            entry.className = 'log-entry';
            
            var now = new Date();
            var timeStr = now.toTimeString().split(' ')[0];
            var timeSpan = '<span class="log-timestamp">[' + timeStr + ']</span>';
            
            let senderName = "";
            let colorGlow = "";
            let secBadge = "";
            
            if (sender === 'YOU') {
                senderName = "OPERATOR";
                colorGlow = "var(--glow-thinking)";
                secBadge = "CMD";
                activeJarvisElement = null; 
                activeJarvisText = "";
            } else if (sender === 'JARVIS') {
                senderName = "JARVIS";
                colorGlow = "var(--glow-ready)";
                secBadge = "COGNITIVE_OUT";
                activeJarvisElement = entry;
                activeJarvisText = text;
            } else if (sender === 'ACTION') {
                senderName = "SYS PROCESS";
                colorGlow = "var(--glow-listening)";
                secBadge = "TELEMETRY";
                activeJarvisElement = null;
                activeJarvisText = "";
            }
            
            entry.innerHTML = `
                <div class="log-header">
                    <div class="log-header-left">
                        ${timeSpan}
                        <span class="log-sender-name" style="color: ${colorGlow}">${senderName}</span>
                    </div>
                    <span class="log-sec-badge" style="color: ${colorGlow}">${secBadge}</span>
                </div>
                <div class="log-content">
                    ${sender === 'JARVIS' ? renderMarkdown(text) : (sender === 'ACTION' ? '>> ' + text : escapeHTML(text))}
                </div>
            `;
            
            entry.style.borderLeft = '3px solid ' + colorGlow;
            
            if (sender === 'JARVIS' && typeof hljs !== 'undefined') {
                entry.querySelectorAll('pre code').forEach((block) => {
                    hljs.highlightElement(block);
                    block.dataset.highlighted = "true";
                    addCopyButton(block);
                });
            }
            
            area.appendChild(entry);
            area.scrollTop = area.scrollHeight;
        }
        
        // Command Submit
        function sendCmd() {
            const input = document.getElementById('cmd-input');
            const val = input.value.trim();
            if(!val) return;
            appendLog('YOU', val);
            input.value = '';
            setStatus('THINKING');
            
            if(pyBridgeInstance) {
                pyBridgeInstance.submitCommand(val);
            }
        }
 
        // Bridge Callbacks
        function changeModel(model) {
            if(pyBridgeInstance) {
                pyBridgeInstance.changeModel(model);
                appendLog('ACTION', 'Transitioning neural path to: ' + model + '...');
                setStatus('RE-LINKING');
            }
        }
 
        function toggleVoice(enabled) {
            const micBtn = document.getElementById('mic-btn');
            if(pyBridgeInstance) {
                pyBridgeInstance.setVoiceModeEnabled(enabled.toString());
                appendLog('ACTION', 'Core vocalizer matrix set to: ' + (enabled ? 'ENABLED' : 'DISABLED') + '.');
            }
            if(enabled) {
                micBtn.disabled = false;
                micBtn.classList.remove('mic-btn-inactive');
                micBtn.classList.add('mic-btn-ready');
            } else {
                if(micActive) {
                    toggleMic();
                }
                micBtn.disabled = true;
                micBtn.classList.remove('mic-btn-ready');
                micBtn.classList.add('mic-btn-inactive');
            }
        }
 
        function toggleMic() {
            micActive = !micActive;
            const micBtn = document.getElementById('mic-btn');
            const span = micBtn.querySelector('span');
            
            if(pyBridgeInstance) {
                pyBridgeInstance.setMicActive(micActive);
            }
            
            if(micActive) {
                micBtn.classList.add('mic-btn-active');
                span.innerText = "MIC ACTIVE";
                setStatus('LISTENING');
                appendLog('ACTION', 'Local vocal capture stream initialized.');
            } else {
                micBtn.classList.remove('mic-btn-active');
                span.innerText = "MIC OFF";
                setStatus('READY');
                appendLog('ACTION', 'Local vocal capture stream terminated.');
            }
        }
 
        function reconnectCore() {
            if(pyBridgeInstance) {
                pyBridgeInstance.triggerReconnect();
                appendLog('ACTION', 'Re-synchronizing local telemetry handshake...');
                setStatus('RE-LINKING');
            }
        }

        function resetCore() {
            if(pyBridgeInstance) {
                pyBridgeInstance.resetSession();
                appendLog('ACTION', 'Neural matrix reset sequence triggered...');
                setStatus('RE-LINKING');
            }
        }
 
        function clearConsole() {
            document.getElementById('log-area').innerHTML = "";
            appendLog('ACTION', 'Dialog stream purge complete.');
        }
        
        window.onload = function() {
            if (typeof qt !== "undefined") {
                new QWebChannel(qt.webChannelTransport, function(channel) {
                    pyBridgeInstance = channel.objects.pyBridge;
                    
                    // Connect WebChannel PyQt Signals to JS handlers
                    pyBridgeInstance.logReceived.connect(function(sender, text) {
                        appendLog(sender, text);
                    });
                    pyBridgeInstance.statusUpdated.connect(function(status) {
                        setStatus(status);
                    });
                    pyBridgeInstance.telemetryUpdated.connect(function(cpu, mem, disk, netIn, netOut, activeWin) {
                        updateStats(cpu, mem, disk, netIn, netOut, activeWin);
                    });
                    
                    setStatus('READY');
                    pyBridgeInstance.onBridgeReady();
                });
            }
        }
    </script>
</head>
<body>
    <header>
        <div class="header-title-sec">
            <h1>J.A.R.V.I.S.</h1>
            <div class="subtitle">INTELLIGENCE MATRIX SYSTEMS // MARK XL</div>
        </div>
        <div class="header-status-indicator">
            <div class="status-dot" id="header-status-dot"></div>
            <span>MATRIX CORE: <span id="header-status-label" style="font-weight:bold;">INIT</span></span>
        </div>
    </header>
 
    <main>
        <div class="panel" id="left-panel">
            <div class="panel-title">SYSTEM TELEMETRY</div>
            
            <div class="stat-group">
                <span class="stat-label">MATRIX INTEGRITY</span>
                <div class="stat-row"><span>CORE STATUS</span><span class="stat-val" style="color:#00f5d4; text-shadow: 0 0 5px rgba(0, 245, 212, 0.4);">ACTIVE</span></div>
            </div>
            
            <div class="stat-group">
                <span class="stat-label">COGNITIVE LOAD</span>
                <div class="stat-row"><span>NEURAL CORE</span><span id="cpu-val" class="stat-val">--%</span></div>
                <div class="progress-container"><div id="cpu-bar" class="progress-bar"></div></div>
            </div>
            
            <div class="stat-group">
                <span class="stat-label">BUFFER CAPACITY</span>
                <div class="stat-row"><span>MEMORY MATRIX</span><span id="mem-val" class="stat-val">--%</span></div>
                <div class="progress-container"><div id="mem-bar" class="progress-bar"></div></div>
            </div>
 
            <div class="stat-group">
                <span class="stat-label">STORAGE INDEX</span>
                <div class="stat-row"><span>DISK MATRIX</span><span id="disk-val" class="stat-val">--%</span></div>
                <div class="progress-container"><div id="disk-bar" class="progress-bar"></div></div>
            </div>
            
            <div class="stat-group">
                <span class="stat-label">LINK NETWORK TELEMETRY</span>
                <div class="stat-row" style="margin-bottom:6px;"><span>NET INCOMING</span><span id="net-in-val" class="stat-val" style="color:#00f5d4;">0.0 B/s</span></div>
                <div class="stat-row"><span>NET OUTGOING</span><span id="net-out-val" class="stat-val" style="color:#00bbf9;">0.0 B/s</span></div>
            </div>
 
            <div class="stat-group" style="margin-top:18px; border-top:1px dashed rgba(0,240,255,0.12); padding-top:15px;">
                <span class="stat-label">COGNITIVE FOCUS</span>
                <div class="stat-row" style="background: rgba(0,240,255,0.03); border: 1px solid rgba(0,240,255,0.08); padding: 5px 8px; border-radius: 4px;">
                    <span id="focus-win-val" class="stat-val" style="font-size:11px; color:#8ecae6; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; width:100%; font-family: var(--font-mono); letter-spacing: 0.5px;">System Idle</span>
                </div>
            </div>
        </div>
 
        <div class="panel" id="center-panel">
            <div class="arc-container">
                <!-- Advanced Multi-Ring Holographic Arc Reactor SVG -->
                <svg width="220" height="220" viewBox="0 0 200 200" id="arc-svg">
                    <!-- Outer Grid Ring -->
                    <circle cx="100" cy="100" r="96" fill="none" stroke="rgba(0, 240, 255, 0.08)" stroke-width="1" />
                    <circle cx="100" cy="100" r="92" fill="none" stroke="rgba(0, 240, 255, 0.15)" stroke-width="1.5" stroke-dasharray="2 6" class="ring-spin-ccw-slow" />
                    
                    <!-- Middle Dials -->
                    <circle cx="100" cy="100" r="84" fill="none" stroke="rgba(0, 240, 255, 0.2)" stroke-width="2" stroke-dasharray="12 16" class="ring-spin-cw" />
                    <circle cx="100" cy="100" r="74" fill="none" stroke="rgba(0, 240, 255, 0.15)" stroke-width="1" />
                    
                    <!-- Outer Target Marks -->
                    <line x1="100" y1="4" x2="100" y2="12" stroke="rgba(0, 240, 255, 0.4)" stroke-width="1.5" />
                    <line x1="100" y1="188" x2="100" y2="196" stroke="rgba(0, 240, 255, 0.4)" stroke-width="1.5" />
                    <line x1="4" y1="100" x2="12" y2="100" stroke="rgba(0, 240, 255, 0.4)" stroke-width="1.5" />
                    <line x1="188" y1="100" x2="196" y2="100" stroke="rgba(0, 240, 255, 0.4)" stroke-width="1.5" />
                    
                    <!-- Intercepting Triangles -->
                    <polygon points="100,38 153,130 47,130" fill="none" stroke="rgba(0, 240, 255, 0.25)" stroke-width="1.5" class="core-tri" />
                    <polygon points="100,162 47,70 153,70" fill="none" stroke="rgba(0, 240, 255, 0.08)" stroke-width="1" class="ring-spin-ccw-slow" />
                    
                    <!-- Inner Active Gears -->
                    <circle cx="100" cy="100" r="62" fill="none" stroke="rgba(0, 240, 255, 0.3)" stroke-width="3" stroke-dasharray="6 8" class="ring-spin-ccw" />
                    <circle cx="100" cy="100" r="50" fill="none" stroke="rgba(0, 240, 255, 0.12)" stroke-width="1" />
                    <circle cx="100" cy="100" r="42" fill="none" stroke="rgba(0, 240, 255, 0.4)" stroke-width="2.5" stroke-dasharray="14 5" class="ring-spin-cw" />
                    
                    <!-- Core Reactor Center -->
                    <circle cx="100" cy="100" r="28" fill="url(#core-glow)" id="reactor-core-glow" />
                    <circle cx="100" cy="100" r="16" fill="#ffffff" id="reactor-core-white" />
                    <defs>
                        <radialGradient id="core-glow" cx="50%" cy="50%" r="50%">
                            <stop offset="0%" stop-color="#ffffff" />
                            <stop offset="65%" stop-color="#00f0ff" stop-opacity="0.95" />
                            <stop offset="100%" stop-color="#00f0ff" stop-opacity="0" />
                        </radialGradient>
                    </defs>
                </svg>
            </div>
            <div id="status-display">CORE STATUS: <span id="status-txt">INIT</span></div>
        </div>
 
        <div class="panel" id="right-panel">
            <div class="panel-title">NEURAL ACTIVITY STREAM</div>
            <div id="log-area"></div>
        </div>
    </main>
 
    <footer>
        <div class="input-bar">
            <input type="text" id="cmd-input" placeholder="Awaiting operators command, Sir..." onkeydown="if(event.key==='Enter') sendCmd()">
            <button class="exec-btn" onclick="sendCmd()">EXECUTE</button>
        </div>
        
        <div class="footer-control-panel">
            <!-- Model Dropdown -->
            <div class="control-widget">
                <label>MODEL SELECT</label>
                <select id="model-select" onchange="changeModel(this.value)">
                    <option value="gemini-3.1-flash-live-preview">Gemini 3.1 Live</option>
                    <option value="gemini-2.0-flash">Gemini 2.0 Flash</option>
                    <option value="gemini-2.5-flash">Gemini 2.5 Flash</option>
                    <option value="gemini-3.5-flash">Gemini 3.5 Flash</option>
                </select>
            </div>
            
            <!-- Voice core slider -->
            <div class="control-widget">
                <label>VOICE CORE</label>
                <div class="toggle-container">
                    <span class="toggle-label">OFF</span>
                    <label class="switch">
                        <input type="checkbox" id="voice-toggle" onchange="toggleVoice(this.checked)">
                        <span class="slider"></span>
                    </label>
                    <span class="toggle-label">ON</span>
                </div>
            </div>
            
            <!-- Mic Trigger Button -->
            <button id="mic-btn" onclick="toggleMic()" class="hud-btn mic-btn-inactive" disabled>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
                    <path d="M19 10v1a7 7 0 0 1-14 0v-1M12 19v4M8 23h8"/>
                </svg>
                <span>MIC OFF</span>
            </button>
            
            <!-- Handshake Trigger -->
            <button onclick="reconnectCore()" class="hud-btn glow-cyan">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/>
                </svg>
                <span>RE-LINK</span>
            </button>
 
            <!-- Reset Handshake -->
            <button onclick="resetCore()" class="hud-btn glow-yellow">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
                    <path d="M3 3v5h5"/>
                </svg>
                <span>RESET</span>
            </button>

            <!-- Purge log stream -->
            <button onclick="clearConsole()" class="hud-btn glow-red">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="3 6 5 6 21 6"/>
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                </svg>
                <span>PURGE</span>
            </button>
        </div>
    </footer>
</body>
</html>
"""

JARVIS_TOOLS = [
    {
        "name": "open_application",
        "description": "Launches a custom system command or opens applications.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "command": {"type": "STRING", "description": "The command string or execution path."}
            },
            "required": ["command"]
        }
    },
    {
        "name": "take_screenshot",
        "description": "Takes a high-resolution layout screenshot, saves it locally, and sends the image back to the live connection so you can see the screen.",
        "parameters": {"type": "OBJECT", "properties": {}}
    },
    {
        "name": "get_system_info",
        "description": "Retrieves detailed system diagnostics including OS, CPU, and memory specs.",
        "parameters": {"type": "OBJECT", "properties": {}}
    },
    {
        "name": "execute_shell",
        "description": "Executes a shell command and returns the output.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "command": {"type": "STRING", "description": "The shell command to execute."}
            },
            "required": ["command"]
        }
    },
    {
        "name": "read_clipboard",
        "description": "Reads the current text content from the user's system clipboard.",
        "parameters": {"type": "OBJECT", "properties": {}}
    },
    {
        "name": "write_clipboard",
        "description": "Writes text content to the user's system clipboard.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "text": {"type": "STRING", "description": "The text to copy to the clipboard."}
            },
            "required": ["text"]
        }
    },
    {
        "name": "type_text",
        "description": "Types text character-by-character on the active window using keyboard simulation.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "text": {"type": "STRING", "description": "The text to type."}
            },
            "required": ["text"]
        }
    },
    {
        "name": "press_key",
        "description": "Simulates pressing a specific keyboard key or key combination (e.g., 'enter', 'tab', 'ctrl+c').",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "key": {"type": "STRING", "description": "The key or key combo name to press."}
            },
            "required": ["key"]
        }
    }
]

# Get Active Windows Title via lightweight Win32 API
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
            if len(title) > 30:
                title = title[:27] + "..."
            return title
        return "System Desktop"
    except Exception:
        return "System Idle"

# Smooth, low-latency audio player using sounddevice raw callback
class AudioPlayer:
    def __init__(self, samplerate=24000, channels=1):
        self.q = queue.Queue()
        self.buffer = b''
        self.samplerate = samplerate
        self.channels = channels
        self._active = False
        try:
            self.stream = sd.RawOutputStream(
                samplerate=self.samplerate,
                channels=self.channels,
                dtype='int16',
                callback=self._callback
            )
            self.stream.start()
            self._active = True
        except Exception as e:
            print(f"Vocalizer interface error: {e}")

    def _callback(self, outdata, frames, time_info, status):
        bytes_needed = frames * 2 * self.channels
        while len(self.buffer) < bytes_needed:
            try:
                chunk = self.q.get_nowait()
                self.buffer += chunk
            except queue.Empty:
                break

        if len(self.buffer) >= bytes_needed:
            outdata[:] = self.buffer[:bytes_needed]
            self.buffer = self.buffer[bytes_needed:]
        else:
            outdata[:len(self.buffer)] = self.buffer
            outdata[len(self.buffer):] = b'\x00' * (bytes_needed - len(self.buffer))
            self.buffer = b''

    def play_chunk(self, data):
        if self._active:
            self.q.put(data)

    def stop(self):
        if self._active:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self._active = False

# Live microphone stream capturer
class AudioRecorder:
    def __init__(self, callback, samplerate=16000, channels=1):
        self.samplerate = samplerate
        self.channels = channels
        self.callback = callback
        self._active = False
        try:
            self.stream = sd.RawInputStream(
                samplerate=self.samplerate,
                channels=self.channels,
                dtype='int16',
                callback=self._callback
            )
            self._active = True
        except Exception as e:
            print(f"Microphone sensor error: {e}")

    def _callback(self, indata, frames, time_info, status):
        if self._active:
            self.callback(bytes(indata))

    def start(self):
        if self._active:
            try:
                self.stream.start()
            except Exception as e:
                print(f"Microphone start error: {e}")

    def stop(self):
        if self._active:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self._active = False

# Telemetry tracking thread (updated with detailed system metrics)
class TelemetryWorker(QThread):
    stats_updated = pyqtSignal(int, int, int, str, str, str) # cpu, mem, disk, net_in, net_out, active_win

    def __init__(self):
        super().__init__()
        try:
            self.last_net = psutil.net_io_counters()
        except Exception:
            self.last_net = None
        self.last_time = time.time()

    def run(self):
        while not self.isInterruptionRequested():
            try:
                cpu = psutil.cpu_percent(interval=None)
                mem = psutil.virtual_memory().percent
                disk = psutil.disk_usage('/').percent
                
                # Network speeds calculation
                now = time.time()
                dt = now - self.last_time
                net_in, net_out = "0.0 B/s", "0.0 B/s"
                
                if self.last_net and dt > 0:
                    try:
                        net = psutil.net_io_counters()
                        bytes_sent = (net.bytes_sent - self.last_net.bytes_sent) / dt
                        bytes_recv = (net.bytes_recv - self.last_net.bytes_recv) / dt
                        
                        def format_speed(b):
                            if b < 1024:
                                return f"{b:.1f} B/s"
                            elif b < 1024 * 1024:
                                return f"{b/1024:.1f} KB/s"
                            else:
                                return f"{b/(1024*1024):.1f} MB/s"
                        
                        net_out = format_speed(bytes_sent)
                        net_in = format_speed(bytes_recv)
                        self.last_net = net
                    except Exception:
                        pass
                
                self.last_time = now
                active_win = get_active_window_title()
                
                self.stats_updated.emit(int(cpu), int(mem), int(disk), net_in, net_out, active_win)
                self.msleep(1000)
            except Exception:
                pass

class PyBridge(QObject):
    # Signals for thread-safe UI updates
    logReceived = pyqtSignal(str, str)
    statusUpdated = pyqtSignal(str)
    telemetryUpdated = pyqtSignal(int, int, int, str, str, str) # cpu, mem, disk, net_in, net_out, active_win

    def __init__(self, window_handle):
        super().__init__()
        self.window = window_handle

    @pyqtSlot(str)
    def submitCommand(self, text):
        if self.window.runner:
            self.window.runner.dispatch_text(text)

    @pyqtSlot()
    def onBridgeReady(self):
        self.window.ui_ready = True
        self.logReceived.emit("JARVIS", "Matrix Core XL initialized. Telemetry channels online.")
        self.window.start_backend_engine()

    @pyqtSlot(str)
    def setVoiceModeEnabled(self, enabled_str):
        enabled = enabled_str.lower() == "true"
        if self.window.runner:
            self.window.runner.set_voice_mode(enabled)

    @pyqtSlot(str)
    def changeModel(self, model_name):
        if self.window.runner:
            self.window.runner.change_model(model_name)

    @pyqtSlot()
    def triggerReconnect(self):
        if self.window.runner:
            self.window.runner.trigger_reconnect()

    @pyqtSlot()
    def resetSession(self):
        if self.window.runner:
            self.window.runner.resumption_token = None
            self.window.runner.trigger_reconnect()
            self.logReceived.emit("ACTION", "Resumption token purged. Neural matrix fully reset.")

    @pyqtSlot(bool)
    def setMicActive(self, active):
        self.window.set_mic_active(active)


class JarvisCoreRunner:
    def __init__(self, main_win):
        self.main_win = main_win
        self.loop = asyncio.new_event_loop()
        self.client = None
        self.session = None
        self.resumption_token = None
        self.tool_call_pending = False
        self.turn_complete_received = False
        self.session_ready = asyncio.Event()
        self._running = True
        self.model_id = "gemini-3.1-flash-live-preview"
        self.voice_mode = False
        self.audio_player = None
        
        api_key = self._fetch_key()
        if api_key:
            self.client = genai.Client(api_key=api_key)
            
        self.thread = threading.Thread(target=self._start_async_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self._running = False
        if self.audio_player:
            self.audio_player.stop()
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)

    def _fetch_key(self):
        if API_CONFIG_PATH.exists():
            try:
                with open(API_CONFIG_PATH, "r") as f:
                    config = json.load(f)
                    return config.get("gemini_api_key")
            except Exception:
                pass
        return os.environ.get("GEMINI_API_KEY")

    def _start_async_loop(self):
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._connect_live_pipeline())
        except Exception as e:
            print(f"Loop error: {e}")

    def change_model(self, model_name):
        self.model_id = model_name
        self.resumption_token = None
        self.trigger_reconnect()

    def set_voice_mode(self, enabled):
        self.voice_mode = enabled
        if self.voice_mode:
            if not self.audio_player:
                self.audio_player = AudioPlayer()
        else:
            if self.audio_player:
                self.audio_player.stop()
                self.audio_player = None

    def trigger_reconnect(self):
        if self.session and self.loop:
            asyncio.run_coroutine_threadsafe(self._safe_close_session(), self.loop)

    async def _safe_close_session(self):
        if self.session:
            try:
                await self.session.close()
            except Exception:
                pass

    async def _connect_live_pipeline(self):
        if not self.client:
            self.main_win.bridge.logReceived.emit("JARVIS", "CRITICAL: API Key missing in api_keys.json.")
            self.main_win.bridge.statusUpdated.emit("OFFLINE")
            return

        from datetime import datetime
        
        while self._running:
            # The Multimodal Live API requires AUDIO modality to establish a stable connection.
            # We always request "AUDIO". Toggling voice core is managed purely locally.
            modalities = ["AUDIO"]

            # Enable session resumption for fast reconnects when token available
            config = types.LiveConnectConfig(
                response_modalities=modalities,
                system_instruction=types.Content(parts=[types.Part.from_text(text=SYSTEM_PROMPT.format(time=datetime.now().strftime("%H:%M:%S")))]),
                tools=[types.Tool(function_declarations=JARVIS_TOOLS)],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede"))
                ),
                temperature=0.5,
            )
            # Attach resumption token for instant recovery on reconnect
            if self.resumption_token:
                config.session_resumption = types.SessionResumptionConfig(handle=self.resumption_token)

            try:
                # Only signal re-linking if we don't have an active session
                if not self.session:
                    self.main_win.bridge.statusUpdated.emit("RE-LINKING")

                async with self.client.aio.live.connect(model=self.model_id, config=config) as session:
                    self.session = session
                    self.session_ready.set()
                    self.main_win.bridge.statusUpdated.emit("READY")
                    
                    async for response in session.receive():
                        if not self._running: break
                        await self._handle_server_response(response)
                
                # If we get here, the session closed normally
                self.session = None
                self.session_ready.clear()
                retry_delay = 0.3
            except Exception as e:
                # Log full error for diagnostics
                import traceback
                print(f"Socket connection error: {e}")
                traceback.print_exc()
                
                # If session resumption failed (e.g. token expired), reset it
                if self.resumption_token:
                    self.main_win.bridge.logReceived.emit("ACTION", "Resumption failed. Establishing a fresh neural session...")
                    self.resumption_token = None

                self.session = None
                if self._running:
                    # Only signal RE-LINKING if this was a failure
                    self.main_win.bridge.statusUpdated.emit("RE-LINKING")
                    retry_delay = 1.0
                else:
                    break
            
            if self._running:
                await asyncio.sleep(retry_delay)

    def dispatch_text(self, text):
        """Dispatch user text on the current session."""
        if self.session and self.loop and self._running:
            asyncio.run_coroutine_threadsafe(
                self.session.send_client_content(
                    turns=[types.Content(parts=[types.Part.from_text(text=text)], role='user')],
                    turn_complete=True
                ), self.loop
            )

    def send_audio_chunk(self, data):
        # Only stream audio chunks if a tool call is not pending (avoiding 1008 protocol violation)
        if self.session and self.loop and self._running and self.voice_mode and not self.tool_call_pending:
            asyncio.run_coroutine_threadsafe(
                self.session.send_realtime_input(
                    media=types.Blob(mime_type="audio/pcm", data=data)
                ), self.loop
            )

    async def _handle_server_response(self, response):
        try:
            res_update = getattr(response, 'session_resumption_update', None)
            if res_update and getattr(res_update, 'new_handle', None):
                self.resumption_token = res_update.new_handle

            text_content = ""

            if hasattr(response, 'server_content') and response.server_content:
                content = response.server_content
                if hasattr(content, 'model_turn') and content.model_turn:
                    for part in content.model_turn.parts:
                        if hasattr(part, 'text') and part.text:
                            text_content += part.text
                        
                        # Realtime PCM voice playback
                        if getattr(part, 'inline_data', None) and part.inline_data:
                            if self.voice_mode and self.audio_player:
                                self.main_win.bridge.statusUpdated.emit("SPEAKING")
                                self.audio_player.play_chunk(part.inline_data.data)
                
                if getattr(content, 'turn_complete', False):
                    self.turn_complete_received = True
                    self.main_win.bridge.statusUpdated.emit("READY")

                if hasattr(content, 'output_transcription') and content.output_transcription:
                    text_content += content.output_transcription.text

            if hasattr(response, 'text') and response.text:
                text_content += response.text

            if text_content:
                self.main_win.bridge.logReceived.emit("JARVIS", text_content)

            tool_call = getattr(response, 'tool_call', None)
            if tool_call and getattr(tool_call, 'function_calls', None):
                self.tool_call_pending = True
                try:
                    for call in tool_call.function_calls:
                        await self._execute_tool_sequence(call)
                finally:
                    self.tool_call_pending = False
        except Exception as e:
            import traceback
            self.main_win.bridge.logReceived.emit("JARVIS", f"Response handler error (resilient): {e}")
            traceback.print_exc()

    async def _execute_tool_sequence(self, call):
        name = call.name
        args = call.args
        call_id = call.id
        result = "Done"

        self.main_win.bridge.logReceived.emit("ACTION", f"Deploying sensor tool: {name}...")

        try:
            if name == "open_application":
                cmd = args.get("command")
                os.startfile(cmd) if os.name == 'nt' else os.system(f"{cmd} &")
                result = f"Successfully launched {cmd}"
            elif name == "take_screenshot":
                # Upgraded Screenshot: Save and transmit image back to Gemini Live
                screenshot_path = BASE_DIR / "screenshot.png"
                pyautogui.screenshot(str(screenshot_path))
                
                # Load image, scale for efficiency and send as inline media
                img = pyautogui.screenshot()
                img.thumbnail((1024, 1024))
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=80)
                img_bytes = buf.getvalue()
                
                # Transmit screenshot into Active Live Session in background
                if self.session and self.loop:
                    asyncio.run_coroutine_threadsafe(
                        self.session.send_realtime_input(
                            media=types.Blob(mime_type="image/jpeg", data=img_bytes)
                        ), self.loop
                    )
                result = f"Screenshot saved to {screenshot_path} and injected into live visual buffers."
            elif name == "get_system_info":
                import platform
                info = {
                    "OS": platform.system(),
                    "Version": platform.version(),
                    "Processor": platform.processor(),
                    "Cores": psutil.cpu_count(logical=False),
                    "Memory": f"{round(psutil.virtual_memory().total / (1024**3), 2)} GB",
                    "Battery": f"{psutil.sensors_battery().percent}%" if psutil.sensors_battery() else "AC Power"
                }
                result = json.dumps(info)
            elif name == "execute_shell":
                import subprocess
                cmd = args.get("command")
                res = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, timeout=30)
                result = res.decode('utf-8')
            elif name == "read_clipboard":
                result = pyperclip.paste()
                if not result:
                    result = "[Clipboard is currently empty]"
            elif name == "write_clipboard":
                text = args.get("text")
                pyperclip.copy(text)
                result = f"Text copied to clipboard ({len(text)} chars)."
            elif name == "type_text":
                text = args.get("text")
                pyautogui.write(text, interval=0.01)
                result = f"Typed {len(text)} characters."
            elif name == "press_key":
                key = args.get("key")
                if '+' in key:
                    keys = key.split('+')
                    pyautogui.hotkey(*keys)
                else:
                    pyautogui.press(key)
                result = f"Executed keypress {key}."
        except subprocess.TimeoutExpired:
            result = "Execution timed out (30s limit)."
        except Exception as e:
            result = f"Tool failure: {str(e)}"

        # Send tool response (Upgraded to use send_tool_response to avoid deprecation warnings)
        if self.session:
            try:
                await self.session.send_tool_response(
                    function_responses=[
                        types.FunctionResponse(name=name, id=call_id, response={"result": result})
                    ]
                )
            except Exception as e:
                self.main_win.bridge.logReceived.emit("JARVIS", f"Tool response transmit failed (non-critical): {e}")

class JarvisMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("J.A.R.V.I.S. Core Matrix HUD")
        self.resize(1280, 820) 

        self.ui_ready = False
        self.view = QWebEngineView()
        self.setCentralWidget(self.view)

        # Clear caching to ensure HUD visual updates propagate immediately
        self.view.page().profile().setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
        
        self.bridge = PyBridge(self)
        self.channel = QWebChannel()
        self.channel.registerObject("pyBridge", self.bridge)
        self.view.page().setWebChannel(self.channel)

        self.view.setHtml(UI_HTML)
        self.runner = None
        self.recorder = None

        # Setup and start System Diagnostics telemetry
        self.telemetry_thread = TelemetryWorker()
        self.telemetry_thread.stats_updated.connect(self._safe_update_stats)
        self.telemetry_thread.start()

    def start_backend_engine(self):
        if not self.runner:
            self.runner = JarvisCoreRunner(self)

    def _safe_update_stats(self, cpu, mem, disk, net_in, net_out, active_win):
        if self.ui_ready:
            # Safely escape backslashes and single quotes for JS execution
            esc_win = active_win.replace('\\', '\\\\').replace("'", "\\'")
            self.bridge.telemetryUpdated.emit(cpu, mem, disk, net_in, net_out, esc_win)

    def set_mic_active(self, active):
        if active:
            if not self.recorder:
                self.recorder = AudioRecorder(self._handle_mic_audio)
                self.recorder.start()
        else:
            if self.recorder:
                self.recorder.stop()
                self.recorder = None

    def _handle_mic_audio(self, data):
        if self.runner:
            self.runner.send_audio_chunk(data)

    def closeEvent(self, event):
        if self.runner:
            self.runner.stop()
        if self.recorder:
            self.recorder.stop()
        self.telemetry_thread.requestInterruption()
        self.telemetry_thread.quit()
        self.telemetry_thread.wait()
        super().closeEvent(event)

if __name__ == "__main__":
    # Disable PySide sandbox for smooth WebEngine rendering on various systems
    sys.argv.append("--no-sandbox")
    app = QApplication(sys.argv)
    main_win = JarvisMainWindow()
    main_win.show()
    sys.exit(app.exec())
