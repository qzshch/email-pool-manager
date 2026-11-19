# -*- coding: utf-8 -*-
"""Corekiln 平台引擎：自有域名（catch-all）批量生成邮箱地址。

- 地址由 Cloudflare Email Routing catch-all 承接，创建=本地生成+Worker 登记，无第三方节流
- 收信走 Email Worker 的 D1 API（池面板可在线查看）
- count=0 表示无限
"""
from ...email_pool import create_one
from ...log_manager import log_manager as log
from ..base import BaseEngine


class CorekilnEngine(BaseEngine):
    platform_id = "corekiln"
    platform_name = "Corekiln"
    platform_icon = "📮"

    def get_config_fields(self) -> list[dict]:
        return [
            {"key": "corekiln_domain", "label": "域名", "type": "text", "default": "corekiln.com"},
            {"key": "corekiln_base_url", "label": "Worker API 地址", "type": "text", "default": ""},
        ]

    def get_default_config(self) -> dict:
        return {
            "corekiln_domain": "corekiln.com",
            "corekiln_base_url": "",
        }

    async def _run(self, count: int, interval: int, concurrency: int = 1, **kwargs):
        self.running = True
        self.current_round = 0
        self.active_workers = 0
        target = int(count or 0)  # 0 = 无限
        log.info(
            f"[COREKILN] 批量创建启动: {'无限' if target == 0 else target} 个, 间隔 {interval}s"
        )
        try:
            while not self._stop_event.is_set():
                if target and self.current_round >= target:
                    break
                self.active_workers = 1
                result = await create_one("corekiln", detail="平台批量创建")
                self.active_workers = 0
                self.current_round += 1
                if result["ok"]:
                    self.success_count += 1
                    log.success(f"[COREKILN] 进度 {self.current_round}/{target or '∞'}: {result['address']}")
                else:
                    self.fail_count += 1
                    log.error(f"[COREKILN] 进度 {self.current_round}/{target or '∞'}: {result['message']}")
                if target and self.current_round >= target:
                    break
                if await self._wait_for_stop_or_timeout(int(interval or 0)):
                    break
        finally:
            self.active_workers = 0
            self.running = False
            log.info(f"[COREKILN] 批量创建结束: 成功 {self.success_count}, 失败 {self.fail_count}")

    async def register_once(self, proxy=None, email=None, password=None) -> dict:
        result = await create_one("corekiln", detail="平台单次创建")
        return {
            "success": result["ok"],
            "email": result["address"],
            "proxy_used": None,
            "message": "创建成功" if result["ok"] else result["message"],
        }
