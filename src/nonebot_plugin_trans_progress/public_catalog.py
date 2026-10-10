from typing import Any
from datetime import datetime, timezone
from collections import defaultdict
from collections.abc import Iterable

from .models import Episode, Project

STATUS_LABELS = {
    0: "未开始",
    1: "翻译中",
    2: "校对中",
    3: "嵌字中",
    4: "监修中",
    5: "已完结",
}


def format_timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def serialize_episode(episode: Any) -> dict[str, Any]:
    return {
        "id": episode.id,
        "title": episode.title,
        "status": episode.status,
        "progress": STATUS_LABELS.get(episode.status, "未知"),
        "updatedAt": format_timestamp(episode.updated_at),
    }


def build_catalog(
    projects: Iterable[Any],
    episodes: Iterable[Any],
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    episodes_by_project: dict[int, list[Any]] = defaultdict(list)
    for episode in episodes:
        episodes_by_project[episode.project_id].append(episode)

    items = []
    for project in projects:
        project_episodes = episodes_by_project[project.id]
        active_episodes = [
            episode for episode in project_episodes if episode.status < 5
        ]
        current_episode = min(
            active_episodes,
            key=lambda episode: episode.id,
            default=None,
        )
        latest_updated_at = max(
            (episode.updated_at for episode in project_episodes if episode.updated_at),
            default=None,
        )
        items.append(
            {
                "id": project.id,
                "name": project.name,
                "aliases": project.aliases,
                "tags": project.tags,
                "coverUrl": project.cover_url,
                "detailUrl": project.zaimanhua_url,
                "currentEpisode": (
                    serialize_episode(current_episode) if current_episode else None
                ),
                "activeEpisodes": [
                    serialize_episode(episode)
                    for episode in sorted(
                        active_episodes,
                        key=lambda episode: episode.id,
                    )
                ],
                "episodeCount": len(project_episodes),
                "completedEpisodeCount": sum(
                    episode.status == 5 for episode in project_episodes
                ),
                "updatedAt": format_timestamp(latest_updated_at),
            }
        )

    timestamp = generated_at or datetime.now(timezone.utc)
    return {
        "generatedAt": timestamp.isoformat(),
        "items": items,
    }


async def get_public_catalog() -> dict[str, Any]:
    projects = await Project.all().order_by("id")
    episodes = await Episode.all().order_by("id")
    return build_catalog(projects, episodes)
