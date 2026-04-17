"""
LADA v7.0 - Main Entry Point
Language Agnostic Digital Assistant with Tamil + English Support

Usage:
    python main.py          # Voice mode (default)
    python main.py voice    # Voice mode
    python main.py text     # Text-only mode
    python main.py gui      # GUI mode (Desktop App)
    python main.py webui    # Web UI (browser-based chat)
    python main.py verify   # Verify all module connections
    python main.py status   # Check backend status
"""

import os
import sys
import logging
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Best-effort UTF-8 console output so emoji/status lines do not crash on cp1252 terminals.
try:
    from modules.console_encoding import configure_console_utf8

    configure_console_utf8()
except Exception:
    pass

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configure logging
log_level = os.getenv('LOG_LEVEL', 'INFO')
log_file = os.getenv('LOG_FILE', 'logs/lada.log')

# Ensure log directory exists
Path(log_file).parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=getattr(logging, log_level.upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class LADA:
    """
    LADA v7.0 - Language Agnostic Digital Assistant
    
    Features:
    - Tamil + English voice support (Thanglish)
    - Quad-AI backend (Ollama, Gemini, Colab)
    - Long-term memory
    - System control
    - Responds in the same language as user
    """
    
    VERSION = "6.0"
    
    def __init__(self, init_voice: bool = True, init_ai: bool = True, init_memory: bool = True):
        """Initialize LADA components. Status mode can skip heavy subsystems."""
        
        print("=" * 70)
        print(f"🤖 LADA v{self.VERSION} - Initializing...")
        print("=" * 70)
        
        # Initialize components
        self.voice = None
        self.ai_router = None
        self.memory = None

        if init_voice:
            logger.info("Initializing Voice System...")
            from voice_tamil_free import FreeNaturalVoice
            self.voice = FreeNaturalVoice(
                tamil_mode=os.getenv('TAMIL_MODE', 'true').lower() == 'true',
                auto_detect=os.getenv('AUTO_DETECT_LANGUAGE', 'true').lower() == 'true'
            )

        if init_ai:
            logger.info("Initializing AI Router...")
            from lada_ai_router import HybridAIRouter
            self.ai_router = HybridAIRouter()

        if init_memory:
            logger.info("Initializing Memory System...")
            from lada_memory import MemorySystem
            self.memory = MemorySystem()
        
        # Running state
        self.running = False
        
        print("\n✅ LADA v7.0 Ready!")
        voice_state = "Tamil + English" if self.voice else "Skipped"
        ai_state = "Multi-backend (Ollama/Gemini)" if self.ai_router else "Skipped"
        memory_state = "Enabled" if self.memory else "Skipped"
        print(f"   🎤 Voice: {voice_state}")
        print(f"   🧠 AI: {ai_state}")
        print(f"   💾 Memory: {memory_state}")
        print("=" * 70)
        
        logger.info("LADA initialization complete")

    def _ensure_voice_initialized(self):
        """Initialize voice lazily for modes that require it."""
        if self.voice is None:
            from voice_tamil_free import FreeNaturalVoice
            self.voice = FreeNaturalVoice(
                tamil_mode=os.getenv('TAMIL_MODE', 'true').lower() == 'true',
                auto_detect=os.getenv('AUTO_DETECT_LANGUAGE', 'true').lower() == 'true'
            )
    
    def run_voice_mode(self):
        """
        Run LADA in voice mode - speak and listen
        Responds in the same language as the user
        """
        
        print("\n" + "=" * 70)
        print("🎤 LADA v7.0 - Voice Mode (Tamil + English)")
        print("=" * 70)
        print("🗣️  Speak in Tamil or English - I'll respond in the same language!")
        print("💬  Say 'exit', 'quit', 'bye', or 'வெளியேறு' to stop")
        print("=" * 70 + "\n")
        
        self._ensure_voice_initialized()

        # Welcome message (mixed language)
        self.voice.speak(
            "வணக்கம்! Hello! I am LADA, your personal assistant. "
            "You can speak to me in Tamil or English!",
            language='en'
        )
        
        self.running = True
        
        while self.running:
            try:
                # Listen for command
                command = self.voice.listen_mixed()
                
                if not command:
                    continue
                
                # Check for exit commands
                exit_words = ['exit', 'quit', 'bye', 'goodbye', 'stop', 'வெளியேறு', 'நிறுத்து', 'போறேன்']
                if any(word in command.lower() for word in exit_words):
                    # Detect language and respond accordingly
                    if self.voice.get_current_language() == 'ta':
                        self.voice.speak("சரி! பிறகு சந்திப்போம். நன்றி!", language='ta')
                    else:
                        self.voice.speak("Goodbye! See you next time!", language='en')
                    break
                
                # Get AI response
                logger.info(f"Processing: {command}")
                response = self.ai_router.query(command)
                
                # Speak response in the same language as the user
                current_lang = self.voice.get_current_language()
                self.voice.speak(response, language=current_lang)
                
                # Save to memory
                self.memory.remember('user', command, current_lang)
                self.memory.remember('assistant', response, current_lang)
                
            except KeyboardInterrupt:
                print("\n\n⏹️ Interrupted by user")
                self.voice.speak("Shutting down. Goodbye!", language='en')
                break
            except Exception as e:
                logger.error(f"Voice mode error: {e}")
                self.voice.speak("Sorry, I encountered an error. Please try again.", language='en')
        
        # Cleanup
        self._shutdown()
    
    def run_text_mode(self):
        """
        Run LADA in text mode - type commands
        """
        
        self._ensure_voice_initialized()

        print("\n" + "=" * 70)
        print("📝 LADA v7.0 - Text Mode")
        print("=" * 70)
        print("💬  Type in Tamil or English")
        print("📤  Type 'exit' or 'quit' to stop")
        print("📊  Type 'status' to see AI backend status")
        print("=" * 70 + "\n")
        
        print("வணக்கம்! Hello! I am LADA. Type your question below.\n")
        
        self.running = True
        
        while self.running:
            try:
                # Get input
                command = input("\n📝 You: ").strip()
                
                if not command:
                    continue
                
                # Check for exit
                if command.lower() in ['exit', 'quit', 'bye']:
                    print("\n👋 Goodbye! See you next time!")
                    break
                
                # Check for status command
                if command.lower() == 'status':
                    self._show_status()
                    continue
                
                # Detect language
                lang = self.voice.detect_language(command)
                lang_emoji = "🇮🇳" if lang == 'ta' else "🇬🇧"
                
                # Get AI response
                print(f"\n{lang_emoji} Processing...")
                response = self.ai_router.query(command)
                
                print(f"\n🤖 LADA: {response}")
                
                # Save to memory
                self.memory.remember('user', command, lang)
                self.memory.remember('assistant', response, lang)
                
            except KeyboardInterrupt:
                print("\n\n⏹️ Interrupted by user")
                break
            except Exception as e:
                logger.error(f"Text mode error: {e}")
                print(f"\n❌ Error: {e}")
        
        # Cleanup
        self._shutdown()
    
    def run_gui_mode(self):
        """
        Run LADA with Desktop GUI
        """
        try:
            # Try to import and run the desktop app
            from lada_desktop_app import main as run_gui
            run_gui()
        except ImportError as e:
            print(f"\n❌ GUI mode requires lada_desktop_app.py")
            print(f"   Error: {e}")
            print(f"\n💡 Falling back to text mode...\n")
            self.run_text_mode()
    
    def _show_status(self):
        """Show status of all components"""
        
        print("\n" + "=" * 50)
        print("📊 LADA System Status")
        print("=" * 50)
        
        # AI Backend Status
        print("\n🧠 AI Backends:")
        if self.ai_router:
            status = self.ai_router.get_status()
            for backend, info in status.items():
                emoji = "✅" if info["available"] else "❌"
                time_str = f" ({info['response_time']})" if info.get('response_time') != 'N/A' else ""
                error_str = f" - {info['error']}" if info.get('error') else ""
                print(f"   {emoji} {info['name']}{time_str}{error_str}")
        else:
            print("   ⚠️ AI router not initialized")
        
        # Memory Status
        print("\n💾 Memory:")
        if self.memory:
            mem_stats = self.memory.get_statistics()
            print(f"   📝 Total messages: {mem_stats['total_messages']}")
            print(f"   💬 Current conversation: {mem_stats['current_conversation_length']} messages")
            print(f"   🌐 Preferred language: {mem_stats['preferred_language']}")
        else:
            print("   ⚠️ Memory system not initialized")
        
        # Voice Status
        print("\n🎤 Voice:")
        if self.voice:
            print(f"   🗣️ Tamil mode: {self.voice.tamil_mode}")
            print(f"   🔄 Auto-detect: {self.voice.auto_detect}")
            print(f"   🔊 Current language: {self.voice.get_current_language()}")
        else:
            print("   ⏭️ Voice not initialized (status-only mode)")
        
        print("\n" + "=" * 50)
    
    def _shutdown(self):
        """Clean shutdown"""
        logger.info("Shutting down LADA...")
        
        # Save memory
        if self.memory:
            self.memory.shutdown()
        
        # Clean up voice
        if self.voice:
            self.voice.cleanup()
        
        self.running = False
        logger.info("LADA shutdown complete")


def run_doctor_command(args):
    """Run doctor diagnostics command."""
    from modules.doctor import DiagnosticsRunner, get_health_registry, AutoFixEngine
    
    subcommand = args[0] if args else "run"
    
    if subcommand == "run":
        # Run all diagnostics
        print("\n🩺 LADA Doctor - Running Diagnostics...\n")
        runner = DiagnosticsRunner()
        report = runner.run_all()
        
        # Print results
        is_healthy = report.failed == 0
        print(f"{'='*60}")
        print(f"📊 Diagnostics Report")
        print(f"{'='*60}")
        print(f"Status: {'✅ HEALTHY' if is_healthy else '❌ UNHEALTHY'}")
        print(f"Checks: {report.passed}/{report.total_checks} passed")
        print(f"Duration: {report.duration_ms:.0f}ms")
        
        failed_results = [r for r in report.results if not r.passed]
        warning_results = [r for r in report.results if r.severity.value == 'warning']
        
        if failed_results:
            print(f"\n❌ Failed Checks:")
            for check in failed_results:
                print(f"   • {check.name}: {check.message}")
                if check.details:
                    print(f"     Details: {check.details}")
        
        if warning_results:
            print(f"\n⚠️ Warnings:")
            for check in warning_results:
                print(f"   • {check.name}: {check.message}")
        
        print(f"\n{'='*60}")
        return 0 if is_healthy else 1
    
    elif subcommand == "list":
        # List available checks
        print("\n🩺 LADA Doctor - Available Diagnostics\n")
        runner = DiagnosticsRunner()
        checks = runner.list_diagnostics()
        
        for check in checks:
            print(f"   • {check.name}: {check.description}")
        
        print(f"\nTotal: {len(checks)} checks available")
        return 0
    
    elif subcommand == "health":
        # Show health status
        print("\n🩺 LADA Doctor - Health Status\n")
        registry = get_health_registry()
        status = registry.get_status()
        
        print(f"Overall: {'✅ HEALTHY' if status['healthy'] else '❌ UNHEALTHY'}")
        print(f"\nComponents:")
        for name, check in status['checks'].items():
            emoji = "✅" if check['healthy'] else "❌"
            print(f"   {emoji} {name}: {check.get('message', 'OK')}")
        
        return 0 if status['healthy'] else 1
    
    elif subcommand == "fix":
        # Run auto-fix
        fix_id = args[1] if len(args) > 1 else None
        
        if not fix_id:
            print("\n🔧 LADA Doctor - Available Fixes\n")
            engine = AutoFixEngine()
            fixes = engine.list_fixes()
            
            for fix in fixes:
                print(f"   • {fix.id}: {fix.description}")
                print(f"     Risk: {fix.risk.value}, Requires approval: {fix.requires_approval}")
            
            print(f"\nUsage: python main.py doctor fix <fix_id>")
            return 0
        
        print(f"\n🔧 Running fix: {fix_id}...")
        engine = AutoFixEngine()
        result = engine.execute(fix_id)
        
        if result.success:
            print(f"✅ Fix applied successfully!")
            if result.changes:
                print(f"   Changes: {result.changes}")
        else:
            print(f"❌ Fix failed: {result.error}")
        
        return 0 if result.success else 1
    
    else:
        print(f"❌ Unknown doctor subcommand: {subcommand}")
        print("Available: run, list, health, fix")
        return 1


def run_security_scan_command(args):
    """Run security scan command for plugins."""
    from modules.plugins import PluginScanner, get_trust_registry
    
    plugin_id = args[0] if args else None
    
    if not plugin_id:
        # List all plugins and their scan status
        print("\n🔒 LADA Security Scanner\n")
        registry = get_trust_registry()
        entries = registry.list_all()
        
        if not entries:
            print("No plugins registered. Use: python main.py scan <plugin_id>")
            return 0
        
        print(f"{'Plugin':<30} {'Trust Level':<15} {'Scanned':<10} {'Risk':<10}")
        print("-" * 65)
        for entry in entries:
            scanned = "✅" if entry.scan_passed else "❌" if entry.last_scanned else "⏳"
            print(f"{entry.plugin_id:<30} {entry.trust_level.value:<15} {scanned:<10} {entry.risk_level.value:<10}")
        
        print(f"\nTo scan a plugin: python main.py scan <plugin_id>")
        return 0
    
    # Scan specific plugin
    print(f"\n🔒 Scanning plugin: {plugin_id}...\n")
    
    scanner = PluginScanner()
    result = scanner.scan(plugin_id)
    
    print(f"{'='*60}")
    print(f"📊 Scan Report: {plugin_id}")
    print(f"{'='*60}")
    print(f"Status: {'✅ PASSED' if result.passed else '❌ FAILED'}")
    print(f"Risk Level: {result.risk_level.value.upper()}")
    print(f"Files Scanned: {result.files_scanned}")
    print(f"Lines Scanned: {result.lines_scanned}")
    print(f"Duration: {result.scan_duration_ms}ms")
    
    if result.findings:
        print(f"\n🔍 Findings ({len(result.findings)}):")
        
        # Group by severity
        by_severity = {}
        for finding in result.findings:
            sev = finding.severity.value
            if sev not in by_severity:
                by_severity[sev] = []
            by_severity[sev].append(finding)
        
        severity_order = ['critical', 'error', 'warning', 'info']
        emoji_map = {'critical': '🔴', 'error': '🟠', 'warning': '🟡', 'info': '🔵'}
        
        for sev in severity_order:
            if sev in by_severity:
                print(f"\n{emoji_map[sev]} {sev.upper()} ({len(by_severity[sev])}):")
                for finding in by_severity[sev]:
                    loc = f"{finding.file_path}:{finding.line_number}" if finding.file_path else ""
                    print(f"   • {finding.message}")
                    if loc:
                        print(f"     Location: {loc}")
                    if finding.code_snippet:
                        print(f"     Code: {finding.code_snippet[:60]}...")
    else:
        print("\n✅ No security issues found!")
    
    print(f"\n{'='*60}")
    
    # Update trust registry
    registry = get_trust_registry()
    registry.mark_scanned(plugin_id, result.passed, [f.message for f in result.findings])
    
    return 0 if result.passed else 1


def print_help():
    """Print usage help"""
    print("""
LADA v7.0 - Language Agnostic Digital Assistant
================================================

Usage:
    python main.py [mode]

Modes:
    voice   - Voice mode (speak and listen) [default]
    text    - Text mode (type commands)
    gui     - Desktop GUI mode
    webui   - Web UI mode (browser-based chat)
    daemon  - Headless gateway daemon mode (API + WS, no browser)
    verify  - Verify all module connections and configuration
    status  - Show system status and exit
    doctor  - Run system diagnostics
    scan    - Security scan plugins

Doctor Commands:
    python main.py doctor           # Run all diagnostics
    python main.py doctor run       # Run all diagnostics
    python main.py doctor list      # List available checks
    python main.py doctor health    # Show health status
    python main.py doctor fix       # List available fixes
    python main.py doctor fix <id>  # Apply a specific fix

Security Scanner:
    python main.py scan             # List plugins and scan status
    python main.py scan <plugin>    # Scan a specific plugin

Examples:
    python main.py          # Start in voice mode
    python main.py voice    # Start in voice mode
    python main.py text     # Start in text mode
    python main.py gui      # Start desktop app
    python main.py webui    # Start web UI in browser
    python main.py daemon   # Start headless gateway daemon on port 18790
    python main.py verify   # Test all module connections
    python main.py doctor   # Run system diagnostics
    python main.py scan my-plugin  # Scan a plugin

Features:
    🎤 Tamil + English voice support
    🧠 Multiple AI backends (Ollama, Gemini, Colab)
    💾 Long-term memory
    🔄 Auto language detection
    🩺 System diagnostics and auto-fix
    🔒 Plugin security scanning
    """)


def main():
    """Main entry point"""
    
    # Parse command line arguments
    mode = 'voice'  # Default mode
    
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        
        if arg in ['help', '-h', '--help']:
            print_help()
            return
        
        if arg == 'status':
            # Quick status check
            lada = LADA(init_voice=False, init_ai=True, init_memory=True)
            lada._show_status()
            return

        if arg == 'doctor':
            # Doctor diagnostics
            try:
                exit_code = run_doctor_command(sys.argv[2:])
                sys.exit(exit_code)
            except Exception as e:
                logger.error(f"Doctor error: {e}")
                print(f"\n❌ Doctor error: {e}")
                sys.exit(1)

        if arg == 'scan':
            # Security scanner
            try:
                exit_code = run_security_scan_command(sys.argv[2:])
                sys.exit(exit_code)
            except Exception as e:
                logger.error(f"Scan error: {e}")
                print(f"\n❌ Scan error: {e}")
                sys.exit(1)

        if arg == 'gui':
            # GUI mode should start fast without initializing the full CLI stack.
            # (We still keep dotenv loading at module import time.)
            try:
                from lada_desktop_app import main as run_gui
                run_gui()
                return
            except Exception as e:
                logger.error(f"GUI launch error: {e}")
                print(f"\n❌ GUI launch error: {e}")
                print(f"\n💡 Falling back to text mode...\n")
                lada = LADA()
                lada.run_text_mode()
                return

        if arg == 'webui':
            try:
                from lada_webui import main as run_webui
                run_webui()
                return
            except Exception as e:
                logger.error(f"WebUI launch error: {e}")
                print(f"\n❌ WebUI launch error: {e}")
                print(f"\n💡 Check the error details above and try again.")
                return

        if arg == 'daemon':
            try:
                from modules.gateway_daemon import run_gateway_daemon
                run_gateway_daemon()
                return
            except Exception as e:
                logger.error(f"Gateway daemon launch error: {e}")
                print(f"\n❌ Gateway daemon launch error: {e}")
                print("\n💡 Ensure fastapi/uvicorn dependencies are installed.")
                return

        if arg == 'verify':
            try:
                from modules.connection_verifier import verify_all
                verify_all()
            except Exception as e:
                print(f"\n❌ Verifier error: {e}")
            return

        if arg in ['voice', 'text', 'gui', 'daemon']:
            mode = arg
        else:
            print(f"❌ Unknown mode: {arg}")
            print_help()
            return
    
    # Create and run LADA
    try:
        if mode == 'gui':
            # Start GUI directly (fast path).
            from lada_desktop_app import main as run_gui
            run_gui()
            return

        lada = LADA()

        if mode == 'voice':
            lada.run_voice_mode()
        elif mode == 'text':
            lada.run_text_mode()
            
    except Exception as e:
        logger.error(f"LADA error: {e}")
        print(f"\n❌ Error: {e}")
        raise


if __name__ == "__main__":
    main()
