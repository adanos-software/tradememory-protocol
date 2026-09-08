"""Regression tests for GitHub issue #13: SPA catch-all path containment.

The dashboard catch-all in ``server.py`` used to check containment with
``str(path).startswith(str(dist_root))``, which has no component
boundary: a sibling directory ``<dist>-x/`` shares the string prefix and
slipped through. The check is now ``Path.is_relative_to``.

The helper ``_resolve_static_file`` is tested directly (it exists whether
or not ``dashboard/dist`` was built), and the HTTP route is tested when
it was registered at import time (only when the dist folder exists).
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from tradememory import server


@pytest.fixture
def dist_tree(tmp_path):
    """<tmp>/dist with index.html + vite.svg, plus a sibling <tmp>/dist-x."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>spa</html>", encoding="utf-8")
    (dist / "vite.svg").write_text("<svg/>", encoding="utf-8")
    (dist / "assets").mkdir()
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")

    sibling = tmp_path / "dist-x"
    sibling.mkdir()
    (sibling / "secret.txt").write_text("leaked", encoding="utf-8")

    (tmp_path / "outside.txt").write_text("outside", encoding="utf-8")
    return dist


# ---------------------------------------------------------------------------
# Unit: _resolve_static_file
# ---------------------------------------------------------------------------

def test_real_file_under_dist_resolves(dist_tree):
    resolved = server._resolve_static_file("vite.svg", dist_tree)
    assert resolved == (dist_tree / "vite.svg").resolve()


def test_nested_real_file_resolves(dist_tree):
    resolved = server._resolve_static_file("assets/app.js", dist_tree)
    assert resolved == (dist_tree / "assets" / "app.js").resolve()


def test_missing_file_inside_dist_falls_back_to_none(dist_tree):
    # SPA client-side route: not a file, not an escape -> caller serves index.html
    assert server._resolve_static_file("trades/123", dist_tree) is None


def test_empty_path_is_none(dist_tree):
    assert server._resolve_static_file("", dist_tree) is None


def test_directory_itself_is_none(dist_tree):
    assert server._resolve_static_file("assets", dist_tree) is None


def test_sibling_prefix_directory_is_rejected(dist_tree):
    """The #13 case: '<dist>-x/secret.txt' shares the string prefix of dist."""
    with pytest.raises(HTTPException) as exc:
        server._resolve_static_file("../dist-x/secret.txt", dist_tree)
    assert exc.value.status_code == 404


def test_dotdot_traversal_is_rejected(dist_tree):
    with pytest.raises(HTTPException) as exc:
        server._resolve_static_file("../outside.txt", dist_tree)
    assert exc.value.status_code == 404


def test_deep_dotdot_traversal_is_rejected(dist_tree):
    with pytest.raises(HTTPException) as exc:
        server._resolve_static_file("assets/../../outside.txt", dist_tree)
    assert exc.value.status_code == 404


def test_absolute_path_is_rejected(dist_tree, tmp_path):
    outside = str((tmp_path / "outside.txt").resolve())
    with pytest.raises(HTTPException) as exc:
        server._resolve_static_file(outside, dist_tree)
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Integration: the catch-all route (registered only if dashboard/dist exists)
# ---------------------------------------------------------------------------

_spa_registered = any(
    getattr(r, "name", "") == "_serve_spa" for r in server.app.routes
)


@pytest.fixture
def spa_client(dist_tree, monkeypatch):
    if not _spa_registered:
        pytest.skip("dashboard/dist not built; SPA catch-all route not registered")
    monkeypatch.setattr(server, "_dashboard_dist", dist_tree)
    return TestClient(server.app)


def test_route_serves_real_file(spa_client):
    r = spa_client.get("/vite.svg")
    assert r.status_code == 200
    assert r.text == "<svg/>"


def test_route_serves_index_for_client_side_path(spa_client):
    r = spa_client.get("/some/client/route")
    assert r.status_code == 200
    assert "spa" in r.text


def test_route_rejects_sibling_prefix_directory(spa_client):
    # Encoded so the HTTP client does not normalise the dot segments away.
    r = spa_client.get("/..%2Fdist-x%2Fsecret.txt")
    assert r.status_code == 404
    assert "leaked" not in r.text


def test_route_rejects_dotdot_traversal(spa_client):
    r = spa_client.get("/..%2Foutside.txt")
    assert r.status_code == 404
    assert "outside" not in r.text
