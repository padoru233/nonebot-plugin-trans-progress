"""
TODO: 预留出中间件,对接moeflow-backend
"""
import httpx
from typing import Any, Dict, Optional
from nonebot import logger, get_plugin_config
from .config import Config

plugin_config = get_plugin_config(Config)

class MoeFlowMiddleware:
    """
    Moeflow Backend HTTP 客户端中间件
    负责与外部 FastAPI 后端进行通讯
    """

    def __init__(self):
        self.base_url = plugin_config.moeflow_api_url.rstrip("/")
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {plugin_config.moeflow_api_token}" if plugin_config.moeflow_api_token else ""
        }
        self.timeout = plugin_config.moeflow_timeout

    async def call_api(self, endpoint: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        通用的 API 调用方法
        :param endpoint: API 路径，例如 "/api/v1/translate"
        :param payload: 发送的 JSON 数据
        :return: 成功返回 JSON 字典，失败返回 None
        """
        # 确保 endpoint 以 / 开头
        if not endpoint.startswith("/"):
            endpoint = "/" + endpoint

        url = f"{self.base_url}{endpoint}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                logger.debug(f"[MoeFlow] 正在请求: {url} | 数据: {payload}")

                resp = await client.post(url, json=payload, headers=self.headers)

                # 检查 HTTP 状态码
                if resp.status_code != 200:
                    logger.error(f"[MoeFlow] 请求失败: {resp.status_code} - {resp.text}")
                    return None

                # 解析返回结果
                result = resp.json()
                logger.debug(f"[MoeFlow] 请求成功，响应: {result}")
                return result

        except httpx.TimeoutException:
            logger.error(f"[MoeFlow] 请求超时！(URL: {url})")
            return None
        except httpx.ConnectError:
            logger.error(f"[MoeFlow] 连接失败，请检查后端地址是否正确！(URL: {url})")
            return None
        except Exception as e:
            logger.error(f"[MoeFlow] 未知错误: {e}")
            return None


# 单例模式：全局只用这一个实例
moeflow_client = MoeFlowMiddleware()
