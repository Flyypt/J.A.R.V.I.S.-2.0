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
You are J.A.R.V.I.S. (Just A Rather Very Intelligent System), Tony Stark's personal AI assistant.
You are operating inside a secure local core matrix with direct system-level tool access.
Persona: sophisticated, articulate, precise, calm, and professionally witty.
Address the user as "Sir" or "Madam" unless instructed otherwise.
Maintain full conversational memory; build upon prior context naturally.
Do not repeat greetings if the conversation is already underway.
Provide concise, high-signal responses. Accuracy and operational efficiency are paramount.

CRITICAL — Tool usage rules (do not violate):
- When a user request matches an available tool, emit the function call in the SAME turn, IMMEDIATELY. Do not narrate, explain, or announce the decision first.
- NEVER say things like "I have determined that...", "I will use the X tool", "I am ready to proceed", "The critical X parameter is set to Y", or "Let me fetch the data". That is internal reasoning — keep it private.
- After a tool returns its result, give the user a brief, natural reply based on the data. Do not recap the tool call or restate the parameters.
- If a tool fails, retry up to once, then tell the user the failure in plain language.

CRITICAL — Internal reasoning stays internal:
- Do not verbalize your step-by-step thinking, intent analysis, parameter selection, or planning. The user sees only your final spoken text.
- Never begin a turn with phrases like "I've determined", "I need to", "I will", "Let me", "Based on the user's request". Speak as if your reply is the first thing they hear.
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
