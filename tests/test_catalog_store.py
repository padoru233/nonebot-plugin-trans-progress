import json
import asyncio
from pathlib import Path


def test_catalog_store_syncs_only_changed_catalogs(tmp_path, monkeypatch):
    import nonebot

    nonebot.init()

    from nonebot_plugin_trans_progress import catalog_store

    catalog_path = Path(tmp_path) / "catalog.json"
    catalogs = iter(
        [
            {"generatedAt": "2026-10-11T03:00:00+00:00", "items": [{"name": "A"}]},
            {"generatedAt": "2026-10-11T03:01:00+00:00", "items": [{"name": "A"}]},
            {"generatedAt": "2026-10-11T03:02:00+00:00", "items": [{"name": "B"}]},
        ]
    )
    synchronized_catalogs = []

    async def get_catalog():
        return next(catalogs)

    async def sync_catalog(serialized_catalog: str, item_count: int = 0):
        synchronized_catalogs.append(json.loads(serialized_catalog))

    monkeypatch.setattr(catalog_store, "get_catalog_path", lambda: catalog_path)
    monkeypatch.setattr(catalog_store, "get_public_catalog", get_catalog)
    monkeypatch.setattr(catalog_store, "sync_public_catalog", sync_catalog)

    async def generate_catalogs():
        await catalog_store.generate_public_catalog()
        await catalog_store.generate_public_catalog()
        await catalog_store.generate_public_catalog()

    asyncio.run(generate_catalogs())

    assert synchronized_catalogs == [
        {"generatedAt": "2026-10-11T03:00:00+00:00", "items": [{"name": "A"}]},
        {"generatedAt": "2026-10-11T03:02:00+00:00", "items": [{"name": "B"}]},
    ]
    assert json.loads(catalog_path.read_text(encoding="utf-8")) == (
        synchronized_catalogs[-1]
    )


def test_force_sync_sends_fresh_snapshot_when_items_unchanged(tmp_path, monkeypatch):
    import nonebot

    nonebot.init()

    from nonebot_plugin_trans_progress import catalog_store

    catalog_path = Path(tmp_path) / "catalog.json"
    catalogs = iter(
        [
            {"generatedAt": "2026-10-11T03:00:00+00:00", "items": [{"name": "A"}]},
            {"generatedAt": "2026-10-11T04:00:00+00:00", "items": [{"name": "A"}]},
        ]
    )
    synchronized_catalogs = []

    async def get_catalog():
        return next(catalogs)

    async def sync_catalog(serialized_catalog: str, item_count: int = 0):
        synchronized_catalogs.append((json.loads(serialized_catalog), item_count))

    monkeypatch.setattr(catalog_store, "get_catalog_path", lambda: catalog_path)
    monkeypatch.setattr(catalog_store, "get_public_catalog", get_catalog)
    monkeypatch.setattr(catalog_store, "sync_public_catalog", sync_catalog)

    async def generate_catalogs():
        await catalog_store.generate_public_catalog()
        await catalog_store.generate_public_catalog(force_sync=True)

    asyncio.run(generate_catalogs())

    assert [catalog["generatedAt"] for catalog, _ in synchronized_catalogs] == [
        "2026-10-11T03:00:00+00:00",
        "2026-10-11T04:00:00+00:00",
    ]
    assert synchronized_catalogs[-1][1] == 1
    assert json.loads(catalog_path.read_text(encoding="utf-8"))["generatedAt"] == (
        "2026-10-11T04:00:00+00:00"
    )
