import asyncio
from types import SimpleNamespace


def test_project_query_matches_multiword_name_and_episode():
    import nonebot

    nonebot.init()
    from nonebot_plugin_trans_progress import match_project_query

    project = SimpleNamespace(name="Odd and Kind", aliases=[], tags=[])

    assert match_project_query("odd and kind", [project]) == (project, None)
    assert match_project_query("odd and kind 第 1 话", [project]) == (
        project,
        "第 1 话",
    )


def test_project_query_matches_multiword_alias():
    import nonebot

    nonebot.init()
    from nonebot_plugin_trans_progress import match_project_query

    project = SimpleNamespace(
        name="正式作品名", aliases=["Odd and Kind"], tags=[]
    )

    assert match_project_query("ODD AND KIND 2", [project]) == (project, "2")


def test_find_episode_matches_number_without_confusing_decimal_chapters(monkeypatch):
    import nonebot

    nonebot.init()
    import nonebot_plugin_trans_progress as plugin

    episodes = [
        SimpleNamespace(title="第 2 话"),
        SimpleNamespace(title="第 6.2 话"),
    ]

    class Query:
        def __init__(self, result=None, items=None):
            self.result = result
            self.items = items or []

        def prefetch_related(self, *_relations):
            return self

        def __await__(self):
            async def resolve():
                return self.result

            return resolve().__await__()

        async def all(self):
            return self.items

    class EpisodeModel:
        @classmethod
        def get_or_none(cls, **_filters):
            return Query()

        @classmethod
        def filter(cls, **filters):
            matching = [
                episode
                for episode in episodes
                if filters.get("title__contains", "") in episode.title
            ]
            return Query(items=matching)

    monkeypatch.setattr(plugin, "Episode", EpisodeModel)
    result = asyncio.run(
        plugin.find_episode(SimpleNamespace(), "2")
    )

    assert result.title == "第 2 话"
