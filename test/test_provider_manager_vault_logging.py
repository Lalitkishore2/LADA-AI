import logging
import os
import threading
from unittest.mock import Mock, patch


def test_vault_fallback_info_emitted_once_for_unconfigured_vault(caplog):
    with patch('modules.providers.provider_manager.get_model_registry', return_value=None):
        with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
            with patch('modules.providers.provider_manager.SECURE_VAULT_OK', True):
                with patch('modules.providers.provider_manager.get_secure_vault') as mock_get_vault:
                    vault = Mock()
                    vault.get.side_effect = ValueError(
                        'Master key not found. Set LADA_MASTER_KEY environment variable'
                    )
                    mock_get_vault.return_value = vault

                    from modules.providers.provider_manager import ProviderManager

                    manager = ProviderManager()

                    with patch.dict(os.environ, {'KEY_ONE': 'one', 'KEY_TWO': 'two'}, clear=False):
                        with caplog.at_level(logging.INFO):
                            value_one = manager._get_secret_from_vault_or_env('KEY_ONE')
                            value_two = manager._get_secret_from_vault_or_env('KEY_TWO')

                    info_records = [
                        rec for rec in caplog.records
                        if rec.levelno == logging.INFO and 'Secure vault unavailable' in rec.message
                    ]
                    warning_records = [
                        rec for rec in caplog.records
                        if rec.levelno == logging.WARNING and 'Secure vault unavailable' in rec.message
                    ]

                    assert value_one == 'one'
                    assert value_two == 'two'
                    assert len(info_records) == 1
                    assert len(warning_records) == 0


def test_vault_fallback_warning_emitted_once_for_unexpected_error(caplog):
    with patch('modules.providers.provider_manager.get_model_registry', return_value=None):
        with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
            with patch('modules.providers.provider_manager.SECURE_VAULT_OK', True):
                with patch('modules.providers.provider_manager.get_secure_vault') as mock_get_vault:
                    vault = Mock()
                    vault.get.side_effect = RuntimeError('vault backend unreachable')
                    mock_get_vault.return_value = vault

                    from modules.providers.provider_manager import ProviderManager

                    manager = ProviderManager()

                    with patch.dict(os.environ, {'KEY_ONE': 'one', 'KEY_TWO': 'two'}, clear=False):
                        with caplog.at_level(logging.WARNING):
                            value_one = manager._get_secret_from_vault_or_env('KEY_ONE')
                            value_two = manager._get_secret_from_vault_or_env('KEY_TWO')

                    warning_records = [
                        rec for rec in caplog.records
                        if rec.levelno == logging.WARNING and 'Secure vault unavailable' in rec.message
                    ]

                    assert value_one == 'one'
                    assert value_two == 'two'
                    assert len(warning_records) == 1


def test_vault_fallback_warning_emitted_once(caplog):
    """Backward-compat: non-ValueError with 'master key missing' still treated as unconfigured."""
    with patch('modules.providers.provider_manager.get_model_registry', return_value=None):
        with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
            with patch('modules.providers.provider_manager.SECURE_VAULT_OK', True):
                with patch('modules.providers.provider_manager.get_secure_vault') as mock_get_vault:
                    vault = Mock()
                    vault.get.side_effect = RuntimeError('master key missing')
                    mock_get_vault.return_value = vault

                    from modules.providers.provider_manager import ProviderManager

                    manager = ProviderManager()

                    with patch.dict(os.environ, {'KEY_ONE': 'one', 'KEY_TWO': 'two'}, clear=False):
                        with caplog.at_level(logging.INFO):
                            value_one = manager._get_secret_from_vault_or_env('KEY_ONE')
                            value_two = manager._get_secret_from_vault_or_env('KEY_TWO')

                    info_records = [
                        rec for rec in caplog.records
                        if rec.levelno == logging.INFO and 'Secure vault unavailable' in rec.message
                    ]

                    assert value_one == 'one'
                    assert value_two == 'two'
                    assert len(info_records) == 1


def test_vault_fallback_logging_threadsafe_once(caplog):
    with patch('modules.providers.provider_manager.get_model_registry', return_value=None):
        with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
            with patch('modules.providers.provider_manager.SECURE_VAULT_OK', True):
                with patch('modules.providers.provider_manager.get_secure_vault') as mock_get_vault:
                    vault = Mock()
                    vault.get.side_effect = RuntimeError('vault backend unreachable')
                    mock_get_vault.return_value = vault

                    from modules.providers.provider_manager import ProviderManager

                    manager = ProviderManager()

                    barrier = threading.Barrier(8)

                    def _worker():
                        barrier.wait()
                        manager._get_secret_from_vault_or_env('KEY_ONE')

                    with patch.dict(os.environ, {'KEY_ONE': 'one'}, clear=False):
                        with caplog.at_level(logging.WARNING):
                            threads = [threading.Thread(target=_worker) for _ in range(8)]
                            for thread in threads:
                                thread.start()
                            for thread in threads:
                                thread.join()

                    warning_records = [
                        rec for rec in caplog.records
                        if rec.levelno == logging.WARNING and 'Secure vault unavailable' in rec.message
                    ]

                    assert len(warning_records) == 1
