from nonebot import get_driver, get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    # 数据库链接格式: postgres://用户名:密码@地址:端口/数据库名
    trans_db_url: str = "postgres://postgres:password@127.0.0.1:5432/trans_db"
    # Moeflow Backend 后端 API 地址，不带尾部斜杠
    moeflow_api_url: str = "http://127.0.0.1:8000"
    # Moeflow 前端地址，不带尾部斜杠；用于跳转至萌翻登录和授权页
    moeflow_web_url: str | None = None
    # Moeflow 中为本插件配置的授权客户端
    trans_moeflow_client_id: str = "trans-progress"
    trans_moeflow_client_secret: str | None = None
    # 必须与 Moeflow BOT_AUTHORIZATION_CLIENTS 中登记的回调地址完全一致
    trans_moeflow_redirect_uri: str | None = None
    # 用于签名 Bot 后台浏览器会话，必须是随机的高强度密钥
    trans_auth_session_secret: str | None = None
    # 允许访问后台的萌翻用户 ID；萌翻站点管理员始终允许访问
    trans_moeflow_allowed_subjects: list[str] = []
    # 萌翻团队 ID -> 该团队管理员可管理的 QQ 群号；用于限定团队管理员的可见范围
    trans_moeflow_team_groups: dict[str, list[str]] = {}
    # 萌翻服务器调用 Bot webhook 时使用的令牌（团队设置中的机器人鉴权 Token）
    trans_webhook_token: str | None = None
    # Bot 后台会话存活时间（秒）
    trans_auth_session_max_age: int = 28800
    # 是否公开漫画进度目录 JSON
    trans_public_catalog_enabled: bool = False
    # 允许读取公开目录的前端来源
    trans_public_catalog_allow_origin: str = "https://keli.love"
    # CDN 可缓存公开目录的秒数
    trans_public_catalog_cache_seconds: int = 60
    # CDN 可缓存公开目录的秒数，需大于等于浏览器缓存时间
    trans_public_catalog_cdn_cache_seconds: int = 300
    # Makers 私有目录同步接口；不配置时仅生成本地静态目录
    trans_public_catalog_sync_url: str | None = None
    # Makers 私有目录同步接口的 Bearer Token
    trans_public_catalog_sync_token: str | None = None


# 配置加载
plugin_config: Config = get_plugin_config(Config)
global_config = get_driver().config

# 全局名称
NICKNAME: str = next(iter(global_config.nickname), "")
