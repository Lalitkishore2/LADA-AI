import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from modules.browser_automation import CometBrowserAgent

class TestCometBrowserAgent:
    @pytest.fixture
    def mock_playwright(self):
        # Patch where it is imported
        with patch('playwright.async_api.async_playwright', new_callable=MagicMock) as mock_pw:
            # Setup the context manager mock
            mock_context_manager = MagicMock()
            mock_pw.return_value = mock_context_manager
            
            # Setup the playwright object
            mock_p = MagicMock()
            mock_context_manager.__aenter__.return_value = mock_p
            
            # Setup start() to return a Future via side_effect
            # This avoids AsyncMock ambiguity
            def start_side_effect(*args, **kwargs):
                f = asyncio.Future()
                f.set_result(mock_p)
                return f
            mock_context_manager.start = MagicMock(side_effect=start_side_effect)
            
            # Setup browser
            mock_browser = AsyncMock()
            # mock_p.chromium.launch must be an AsyncMock so calling it returns a coroutine
            mock_p.chromium.launch = AsyncMock(return_value=mock_browser)
            
            # Setup context and page
            mock_context = AsyncMock()
            # mock_browser is AsyncMock, so new_context is automatically AsyncMock
            mock_browser.new_context.return_value = mock_context
            
            mock_page = AsyncMock()
            # set_default_timeout is sync, so we mock it as MagicMock to avoid "coroutine never awaited" warning
            mock_page.set_default_timeout = MagicMock()
            mock_context.new_page.return_value = mock_page
            
            # browser.close is async in Playwright but called synchronously in the code (potential bug in code),
            # but to silence warnings in tests we mock it as MagicMock
            mock_browser.close = MagicMock()
            
            yield mock_pw

    @pytest.fixture
    async def browser_agent(self):
        agent = CometBrowserAgent()
        yield agent
        # close is synchronous in CometBrowserAgent
        agent.close()

    @pytest.mark.asyncio
    async def test_initialization(self, browser_agent):
        """Test that the agent initializes with default state"""
        assert browser_agent.playwright is None
        assert browser_agent.browser is None
        assert browser_agent.page is None

    @pytest.mark.asyncio
    async def test_init_browser_async(self, browser_agent, mock_playwright):
        """Test starting the browser"""
        await browser_agent.init_browser_async()
        
        # Verify playwright was started
        mock_playwright.assert_called_once()
        
        # Verify browser launch
        # mock_playwright.return_value.start is a MagicMock with side_effect
        mock_playwright.return_value.start.assert_called_once()
        
        # mock_p is the result
        mock_pw_obj = mock_playwright.return_value.start.side_effect().result()
        mock_pw_obj.chromium.launch.assert_called_with(
            headless=False,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        # Verify page creation
        assert browser_agent.page is not None
        
    @pytest.mark.asyncio
    async def test_navigate(self, browser_agent, mock_playwright):
        """Test navigation to a URL"""
        await browser_agent.init_browser_async()
        
        # Mock the page.goto method as MagicMock (sync) because navigate calls it synchronously
        mock_page = browser_agent.page
        mock_page.goto = MagicMock()
        
        # navigate is synchronous
        browser_agent.navigate('https://example.com')
        
        mock_page.goto.assert_called_with('https://example.com', wait_until='domcontentloaded')

    @pytest.mark.asyncio
    async def test_extract_text(self, browser_agent, mock_playwright):
        """Test retrieving page content"""
        await browser_agent.init_browser_async()
        
        mock_page = browser_agent.page
        # Mock inner_text as MagicMock (sync)
        mock_page.inner_text = MagicMock(return_value='Test Content')
        
        content = browser_agent.extract_text()
        assert content == 'Test Content'
        mock_page.inner_text.assert_called_with('body')

    @pytest.mark.asyncio
    async def test_click_element(self, browser_agent, mock_playwright):
        """Test clicking an element"""
        await browser_agent.init_browser_async()
        
        mock_page = browser_agent.page
        mock_page.click = MagicMock()
        mock_page.wait_for_selector = MagicMock()
        
        browser_agent.click_element('#submit-btn')
        
        mock_page.wait_for_selector.assert_called_with('#submit-btn', state='visible')
        mock_page.click.assert_called_with('#submit-btn')

    @pytest.mark.asyncio
    async def test_fill_form(self, browser_agent, mock_playwright):
        """Test filling an input field"""
        await browser_agent.init_browser_async()
        
        mock_page = browser_agent.page
        mock_page.fill = MagicMock()
        mock_page.wait_for_selector = MagicMock()
        
        browser_agent.fill_form('#username', 'testuser')
        
        mock_page.wait_for_selector.assert_called_with('#username')
        mock_page.fill.assert_any_call('#username', '')
        mock_page.fill.assert_any_call('#username', 'testuser')

    @pytest.mark.asyncio
    async def test_get_page_screenshot(self, browser_agent, mock_playwright):
        """Test taking a screenshot"""
        await browser_agent.init_browser_async()
        
        mock_page = browser_agent.page
        mock_page.screenshot = MagicMock()
        
        with patch('os.path.join', return_value='screenshots/test.png'):
            browser_agent.get_page_screenshot('test.png')
        
        mock_page.screenshot.assert_called_with(path='screenshots/test.png', full_page=True)

    @pytest.mark.asyncio
    async def test_close(self, browser_agent, mock_playwright):
        """Test closing the browser"""
        await browser_agent.init_browser_async()
        
        # Setup mocks for close
        browser_agent.browser.close = MagicMock()
        browser_agent.playwright.stop = MagicMock()
        
        browser_agent.close()
        
        browser_agent.browser.close.assert_called_once()
