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
    verify  - Verify all module connections and configuration
    status  - Show system status and exit

Examples:
    python main.py          # Start in voice mode
    python main.py voice    # Start in voice mode
    python main.py text     # Start in text mode
    python main.py gui      # Start desktop app
    python main.py webui    # Start web UI in browser
    python main.py verify   # Test all module connections

Features:
    🎤 Tamil + English voice support
    🧠 Multiple AI backends (Ollama, Gemini, Colab)
    💾 Long-term memory
    🔄 Auto language detection
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

        if arg == 'verify':
            try:
                from modules.connection_verifier import verify_all
                verify_all()
            except Exception as e:
                print(f"\n❌ Verifier error: {e}")
            return

        if arg in ['voice', 'text', 'gui']:
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
