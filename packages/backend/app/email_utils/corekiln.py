# -*- coding: utf-8 -*-
"""corekiln 自有域名邮箱客户端（Cloudflare Email Worker + D1）。

地址由 catch-all 承接，无需远端"创建"；此处 register 仅做管理登记。
鉴权：Bearer token（Worker secret EMAIL_POOL_TOKEN）。
"""
from typing import Optional

import httpx

from ..log_manager import log_manager as log


async def corekiln_health(base_url: str, timeout: int = 10) -> bool:
    if not base_url:
        return False
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{base_url.rstrip('/')}/health")
        return resp.status_code == 200
    except Exception:
        return False


async def corekiln_register_address(
    base_url: str, token: str, address: str, timeout: int = 20
) -> tuple[bool, str]:
    if not (base_url and token and address):
        return False, "缺少 base_url/token/address"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{base_url.rstrip('/')}/v1/addresses",
                headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
                json={"address": address},
            )
        if resp.status_code in (200, 201):
            return True, "已登记"
        if resp.status_code == 401:
            return False, "Worker token 无效"
        return False, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, f"异常: {e}"


async def corekiln_list_messages(
    base_url: str, token: str, address: str = "", limit: int = 20, timeout: int = 20
) -> tuple[bool, Optional[list], str]:
    if not (base_url and token):
        return False, None, "未配置 corekiln_base_url/corekiln_api_token"
    try:
        params = {"limit": limit}
        if address:
            params["address"] = address
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                f"{base_url.rstrip('/')}/v1/messages",
                headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
                params=params,
            )
        if resp.status_code == 200:
            data = resp.json() or {}
            return True, data.get("items") or [], "ok"
        if resp.status_code == 401:
            return False, None, "Worker token 无效"
        return False, None, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, None, f"异常: {e}"


async def corekiln_get_message(
    base_url: str, token: str, message_id: int, timeout: int = 20
) -> tuple[bool, Optional[dict], str]:
    if not (base_url and token):
        return False, None, "未配置 corekiln_base_url/corekiln_api_token"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                f"{base_url.rstrip('/')}/v1/messages/{int(message_id)}",
                headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
            )
        if resp.status_code == 200:
            return True, (resp.json() or {}).get("item"), "ok"
        if resp.status_code == 404:
            return False, None, "邮件不存在"
        if resp.status_code == 401:
            return False, None, "Worker token 无效"
        return False, None, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, None, f"异常: {e}"
