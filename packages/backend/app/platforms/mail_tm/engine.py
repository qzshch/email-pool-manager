# -*- coding: utf-8 -*-
"""Mail.tm 平台引擎：批量创建邮箱（自动入池）。

- 每个"轮次"= 创建一个邮箱；建号节流由全局串行锁 + 429 退避保证
- count=0 表示无限循环，直到手动停止
- concurrency 强制为 1（mail.tm 创建接口按 IP 限流，并发只会全撞 429）
"""
from ...email_pool import create_one
from ...log_manager import log_manager as log
from ..base import BaseEngine


class MailTmEngine(BaseEngine):
    platform_id = "mail_tm"
    platform_name = "Mail.tm"
    platform_icon = "📧"

    def get_config_fields(self) -> list[dict]:
        return [
            {"key": "mailtm_base_url", "label": "Mail.tm API", "type": "text", "default": "https://api.mail.tm"},
        ]

    def get_default_config(self) -> dict:
        return {"mailtm_base_url": "https://api.mail.tm"}

    async def _run(self, count: int, interval: int, concurrency: int = 1, **kwargs):
        from ...config import get_config

        self.running = True
        self.current_round = 0
        self.active_workers = 0
        target = int(count or 0)  # 0 = 无限
        if int(concurrency or 1) > 1:
            log.info("[MAILTM] 创建接口按 IP 限流，并发已强制为 1")
        log.info(
            f"[MAILTM] 批量创建启动: {'无限' if target == 0 else target} 个, 间隔 {interval}s"
        )
        try:
            while not self._stop_event.is_set():
                if target and self.current_round >= target:
                    break
                self.active_workers = 1
                result = await create_one("mail_tm", detail="平台批量创建")
                self.active_workers = 0
                self.current_round += 1
                if result["ok"]:
                    self.success_count += 1
                    log.success(f"[MAILTM] 进度 {self.current_round}/{target or '∞'}: {result['address']}")
                else:
                    self.fail_count += 1
                    log.error(f"[MAILTM] 进度 {self.current_round}/{target or '∞'}: {result['message']}")
                if target and self.current_round >= target:
                    break
                if await self._wait_for_stop_or_timeout(int(interval or 0)):
                    break
        finally:
            self.active_workers = 0
            self.running = False
            log.info(f"[MAILTM] 批量创建结束: 成功 {self.success_count}, 失败 {self.fail_count}")

    async def register_once(self, proxy=None, email=None, password=None) -> dict:
        """单次创建（/api/task/register-once?platform=mail_tm）。"""
        result = await create_one("mail_tm", detail="平台单次创建")
        return {
            "success": result["ok"],
            "email": result["address"],
            "proxy_used": None,
            "message": "创建成功" if result["ok"] else result["message"],
        }
