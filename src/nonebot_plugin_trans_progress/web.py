import base64
import hashlib
import secrets
from datetime import datetime
from typing import List, Optional, Dict, Set
from collections import defaultdict
import unicodedata
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from nonebot import get_bots, logger, get_plugin_config
from nonebot.adapters.onebot.v11 import Message, MessageSegment, Bot

from .models import Project, Episode, User, GroupSetting
from .utils import get_default_ddl, send_group_message
from .notifications import (
    notify_episode_created,
    notify_episode_manually_completed,
    notify_episode_member_removed,
    notify_episode_updated,
    notify_project_created,
)
from .workflow import complete_episode
from .scheduling import (
    STAGE_TIMING_FIELDS,
    initialize_episode_schedule,
    record_stage_completion,
)
from .config import Config
from .auth_pages import render_auth_page
from .broadcast import check_and_send_broadcast
from .catalog_store import get_or_generate_public_catalog, mark_public_catalog_dirty
from .zaimanhua import ZaiManhuaMetadataError, get_metadata


plugin_config = get_plugin_config(Config)

LOGIN_PATH = "/trans/auth/moeflow/login"


def get_auth_configuration_error() -> str | None:
    missing = [
        name
        for name, value in {
            "MOEFLOW_WEB_URL": plugin_config.moeflow_web_url,
            "TRANS_MOEFLOW_CLIENT_SECRET": plugin_config.trans_moeflow_client_secret,
            "TRANS_MOEFLOW_REDIRECT_URI": plugin_config.trans_moeflow_redirect_uri,
            "TRANS_AUTH_SESSION_SECRET": plugin_config.trans_auth_session_secret,
        }.items()
        if not value
    ]
    if missing:
        return f"缺少萌翻登录配置：{', '.join(missing)}"
    return None


def require_auth_configuration() -> None:
    if error := get_auth_configuration_error():
        raise HTTPException(status_code=503, detail=error)


async def require_admin_session(request: Request) -> dict[str, str]:
    require_auth_configuration()
    user = request.session.get("trans_admin")
    if not isinstance(user, dict):
        raise HTTPException(status_code=401, detail="请先使用萌翻账号登录")
    subject = user.get("subject")
    name = user.get("name")
    if not isinstance(subject, str) or not isinstance(name, str):
        request.session.clear()
        raise HTTPException(status_code=401, detail="登录会话无效")
    return {"subject": subject, "name": name}


def create_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


api_router = APIRouter(dependencies=[Depends(require_admin_session)])
public_router = APIRouter()


@public_router.get("/auth/moeflow/login")
async def login_with_moeflow(request: Request):
    require_auth_configuration()
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    request.session.clear()
    request.session["moeflow_oauth_state"] = state
    request.session["moeflow_oauth_verifier"] = verifier

    query = urlencode(
        {
            "client_id": plugin_config.trans_moeflow_client_id,
            "redirect_uri": plugin_config.trans_moeflow_redirect_uri,
            "state": state,
            "code_challenge": create_code_challenge(verifier),
        }
    )
    return RedirectResponse(
        f"{plugin_config.moeflow_web_url.rstrip('/')}/authorize?{query}",
        status_code=303,
    )


def login_error_page(
    title: str, message: str, status_code: int, details: list[str] | None = None
):
    return render_auth_page(
        title,
        message,
        status_code=status_code,
        details=details,
        actions=[("重新登录", LOGIN_PATH, True)],
    )


@public_router.get("/auth/moeflow/callback")
async def moeflow_login_callback(
    request: Request, code: str | None = None, state: str | None = None
):
    require_auth_configuration()
    expected_state = request.session.pop("moeflow_oauth_state", None)
    verifier = request.session.pop("moeflow_oauth_verifier", None)
    # compare_digest 对含非 ASCII 的 str 会抛 TypeError，所以比较字节
    if (
        not code
        or not state
        or not isinstance(expected_state, str)
        or not isinstance(verifier, str)
        or not secrets.compare_digest(state.encode(), expected_state.encode())
    ):
        return login_error_page(
            "登录已失效", "登录请求已过期或与当前浏览器不匹配，请重新登录。", 400
        )

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{plugin_config.moeflow_api_url.rstrip('/')}/v1/bot-authorization/tokens",
                json={
                    "client_id": plugin_config.trans_moeflow_client_id,
                    "client_secret": plugin_config.trans_moeflow_client_secret,
                    "redirect_uri": plugin_config.trans_moeflow_redirect_uri,
                    "code": code,
                    "code_verifier": verifier,
                },
            )
            response.raise_for_status()
            identity = response.json()
    except httpx.HTTPError as exc:
        logger.warning(f"萌翻授权码交换失败：{exc}")
        return login_error_page(
            "无法验证登录", "暂时无法向萌翻确认你的身份，请稍后重试或联系管理员。", 502
        )
    except ValueError as exc:
        logger.warning(f"萌翻授权码交换返回了无效响应：{exc}")
        return login_error_page(
            "无法验证登录", "萌翻返回了无法识别的身份信息，请联系管理员。", 502
        )

    subject = identity.get("subject") if isinstance(identity, dict) else None
    name = identity.get("name") if isinstance(identity, dict) else None
    admin = identity.get("admin") if isinstance(identity, dict) else None
    if (
        not isinstance(subject, str)
        or not isinstance(name, str)
        or not isinstance(admin, bool)
    ):
        return login_error_page(
            "无法验证登录", "萌翻返回了不完整的身份信息，请联系管理员。", 502
        )
    if not admin and subject not in plugin_config.trans_moeflow_allowed_subjects:
        logger.warning(f"拒绝未授权的萌翻账号登录后台：{subject}")
        return render_auth_page(
            "没有访问权限",
            "此萌翻账号未获准访问 Bot 后台。",
            status_code=403,
            details=[
                f"当前萌翻账号：{name}",
                f"用户 ID：{subject}",
                "请把用户 ID 发给管理员，由其加入 TRANS_MOEFLOW_ALLOWED_SUBJECTS。",
                "如需更换账号，请先在萌翻网站退出登录。",
            ],
            actions=[
                ("重新登录", LOGIN_PATH, True),
                ("前往萌翻", plugin_config.moeflow_web_url or "/", False),
            ],
        )

    request.session.clear()
    request.session["trans_admin"] = {"subject": subject, "name": name}
    return RedirectResponse("/trans/", status_code=303)


@api_router.get("/auth/me")
async def current_admin(admin: dict[str, str] = Depends(require_admin_session)):
    return admin


@public_router.post("/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return {"message": "已退出登录"}


@public_router.get("/auth/logged-out")
async def logged_out():
    return render_auth_page(
        "已退出登录",
        "你已退出 Bot 后台。这不会退出你的萌翻账号，再次登录时可能无需重新输入密码。",
        actions=[("重新登录", LOGIN_PATH, True)],
    )


def get_public_catalog_allowed_origins() -> set[str]:
    origin = plugin_config.trans_public_catalog_allow_origin
    origins = {origin}
    if origin == "https://keli.love":
        origins.add("https://www.keli.love")
    return origins


@public_router.get("/catalog.json")
async def get_catalog(request: Request):
    if not plugin_config.trans_public_catalog_enabled:
        raise HTTPException(status_code=404, detail="Public catalog is disabled")

    cache_seconds = plugin_config.trans_public_catalog_cache_seconds
    cdn_cache_seconds = plugin_config.trans_public_catalog_cdn_cache_seconds
    headers = {
        "Cache-Control": (
            f"public, max-age={cache_seconds}, s-maxage={cdn_cache_seconds}, "
            f"stale-while-revalidate={cdn_cache_seconds * 2}"
        )
    }
    origin = request.headers.get("origin")
    if origin in get_public_catalog_allowed_origins():
        headers["Access-Control-Allow-Origin"] = origin
        headers["Vary"] = "Origin"
    return FileResponse(
        await get_or_generate_public_catalog(),
        media_type="application/json",
        headers=headers,
    )

# --- Pydantic Models ---
class ProjectCreate(BaseModel):
    name: str
    aliases: List[str] = []
    tags: List[str] = []
    zaimanhua_url: Optional[str] = None
    group_id: str
    auto_schedule: bool = True
    needs_proofreading: bool = True
    standalone_episodes: bool = False
    leader_qq: Optional[str] = None
    default_translator_qq: Optional[str] = None
    default_proofreader_qq: Optional[str] = None
    default_typesetter_qq: Optional[str] = None
    default_supervisor_qq: Optional[str] = None

class ProjectUpdate(BaseModel):
    name: str
    aliases: List[str] = []
    tags: List[str] = []
    zaimanhua_url: Optional[str] = None
    auto_schedule: bool = True
    needs_proofreading: Optional[bool] = None
    # 为 None 表示调用方未提供，保持原值
    standalone_episodes: Optional[bool] = None
    leader_qq: Optional[str] = None
    default_translator_qq: Optional[str] = None
    default_proofreader_qq: Optional[str] = None
    default_typesetter_qq: Optional[str] = None
    default_supervisor_qq: Optional[str] = None

class MemberUpdate(BaseModel):
    name: str
    tags: List[str] = []

class EpisodeCreate(BaseModel):
    project_name: str
    title: str
    zaimanhua_url: Optional[str] = None
    needs_proofreading: Optional[bool] = None
    translator_qq: Optional[str] = None
    proofreader_qq: Optional[str] = None
    typesetter_qq: Optional[str] = None
    supervisor_qq: Optional[str] = None
    ddl_trans: Optional[datetime] = None
    ddl_proof: Optional[datetime] = None
    ddl_type: Optional[datetime] = None
    ddl_supervision: Optional[datetime] = None

class EpisodeUpdate(BaseModel):
    title: str
    status: int
    zaimanhua_url: Optional[str] = None
    needs_proofreading: Optional[bool] = None
    translator_qq: Optional[str] = None
    proofreader_qq: Optional[str] = None
    typesetter_qq: Optional[str] = None
    supervisor_qq: Optional[str] = None
    ddl_trans: Optional[datetime] = None
    ddl_proof: Optional[datetime] = None
    ddl_type: Optional[datetime] = None
    ddl_supervision: Optional[datetime] = None

class SyncGroupModel(BaseModel):
    group_id: str

class SettingUpdate(BaseModel):
    group_id: str
    enable: bool
    time: str = "10:00"

class RemindNow(BaseModel):
    group_id: str

class EpisodeCompletion(BaseModel):
    project_name: str
    episode_title: str
    user_name: str
    role: str

class ManualEpisodeCompletion(BaseModel):
    project_name: str
    episode_title: str

class MemberSynchronization(BaseModel):
    project_name: str
    episode_title: str
    user_name: str
    role: str
    action: str

class ProjectEnsure(BaseModel):
    name: str
    group_id: str

class EpisodeEnsure(BaseModel):
    project_name: str
    title: str
    group_id: str

# --- Helpers ---
async def get_project_default_assignees(project: Project) -> dict[str, Optional[User]]:
    await project.fetch_related(
        "leader",
        "default_translator",
        "default_proofreader",
        "default_typesetter",
        "default_supervisor",
    )
    return {
        "translator": project.default_translator,
        "proofreader": project.default_proofreader,
        "typesetter": project.default_typesetter,
        "supervisor": project.default_supervisor or project.leader,
    }

async def apply_missing_default_assignees(
    episode: Episode, default_assignees: dict[str, Optional[User]]
) -> bool:
    changed = False
    for field_name, assignee in default_assignees.items():
        if assignee and getattr(episode, f"{field_name}_id") is None:
            setattr(episode, field_name, assignee)
            changed = True
    if changed:
        await episode.save()
    return changed

async def get_db_user(qq, group_id):
    if not qq: return None
    return await User.get_or_none(qq_id=str(qq), group_id=str(group_id))

def normalize_project_identifier(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()

async def resolve_zaimanhua_link(url: Optional[str]):
    """校验再漫画地址并取得封面；空值返回 None，失败时在保存前抛出 422。"""
    if not url or not url.strip():
        return None
    try:
        return await get_metadata(url.strip())
    except ZaiManhuaMetadataError as exc:
        raise HTTPException(422, str(exc)) from exc

async def find_projects_by_name_or_alias(identifier: str) -> List[Project]:
    projects = await Project.all()
    normalized_identifier = normalize_project_identifier(identifier)
    name_matches = [
        project
        for project in projects
        if normalize_project_identifier(project.name) == normalized_identifier
    ]
    if name_matches:
        return name_matches
    return [
        project
        for project in projects
        if any(
            normalize_project_identifier(alias) == normalized_identifier
            for alias in project.aliases
        )
    ]

async def find_episodes_by_title(identifier: str) -> List[Episode]:
    normalized_identifier = normalize_project_identifier(identifier)
    episodes = await Episode.all().prefetch_related("project")
    return [
        episode
        for episode in episodes
        if normalize_project_identifier(episode.title) == normalized_identifier
    ]

async def find_or_create_group_user(project: Project, user_name: str) -> User:
    group_id = str(project.group_id)
    users = await User.filter(group_id=group_id, name=user_name).all()
    if len(users) == 1:
        return users[0]
    if len(users) > 1:
        raise HTTPException(409, "群内匹配到多个同名成员")

    bot = await find_bot_for_group(group_id)
    if not bot:
        raise HTTPException(404, "Bot 未加入项目所属群，无法同步成员")
    members = await bot.get_group_member_list(group_id=int(group_id))
    matched_members = [
        member
        for member in members
        if user_name in {member.get("card"), member.get("nickname")}
    ]
    if not matched_members:
        raise HTTPException(404, "项目所属群内未找到同名成员")
    if len(matched_members) > 1:
        raise HTTPException(409, "项目所属群内匹配到多个同名成员")

    member = matched_members[0]
    qq_id = str(member["user_id"])
    user = await get_db_user(qq_id, group_id)
    if user:
        user.name = user_name
        await user.save()
        return user
    return await User.create(qq_id=qq_id, group_id=group_id, name=user_name)

def get_online_bots() -> List[Bot]:
    return [bot for bot in get_bots().values() if isinstance(bot, Bot)]

async def find_bot_for_group(group_id: str) -> Optional[Bot]:
    """遍历所有 Bot，找到在该群内的一个 Bot"""
    for bot in get_online_bots():
        try:
            g_list = await bot.get_group_list()
            if any(str(g['group_id']) == str(group_id) for g in g_list):
                return bot
        except Exception:
            continue
    return None

async def ensure_project_for_group(name: str, group_id: str):
    """
    确保群内存在对应名称的项目（项目集），不存在则创建（并播报"新坑开张"）。
    只有当同名项目在 bot 侧确实是第一次出现时才会创建+播报，
    已存在的项目会直接复用，不会重复创建或播报。
    """
    projects = await find_projects_by_name_or_alias(name)
    if len(projects) > 1:
        raise HTTPException(409, "匹配到多个项目，无法确认要同步的项目")
    if projects:
        if str(projects[0].group_id) != str(group_id):
            raise HTTPException(409, "同名项目已绑定到其他 QQ 群")
        return projects[0], False

    if not get_online_bots():
        raise HTTPException(503, "没有在线的 OneBot V11 机器人，无法创建项目")
    bot = await find_bot_for_group(group_id)
    if not bot:
        raise HTTPException(404, "Bot 未加入配置的 QQ 群，无法创建项目")
    try:
        group_info = await bot.get_group_info(group_id=int(group_id))
    except Exception as exc:
        raise HTTPException(502, f"无法读取配置的 QQ 群信息: {exc}")

    project = await Project.create(
        name=name,
        group_id=group_id,
        group_name=group_info.get("group_name", "未同步"),
    )
    await notify_project_created(project, group_id)
    return project, True

def ensure_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """确保 datetime 对象有时区信息，如果没有则添加本地时区"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        # 如果是 naive datetime，添加本地时区
        import pytz
        from datetime import timezone
        # 使用系统本地时区
        return dt.replace(tzinfo=timezone.utc).astimezone()
    return dt

# --- Routes ---

@api_router.get("/health")
async def get_bot_health():
    bots = []
    for bot in get_online_bots():
        try:
            groups = await bot.get_group_list()
            bots.append({
                "self_id": str(bot.self_id),
                "connected": True,
                "group_count": len(groups),
            })
        except Exception as exc:
            bots.append({
                "self_id": str(bot.self_id),
                "connected": False,
                "error": str(exc),
            })
    return {
        "status": "ok" if bots else "offline",
        "bot_count": len(bots),
        "bots": bots,
    }

@api_router.get("/groups/all")
async def get_all_bot_groups():
    groups_map = {}
    for bot in get_bots().values():
        if isinstance(bot, Bot):
            try:
                g_list = await bot.get_group_list()
                for g in g_list:
                    gid = str(g['group_id'])
                    groups_map[gid] = {"group_id": gid, "group_name": g['group_name']}
            except Exception as e:
                logger.warning(f"Bot {bot.self_id} 获取群列表异常: {e}")
    return list(groups_map.values())

@api_router.get("/groups/db")
async def get_db_groups():
    all_groups_map = {}
    for bot in get_bots().values():
        if isinstance(bot, Bot):
            try:
                g_list = await bot.get_group_list()
                for g in g_list:
                    all_groups_map[str(g['group_id'])] = g['group_name']
            except: pass

    try:
        db_group_ids = set(await User.all().distinct().values_list("group_id", flat=True))
        filtered = []
        for gid in db_group_ids:
            g_name = all_groups_map.get(gid, "未知群聊(Bot不在群内)")
            filtered.append({"group_id": gid, "group_name": g_name})
        return filtered
    except Exception as e:
        logger.error(f"获取DB群列表失败: {e}")
        return []

@api_router.get("/projects")
async def get_projects():
    projects = await Project.all().order_by('-id').prefetch_related('leader', 'default_translator', 'default_proofreader', 'default_typesetter', 'default_supervisor')

    bot_groups_map = {}
    for bot in get_bots().values():
        if isinstance(bot, Bot):
            try:
                g_list = await bot.get_group_list()
                for g in g_list:
                    bot_groups_map[str(g['group_id'])] = g['group_name']
            except: pass

    result = []
    for p in projects:
        eps = await Episode.filter(project=p).prefetch_related('translator', 'proofreader', 'typesetter', 'supervisor').order_by('id').all()
        ep_list = []
        for e in eps:
            ep_list.append({
                "id": e.id, "title": e.title, "status": e.status,
                "needs_proofreading": e.needs_proofreading,
                "zaimanhua_url": e.zaimanhua_url,
                "ddl_trans": e.ddl_trans, "ddl_proof": e.ddl_proof, "ddl_type": e.ddl_type,
                "ddl_supervision": e.ddl_supervision,
                "translator": {"name": e.translator.name, "qq_id": e.translator.qq_id} if e.translator else None,
                "proofreader": {"name": e.proofreader.name, "qq_id": e.proofreader.qq_id} if e.proofreader else None,
                "typesetter": {"name": e.typesetter.name, "qq_id": e.typesetter.qq_id} if e.typesetter else None,
                "supervisor": {"name": e.supervisor.name, "qq_id": e.supervisor.qq_id} if e.supervisor else None,
            })

        defaults = {
            "trans": p.default_translator.qq_id if p.default_translator else "",
            "proof": p.default_proofreader.qq_id if p.default_proofreader else "",
            "type": p.default_typesetter.qq_id if p.default_typesetter else "",
            "super": p.default_supervisor.qq_id if p.default_supervisor else "",
        }

        real_group_name = bot_groups_map.get(p.group_id) or p.group_name or "未同步"

        result.append({
            "id": p.id,
            "name": p.name,
            "aliases": p.aliases,
            "tags": p.tags,
            "zaimanhua_url": p.zaimanhua_url,
            "group_id": p.group_id,
            "group_name": real_group_name,
            "leader": {"name": p.leader.name, "qq_id": p.leader.qq_id} if p.leader else None,
            "auto_schedule": p.auto_schedule,
            "needs_proofreading": p.needs_proofreading,
            "standalone_episodes": p.standalone_episodes,
            "defaults": defaults,
            "episodes": ep_list
        })
    return result

@api_router.get("/members")
async def get_members():
    return await User.all()

@api_router.post("/group/sync_members")
async def sync_group_members(data: SyncGroupModel):
    gid = str(data.group_id)
    target_bot = await find_bot_for_group(gid)

    if not target_bot:
        raise HTTPException(500, f"没有找到任何 OneBot V11 账号加入了群 {gid}")

    try:
        g_info = await target_bot.get_group_info(group_id=int(gid))
        g_name = g_info.get("group_name", "未知群聊")
        await Project.filter(group_id=gid).update(group_name=g_name)
        member_list = await target_bot.get_group_member_list(group_id=int(gid))
    except Exception as e:
        raise HTTPException(500, f"Bot通讯失败: {e}")

    count = 0
    for m in member_list:
        qq = str(m['user_id'])
        name = m['card'] or m['nickname'] or f"用户{qq}"
        u = await User.get_or_none(qq_id=qq, group_id=gid)
        if u:
            u.name = name
            await u.save()
        else:
            await User.create(qq_id=qq, group_id=gid, name=name)
        count += 1
    return {"status": "success", "count": count, "group_name": g_name}

@api_router.post("/project/create")
async def create_project(proj: ProjectCreate):
    if await Project.filter(name=proj.name).exists():
        raise HTTPException(400, "项目名已存在")

    gid = str(proj.group_id)
    bot = await find_bot_for_group(gid)
    g_name = "未同步"

    if bot:
        try:
            info = await bot.get_group_info(group_id=int(gid))
            g_name = info.get("group_name", "未同步")
        except: pass

    leader = await get_db_user(proj.leader_qq, gid)

    # 自动创建负责人
    if not leader and proj.leader_qq and bot:
         try:
            u_info = await bot.get_group_member_info(group_id=int(gid), user_id=int(proj.leader_qq))
            leader = await User.create(qq_id=proj.leader_qq, group_id=gid, name=u_info['card'] or u_info['nickname'])
         except: pass

    d_trans = await get_db_user(proj.default_translator_qq, gid)
    d_proof = await get_db_user(proj.default_proofreader_qq, gid)
    d_type = await get_db_user(proj.default_typesetter_qq, gid)
    d_super = await get_db_user(proj.default_supervisor_qq, gid)
    metadata = None
    if proj.zaimanhua_url:
        try:
            metadata = await get_metadata(proj.zaimanhua_url)
        except ZaiManhuaMetadataError as exc:
            raise HTTPException(422, str(exc)) from exc

    project = await Project.create(
        name=proj.name,
        aliases=proj.aliases,
        tags=proj.tags,
        cover_url=metadata.cover_url if metadata else None,
        zaimanhua_url=metadata.detail_url if metadata else None,
        auto_schedule=proj.auto_schedule,
        needs_proofreading=proj.needs_proofreading,
        standalone_episodes=proj.standalone_episodes,
        group_id=gid, group_name=g_name, leader=leader,
        default_translator=d_trans, default_proofreader=d_proof, default_typesetter=d_type,
        default_supervisor=d_super
    )

    await notify_project_created(project, gid, proj.aliases, proj.tags)
    return {"status": "success"}

@api_router.post("/project/ensure")
async def ensure_project(form: ProjectEnsure):
    group_id = str(form.group_id)
    project, created = await ensure_project_for_group(form.name, group_id)
    return {"status": "success", "created": created, "project_id": project.id}

@api_router.put("/project/{id}")
async def update_project(id: int, form: ProjectUpdate):
    p = await Project.get_or_none(id=id)
    if not p: raise HTTPException(404)
    gid = str(p.group_id)
    p.name = form.name
    p.aliases = form.aliases
    p.tags = form.tags
    if form.zaimanhua_url:
        try:
            metadata = await get_metadata(form.zaimanhua_url)
        except ZaiManhuaMetadataError as exc:
            raise HTTPException(422, str(exc)) from exc
        p.zaimanhua_url = metadata.detail_url
        p.cover_url = metadata.cover_url
    else:
        p.zaimanhua_url = None
        p.cover_url = None
    p.auto_schedule = form.auto_schedule
    if (
        "needs_proofreading" in form.model_fields_set
        and form.needs_proofreading is not None
    ):
        p.needs_proofreading = form.needs_proofreading
    if form.standalone_episodes is not None:
        p.standalone_episodes = form.standalone_episodes

    p.leader = await get_db_user(form.leader_qq, gid)
    p.default_translator = await get_db_user(form.default_translator_qq, gid)
    p.default_proofreader = await get_db_user(form.default_proofreader_qq, gid)
    p.default_typesetter = await get_db_user(form.default_typesetter_qq, gid)
    p.default_supervisor = await get_db_user(form.default_supervisor_qq, gid)
    await p.save()
    return {"status": "success"}

@api_router.delete("/project/{id}")
async def delete_project(id: int):
    p = await Project.get_or_none(id=id)
    if not p: raise HTTPException(404)
    await Episode.filter(project=p).delete()
    await p.delete()
    return {"status": "success"}

@api_router.post("/episode/ensure")
async def ensure_episode(form: EpisodeEnsure):
    group_id = str(form.group_id)
    # 项目集若在 bot 侧确实是第一次出现（比如萌翻已有项目集刚同步/还未通过
    # /project/ensure 单独同步过），这里兜底创建时也要正常播报"新坑开张"，
    # 否则会出现"bot 创建了项目但完全没播报"的情况。
    # 重复播报问题应通过让萌翻侧对已有项目集做一次性同步来解决，而不是在这里吞掉播报。
    project, project_created = await ensure_project_for_group(form.project_name, group_id)
    episode = await Episode.get_or_none(project=project, title=form.title)
    default_assignees = await get_project_default_assignees(project)
    if episode:
        changed = await apply_missing_default_assignees(episode, default_assignees)
        if changed:
            await initialize_episode_schedule(episode)
        return {
            "status": "success",
            "created": False,
            "project_created": project_created,
            "episode_id": episode.id,
        }

    episode = await Episode.create(
        project=project,
        title=form.title,
        status=1,
        needs_proofreading=project.needs_proofreading,
        **default_assignees,
    )
    await initialize_episode_schedule(episode)
    await notify_episode_created(project, episode, group_id)
    return {
        "status": "success",
        "created": True,
        "project_created": project_created,
        "episode_id": episode.id,
    }

@api_router.post("/episode/add")
async def add_episode(ep: EpisodeCreate):
    projects = await find_projects_by_name_or_alias(ep.project_name)
    if not projects:
        raise HTTPException(404, "未找到匹配的项目或别名")
    if len(projects) > 1:
        raise HTTPException(409, "匹配到多个项目，无法确认要分配的项目")
    project = projects[0]
    gid = str(project.group_id)

    trans = await get_db_user(ep.translator_qq, gid)
    proof = await get_db_user(ep.proofreader_qq, gid)
    type_ = await get_db_user(ep.typesetter_qq, gid)
    super_ = await get_db_user(ep.supervisor_qq, gid)
    if super_ is None:
        default_assignees = await get_project_default_assignees(project)
        super_ = default_assignees["supervisor"]

    # 确保所有 datetime 都是 aware 的
    dt_trans = ensure_aware(ep.ddl_trans)
    dt_proof = ensure_aware(ep.ddl_proof)
    dt_type = ensure_aware(ep.ddl_type)
    dt_super = ensure_aware(ep.ddl_supervision)
    metadata = await resolve_zaimanhua_link(ep.zaimanhua_url)

    episode = await Episode.create(
        project=project, title=ep.title, status=1,
        needs_proofreading=(
            project.needs_proofreading
            if ep.needs_proofreading is None
            else ep.needs_proofreading
        ),
        zaimanhua_url=metadata.detail_url if metadata else None,
        cover_url=metadata.cover_url if metadata else None,
        translator=trans, proofreader=proof, typesetter=type_, supervisor=super_,
        ddl_trans=None if project.auto_schedule else dt_trans,
        ddl_proof=None if project.auto_schedule else dt_proof,
        ddl_type=None if project.auto_schedule else dt_type,
        ddl_supervision=None if project.auto_schedule else dt_super,
    )
    if project.auto_schedule:
        await initialize_episode_schedule(episode)

    await notify_episode_created(project, episode, gid)
    return {"status": "created"}

@api_router.put("/episode/{id}")
async def update_episode(id: int, form: EpisodeUpdate):
    ep = await Episode.get_or_none(id=id).prefetch_related('project', 'project__leader', 'translator', 'proofreader', 'typesetter', 'supervisor')
    if not ep: raise HTTPException(404)
    gid = str(ep.project.group_id)

    # 仅在请求带了该字段时才改动链接，避免其他调用方的 PUT 误清空；地址未变则不再请求再漫画
    new_zaimanhua_url, new_cover_url = ep.zaimanhua_url, ep.cover_url
    if "zaimanhua_url" in form.model_fields_set:
        requested_url = (form.zaimanhua_url or "").strip()
        if requested_url != (ep.zaimanhua_url or ""):
            metadata = await resolve_zaimanhua_link(requested_url)
            new_zaimanhua_url = metadata.detail_url if metadata else None
            new_cover_url = metadata.cover_url if metadata else None

    new_trans = await get_db_user(form.translator_qq, gid)
    new_proof = await get_db_user(form.proofreader_qq, gid)
    new_type = await get_db_user(form.typesetter_qq, gid)
    new_super = await get_db_user(form.supervisor_qq, gid)

    new_ddl_trans = ensure_aware(form.ddl_trans)
    new_ddl_proof = ensure_aware(form.ddl_proof)
    new_ddl_type = ensure_aware(form.ddl_type)
    new_ddl_super = ensure_aware(form.ddl_supervision)

    changes = []
    mentions_qq = set()

    def fmt_date(d): return d.strftime('%m-%d') if d else "未定"
    def fmt_user(u): return u.name if u else "未分配"

    if ep.title != form.title:
        changes.append(f"标题: {ep.title} -> {form.title}")

    needs_proofreading = ep.needs_proofreading
    if "needs_proofreading" in form.model_fields_set:
        needs_proofreading = (
            ep.project.needs_proofreading
            if form.needs_proofreading is None
            else form.needs_proofreading
        )

    new_status = form.status
    skipped_proofreading = (
        ep.status == 2 and new_status == 2 and not needs_proofreading
    )
    if skipped_proofreading:
        new_status = 3

    status_map = {0: '未开始', 1: '翻译', 2: '校对', 3: '嵌字', 4: '监修', 5: '完结'}
    if ep.status != new_status:
        old_s = status_map.get(ep.status, str(ep.status))
        new_s = status_map.get(new_status, str(new_status))
        changes.append(f"状态: {old_s} -> {new_s}")
        if new_status == 1 and new_trans: mentions_qq.add(new_trans.qq_id)
        elif new_status == 2 and new_proof: mentions_qq.add(new_proof.qq_id)
        elif new_status == 3 and new_type: mentions_qq.add(new_type.qq_id)
        elif new_status == 4 and new_super: mentions_qq.add(new_super.qq_id)
    if skipped_proofreading:
        changes.append("本话无需校对，已自动跳过校对阶段")

    def check_role_change(label, old_u, new_u, old_ddl, new_ddl):
        old_uid = old_u.id if old_u else None
        new_uid = new_u.id if new_u else None
        if old_uid != new_uid:
            changes.append(f"{label}: {fmt_user(old_u)} -> {fmt_user(new_u)}")
            if new_u: mentions_qq.add(new_u.qq_id)

        if old_ddl != new_ddl:
            changes.append(f"{label}DDL: {fmt_date(old_ddl)} -> {fmt_date(new_ddl)}")
            target = new_u if new_u else old_u
            if target: mentions_qq.add(target.qq_id)

    check_role_change("翻译", ep.translator, new_trans, ep.ddl_trans, new_ddl_trans)
    check_role_change("校对", ep.proofreader, new_proof, ep.ddl_proof, new_ddl_proof)
    check_role_change("嵌字", ep.typesetter, new_type, ep.ddl_type, new_ddl_type)
    check_role_change("监修", ep.supervisor, new_super, ep.ddl_supervision, new_ddl_super)

    ep.title = form.title
    ep.zaimanhua_url = new_zaimanhua_url
    ep.cover_url = new_cover_url
    ep.status = new_status
    if "needs_proofreading" in form.model_fields_set:
        ep.needs_proofreading = needs_proofreading
    ep.translator = new_trans
    ep.proofreader = new_proof
    ep.typesetter = new_type
    ep.supervisor = new_super
    ep.ddl_trans = new_ddl_trans
    ep.ddl_proof = new_ddl_proof
    ep.ddl_type = new_ddl_type
    ep.ddl_supervision = new_ddl_super
    await ep.save()
    if skipped_proofreading:
        await record_stage_completion(ep, 2)
    if ep.project.auto_schedule and ep.status < 5:
        await initialize_episode_schedule(ep)

    if changes:
        await notify_episode_updated(ep.project, ep, gid, changes, mentions_qq)

    return {"status": "success"}

@api_router.post("/episode/complete")
async def complete_episode_by_assignee(form: EpisodeCompletion):
    role_status = {
        "translator": (1, "translator"),
        "proofreader": (2, "proofreader"),
        "picture_editor": (3, "typesetter"),
        "coordinator": (4, "supervisor"),
    }
    if form.role not in role_status:
        raise HTTPException(422, "不支持的任务角色")

    _, assignee_field = role_status[form.role]
    projects = await find_projects_by_name_or_alias(form.project_name)
    if not projects:
        raise HTTPException(404, "未找到匹配的项目或别名")
    if len(projects) > 1:
        raise HTTPException(409, "匹配到多个项目，无法确认要完成的项目")
    episode = await Episode.get_or_none(
        project=projects[0], title=form.episode_title, status__lt=5
    ).prefetch_related(
        "project",
        "project__leader",
        "translator",
        "proofreader",
        "typesetter",
        "supervisor",
    )
    if not episode:
        raise HTTPException(404, "未找到进行中的任务")
    assignee = getattr(episode, assignee_field)
    if not assignee or assignee.name != form.user_name:
        raise HTTPException(403, "当前成员不是所提交工序的负责人")
    bot = await find_bot_for_group(str(episode.project.group_id))
    try:
        await complete_episode(
            episode,
            assignee.qq_id,
            assignee.name,
            int(episode.project.group_id),
            bot,
        )
    except PermissionError as error:
        raise HTTPException(403, str(error)) from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    return {"status": "success", "episode_id": episode.id}

@api_router.post("/episode/manual-complete")
async def manually_complete_episode(form: ManualEpisodeCompletion):
    projects = await find_projects_by_name_or_alias(form.project_name)
    if not projects:
        raise HTTPException(404, "未找到匹配的项目或别名")
    if len(projects) > 1:
        raise HTTPException(409, "匹配到多个项目，无法确认要完结的话数")
    project = projects[0]
    episode = await Episode.get_or_none(
        project=project, title=form.episode_title
    )
    if not episode:
        raise HTTPException(404, "未找到匹配的话数")
    if episode.status == 5:
        return {
            "status": "already_completed",
            "episode_id": episode.id,
        }

    episode.status = 5
    for stage in range(1, 5):
        if getattr(episode, STAGE_TIMING_FIELDS[stage][1]) is None:
            await record_stage_completion(episode, stage)
    await episode.save()
    await notify_episode_manually_completed(project, episode, str(project.group_id))
    return {"status": "success", "episode_id": episode.id}

@api_router.post("/episode/member/sync")
async def sync_member(form: MemberSynchronization):
    if form.action not in {"added", "changed", "removed"}:
        raise HTTPException(422, "不支持的成员变动类型")
    projects = await find_projects_by_name_or_alias(form.project_name)
    if not projects:
        raise HTTPException(404, "未找到匹配的项目或别名")
    if len(projects) > 1:
        raise HTTPException(409, "匹配到多个项目，无法确认要同步的项目")
    project = projects[0]
    episode = await Episode.get_or_none(project=project, title=form.episode_title)
    if not episode:
        raise HTTPException(404, "未找到匹配的话数")
    role_fields = {
        "translator": "translator",
        "proofreader": "proofreader",
        "picture_editor": "typesetter",
        "coordinator": "supervisor",
    }
    role_field = role_fields.get(form.role)
    user = None
    if role_field and form.action != "removed":
        user = await find_or_create_group_user(project, form.user_name)
        setattr(episode, role_field, user)
        await episode.save()
    elif role_field:
        assigned_user = await getattr(episode, role_field)
        if assigned_user and assigned_user.name == form.user_name:
            setattr(episode, role_field, None)
            await episode.save()

    if form.action == "removed":
        await notify_episode_member_removed(
            project, episode, str(project.group_id), form.user_name, form.role
        )
    return {
        "status": "success",
        "user_id": user.id if user else None,
        "episode_role": role_field,
    }

@api_router.delete("/episode/{id}")
async def delete_episode(id: int):
    await Episode.filter(id=id).delete()
    mark_public_catalog_dirty()
    return {"status": "success"}

@api_router.put("/member/{id}")
async def update_member(id: int, form: MemberUpdate):
    u = await User.get_or_none(id=id)
    if not u: raise HTTPException(404)
    u.name = form.name
    u.tags = form.tags
    await u.save()
    return {"status": "success"}

@api_router.delete("/member/{id}")
async def delete_member(id: int):
    u = await User.get_or_none(id=id)
    if not u: raise HTTPException(404)
    await u.delete()
    return {"status": "success"}

@api_router.get("/settings/list")
async def get_settings_list():
    synced_group_ids = await User.all().distinct().values_list("group_id", flat=True)
    synced_group_ids = [str(gid) for gid in synced_group_ids]
    if not synced_group_ids: return []

    group_name_map = {}
    for bot in get_bots().values():
        if isinstance(bot, Bot):
            try:
                g_list = await bot.get_group_list()
                for g in g_list: group_name_map[str(g['group_id'])] = g['group_name']
            except: pass

    settings_db = await GroupSetting.filter(group_id__in=synced_group_ids).all()
    settings_map = {s.group_id: s for s in settings_db}

    active_eps = await Episode.filter(status__in=[1, 2, 3, 4], project__group_id__in=synced_group_ids).prefetch_related('project', 'translator', 'proofreader', 'typesetter', 'supervisor')
    tasks_map = defaultdict(list)

    today = datetime.now().date()

    for ep in active_eps:
        gid = ep.project.group_id
        stage_text = ""
        user_name = "未分配"
        current_ddl = None

        if ep.status == 1:
            stage_text, user_name = "翻译", ep.translator.name if ep.translator else "未分配"
            current_ddl = ep.ddl_trans
        elif ep.status == 2:
            stage_text, user_name = "校对", ep.proofreader.name if ep.proofreader else "未分配"
            current_ddl = ep.ddl_proof
        elif ep.status == 3:
            stage_text, user_name = "嵌字", ep.typesetter.name if ep.typesetter else "未分配"
            current_ddl = ep.ddl_type
        elif ep.status == 4:
            stage_text, user_name = "监修", ep.supervisor.name if ep.supervisor else "未分配"
            current_ddl = ep.ddl_supervision

        is_overdue = False
        if current_ddl and current_ddl.date() < today:
            is_overdue = True

        tasks_map[gid].append({
            "project_name": ep.project.name,
            "title": ep.title,
            "stage": stage_text,
            "user": user_name,
            "status": ep.status,
            "is_overdue": is_overdue
        })

    result = []
    for gid in synced_group_ids:
        setting = settings_map.get(gid)
        result.append({
            "group_id": gid,
            "group_name": group_name_map.get(gid, f"群{gid}"),
            "enable_broadcast": setting.enable_broadcast if setting else True,
            "broadcast_time": setting.broadcast_time if setting else "10:00",
            "tasks": tasks_map.get(gid, [])
        })
    result.sort(key=lambda x: x['group_id'])
    return result

@api_router.post("/settings/update")
async def update_setting(form: SettingUpdate):
    await GroupSetting.update_or_create(group_id=form.group_id, defaults={"enable_broadcast": form.enable, "broadcast_time": form.time})
    return {"status": "success"}

@api_router.post("/settings/remind_now")
async def remind_now(form: RemindNow):
    await check_and_send_broadcast(form.group_id, is_manual=True)
    return {"status": "success"}
