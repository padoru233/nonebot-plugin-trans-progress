import pytz
from datetime import datetime
from nonebot import require, logger
from .models import GroupSetting
from .broadcast import check_and_send_broadcast # 引入刚才写的新文件

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

# 每分钟执行一次
@scheduler.scheduled_job("cron", minute="*")
async def check_broadcast_time():
    # 强制指定为北京时间，防止服务器时区不同步
    tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(tz)
    current_time_str = now.strftime("%H:%M")

    logger.debug(f"[Scheduler] 定时任务触发检查，当前时间: {current_time_str}")

    target_settings = await GroupSetting.filter(
        enable_broadcast=True,
        broadcast_time=current_time_str
    ).all()

    if target_settings:
        logger.info(f"⏰ 触发定时播报: {current_time_str}, 共 {len(target_settings)} 个群")
        for setting in target_settings:
            await check_and_send_broadcast(setting.group_id, is_manual=False)

    else:
        logger.debug(f"[Scheduler] 当前时间 {current_time_str} 没有需要播报的群")
