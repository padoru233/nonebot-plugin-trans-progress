import json
import asyncio
from pathlib import Path

import httpx
from nonebot import logger, require
from tortoise.signals import post_save, post_delete

require("nonebot_plugin_localstore")
from nonebot_plugin_localstore import get_plugin_data_file

from .config import plugin_config
from .models import Episode, Project
from .public_catalog import get_public_catalog

CATALOG_REFRESH_DELAY_SECONDS = 0.5
_catalog_write_lock = asyncio.Lock()
_pending_refresh_task: asyncio.Task[None] | None = None


def is_catalog_generation_enabled() -> bool:
    return bool(
        plugin_config.trans_public_catalog_enabled
        or plugin_config.trans_public_catalog_sync_url
    )


def get_catalog_path() -> Path:
    return get_plugin_data_file("catalog.json")


async def generate_public_catalog(*, force_sync: bool = False) -> Path:
    """Generate the public catalog once and atomically replace the previous file."""
    async with _catalog_write_lock:
        catalog_path = get_catalog_path()
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        catalog = await get_public_catalog()
        existing_catalog = None
        if catalog_path.exists():
            try:
                existing_catalog = json.loads(
                    await asyncio.to_thread(catalog_path.read_text, encoding="utf-8")
                )
            except json.JSONDecodeError:
                logger.warning("公开漫画目录静态文件无效，将重新生成")
        changed = (
            not existing_catalog or existing_catalog.get("items") != catalog["items"]
        )
        if changed or force_sync:
            serialized_catalog = json.dumps(
                catalog,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            temporary_path = catalog_path.with_suffix(".json.tmp")
            await asyncio.to_thread(
                temporary_path.write_text,
                serialized_catalog,
                encoding="utf-8",
            )
            await asyncio.to_thread(temporary_path.replace, catalog_path)
        else:
            serialized_catalog = json.dumps(
                existing_catalog,
                ensure_ascii=False,
                separators=(",", ":"),
            )
    if changed or force_sync:
        await sync_public_catalog(serialized_catalog, len(catalog["items"]))
    return catalog_path


async def sync_public_catalog(serialized_catalog: str, item_count: int = 0) -> None:
    url = plugin_config.trans_public_catalog_sync_url
    token = plugin_config.trans_public_catalog_sync_token

    if not url and not token:
        return
    if not url or not token:
        logger.error(
            "公开漫画目录未同步：TRANS_PUBLIC_CATALOG_SYNC_URL 与 "
            "TRANS_PUBLIC_CATALOG_SYNC_TOKEN 必须同时配置"
        )
        return
    if not url.startswith("https://"):
        logger.error("公开漫画目录未同步：同步接口必须使用 HTTPS")
        return

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                url,
                content=serialized_catalog.encode(),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error(f"公开漫画目录同步到 Makers 失败: {exc}")
        return

    logger.info(f"公开漫画目录已同步到 Makers（{item_count} 个项目）")


async def get_or_generate_public_catalog() -> Path:
    catalog_path = get_catalog_path()
    if catalog_path.exists():
        return catalog_path
    return await generate_public_catalog()


async def _refresh_catalog_after_delay() -> None:
    await asyncio.sleep(CATALOG_REFRESH_DELAY_SECONDS)
    try:
        await generate_public_catalog()
    except Exception:
        logger.exception("公开漫画目录静态文件生成失败")


def mark_public_catalog_dirty() -> None:
    global _pending_refresh_task

    if not is_catalog_generation_enabled():
        return
    if _pending_refresh_task is None or _pending_refresh_task.done():
        _pending_refresh_task = asyncio.create_task(_refresh_catalog_after_delay())


async def flush_public_catalog() -> None:
    if _pending_refresh_task and not _pending_refresh_task.done():
        await _pending_refresh_task


@post_save(Project, Episode)
async def refresh_public_catalog_after_save(*args: object) -> None:
    _ = args
    mark_public_catalog_dirty()


@post_delete(Project, Episode)
async def refresh_public_catalog_after_delete(*args: object) -> None:
    _ = args
    mark_public_catalog_dirty()
