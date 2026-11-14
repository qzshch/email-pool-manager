import asyncio
import random
import string
import time
from typing import Optional

import httpx

from ..log_manager import log_manager as log
from .parsing import extract_otp_from_text, is_openai_sender
from .tempmail import TEMPMAIL_OTP_TOLERANCE_SECONDS, get_tempmail_received_timestamp


MAILTM_DEFAULT_BASE_URL = "https://api.mail.tm"
MAILTM_CREATE_MAX_ATTEMPTS = 5


def _random_mailtm_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choices(alphabet, k=length))


def _hydra_items(payload: object) -> list:
    """mail.tm 兼容：Accept: application/json 返回裸数组，ld+json 返回 hydra:member 包装。"""
    if isinstance(payload, dict):
        return payload.get("hydra:member", []) or []
    if isinstance(payload, list):
        return payload
    return []


def _pick_mailtm_domain(domains: list) -> Optional[str]:
    for item in domains:
        if not isinstance(item, dict):
            continue
        if item.get("isActive") and not item.get("isPrivate"):
            domain = str(item.get("domain", "")).strip()
            if domain:
                return domain
    return None


async def create_mailtm_inbox(
    base_url: str = MAILTM_DEFAULT_BASE_URL,
    timeout: int = 30,
) -> tuple[Optional[str], Optional[str]]:
    """创建 mail.tm 临时邮箱，返回 (address, token)。

    mail.tm 创建接口有独立节流（实测约 1 个/6s，过快返回 HTTP 429），
    因此带退避重试；批量任务请把并发压低。
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                f"{base_url.rstrip('/')}/domains",
                headers={"Accept": "application/json"},
            )
            if response.status_code != 200:
                log.error(f"[MAILTM] 获取域名失败: HTTP {response.status_code}")
                return None, None
            domain = _pick_mailtm_domain(_hydra_items(response.json()))
            if not domain:
                log.error("[MAILTM] 无可用公开域名")
                return None, None

            address = (
                "".join(random.choices(string.ascii_lowercase, k=12))
                + str(random.randint(100, 999))
                + f"@{domain}"
            )
            password = _random_mailtm_password()
            account_created = False
            for attempt in range(1, MAILTM_CREATE_MAX_ATTEMPTS + 1):
                response = await client.post(
                    f"{base_url.rstrip('/')}/accounts",
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    json={"address": address, "password": password},
                )
                if response.status_code in (200, 201):
                    account_created = True
                    break
                if response.status_code == 429:
                    wait_seconds = min(60, 10 * attempt)
                    log.warning(
                        f"[MAILTM] 创建被限流(HTTP 429)，{wait_seconds}s 后重试 ({attempt}/{MAILTM_CREATE_MAX_ATTEMPTS})"
                    )
                    await asyncio.sleep(wait_seconds)
                    continue
                log.error(f"[MAILTM] 创建账号失败: HTTP {response.status_code} {response.text[:200]}")
                return None, None
            if not account_created:
                log.error("[MAILTM] 创建账号失败: 限流重试耗尽")
                return None, None

            response = await client.post(
                f"{base_url.rstrip('/')}/token",
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json={"address": address, "password": password},
            )
            if response.status_code != 200:
                log.error(f"[MAILTM] 获取收信 token 失败: HTTP {response.status_code}")
                return None, None
            token = str((response.json() or {}).get("token", "")).strip()
            if not token:
                log.error("[MAILTM] 创建邮箱失败: 返回 token 缺失")
                return None, None
            log.success(f"[MAILTM] 创建邮箱成功: {address}")
            return address, token
    except Exception as e:
        log.exception("[MAILTM] 创建邮箱异常", e)
        return None, None


async def get_verification_code_mailtm(
    email: str,
    token: str,
    timeout: int = 120,
    base_url: str = MAILTM_DEFAULT_BASE_URL,
    stop_event=None,
    otp_sent_at: Optional[float] = None,
) -> Optional[str]:
    log.info(f"[MAILTM] 等待验证码... (目标: {email})")
    start_time = time.time()
    seen_ids = set()
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    base = base_url.rstrip("/")
    while time.time() - start_time < timeout:
        if stop_event and stop_event.is_set():
            log.info("[MAILTM] 任务已停止，中断验证码获取")
            return None
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(f"{base}/messages", params={"page": 1}, headers=headers)
            if response.status_code == 401:
                log.error("[MAILTM] 收信 token 已失效")
                return None
            if response.status_code != 200:
                await asyncio.sleep(3)
                continue
            messages = _hydra_items(response.json())
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                msg_timestamp = get_tempmail_received_timestamp(msg)
                if otp_sent_at is not None:
                    min_allowed_timestamp = otp_sent_at - TEMPMAIL_OTP_TOLERANCE_SECONDS
                    if msg_timestamp is None or msg_timestamp <= min_allowed_timestamp:
                        continue
                message_id = str(msg.get("id") or "").strip()
                if not message_id or message_id in seen_ids:
                    continue
                seen_ids.add(message_id)
                sender_obj = msg.get("from")
                sender = str(
                    sender_obj.get("address", "") if isinstance(sender_obj, dict) else sender_obj or ""
                ).lower()
                subject = str(msg.get("subject") or "")
                intro = msg.get("intro") if isinstance(msg.get("intro"), str) else ""
                # 列表项只有摘要，取全文参与提码
                text = ""
                html_text = ""
                try:
                    detail_resp = await client.get(f"{base}/messages/{message_id}", headers=headers)
                    if detail_resp.status_code == 200:
                        detail = detail_resp.json() or {}
                        text = str(detail.get("text") or "")
                        html_value = detail.get("html")
                        if isinstance(html_value, list):
                            html_text = "\n".join(str(item) for item in html_value)
                        elif html_value:
                            html_text = str(html_value)
                except Exception as fetch_error:
                    log.exception("[MAILTM] 读取邮件详情异常", fetch_error)
                content = "\n".join([sender, subject, intro, text, html_text])
                if not is_openai_sender(sender) and "openai" not in content.lower():
                    continue
                code = extract_otp_from_text(content)
                if code:
                    log.success(f"[MAILTM] 获取到验证码: {code}")
                    return code
        except Exception as e:
            log.exception("[MAILTM] 查询收件箱异常", e)
        await asyncio.sleep(3)
    return None
