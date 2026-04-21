"""
LADA v7.0 - Chat Manager
ChatGPT/Perplexity-style conversation management with streaming support
"""

import json
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Generator, Any, Callable
from pathlib import Path

# Import markdown renderer
try:
    from .markdown_renderer import MarkdownRenderer
    RENDERER_OK = True
except ImportError:
    try:
        from markdown_renderer import MarkdownRenderer
        RENDERER_OK = True
    except ImportError:
        RENDERER_OK = False
        print("[ChatManager] MarkdownRenderer not available")


class Message:
    """
    Enhanced message object with ChatGPT-style metadata.
    """
    def __init__(
        self,
        role: str,
        content: str,
        message_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        model_used: Optional[str] = None,
        sources: Optional[List[Dict]] = None,
        reactions: Optional[Dict] = None,
        is_streaming: bool = False,
        tokens_used: int = 0,
        thinking_time: float = 0.0
    ):
        self.id = message_id or str(uuid.uuid4())[:8]
        self.role = role  # 'user', 'assistant', 'system'
        self.content = content
        self.timestamp = timestamp or datetime.now()
        self.model_used = model_used
        self.sources = sources or []  # Web search citations
        self.reactions = reactions or {}  # {'thumbs_up': False, 'thumbs_down': False}
        self.is_streaming = is_streaming
        self.tokens_used = tokens_used
        self.thinking_time = thinking_time
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for storage."""
        return {
            'id': self.id,
            'role': self.role,
            'content': self.content,
            'timestamp': self.timestamp.isoformat(),
            'model_used': self.model_used,
            'sources': self.sources,
            'reactions': self.reactions,
            'tokens_used': self.tokens_used,
            'thinking_time': self.thinking_time
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Message':
        """Create from dictionary."""
        return cls(
            role=data['role'],
            content=data['content'],
            message_id=data.get('id'),
            timestamp=datetime.fromisoformat(data['timestamp']) if data.get('timestamp') else None,
            model_used=data.get('model_used'),
            sources=data.get('sources', []),
            reactions=data.get('reactions', {}),
            tokens_used=data.get('tokens_used', 0),
            thinking_time=data.get('thinking_time', 0.0)
        )


class Conversation:
    """
    A chat conversation with multiple messages.
    """
    def __init__(
        self,
        conversation_id: Optional[str] = None,
        title: Optional[str] = None,
        created_at: Optional[datetime] = None
    ):
        self.id = conversation_id or str(uuid.uuid4())[:8]
        self.title = title or "New Chat"
        self.created_at = created_at or datetime.now()
        self.updated_at = self.created_at
        self.messages: List[Message] = []
        self.metadata: Dict = {}
    
    def add_message(self, message: Message):
        """Add a message to the conversation."""
        self.messages.append(message)
        self.updated_at = datetime.now()
        
        # Auto-title from first user message
        if not self.title or self.title == "New Chat":
            if message.role == 'user' and len(message.content) > 0:
                self.title = message.content[:50] + ("..." if len(message.content) > 50 else "")
    
    def get_context(self, max_messages: int = 20) -> List[Dict]:
        """Get conversation context for AI."""
        recent = self.messages[-max_messages:] if len(self.messages) > max_messages else self.messages
        return [{'role': m.role, 'content': m.content} for m in recent]
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for storage."""
        return {
            'id': self.id,
            'title': self.title,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'messages': [m.to_dict() for m in self.messages],
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Conversation':
        """Create from dictionary."""
        conv = cls(
            conversation_id=data.get('id'),
            title=data.get('title'),
            created_at=datetime.fromisoformat(data['created_at']) if data.get('created_at') else None
        )
        conv.updated_at = datetime.fromisoformat(data['updated_at']) if data.get('updated_at') else conv.created_at
        conv.messages = [Message.from_dict(m) for m in data.get('messages', [])]
        conv.metadata = data.get('metadata', {})
        return conv


class ChatManager:
    """
    Manage chat conversations with streaming support.
    Features:
    - Create/load/save conversations
    - Stream AI responses
    - Track tokens and timing
    - Handle web search citations
    """
    
    def __init__(
        self,
        data_dir: str = "data/conversations",
        ai_router=None
    ):
        """
        Initialize chat manager.
        
        Args:
            data_dir: Directory to store conversation files
            ai_router: HybridAIRouter instance for AI queries
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.ai_router = ai_router
        self.current_conversation: Optional[Conversation] = None
        self.conversations: Dict[str, Conversation] = {}
        
        # Markdown renderer
        self.renderer = MarkdownRenderer() if RENDERER_OK else None
        
        # Streaming state
        self.is_streaming = False
        self.stream_buffer = ""
        
        # Callbacks
        self.on_chunk_received: Optional[Callable[[str], None]] = None
        self.on_stream_complete: Optional[Callable[[Message], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
    
    def create_conversation(self, title: Optional[str] = None) -> Conversation:
        """Create a new conversation."""
        conv = Conversation(title=title)
        self.conversations[conv.id] = conv
        self.current_conversation = conv
        return conv
    
    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Get a conversation by ID."""
        if conversation_id in self.conversations:
            return self.conversations[conversation_id]
        
        # Try to load from file
        return self.load_conversation(conversation_id)

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        *,
        model_used: Optional[str] = None,
        sources: Optional[List[Dict]] = None,
    ) -> Conversation:
        """Append a message to a conversation, creating it when missing."""
        normalized_role = str(role or "").strip().lower()
        if normalized_role not in {"user", "assistant", "system"}:
            raise ValueError(f"Unsupported role: {role}")

        target_id = str(conversation_id or "").strip()
        if target_id:
            conversation = self.get_conversation(target_id)
            if conversation is None:
                conversation = Conversation(conversation_id=target_id)
                self.conversations[conversation.id] = conversation
        else:
            conversation = self.create_conversation()

        message = Message(
            role=normalized_role,
            content=str(content or ""),
            model_used=model_used,
            sources=sources or [],
        )
        conversation.add_message(message)
        self.current_conversation = conversation
        self.save_conversation(conversation)
        return conversation
    
    def load_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Load a conversation from file."""
        file_path = self.data_dir / f"{conversation_id}.json"
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                conv = Conversation.from_dict(data)
                self.conversations[conv.id] = conv
                return conv
            except Exception as e:
                print(f"[ChatManager] Error loading conversation: {e}")
        return None
    
    def save_conversation(self, conversation: Optional[Conversation] = None):
        """Save a conversation to file."""
        conv = conversation or self.current_conversation
        if not conv:
            return
        
        file_path = self.data_dir / f"{conv.id}.json"
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(conv.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[ChatManager] Error saving conversation: {e}")
    
    def list_conversations(self) -> List[Dict]:
        """List all saved conversations."""
        conversations = []
        
        for file_path in self.data_dir.glob("*.json"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                conversations.append({
                    'id': data.get('id'),
                    'title': data.get('title', 'Untitled'),
                    'updated_at': data.get('updated_at'),
                    'message_count': len(data.get('messages', []))
                })
            except Exception as e:
                continue
        
        # Sort by updated_at descending
        conversations.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
        return conversations
    
    def send_message(
        self,
        content: str,
        conversation: Optional[Conversation] = None,
        include_web_search: bool = False,
        stream: bool = True
    ) -> Message:
        """
        Send a message and get AI response.
        
        Args:
            content: User message content
            conversation: Conversation to add to (uses current if None)
            include_web_search: Whether to include web search results
            stream: Whether to stream the response
            
        Returns:
            Assistant's response message
        """
        conv = conversation or self.current_conversation
        if not conv:
            conv = self.create_conversation()
        
        # Add user message
        user_msg = Message(role='user', content=content)
        conv.add_message(user_msg)
        
        # Get AI response
        if stream and self.ai_router:
            response_msg = self._stream_response(conv, include_web_search)
        else:
            response_msg = self._get_response(conv, include_web_search)
        
        # Save conversation
        self.save_conversation(conv)
        
        return response_msg
    
    def _get_response(
        self,
        conversation: Conversation,
        include_web_search: bool = False
    ) -> Message:
        """Get non-streaming AI response."""
        import time
        start_time = time.time()
        
        sources = []
        enhanced_content = conversation.messages[-1].content if conversation.messages else ""
        
        # Web search if requested
        if include_web_search:
            try:
                from .web_search import WebSearcher
                searcher = WebSearcher()
                results = searcher.search(enhanced_content, max_results=3)
                
                if results:
                    sources = results
                    context = "\n\nWeb search results:\n"
                    for i, r in enumerate(results, 1):
                        context += f"[{i}] {r.get('title', '')}: {r.get('snippet', '')}\n"
                    enhanced_content += context
            except Exception as e:
                print(f"[ChatManager] Web search error: {e}")
        
        # Get AI response
        response_content = ""
        model_used = "unknown"
        
        if self.ai_router:
            try:
                # Build context
                context = conversation.get_context()
                response = self.ai_router.query(enhanced_content, context=context[:-1])
                response_content = response.get('response', 'I apologize, but I could not generate a response.')
                model_used = response.get('source', 'unknown')
            except Exception as e:
                response_content = f"Error: {str(e)}"
        else:
            response_content = "AI router not configured."
        
        thinking_time = time.time() - start_time
        
        # Create response message
        response_msg = Message(
            role='assistant',
            content=response_content,
            model_used=model_used,
            sources=sources,
            thinking_time=thinking_time
        )
        
        conversation.add_message(response_msg)
        return response_msg
    
    def _stream_response(
        self,
        conversation: Conversation,
        include_web_search: bool = False
    ) -> Message:
        """
        Stream AI response chunk by chunk.
        Calls on_chunk_received for each chunk.
        """
        import time
        start_time = time.time()
        
        self.is_streaming = True
        self.stream_buffer = ""
        sources = []
        
        enhanced_content = conversation.messages[-1].content if conversation.messages else ""
        
        # Web search if requested
        if include_web_search:
            try:
                from .web_search import WebSearcher
                searcher = WebSearcher()
                results = searcher.search(enhanced_content, max_results=3)
                
                if results:
                    sources = results
                    context = "\n\nWeb search results:\n"
                    for i, r in enumerate(results, 1):
                        context += f"[{i}] {r.get('title', '')}: {r.get('snippet', '')}\n"
                    enhanced_content += context
            except Exception as e:
                print(f"[ChatManager] Web search error: {e}")
        
        # Get streaming response
        model_used = "unknown"
        
        if self.ai_router and hasattr(self.ai_router, 'stream_query'):
            try:
                context = conversation.get_context()
                
                for chunk in self.ai_router.stream_query(enhanced_content, context=context[:-1]):
                    if not self.is_streaming:
                        break  # Allow cancellation
                    
                    self.stream_buffer += chunk
                    model_used = chunk.get('source', model_used) if isinstance(chunk, dict) else model_used
                    
                    if self.on_chunk_received:
                        text_chunk = chunk.get('chunk', chunk) if isinstance(chunk, dict) else chunk
                        self.on_chunk_received(text_chunk)
                        
            except Exception as e:
                self.stream_buffer = f"Error: {str(e)}"
        else:
            # Fallback to non-streaming
            response = self._get_response(conversation, include_web_search)
            self.stream_buffer = response.content
            model_used = response.model_used
        
        thinking_time = time.time() - start_time
        self.is_streaming = False
        
        # Create response message
        response_msg = Message(
            role='assistant',
            content=self.stream_buffer,
            model_used=model_used,
            sources=sources,
            thinking_time=thinking_time
        )
        
        # Don't double-add if fallback was used
        if conversation.messages[-1].role != 'assistant':
            conversation.add_message(response_msg)
        
        if self.on_stream_complete:
            self.on_stream_complete(response_msg)
        
        return response_msg
    
    def cancel_stream(self):
        """Cancel ongoing stream."""
        self.is_streaming = False
    
    def render_message(self, message: Message) -> str:
        """Render message content as HTML with markdown."""
        if self.renderer:
            html = self.renderer.render(message.content)
            
            # Add citations if available
            if message.sources:
                html += self.renderer.render_citations(message.sources)
            
            return html
        else:
            # Fallback: basic HTML
            import html as html_lib
            content = html_lib.escape(message.content)
            content = content.replace('\n', '<br>')
            return f'<p style="color: #ececec;">{content}</p>'
    
    def regenerate_response(
        self,
        conversation: Optional[Conversation] = None
    ) -> Optional[Message]:
        """Regenerate the last assistant response."""
        conv = conversation or self.current_conversation
        if not conv or len(conv.messages) < 2:
            return None
        
        # Remove last assistant message
        if conv.messages[-1].role == 'assistant':
            conv.messages.pop()
        
        # Get last user message
        if conv.messages and conv.messages[-1].role == 'user':
            last_user_content = conv.messages[-1].content
            conv.messages.pop()  # Remove it temporarily
            
            # Resend
            return self.send_message(last_user_content, conv)
        
        return None
    
    def add_reaction(
        self,
        message_id: str,
        reaction: str,
        value: bool = True,
        conversation: Optional[Conversation] = None
    ):
        """Add reaction to a message."""
        conv = conversation or self.current_conversation
        if not conv:
            return
        
        for msg in conv.messages:
            if msg.id == message_id:
                msg.reactions[reaction] = value
                self.save_conversation(conv)
                break
    
    def delete_conversation(self, conversation_id: str):
        """Delete a conversation."""
        # Remove from memory
        if conversation_id in self.conversations:
            del self.conversations[conversation_id]
        
        # Remove file
        file_path = self.data_dir / f"{conversation_id}.json"
        if file_path.exists():
            file_path.unlink()


# ============================================================
# EXAMPLE USAGE
# ============================================================
if __name__ == "__main__":
    print("🚀 Testing ChatManager...")
    
    # Create manager
    manager = ChatManager(data_dir="data/test_conversations")
    
    # Create conversation
    conv = manager.create_conversation("Test Chat")
    print(f"📝 Created conversation: {conv.id}")
    
    # Add messages manually (without AI)
    user_msg = Message(role='user', content='Hello, how are you?')
    conv.add_message(user_msg)
    
    assistant_msg = Message(
        role='assistant',
        content='Hello! I\'m doing great. Here\'s some **markdown**:\n\n```python\nprint("Hello!")\n```',
        model_used='test',
        sources=[{'title': 'Python Docs', 'url': 'https://python.org'}]
    )
    conv.add_message(assistant_msg)
    
    # Render
    html = manager.render_message(assistant_msg)
    print(f"📄 Rendered HTML length: {len(html)} chars")
    
    # Save
    manager.save_conversation(conv)
    print(f"💾 Saved conversation")
    
    # List
    conversations = manager.list_conversations()
    print(f"📚 Total conversations: {len(conversations)}")
    
    print("\n✅ ChatManager test complete!")
