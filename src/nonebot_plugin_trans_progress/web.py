from datetime import datetime
from typing import List, Optional, Dict, Set
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel

from nonebot import get_bots, logger, get_plugin_config
from nonebot.adapters.onebot.v11 import Message, MessageSegment, Bot

from .models import Project, Episode, User, GroupSetting
from .utils import get_default_ddl, send_group_message
from .config import Config
from .broadcast import check_and_send_broadcast


plugin_config = get_plugin_config(Config)

async def verify_token(x_auth_token: str = Header(..., alias="X-Auth-Token")):
    if x_auth_token != plugin_config.trans_auth_password:
        raise HTTPException(status_code=401, detail="Invalid Password")
    return x_auth_token

api_router = APIRouter(dependencies=[Depends(verify_token)])

# --- Pydantic Models ---
class ProjectCreate(BaseModel):
    name: str
    aliases: List[str] = []
    tags: List[str] = []
    group_id: str
    leader_qq: Optional[str] = None
    default_translator_qq: Optional[str] = None
    default_proofreader_qq: Optional[str] = None
    default_typesetter_qq: Optional[str] = None
    default_supervisor_qq: Optional[str] = None

class ProjectUpdate(BaseModel):
    name: str
    aliases: List[str] = []
    tags: List[str] = []
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

# --- Helpers ---
async def get_db_user(qq, group_id):
    if not qq: return None
    return await User.get_or_none(qq_id=str(qq), group_id=str(group_id))

async def find_bot_for_group(group_id: str) -> Optional[Bot]:
    """遍历所有 Bot，找到在该群内的一个 Bot"""
    all_bots = get_bots()
    for bot in all_bots.values():
        if isinstance(bot, Bot):
            try:
                g_list = await bot.get_group_list()
                if any(str(g['group_id']) == str(group_id) for g in g_list):
                    return bot
            except Exception:
                continue
    return None

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
    projects = await Project.all().prefetch_related('leader', 'default_translator', 'default_proofreader', 'default_typesetter', 'default_supervisor')

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
            "group_id": p.group_id,
            "group_name": real_group_name,
            "leader": {"name": p.leader.name, "qq_id": p.leader.qq_id} if p.leader else None,
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

    await Project.create(
        name=proj.name,
        aliases=proj.aliases,
        tags=proj.tags,
        group_id=gid, group_name=g_name, leader=leader,
        default_translator=d_trans, default_proofreader=d_proof, default_typesetter=d_type,
        default_supervisor=d_super
    )

    msg = Message(f"🔨 挖到新坑啦！新坑开张：{proj.name}")
    if proj.aliases: msg += Message(f" (别名: {', '.join(proj.aliases)})")
    if proj.tags: msg += Message(f"\n🏷️ 标签: {', '.join(proj.tags)}")
    msg += Message("\n")

    targets = []
    if leader: targets.append((leader, "负责人"))
    if d_trans: targets.append((d_trans, "默认翻译"))

    seen_qq = set()
    for user, role in targets:
        if user.qq_id not in seen_qq:
            msg += Message(f"{role}: ") + MessageSegment.at(user.qq_id) + Message(" ")
            seen_qq.add(user.qq_id)
    msg += Message("\n✨ 大家加油！")

    await send_group_message(int(gid), msg)
    return {"status": "success"}

@api_router.put("/project/{id}")
async def update_project(id: int, form: ProjectUpdate):
    p = await Project.get_or_none(id=id)
    if not p: raise HTTPException(404)
    gid = str(p.group_id)
    p.name = form.name
    p.aliases = form.aliases
    p.tags = form.tags

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

@api_router.post("/episode/add")
async def add_episode(ep: EpisodeCreate):
    project = await Project.get_or_none(name=ep.project_name)
    if not project: raise HTTPException(404, "项目不存在")
    gid = str(project.group_id)

    trans = await get_db_user(ep.translator_qq, gid)
    proof = await get_db_user(ep.proofreader_qq, gid)
    type_ = await get_db_user(ep.typesetter_qq, gid)
    super_ = await get_db_user(ep.supervisor_qq, gid)

    # 确保所有 datetime 都是 aware 的
    dt_trans = ensure_aware(ep.ddl_trans)
    dt_proof = ensure_aware(ep.ddl_proof)
    dt_type = ensure_aware(ep.ddl_type)
    dt_super = ensure_aware(ep.ddl_supervision)

    await Episode.create(
        project=project, title=ep.title, status=1,
        translator=trans, proofreader=proof, typesetter=type_, supervisor=super_,
        ddl_trans=dt_trans, ddl_proof=dt_proof, ddl_type=dt_type, ddl_supervision=dt_super
    )

    msg = Message(f"📦 掉落新任务：{project.name} {ep.title}\n")
    if trans: msg += Message("翻译就决定是你了！") + MessageSegment.at(trans.qq_id) + Message(" 冲鸭！")
    else: msg += Message("✍️ 翻译未分锅")

    await send_group_message(int(gid), msg)
    return {"status": "created"}

@api_router.put("/episode/{id}")
async def update_episode(id: int, form: EpisodeUpdate):
    ep = await Episode.get_or_none(id=id).prefetch_related('project', 'project__leader', 'translator', 'proofreader', 'typesetter', 'supervisor')
    if not ep: raise HTTPException(404)
    gid = str(ep.project.group_id)

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

    status_map = {0: '未开始', 1: '翻译', 2: '校对', 3: '嵌字', 4: '监修', 5: '完结'}
    if ep.status != form.status:
        old_s = status_map.get(ep.status, str(ep.status))
        new_s = status_map.get(form.status, str(form.status))
        changes.append(f"状态: {old_s} -> {new_s}")
        if form.status == 1 and new_trans: mentions_qq.add(new_trans.qq_id)
        elif form.status == 2 and new_proof: mentions_qq.add(new_proof.qq_id)
        elif form.status == 3 and new_type: mentions_qq.add(new_type.qq_id)
        elif form.status == 4 and new_super: mentions_qq.add(new_super.qq_id)

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
    ep.status = form.status
    ep.translator = new_trans
    ep.proofreader = new_proof
    ep.typesetter = new_type
    ep.supervisor = new_super
    ep.ddl_trans = new_ddl_trans
    ep.ddl_proof = new_ddl_proof
    ep.ddl_type = new_ddl_type
    ep.ddl_supervision = new_ddl_super
    await ep.save()

    if changes:
        msg = Message(f"📢 注意！[{ep.project.name} {ep.title}] 情报有变：\n")
        for idx, c in enumerate(changes, 1):
            msg += Message(f"{idx}. {c}\n")

        if mentions_qq:
            for qid in mentions_qq:
                msg += MessageSegment.at(qid) + Message(" ")
            msg += Message("上面被点到的同学，请确认一下新的安排哦~ 👀")

        await send_group_message(int(gid), msg)

    return {"status": "success"}

@api_router.delete("/episode/{id}")
async def delete_episode(id: int):
    await Episode.filter(id=id).delete()
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
