from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import email_pool
from ..database import EmailPoolItem, db

router = APIRouter(prefix="/api/emails", tags=["emails"])


class EmailImport(BaseModel):
    provider: str  # mail_tm | tempmail_lol | imap
    address: str
    password: str = ""
    token: str = ""
    imap_host: str = ""
    imap_port: int = 993
    purpose: str = ""


class BatchCreateRequest(BaseModel):
    provider: str
    count: int = 1
    purpose: str = ""


class CheckRequest(BaseModel):
    id: int


class PurposeUpdate(BaseModel):
    purpose: str


@router.get("")
async def list_emails(
    provider: str = "",
    status: str = "",
    search: str = "",
    page: int = 1,
    page_size: int = 50,
    include_secret: bool = False,
):
    with db.get_session() as session:
        query = session.query(EmailPoolItem)
        if provider:
            query = query.filter(EmailPoolItem.provider == provider)
        if status:
            query = query.filter(EmailPoolItem.status == status)
        if search:
            query = query.filter(EmailPoolItem.address.ilike(f"%{search}%"))
        total = query.count()
        items = (
            query.order_by(EmailPoolItem.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return {
            "items": [i.to_dict(include_secret) for i in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }


@router.post("")
async def import_email(data: EmailImport):
    if data.provider not in email_pool.VALID_PROVIDERS:
        raise HTTPException(status_code=400, detail="provider 仅支持 mail_tm / tempmail_lol / imap")
    address = data.address.strip()
    if not address or "@" not in address:
        raise HTTPException(status_code=400, detail="地址无效")
    if data.provider == "imap" and not data.imap_host.strip():
        raise HTTPException(status_code=400, detail="IMAP 导入需提供 imap_host")
    with db.get_session() as session:
        exists = (
            session.query(EmailPoolItem)
            .filter(EmailPoolItem.provider == data.provider, EmailPoolItem.address == address)
            .first()
        )
        if exists:
            raise HTTPException(status_code=400, detail="该邮箱已在池中")
        item = EmailPoolItem(
            provider=data.provider,
            address=address,
            password=data.password,
            token=data.token,
            imap_host=data.imap_host,
            imap_port=data.imap_port,
            purpose=data.purpose,
            status="unknown",
            status_detail="手动导入待探活",
        )
        session.add(item)
        session.flush()
        item_id = item.id
    return {"ok": True, "id": item_id, "message": "已导入，建议立即探活"}


@router.post("/batch-create")
async def batch_create(req: BatchCreateRequest):
    result = await email_pool.batch_create(req.provider, req.count, req.purpose)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message", "创建失败"))
    return result


@router.get("/task-status")
async def task_status():
    return email_pool.get_task_status()


@router.post("/check")
async def check_one(req: CheckRequest):
    return await email_pool.check_single(req.id)


@router.post("/check-all")
async def check_all():
    result = await email_pool.check_all()
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message", "探活失败"))
    return result


@router.put("/{item_id}")
async def update_email(item_id: int, data: PurposeUpdate):
    with db.get_session() as session:
        item = session.get(EmailPoolItem, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="邮箱不存在")
        item.purpose = data.purpose
    return {"ok": True, "message": "已更新"}


@router.delete("/{item_id}")
async def delete_email(item_id: int, purge_remote: bool = False):
    return await email_pool.delete_item(item_id, purge_remote)


@router.get("/stats/summary")
async def stats_summary():
    with db.get_session() as session:
        base = session.query(EmailPoolItem)
        total = base.count()
        active = (
            session.query(EmailPoolItem).filter(EmailPoolItem.status == "active").count()
        )
        dead = session.query(EmailPoolItem).filter(EmailPoolItem.status == "dead").count()
        unknown = (
            session.query(EmailPoolItem).filter(EmailPoolItem.status == "unknown").count()
        )
        by_provider = {
            provider: session.query(EmailPoolItem).filter(EmailPoolItem.provider == provider).count()
            for provider in email_pool.VALID_PROVIDERS
        }
    return {
        "total": total,
        "active": active,
        "dead": dead,
        "unknown": unknown,
        "by_provider": by_provider,
    }
