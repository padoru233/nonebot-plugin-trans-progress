from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

DETAIL_HOST = "manhua.zaimanhua.com"
COVER_HOST = "images.zaimanhua.com"
DETAIL_API = "https://v4api.zaimanhua.com/api/v1/comic2/comic/detail"


class ZaiManhuaMetadataError(ValueError):
    pass


@dataclass(frozen=True)
class ZaiManhuaMetadata:
    detail_url: str
    cover_url: str


def get_comic_id(detail_url: str) -> int:
    parsed = urlsplit(detail_url)
    path_parts = parsed.path.strip("/").split("/")
    if (
        parsed.scheme != "https"
        or parsed.hostname != DETAIL_HOST
        or len(path_parts) != 2
        or path_parts[0] != "details"
        or not path_parts[1].isdigit()
    ):
        raise ZaiManhuaMetadataError(
            "再漫画地址必须是 https://manhua.zaimanhua.com/details/<漫画 ID>"
        )
    return int(path_parts[1])


def get_cover_url(payload: object) -> str:
    if not isinstance(payload, dict):
        raise ZaiManhuaMetadataError("再漫画返回了无效的数据")

    if payload.get("errno") != 0:
        raise ZaiManhuaMetadataError("再漫画未返回该漫画详情")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise ZaiManhuaMetadataError("再漫画未返回漫画详情")
    comic_info = data.get("comicInfo")
    if not isinstance(comic_info, dict):
        raise ZaiManhuaMetadataError("再漫画未返回漫画详情")

    cover_url = comic_info.get("cover")
    if not isinstance(cover_url, str):
        raise ZaiManhuaMetadataError("再漫画未返回漫画封面")

    parsed = urlsplit(cover_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != COVER_HOST
        or not parsed.path.startswith("/webpic/")
    ):
        raise ZaiManhuaMetadataError("再漫画返回了不受支持的封面地址")
    return cover_url


async def get_metadata(detail_url: str) -> ZaiManhuaMetadata:
    comic_id = get_comic_id(detail_url)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(DETAIL_API, params={"id": comic_id})
            response.raise_for_status()
            cover_url = get_cover_url(response.json())
    except httpx.HTTPError as exc:
        raise ZaiManhuaMetadataError("无法获取再漫画详情，请稍后重试") from exc
    except ValueError as exc:
        if isinstance(exc, ZaiManhuaMetadataError):
            raise
        raise ZaiManhuaMetadataError("再漫画返回了无法解析的数据") from exc

    return ZaiManhuaMetadata(
        detail_url=f"https://{DETAIL_HOST}/details/{comic_id}",
        cover_url=cover_url,
    )
