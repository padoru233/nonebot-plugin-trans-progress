from types import SimpleNamespace
from datetime import datetime, timezone


def test_build_catalog_exports_current_progress_and_metadata():
    from nonebot_plugin_trans_progress.public_catalog import build_catalog

    project = SimpleNamespace(
        id=4,
        name="漫画名",
        aliases=["别称"],
        tags=["百合", "连载"],
        cover_url="https://images.zaimanhua.com/webpic/8/example.webp",
        zaimanhua_url="https://manhua.zaimanhua.com/details/84456",
        standalone_episodes=False,
    )
    episodes = [
        SimpleNamespace(
            id=11,
            project_id=4,
            title="第 2 话",
            status=2,
            updated_at=datetime(2026, 10, 11, 1, 0, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            id=10,
            project_id=4,
            title="第 1 话",
            status=5,
            updated_at=datetime(2026, 10, 10, 1, 0, tzinfo=timezone.utc),
        ),
    ]

    catalog = build_catalog(
        [project],
        episodes,
        generated_at=datetime(2026, 10, 11, 2, 0, tzinfo=timezone.utc),
    )

    assert catalog == {
        "generatedAt": "2026-10-11T02:00:00+00:00",
        "items": [
            {
                "id": 4,
                "name": "漫画名",
                "aliases": ["别称"],
                "tags": ["百合", "连载"],
                "coverUrl": "https://images.zaimanhua.com/webpic/8/example.webp",
                "detailUrl": "https://manhua.zaimanhua.com/details/84456",
                "currentEpisode": {
                    "id": 11,
                    "title": "第 2 话",
                    "status": 2,
                    "progress": "校对中",
                    "updatedAt": "2026-10-11T01:00:00+00:00",
                },
                "activeEpisodes": [
                    {
                        "id": 11,
                        "title": "第 2 话",
                        "status": 2,
                        "progress": "校对中",
                        "updatedAt": "2026-10-11T01:00:00+00:00",
                    }
                ],
                "episodeCount": 2,
                "completedEpisodeCount": 1,
                "updatedAt": "2026-10-11T01:00:00+00:00",
            }
        ],
    }


def test_build_catalog_hides_default_project():
    from nonebot_plugin_trans_progress.public_catalog import build_catalog

    def project(project_id: int, name: str):
        return SimpleNamespace(
            id=project_id,
            name=name,
            aliases=[],
            tags=[],
            cover_url=None,
            zaimanhua_url=None,
            standalone_episodes=False,
        )

    catalog = build_catalog(
        [project(1, "default"), project(2, " Default "), project(3, "漫画名")],
        [],
        generated_at=datetime(2026, 10, 11, 2, 0, tzinfo=timezone.utc),
    )

    assert [item["name"] for item in catalog["items"]] == ["漫画名"]


def test_build_catalog_expands_standalone_project_into_episode_cards():
    from nonebot_plugin_trans_progress.public_catalog import build_catalog

    project = SimpleNamespace(
        id=7,
        name="短篇集",
        aliases=["不应出现"],
        tags=["短篇"],
        cover_url="https://images.zaimanhua.com/webpic/1/collection.jpg",
        zaimanhua_url="https://manhua.zaimanhua.com/details/1",
        standalone_episodes=True,
    )
    episodes = [
        SimpleNamespace(
            id=22,
            project_id=7,
            title="第二篇",
            status=5,
            cover_url=None,
            zaimanhua_url=None,
            updated_at=datetime(2026, 10, 11, 1, 0, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            id=21,
            project_id=7,
            title="第一篇",
            status=2,
            cover_url="https://images.zaimanhua.com/webpic/2/one.jpg",
            zaimanhua_url="https://manhua.zaimanhua.com/details/2",
            updated_at=datetime(2026, 10, 10, 1, 0, tzinfo=timezone.utc),
        ),
    ]

    items = build_catalog([project], episodes)["items"]

    assert [item["name"] for item in items] == ["第一篇", "第二篇"]
    first, second = items
    assert first["id"] == "episode-21"
    assert first["aliases"] == ["短篇集"]
    assert first["tags"] == ["短篇"]
    assert first["standalone"] is True
    assert first["coverUrl"] == "https://images.zaimanhua.com/webpic/2/one.jpg"
    assert first["detailUrl"] == "https://manhua.zaimanhua.com/details/2"
    assert first["currentEpisode"]["progress"] == "校对中"
    assert (first["episodeCount"], first["completedEpisodeCount"]) == (1, 0)
    # 作品集自己的封面和链接不会借给没有填写的单话
    assert second["coverUrl"] is None
    assert second["detailUrl"] is None
    assert second["currentEpisode"] is None
    assert (second["episodeCount"], second["completedEpisodeCount"]) == (1, 1)
