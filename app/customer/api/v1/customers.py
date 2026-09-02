"""客户主路由：列表/详情/创建/批量移交/子资源/核心企业额度/统计。

客户审批场景已移除，所有写操作直接生效。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, get_current_user, require_perm
from app.core.db import get_db
from app.core.response import ok
from app.core.response import page as page_result
from app.customer.schemas import (
    ClassificationChange,
    ControlerChangeReq,
    CoreLimitCreate,
    CoreLimitUpdate,
    CustomerContactCreate,
    CustomerContactUpdate,
    CustomerCreate,
    CustomerExtendCreate,
    CustomerTransferReq,
    CustomerUpdate,
    DirectorCreate,
    DirectorOrderReq,
    PersonalProfileUpdate,
    ShareholderCreate,
    SpouseBindReq,
)
from app.customer.services import customer_service, group_service

router = APIRouter(prefix="/customers", tags=["customer"])


# ===== 列表 / 统计（静态路径优先注册）=====

@router.get("")
def list_customers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    genre: int | None = None,
    group_id: int | None = None,
    credit_region_id: int | None = None,
    region_id: int | None = None,
    industry_id: int | None = None,
    managementor_id: int | None = None,
    controler_id: int | None = None,
    classification: int | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_perm("customer:list")),
):
    """客户列表（数据级权限按管护经理过滤）。"""
    items, total = customer_service.list_customers(
        db, ctx, page, page_size, genre, group_id,
        credit_region_id, region_id, industry_id,
        managementor_id, controler_id, classification, q,
    )
    return page_result(items, total, page, page_size)


@router.post("/transfer-requests")
def batch_transfer(
    body: CustomerTransferReq,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("customer:transfer")),
):
    """批量管护经理移交（直接生效，≤200 个客户）。"""
    count = customer_service.batch_transfer(db, body, user.user_id)
    db.commit()
    return ok({"count": count}, message=f"已移交 {count} 个客户")


@router.get("/stats/overview")
def stats_overview(
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:list")),
):
    """客户统计概览（总数/在保/五级分类分布）。"""
    return ok(customer_service.stats_overview(db))


@router.get("/stats/industry-chart")
def stats_industry_chart(
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:list")),
):
    """行业分布图表数据。"""
    return ok(customer_service.stats_industry_chart(db))


@router.get("/stats/group-summary/{group_id}")
def stats_group_summary(
    group_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:detail")),
):
    """集团内成员授信/在保汇总（实时统计）。"""
    return ok(group_service.group_summary(db, group_id))


@router.get("/stats/region-summary/{region_id}")
def stats_region_summary(
    region_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:list")),
):
    """授信区域内成员授信/在保汇总（实时统计）。"""
    return ok(customer_service.region_summary(db, region_id))


# ===== 详情 / 创建 / 修改 =====

@router.post("")
def create_customer(
    body: CustomerCreate,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("customer:create")),
):
    """添加客户 → 直接落库（不走审批）。"""
    customer_id = customer_service.create_customer(db, body, user.user_id)
    db.commit()
    return ok({"id": customer_id}, message="客户创建成功")


@router.get("/{customer_id}")
def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:detail")),
):
    """客户详情（含扩展信息/集团/核心企业额度概要）。"""
    return ok(customer_service.get_detail(db, customer_id))


@router.patch("/{customer_id}")
def update_customer(
    customer_id: int,
    body: CustomerUpdate,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:update")),
):
    """修改客户（所有字段直接生效，含原敏感字段）。"""
    customer_service.update_free_fields(db, customer_id, body)
    db.commit()
    return ok(message="修改成功")


@router.patch("/{customer_id}/controler")
def change_controler(
    customer_id: int,
    body: ControlerChangeReq,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:update")),
):
    """变更风控专员。"""
    customer_service.change_controler(db, customer_id, body.controler_id)
    db.commit()
    return ok(message="风控专员已变更")


# ===== 经营快照 / 分类 / 标签 =====

@router.get("/{customer_id}/extends")
def list_extends(
    customer_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(get_current_user),
):
    """经营快照历史列表（仅登录即可，只读字典接口不绑定 module:list）。"""
    return ok(customer_service.list_extends(db, customer_id))


@router.post("/{customer_id}/extends")
def add_extend(
    customer_id: int,
    body: CustomerExtendCreate,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("customer:update")),
):
    """添加经营信息快照（同日覆盖；触发划型重算并同步主表）。"""
    extend_id = customer_service.add_extend(
        db, customer_id, body.sales_revenue, body.total_assets,
        body.people_engaged, body.data_date, user.user_id,
    )
    db.commit()
    return ok({"id": extend_id}, message="经营信息已保存")


@router.delete("/{customer_id}/extends/{extend_id}")
def delete_extend(
    customer_id: int,
    extend_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:update")),
):
    customer_service.delete_extend(db, customer_id, extend_id)
    db.commit()
    return ok(message="快照已删除")


@router.post("/{customer_id}/classification")
def change_classification(
    customer_id: int,
    body: ClassificationChange,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("customer:update")),
):
    """调整五级分类（风控操作，记审计）。"""
    customer_service.change_classification(
        db, customer_id, body.classification, body.reason, user.user_id
    )
    db.commit()
    return ok(message="分类已调整")


@router.patch("/{customer_id}/tags")
def update_tags(
    customer_id: int,
    body: CustomerUpdate,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:update")),
):
    """更新客户行业/业务标签。"""
    customer_service.update_free_fields(db, customer_id, body)
    db.commit()
    return ok(message="标签已更新")


# ===== 核心企业额度 =====

@router.get("/{customer_id}/core-limits")
def list_core_limits(
    customer_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:detail")),
):
    """核心企业授信额度列表（任何有额度记录的客户）。"""
    return ok(customer_service.list_core_limits(db, customer_id))


@router.post("/{customer_id}/core-limits")
def add_core_limit(
    customer_id: int,
    body: CoreLimitCreate,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("customer:update")),
):
    """新增授信额度（旧额度自动置失效 + 写历史）。"""
    limit_id = customer_service.add_core_limit(
        db, customer_id, body.credit_amount,
        body.valid_begin_date, body.valid_end_date, body.remark, user.user_id,
    )
    db.commit()
    return ok({"id": limit_id}, message="额度已创建")


@router.patch("/{customer_id}/core-limits/{limit_id}")
def update_core_limit(
    customer_id: int,
    limit_id: int,
    body: CoreLimitUpdate,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("customer:update")),
):
    """修改额度（状态/有效期/已用额；变更写历史）。"""
    customer_service.update_core_limit(
        db, customer_id, limit_id, body.model_dump(exclude_unset=True), user.user_id
    )
    db.commit()
    return ok(message="额度已修改")


@router.get("/{customer_id}/core-history")
def list_core_histories(
    customer_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:detail")),
):
    """核心企业变更历史。"""
    return ok(customer_service.list_core_histories(db, customer_id))


# ===== 企业子资源：股东 / 董事 =====

@router.get("/{customer_id}/shareholders")
def list_shareholders(
    customer_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:detail")),
):
    return ok(customer_service.list_shareholders(db, customer_id))


@router.post("/{customer_id}/shareholders")
def add_shareholder(
    customer_id: int,
    body: ShareholderCreate,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("customer:update")),
):
    """添加股东（持股比例合计 ≤100%）。"""
    sid = customer_service.add_shareholder(
        db, customer_id, body.shareholder_name,
        body.invested_amount, body.shareholding_ratio, user.user_id,
    )
    db.commit()
    return ok({"id": sid}, message="股东已添加")


@router.delete("/{customer_id}/shareholders/{shareholder_id}")
def delete_shareholder(
    customer_id: int,
    shareholder_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:update")),
):
    customer_service.delete_shareholder(db, customer_id, shareholder_id)
    db.commit()
    return ok(message="股东已删除")


@router.get("/{customer_id}/directors")
def list_directors(
    customer_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:detail")),
):
    return ok(customer_service.list_directors(db, customer_id))


@router.post("/{customer_id}/directors")
def add_director(
    customer_id: int,
    body: DirectorCreate,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("customer:update")),
):
    did = customer_service.add_director(
        db, customer_id, body.director_name, user.user_id
    )
    db.commit()
    return ok({"id": did}, message="董事已添加")


@router.delete("/{customer_id}/directors/{director_id}")
def delete_director(
    customer_id: int,
    director_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:update")),
):
    customer_service.delete_director(db, customer_id, director_id)
    db.commit()
    return ok(message="董事已删除")


@router.put("/{customer_id}/directors/order")
def order_directors(
    customer_id: int,
    body: DirectorOrderReq,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:update")),
):
    """董事排序（全量有序 ID 列表）。"""
    customer_service.order_directors(db, customer_id, body.ordered_ids)
    db.commit()
    return ok(message="排序已保存")


# ===== 个人子资源：配偶 =====

@router.post("/{customer_id}/spouse")
def bind_spouse(
    customer_id: int,
    body: SpouseBindReq,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("customer:update")),
):
    """绑定配偶（双向关联 + 双方婚姻状态置已婚）。"""
    customer_service.bind_spouse(
        db, customer_id, body.spouse_customer_id, user.user_id
    )
    db.commit()
    return ok(message="配偶已绑定")


@router.delete("/{customer_id}/spouse")
def unbind_spouse(
    customer_id: int,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("customer:update")),
):
    """解绑配偶（双向解绑 + 婚姻状态置默认）。"""
    customer_service.unbind_spouse(db, customer_id, user.user_id)
    db.commit()
    return ok(message="配偶已解绑")


@router.patch("/{customer_id}/personal")
def update_personal_profile(
    customer_id: int,
    body: PersonalProfileUpdate,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:update")),
):
    """更新个人扩展信息（婚姻状态/户籍性质/配偶，三个字段一起编辑）。"""
    customer_service.update_personal_profile(
        db,
        customer_id,
        marital_status=body.marital_status,
        household_nature=body.household_nature,
        spouse_id=body.spouse_id,
    )
    db.commit()
    return ok(message="个人信息已更新")


# ===== 联系人 =====

@router.get("/{customer_id}/contacts")
def list_contacts(
    customer_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:detail")),
):
    """客户联系人列表。"""
    return ok(customer_service.list_contacts(db, customer_id))


@router.post("/{customer_id}/contacts")
def add_contact(
    customer_id: int,
    body: CustomerContactCreate,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("customer:update")),
):
    """新增联系人。"""
    contact_id = customer_service.add_contact(db, customer_id, body, user.user_id)
    db.commit()
    return ok({"id": contact_id}, message="联系人已添加")


@router.patch("/{customer_id}/contacts/{contact_id}")
def update_contact(
    customer_id: int,
    contact_id: int,
    body: CustomerContactUpdate,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:update")),
):
    """修改联系人。"""
    customer_service.update_contact(db, customer_id, contact_id, body)
    db.commit()
    return ok(message="联系人已更新")


@router.delete("/{customer_id}/contacts/{contact_id}")
def delete_contact(
    customer_id: int,
    contact_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:update")),
):
    """删除联系人。"""
    customer_service.delete_contact(db, customer_id, contact_id)
    db.commit()
    return ok(message="联系人已删除")
