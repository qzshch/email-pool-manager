# -*- coding: utf-8 -*-
"""Tempmail.lol 平台引擎：批量创建临时邮箱（自动入池）。

- 每个"轮次"= 创建一个 inbox；count=0 表示无限
- 与 Mail.tm 共享全局建号串行锁，避免混合任务时互相干扰
- 该服务邮箱短时效，入池后会较快判死，属预期
"""
from ...email_pool import create_one
from ...log_manager import log_manager as log
from ..base import BaseEngine


class TempmailLolEngine(BaseEngine):
    platform_id = "tempmail_lol"
    platform_name = "Tempmail.lol"
    platform_icon = "📨"

    def get_config_fields(self) -> list[dict]:
        return [
            {"key": "tempmail_base_url", "label": "Tempmail API", "type": "text", "default": "https://api.tempmail.lol/v2"},
        ]

    def get_default_config(self) -> dict:
        return {"tempmail_base_url": "https://api.tempmail.lol/v2"}

    async def _run(self, count: int, interval: int, concurrency: int = 1, **kwargs):
        self.running = True
        self.current_round = 0
        self.active_workers = 0
        target = int(count or 0)  # 0 = 无限
        log.info(
            f"[TEMPMAIL] 批量创建启动: {'无限' if target == 0 else target} 个, 间隔 {interval}s"
        )
        try:
            while not self._stop_event.is_set():
                if target and self.current_round >= target:
                    break
                self.active_workers = 1
                result = await create_one("tempmail_lol", detail="平台批量创建")
                self.active_workers = 0
                self.current_round += 1
                if result["ok"]:
                    self.success_count += 1
                    log.success(f"[TEMPMAIL] 进度 {self.current_round}/{target or '∞'}: {result['address']}")
                else:
                    self.fail_count += 1
                    log.error(f"[TEMPMAIL] 进度 {self.current_round}/{target or '∞'}: {result['message']}")
                if target and self.current_round >= target:
                    break
                if await self._wait_for_stop_or_timeout(int(interval or 0)):
                    break
        finally:
            self.active_workers = 0
            self.running = False
            log.info(f"[TEMPMAIL] 批量创建结束: 成功 {self.success_count}, 失败 {self.fail_count}")

    async def register_once(self, proxy=None, email=None, password=None) -> dict:
        """单次创建（/api/task/register-once?platform=tempmail_lol）。"""
        result = await create_one("tempmail_lol", detail="平台单次创建")
        return {
            "success": result["ok"],
            "email": result["address"],
            "proxy_used": None,
            "message": "创建成功" if result["ok"] else result["message"],
        }
