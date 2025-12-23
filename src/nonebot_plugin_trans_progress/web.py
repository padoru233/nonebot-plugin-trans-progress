from datetime import datetime
from typing import List, Optional, Dict
from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# NoneBot 依赖
from nonebot import get_bot, logger, get_plugin_config
from nonebot.adapters.onebot.v11 import Message, MessageSegment

# 本地模块 (确保这些文件都在同级目录下)
from .models import Project, Episode, User
from .utils import get_default_ddl, send_group_message
from .config import Config

# 加载配置
plugin_config = get_plugin_config(Config)

# === 鉴权依赖 ===
async def verify_token(x_auth_token: str = Header(..., alias="X-Auth-Token")):
    """
    验证请求头中的密码是否与配置文件一致
    """
    if x_auth_token != plugin_config.trans_auth_password:
        raise HTTPException(status_code=401, detail="Invalid Password")
    return x_auth_token

# 主路由 (不加锁，用于加载 HTML)
app = APIRouter()

# API 子路由 (加锁，用于数据交互)
api_router = APIRouter(dependencies=[Depends(verify_token)])

# --- Pydantic Models ---
class ProjectCreate(BaseModel):
    name: str
    alias: Optional[str] = None
    group_id: str
    leader_qq: Optional[str] = None
    default_translator_qq: Optional[str] = None
    default_proofreader_qq: Optional[str] = None
    default_typesetter_qq: Optional[str] = None

class ProjectUpdate(BaseModel):
    name: str
    alias: Optional[str] = None
    leader_qq: Optional[str] = None
    default_translator_qq: Optional[str] = None
    default_proofreader_qq: Optional[str] = None
    default_typesetter_qq: Optional[str] = None

class EpisodeCreate(BaseModel):
    project_name: str
    title: str
    translator_qq: Optional[str] = None
    proofreader_qq: Optional[str] = None
    typesetter_qq: Optional[str] = None
    ddl_trans: Optional[datetime] = None
    ddl_proof: Optional[datetime] = None
    ddl_type: Optional[datetime] = None

class EpisodeUpdate(BaseModel):
    title: str
    status: int
    translator_qq: Optional[str] = None
    proofreader_qq: Optional[str] = None
    typesetter_qq: Optional[str] = None
    ddl_trans: Optional[datetime] = None
    ddl_proof: Optional[datetime] = None
    ddl_type: Optional[datetime] = None

class MemberUpdate(BaseModel):
    name: str

class SyncGroupModel(BaseModel):
    group_id: str

# --- Helpers ---
async def get_db_user(qq, group_id):
    if not qq: return None
    return await User.get_or_none(qq_id=qq, group_id=group_id)

# --- Routes (无需鉴权) ---

@app.get("/", response_class=HTMLResponse)
async def index_page():
    import os
    with open(os.path.join(os.path.dirname(__file__), "templates", "index.html"), "r", encoding="utf-8") as f:
        return f.read()

# --- Routes (需要鉴权 - 挂载到 api_router) ---

# === 获取 Bot 加入的所有群 (用于同步弹窗) ===
@api_router.get("/groups/all")
async def get_all_bot_groups():
    try:
        bot = get_bot()
        group_list = await bot.get_group_list()
        # 返回格式: [{"group_id": "123", "group_name": "某群"}]
        return [{"group_id": str(g['group_id']), "group_name": g['group_name']} for g in group_list]
    except Exception as e:
        logger.error(f"获取Bot群列表失败: {e}")
        return []

# === 获取数据库中已存在的群 (用于新建项目，筛选后的) ===
@api_router.get("/groups/db")
async def get_db_groups():
    try:
        bot = get_bot()
        all_groups = await bot.get_group_list()

        # 获取数据库中所有出现过的 group_id
        db_group_ids = set(await User.all().distinct().values_list("group_id", flat=True))

        filtered = []
        for g in all_groups:
            gid = str(g['group_id'])
            # 只有数据库里有人的群才返回
            if gid in db_group_ids:
                filtered.append({"group_id": gid, "group_name": g['group_name']})
        return filtered
    except Exception as e:
        logger.error(f"获取DB群列表失败: {e}")
        return []

@api_router.get("/projects")
async def get_projects():
    # 修复 NameError: Project 未定义的问题
    projects = await Project.all().prefetch_related('leader', 'default_translator', 'default_proofreader', 'default_typesetter')
    result = []
    for p in projects:
        eps = await Episode.filter(project=p).prefetch_related('translator', 'proofreader', 'typesetter').order_by('id').all()
        ep_list = []
        for e in eps:
            ep_list.append({
                "id": e.id, "title": e.title, "status": e.status,
                "ddl_trans": e.ddl_trans, "ddl_proof": e.ddl_proof, "ddl_type": e.ddl_type,
                "translator": {"name": e.translator.name, "qq_id": e.translator.qq_id} if e.translator else None,
                "proofreader": {"name": e.proofreader.name, "qq_id": e.proofreader.qq_id} if e.proofreader else None,
                "typesetter": {"name": e.typesetter.name, "qq_id": e.typesetter.qq_id} if e.typesetter else None,
            })

        defaults = {
            "trans": p.default_translator.qq_id if p.default_translator else "",
            "proof": p.default_proofreader.qq_id if p.default_proofreader else "",
            "type": p.default_typesetter.qq_id if p.default_typesetter else "",
        }

        result.append({
            "id": p.id, "name": p.name, "alias": p.alias, "group_id": p.group_id, "group_name": p.group_name,
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
    try:
        bot = get_bot()
        gid = int(data.group_id)
        g_info = await bot.get_group_info(group_id=gid)
        g_name = g_info.get("group_name", "未知群聊")
        await Project.filter(group_id=data.group_id).update(group_name=g_name)
        member_list = await bot.get_group_member_list(group_id=gid)
    except Exception as e:
        raise HTTPException(500, f"Bot通讯失败: {e}")

    count = 0
    for m in member_list:
        qq = str(m['user_id'])
        name = m['card'] or m['nickname'] or f"用户{qq}"
        await User.update_or_create(qq_id=qq, group_id=data.group_id, defaults={"name": name})
        count += 1
    return {"status": "success", "count": count, "group_name": g_name}

@api_router.post("/project/create")
async def create_project(proj: ProjectCreate):
    if await Project.filter(name=proj.name).exists():
        raise HTTPException(400, "项目名已存在")

    g_name = "未同步"
    try:
        info = await get_bot().get_group_info(group_id=int(proj.group_id))
        g_name = info.get("group_name", "未同步")
    except: pass

    gid = proj.group_id
    leader = await get_db_user(proj.leader_qq, gid)

    # 自动录入组长逻辑
    if not leader:
        try:
            bot = get_bot()
            # 如果指定了leader_qq但数据库没有，尝试获取名字录入
            if proj.leader_qq:
                try:
                    u_info = await bot.get_group_member_info(group_id=int(gid), user_id=int(proj.leader_qq))
                    u_name = u_info['card'] or u_info['nickname']
                    leader, _ = await User.update_or_create(qq_id=proj.leader_qq, group_id=gid, defaults={"name": u_name})
                except: pass
            else:
                # 没指定，找群主
                mlist = await bot.get_group_member_list(group_id=int(gid))
                owner = next((m for m in mlist if m['role'] == 'owner'), None)
                if owner:
                    o_qq = str(owner['user_id'])
                    o_name = owner['card'] or owner['nickname']
                    leader, _ = await User.update_or_create(qq_id=o_qq, group_id=gid, defaults={"name": o_name})
        except: pass

    d_trans = await get_db_user(proj.default_translator_qq, gid)
    d_proof = await get_db_user(proj.default_proofreader_qq, gid)
    d_type = await get_db_user(proj.default_typesetter_qq, gid)

    await Project.create(
        name=proj.name, alias=proj.alias, group_id=gid, group_name=g_name, leader=leader,
        default_translator=d_trans, default_proofreader=d_proof, default_typesetter=d_type
    )

    # === 构建多 At 消息 ===
    msg = Message(f"🎉 新坑开张：{proj.name}")
    if proj.alias: msg += Message(f" ({proj.alias})")
    msg += Message("\n")

    targets = []
    if leader: targets.append((leader, "负责人"))
    if d_trans: targets.append((d_trans, "默认翻译"))
    if d_proof: targets.append((d_proof, "默认校对"))
    if d_type: targets.append((d_type, "默认嵌字"))

    seen_qq = set()
    for user, role in targets:
        if user.qq_id not in seen_qq:
            msg += Message(f"{role}: ") + MessageSegment.at(user.qq_id) + Message(" ")
            seen_qq.add(user.qq_id)

    msg += Message("\n大家加油！")

    await send_group_message(int(gid), msg)
    return {"status": "success"}

@api_router.put("/project/{id}")
async def update_project(id: int, form: ProjectUpdate):
    p = await Project.get_or_none(id=id)
    if not p: raise HTTPException(404)
    gid = p.group_id
    p.name = form.name
    p.alias = form.alias
    p.leader = await get_db_user(form.leader_qq, gid)
    p.default_translator = await get_db_user(form.default_translator_qq, gid)
    p.default_proofreader = await get_db_user(form.default_proofreader_qq, gid)
    p.default_typesetter = await get_db_user(form.default_typesetter_qq, gid)
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
    # 修复 NameError: project not defined
    project = await Project.get_or_none(name=ep.project_name)
    if not project: raise HTTPException(404, "项目不存在")
    gid = project.group_id

    trans = await get_db_user(ep.translator_qq, gid)
    proof = await get_db_user(ep.proofreader_qq, gid)
    type_ = await get_db_user(ep.typesetter_qq, gid)

    await Episode.create(
        project=project, title=ep.title, status=1,
        translator=trans, proofreader=proof, typesetter=type_,
        ddl_trans=ep.ddl_trans, ddl_proof=ep.ddl_proof, ddl_type=ep.ddl_type
    )

    # 构建消息
    msg = Message(f"📢 新任务：{project.name} {ep.title}\n")
    if trans:
        msg += Message("请 ") + MessageSegment.at(trans.qq_id) + Message(" 接翻译")
        if ep.ddl_trans: msg += Message(f" (死线: {ep.ddl_trans.strftime('%m-%d')})")
    else:
        msg += Message("⚠️ 翻译未分配")

    await send_group_message(int(gid), msg)
    return {"status": "created"}

@api_router.put("/episode/{id}")
async def update_episode(id: int, form: EpisodeUpdate):
    # 修复 prefetch 写法
    ep = await Episode.get_or_none(id=id).prefetch_related('project', 'project__leader', 'translator', 'proofreader', 'typesetter')
    if not ep: raise HTTPException(404)
    gid = int(ep.project.group_id)

    old_status = ep.status
    ep.title = form.title
    ep.status = form.status

    ep.translator = await get_db_user(form.translator_qq, str(gid))
    ep.proofreader = await get_db_user(form.proofreader_qq, str(gid))
    ep.typesetter = await get_db_user(form.typesetter_qq, str(gid))

    ep.ddl_trans = form.ddl_trans
    ep.ddl_proof = form.ddl_proof
    ep.ddl_type = form.ddl_type

    await ep.save()

    # 状态更新播报
    if form.status != old_status:
        status_str = ['未','翻','校','嵌','完']
        msg = Message(f"🔄 [{ep.project.name} {ep.title}] 进度更新：{status_str[old_status]}->{status_str[form.status]}\n")

        target_qq = None
        tip = ""
        ddl = None

        if form.status == 2: # 翻->校
            target_qq = ep.proofreader.qq_id if ep.proofreader else None
            tip = "请接校对"
            ddl = ep.ddl_proof
        elif form.status == 3: # 校->嵌
            target_qq = ep.typesetter.qq_id if ep.typesetter else None
            tip = "请接嵌字"
            ddl = ep.ddl_type
        elif form.status == 4: # 嵌->完
            if ep.project.leader: target_qq = ep.project.leader.qq_id
            tip = "全流程完结，请查收"

        if target_qq:
            msg += Message("请 ") + MessageSegment.at(target_qq) + Message(f" {tip}")
            if ddl: msg += Message(f" (死线: {ddl.strftime('%m-%d')})")
        else:
            if form.status < 4: msg += Message("⚠️ 下一阶段未分配人员")
            else: msg += Message("🎉 全流程完结！")

        await send_group_message(gid, msg)

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
    await u.save()
    return {"status": "success"}

@api_router.delete("/member/{id}")
async def delete_member(id: int):
    u = await User.get_or_none(id=id)
    if not u: raise HTTPException(404)
    # 解除关联
    await Episode.filter(translator=u).update(translator_id=None)
    await Episode.filter(proofreader=u).update(proofreader_id=None)
    await Episode.filter(typesetter=u).update(typesetter_id=None)
    await Project.filter(leader=u).update(leader_id=None)
    await Project.filter(default_translator=u).update(default_translator_id=None)
    await Project.filter(default_proofreader=u).update(default_proofreader_id=None)
    await Project.filter(default_typesetter=u).update(default_typesetter_id=None)
    await u.delete()
    return {"status": "success"}

# 挂载鉴权路由
app.include_router(api_router)
