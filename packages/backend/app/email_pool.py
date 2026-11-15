# -*- coding: utf-8 -*-
"""邮箱池服务：批量注册、托管、探活、自动补池、注册联动捕获、定时调度。

- mail.tm 探活 = 重登（兼做保活，新 token 回写池表）
- tempmail.lol 邮箱天然短时效，探活判死属预期
- 批量创建串行执行（mail.tm 建号节流 ~6s/个，退避内置在 mailtm.py）
"""
import asyncio
from datetime import datetime
from typing import Optional

from .config import get_config
from .database import EmailPoolItem, db
from .email_utils.mailtm import (
    MAILTM_DEFAULT_BASE_URL,
    create_mailtm_account,
    mailtm_delete_account,
)
from .email_utils.pool_health import check_imap_alive, check_mailtm_alive, check_tempmail_alive
from .email_utils.tempmail import create_tempmail_inbox
from .log_manager import log_manager as log

TEMPMAIL_DEFAULT_BASE_URL = "https://api.tempmail.lol/v2"
VALID_PROVIDERS = ("mail_tm", "tempmail_lol", "imap")
MAX_BATCH_CREATE = 50
MAX_REPLENISH_PER_CYCLE = 10

_task_state = {"running": False, "kind": "", "done": 0, "total": 0, "success": 0, "fail": 0}
_scheduler_task: Optional[asyncio.Task] = None
# 全局建号串行锁：mail.tm 创建接口有节流，平台任务与池任务不能并发建号
_create_lock = asyncio.Lock()


def get_task_status() -> dict:
    return dict(_task_state)


def _insert_item(
    provider: str,
    address: str,
    token: str = "",
    password: str = "",
    account_id: str = "",
    purpose: str = "",
    status: str = "active",
    detail: str = "",
    imap_host: str = "",
    imap_port: int = 993,
) -> bool:
    with db.get_session() as session:
        exists = (
            session.query(EmailPoolItem)
            .filter(EmailPoolItem.provider == provider, EmailPoolItem.address == address)
            .first()
        )
        if exists:
            return False
        session.add(
            EmailPoolItem(
                provider=provider,
                address=address,
                token=token or "",
                password=password or "",
                mailtm_account_id=account_id or "",
                purpose=purpose or "",
                status=status,
                status_detail=detail,
                imap_host=imap_host or "",
                imap_port=imap_port or 993,
            )
        )
    return True


def capture_email(provider: str, address: str, token: str, password: str = "", account_id: str = "") -> bool:
    """注册流程创建的临时邮箱自动入池（幂等，绝不抛错打断注册）。"""
    try:
        cfg = get_config()
        if not cfg.get("email_pool_auto_capture", True):
            return False
        if provider not in ("mail_tm", "tempmail_lol") or not address:
            return False
        ok = _insert_item(
            provider, address, token=token or "", password=password or "",
            account_id=account_id or "", detail="注册流程自动捕获",
        )
        if ok:
            log.info(f"[EMAILPOOL] 已自动入池: {address}")
        return ok
    except Exception as e:
        log.warning(f"[EMAILPOOL] 自动入池失败 {address}: {e}")
        return False


async def create_one(provider: str, purpose: str = "", detail: str = "手动创建") -> dict:
    """创建单个邮箱并入池（全局串行，遵守 mail.tm 建号节流）。

    返回 {"ok": bool, "address": str|None, "message": str}。
    平台引擎（mail_tm / tempmail_lol）与池批量创建都走这里。
    """
    cfg = get_config()
    if provider == "mail_tm":
        async with _create_lock:
            address, password, token, account_id = await create_mailtm_account(
                cfg.get("mailtm_base_url", MAILTM_DEFAULT_BASE_URL)
            )
        if not (address and token):
            return {"ok": False, "address": None, "message": "mail.tm 创建失败"}
        _insert_item("mail_tm", address, token=token, password=password or "",
                     account_id=account_id or "", purpose=purpose, detail=detail)
        return {"ok": True, "address": address, "message": "ok"}
    if provider == "tempmail_lol":
        async with _create_lock:
            address, token = await create_tempmail_inbox(
                cfg.get("tempmail_base_url", TEMPMAIL_DEFAULT_BASE_URL)
            )
        if not (address and token):
            return {"ok": False, "address": None, "message": "tempmail.lol 创建失败"}
        _insert_item("tempmail_lol", address, token=token, purpose=purpose, detail=detail)
        return {"ok": True, "address": address, "message": "ok"}
    return {"ok": False, "address": None, "message": f"不支持的 provider: {provider}"}


async def batch_create(provider: str, count: int, purpose: str = "") -> dict:
    if provider not in ("mail_tm", "tempmail_lol"):
        return {"ok": False, "message": "provider 仅支持 mail_tm / tempmail_lol（IMAP 邮箱请用手动导入）"}
    count = max(1, min(int(count or 0), MAX_BATCH_CREATE))
    if _task_state["running"]:
        return {"ok": False, "message": "已有池任务在执行，请稍后再试"}
    _task_state.update(running=True, kind="batch_create", done=0, total=count, success=0, fail=0)
    log.info(f"[EMAILPOOL] 批量创建开始: provider={provider} count={count}")
    try:
        for i in range(count):
            result = await create_one(provider, purpose=purpose, detail="池批量创建")
            if result["ok"]:
                _task_state["success"] += 1
                log.success(f"[EMAILPOOL] 进度 {i + 1}/{count}: {result['address']}")
            else:
                _task_state["fail"] += 1
            _task_state["done"] += 1
    finally:
        _task_state["running"] = False
        log.info(f"[EMAILPOOL] 批量创建结束: 成功 {_task_state['success']}, 失败 {_task_state['fail']}")
    return {"ok": True, "message": f"批量创建完成: 成功 {_task_state['success']}, 失败 {_task_state['fail']}"}


async def _check_item(provider: str, address: str, password: str, token: str,
                      imap_host: str, imap_port: int, cfg: dict) -> tuple[bool, str, Optional[str]]:
    if provider == "mail_tm":
        return await check_mailtm_alive(cfg.get("mailtm_base_url", MAILTM_DEFAULT_BASE_URL), address, password)
    if provider == "tempmail_lol":
        return await check_tempmail_alive(cfg.get("tempmail_base_url", TEMPMAIL_DEFAULT_BASE_URL), token)
    if provider == "imap":
        return check_imap_alive(imap_host, imap_port or 993, address, password)
    return False, f"未知 provider: {provider}", None


def _update_check_result(item_id: int, alive: bool, detail: str, new_token: Optional[str]) -> None:
    with db.get_session() as session:
        item = session.get(EmailPoolItem, item_id)
        if not item:
            return
        item.status = "active" if alive else "dead"
        item.status_detail = (detail or "")[:250]
        item.last_checked_at = datetime.utcnow()
        if new_token:
            item.token = new_token


async def check_single(item_id: int) -> dict:
    cfg = get_config()
    with db.get_session() as session:
        item = session.get(EmailPoolItem, item_id)
        if not item:
            return {"ok": False, "message": "邮箱不存在"}
        provider, address = item.provider, item.address
        password, token = item.password or "", item.token or ""
        imap_host, imap_port = item.imap_host or "", item.imap_port or 993
    alive, detail, new_token = await _check_item(provider, address, password, token, imap_host, imap_port, cfg)
    _update_check_result(item_id, alive, detail, new_token)
    log.info(f"[EMAILPOOL] 单条探活 {address}: {'存活' if alive else '死亡'} ({detail})")
    return {"ok": True, "id": item_id, "alive": alive, "detail": detail}


async def check_all() -> dict:
    if _task_state["running"]:
        return {"ok": False, "message": "已有池任务在执行，请稍后再试"}
    cfg = get_config()
    with db.get_session() as session:
        items = (
            session.query(EmailPoolItem)
            .filter(EmailPoolItem.status.in_(("active", "unknown")))
            .all()
        )
        targets = [
            (i.id, i.provider, i.address, i.password or "", i.token or "", i.imap_host or "", i.imap_port or 993)
            for i in items
        ]
    total = len(targets)
    _task_state.update(running=True, kind="check_all", done=0, total=total, success=0, fail=0)
    log.info(f"[EMAILPOOL] 全量探活开始: {total} 条")
    try:
        for item_id, provider, address, password, token, imap_host, imap_port in targets:
            alive, detail, new_token = await _check_item(provider, address, password, token, imap_host, imap_port, cfg)
            _update_check_result(item_id, alive, detail, new_token)
            _task_state["done"] += 1
            _task_state["success" if alive else "fail"] += 1
        target = int(cfg.get("email_pool_target_size", 0) or 0)
        if target > 0:
            await _replenish_mailtm(cfg, target)
    finally:
        _task_state["running"] = False
        log.info(f"[EMAILPOOL] 全量探活结束: 存活 {_task_state['success']}, 死亡 {_task_state['fail']}")
    return {"ok": True, "message": f"探活完成: 存活 {_task_state['success']}, 死亡 {_task_state['fail']}"}


async def _replenish_mailtm(cfg: dict, target: int) -> None:
    with db.get_session() as session:
        alive_count = (
            session.query(EmailPoolItem)
            .filter(EmailPoolItem.provider == "mail_tm", EmailPoolItem.status == "active")
            .count()
        )
    deficit = min(target - alive_count, MAX_REPLENISH_PER_CYCLE)
    if deficit <= 0:
        return
    log.info(f"[EMAILPOOL] 自动补池: mail.tm 存活 {alive_count}/{target}，本轮补建 {deficit}")
    for _ in range(deficit):
        result = await create_one("mail_tm", detail="自动补池")
        if not result["ok"]:
            log.warning("[EMAILPOOL] 自动补池中断: 创建失败")
            break
        log.success(f"[EMAILPOOL] 补池成功: {result['address']}")


async def delete_item(item_id: int, purge_remote: bool = False) -> dict:
    with db.get_session() as session:
        item = session.get(EmailPoolItem, item_id)
        if not item:
            return {"ok": False, "message": "邮箱不存在"}
        provider, address = item.provider, item.address
        account_id, token = item.mailtm_account_id or "", item.token or ""
        session.delete(item)
    detail = "本地已移除"
    if purge_remote and provider == "mail_tm":
        cfg = get_config()
        ok, remote_detail = await mailtm_delete_account(
            cfg.get("mailtm_base_url", MAILTM_DEFAULT_BASE_URL), account_id, token
        )
        detail = f"本地已移除；远端删除{'成功' if ok else '失败: ' + remote_detail}"
    log.info(f"[EMAILPOOL] 删除 {address}: {detail}")
    return {"ok": True, "message": detail}


def _get_interval_hours() -> int:
    try:
        return int(get_config().get("email_pool_check_interval_hours", 24) or 0)
    except Exception:
        return 24


async def _pool_scheduler_loop() -> None:
    while True:
        try:
            interval_hours = _get_interval_hours()
            if interval_hours <= 0:
                await asyncio.sleep(600)  # 关闭状态下每 10 分钟重读一次配置
                continue
            await check_all()
            interval_hours = _get_interval_hours()  # 探活期间配置可能被修改
            await asyncio.sleep(max(interval_hours, 1) * 3600 if interval_hours > 0 else 600)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.exception("[EMAILPOOL] 定时探活异常", e)
            await asyncio.sleep(300)


def start_pool_scheduler() -> None:
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(_pool_scheduler_loop())
        log.info("[EMAILPOOL] 定时探活调度器已启动")


def stop_pool_scheduler() -> None:
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
    _scheduler_task = None
    log.info("[EMAILPOOL] 定时探活调度器已停止")
