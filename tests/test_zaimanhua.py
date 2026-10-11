import pytest


def test_get_comic_id_accepts_detail_url():
    from nonebot_plugin_trans_progress.zaimanhua import get_comic_id

    assert get_comic_id("https://manhua.zaimanhua.com/details/84456") == 84456


@pytest.mark.parametrize(
    "url",
    [
        "http://manhua.zaimanhua.com/details/84456",
        "https://example.com/details/84456",
        "https://manhua.zaimanhua.com/reader/84456",
    ],
)
def test_get_comic_id_rejects_other_urls(url: str):
    from nonebot_plugin_trans_progress.zaimanhua import (
        ZaiManhuaMetadataError,
        get_comic_id,
    )

    with pytest.raises(ZaiManhuaMetadataError):
        get_comic_id(url)


def test_get_cover_url_accepts_zaimanhua_webpic():
    from nonebot_plugin_trans_progress.zaimanhua import get_cover_url

    payload = {
        "errno": 0,
        "data": {
            "comicInfo": {
                "cover": "https://images.zaimanhua.com/webpic/8/example.jpg"
            }
        },
    }

    assert get_cover_url(payload) == "https://images.zaimanhua.com/webpic/8/example.jpg"


def test_get_cover_url_rejects_error_response():
    from nonebot_plugin_trans_progress.zaimanhua import (
        ZaiManhuaMetadataError,
        get_cover_url,
    )

    payload = {"errno": 1, "errmsg": "not found", "data": {}}

    with pytest.raises(ZaiManhuaMetadataError):
        get_cover_url(payload)
