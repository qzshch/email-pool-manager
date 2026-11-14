# -*- coding: utf-8 -*-
"""邮箱池探活：mail.tm / tempmail.lol / IMAP 三类存活判定。

约定：返回 (alive: bool, detail: str, new_token: Optional[str])。
new_token 仅在探活过程中换取到新收信凭据时非空，调用方应回写池表（兼做保活）。
"""
from typing import Optional

import httpx
from imap_tools import MailBox

from ..log_manager import log_manager as log
from .mailtm import MAILTM_DEFAULT_BASE_URL, mailtm_login


async def check_mailtm_alive(
    base_url: str,
    address: str,
    password: str,
) -> tuple[bool, str, Optional[str]]:
    """mail.tm 探活：重登（200=alive，401/403=账号已删或凭据失效）+ 域名在池检查。"""
    if not address or not password:
        return False, "缺少 address/password", None
    domain = address.rsplit("@", 1)[-1].lower()

    token = await mailtm_login(base_url or MAILTM_DEFAULT_BASE_URL, address, password)
    if not token:
        return False, "登录失败（账号可能已删除或被禁用）", None

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{(base_url or MAILTM_DEFAULT_BASE_URL).rstrip('/')}/domains",
                headers={"Accept": "application/json"},
            )
        if response.status_code == 200:
            payload = response.json()
            items = payload.get("hydra:member", []) if isinstance(payload, dict) else (payload or [])
            domains = {
                str(item.get("domain", "")).lower()
                for item in items or []
                if isinstance(item, dict) and item.get("isActive")
            }
            if domains and domain not in domains:
                return False, f"域名已下线: {domain}", None
    except Exception as e:
        # 域名检查失败不影响存活判定（登录已成功）
        log.warning(f"[EMAILPOOL] mail.tm 域名检查异常（忽略）: {e}")
    return True, "alive", token


async def check_tempmail_alive(
    base_url: str,
    token: str,
) -> tuple[bool, str, Optional[str]]:
    """tempmail.lol 探活：GET /inbox?token 判定。该服务邮箱天然短时效，判死属预期。"""
    if not token:
        return False, "缺少 token", None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{base_url.rstrip('/')}/inbox",
                params={"token": token},
                headers={"Accept": "application/json"},
            )
        if response.status_code == 200:
            return True, "alive", None
        if response.status_code in (401, 403, 404):
            return False, f"inbox 已过期/失效（HTTP {response.status_code}）", None
        return False, f"HTTP {response.status_code}", None
    except Exception as e:
        return False, f"异常: {e}", None


def check_imap_alive(
    imap_host: str,
    imap_port: int,
    imap_user: str,
    imap_pass: str,
) -> tuple[bool, str, Optional[str]]:
    """IMAP 探活：登录+登出判定（只验证凭据，不读邮件内容）。同步接口。"""
    if not (imap_host and imap_user and imap_pass):
        return False, "缺少 host/user/password", None
    try:
        mailbox = MailBox(imap_host, port=imap_port or 993)
        with mailbox.login(imap_user, imap_pass, initial_folder_size_check=False):
            pass
        return True, "alive", None
    except Exception as e:
        return False, f"登录失败: {e}", None
