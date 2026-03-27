"""Alexa Skill Server for LADA

Flask endpoint that receives commands from Alexa and forwards to local LADA API.

Features:
- Alexa Skills Kit SDK integration
- Invocation name: "lada"
- LADACommandIntent with {command} slot
- HTTP POST to local LADA API
- Returns voice response back to Alexa
- ngrok tunnel management for HTTPS

Environment variables:
- ALEXA_SKILL_ID: Alexa skill ID for validation
- LADA_ALEXA_PORT: Port for Flask server (default: 5001)
- LADA_API_URL: Local LADA API URL (default: http://localhost:5000)
- NGROK_AUTH_TOKEN: ngrok auth token for tunnel

Usage:
    python -m integrations.alexa_server
    
Or programmatically:
    from integrations.alexa_server import AlexaSkillServer
    server = AlexaSkillServer()
    server.start()
"""

from __future__ import annotations

import os
import json
import time
import logging
import threading
import requests
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Flask and Alexa SDK (optional)
try:
    from flask import Flask, request, jsonify
    FLASK_AVAILABLE = True
except ImportError:
    Flask = None
    FLASK_AVAILABLE = False

try:
    from ask_sdk_core.skill_builder import SkillBuilder
    from ask_sdk_core.dispatch_components import AbstractRequestHandler
    from ask_sdk_core.utils import is_intent_name, is_request_type
    from ask_sdk_model import Response
    from ask_sdk_model.ui import SimpleCard
    ASK_SDK_AVAILABLE = True
except ImportError:
    ASK_SDK_AVAILABLE = False

try:
    import ngrok
    NGROK_AVAILABLE = True
except ImportError:
    ngrok = None
    NGROK_AVAILABLE = False


@dataclass
class AlexaConfig:
    """Alexa server configuration."""
    skill_id: str = ""
    port: int = 5001
    lada_api_url: str = "http://localhost:5000"
    ngrok_auth_token: str = ""
    auto_start_ngrok: bool = True
    
    @classmethod
    def from_env(cls) -> "AlexaConfig":
        """Load config from environment variables."""
        return cls(
            skill_id=os.getenv("ALEXA_SKILL_ID", ""),
            port=int(os.getenv("LADA_ALEXA_PORT", "5001")),
            lada_api_url=os.getenv("LADA_API_URL", "http://localhost:5000"),
            ngrok_auth_token=os.getenv("NGROK_AUTH_TOKEN", ""),
            auto_start_ngrok=os.getenv("LADA_ALEXA_NGROK", "true").lower() == "true",
        )


class AlexaSkillServer:
    """Flask server for Alexa skill webhook.
    
    Receives requests from Alexa, forwards commands to LADA API,
    and returns responses back to Alexa for speech output.
    """
    
    def __init__(self, config: Optional[AlexaConfig] = None):
        """Initialize Alexa skill server.
        
        Args:
            config: Server configuration (default: from environment)
        """
        if not FLASK_AVAILABLE:
            raise ImportError("Flask required: pip install flask")
        
        self.config = config or AlexaConfig.from_env()
        self._app: Optional[Flask] = None
        self._thread: Optional[threading.Thread] = None
        self._ngrok_url: Optional[str] = None
        self._running = False
        
        self._setup_flask()
        logger.info(f"[AlexaServer] Initialized on port {self.config.port}")
    
    def _setup_flask(self):
        """Set up Flask application with routes."""
        self._app = Flask(__name__)
        
        # Disable Flask's default logging
        import logging as flask_logging
        flask_logging.getLogger('werkzeug').setLevel(flask_logging.WARNING)
        
        # Register routes
        self._app.add_url_rule(
            '/alexa',
            'alexa_webhook',
            self._handle_alexa_request,
            methods=['POST']
        )
        
        self._app.add_url_rule(
            '/health',
            'health_check',
            self._health_check,
            methods=['GET']
        )
        
        # If ASK SDK available, set up proper skill handlers
        if ASK_SDK_AVAILABLE:
            self._setup_ask_sdk()
    
    def _setup_ask_sdk(self):
        """Set up Alexa Skills Kit SDK handlers."""
        sb = SkillBuilder()
        
        # Launch request handler
        class LaunchRequestHandler(AbstractRequestHandler):
            def can_handle(self, handler_input):
                return is_request_type("LaunchRequest")(handler_input)
            
            def handle(self, handler_input):
                speech = "LADA is ready. What would you like me to do?"
                return handler_input.response_builder.speak(speech).set_should_end_session(False).response
        
        # LADA Command intent handler
        class LADACommandHandler(AbstractRequestHandler):
            def __init__(self, server: AlexaSkillServer):
                self.server = server
            
            def can_handle(self, handler_input):
                return is_intent_name("LADACommandIntent")(handler_input)
            
            def handle(self, handler_input):
                slots = handler_input.request_envelope.request.intent.slots
                command = slots.get("command", {}).value if slots else None
                
                if command:
                    response_text = self.server._forward_to_lada(command)
                else:
                    response_text = "I didn't catch that. Could you repeat?"
                
                return (
                    handler_input.response_builder
                    .speak(response_text)
                    .set_should_end_session(False)
                    .response
                )
        
        # Help intent
        class HelpIntentHandler(AbstractRequestHandler):
            def can_handle(self, handler_input):
                return is_intent_name("AMAZON.HelpIntent")(handler_input)
            
            def handle(self, handler_input):
                speech = "You can ask LADA to control your computer. Try saying: LADA, open Chrome."
                return handler_input.response_builder.speak(speech).set_should_end_session(False).response
        
        # Stop/Cancel intent
        class StopIntentHandler(AbstractRequestHandler):
            def can_handle(self, handler_input):
                return (
                    is_intent_name("AMAZON.StopIntent")(handler_input) or
                    is_intent_name("AMAZON.CancelIntent")(handler_input)
                )
            
            def handle(self, handler_input):
                speech = "Goodbye!"
                return handler_input.response_builder.speak(speech).set_should_end_session(True).response
        
        # Session ended
        class SessionEndedHandler(AbstractRequestHandler):
            def can_handle(self, handler_input):
                return is_request_type("SessionEndedRequest")(handler_input)
            
            def handle(self, handler_input):
                return handler_input.response_builder.response
        
        # Register handlers
        sb.add_request_handler(LaunchRequestHandler())
        sb.add_request_handler(LADACommandHandler(self))
        sb.add_request_handler(HelpIntentHandler())
        sb.add_request_handler(StopIntentHandler())
        sb.add_request_handler(SessionEndedHandler())
        
        self._skill = sb.create()
    
    def _handle_alexa_request(self):
        """Handle incoming Alexa webhook request."""
        try:
            body = request.get_json(force=True)
            logger.debug(f"[AlexaServer] Request: {json.dumps(body)[:200]}...")
            
            # Validate skill ID if configured
            if self.config.skill_id:
                req_skill_id = body.get("session", {}).get("application", {}).get("applicationId", "")
                if req_skill_id != self.config.skill_id:
                    logger.warning(f"[AlexaServer] Invalid skill ID: {req_skill_id}")
                    return jsonify({"error": "Invalid skill ID"}), 403
            
            # If ASK SDK available, use it
            if ASK_SDK_AVAILABLE:
                from ask_sdk_core.serialize import DefaultSerializer
                from ask_sdk_model import RequestEnvelope
                
                serializer = DefaultSerializer()
                request_envelope = serializer.deserialize(json.dumps(body), RequestEnvelope)
                response_envelope = self._skill.invoke(request_envelope, None)
                return jsonify(serializer.serialize(response_envelope))
            
            # Simple fallback handler
            return self._simple_handler(body)
            
        except Exception as e:
            logger.error(f"[AlexaServer] Request error: {e}")
            return jsonify(self._build_response("Sorry, something went wrong.")), 500
    
    def _simple_handler(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Simple request handler without ASK SDK."""
        request_type = body.get("request", {}).get("type", "")
        
        if request_type == "LaunchRequest":
            return jsonify(self._build_response(
                "LADA is ready. What would you like me to do?",
                end_session=False
            ))
        
        elif request_type == "IntentRequest":
            intent_name = body.get("request", {}).get("intent", {}).get("name", "")
            
            if intent_name == "LADACommandIntent":
                slots = body.get("request", {}).get("intent", {}).get("slots", {})
                command = slots.get("command", {}).get("value", "")
                
                if command:
                    response_text = self._forward_to_lada(command)
                else:
                    response_text = "I didn't catch that. Could you repeat?"
                
                return jsonify(self._build_response(response_text, end_session=False))
            
            elif intent_name in ("AMAZON.HelpIntent",):
                return jsonify(self._build_response(
                    "You can ask LADA to control your computer.",
                    end_session=False
                ))
            
            elif intent_name in ("AMAZON.StopIntent", "AMAZON.CancelIntent"):
                return jsonify(self._build_response("Goodbye!", end_session=True))
        
        elif request_type == "SessionEndedRequest":
            return jsonify(self._build_response("", end_session=True))
        
        return jsonify(self._build_response("I'm not sure how to help with that."))
    
    def _build_response(
        self,
        speech: str,
        end_session: bool = False,
        card_title: str = "LADA",
        card_content: str = ""
    ) -> Dict[str, Any]:
        """Build Alexa response envelope."""
        response = {
            "version": "1.0",
            "response": {
                "outputSpeech": {
                    "type": "PlainText",
                    "text": speech
                },
                "shouldEndSession": end_session
            }
        }
        
        if card_content or speech:
            response["response"]["card"] = {
                "type": "Simple",
                "title": card_title,
                "content": card_content or speech
            }
        
        return response
    
    def _forward_to_lada(self, command: str) -> str:
        """Forward command to local LADA API.
        
        Args:
            command: Voice command text
            
        Returns:
            Response text from LADA
        """
        try:
            url = f"{self.config.lada_api_url}/chat"
            payload = {
                "message": command,
                "source": "alexa",
                "session_id": "alexa_session"
            }
            
            logger.info(f"[AlexaServer] Forwarding: {command}")
            
            response = requests.post(
                url,
                json=payload,
                timeout=30
            )
            
            if response.ok:
                data = response.json()
                return data.get("response", "Command executed.")
            else:
                logger.error(f"[AlexaServer] LADA API error: {response.status_code}")
                return "Sorry, I couldn't complete that request."
                
        except requests.exceptions.ConnectionError:
            logger.error("[AlexaServer] Cannot connect to LADA API")
            return "LADA is not responding. Please check if it's running."
        except requests.exceptions.Timeout:
            logger.error("[AlexaServer] LADA API timeout")
            return "The request is taking too long. Please try again."
        except Exception as e:
            logger.error(f"[AlexaServer] Forward error: {e}")
            return "Sorry, something went wrong."
    
    def _health_check(self):
        """Health check endpoint."""
        return jsonify({
            "status": "ok",
            "service": "lada-alexa",
            "ngrok_url": self._ngrok_url,
            "ask_sdk": ASK_SDK_AVAILABLE,
        })
    
    def _start_ngrok(self) -> Optional[str]:
        """Start ngrok tunnel for HTTPS."""
        if not NGROK_AVAILABLE:
            logger.warning("[AlexaServer] ngrok not available: pip install ngrok")
            return None
        
        if not self.config.ngrok_auth_token:
            logger.warning("[AlexaServer] NGROK_AUTH_TOKEN not set")
            return None
        
        try:
            ngrok.set_auth_token(self.config.ngrok_auth_token)
            listener = ngrok.forward(self.config.port, "http")
            self._ngrok_url = listener.url()
            logger.info(f"[AlexaServer] ngrok tunnel: {self._ngrok_url}")
            return self._ngrok_url
        except Exception as e:
            logger.error(f"[AlexaServer] ngrok error: {e}")
            return None
    
    def start(self, blocking: bool = False):
        """Start the Alexa skill server.
        
        Args:
            blocking: If True, run in main thread (blocks). If False, run in background.
        """
        if self._running:
            logger.warning("[AlexaServer] Already running")
            return
        
        self._running = True
        
        # Start ngrok if configured
        if self.config.auto_start_ngrok:
            self._start_ngrok()
        
        if blocking:
            self._run_server()
        else:
            self._thread = threading.Thread(target=self._run_server, daemon=True)
            self._thread.start()
            logger.info(f"[AlexaServer] Started on port {self.config.port}")
    
    def _run_server(self):
        """Run Flask server."""
        try:
            self._app.run(
                host="0.0.0.0",
                port=self.config.port,
                debug=False,
                use_reloader=False
            )
        except Exception as e:
            logger.error(f"[AlexaServer] Server error: {e}")
        finally:
            self._running = False
    
    def stop(self):
        """Stop the server."""
        self._running = False
        logger.info("[AlexaServer] Stopped")
    
    @property
    def ngrok_url(self) -> Optional[str]:
        """Get the ngrok HTTPS URL for Alexa skill configuration."""
        return self._ngrok_url
    
    def get_skill_manifest_snippet(self) -> Dict[str, Any]:
        """Get Alexa skill manifest snippet for configuration."""
        return {
            "manifest": {
                "apis": {
                    "custom": {
                        "endpoint": {
                            "uri": f"{self._ngrok_url}/alexa" if self._ngrok_url else "YOUR_HTTPS_URL/alexa"
                        }
                    }
                }
            },
            "interactionModel": {
                "languageModel": {
                    "invocationName": "lada",
                    "intents": [
                        {
                            "name": "LADACommandIntent",
                            "slots": [
                                {
                                    "name": "command",
                                    "type": "AMAZON.SearchQuery"
                                }
                            ],
                            "samples": [
                                "{command}",
                                "please {command}",
                                "can you {command}",
                                "do {command}",
                                "i want you to {command}",
                                "i need you to {command}",
                                "help me {command}",
                                "would you {command}"
                            ]
                        },
                        {"name": "AMAZON.HelpIntent", "samples": []},
                        {"name": "AMAZON.StopIntent", "samples": []},
                        {"name": "AMAZON.CancelIntent", "samples": []}
                    ]
                }
            }
        }


def main():
    """Run Alexa skill server standalone."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    
    server = AlexaSkillServer()
    
    print("\n" + "="*60)
    print("LADA Alexa Skill Server")
    print("="*60)
    print(f"Local URL: http://localhost:{server.config.port}/alexa")
    
    if server._ngrok_url:
        print(f"Public URL: {server._ngrok_url}/alexa")
        print("\nConfigure this URL in your Alexa Developer Console:")
        print(f"  Endpoint: {server._ngrok_url}/alexa")
    else:
        print("\nNo ngrok tunnel. Set NGROK_AUTH_TOKEN for public URL.")
    
    print("="*60 + "\n")
    
    try:
        server.start(blocking=True)
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.stop()


if __name__ == "__main__":
    main()
