"""
LADA v9.0 - Gmail Full Control
Complete Gmail control for JARVIS-level email automation.

Features:
- Compose and send emails
- Read and search emails
- Organize emails (labels, archive, delete)
- Handle attachments
- Draft management
- OAuth2 authentication with Gmail API
"""

import os
import base64
import logging
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import mimetypes

logger = logging.getLogger(__name__)

# Try to import Google API libraries
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_API_OK = True
except ImportError:
    GOOGLE_API_OK = False
    logger.warning("[!] Google API libraries not available - install google-api-python-client, google-auth-oauthlib")


# Gmail API scopes
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.labels',
]


@dataclass
class EmailMessage:
    """Represents an email message"""
    id: str
    thread_id: str
    subject: str
    sender: str
    recipients: List[str]
    date: datetime
    snippet: str
    body: str = ""
    labels: List[str] = field(default_factory=list)
    attachments: List[Dict] = field(default_factory=list)
    is_unread: bool = False
    is_starred: bool = False
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'thread_id': self.thread_id,
            'subject': self.subject,
            'sender': self.sender,
            'recipients': self.recipients,
            'date': self.date.isoformat() if self.date else None,
            'snippet': self.snippet,
            'body': self.body[:500] if self.body else "",
            'labels': self.labels,
            'attachments': self.attachments,
            'is_unread': self.is_unread,
            'is_starred': self.is_starred
        }


class GmailController:
    """
    Complete Gmail control via Gmail API.
    Enables JARVIS-level email automation.
    """
    
    def __init__(self, credentials_path: str = "config/credentials.json",
                 token_path: str = "config/gmail_token.json"):
        """
        Initialize Gmail controller.
        Authentication is deferred until first use to avoid blocking startup.
        
        Args:
            credentials_path: Path to OAuth2 credentials JSON
            token_path: Path to store/load token
        """
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        self.service = None
        self.user_email = None
        self._auth_attempted = False
        
        # Don't authenticate on init - defer until first use
        if not GOOGLE_API_OK:
            logger.warning("[!] Google API not available - Gmail features disabled")
        
        logger.info("[OK] Gmail Controller initialized (auth deferred)")
    
    def _ensure_authenticated(self) -> bool:
        """
        Ensure we're authenticated before making API calls.
        Only attempts authentication once, and only if credentials exist.
        """
        if self.service is not None:
            return True
        
        if self._auth_attempted:
            return False
        
        if not GOOGLE_API_OK:
            return False
        
        # Check if credentials file exists before attempting OAuth
        if not self.credentials_path.exists():
            logger.warning(f"[!] Gmail credentials not found: {self.credentials_path}")
            logger.info("[!] To enable Gmail: Add credentials.json from Google Cloud Console")
            self._auth_attempted = True
            return False
        
        # Check if we have a valid token already (no browser needed)
        if self.token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
                if creds and creds.valid:
                    self.service = build('gmail', 'v1', credentials=creds)
                    profile = self.service.users().getProfile(userId='me').execute()
                    self.user_email = profile.get('emailAddress')
                    logger.info(f"[OK] Gmail authenticated as {self.user_email}")
                    return True
                elif creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    with open(self.token_path, 'w') as token:
                        token.write(creds.to_json())
                    self.service = build('gmail', 'v1', credentials=creds)
                    profile = self.service.users().getProfile(userId='me').execute()
                    self.user_email = profile.get('emailAddress')
                    logger.info(f"[OK] Gmail token refreshed for {self.user_email}")
                    return True
            except Exception as e:
                logger.warning(f"[!] Gmail token invalid: {e}")
        
        # No valid token - require manual authentication via settings
        logger.info("[!] Gmail requires authentication - use Settings to connect")
        self._auth_attempted = True
        return False
    
    def authenticate_interactive(self) -> bool:
        """
        Perform interactive OAuth authentication (opens browser).
        Call this from Settings when user explicitly wants to connect Gmail.
        """
        if not GOOGLE_API_OK:
            return False
        
        if not self.credentials_path.exists():
            logger.error(f"[X] Credentials file not found: {self.credentials_path}")
            return False
        
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.credentials_path), SCOPES
            )
            creds = flow.run_local_server(port=0)
            
            # Save token
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.token_path, 'w') as token:
                token.write(creds.to_json())
            
            # Build service
            self.service = build('gmail', 'v1', credentials=creds)
            
            # Get user email
            profile = self.service.users().getProfile(userId='me').execute()
            self.user_email = profile.get('emailAddress')
            self._auth_attempted = False  # Reset so future calls work
            
            logger.info(f"[OK] Gmail authenticated as {self.user_email}")
            return True
        
        except Exception as e:
            logger.error(f"[X] Gmail authentication failed: {e}")
            return False
    
    def _authenticate(self) -> bool:
        """Legacy method - now just calls _ensure_authenticated"""
        return self._ensure_authenticated()
    
    def is_authenticated(self) -> bool:
        """Check if Gmail is authenticated"""
        return self.service is not None
    
    # ==================== SEND EMAILS ====================
    
    def send_email(self, to: str, subject: str, body: str,
                   cc: Optional[List[str]] = None,
                   bcc: Optional[List[str]] = None,
                   attachments: Optional[List[str]] = None,
                   html: bool = False) -> Dict[str, Any]:
        """
        Send an email.
        
        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body
            cc: CC recipients
            bcc: BCC recipients
            attachments: List of file paths to attach
            html: Whether body is HTML
        
        Returns:
            Dict with success status
        """
        if not self.service:
            return {'success': False, 'error': 'Gmail not authenticated'}
        
        try:
            # Create message
            if attachments:
                message = MIMEMultipart()
                message.attach(MIMEText(body, 'html' if html else 'plain'))
                
                for filepath in attachments:
                    self._attach_file(message, filepath)
            else:
                message = MIMEText(body, 'html' if html else 'plain')
            
            message['to'] = to
            message['subject'] = subject
            
            if cc:
                message['cc'] = ', '.join(cc)
            if bcc:
                message['bcc'] = ', '.join(bcc)
            
            # Encode message
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            # Send
            result = self.service.users().messages().send(
                userId='me',
                body={'raw': raw}
            ).execute()
            
            logger.info(f"[OK] Email sent to {to}: {subject}")
            return {
                'success': True,
                'message_id': result['id'],
                'to': to,
                'subject': subject,
                'message': f"Email sent to {to}"
            }
        
        except HttpError as e:
            logger.error(f"[X] Failed to send email: {e}")
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"[X] Failed to send email: {e}")
            return {'success': False, 'error': str(e)}
    
    def _attach_file(self, message: MIMEMultipart, filepath: str):
        """Attach a file to the message"""
        path = Path(filepath)
        if not path.exists():
            logger.warning(f"[!] Attachment not found: {filepath}")
            return
        
        content_type, _ = mimetypes.guess_type(str(path))
        if content_type is None:
            content_type = 'application/octet-stream'
        
        main_type, sub_type = content_type.split('/', 1)
        
        with open(path, 'rb') as f:
            part = MIMEBase(main_type, sub_type)
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', 'attachment', filename=path.name)
            message.attach(part)
    
    def send_reply(self, message_id: str, body: str, 
                   reply_all: bool = False) -> Dict[str, Any]:
        """
        Reply to an email.
        
        Args:
            message_id: ID of message to reply to
            body: Reply body
            reply_all: Reply to all recipients
        
        Returns:
            Dict with success status
        """
        if not self.service:
            return {'success': False, 'error': 'Gmail not authenticated'}
        
        try:
            # Get original message
            original = self.service.users().messages().get(
                userId='me', id=message_id, format='metadata',
                metadataHeaders=['Subject', 'From', 'To', 'Cc', 'Message-ID']
            ).execute()
            
            headers = {h['name']: h['value'] for h in original['payload']['headers']}
            
            # Create reply
            message = MIMEText(body)
            message['Subject'] = 'Re: ' + headers.get('Subject', '')
            message['To'] = headers.get('From', '')
            message['In-Reply-To'] = headers.get('Message-ID', '')
            message['References'] = headers.get('Message-ID', '')
            
            if reply_all:
                cc_list = []
                if 'To' in headers:
                    cc_list.extend([e.strip() for e in headers['To'].split(',')])
                if 'Cc' in headers:
                    cc_list.extend([e.strip() for e in headers['Cc'].split(',')])
                # Remove self
                cc_list = [e for e in cc_list if self.user_email not in e]
                if cc_list:
                    message['Cc'] = ', '.join(cc_list)
            
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            result = self.service.users().messages().send(
                userId='me',
                body={'raw': raw, 'threadId': original['threadId']}
            ).execute()
            
            return {
                'success': True,
                'message_id': result['id'],
                'thread_id': result['threadId'],
                'message': "Reply sent"
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def create_draft(self, to: str, subject: str, body: str) -> Dict[str, Any]:
        """
        Create a draft email.
        
        Args:
            to: Recipient email
            subject: Email subject
            body: Email body
        
        Returns:
            Dict with success status
        """
        if not self.service:
            return {'success': False, 'error': 'Gmail not authenticated'}
        
        try:
            message = MIMEText(body)
            message['to'] = to
            message['subject'] = subject
            
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            draft = self.service.users().drafts().create(
                userId='me',
                body={'message': {'raw': raw}}
            ).execute()
            
            return {
                'success': True,
                'draft_id': draft['id'],
                'message': f"Draft created: {subject}"
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ==================== READ EMAILS ====================
    
    def get_inbox(self, max_results: int = 10, 
                  unread_only: bool = False) -> Dict[str, Any]:
        """
        Get inbox messages.
        
        Args:
            max_results: Maximum messages to return
            unread_only: Only return unread messages
        
        Returns:
            Dict with messages
        """
        query = 'in:inbox'
        if unread_only:
            query += ' is:unread'
        
        return self.search_emails(query, max_results)
    
    def get_unread_count(self) -> Dict[str, Any]:
        """Get count of unread emails"""
        if not self.service:
            return {'success': False, 'error': 'Gmail not authenticated'}
        
        try:
            result = self.service.users().messages().list(
                userId='me',
                q='is:unread',
                maxResults=1
            ).execute()
            
            count = result.get('resultSizeEstimate', 0)
            
            return {
                'success': True,
                'unread_count': count,
                'message': f"You have {count} unread emails"
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def search_emails(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        """
        Search emails with Gmail query syntax.
        
        Args:
            query: Gmail search query (e.g., "from:john subject:meeting")
            max_results: Maximum results to return
        
        Returns:
            Dict with matching emails
        """
        if not self.service:
            return {'success': False, 'error': 'Gmail not authenticated'}
        
        try:
            result = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
            
            messages = []
            for msg in result.get('messages', []):
                email = self._get_message_details(msg['id'])
                if email:
                    messages.append(email.to_dict())
            
            return {
                'success': True,
                'query': query,
                'count': len(messages),
                'messages': messages
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_email(self, message_id: str) -> Dict[str, Any]:
        """
        Get a specific email by ID.
        
        Args:
            message_id: Message ID
        
        Returns:
            Dict with email details
        """
        if not self.service:
            return {'success': False, 'error': 'Gmail not authenticated'}
        
        try:
            email = self._get_message_details(message_id, include_body=True)
            if email:
                return {
                    'success': True,
                    'email': email.to_dict()
                }
            return {'success': False, 'error': 'Email not found'}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _get_message_details(self, message_id: str, 
                              include_body: bool = False) -> Optional[EmailMessage]:
        """Get email message details"""
        try:
            msg = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full' if include_body else 'metadata',
                metadataHeaders=['Subject', 'From', 'To', 'Date']
            ).execute()
            
            headers = {h['name']: h['value'] for h in msg['payload']['headers']}
            
            # Parse date
            date_str = headers.get('Date', '')
            try:
                from email.utils import parsedate_to_datetime
                date = parsedate_to_datetime(date_str)
            except:
                date = datetime.now()
            
            # Get body if requested
            body = ""
            if include_body:
                body = self._extract_body(msg['payload'])
            
            # Parse labels
            labels = msg.get('labelIds', [])
            
            return EmailMessage(
                id=msg['id'],
                thread_id=msg['threadId'],
                subject=headers.get('Subject', '(No Subject)'),
                sender=headers.get('From', ''),
                recipients=[r.strip() for r in headers.get('To', '').split(',')],
                date=date,
                snippet=msg.get('snippet', ''),
                body=body,
                labels=labels,
                is_unread='UNREAD' in labels,
                is_starred='STARRED' in labels
            )
        
        except Exception as e:
            logger.error(f"[X] Failed to get message details: {e}")
            return None
    
    def _extract_body(self, payload: Dict) -> str:
        """Extract email body from payload"""
        body = ""
        
        if 'body' in payload and payload['body'].get('data'):
            body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
        elif 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain' and part['body'].get('data'):
                    body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                    break
                elif part['mimeType'] == 'text/html' and part['body'].get('data') and not body:
                    body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
        
        return body
    
    # ==================== ORGANIZE EMAILS ====================
    
    def mark_as_read(self, message_id: str) -> Dict[str, Any]:
        """Mark an email as read"""
        return self._modify_labels(message_id, remove_labels=['UNREAD'])
    
    def mark_as_unread(self, message_id: str) -> Dict[str, Any]:
        """Mark an email as unread"""
        return self._modify_labels(message_id, add_labels=['UNREAD'])
    
    def star_email(self, message_id: str) -> Dict[str, Any]:
        """Star an email"""
        return self._modify_labels(message_id, add_labels=['STARRED'])
    
    def unstar_email(self, message_id: str) -> Dict[str, Any]:
        """Remove star from email"""
        return self._modify_labels(message_id, remove_labels=['STARRED'])
    
    def archive_email(self, message_id: str) -> Dict[str, Any]:
        """Archive an email (remove from inbox)"""
        return self._modify_labels(message_id, remove_labels=['INBOX'])
    
    def trash_email(self, message_id: str) -> Dict[str, Any]:
        """Move email to trash"""
        if not self.service:
            return {'success': False, 'error': 'Gmail not authenticated'}
        
        try:
            self.service.users().messages().trash(
                userId='me', id=message_id
            ).execute()
            
            return {'success': True, 'message': 'Email moved to trash'}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def delete_email(self, message_id: str) -> Dict[str, Any]:
        """Permanently delete an email"""
        if not self.service:
            return {'success': False, 'error': 'Gmail not authenticated'}
        
        try:
            self.service.users().messages().delete(
                userId='me', id=message_id
            ).execute()
            
            return {'success': True, 'message': 'Email permanently deleted'}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _modify_labels(self, message_id: str, 
                       add_labels: List[str] = None,
                       remove_labels: List[str] = None) -> Dict[str, Any]:
        """Modify email labels"""
        if not self.service:
            return {'success': False, 'error': 'Gmail not authenticated'}
        
        try:
            body = {}
            if add_labels:
                body['addLabelIds'] = add_labels
            if remove_labels:
                body['removeLabelIds'] = remove_labels
            
            self.service.users().messages().modify(
                userId='me', id=message_id, body=body
            ).execute()
            
            return {'success': True, 'message': 'Labels updated'}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ==================== LABELS ====================
    
    def get_labels(self) -> Dict[str, Any]:
        """Get all Gmail labels"""
        if not self.service:
            return {'success': False, 'error': 'Gmail not authenticated'}
        
        try:
            result = self.service.users().labels().list(userId='me').execute()
            
            labels = [
                {'id': l['id'], 'name': l['name'], 'type': l['type']}
                for l in result.get('labels', [])
            ]
            
            return {
                'success': True,
                'labels': labels,
                'count': len(labels)
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def create_label(self, name: str) -> Dict[str, Any]:
        """Create a new label"""
        if not self.service:
            return {'success': False, 'error': 'Gmail not authenticated'}
        
        try:
            label = self.service.users().labels().create(
                userId='me',
                body={'name': name}
            ).execute()
            
            return {
                'success': True,
                'label_id': label['id'],
                'name': name,
                'message': f"Label '{name}' created"
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def apply_label(self, message_id: str, label_name: str) -> Dict[str, Any]:
        """Apply a label to an email"""
        # First get label ID
        labels = self.get_labels()
        if not labels.get('success'):
            return labels
        
        label_id = None
        for label in labels['labels']:
            if label['name'].lower() == label_name.lower():
                label_id = label['id']
                break
        
        if not label_id:
            # Create label if it doesn't exist
            result = self.create_label(label_name)
            if result.get('success'):
                label_id = result['label_id']
            else:
                return result
        
        return self._modify_labels(message_id, add_labels=[label_id])
    
    # ==================== UTILITY METHODS ====================
    
    def get_profile(self) -> Dict[str, Any]:
        """Get user's Gmail profile"""
        if not self.service:
            return {'success': False, 'error': 'Gmail not authenticated'}
        
        try:
            profile = self.service.users().getProfile(userId='me').execute()
            
            return {
                'success': True,
                'email': profile['emailAddress'],
                'messages_total': profile.get('messagesTotal', 0),
                'threads_total': profile.get('threadsTotal', 0),
                'history_id': profile.get('historyId', '')
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}


# Factory function for workflow engine integration
def create_gmail_controller(credentials_path: str = "config/credentials.json") -> GmailController:
    """Create and return a GmailController instance"""
    return GmailController(credentials_path)


if __name__ == '__main__':
    # Test the Gmail controller
    logging.basicConfig(level=logging.INFO)
    gmail = GmailController()
    
    print("\n=== Testing Gmail Controller ===")
    
    if gmail.is_authenticated():
        # Get profile
        profile = gmail.get_profile()
        if profile['success']:
            print(f"Authenticated as: {profile['email']}")
            print(f"Total messages: {profile['messages_total']}")
        
        # Get unread count
        unread = gmail.get_unread_count()
        if unread['success']:
            print(f"Unread emails: {unread['unread_count']}")
        
        # Get labels
        labels = gmail.get_labels()
        if labels['success']:
            print(f"Labels: {labels['count']}")
    else:
        print("[!] Gmail not authenticated")
        print("    Place credentials.json in config/ folder")
    
    print("\n[OK] Gmail Controller tests complete!")
    print("\nTry commands like:")
    print("  gmail.send_email('to@example.com', 'Subject', 'Body')")
    print("  gmail.get_inbox(5)")
    print("  gmail.search_emails('from:boss subject:urgent')")
