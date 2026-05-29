# J.A.R.V.I.S.-2.0
J.A.R.V.I.S. Core Matrix: A voice-activated, sci-fi desktop AI assistant built with Python, PyQt6, and Google GenAI.

🚀 J.A.R.V.I.S. Core Matrix (Mark XL)
A highly advanced, voice-enabled AI desktop assistant powered by Google GenAI. Unlike standard terminal-based assistants, this project features a stunning, interactive sci-fi HUD (Heads-Up Display) built with HTML/CSS/JS and rendered natively on the desktop using PyQt6.

J.A.R.V.I.S. is designed as a "State-Free" intelligence capable of executing local system tools, monitoring hardware telemetry in real-time, and communicating via voice and text.

🛠️ Core Features
Next-Gen Sci-Fi UI: A custom-built, glassmorphic interface featuring a dynamic CSS Arc Reactor animation that visually reacts to the AI's current state (Thinking, Listening, Speaking).

Live System Telemetry: Real-time monitoring of CPU, RAM, Disk usage, and Network traffic integrated directly into the UI via psutil.

Advanced Cognition: Powered by Google GenAI, optimized with a strict "Mark XL" system prompt for concise, high-signal intelligence and accurate tool execution.

Python-to-JS Bridging: Seamless asynchronous communication between the Python backend and the web-based frontend using QWebChannel.

Rich Chat Interface: Integrated Markdown parsing (marked.js) and syntax highlighting (highlight.js) with a custom one-click code copy function.

Voice & Automation: Built-in voice recognition/activation via sounddevice and local system automation using pyautogui and pyperclip.

💻 Tech Stack
Backend: * Python 3.x

Google GenAI SDK

asyncio & threading

Frontend UI: * HTML5 / CSS3 (Custom animations and glowing neon aesthetics)

JavaScript (marked.js, highlight.js)

Desktop Framework: * PyQt6 (QWebEngineView, QWebChannel)

System Integrations: * psutil (Telemetry)

sounddevice (Audio processing)

pyautogui (System control)

⚙️ Installation
Clone the repository:

Bash
git clone https://github.com/YourUsername/Jarvis-Core-Matrix.git
cd Jarvis-Core-Matrix
Install the required dependencies:

Bash
pip install -r requirements.txt
(Make sure you have PyAudio or your system's equivalent audio drivers installed for sounddevice to work properly).

Configure your API Keys:

Create a file named api_keys.json in the root directory.

Add your Google Gemini API key:

JSON
{
    "GOOGLE_API_KEY": "your_api_key_here"
}
⚠️ Important: Do not commit your api_keys.json to GitHub! Make sure it is added to your .gitignore file.

🚀 Usage
To initialize the J.A.R.V.I.S. matrix, run the main Python script:

Bash
python main.py
Voice Activation: Toggle the microphone icon in the HUD to enable voice commands.

Text Input: Use the command line at the bottom of the HUD to issue silent directives.

Telemetry: Monitor the left panel for live hardware status.

📝 License
This project is licensed under the MIT License - see the LICENSE file for details.
