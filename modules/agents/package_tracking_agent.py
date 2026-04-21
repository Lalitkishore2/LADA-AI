"""
LADA v10.0 - Package Tracking Agent
Automated package and shipment tracking across multiple carriers

Supports:
- Amazon tracking
- FedEx, UPS, USPS, DHL
- India Post, Blue Dart, Delhivery
- Flipkart, Myntra orders
- Generic tracking number lookup
"""

import os
import sys
import json
import logging
import re
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

logger = logging.getLogger(__name__)


class Carrier(Enum):
    """Supported shipping carriers"""
    AMAZON = "amazon"
    FEDEX = "fedex"
    UPS = "ups"
    USPS = "usps"
    DHL = "dhl"
    INDIA_POST = "india_post"
    BLUE_DART = "blue_dart"
    DELHIVERY = "delhivery"
    FLIPKART = "flipkart"
    UNKNOWN = "unknown"


class PackageStatus(Enum):
    """Package delivery status"""
    ORDERED = "ordered"
    SHIPPED = "shipped"
    IN_TRANSIT = "in_transit"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    EXCEPTION = "exception"
    RETURNED = "returned"
    UNKNOWN = "unknown"


@dataclass
class TrackingResult:
    """Result from package tracking"""
    success: bool
    carrier: Carrier
    tracking_number: str
    status: PackageStatus
    status_description: str
    estimated_delivery: Optional[str] = None
    last_location: Optional[str] = None
    last_update: Optional[str] = None
    delivery_date: Optional[str] = None
    tracking_history: Optional[List[Dict]] = None
    tracking_url: Optional[str] = None
    error: Optional[str] = None


class PackageTrackingAgent:
    """
    Automated package tracking agent.
    Tracks packages across multiple carriers using browser automation.
    """
    
    # Tracking number patterns for carrier detection
    CARRIER_PATTERNS = {
        Carrier.FEDEX: [
            r'^\d{12}$',           # 12 digits
            r'^\d{15}$',           # 15 digits
            r'^\d{20}$',           # 20 digits
            r'^[0-9]{22}$',        # 22 digits (door tag)
        ],
        Carrier.UPS: [
            r'^1Z[A-Z0-9]{16}$',   # 1Z + 16 alphanumeric
            r'^T\d{10}$',          # T + 10 digits
            r'^\d{9}$',            # 9 digits
            r'^\d{26}$',           # 26 digits (mail innovations)
        ],
        Carrier.USPS: [
            r'^[0-9]{20,22}$',     # 20-22 digits
            r'^[A-Z]{2}\d{9}US$',  # International format
            r'^94\d{20}$',         # Starts with 94
            r'^92\d{20}$',         # Starts with 92
        ],
        Carrier.DHL: [
            r'^\d{10}$',           # 10 digits
            r'^[A-Z]{3}\d{7}$',    # 3 letters + 7 digits
            r'^\d{11}$',           # 11 digits (eCommerce)
        ],
        Carrier.INDIA_POST: [
            r'^[A-Z]{2}\d{9}IN$',  # International format
            r'^[E-R][A-Z]\d{9}IN$',# Speed Post
        ],
        Carrier.BLUE_DART: [
            r'^\d{11}$',           # 11 digits
            r'^[A-Z0-9]{9,11}$',   # Alphanumeric
        ],
        Carrier.DELHIVERY: [
            r'^\d{13,14}$',        # 13-14 digits
        ],
    }
    
    # Carrier tracking URLs
    TRACKING_URLS = {
        Carrier.AMAZON: "https://www.amazon.in/gp/css/order-history",
        Carrier.FEDEX: "https://www.fedex.com/fedextrack/?trknbr={tracking}",
        Carrier.UPS: "https://www.ups.com/track?tracknum={tracking}",
        Carrier.USPS: "https://tools.usps.com/go/TrackConfirmAction?tLabels={tracking}",
        Carrier.DHL: "https://www.dhl.com/en/express/tracking.html?AWB={tracking}",
        Carrier.INDIA_POST: "https://www.indiapost.gov.in/_layouts/15/dop.portal.tracking/trackconsignment.aspx",
        Carrier.BLUE_DART: "https://www.bluedart.com/tracking/{tracking}",
        Carrier.DELHIVERY: "https://www.delhivery.com/track/package/{tracking}",
        Carrier.FLIPKART: "https://www.flipkart.com/account/orders",
    }
    
    def __init__(self, ai_router=None):
        """
        Initialize package tracking agent.
        
        Args:
            ai_router: Optional HybridAIRouter for AI-powered extraction
        """
        self.ai_router = ai_router
        self.browser = None
        self.tracked_packages = {}  # Cache of tracked packages
        
    def _init_browser(self):
        """Initialize browser for tracking"""
        try:
            from modules.browser_automation import CometBrowserAgent
            self.browser = CometBrowserAgent(headless=True)
            return self.browser.init_browser()
        except Exception as e:
            logger.error(f"Failed to initialize browser: {e}")
            return False
    
    def detect_carrier(self, tracking_number: str) -> Carrier:
        """
        Detect carrier from tracking number format.
        
        Args:
            tracking_number: The tracking number to analyze
            
        Returns:
            Detected Carrier enum value
        """
        tracking = tracking_number.upper().replace(' ', '').replace('-', '')
        
        for carrier, patterns in self.CARRIER_PATTERNS.items():
            for pattern in patterns:
                if re.match(pattern, tracking):
                    return carrier
        
        return Carrier.UNKNOWN
    
    def get_tracking_url(self, tracking_number: str, carrier: Optional[Carrier] = None) -> str:
        """
        Get the tracking URL for a package.
        
        Args:
            tracking_number: The tracking number
            carrier: Optional carrier (will auto-detect if not provided)
            
        Returns:
            Tracking URL string
        """
        if not carrier:
            carrier = self.detect_carrier(tracking_number)
        
        url_template = self.TRACKING_URLS.get(carrier, "")
        if url_template:
            return url_template.format(tracking=tracking_number)
        
        # Fallback to generic search
        return f"https://www.google.com/search?q=track+package+{tracking_number}"
    
    def track_package(
        self,
        tracking_number: str,
        carrier: Optional[Carrier] = None,
        use_browser: bool = True,
        progress_callback=None
    ) -> TrackingResult:
        """
        Track a package by tracking number.
        
        Args:
            tracking_number: The package tracking number
            carrier: Optional carrier (auto-detected if not provided)
            use_browser: Whether to use browser automation for live tracking
            progress_callback: Optional callback(step, total, description)
            
        Returns:
            TrackingResult with package status and history
        """
        tracking = tracking_number.upper().replace(' ', '').replace('-', '')
        
        # Auto-detect carrier if not provided
        if not carrier:
            carrier = self.detect_carrier(tracking)
        
        if progress_callback:
            progress_callback(1, 5, f"Detected carrier: {carrier.value}")
        
        # Get tracking URL
        tracking_url = self.get_tracking_url(tracking, carrier)
        
        if not use_browser:
            # Return basic result without browser automation
            return TrackingResult(
                success=True,
                carrier=carrier,
                tracking_number=tracking,
                status=PackageStatus.UNKNOWN,
                status_description="Use the tracking URL to check status",
                tracking_url=tracking_url
            )
        
        # Use browser automation for live tracking
        try:
            if progress_callback:
                progress_callback(2, 5, "Initializing browser...")
            
            if not self.browser:
                if not self._init_browser():
                    return TrackingResult(
                        success=False,
                        carrier=carrier,
                        tracking_number=tracking,
                        status=PackageStatus.UNKNOWN,
                        status_description="Could not initialize browser",
                        tracking_url=tracking_url,
                        error="Browser initialization failed"
                    )
            
            if progress_callback:
                progress_callback(3, 5, f"Opening {carrier.value} tracking...")
            
            # Navigate to tracking page
            result = self.browser.navigate(tracking_url)
            if not result.get('success'):
                return TrackingResult(
                    success=False,
                    carrier=carrier,
                    tracking_number=tracking,
                    status=PackageStatus.UNKNOWN,
                    status_description="Could not open tracking page",
                    tracking_url=tracking_url,
                    error=result.get('error', 'Navigation failed')
                )
            
            # Wait for page to load
            import time
            time.sleep(3)
            
            if progress_callback:
                progress_callback(4, 5, "Extracting tracking info...")
            
            # Extract tracking information based on carrier
            tracking_info = self._extract_tracking_info(carrier, tracking)
            
            if progress_callback:
                progress_callback(5, 5, "Done!")
            
            return tracking_info
            
        except Exception as e:
            logger.error(f"Tracking error: {e}")
            return TrackingResult(
                success=False,
                carrier=carrier,
                tracking_number=tracking,
                status=PackageStatus.UNKNOWN,
                status_description=str(e),
                tracking_url=tracking_url,
                error=str(e)
            )
        finally:
            if self.browser:
                try:
                    self.browser.close()
                except Exception as e:
                    pass
                self.browser = None
    
    def _extract_tracking_info(self, carrier: Carrier, tracking_number: str) -> TrackingResult:
        """
        Extract tracking information from the current page.
        Uses AI vision if available, otherwise uses DOM parsing.
        """
        tracking_url = self.get_tracking_url(tracking_number, carrier)
        
        # Try to get page content
        try:
            page_text = self.browser.get_page_text() if self.browser else ""
        except Exception as e:
            page_text = ""
        
        # Try AI-powered extraction if available
        if self.ai_router and page_text:
            try:
                prompt = f"""
                Analyze this shipping tracking page and extract:
                1. Current status (ordered/shipped/in_transit/out_for_delivery/delivered/exception)
                2. Status description
                3. Estimated delivery date
                4. Last known location
                5. Last update time

                Page content:
                {page_text[:3000]}

                Respond in JSON format:
                {{"status": "...", "description": "...", "delivery_date": "...", "location": "...", "last_update": "..."}}
                """
                
                response = self.ai_router.query(prompt)
                if response:
                    # Try to parse JSON from response
                    import json
                    # Find JSON in response
                    json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
                    if json_match:
                        info = json.loads(json_match.group())
                        
                        status_map = {
                            'ordered': PackageStatus.ORDERED,
                            'shipped': PackageStatus.SHIPPED,
                            'in_transit': PackageStatus.IN_TRANSIT,
                            'out_for_delivery': PackageStatus.OUT_FOR_DELIVERY,
                            'delivered': PackageStatus.DELIVERED,
                            'exception': PackageStatus.EXCEPTION,
                        }
                        
                        status = status_map.get(
                            info.get('status', '').lower(),
                            PackageStatus.UNKNOWN
                        )
                        
                        return TrackingResult(
                            success=True,
                            carrier=carrier,
                            tracking_number=tracking_number,
                            status=status,
                            status_description=info.get('description', 'Package is being tracked'),
                            estimated_delivery=info.get('delivery_date'),
                            last_location=info.get('location'),
                            last_update=info.get('last_update'),
                            tracking_url=tracking_url
                        )
            except Exception as e:
                logger.warning(f"AI extraction failed: {e}")
        
        # Fallback: Basic keyword detection
        page_lower = page_text.lower()
        
        if 'delivered' in page_lower:
            status = PackageStatus.DELIVERED
            description = "Package has been delivered"
        elif 'out for delivery' in page_lower:
            status = PackageStatus.OUT_FOR_DELIVERY
            description = "Package is out for delivery"
        elif 'in transit' in page_lower or 'on the way' in page_lower:
            status = PackageStatus.IN_TRANSIT
            description = "Package is in transit"
        elif 'shipped' in page_lower or 'dispatched' in page_lower:
            status = PackageStatus.SHIPPED
            description = "Package has been shipped"
        elif 'exception' in page_lower or 'delay' in page_lower:
            status = PackageStatus.EXCEPTION
            description = "There may be a delivery exception"
        else:
            status = PackageStatus.UNKNOWN
            description = "Status could not be determined"
        
        return TrackingResult(
            success=True,
            carrier=carrier,
            tracking_number=tracking_number,
            status=status,
            status_description=description,
            tracking_url=tracking_url
        )
    
    def track_amazon_orders(self, progress_callback=None) -> List[TrackingResult]:
        """
        Track all recent Amazon orders.
        Requires Amazon login.
        
        Returns:
            List of TrackingResult for each order
        """
        results = []
        
        try:
            if progress_callback:
                progress_callback(1, 4, "Opening Amazon orders...")
            
            if not self.browser:
                if not self._init_browser():
                    return []
            
            # Navigate to Amazon order history
            self.browser.navigate("https://www.amazon.in/gp/css/order-history")
            
            import time
            time.sleep(3)
            
            if progress_callback:
                progress_callback(2, 4, "Checking login status...")
            
            # Check if login required
            page_text = self.browser.get_page_text() if self.browser else ""
            
            if 'sign in' in page_text.lower() or 'sign-in' in page_text.lower():
                return [TrackingResult(
                    success=False,
                    carrier=Carrier.AMAZON,
                    tracking_number="",
                    status=PackageStatus.UNKNOWN,
                    status_description="Amazon login required",
                    tracking_url=self.TRACKING_URLS[Carrier.AMAZON],
                    error="Please log in to Amazon to view orders"
                )]
            
            if progress_callback:
                progress_callback(3, 4, "Extracting order info...")
            
            # Extract order information using AI if available
            if self.ai_router and page_text:
                prompt = f"""
                Extract all orders from this Amazon order history page.
                For each order provide:
                - Order ID
                - Product name
                - Status (ordered/shipped/delivered)
                - Estimated delivery date

                Page content:
                {page_text[:5000]}

                Respond as JSON array:
                [{{"order_id": "...", "product": "...", "status": "...", "delivery": "..."}}]
                """
                
                response = self.ai_router.query(prompt)
                if response:
                    try:
                        json_match = re.search(r'\[.*\]', response, re.DOTALL)
                        if json_match:
                            orders = json.loads(json_match.group())
                            
                            for order in orders:
                                status_map = {
                                    'ordered': PackageStatus.ORDERED,
                                    'shipped': PackageStatus.SHIPPED,
                                    'delivered': PackageStatus.DELIVERED,
                                }
                                
                                results.append(TrackingResult(
                                    success=True,
                                    carrier=Carrier.AMAZON,
                                    tracking_number=order.get('order_id', 'Unknown'),
                                    status=status_map.get(
                                        order.get('status', '').lower(),
                                        PackageStatus.UNKNOWN
                                    ),
                                    status_description=order.get('product', 'Amazon Order'),
                                    estimated_delivery=order.get('delivery'),
                                    tracking_url=self.TRACKING_URLS[Carrier.AMAZON]
                                ))
                    except Exception as e:
                        pass
            
            if progress_callback:
                progress_callback(4, 4, "Done!")
            
            return results
            
        except Exception as e:
            logger.error(f"Amazon tracking error: {e}")
            return [TrackingResult(
                success=False,
                carrier=Carrier.AMAZON,
                tracking_number="",
                status=PackageStatus.UNKNOWN,
                status_description=str(e),
                error=str(e)
            )]
        finally:
            if self.browser:
                try:
                    self.browser.close()
                except Exception as e:
                    pass
                self.browser = None
    
    def format_tracking_result(self, result: TrackingResult) -> str:
        """
        Format tracking result as human-readable text.
        
        Args:
            result: TrackingResult to format
            
        Returns:
            Formatted string
        """
        if not result.success:
            return f"❌ Tracking failed: {result.error or result.status_description}"
        
        status_icons = {
            PackageStatus.ORDERED: "📦",
            PackageStatus.SHIPPED: "🚚",
            PackageStatus.IN_TRANSIT: "🛫",
            PackageStatus.OUT_FOR_DELIVERY: "🏃",
            PackageStatus.DELIVERED: "✅",
            PackageStatus.EXCEPTION: "⚠️",
            PackageStatus.RETURNED: "↩️",
            PackageStatus.UNKNOWN: "❓",
        }
        
        icon = status_icons.get(result.status, "📦")
        
        lines = [
            f"{icon} **{result.carrier.value.upper()} Tracking**",
            f"📋 Tracking #: `{result.tracking_number}`",
            f"📊 Status: {result.status.value.replace('_', ' ').title()}",
            f"📝 {result.status_description}",
        ]
        
        if result.estimated_delivery:
            lines.append(f"📅 Est. Delivery: {result.estimated_delivery}")
        
        if result.last_location:
            lines.append(f"📍 Last Location: {result.last_location}")
        
        if result.last_update:
            lines.append(f"🕐 Last Update: {result.last_update}")
        
        if result.tracking_url:
            lines.append(f"\n🔗 [Track Online]({result.tracking_url})")
        
        return "\n".join(lines)


# ============================================================
# EXAMPLE USAGE
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    agent = PackageTrackingAgent()
    
    print("📦 Package Tracking Agent Test")
    print("=" * 50)
    
    # Test carrier detection
    test_numbers = [
        "1Z9999999999999999",  # UPS
        "123456789012",        # FedEx
        "9400111899223033333333",  # USPS
        "1234567890",          # DHL
        "EE123456789IN",       # India Post
    ]
    
    for tracking in test_numbers:
        carrier = agent.detect_carrier(tracking)
        url = agent.get_tracking_url(tracking)
        print(f"\n{tracking}")
        print(f"  Carrier: {carrier.value}")
        print(f"  URL: {url[:60]}...")
    
    # Test tracking (without browser)
    print("\n" + "=" * 50)
    print("Testing basic tracking (no browser)...")
    
    result = agent.track_package("1Z9999999999999999", use_browser=False)
    print(agent.format_tracking_result(result))
    
    print("\n✅ Package Tracking Agent test complete!")
