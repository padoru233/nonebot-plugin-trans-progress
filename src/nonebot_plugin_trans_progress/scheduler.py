from datetime import datetime
from collections import defaultdict
from nonebot import require, logger
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from .models import Episode
from .utils import send_group_message  # 引入通用发送函数

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

# 每天上午 10:00 播报
@scheduler.scheduled_job("cron", hour=10, minute=0)
async def check_deadlines():
    logger.info("开始检查死线...")
    now = datetime.now()

    # 找出所有未完结的任务
    active_eps = await Episode.filter(status__in=[1, 2, 3]).prefetch_related('project', 'translator', 'proofreader', 'typesetter')

    # 按群分组: { group_id: [Message对象列表] }
    alerts = defaultdict(list)

    for ep in active_eps:
        is_overdue = False
        target_user = None
        stage_name = ""
        current_ddl = None

        # 根据状态检查对应的死线
        if ep.status == 1:
            if ep.ddl_trans and ep.ddl_trans < now:
                is_overdue = True
                target_user = ep.translator
                stage_name = "翻译"
                current_ddl = ep.ddl_trans
        elif ep.status == 2:
            if ep.ddl_proof and ep.ddl_proof < now:
                is_overdue = True
                target_user = ep.proofreader
                stage_name = "校对"
                current_ddl = ep.ddl_proof
        elif ep.status == 3:
            if ep.ddl_type and ep.ddl_type < now:
                is_overdue = True
                target_user = ep.typesetter
                stage_name = "嵌字"
                current_ddl = ep.ddl_type

        # 只有超期的才加入播报列表
        if is_overdue:
            date_str = current_ddl.strftime('%m-%d')

            # 使用 Message 对象构建单条消息
            # 格式: ❌ [项目名 话数] 翻译已超期 (12-24) @某人
            line = Message(f"❌ [{ep.project.name} {ep.title}] {stage_name}已超期 ({date_str}) ")

            if target_user:
                line += MessageSegment.at(target_user.qq_id)
            else:
                line += Message("(未分配人员)")

            line += Message("\n") # 换行

            alerts[ep.project.group_id].append(line)

    # 遍历每个群，拼接消息并发送
    for group_id, msg_list in alerts.items():
        if not msg_list:
            continue

        # 构建最终汇总消息
        final_message = Message("⏰ 今日死线催更播报：\n")
        for fragment in msg_list:
            final_message += fragment

        # 调用 utils 中的通用发送函数
        await send_group_message(int(group_id), final_message)
