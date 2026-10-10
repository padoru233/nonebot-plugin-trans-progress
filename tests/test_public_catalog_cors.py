def test_public_catalog_allows_apex_and_www_domains():
    import nonebot

    nonebot.init()

    from nonebot_plugin_trans_progress.web import get_public_catalog_allowed_origins

    assert get_public_catalog_allowed_origins() == {
        "https://keli.love",
        "https://www.keli.love",
    }
