from modules.desktop.common import *

class AIWorker(QThread):
    done = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, prompt, router, files=None, preferred_backend=None):
        super().__init__()
        self.prompt = prompt
        self.router = router
        self.files = files or []
        self.preferred_backend = preferred_backend  # Backend name from model selector

    def run(self):
        ctx = self.prompt
        for f in self.files:
            if f.get('type') == 'text':
                ctx = f"[File: {f['name']}]\n{f['content']}\n\n{ctx}"
            elif f.get('type') == 'image':
                ctx = f"[Attached image: {f['name']}]\n\n{ctx}"

        if not self.router:
            self.error.emit("AI not initialized")
            return

        # Try up to 2 times
        for attempt in range(2):
            try:
                r = self.router.query(ctx, model=self.preferred_backend)
                if r:
                    self.done.emit(r)
                    return
            except Exception as e:
                print(f"[LADA] Query attempt {attempt+1} failed: {e}")
                if attempt == 0:
                    import time
                    time.sleep(0.5)
        
        self.error.emit("Could not get response. Please try again.")



class StreamingAIWorker(QThread):
    """AI Worker with streaming support for ChatGPT-style typing effect."""
    chunk_received = pyqtSignal(str)  # Individual chunk
    done = pyqtSignal(str)  # Full response when complete
    error = pyqtSignal(str)
    source_detected = pyqtSignal(str)  # Backend source name
    web_sources = pyqtSignal(list)  # Web search sources for badges

    def __init__(self, prompt, router, files=None, preferred_backend=None):
        super().__init__()
        self.prompt = prompt
        self.router = router
        self.files = files or []
        self.preferred_backend = preferred_backend
        self._cancelled = False
        self.full_response = ""

    def cancel(self):
        """Cancel the streaming operation."""
        self._cancelled = True

    def run(self):
        ctx = self.prompt
        for f in self.files:
            if f.get('type') == 'text':
                ctx = f"[File: {f['name']}]\n{f['content']}\n\n{ctx}"
            elif f.get('type') == 'image':
                ctx = f"[Attached image: {f['name']}]\n\n{ctx}"

        if not self.router:
            self.error.emit("AI not initialized")
            return

        try:
            # Check if router supports streaming
            if hasattr(self.router, 'stream_query'):
                for data in self.router.stream_query(ctx, model=self.preferred_backend):
                    if self._cancelled:
                        break
                    
                    # Check for sources data
                    if isinstance(data, dict) and 'sources' in data:
                        sources = data.get('sources', [])
                        if sources:
                            self.web_sources.emit(sources)
                        continue
                    
                    chunk = data.get('chunk', '') if isinstance(data, dict) else data
                    source = data.get('source', '') if isinstance(data, dict) else ''
                    is_done = data.get('done', False) if isinstance(data, dict) else False
                    
                    if chunk:
                        self.full_response += chunk
                        self.chunk_received.emit(chunk)
                    
                    if source and not hasattr(self, '_source_sent'):
                        self._source_sent = True
                        self.source_detected.emit(source)
                    
                    if is_done:
                        break
                
                if not self._cancelled:
                    self.done.emit(self.full_response)
            else:
                # Fallback to non-streaming
                r = self.router.query(ctx, model=self.preferred_backend)
                if r and not self._cancelled:
                    self.full_response = r
                    self.chunk_received.emit(r)  # Emit all at once
                    self.done.emit(r)
                elif not self._cancelled:
                    self.error.emit("No response received")
                    
        except Exception as e:
            print(f"[LADA] Streaming error: {e}")
            self.error.emit(f"Streaming error: {str(e)}")



class VoiceWorker(QThread):
    result = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, voice=None):
        super().__init__()
        self.voice = voice
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            if self.voice:
                txt = self.voice.listen_mixed()
                if txt and not self._stop:
                    self.result.emit(txt)
                elif not self._stop:
                    self.error.emit("No speech")
            else:
                import speech_recognition as sr
                rec = sr.Recognizer()
                with sr.Microphone() as src:
                    rec.adjust_for_ambient_noise(src, 0.3)
                    audio = rec.listen(src, timeout=8, phrase_time_limit=12)
                txt = rec.recognize_google(audio)
                if txt:
                    self.result.emit(txt)
        except Exception as e:
            if not self._stop:
                self.error.emit(str(e))



class RemoteBridgeWorker(QThread):
    running_changed = pyqtSignal(bool)
    error = pyqtSignal(str)

    def __init__(self, client):
        super().__init__()
        self.client = client

    def stop(self):
        try:
            self.client.stop()
        except Exception:
            pass

    def run(self):
        self.running_changed.emit(True)
        try:
            self.client.run_forever()
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.running_changed.emit(False)



