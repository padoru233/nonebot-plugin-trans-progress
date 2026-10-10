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
