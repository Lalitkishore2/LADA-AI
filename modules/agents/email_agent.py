"""
LADA v7.0 - Email Agent
Gmail integration for email management
"""

import os
import json
import base64
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

# Try to import Google API libraries
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    GMAIL_OK = True
except ImportError:
    GMAIL_OK = False
    logger.warning("[EmailAgent] Google API libraries not installed. Run: pip install google-auth-oauthlib google-api-python-client")


class EmailAgent:
    """
    Gmail-based email agent for LADA.
    
    Features:
    - Draft emails
    - Send emails
    - Check inbox
    - Reply to emails
    - Search emails
    """
    
    # Gmail API scopes
    SCOPES = [
        'https://www.googleapis.com/auth/gmail.readonly',
        'https://www.googleapis.com/auth/gmail.send',
        'https://www.googleapis.com/auth/gmail.compose',
        'https://www.googleapis.com/auth/gmail.modify'
    ]
    
    def __init__(self, credentials_path: str = "config/gmail_credentials.json"):
        """
        Initialize the email agent.
        Authentication is deferred until first use to avoid blocking startup.
        
        Args:
            credentials_path: Path to Gmail API credentials file
        """
        self.credentials_path = Path(credentials_path)
        self.token_path = Path("config/gmail_token.json")
        self.service = None
        self.initialized = False
        self._auth_attempted = False
        
        # Don't authenticate on init - defer until first use
        if not GMAIL_OK:
            logger.warning("[EmailAgent] Gmail API not available")
    
    def _ensure_authenticated(self) -> bool:
        """
        Ensure authenticated before API calls.
        Only tries once, only if valid token exists (no browser popup).
        """
        if self.initialized:
            return True
        
        if self._auth_attempted:
            return False
        
        if not GMAIL_OK:
            return False
        
        # Check for credentials file
        if not self.credentials_path.exists():
            logger.warning("[EmailAgent] No credentials file found")
            self._auth_attempted = True
            return False
        
        # Try to use existing token (no browser popup)
        if self.token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_path), self.SCOPES)
                
                if creds and creds.valid:
                    self.service = build('gmail', 'v1', credentials=creds)
                    self.initialized = True
                    logger.info("[EmailAgent] Authenticated successfully")
                    return True
                elif creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    with open(self.token_path, 'w') as token:
                        token.write(creds.to_json())
                    self.service = build('gmail', 'v1', credentials=creds)
                    self.initialized = True
                    logger.info("[EmailAgent] Token refreshed")
                    return True
            except Exception as e:
                logger.warning(f"[EmailAgent] Token invalid: {e}")
        
        # No valid token - require manual auth
        logger.info("[EmailAgent] Requires authentication via Settings")
        self._auth_attempted = True
        return False
    
    def _authenticate(self):
        """Legacy method - now just calls _ensure_authenticated"""
        return self._ensure_authenticated()
    
    def draft_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[str] = None,
        bcc: Optional[str] = None,
        html: bool = False
    ) -> Dict:
        """
        Create an email draft.
        
        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body content
            cc: CC recipients (comma-separated)
            bcc: BCC recipients (comma-separated)
            html: Whether body is HTML
            
        Returns:
            Draft info dict
        """
        if not self.initialized:
            return self._generate_fallback_draft(to, subject, body, cc, bcc)
        
        try:
            message = MIMEMultipart()
            message['to'] = to
            message['subject'] = subject
            
            if cc:
                message['cc'] = cc
            if bcc:
                message['bcc'] = bcc
            
            # Attach body
            if html:
                message.attach(MIMEText(body, 'html'))
            else:
                message.attach(MIMEText(body, 'plain'))
            
            # Encode message
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            # Create draft
            draft = self.service.users().drafts().create(
                userId='me',
                body={'message': {'raw': raw}}
            ).execute()
            
            return {
                'success': True,
                'draft_id': draft['id'],
                'message': f"Draft created successfully. To: {to}, Subject: {subject}",
                'to': to,
                'subject': subject
            }
            
        except Exception as e:
            logger.error(f"[EmailAgent] Failed to create draft: {e}")
            return self._generate_fallback_draft(to, subject, body, cc, bcc)
    
    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[str] = None,
        bcc: Optional[str] = None,
        html: bool = False
    ) -> Dict:
        """
        Send an email.
        
        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body content
            cc: CC recipients
            bcc: BCC recipients
            html: Whether body is HTML
            
        Returns:
            Send result dict
        """
        if not self.initialized:
            return {
                'success': False,
                'error': 'Gmail not initialized. Please set up Gmail API credentials.',
                'fallback': self._generate_fallback_draft(to, subject, body, cc, bcc)
            }
        
        try:
            message = MIMEMultipart()
            message['to'] = to
            message['subject'] = subject
            
            if cc:
                message['cc'] = cc
            if bcc:
                message['bcc'] = bcc
            
            if html:
                message.attach(MIMEText(body, 'html'))
            else:
                message.attach(MIMEText(body, 'plain'))
            
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            sent = self.service.users().messages().send(
                userId='me',
                body={'raw': raw}
            ).execute()
            
            return {
                'success': True,
                'message_id': sent['id'],
                'message': f"Email sent successfully to {to}",
                'to': to,
                'subject': subject
            }
            
        except Exception as e:
            logger.error(f"[EmailAgent] Failed to send email: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f"Failed to send email: {e}"
            }
    
    def check_inbox(
        self,
        max_results: int = 10,
        unread_only: bool = False,
        query: Optional[str] = None
    ) -> Dict:
        """
        Check inbox for emails.
        
        Args:
            max_results: Maximum number of emails to return
            unread_only: Only return unread emails
            query: Gmail search query (e.g., "from:boss@company.com")
            
        Returns:
            Inbox results dict
        """
        if not self.initialized:
            return self._generate_fallback_inbox()
        
        try:
            # Build query
            q_parts = []
            if unread_only:
                q_parts.append('is:unread')
            if query:
                q_parts.append(query)
            
            q = ' '.join(q_parts) if q_parts else None
            
            # Get messages
            results = self.service.users().messages().list(
                userId='me',
                maxResults=max_results,
                q=q
            ).execute()
            
            messages = results.get('messages', [])
            
            # Get message details
            emails = []
            for msg in messages[:max_results]:
                msg_data = self.service.users().messages().get(
                    userId='me',
                    id=msg['id'],
                    format='metadata',
                    metadataHeaders=['From', 'Subject', 'Date']
                ).execute()
                
                headers = {h['name']: h['value'] for h in msg_data.get('payload', {}).get('headers', [])}
                
                emails.append({
                    'id': msg['id'],
                    'from': headers.get('From', 'Unknown'),
                    'subject': headers.get('Subject', '(No Subject)'),
                    'date': headers.get('Date', ''),
                    'snippet': msg_data.get('snippet', '')[:100],
                    'unread': 'UNREAD' in msg_data.get('labelIds', [])
                })
            
            return {
                'success': True,
                'count': len(emails),
                'emails': emails,
                'message': f"Found {len(emails)} emails"
            }
            
        except Exception as e:
            logger.error(f"[EmailAgent] Failed to check inbox: {e}")
            return self._generate_fallback_inbox()
    
    def reply_to_email(
        self,
        message_id: str,
        body: str,
        html: bool = False
    ) -> Dict:
        """
        Reply to an email.
        
        Args:
            message_id: ID of the email to reply to
            body: Reply body content
            html: Whether body is HTML
            
        Returns:
            Reply result dict
        """
        if not self.initialized:
            return {
                'success': False,
                'error': 'Gmail not initialized',
                'message': 'Please set up Gmail API credentials.'
            }
        
        try:
            # Get original message
            original = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='metadata',
                metadataHeaders=['From', 'Subject', 'Message-ID']
            ).execute()
            
            headers = {h['name']: h['value'] for h in original.get('payload', {}).get('headers', [])}
            
            # Build reply
            to = headers.get('From', '')
            subject = headers.get('Subject', '')
            if not subject.lower().startswith('re:'):
                subject = f"Re: {subject}"
            
            message = MIMEMultipart()
            message['to'] = to
            message['subject'] = subject
            message['In-Reply-To'] = headers.get('Message-ID', '')
            message['References'] = headers.get('Message-ID', '')
            
            if html:
                message.attach(MIMEText(body, 'html'))
            else:
                message.attach(MIMEText(body, 'plain'))
            
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            sent = self.service.users().messages().send(
                userId='me',
                body={
                    'raw': raw,
                    'threadId': original.get('threadId')
                }
            ).execute()
            
            return {
                'success': True,
                'message_id': sent['id'],
                'message': f"Reply sent to {to}",
                'to': to,
                'subject': subject
            }
            
        except Exception as e:
            logger.error(f"[EmailAgent] Failed to reply: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f"Failed to reply: {e}"
            }
    
    def _generate_fallback_draft(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[str] = None,
        bcc: Optional[str] = None
    ) -> Dict:
        """Generate a fallback draft when Gmail is not available."""
        draft_content = f"""To: {to}
Subject: {subject}
{f'CC: {cc}' if cc else ''}
{f'BCC: {bcc}' if bcc else ''}

{body}

---
(Draft generated by LADA - Gmail API not configured)
"""
        
        # Save to drafts folder
        drafts_dir = Path("data/email_drafts")
        drafts_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"draft_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        filepath = drafts_dir / filename
        
        filepath.write_text(draft_content, encoding='utf-8')
        
        return {
            'success': True,
            'type': 'local_draft',
            'path': str(filepath),
            'message': f"Draft saved locally (Gmail not configured): {filepath}",
            'to': to,
            'subject': subject,
            'content': draft_content
        }
    
    def _generate_fallback_inbox(self) -> Dict:
        """Generate fallback inbox data when Gmail is not available."""
        return {
            'success': False,
            'count': 0,
            'emails': [],
            'message': 'Gmail API not configured. To enable email features:\n'
                      '1. Go to console.cloud.google.com\n'
                      '2. Create OAuth credentials for Gmail API\n'
                      '3. Save as config/gmail_credentials.json\n'
                      '4. Restart LADA'
        }
    
    def process(self, query: str) -> Dict:
        """
        Process a natural language email request.
        
        Args:
            query: Natural language query
            
        Returns:
            Result dict
        """
        query_lower = query.lower()
        
        # Check inbox
        if any(kw in query_lower for kw in ['inbox', 'check email', 'check mail', 'new email', 'unread']):
            unread_only = 'unread' in query_lower
            return self.check_inbox(unread_only=unread_only)
        
        # Draft email
        if any(kw in query_lower for kw in ['draft', 'compose', 'write email', 'write mail']):
            return {
                'success': True,
                'action': 'draft',
                'message': 'To draft an email, please provide:\n'
                          '- To: recipient@email.com\n'
                          '- Subject: Your subject\n'
                          '- Body: Your message\n\n'
                          'Example: "Draft email to boss@company.com about meeting"'
            }
        
        # Send email
        if any(kw in query_lower for kw in ['send email', 'send mail']):
            return {
                'success': True,
                'action': 'send',
                'message': 'To send an email, please provide recipient, subject, and body.'
            }
        
        return {
            'success': True,
            'message': 'Email agent ready. Commands:\n'
                      '- "Check inbox" - View recent emails\n'
                      '- "Check unread" - View unread emails\n'
                      '- "Draft email" - Compose a new email\n'
                      '- "Send email to X" - Send an email'
        }


# ============================================================
# EXAMPLE USAGE
# ============================================================
if __name__ == "__main__":
    print("🚀 Testing EmailAgent...")
    
    agent = EmailAgent()
    
    print(f"\n📧 Gmail API available: {GMAIL_OK}")
    print(f"📧 Agent initialized: {agent.initialized}")
    
    # Test draft generation (fallback)
    print("\n📝 Testing draft generation...")
    draft = agent.draft_email(
        to="test@example.com",
        subject="Test Email from LADA",
        body="Hello,\n\nThis is a test email generated by LADA.\n\nBest regards,\nLADA"
    )
    print(f"  Result: {draft.get('message', draft)}")
    
    # Test process
    print("\n🔍 Testing process...")
    result = agent.process("check my inbox")
    print(f"  Result: {result.get('message', result)[:100]}...")
    
    print("\n✅ EmailAgent test complete!")
