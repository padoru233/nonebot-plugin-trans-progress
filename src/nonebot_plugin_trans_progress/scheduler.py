from datetime import datetime
from zoneinfo import ZoneInfo

from nonebot import require, logger

from .models import GroupSetting
from .broadcast import check_and_send_broadcast

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

BROADCAST_TIMEZONE = ZoneInfo("Asia/Shanghai")

# 每分钟执行一次
@scheduler.scheduled_job(
    "cron",
    minute="*",
    timezone=BROADCAST_TIMEZONE,
    id="trans-progress-broadcast-check",
    max_instances=1,
    coalesce=True,
    misfire_grace_time=60,
)
async def check_broadcast_time():
    now = datetime.now(BROADCAST_TIMEZONE)
    current_time_str = now.strftime("%H:%M")

    logger.debug(f"[Scheduler] 定时任务触发检查，当前时间: {current_time_str}")

    target_settings = await GroupSetting.filter(
        enable_broadcast=True,
        broadcast_time=current_time_str
    ).all()

    if target_settings:
        logger.info(f"⏰ 触发定时播报: {current_time_str}, 共 {len(target_settings)} 个群")
        for setting in target_settings:
            await check_and_send_broadcast(
                setting.group_id, is_manual=False, now=now
            )

    else:
        logger.debug(f"[Scheduler] 当前时间 {current_time_str} 没有需要播报的群")
