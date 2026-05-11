import sys
import os
import signal
import time
import threading
import subprocess
import socket
import json
import tempfile
import urllib.request
from urllib.parse import urlparse
from PyQt6.QtWidgets import (QApplication, QLabel, QWidget, QHBoxLayout, 
                             QPushButton, QVBoxLayout, QGraphicsDropShadowEffect,
                             QSystemTrayIcon, QMenu, QInputDialog, QFileIconProvider)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QFileInfo
from PyQt6.QtGui import QIcon, QPixmap, QAction
from pydantic import BaseModel
import ollama

# Suppress macOS MallocStackLogging warnings
os.environ['MALLOC_STACK_LOGGING'] = '0'
# Also suppress general AppleScript/subprocess noise if needed
os.environ['NSUnbufferedIO'] = 'YES'

# --- 1. Helper Functions (Native macOS/AppleScript) ---

def run_applescript(script):
    """Runs an AppleScript command and returns the output."""
    try:
        result = subprocess.run(
            ['osascript', '-e', script], 
            capture_output=True, 
            text=True, 
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None

def get_active_app():
    """Gets the true localized name of the currently active (frontmost) application."""
    script = "ObjC.import('AppKit'); $.NSWorkspace.sharedWorkspace.frontmostApplication.localizedName.js"
    try:
        result = subprocess.run(
            ['osascript', '-l', 'JavaScript', '-e', script], 
            capture_output=True, 
            text=True, 
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None

def get_all_running_apps():
    """Gets a list of all currently running applications with windows."""
    script = "ObjC.import('AppKit'); var apps = $.NSWorkspace.sharedWorkspace.runningApplications.js; var names = []; for(var i=0; i<apps.length; i++) { if(apps[i].activationPolicy == 0) names.push(apps[i].localizedName.js); }; names.join('|||');"
    try:
        result = subprocess.run(
            ['osascript', '-l', 'JavaScript', '-e', script], 
            capture_output=True, 
            text=True, 
            check=True
        )
        if result.stdout:
            apps = [app.strip() for app in result.stdout.strip().split("|||") if app.strip() and app.strip() not in ["Python", "Finder"]]
            front_app = get_active_app()
            if front_app in apps:
                apps.remove(front_app)
                apps.insert(0, front_app)
            return apps
    except subprocess.CalledProcessError:
        pass
    return []

def get_app_path(app_name):
    """Gets the path to an application bundle given its name."""
    script = f'POSIX path of (path to application "{app_name}")'
    return run_applescript(script)

def get_browser_info(browser_name):
    """Gets the current URL and Title from the specified browser."""
    script = ""
    if browser_name in ["Google Chrome", "Brave Browser", "Microsoft Edge", "Arc"]:
        script = f'''
        tell application "{browser_name}"
            if (count of windows) > 0 then
                set tabUrl to URL of active tab of front window
                set tabTitle to title of active tab of front window
                return tabUrl & "|||" & tabTitle
            end if
        end tell
        '''
    elif browser_name == "Safari":
        script = '''
        tell application "Safari"
            if (count of documents) > 0 then
                set tabUrl to URL of front document
                set tabTitle to name of front document
                return tabUrl & "|||" & tabTitle
            end if
        end tell
        '''
    
    if script:
        result = run_applescript(script)
        if result and "|||" in result:
            url, title = result.split("|||", 1)
            return url, title
        elif result:
            return result, "Unknown Title"
    return None, None

def get_zoom_state():
    """Determines the state of the Zoom application based on its window title."""
    script = '''
    tell application "System Events"
        tell process "zoom.us"
            if exists (window 1) then
                return name of window 1
            else
                return "No Window"
            end if
        end tell
    end tell
    '''
    window_name = run_applescript(script)
    if not window_name:
        return "Unknown State"
    
    if "Zoom Meeting" in window_name:
        return "In a Meeting"
    elif window_name == "Zoom":
        return "On Homepage/Main Window"
    elif window_name == "No Window":
        return "Running in background (No Window)"
    else:
        return f"Other State (Window Title: '{window_name}')"

def get_generic_window_title(app_name):
    """Tries to get the frontmost window title for any other app."""
    script = f'''
    tell application "System Events"
        tell process "{app_name}"
            if exists (window 1) then
                return name of window 1
            end if
        end tell
    end tell
    '''
    return run_applescript(script)

def is_ollama_active():
    try:
        with socket.create_connection(("localhost", 11434), timeout=1):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False

def activate_ollama():
    try:
        print("Activating Ollama...")
        subprocess.run(['open', '-a', 'Ollama'], check=False)
    except Exception as e:
        print(f"Failed to activate Ollama: {e}")

# --- 2. Keyboard & Shortcuts ---

try:
    from pynput.keyboard import Controller as KeyboardController, Key
    keyboard = KeyboardController()
    PYNPUT_AVAILABLE = True
except Exception as e:
    PYNPUT_AVAILABLE = False
    keyboard = None
    print(f"pynput not available: {e}")

def execute_shortcut(shortcut_str, target_app_name=None, restore_app_name=None):
    if not keyboard or not shortcut_str or shortcut_str.upper() in ["NONE", "", "N/A"]:
        return
        
    current_active_app = get_active_app()
        
    if target_app_name and target_app_name != current_active_app:
        print(f"Refocusing {target_app_name} before executing shortcut...")
        try:
            script = f'tell application "{target_app_name}" to activate'
            subprocess.run(['osascript', '-e', script], check=False)
            time.sleep(0.15)
        except Exception as e:
            print(f"Failed to reactivate {target_app_name}: {e}")
            
    print(f"Executing shortcut: {shortcut_str}")
    parts = shortcut_str.replace("_", "+").replace("-", "+").split("+")
    keys_to_press = []
    
    for part in parts:
        part = part.upper().strip()
        if part in ["CMD", "COMMAND", "META"]:
            keys_to_press.append(Key.cmd)
        elif part in ["CTRL", "CONTROL"]:
            keys_to_press.append(Key.ctrl)
        elif part in ["SHIFT"]:
            keys_to_press.append(Key.shift)
        elif part in ["ALT", "OPTION"]:
            keys_to_press.append(Key.alt)
        elif part == "ENTER":
            keys_to_press.append(Key.enter)
        elif part == "SPACE":
            keys_to_press.append(Key.space)
        elif part == "ESC":
            keys_to_press.append(Key.esc)
        else:
            if len(part) == 1:
                keys_to_press.append(part.lower())
                
    if not keys_to_press:
        return
        
    for k in keys_to_press:
        keyboard.press(k)
        
    time.sleep(0.05)
    
    for k in reversed(keys_to_press):
        keyboard.release(k)

    if current_active_app and current_active_app != target_app_name and current_active_app != "Python":
        print(f"Restoring focus back to {current_active_app}...")
        try:
            time.sleep(0.1)
            script = f'tell application "{current_active_app}" to activate'
            subprocess.run(['osascript', '-e', script], check=False)
        except Exception as e:
            pass

# --- 3. AI & Data Models ---

OLLAMA_MODEL = "gemma4:31b-cloud"
ACTIONS_CACHE = {}

class ActionDef(BaseModel):
    action_name: str
    shortcut: str

class AppActions(BaseModel):
    app_name: str
    inferred_context: str
    recommended_actions: list[ActionDef]

class UpdateSignal(QObject):
    update_ui = pyqtSignal(dict)
    ollama_status_changed = pyqtSignal(bool)

# --- 4. UI Components ---

class GlassButton(QPushButton):
    def __init__(self, text=""):
        super().__init__(text)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedHeight(32) # Enforce consistent height
        self.setStyleSheet("""
            QPushButton {
                background-color: rgba(40, 40, 40, 240);
                color: white;
                border: 1px solid rgba(20, 20, 20, 255);
                border-radius: 16px;
                padding: 0px 16px;
                font-family: 'Helvetica Neue', Arial;
                font-size: 13px;
                font-weight: bold;
                text-align: left;
            }
            QPushButton:hover {
                background-color: rgba(70, 70, 70, 255);
                border: 1px solid rgba(40, 40, 40, 255);
                border-radius: 16px;
            }
            QPushButton:pressed {
                background-color: rgba(20, 20, 20, 255);
                border-radius: 16px;
            }
        """)

class NavButton(QPushButton):
    def __init__(self, text=""):
        super().__init__(text)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: rgba(180, 180, 180, 255);
                border: none;
                font-family: 'Helvetica Neue', Arial;
                font-size: 16px;
                font-weight: 800;
            }
            QPushButton:hover {
                color: rgba(255, 255, 255, 255);
            }
            QPushButton:pressed {
                color: rgba(100, 100, 100, 255);
            }
            QPushButton:disabled {
                color: rgba(60, 60, 60, 255);
            }
        """)

class StateController:
    def __init__(self):
        self.manual_override_app = None
        self.force_refresh = False
        self.apps_list = []
        
    def handle_app_change(self, delta):
        if not self.apps_list:
            return
        if self.manual_override_app in self.apps_list:
            idx = self.apps_list.index(self.manual_override_app)
        else:
            idx = 0
            
        new_idx = (idx + delta) % len(self.apps_list)
        self.manual_override_app = self.apps_list[new_idx]
        self.force_refresh = True
        
    def handle_refresh(self):
        self.force_refresh = True

class OverlayWidget(QWidget):
    def __init__(self, tray_icon=None, info_action=None, activate_action=None, model_action=None):
        super().__init__()
        self.controller = StateController()
        self.tray_icon = tray_icon
        self.info_action = info_action
        self.activate_action = activate_action
        self.model_action = model_action
        self.current_app = None
        
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        self.container = QWidget(self)
        self.container.setObjectName("mainContainer")
        self.container.setStyleSheet("""
            QWidget#mainContainer {
                background: transparent;
                border: none;
            }
        """)
        
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        main_layout.addWidget(self.container)
        
        # --- App Header ---
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)
        
        self.close_btn = NavButton("✕")
        self.close_btn.setFixedSize(20, 20)
        self.close_btn.setStyleSheet(self.close_btn.styleSheet() + "font-size: 16px; color: rgba(255, 255, 255, 120);")
        self.close_btn.clicked.connect(QApplication.quit)
        header_layout.addWidget(self.close_btn)
        
        self.prev_btn = NavButton("<")
        self.prev_btn.setFixedSize(24, 24)
        self.prev_btn.clicked.connect(self.on_prev_clicked)
        header_layout.addWidget(self.prev_btn)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(28, 28)
        self.icon_label.setStyleSheet("background: transparent; border: none;")
        header_layout.addWidget(self.icon_label)
        self.icon_label.hide()
        
        self.app_label = QLabel("DONE")
        self.app_label.setStyleSheet("""
            color: #ddd; 
            font-weight: bold; 
            font-size: 16px; 
            font-family: 'Helvetica Neue', Arial;
            background: transparent; 
            border: none;
        """)
        header_layout.addWidget(self.app_label)
        self.app_label.hide()

        self.refresh_btn = NavButton("⟳")
        self.refresh_btn.setFixedSize(24, 24)
        self.refresh_btn.setStyleSheet(self.refresh_btn.styleSheet() + "font-size: 16px;")
        self.refresh_btn.clicked.connect(self.on_refresh_clicked)
        header_layout.addWidget(self.refresh_btn)
        
        self.next_btn = NavButton(">")
        self.next_btn.setFixedSize(24, 24)
        self.next_btn.clicked.connect(self.on_next_clicked)
        header_layout.addWidget(self.next_btn)
        
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        # --- Inferred Context ---
        self.context_label = QLabel("Waiting for an app to open...")
        self.context_label.setWordWrap(True)
        self.context_label.setStyleSheet("""
            color: #999; 
            font-size: 13px; 
            font-family: 'Helvetica Neue', Arial;
            margin-left: 2px;
            margin-bottom: 10px;
            background: transparent;
            border: none;
        """)
        layout.addWidget(self.context_label)
        
        # --- Dynamic Action Buttons ---
        self.buttons_layout = QVBoxLayout()
        self.buttons_layout.setSpacing(10)
        layout.addLayout(self.buttons_layout)
        
        layout.addStretch()
        
        self.updater = UpdateSignal()
        self.updater.update_ui.connect(self.update_ui_state)
        self.updater.ollama_status_changed.connect(self.update_ollama_status)
        
        self.setFixedWidth(350)        
        self.provider = QFileIconProvider()
        
        self._drag_active = False
        self._drag_start_position = None

    def on_prev_clicked(self):
        self.controller.handle_app_change(-1)

    def on_next_clicked(self):
        self.controller.handle_app_change(1)

    def on_refresh_clicked(self):
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("...")
        self.controller.handle_refresh()

    def showEvent(self, event):
        super().showEvent(event)
        screen = QApplication.primaryScreen().geometry()
        x = 40
        y = screen.height() - self.height() - 150
        self.move(x, y)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_active = True
            self._drag_start_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if getattr(self, '_drag_active', False):
            self.move(event.globalPosition().toPoint() - self._drag_start_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_active = False
            event.accept()

    def update_ollama_status(self, is_active):
        status_text = "active" if is_active else "offline"
        if self.tray_icon:
            self.tray_icon.setToolTip(f"DONE ({status_text}) - {OLLAMA_MODEL}")

        if self.info_action:
            if is_active:
                self.info_action.setText("DONE is active")
            else:
                self.info_action.setText("Ollama is offline")
        
        if self.model_action:
            self.model_action.setText(f"⚡︎ {OLLAMA_MODEL}")
            self.model_action.setVisible(True)
            
        if self.activate_action:
            self.activate_action.setVisible(not is_active)

    def change_model(self):
        global OLLAMA_MODEL, ACTIONS_CACHE
        new_model, ok = QInputDialog.getText(self, "Change Model", "Enter Ollama model name:", text=OLLAMA_MODEL)
        if ok and new_model.strip():
            OLLAMA_MODEL = new_model.strip()
            ACTIONS_CACHE.clear()
            print(f"Model changed to: {OLLAMA_MODEL}")
            self.update_ollama_status(is_ollama_active())
            self.controller.force_refresh = True

    def update_ui_state(self, state):
        app_path = state.get('app_path')
        if app_path:
            self.icon_label.show()
            if app_path.endswith('.png'):
                self.icon_label.setPixmap(QPixmap(app_path).scaled(28, 28, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else:
                icon = self.provider.icon(QFileInfo(app_path))
                self.icon_label.setPixmap(icon.pixmap(28, 28))
            
        display_name = state.get('display_name', state.get('app_name', 'Unknown'))
        target_app = state.get('target_app', state.get('app_name', 'Unknown'))
        restore_app = state.get('real_active_app', 'Unknown')
        
        status = state.get('status')
        ollama_active = state.get('ollama_active', True)
        
        if status == 'generating':
            self.app_label.show()
            self.app_label.setText(f"{display_name}")
            if not ollama_active:
                self.context_label.setText("Ollama is offline")
            else:
                self.context_label.setText("Generating actions...")
                # Also reset color to normal grey while generating
                self.context_label.setStyleSheet(self.context_label.styleSheet().replace("color: #f66;", "color: #999;"))
            self.refresh_btn.setEnabled(False)
            self.refresh_btn.setText("...")
            
            if target_app != self.current_app:
                while self.buttons_layout.count():
                    item = self.buttons_layout.takeAt(0)
                    widget = item.widget()
                    if widget is not None:
                        widget.deleteLater()
            self.current_app = target_app
        else:
            self.app_label.show()
            self.app_label.setText(f"{display_name}")
            if not ollama_active:
                self.context_label.setText("Ollama is offline")
            else:
                inferred = state.get('inferred_context')
                if inferred:
                    self.context_label.setText(inferred)
                else:
                    self.context_label.setText(state.get('state_info', ''))
            self.refresh_btn.setEnabled(True)
            self.refresh_btn.setText("⟳")
            
            error = state.get('error')
            if error:
                self.context_label.setText(f"AI Error: {error}")
                # Ensure it's red for errors
                if "color: #f66;" not in self.context_label.styleSheet():
                    self.context_label.setStyleSheet(self.context_label.styleSheet().replace("color: #999;", "color: #f66;"))
                    if "color: #f66;" not in self.context_label.styleSheet():
                         self.context_label.setStyleSheet(self.context_label.styleSheet() + "color: #f66;")
            else:
                # Revert to normal grey if no error
                self.context_label.setStyleSheet(self.context_label.styleSheet().replace("color: #f66;", "color: #999;"))
            
        if status == 'done':
            while self.buttons_layout.count():
                item = self.buttons_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                    
            actions = state.get('actions', [])
            if actions:
                buttons_added = 0
                valid_actions = [act for act in actions if act.shortcut and act.shortcut.upper() not in ["NONE", "", "N/A"]]
                for i, act in enumerate(valid_actions):
                    shortcut = act.shortcut
                    action_container = QWidget()
                    action_container.setFixedHeight(32)
                    action_container.setStyleSheet("background: transparent; border: none;")
                    action_layout = QHBoxLayout(action_container)
                    action_layout.setContentsMargins(0, 0, 0, 0)
                    action_layout.setSpacing(12)
                    
                    capsule = QLabel()
                    capsule.setFixedSize(6, 32)
                    bg_color = "rgba(255, 255, 255, 200)"
                    border_color = "rgba(0, 0, 0, 60)"
                    if i == len(valid_actions) - 1:
                        bg_color = "rgba(160, 186, 212, 200)"
                        border_color = "rgba(100, 126, 152, 150)"
                    capsule.setStyleSheet(f"background-color: {bg_color}; border: 1px solid {border_color}; border-radius: 3px;")
                    action_layout.addWidget(capsule)
                    btn = GlassButton(f"{act.action_name}")
                    # Run execute_shortcut in a separate thread to keep the UI responsive
                    btn.clicked.connect(lambda checked=False, s=shortcut, target=target_app, restore=restore_app: 
                                        threading.Thread(target=execute_shortcut, args=(s, target, restore), daemon=True).start())
                    action_layout.addWidget(btn)
                    action_layout.addStretch()
                    self.buttons_layout.addWidget(action_container)
                    buttons_added += 1
                
                if buttons_added == 0 and not state.get('error'):
                    info_label = QLabel("No actionable shortcuts found.")
                    info_label.setStyleSheet("color: #ccc; background: transparent; border: none;")
                    self.buttons_layout.addWidget(info_label)
            elif not state.get('error'):
                info_label = QLabel("No actionable shortcuts found.")
                info_label.setStyleSheet("color: #ccc; background: transparent; border: none;")
                self.buttons_layout.addWidget(info_label)

# --- 5. AI Interaction ---

def fetch_actions_from_ollama(app_name, state_info):
    cache_key = (app_name, state_info)
    if cache_key in ACTIONS_CACHE:
        print(f"--- USING CACHED ACTIONS FOR {app_name} ---")
        return ACTIONS_CACHE[cache_key]
        
    try:
        schema = AppActions.model_json_schema()
        messages = [
            {
                'role': 'system',
                'content': f"You are a smart context assistant. Suggest exactly 3 short, actionable tasks (1-4 words each) based on the user's active app and current context. If the app is a web browser and a URL or Page Title is provided, prioritize actions specific to that website (e.g., for YouTube suggest Play/Pause, for Gmail suggest Compose). Include common macOS keyboard shortcuts for these actions using '+' as a separator (like CMD+C, CMD+SHIFT+V). If there is no shortcut, put 'None'. You MUST output ONLY raw JSON. No markdown blocks. Use this schema: {schema}"
            },
            {
                'role': 'user',
                'content': f"App: {app_name}\nContext/Window: {state_info}"
            }
        ]
        
        print(f"------- SENDING TO OLLAMA -------")
        print(f"User Prompt:'{messages[1]['content']}'")
        print("---------------------------------")

        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=messages,
            format=schema
        )
        
        raw_output = response['message']['content'].strip()
        
        print(f"------- OLLAMA RESPONSE -------")
        print(f"{raw_output}")
        print("-------------------------------")
        
        content = raw_output
        if content.startswith('```json'): content = content[7:]
        if content.startswith('```'): content = content[3:]
        if content.endswith('```'): content = content[:-3]
        content = content.strip()
        
        data = AppActions.model_validate_json(content)
        result = (data.recommended_actions, data.inferred_context, None)
        ACTIONS_CACHE[cache_key] = result
        return result
        
    except Exception as e:
        error_msg = str(e)
        if "connect" in error_msg.lower(): error_msg = "Could not connect to Ollama"
        elif "timeout" in error_msg.lower(): error_msg = "Request timed out"
        else: error_msg = "Model failed to generate response"
        print(f"\n------- OLLAMA ERROR -------\n{e}\n-----------------------------")
        return [], "", error_msg

# --- 6. Main Monitoring Loop ---

def monitor_loop(updater, controller):
    last_state = None
    last_real_active_app = None
    last_ollama_status = None
    
    try:
        while True:
            # Check Ollama status
            ollama_active = is_ollama_active()
            if ollama_active != last_ollama_status:
                updater.ollama_status_changed.emit(ollama_active)
                last_ollama_status = ollama_active

            real_active_app = get_active_app()
            
            # Ignore the app itself (DONE)
            if real_active_app in ["DONE"]:
                if last_real_active_app: 
                    real_active_app = last_real_active_app
                else:
                    time.sleep(1)
                    continue
            else:
                last_real_active_app = real_active_app
                
            new_apps_list = get_all_running_apps()
            if new_apps_list: controller.apps_list = new_apps_list
            
            # Determine which app to monitor (manual override or current active)
            if not controller.manual_override_app: 
                app_name = real_active_app
            else: 
                app_name = controller.manual_override_app
                
            # If manual app is no longer running, fallback to real active app
            if app_name not in controller.apps_list and app_name != real_active_app:
                controller.manual_override_app = None
                app_name = real_active_app
                
            app_path = get_app_path(app_name) if app_name else None
            state_info = ""
            display_name = app_name

            if app_name in ["Google Chrome", "Safari", "Brave Browser", "Microsoft Edge", "Arc", "Firefox"]:
                url, title = get_browser_info(app_name)
                state_info = f"URL: {url}\nPage: {title}"
                if title and title != "Unknown Title":
                    display_name = title[:40] + "..." if len(title) > 40 else title
                try:
                    if url and not url.startswith("Unknown"):
                        domain = urlparse(url).netloc
                        favicon_path = os.path.join(tempfile.gettempdir(), f"{domain}_favicon.png")
                        if not os.path.exists(favicon_path):
                            urllib.request.urlretrieve(f"https://www.google.com/s2/favicons?domain={domain}&sz=64", favicon_path)
                        app_path = favicon_path
                except: pass
            else:
                window_title = get_generic_window_title(app_name)
                state_info = f"Window: {window_title}" if window_title else "?"
            
            raw_state = f"{app_name} | {state_info}"
            if raw_state != last_state or controller.force_refresh:
                controller.force_refresh = False
                updater.update_ui.emit({
                    'status': 'generating', 'app_name': app_name, 'display_name': display_name,
                    'target_app': app_name, 'real_active_app': real_active_app, 'app_path': app_path,
                    'state_info': state_info, 'ollama_active': ollama_active
                })
                
                actions, inferred_context, error = fetch_actions_from_ollama(app_name, state_info)
                updater.update_ui.emit({
                    'status': 'done', 'app_name': app_name, 'display_name': display_name,
                    'target_app': app_name, 'real_active_app': real_active_app, 'app_path': app_path,
                    'actions': actions, 'inferred_context': inferred_context, 'state_info': state_info,
                    'ollama_active': ollama_active, 'error': error
                })
                last_state = raw_state
            time.sleep(1.5)
    except Exception as e:
        print(f"Error in monitor loop: {e}")

# --- 7. Entry Point ---

if __name__ == "__main__":
    try:
        # Enable High-DPI scaling if available
        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except AttributeError:
        pass

    app = QApplication(sys.argv)
    
    try:
        # Enable high-quality icons on Retina displays if available
        app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)
    except AttributeError:
        pass
    
    app.setQuitOnLastWindowClosed(False)
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # Hide app from Dock
    try:
        import ctypes
        import ctypes.util
        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library('objc'))
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.objc_msgSend.restype = ctypes.c_void_p
        objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        nsshareapp_sel = objc.sel_registerName(b"sharedApplication")
        nsapp_class = objc.objc_getClass(b"NSApplication")
        app_obj = objc.objc_msgSend(nsapp_class, nsshareapp_sel)
        set_policy_sel = objc.sel_registerName(b"setActivationPolicy:")
        objc.objc_msgSend_policy = objc.objc_msgSend
        objc.objc_msgSend_policy.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
        objc.objc_msgSend_policy(app_obj, set_policy_sel, 1)
    except Exception as e:
        print(f"Failed to set activation policy: {e}")
    
    tray_icon = QSystemTrayIcon(app)
    assets_dir = os.path.join(os.path.dirname(__file__), "assets")
    icon_path = os.path.join(assets_dir, "tray_icon.png")
    if os.path.exists(icon_path):
        custom_icon = QIcon(icon_path)
        # On macOS, setting setIsMask(True) tells the system to treat this as a 
        # template image, which handles scaling and theme colors automatically.
        custom_icon.setIsMask(True) 
        tray_icon.setIcon(custom_icon)
    else:
        tray_icon.setIcon(app.style().standardIcon(app.style().StandardPixmap.SP_ComputerIcon))
    
    tray_menu = QMenu()
    info_action = QAction(f"DONE is active", app)
    info_action.setEnabled(False)
    tray_menu.addAction(info_action)

    model_action = QAction(f"⚡︎ {OLLAMA_MODEL}", app)
    model_action.setEnabled(False)
    tray_menu.addAction(model_action)

    tray_menu.addSeparator()
    activate_action = QAction("Activate Ollama", app)
    activate_action.setShortcut("Ctrl+L")
    activate_action.triggered.connect(activate_ollama)
    activate_action.setVisible(False)
    tray_menu.addAction(activate_action)
    
    tray_menu.addSeparator()
    change_model_action = QAction("Change Model...", app)
    tray_menu.addAction(change_model_action)
    
    quit_action = QAction("Quit", app)
    quit_action.setShortcut("Ctrl+Q")
    quit_action.triggered.connect(app.quit)
    tray_menu.addAction(quit_action)
    
    tray_icon.setContextMenu(tray_menu)
    tray_icon.setToolTip(f"DONE - {OLLAMA_MODEL}")
    tray_icon.show()
    
    overlay = OverlayWidget(tray_icon, info_action, activate_action, model_action)
    change_model_action.triggered.connect(overlay.change_model) # Connect after overlay created
    overlay.show()
    
    monitor_thread = threading.Thread(target=monitor_loop, args=(overlay.updater, overlay.controller), daemon=True)
    monitor_thread.start()
    
    sys.exit(app.exec())
