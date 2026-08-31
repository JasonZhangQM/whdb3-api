"""权证主路由（接口 10-25, 29-35, 40-44）。

M2 范围：他权（依赖 agrees 表）与项目绑定（依赖 articles 表）随 M3 开放。
路由顺序约定：静态路径（batch/* / stats/*）先于 /warrants/{id} 注册。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, require_perm
from app.core.db import get_db
from app.core.response import ok
from app.core.response import page as page_result
from app.warrant.schemas import (
    BatchCancelReq,
    BatchStorageReq,
    BatchTransferReq,
    DraftExtendCreate,
    DraftExtendUpdate,
    EvaluateCreate,
    OwnershipCreate,
    OwnershipUpdate,
    ReceiveExtendCreate,
    RecheckCreate,
    StorageCreate,
    TypeDetailUpdate,
    WarrantCreate,
    WarrantUpdate,
)
from app.warrant.services import ext_service, warrant_service

router = APIRouter(prefix="/warrants", tags=["warrant"])


# ===== 列表 / 统计（静态路径优先注册）=====

@router.get("")
def list_warrants(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    warrant_type: int | None = None,
    warrant_state: int | None = None,
    auction_state: int | None = None,
    owner_id: int | None = None,
    evaluate_method: int | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_perm("warrant:list")),
):
    """权证列表（数据级权限按 created_by 过滤，含所有权人/最近出入库聚合）。"""
    items, total = warrant_service.list_warrants(
        db, ctx, page, page_size, warrant_type, warrant_state,
        auction_state, owner_id, evaluate_method, q,
    )
    return page_result(items, total, page, page_size)


@router.post("")
def create_warrant(
    body: WarrantCreate,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("warrant:create")),
):
    """创建权证：主表 + 按类型扩展 + 所有权人（单事务，不走审批流）。"""
    wid = warrant_service.create(db, body, user.user_id)
    db.commit()
    return ok({"id": wid}, message="创建成功")


@router.get("/stats/overview")
def stats_overview(
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("warrant:list")),
):
    """权证统计概览（总数/按类型/按状态/总评估价值/涉拍数量）。"""
    return ok(warrant_service.stats_overview(db))


@router.get("/stats/by-customer/{customer_id}")
def stats_by_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("warrant:list")),
):
    """指定客户名下权证汇总（客户详情聚合用）。"""
    return ok(warrant_service.stats_by_customer(db, customer_id))


# ===== 批量操作 =====

@router.post("/batch/storage")
def batch_storage(
    body: BatchStorageReq,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("warrant:storage")),
):
    """批量出入库（全部成功或全部回滚，联动主表状态）。"""
    count = warrant_service.batch_storage(db, body.warrant_ids, body, user.user_id, user)
    db.commit()
    return ok({"count": count}, message=f"已对 {count} 个权证执行出入库")


@router.post("/batch/transfer")
def batch_transfer(
    body: BatchTransferReq,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("warrant:storage")),
):
    """批量移交（权证管理岗变更 + 移交记录 + 状态联动）。"""
    count = warrant_service.batch_transfer(
        db, body.warrant_ids, body.to_conservator_id, body.reason, user.user_id, user
    )
    db.commit()
    return ok({"count": count}, message=f"已移交 {count} 个权证")


@router.post("/batch/cancel")
def batch_cancel(
    body: BatchCancelReq,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("warrant:update")),
):
    """批量注销（状态置已注销 + 解保出库记录）。"""
    count = warrant_service.batch_cancel(db, body.warrant_ids, body.reason, user.user_id, user)
    db.commit()
    return ok({"count": count}, message=f"已注销 {count} 个权证")


# ===== 主管理 =====

@router.get("/{warrant_id}")
def get_warrant(
    warrant_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_perm("warrant:detail")),
):
    """权证详情（一次性聚合扩展信息+所有权人+出入库+评估复核）。"""
    return ok(warrant_service.get_detail(db, warrant_id, ctx))


@router.patch("/{warrant_id}")
def update_warrant(
    warrant_id: int,
    body: WarrantUpdate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_perm("warrant:update")),
):
    """修改主表字段（评估/状态/查封拍卖）。"""
    warrant_service.update(db, warrant_id, body, ctx)
    db.commit()
    return ok(message="修改成功")


@router.delete("/{warrant_id}")
def delete_warrant(
    warrant_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_perm("warrant:delete")),
):
    """删除权证（拦截：已入库/已流转走注销流程；级联清理扩展）。"""
    warrant_service.delete(db, warrant_id, ctx)
    db.commit()
    return ok(message="删除成功")


@router.get("/{warrant_id}/type-detail")
def get_type_detail(
    warrant_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_perm("warrant:detail")),
):
    """按类型获取扩展信息（warrant_houses / grounds / ...）。"""
    return ok(ext_service.get_type_detail(db, warrant_id, ctx))


@router.put("/{warrant_id}/type-detail")
def update_type_detail(
    warrant_id: int,
    body: TypeDetailUpdate,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("warrant:update")),
):
    """按类型整体替换扩展信息。"""
    ext_service.update_type_detail(db, warrant_id, body, user.user_id, user)
    db.commit()
    return ok(message="扩展信息已更新")


# ===== 所有权人 =====

@router.get("/{warrant_id}/owners")
def list_owners(
    warrant_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_perm("warrant:detail")),
):
    """产权证/所有权人列表。"""
    return ok(ext_service.list_owners(db, warrant_id, ctx))


@router.post("/{warrant_id}/owners")
def add_owner(
    warrant_id: int,
    body: OwnershipCreate,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("warrant:update")),
):
    """添加产权证（所有权人 + 编号 + 共有份额）。"""
    oid = ext_service.add_owner(db, warrant_id, body, user.user_id, user)
    db.commit()
    return ok({"id": oid}, message="产权证已添加")


@router.patch("/{warrant_id}/owners/{owner_row_id}")
def update_owner(
    warrant_id: int,
    owner_row_id: int,
    body: OwnershipUpdate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_perm("warrant:update")),
):
    """修改产权证（编号/份额）。"""
    ext_service.update_owner(db, warrant_id, owner_row_id, body, ctx)
    db.commit()
    return ok(message="修改成功")


@router.delete("/{warrant_id}/owners/{owner_row_id}")
def delete_owner(
    warrant_id: int,
    owner_row_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_perm("warrant:update")),
):
    """删除产权证。"""
    ext_service.delete_owner(db, warrant_id, owner_row_id, ctx)
    db.commit()
    return ok(message="删除成功")


# ===== 出入库 / 评估 =====

@router.get("/{warrant_id}/storages")
def list_storages(
    warrant_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_perm("warrant:detail")),
):
    """出入库历史列表（轻量查询，不加载扩展表 / 所有权人等）。"""
    items = warrant_service.list_storages(db, warrant_id, ctx)
    return ok({"items": items})


@router.post("/{warrant_id}/storages")
def add_storage(
    warrant_id: int,
    body: StorageCreate,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("warrant:storage")),
):
    """新增出入库记录（联动更新主表 warrant_state）。"""
    sid = warrant_service.add_storage(db, warrant_id, body, user.user_id, user)
    db.commit()
    return ok({"id": sid}, message="出入库记录已添加")


@router.get("/{warrant_id}/evaluates")
def list_evaluates(
    warrant_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_perm("warrant:detail")),
):
    """评估历史列表（含复核，轻量查询）。"""
    items = warrant_service.list_evaluates(db, warrant_id, ctx)
    return ok({"items": items})


@router.post("/{warrant_id}/evaluates")
def add_evaluate(
    warrant_id: int,
    body: EvaluateCreate,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("warrant:update")),
):
    """新增评估记录（联动更新主表最新评估字段）。"""
    eid = warrant_service.add_evaluate(db, warrant_id, body, user.user_id, user)
    db.commit()
    return ok({"id": eid}, message="评估记录已添加")


@router.post("/{warrant_id}/evaluates/{evaluate_id}/recheck")
def add_recheck(
    warrant_id: int,
    evaluate_id: int,
    body: RecheckCreate,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("warrant:update")),
):
    """新增评估复核（一条评估仅一条复核）。"""
    rid = warrant_service.add_recheck(db, warrant_id, evaluate_id, body, user.user_id, user)
    db.commit()
    return ok({"id": rid}, message="复核记录已添加")


# ===== 票据明细 =====

@router.get("/{warrant_id}/draft-extends")
def list_draft_extends(
    warrant_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_perm("warrant:detail")),
):
    """票据明细列表（关联核心企业/承兑人名称）。"""
    return ok(ext_service.list_draft_extends(db, warrant_id, ctx))


@router.post("/{warrant_id}/draft-extends")
def add_draft_extend(
    warrant_id: int,
    body: DraftExtendCreate,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("warrant:update")),
):
    """添加票据明细（校验承兑人存在、核心企业 is_core、票据号唯一）。"""
    eid = ext_service.add_draft_extend(db, warrant_id, body, user.user_id, user)
    db.commit()
    return ok({"id": eid}, message="票据明细已添加")


@router.patch("/{warrant_id}/draft-extends/{extend_id}")
def update_draft_extend(
    warrant_id: int,
    extend_id: int,
    body: DraftExtendUpdate,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("warrant:update")),
):
    """修改票据明细（状态/金额/到期日）。"""
    ext_service.update_draft_extend(db, warrant_id, extend_id, body, user.user_id, user)
    db.commit()
    return ok(message="修改成功")


@router.delete("/{warrant_id}/draft-extends/{extend_id}")
def delete_draft_extend(
    warrant_id: int,
    extend_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_perm("warrant:update")),
):
    """删除票据明细。"""
    ext_service.delete_draft_extend(db, warrant_id, extend_id, ctx)
    db.commit()
    return ok(message="删除成功")


# ===== 应收明细 =====

@router.get("/{warrant_id}/receive-extends")
def list_receive_extends(
    warrant_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_perm("warrant:detail")),
):
    """应收账款明细（应收单位）列表。"""
    return ok(ext_service.list_receive_extends(db, warrant_id, ctx))


@router.post("/{warrant_id}/receive-extends")
def add_receive_extend(
    warrant_id: int,
    body: ReceiveExtendCreate,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("warrant:update")),
):
    """添加应收单位（同一权证下不重复）。"""
    eid = ext_service.add_receive_extend(db, warrant_id, body, user.user_id, user)
    db.commit()
    return ok({"id": eid}, message="应收单位已添加")


@router.delete("/{warrant_id}/receive-extends/{extend_id}")
def delete_receive_extend(
    warrant_id: int,
    extend_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_perm("warrant:update")),
):
    """删除应收单位。"""
    ext_service.delete_receive_extend(db, warrant_id, extend_id, ctx)
    db.commit()
    return ok(message="删除成功")
