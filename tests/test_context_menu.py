from pathlib import Path
from fastapi.testclient import TestClient
from bookledger.core import connect
from bookledger.legacy_webapp import create_app


def test_context_menu_asset_and_layout(tmp_path):
    path = tmp_path / 'test.db'
    with connect(path):
        pass
    client = TestClient(create_app(path))
    page = client.get('/')
    assert page.status_code == 200
    assert '/context-menu.js' in page.text
    asset = client.get('/context-menu.js')
    assert asset.status_code == 200
    assert 'javascript' in asset.headers['content-type']
    assert 'contextmenu' in asset.text
    assert 'pointerdown' in asset.text
    assert 'Shift' not in asset.text or 'F10' in asset.text
    assert "case 'stats':" in asset.text
