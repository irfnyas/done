# DONE

**DONE** is a minimalist, context-aware macOS productivity overlay that monitors your active application and uses local AI (via Ollama) to suggest relevant keyboard shortcuts and actions.

## ✨ Features
- **Real-time Monitoring**: Automatically detects active apps, browser URLs, and page titles.
- **AI-Powered Suggestions**: Uses local LLMs (like Gemma or Qwen) to suggest context-specific actions.
- **Accessory UI**: Runs as a sleek, non-intrusive menu bar app.
- **Boomerang Focus**: Executes shortcuts by temporarily focusing the target app and immediately returning to your work.
- **High-DPI Ready**: Fully optimized for Retina displays with sharp icons and text.

## 🚀 Installation

### **Option 1: Use the App (Recommended)**
1. Build the application bundle (see below).
2. Move `dist/DONE.app` to your `/Applications` folder.
3. Grant **Accessibility** permissions in *System Settings > Privacy & Security*.

### **Option 2: Developer Setup**
1. **Clone the repository** and navigate to the directory.
2. **Set up a virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
4. **Run the script**:
   ```bash
   python3 main.py
   ```

## 🛠 Building the .app Bundle
To package the script into a standalone macOS application:
1. Ensure `py2app` is installed: `pip install py2app`
2. Run the build script:
   ```bash
   python3 build.py py2app
   ```
3. Your app will be located in the `dist/` folder.

## ⚠️ Important Note on Permissions
Since **DONE** automates keystrokes and monitors window titles, macOS requires specific permissions:
- **Accessibility**: Required to simulate keyboard events and query window states.
- **Automation**: Required for the terminal/app to control browsers (Chrome, Safari, etc.).

## 📝 License
Copyright © 2026 irfnyas. Licensed under the Apache License, Version 2.0.
