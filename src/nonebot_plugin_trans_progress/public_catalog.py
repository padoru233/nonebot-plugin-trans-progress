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

# 萌翻会把未归入作品集的话数同步到 default 作品集，它不是一部真实作品
HIDDEN_PROJECT_NAMES = frozenset({"default"})


def is_hidden_project(project: Any) -> bool:
    return project.name.strip().casefold() in HIDDEN_PROJECT_NAMES


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


def build_standalone_item(project: Any, episode: Any) -> dict[str, Any]:
    """作品集开启“每话作为独立作品展示”时，每一话各自是一张卡片。"""
    is_active = episode.status < 5
    serialized_episode = serialize_episode(episode)
    return {
        "id": f"episode-{episode.id}",
        "name": episode.title,
        "aliases": [project.name],
        "tags": project.tags,
        "coverUrl": episode.cover_url,
        "detailUrl": episode.zaimanhua_url,
        "standalone": True,
        "currentEpisode": serialized_episode if is_active else None,
        "activeEpisodes": [serialized_episode] if is_active else [],
        "episodeCount": 1,
        "completedEpisodeCount": 0 if is_active else 1,
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
        if is_hidden_project(project):
            continue
        project_episodes = episodes_by_project[project.id]
        if project.standalone_episodes:
            items.extend(
                build_standalone_item(project, episode)
                for episode in sorted(project_episodes, key=lambda ep: ep.id)
            )
            continue
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
