"""
LADA v7.0 - OAuth Setup Wizard
Guides users through Gmail and Calendar API setup
"""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QTextEdit, QStackedWidget, QMessageBox,
                             QWidget, QCheckBox)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QIcon
import webbrowser
import json
from pathlib import Path


class OAuthSetupWizard(QDialog):
    """
    Multi-step wizard to help users set up Gmail and Calendar OAuth credentials
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LADA - Gmail & Calendar Setup")
        self.setMinimumSize(700, 500)
        self.credentials_path = Path("config/credentials.json")
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel("📧 Gmail & Calendar Integration Setup")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Stacked widget for pages
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        
        # Pages
        self.stack.addWidget(self._create_welcome_page())
        self.stack.addWidget(self._create_console_page())
        self.stack.addWidget(self._create_credentials_page())
        self.stack.addWidget(self._create_test_page())
        self.stack.addWidget(self._create_complete_page())
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        self.btn_back = QPushButton("← Back")
        self.btn_next = QPushButton("Next →")
        self.btn_skip = QPushButton("Skip for Now")
        
        self.btn_back.clicked.connect(self.go_back)
        self.btn_next.clicked.connect(self.go_next)
        self.btn_skip.clicked.connect(self.skip_setup)
        
        nav_layout.addWidget(self.btn_back)
        nav_layout.addStretch()
        nav_layout.addWidget(self.btn_skip)
        nav_layout.addWidget(self.btn_next)
        layout.addLayout(nav_layout)
        
        self.update_buttons()
    
    def _create_welcome_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        
        text = QLabel("""
<h2>Welcome to Gmail & Calendar Setup!</h2>

<p>This wizard will help you integrate Gmail and Google Calendar with LADA.</p>

<h3>What you'll need:</h3>
<ul>
    <li>A Google Account</li>
    <li>5-10 minutes of time</li>
    <li>Access to Google Cloud Console</li>
</ul>

<h3>Features you'll unlock:</h3>
<ul>
    <li>✉️ Send emails directly from LADA</li>
    <li>📧 Check inbox and read emails</li>
    <li>📅 Create calendar events with voice commands</li>
    <li>📆 Get daily schedule briefings</li>
</ul>

<p><b>Note:</b> You can skip this setup and enable it later from Settings.</p>
        """)
        text.setWordWrap(True)
        layout.addWidget(text)
        layout.addStretch()
        
        return page
    
    def _create_console_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        
        text = QLabel("""
<h2>Step 1: Create Google Cloud Project</h2>

<p>Follow these steps in Google Cloud Console:</p>

<h3>1. Go to Google Cloud Console</h3>
<p>Click the button below to open Google Cloud Console.</p>
        """)
        text.setWordWrap(True)
        layout.addWidget(text)
        
        btn_console = QPushButton("🌐 Open Google Cloud Console")
        btn_console.setStyleSheet("padding: 10px; font-size: 14px;")
        btn_console.clicked.connect(lambda: webbrowser.open(
            "https://console.cloud.google.com/projectcreate"
        ))
        layout.addWidget(btn_console)
        
        text2 = QLabel("""
<h3>2. Create a New Project</h3>
<ul>
    <li>Click "CREATE PROJECT"</li>
    <li>Name it: "LADA AI Assistant" (or any name)</li>
    <li>Click "Create"</li>
</ul>

<h3>3. Enable APIs</h3>
<p>After project creation, click below to enable Gmail and Calendar APIs:</p>
        """)
        text2.setWordWrap(True)
        layout.addWidget(text2)
        
        btn_gmail = QPushButton("Enable Gmail API")
        btn_gmail.clicked.connect(lambda: webbrowser.open(
            "https://console.cloud.google.com/apis/library/gmail.googleapis.com"
        ))
        layout.addWidget(btn_gmail)
        
        btn_calendar = QPushButton("Enable Calendar API")
        btn_calendar.clicked.connect(lambda: webbrowser.open(
            "https://console.cloud.google.com/apis/library/calendar-json.googleapis.com"
        ))
        layout.addWidget(btn_calendar)
        
        text3 = QLabel("""
<h3>4. Create OAuth Credentials</h3>
<p>Click below to go to credentials page:</p>
        """)
        text3.setWordWrap(True)
        layout.addWidget(text3)
        
        btn_creds = QPushButton("Create OAuth Credentials")
        btn_creds.clicked.connect(lambda: webbrowser.open(
            "https://console.cloud.google.com/apis/credentials"
        ))
        layout.addWidget(btn_creds)
        
        text4 = QLabel("""
<p>In credentials page:</p>
<ul>
    <li>Click "+ CREATE CREDENTIALS" → "OAuth client ID"</li>
    <li>Application type: "Desktop app"</li>
    <li>Name: "LADA Desktop"</li>
    <li>Click "Create"</li>
    <li>Download JSON file (click ⬇️ icon)</li>
</ul>
        """)
        text4.setWordWrap(True)
        layout.addWidget(text4)
        
        layout.addStretch()
        return page
    
    def _create_credentials_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        
        text = QLabel("""
<h2>Step 2: Add Credentials to LADA</h2>

<p>Now paste the content of your downloaded JSON file here:</p>
        """)
        text.setWordWrap(True)
        layout.addWidget(text)
        
        self.creds_text = QTextEdit()
        self.creds_text.setPlaceholderText("""Paste your credentials.json content here...

It should look like:
{
  "installed": {
    "client_id": "YOUR_CLIENT_ID.apps.googleusercontent.com",
    "client_secret": "YOUR_SECRET",
    ...
  }
}""")
        self.creds_text.setMinimumHeight(200)
        layout.addWidget(self.creds_text)
        
        btn_save = QPushButton("💾 Save Credentials")
        btn_save.clicked.connect(self.save_credentials)
        layout.addWidget(btn_save)
        
        self.save_status = QLabel("")
        layout.addWidget(self.save_status)
        
        layout.addStretch()
        return page
    
    def _create_test_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        
        text = QLabel("""
<h2>Step 3: Test Connection</h2>

<p>Click below to test your Gmail and Calendar connection:</p>
        """)
        text.setWordWrap(True)
        layout.addWidget(text)
        
        btn_test_gmail = QPushButton("📧 Test Gmail Connection")
        btn_test_gmail.clicked.connect(self.test_gmail)
        layout.addWidget(btn_test_gmail)
        
        btn_test_calendar = QPushButton("📅 Test Calendar Connection")
        btn_test_calendar.clicked.connect(self.test_calendar)
        layout.addWidget(btn_test_calendar)
        
        self.test_results = QTextEdit()
        self.test_results.setReadOnly(True)
        self.test_results.setMaximumHeight(150)
        layout.addWidget(self.test_results)
        
        layout.addStretch()
        return page
    
    def _create_complete_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        
        text = QLabel("""
<h2>🎉 Setup Complete!</h2>

<p>Your Gmail and Calendar integration is ready!</p>

<h3>You can now:</h3>
<ul>
    <li>Say: "Send email to John about the meeting"</li>
    <li>Say: "Schedule a meeting tomorrow at 3 PM"</li>
    <li>Say: "What's on my calendar today?"</li>
    <li>Say: "Check my inbox"</li>
</ul>

<p>Close this wizard and start using LADA with email and calendar!</p>
        """)
        text.setWordWrap(True)
        text.setAlignment(Qt.AlignCenter)
        layout.addWidget(text)
        
        layout.addStretch()
        return page
    
    def update_buttons(self):
        page_idx = self.stack.currentIndex()
        total = self.stack.count()
        
        self.btn_back.setEnabled(page_idx > 0)
        self.btn_next.setText("Finish" if page_idx == total - 1 else "Next →")
        self.btn_skip.setVisible(page_idx < total - 1)
    
    def go_back(self):
        idx = self.stack.currentIndex()
        if idx > 0:
            self.stack.setCurrentIndex(idx - 1)
            self.update_buttons()
    
    def go_next(self):
        idx = self.stack.currentIndex()
        if idx < self.stack.count() - 1:
            self.stack.setCurrentIndex(idx + 1)
            self.update_buttons()
        else:
            self.accept()
    
    def skip_setup(self):
        reply = QMessageBox.question(
            self, "Skip Setup",
            "Are you sure you want to skip OAuth setup?\n\n"
            "You can enable it later from Settings → Integrations.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.reject()
    
    def save_credentials(self):
        try:
            creds_json = self.creds_text.toPlainText().strip()
            if not creds_json:
                self.save_status.setText("❌ Please paste your credentials")
                self.save_status.setStyleSheet("color: #ff4444;")
                return
            
            # Validate JSON
            creds_data = json.loads(creds_json)
            
            # Check structure
            if "installed" not in creds_data and "web" not in creds_data:
                raise ValueError("Invalid credentials format")
            
            # Save to file
            self.credentials_path.parent.mkdir(exist_ok=True)
            with open(self.credentials_path, 'w') as f:
                json.dump(creds_data, f, indent=2)
            
            self.save_status.setText("✅ Credentials saved successfully!")
            self.save_status.setStyleSheet("color: #10a37f;")
            
        except json.JSONDecodeError:
            self.save_status.setText("❌ Invalid JSON format")
            self.save_status.setStyleSheet("color: #ff4444;")
        except Exception as e:
            self.save_status.setText(f"❌ Error: {str(e)}")
            self.save_status.setStyleSheet("color: #ff4444;")
    
    def test_gmail(self):
        self.test_results.append("\n📧 Testing Gmail connection...")
        try:
            from modules.google_calendar import GoogleCalendarIntegration
            cal = GoogleCalendarIntegration()
            if cal._authenticate():
                self.test_results.append("✅ Gmail connected successfully!")
            else:
                self.test_results.append("❌ Gmail connection failed")
        except Exception as e:
            self.test_results.append(f"❌ Error: {str(e)}")
    
    def test_calendar(self):
        self.test_results.append("\n📅 Testing Calendar connection...")
        try:
            from modules.google_calendar import GoogleCalendarIntegration
            cal = GoogleCalendarIntegration()
            if cal._authenticate():
                events = cal.get_upcoming_events(max_results=1)
                self.test_results.append(f"✅ Calendar connected! Found {len(events)} events")
            else:
                self.test_results.append("❌ Calendar connection failed")
        except Exception as e:
            self.test_results.append(f"❌ Error: {str(e)}")


def run_oauth_wizard():
    """Standalone function to run the wizard"""
    from PyQt5.QtWidgets import QApplication
    import sys
    
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    wizard = OAuthSetupWizard()
    result = wizard.exec_()
    
    return result == QDialog.Accepted


if __name__ == '__main__':
    run_oauth_wizard()
