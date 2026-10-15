import asyncio
from types import SimpleNamespace
from datetime import datetime, timedelta

import pytest


class FakeEpisode:
    def __init__(self):
        self.id = 1
        self.project = SimpleNamespace(name="作品", auto_schedule=True, leader=None)
        self.project.fetch_related = self.fetch_project_related
        self.title = "第 1 话"
        self.status = 1
        self.needs_proofreading = True
        self.translator = SimpleNamespace(qq_id="1", name="翻译")
        self.proofreader = None
        self.typesetter = SimpleNamespace(qq_id="3", name="嵌字")
        self.supervisor = None
        self.ddl_trans = None
        self.ddl_proof = None
        self.ddl_type = None
        self.ddl_supervision = None

    async def fetch_related(self, *_relations):
        return None

    async def fetch_project_related(self, *_relations):
        return None

    async def save(self):
        return None


def test_later_assignee_stops_at_unassigned_required_proofreading(monkeypatch):
    import nonebot

    nonebot.init()
    from nonebot_plugin_trans_progress import workflow

    completed_stages = []
    notifications = []
    scheduled = []
    mentions = []

    async def record_completion(episode, stage):
        completed_stages.append(stage)

    async def initialize_schedule(episode):
        scheduled.append(episode.status)

    async def notify(_group_id, lines, mentioned_qq_ids, _bot):
        notifications.extend(lines)
        mentions.extend(mentioned_qq_ids)

    monkeypatch.setattr(workflow, "record_stage_completion", record_completion)
    monkeypatch.setattr(workflow, "initialize_episode_schedule", initialize_schedule)
    monkeypatch.setattr(workflow, "notify_episode_completed", notify)

    episode = FakeEpisode()
    episode.project.leader = SimpleNamespace(qq_id="9", name="组长")
    asyncio.run(workflow.complete_episode(episode, "3", "嵌字", 100))

    assert completed_stages == [1]
    assert episode.status == 2
    assert scheduled == [2]
    assert "已自动跳过未分配工序：校对" not in notifications
    assert "校对尚未分配负责人，已暂停推进；分配后开始校对期限" in notifications
    assert "由 嵌字 代提交" in notifications
    assert mentions == ["9"]


def test_explicit_no_proofreading_skips_stage(monkeypatch):
    import nonebot

    nonebot.init()
    from nonebot_plugin_trans_progress import workflow

    completed_stages = []
    notifications = []

    async def record_completion(_episode, stage):
        completed_stages.append(stage)

    async def initialize_schedule(_episode):
        return None

    async def notify(_group_id, lines, _mentions, _bot):
        notifications.extend(lines)

    monkeypatch.setattr(workflow, "record_stage_completion", record_completion)
    monkeypatch.setattr(workflow, "initialize_episode_schedule", initialize_schedule)
    monkeypatch.setattr(workflow, "notify_episode_completed", notify)

    episode = FakeEpisode()
    episode.needs_proofreading = False
    episode.proofreader = SimpleNamespace(qq_id="2", name="校对")
    asyncio.run(workflow.complete_episode(episode, "1", "翻译", 100))

    assert completed_stages == [1, 2]
    assert episode.status == 3
    assert "已按设置跳过无需校对工序：校对" in notifications


def test_required_proofreading_cannot_be_submitted_without_assignee(monkeypatch):
    import nonebot

    nonebot.init()
    from nonebot_plugin_trans_progress import workflow

    episode = FakeEpisode()
    episode.status = 2
    with pytest.raises(ValueError, match="校对尚未分配负责人"):
        asyncio.run(workflow.complete_episode(episode, "3", "嵌字", 100))


def test_unassigned_supervision_is_not_skipped(monkeypatch):
    import nonebot

    nonebot.init()
    from nonebot_plugin_trans_progress import workflow

    completed_stages = []

    async def record_completion(episode, stage):
        completed_stages.append(stage)

    async def initialize_schedule(_episode):
        return None

    async def notify(*_args):
        return None

    monkeypatch.setattr(workflow, "record_stage_completion", record_completion)
    monkeypatch.setattr(workflow, "initialize_episode_schedule", initialize_schedule)
    monkeypatch.setattr(workflow, "notify_episode_completed", notify)

    episode = FakeEpisode()
    episode.status = 3
    asyncio.run(workflow.complete_episode(episode, "3", "嵌字", 100))

    assert completed_stages == [3]
    assert episode.status == 4


def test_recording_completion_does_not_schedule_future_work(monkeypatch):
    import nonebot

    nonebot.init()
    from nonebot_plugin_trans_progress import scheduling

    class Episode:
        project = SimpleNamespace(auto_schedule=True)
        completed_trans = None

        async def fetch_related(self, *_relations):
            return None

        async def save(self):
            return None

    episode = Episode()
    completed_at = datetime(2026, 10, 13, 9, 0)
    asyncio.run(scheduling.record_stage_completion(episode, 1, completed_at))

    assert episode.completed_trans == completed_at
    assert not hasattr(episode, "ddl_proof")
    assert completed_at + timedelta(days=14) != getattr(
        episode, "ddl_type", None
    )


def test_proofreading_schedule_waits_for_assignee(monkeypatch):
    import nonebot

    nonebot.init()
    from nonebot_plugin_trans_progress import scheduling

    class Episode:
        id = 1
        status = 2
        needs_proofreading = True
        project = SimpleNamespace(auto_schedule=True)
        proofreader = None
        started_proof = datetime(2026, 10, 1, 9, 0)
        ddl_proof = datetime(2026, 10, 15, 9, 0)

        async def fetch_related(self, *_relations):
            return None

        async def save(self):
            return None

    episode = Episode()

    class EpisodeQuery:
        def order_by(self, *_args):
            return self

        async def first(self):
            return episode

    class EpisodeModel:
        @classmethod
        def filter(cls, **_filters):
            return EpisodeQuery()

    monkeypatch.setattr(scheduling, "Episode", EpisodeModel)
    now = datetime(2026, 10, 13, 9, 0)

    asyncio.run(scheduling.initialize_episode_schedule(episode, now))
    assert episode.ddl_proof is None
    assert episode.started_proof is None

    episode.proofreader = SimpleNamespace(qq_id="2")
    asyncio.run(scheduling.initialize_episode_schedule(episode, now))
    assert episode.started_proof == now
    assert episode.ddl_proof == now + timedelta(days=14)


def test_auto_schedule_keeps_episode_workflows_independent(monkeypatch):
    import nonebot

    nonebot.init()
    from nonebot_plugin_trans_progress import workflow

    async def record_completion(_episode, _stage):
        return None

    async def initialize_schedule(_episode):
        return None

    async def notify(*_args):
        return None

    monkeypatch.setattr(workflow, "record_stage_completion", record_completion)
    monkeypatch.setattr(
        workflow, "initialize_episode_schedule", initialize_schedule
    )
    monkeypatch.setattr(workflow, "notify_episode_completed", notify)

    episode = FakeEpisode()
    episode.project.previous_episode_status = 3
    episode.status = 1
    episode.proofreader = SimpleNamespace(qq_id="2", name="校对")

    asyncio.run(workflow.complete_episode(episode, "1", "翻译", 100))

    assert episode.project.previous_episode_status == 3
    assert episode.status == 2
