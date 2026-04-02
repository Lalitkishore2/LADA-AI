"""
LADA - Plugin Marketplace
ClawHub-style plugin discovery, installation, and update system.

Supports both a local index file and an optional remote index URL.
Integrates with the existing PluginRegistry for plugin lifecycle.
"""

import os
import json
import shutil
import logging
import zipfile
import tempfile
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Try to import aiohttp for async HTTP downloads
try:
    import aiohttp
    AIOHTTP_OK = True
except ImportError:
    AIOHTTP_OK = False

# Try to import requests as fallback
try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

# Import plugin registry
from modules.plugin_system import get_plugin_registry


PLUGIN_INDEX_URL = os.getenv('PLUGIN_INDEX_URL', '')
LOCAL_INDEX_FILE = Path(os.getenv('PLUGIN_INDEX_FILE', 'plugins/marketplace_index.json'))


@dataclass
class MarketplacePlugin:
    """Represents a plugin available in the marketplace."""
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    download_url: str = ""
    keywords: List[str] = field(default_factory=list)
    category: str = "general"
    size: int = 0
    downloads: int = 0
    rating: float = 0.0
    updated_at: str = ""
    min_lada_version: str = ""
    dependencies: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MarketplacePlugin':
        """Create a MarketplacePlugin from a dictionary."""
        return cls(
            name=data.get('name', 'unnamed'),
            version=data.get('version', '1.0.0'),
            description=data.get('description', ''),
            author=data.get('author', ''),
            download_url=data.get('download_url', ''),
            keywords=data.get('keywords', []),
            category=data.get('category', 'general'),
            size=data.get('size', 0),
            downloads=data.get('downloads', 0),
            rating=data.get('rating', 0.0),
            updated_at=data.get('updated_at', ''),
            min_lada_version=data.get('min_lada_version', ''),
            dependencies=data.get('dependencies', []),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            'name': self.name,
            'version': self.version,
            'description': self.description,
            'author': self.author,
            'download_url': self.download_url,
            'keywords': self.keywords,
            'category': self.category,
            'size': self.size,
            'downloads': self.downloads,
            'rating': self.rating,
            'updated_at': self.updated_at,
            'min_lada_version': self.min_lada_version,
            'dependencies': self.dependencies,
        }


class PluginMarketplace:
    """
    Plugin marketplace for discovering, installing, and updating plugins.

    Usage:
        marketplace = get_marketplace()
        available = marketplace.list_available()
        marketplace.install('weather')
        marketplace.uninstall('weather')
        updates = marketplace.check_updates()
    """

    def __init__(self):
        self._registry = get_plugin_registry()
        self._index: List[MarketplacePlugin] = []
        self._last_refresh: Optional[datetime] = None
        self._cache_ttl = 300  # 5 minutes
        self._plugins_dir = self._registry.plugins_dir
        self._load_local_index()

    def _load_local_index(self):
        """Load the local marketplace index file."""
        index_path = LOCAL_INDEX_FILE
        # If the path is relative, resolve it from the project root
        if not index_path.is_absolute():
            project_root = Path(os.path.dirname(os.path.dirname(__file__)))
            index_path = project_root / index_path

        if not index_path.exists():
            logger.info(f"[Marketplace] No local index found at {index_path}")
            return

        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            plugins_data = data.get('plugins', [])
            self._index = [MarketplacePlugin.from_dict(p) for p in plugins_data]
            logger.info(f"[Marketplace] Loaded local index: {len(self._index)} plugins")
        except Exception as e:
            logger.error(f"[Marketplace] Failed to load local index: {e}")

    def _save_local_index(self):
        """Save the current index to local file."""
        index_path = LOCAL_INDEX_FILE
        if not index_path.is_absolute():
            project_root = Path(os.path.dirname(os.path.dirname(__file__)))
            index_path = project_root / index_path

        # Ensure parent directory exists
        index_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            data = {
                'version': '1.0.0',
                'updated_at': datetime.now().strftime('%Y-%m-%d'),
                'plugins': [p.to_dict() for p in self._index],
            }
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"[Marketplace] Saved local index: {len(self._index)} plugins")
        except Exception as e:
            logger.error(f"[Marketplace] Failed to save local index: {e}")

    async def refresh_index(self) -> int:
        """Fetch the latest index from remote URL if configured.
        Returns count of available plugins."""
        if not PLUGIN_INDEX_URL:
            logger.info("[Marketplace] No remote index URL configured, using local index only")
            return len(self._index)

        remote_data = None

        # Try aiohttp first for true async
        if AIOHTTP_OK:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(PLUGIN_INDEX_URL, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        if resp.status == 200:
                            remote_data = await resp.json()
                            logger.info("[Marketplace] Fetched remote index via aiohttp")
                        else:
                            logger.warning(f"[Marketplace] Remote index returned HTTP {resp.status}")
            except Exception as e:
                logger.warning(f"[Marketplace] aiohttp fetch failed: {e}")

        # Fall back to requests (synchronous but called from async context)
        if remote_data is None and REQUESTS_OK:
            try:
                resp = requests.get(PLUGIN_INDEX_URL, timeout=30)
                if resp.status_code == 200:
                    remote_data = resp.json()
                    logger.info("[Marketplace] Fetched remote index via requests")
                else:
                    logger.warning(f"[Marketplace] Remote index returned HTTP {resp.status_code}")
            except Exception as e:
                logger.warning(f"[Marketplace] requests fetch failed: {e}")

        if remote_data is None:
            logger.warning("[Marketplace] Could not fetch remote index, keeping local index")
            return len(self._index)

        # Parse remote plugins
        remote_plugins_data = remote_data.get('plugins', [])
        remote_plugins = [MarketplacePlugin.from_dict(p) for p in remote_plugins_data]

        # Merge: remote takes precedence for same-name plugins
        local_by_name = {p.name: p for p in self._index}
        remote_by_name = {p.name: p for p in remote_plugins}

        # Start with all local plugins
        merged = dict(local_by_name)
        # Override/add with remote plugins
        merged.update(remote_by_name)

        self._index = list(merged.values())
        self._last_refresh = datetime.now()

        # Persist the merged index locally
        self._save_local_index()

        logger.info(f"[Marketplace] Index refreshed: {len(self._index)} plugins available")
        return len(self._index)

    def list_available(self, category: str = None, search: str = None) -> List[Dict[str, Any]]:
        """List available plugins, optionally filtered by category or search term.
        Returns list of dicts with plugin info + 'installed' boolean."""
        results = []
        installed_names = set(self._registry.plugins.keys())

        for plugin in self._index:
            # Filter by category if specified
            if category and plugin.category.lower() != category.lower():
                continue

            # Filter by search term if specified (match against name, description, keywords)
            if search:
                search_lower = search.lower()
                searchable = (
                    plugin.name.lower() + ' ' +
                    plugin.description.lower() + ' ' +
                    ' '.join(kw.lower() for kw in plugin.keywords)
                )
                if search_lower not in searchable:
                    continue

            info = plugin.to_dict()
            info['installed'] = plugin.name in installed_names
            results.append(info)

        return results

    def get_plugin_info(self, name: str) -> Optional[Dict[str, Any]]:
        """Get detailed info about a marketplace plugin."""
        for plugin in self._index:
            if plugin.name == name:
                info = plugin.to_dict()
                info['installed'] = name in self._registry.plugins
                # If installed, augment with runtime state
                if info['installed']:
                    loaded = self._registry.plugins[name]
                    info['state'] = loaded.state.value
                    info['installed_version'] = loaded.manifest.version
                    info['has_update'] = self._version_gt(plugin.version, loaded.manifest.version)
                return info
        return None

    def install(self, name: str) -> Dict[str, Any]:
        """Install a plugin from the marketplace.
        Returns dict with 'success', 'message', 'plugin_name'."""
        # Check if already installed
        if name in self._registry.plugins:
            return {
                'success': False,
                'message': f"Plugin '{name}' is already installed. Use update_plugin() to upgrade.",
                'plugin_name': name,
            }

        # Find plugin in index
        marketplace_entry = None
        for p in self._index:
            if p.name == name:
                marketplace_entry = p
                break

        if marketplace_entry is None:
            return {
                'success': False,
                'message': f"Plugin '{name}' not found in marketplace index.",
                'plugin_name': name,
            }

        plugin_dest = self._plugins_dir / name

        # If plugin has a download URL, download and extract
        if marketplace_entry.download_url:
            try:
                success = self._download_plugin(marketplace_entry.download_url, plugin_dest)
                if not success:
                    return {
                        'success': False,
                        'message': f"Failed to download plugin '{name}' from {marketplace_entry.download_url}.",
                        'plugin_name': name,
                    }
            except Exception as e:
                # Clean up partial download
                if plugin_dest.exists():
                    shutil.rmtree(plugin_dest, ignore_errors=True)
                return {
                    'success': False,
                    'message': f"Error downloading plugin '{name}': {e}",
                    'plugin_name': name,
                }
        else:
            # No download URL: create a scaffold directory with a manifest
            try:
                plugin_dest.mkdir(parents=True, exist_ok=True)

                # Create a plugin.json manifest
                manifest_data = {
                    'name': marketplace_entry.name,
                    'version': marketplace_entry.version,
                    'description': marketplace_entry.description,
                    'author': marketplace_entry.author,
                    'entry_point': 'main.py',
                    'class_name': '',
                    'capabilities': [],
                    'dependencies': marketplace_entry.dependencies,
                    'permissions': [],
                    'min_lada_version': marketplace_entry.min_lada_version,
                    'enabled': True,
                }
                manifest_path = plugin_dest / 'plugin.json'
                with open(manifest_path, 'w', encoding='utf-8') as f:
                    json.dump(manifest_data, f, indent=2, ensure_ascii=False)

                # Create a minimal main.py entry point
                main_path = plugin_dest / 'main.py'
                if not main_path.exists():
                    with open(main_path, 'w', encoding='utf-8') as f:
                        f.write(f'"""\nLADA Plugin: {marketplace_entry.name}\n'
                                f'{marketplace_entry.description}\n"""\n\n'
                                f'class {_to_class_name(marketplace_entry.name)}Plugin:\n'
                                f'    """Plugin implementation for {marketplace_entry.name}."""\n\n'
                                f'    def on_load(self):\n'
                                f'        pass\n\n'
                                f'    def on_activate(self):\n'
                                f'        pass\n\n'
                                f'    def on_deactivate(self):\n'
                                f'        pass\n\n'
                                f'    def on_unload(self):\n'
                                f'        pass\n')

                logger.info(f"[Marketplace] Created scaffold for plugin '{name}'")
            except Exception as e:
                if plugin_dest.exists():
                    shutil.rmtree(plugin_dest, ignore_errors=True)
                return {
                    'success': False,
                    'message': f"Error creating plugin scaffold for '{name}': {e}",
                    'plugin_name': name,
                }

        # Discover, load, and activate via the registry
        try:
            self._registry.discover_plugins()
            loaded = self._registry.load_plugin(name)
            if loaded:
                self._registry.activate_plugin(name)
                logger.info(f"[Marketplace] Installed and activated plugin '{name}'")
                return {
                    'success': True,
                    'message': f"Plugin '{name}' v{marketplace_entry.version} installed and activated successfully.",
                    'plugin_name': name,
                }
            else:
                # Plugin directory exists but load failed -- still counts as installed on disk
                error_msg = ''
                if name in self._registry.plugins and self._registry.plugins[name].error:
                    error_msg = f" Error: {self._registry.plugins[name].error}"
                logger.warning(f"[Marketplace] Plugin '{name}' installed but failed to load.{error_msg}")
                return {
                    'success': True,
                    'message': (f"Plugin '{name}' installed on disk but could not be loaded/activated."
                                f"{error_msg} You may need to install its dependencies."),
                    'plugin_name': name,
                }
        except Exception as e:
            logger.error(f"[Marketplace] Error during post-install activation of '{name}': {e}")
            return {
                'success': True,
                'message': f"Plugin '{name}' installed on disk but activation failed: {e}",
                'plugin_name': name,
            }

    def _download_plugin(self, url: str, dest_dir: Path) -> bool:
        """Download and extract a plugin zip from URL.
        Returns True on success."""
        if not REQUESTS_OK and not AIOHTTP_OK:
            logger.error("[Marketplace] No HTTP library available (install requests or aiohttp)")
            return False

        tmp_fd = None
        tmp_path = None
        try:
            # Download to a temporary file
            tmp_fd, tmp_path = tempfile.mkstemp(suffix='.zip', prefix='lada_plugin_')
            os.close(tmp_fd)
            tmp_fd = None

            if REQUESTS_OK:
                resp = requests.get(url, timeout=60, stream=True)
                if resp.status_code != 200:
                    logger.error(f"[Marketplace] Download failed: HTTP {resp.status_code}")
                    return False
                with open(tmp_path, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
            else:
                # aiohttp is async-only; use a basic urllib fallback for sync download
                import urllib.request
                urllib.request.urlretrieve(url, tmp_path)

            # Verify it is a valid zip
            if not zipfile.is_zipfile(tmp_path):
                logger.error("[Marketplace] Downloaded file is not a valid zip archive")
                return False

            # Extract to a temporary directory first for validation
            with tempfile.TemporaryDirectory(prefix='lada_plugin_extract_') as extract_dir:
                with zipfile.ZipFile(tmp_path, 'r') as zf:
                    # Security: check for path traversal
                    for member in zf.namelist():
                        member_path = Path(extract_dir) / member
                        resolved = member_path.resolve()
                        if not str(resolved).startswith(str(Path(extract_dir).resolve())):
                            logger.error(f"[Marketplace] Zip contains unsafe path: {member}")
                            return False
                    zf.extractall(extract_dir)

                # The zip might contain a single top-level directory or files directly
                extract_path = Path(extract_dir)
                contents = list(extract_path.iterdir())

                # If there is exactly one directory at the top level, treat it as the plugin root
                if len(contents) == 1 and contents[0].is_dir():
                    source_dir = contents[0]
                else:
                    source_dir = extract_path

                # Validate: must contain a manifest file
                has_manifest = any(
                    (source_dir / mf).exists()
                    for mf in ('plugin.yaml', 'plugin.yml', 'plugin.json', 'SKILL.md')
                )
                if not has_manifest:
                    has_manifest = any(source_dir.glob('*.skill.md'))
                if not has_manifest:
                    logger.error("[Marketplace] Downloaded plugin has no manifest (plugin.yaml/json or SKILL.md)")
                    return False

                # Move to destination
                if dest_dir.exists():
                    shutil.rmtree(dest_dir)
                shutil.copytree(str(source_dir), str(dest_dir))

            logger.info(f"[Marketplace] Downloaded and extracted plugin to {dest_dir}")
            return True

        except Exception as e:
            logger.error(f"[Marketplace] Download/extract error: {e}")
            return False
        finally:
            # Clean up temp file
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def uninstall(self, name: str) -> Dict[str, Any]:
        """Uninstall a plugin by removing its directory.
        Returns dict with 'success', 'message'."""
        plugin_dir = self._plugins_dir / name

        # Deactivate and unload via registry if loaded
        if name in self._registry.plugins:
            try:
                self._registry.deactivate_plugin(name)
            except Exception as e:
                logger.warning(f"[Marketplace] Deactivation warning for '{name}': {e}")

            try:
                self._registry.unload_plugin(name)
            except Exception as e:
                logger.warning(f"[Marketplace] Unload warning for '{name}': {e}")

            # Remove from registry tracking
            del self._registry.plugins[name]

        # Remove the plugin directory from disk
        if plugin_dir.exists():
            try:
                shutil.rmtree(str(plugin_dir))
                logger.info(f"[Marketplace] Removed plugin directory: {plugin_dir}")
            except Exception as e:
                return {
                    'success': False,
                    'message': f"Failed to remove plugin directory '{plugin_dir}': {e}",
                }
        else:
            return {
                'success': False,
                'message': f"Plugin '{name}' directory not found at {plugin_dir}.",
            }

        logger.info(f"[Marketplace] Uninstalled plugin '{name}'")
        return {
            'success': True,
            'message': f"Plugin '{name}' has been uninstalled.",
        }

    def check_updates(self) -> List[Dict[str, Any]]:
        """Check for available updates by comparing installed vs index versions.
        Returns list of {name, current_version, available_version}."""
        updates = []

        for marketplace_plugin in self._index:
            name = marketplace_plugin.name
            if name not in self._registry.plugins:
                continue

            installed = self._registry.plugins[name]
            installed_version = installed.manifest.version
            available_version = marketplace_plugin.version

            if self._version_gt(available_version, installed_version):
                updates.append({
                    'name': name,
                    'current_version': installed_version,
                    'available_version': available_version,
                    'description': marketplace_plugin.description,
                })

        return updates

    def update_plugin(self, name: str) -> Dict[str, Any]:
        """Update a plugin to the latest version."""
        # Verify it is installed
        if name not in self._registry.plugins:
            return {
                'success': False,
                'message': f"Plugin '{name}' is not installed.",
                'plugin_name': name,
            }

        # Verify an update is available
        marketplace_entry = None
        for p in self._index:
            if p.name == name:
                marketplace_entry = p
                break

        if marketplace_entry is None:
            return {
                'success': False,
                'message': f"Plugin '{name}' not found in marketplace index.",
                'plugin_name': name,
            }

        installed_version = self._registry.plugins[name].manifest.version
        if not self._version_gt(marketplace_entry.version, installed_version):
            return {
                'success': False,
                'message': (f"Plugin '{name}' is already at version {installed_version} "
                            f"(marketplace has {marketplace_entry.version}). No update needed."),
                'plugin_name': name,
            }

        # Uninstall the old version
        uninstall_result = self.uninstall(name)
        if not uninstall_result['success']:
            return {
                'success': False,
                'message': f"Could not uninstall old version of '{name}': {uninstall_result['message']}",
                'plugin_name': name,
            }

        # Install the new version
        install_result = self.install(name)
        if install_result['success']:
            install_result['message'] = (
                f"Plugin '{name}' updated from v{installed_version} to v{marketplace_entry.version}."
            )
        return install_result

    def add_to_index(self, plugin_info: Dict[str, Any]) -> bool:
        """Add/update a plugin entry in the local index (for plugin developers)."""
        if 'name' not in plugin_info:
            logger.error("[Marketplace] Cannot add plugin to index: missing 'name'")
            return False

        new_plugin = MarketplacePlugin.from_dict(plugin_info)

        # Check if plugin already exists in index -- replace it
        for i, existing in enumerate(self._index):
            if existing.name == new_plugin.name:
                self._index[i] = new_plugin
                self._save_local_index()
                logger.info(f"[Marketplace] Updated index entry for '{new_plugin.name}'")
                return True

        # Otherwise, add as new entry
        self._index.append(new_plugin)
        self._save_local_index()
        logger.info(f"[Marketplace] Added new index entry for '{new_plugin.name}'")
        return True

    def remove_from_index(self, name: str) -> bool:
        """Remove a plugin entry from the local index."""
        original_len = len(self._index)
        self._index = [p for p in self._index if p.name != name]

        if len(self._index) < original_len:
            self._save_local_index()
            logger.info(f"[Marketplace] Removed '{name}' from index")
            return True

        logger.warning(f"[Marketplace] Plugin '{name}' not found in index")
        return False

    def get_categories(self) -> List[str]:
        """Get list of unique plugin categories."""
        categories = set()
        for plugin in self._index:
            if plugin.category:
                categories.add(plugin.category)
        return sorted(categories)

    def get_stats(self) -> Dict[str, Any]:
        """Get marketplace statistics."""
        installed_names = set(self._registry.plugins.keys())
        index_names = {p.name for p in self._index}

        return {
            'total_available': len(self._index),
            'total_installed': len(installed_names & index_names),
            'total_installed_all': len(installed_names),
            'categories': self.get_categories(),
            'last_refresh': self._last_refresh.isoformat() if self._last_refresh else None,
            'remote_url_configured': bool(PLUGIN_INDEX_URL),
            'index_file': str(LOCAL_INDEX_FILE),
        }

    @staticmethod
    def _version_gt(version_a: str, version_b: str) -> bool:
        """Check if version_a is greater than version_b using semantic versioning.
        Handles versions like '1.0.0', '1.2', '2', etc."""
        def parse_version(v: str) -> List[int]:
            parts = []
            for part in v.strip().split('.'):
                try:
                    parts.append(int(part))
                except ValueError:
                    parts.append(0)
            # Pad to at least 3 components
            while len(parts) < 3:
                parts.append(0)
            return parts

        try:
            a_parts = parse_version(version_a)
            b_parts = parse_version(version_b)
            return a_parts > b_parts
        except Exception:
            # Fallback: simple string comparison
            return version_a > version_b


def _to_class_name(plugin_name: str) -> str:
    """Convert a plugin name like 'my_plugin' to a class name like 'MyPlugin'."""
    return ''.join(word.capitalize() for word in plugin_name.replace('-', '_').split('_'))


# Singleton
_marketplace: Optional[PluginMarketplace] = None


def get_marketplace() -> PluginMarketplace:
    """Get or create the global marketplace instance."""
    global _marketplace
    if _marketplace is None:
        _marketplace = PluginMarketplace()
    return _marketplace
