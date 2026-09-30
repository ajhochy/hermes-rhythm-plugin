"""Explicit backend plugin reconciliation through the running gateway."""

from unittest.mock import patch

from tui_gateway import server


def test_plugins_manage_reconcile_disposes_removed_and_returns_fresh_inventory():
    with patch('hermes_cli.plugins.get_plugin_manager') as manager, patch(
        'hermes_cli.plugins_cmd._discover_all_plugins', return_value=[]
    ):
        manager.return_value.reconcile_removed_plugins.return_value = ['removed-plugin']
        response = server.handle_request({
            'id': 'reconcile-1', 'method': 'plugins.manage',
            'params': {'action': 'reconcile'},
        })

    assert response['result']['removed'] == ['removed-plugin']
    assert response['result']['plugins'] == []
    manager.return_value.reconcile_removed_plugins.assert_called_once_with()
