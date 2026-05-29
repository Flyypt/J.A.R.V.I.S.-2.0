# 🚀 J.A.R.V.I.S. Core Matrix (Mark XL)

A voice-activated, cyberpunk-inspired desktop AI assistant. This architecture wraps a responsive HTML5/CSS3 HUD inside a native **PyQt6** application window, leveraging **Google GenAI** to bridge advanced LLM cognition with local system automation.

---

## 🛠️ Core Capabilities

* 🌐 **Futuristic HUD:** Powered by a glassmorphic HTML user interface featuring state-driven CSS Arc Reactor animations (Reacts to *Thinking, Listening, and Speaking* states).
* 📊 **Hardware Telemetry:** Direct backend hooks via `psutil` providing real-time data streaming of CPU, Memory, Disk, and Network metrics directly to the HUD.
* 🧠 **State-Free Cognition:** Powered by Google's GenAI SDK, utilizing an aggressive "clean slate" system mandate for high-signal, zero-hallucination command processing.
* 🌉 **Asynchronous Data Bridge:** High-performance, bidirectional event handling utilizing `QWebChannel` to pass data seamlessly between Python and JavaScript.
* 💬 **Advanced Developer Console:** Integrated Markdown parsing (`marked.js`) and live syntax highlighting (`highlight.js`) featuring localized one-click code copy arrays.

---

## 💻 Tech Stack

| Layer | Technologies Used |
| :--- | :--- |
| **Core Architecture** | Python 3.x, `asyncio`, `threading` |
| **Desktop / Rendering** | PyQt6 (`QWebEngineView`, `QWebChannel`) |
| **Cognitive Engine** | Google GenAI SDK |
| **System & Media** | `psutil`, `sounddevice`, `pyautogui`, `pyperclip` |
| **UI Environment** | HTML5, CSS3, JavaScript (`marked.js`, `highlight.js`) |

---

## ⚙️ Engineering & Architecture

### The System Matrix Prompt
The engine operates on a customized neural persona constraint structure, built dynamically at runtime:

```text
You are J.A.R.V.I.S., a super-intelligent AI persona. 
Your tone is sophisticated, articulate, and slightly witty.
You have direct system access via tools. Use them whenever necessary.

Context Relevance Mandate:
- Keep your answers strictly focused on the operator's current query. 
- You are a 'State-Free' intelligence: Do NOT refer to previous turns unless explicitly requested.

```
## 🚀 Installation & Initialization

### 1. Repository Setup
```bash
git clone [https://github.com/Pathetic101/JARVIS-2.0.git](https://github.com/Pathetic101/JARVIS-2.0.git)
cd JARVIS-2.0

```
### 2. Dependency Deployment
```Bash
pip install -r requirements.txt
🛈 Note: Ensure your operating system has native audio drivers installed for sounddevice to map audio queues correctly.

```
### 3. Neural Access Configuration
```Generate a file named api_keys.json within the root directory:

JSON
{
    "GOOGLE_API_KEY": "YOUR_GEMINI_API_KEY_HERE"
}
⚠️ Security Mandate: Do not push api_keys.json to public origin servers. Ensure it is explicitly defined within your .gitignore.

```
### 4. Boot Cycle
```Initialize the native core process framework:

Bash
python main.py

```
### 📝 License
Distributed under the MIT License. See LICENSE for more information.
