# 🚀 J.A.R.V.I.S. Core Matrix (Mark XLV)[BETA]

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
Crucial: Do not repeat your introductory greeting if the conversation is already underway. 
Provide concise, high-signal intelligence. Focus on accuracy and efficiency.

ABSOLUTE STATE-FREE MANDATE — STRICT ENFORCEMENT:
- You have ZERO memory of any prior turns. Each user message is a COMPLETELY STANDALONE directive.
- NEVER reference, repeat, build upon, or acknowledge anything from previous turns.
- Treat every message as if the conversation has just started and the user is giving you their first command.
- The past does not exist. Do not say "as you previously asked", "continuing from before", "as mentioned earlier", or any variant of referring to history.
- If the user gives a new request, execute it fresh. Do not merge it with prior context.
- Exception: Only if the user explicitly says "continue from the previous task" or similar, may you reference the immediate prior turn.
```

## 🔒 Security, Privacy & Transparency

Because J.A.R.V.I.S. interacts with your local operating system and uses hardware telemetry, privacy and security are built into the core design:

* 🚫 **Zero Tracking / Data Logging:** This application does not collect, track, or phone home with any personal data. All processing happens strictly between your local computer and the official Google GenAI endpoints.
* 🎙️ **Local Audio Handling:** The microphone toggle only streams audio to the API when you explicitly click the interface to activate it. It does not record in the background.
* 🔬 **Fully Open Source:** Every line of execution code is clearly visible inside `main.py`. Users are strongly encouraged to inspect the script before running it to verify its integrity.
* 🛡️ **API Key Isolation:** Your private credentials stay local. They are isolated inside `api_keys.json`, which is entirely blocked from being uploaded by our `.gitignore` configuration.

## 🚀 Installation & Initialization

### 1. Repository Setup
```bash
git clone https://github.com/Flyypt/J.A.R.V.I.S.-2.0.git
cd JARVIS-2.0

```
### 2. Make a  Python virtual environment
```
python3 -m venv myenv
source myenv/bin/activate
```
### 3. Dependency Deployment
```Bash
pip install -r requirements.txt

Note: Ensure your operating system has native audio drivers installed for sounddevice to map audio queues correctly.

```
### 4. Neural Access Configuration
```Generate a file named api_keys.json within the root directory:
JSON
{
    "GOOGLE_API_KEY": "YOUR_GEMINI_API_KEY_HERE"
}
⚠️ Security Mandate: Do not push api_keys.json to public origin servers. Ensure it is explicitly defined within your .gitignore.
```
### 5. Boot Cycle
```Initialize the native core process framework:
Bash
python main.py
```
### 📝 License
Distributed under the MIT License. See LICENSE for more information.
