from datetime import datetime
from typing import List, Optional, Dict, Set
from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# NoneBot 依赖
from nonebot import get_bot, logger, get_plugin_config
from nonebot.adapters.onebot.v11 import Message, MessageSegment

# 本地模块
from .models import Project, Episode, User
from .utils import get_default_ddl, send_group_message
from .config import Config

# 加载配置
plugin_config = get_plugin_config(Config)

# === 鉴权依赖 ===
async def verify_token(x_auth_token: str = Header(..., alias="X-Auth-Token")):
    if x_auth_token != plugin_config.trans_auth_password:
        raise HTTPException(status_code=401, detail="Invalid Password")
    return x_auth_token

# 主路由 (不加锁)
app = APIRouter()

# API 子路由 (加锁)
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

# --- Routes (无鉴权) ---

@app.get("/", response_class=HTMLResponse)
async def index_page():
    import os
    with open(os.path.join(os.path.dirname(__file__), "templates", "index.html"), "r", encoding="utf-8") as f:
        return f.read()

# --- Routes (有鉴权) ---

@api_router.get("/groups/all")
async def get_all_bot_groups():
    try:
        bot = get_bot()
        group_list = await bot.get_group_list()
        return [{"group_id": str(g['group_id']), "group_name": g['group_name']} for g in group_list]
    except Exception as e:
        logger.error(f"获取Bot群列表失败: {e}")
        return []

@api_router.get("/groups/db")
async def get_db_groups():
    try:
        bot = get_bot()
        all_groups = await bot.get_group_list()
        db_group_ids = set(await User.all().distinct().values_list("group_id", flat=True))
        filtered = []
        for g in all_groups:
            gid = str(g['group_id'])
            if gid in db_group_ids:
                filtered.append({"group_id": gid, "group_name": g['group_name']})
        return filtered
    except Exception as e:
        logger.error(f"获取DB群列表失败: {e}")
        return []

@api_router.get("/projects")
async def get_projects():
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

    if not leader:
        try:
            bot = get_bot()
            if proj.leader_qq:
                try:
                    u_info = await bot.get_group_member_info(group_id=int(gid), user_id=int(proj.leader_qq))
                    u_name = u_info['card'] or u_info['nickname']
                    leader, _ = await User.update_or_create(qq_id=proj.leader_qq, group_id=gid, defaults={"name": u_name})
                except: pass
            else:
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

    msg = Message(f"📢 新任务：{project.name} {ep.title}\n")
    if trans:
        msg += Message("请 ") + MessageSegment.at(trans.qq_id) + Message(" 接翻译")
        if ep.ddl_trans: msg += Message(f" (死线: {ep.ddl_trans.strftime('%m-%d')})")
    else:
        msg += Message("⚠️ 翻译未分配")

    await send_group_message(int(gid), msg)
    return {"status": "created"}

# === 核心逻辑：编辑进度 + 智能播报 ===
@api_router.put("/episode/{id}")
async def update_episode(id: int, form: EpisodeUpdate):
    # 1. 预加载所有相关对象
    ep = await Episode.get_or_none(id=id).prefetch_related(
        'project', 'project__leader', 'translator', 'proofreader', 'typesetter'
    )
    if not ep: raise HTTPException(404)
    gid = int(ep.project.group_id)

    # 2. 准备新的人员对象 (为了对比)
    new_trans = await get_db_user(form.translator_qq, str(gid))
    new_proof = await get_db_user(form.proofreader_qq, str(gid))
    new_type = await get_db_user(form.typesetter_qq, str(gid))

    # 3. 记录变更点
    changes: List[str] = []
    at_qq_set: Set[str] = set() # 待At的人员集合

    # 辅助对比函数
    def check_field_change(label, old_val, new_val):
        if old_val != new_val:
            changes.append(f"{label}: {old_val} -> {new_val}")
            return True
        return False

    def fmt_date(d):
        return d.strftime('%m-%d') if d else "无"

    def fmt_user_name(u):
        return u.name if u else "未分配"

    # --- 对比人员 ---
    if (ep.translator and ep.translator.id) != (new_trans and new_trans.id):
        changes.append(f"翻译: {fmt_user_name(ep.translator)} -> {fmt_user_name(new_trans)}")
        if new_trans: at_qq_set.add(new_trans.qq_id)

    if (ep.proofreader and ep.proofreader.id) != (new_proof and new_proof.id):
        changes.append(f"校对: {fmt_user_name(ep.proofreader)} -> {fmt_user_name(new_proof)}")
        if new_proof: at_qq_set.add(new_proof.qq_id)

    if (ep.typesetter and ep.typesetter.id) != (new_type and new_type.id):
        changes.append(f"嵌字: {fmt_user_name(ep.typesetter)} -> {fmt_user_name(new_type)}")
        if new_type: at_qq_set.add(new_type.qq_id)

    # --- 对比日期 (如果日期变了，At当前负责人) ---
    # 这里的逻辑是：如果该工序日期变了，且该工序有人，就At他
    if fmt_date(ep.ddl_trans) != fmt_date(form.ddl_trans):
        changes.append(f"翻译DDL: {fmt_date(ep.ddl_trans)} -> {fmt_date(form.ddl_trans)}")
        # 优先At新负责人，如果没有变动则At旧负责人
        target = new_trans if new_trans else ep.translator
        if target: at_qq_set.add(target.qq_id)

    if fmt_date(ep.ddl_proof) != fmt_date(form.ddl_proof):
        changes.append(f"校对DDL: {fmt_date(ep.ddl_proof)} -> {fmt_date(form.ddl_proof)}")
        target = new_proof if new_proof else ep.proofreader
        if target: at_qq_set.add(target.qq_id)

    if fmt_date(ep.ddl_type) != fmt_date(form.ddl_type):
        changes.append(f"嵌字DDL: {fmt_date(ep.ddl_type)} -> {fmt_date(form.ddl_type)}")
        target = new_type if new_type else ep.typesetter
        if target: at_qq_set.add(target.qq_id)

    # --- 对比状态 (状态流转 At 下一棒) ---
    status_map = ['未开始','翻译','校对','嵌字','完结']
    if ep.status != form.status:
        changes.append(f"状态: {status_map[ep.status]} -> {status_map[form.status]}")
        # 根据新状态 At 相应人员
        if form.status == 1 and new_trans: at_qq_set.add(new_trans.qq_id)
        elif form.status == 2 and new_proof: at_qq_set.add(new_proof.qq_id)
        elif form.status == 3 and new_type: at_qq_set.add(new_type.qq_id)
        elif form.status == 4:
            # 完结 At 组长
            if ep.project.leader: at_qq_set.add(ep.project.leader.qq_id)

    # 4. 执行数据库更新
    ep.title = form.title
    ep.status = form.status
    ep.translator = new_trans
    ep.proofreader = new_proof
    ep.typesetter = new_type
    ep.ddl_trans = form.ddl_trans
    ep.ddl_proof = form.ddl_proof
    ep.ddl_type = form.ddl_type

    await ep.save()

    # 5. 发送播报 (如果有变动)
    if changes:
        msg = Message(f"📝 [{ep.project.name} {ep.title}] 信息更新：\n")
        # 添加变更列表
        for idx, change in enumerate(changes, 1):
            msg += Message(f"{idx}. {change}\n")

        # 添加 At 列表
        if at_qq_set:
            msg += Message("请 ")
            for qq in at_qq_set:
                msg += MessageSegment.at(qq) + Message(" ")
            msg += Message("留意变动")

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
    await Episode.filter(translator=u).update(translator_id=None)
    await Episode.filter(proofreader=u).update(proofreader_id=None)
    await Episode.filter(typesetter=u).update(typesetter_id=None)
    await Project.filter(leader=u).update(leader_id=None)
    await Project.filter(default_translator=u).update(default_translator_id=None)
    await Project.filter(default_proofreader=u).update(default_proofreader_id=None)
    await Project.filter(default_typesetter=u).update(default_typesetter_id=None)
    await u.delete()
    return {"status": "success"}

app.include_router(api_router)
