"""客户主服务：列表/详情/创建/批量移交/子资源/统计。

所有字段直接写入（客户审批场景已移除，后续如有需要按新业务要求重新接入）。
"""

from datetime import datetime

from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, apply_data_scope_filter
from app.core.exceptions import BizError
from app.customer.enums import Classification, Genre, LABELS
from app.customer.models import (
    CompanyProfile,
    CoreHistory,
    CoreLimit,
    Customer,
    CustomerContact,
    CustomerExtend,
    CustomerTagRelation,
    Director,
    ExtraTag,
    PersonalProfile,
    Shareholder,
)
from app.customer.schemas import (
    CustomerContactCreate,
    CustomerContactUpdate,
    CustomerCreate,
    CustomerTransferReq,
    CustomerUpdate,
)


def _get_or_404(db: Session, customer_id: int) -> Customer:
    c = db.get(Customer, customer_id)
    if c is None:
        raise BizError(4041, "客户不存在")
    return c


def _disp(group: str, value: int | None) -> str | None:
    if value is None:
        return None
    return LABELS[group].get(value, str(value))


def _replace_tags(db: Session, customer_id: int, tag_ids: list[int]) -> None:
    """整体替换客户标签（校验存在性 + 删旧插新，同一事务内完成）。"""
    if tag_ids:
        valid_ids = set(
            db.scalars(select(ExtraTag.id).where(ExtraTag.id.in_(tag_ids))).all()
        )
        missing = set(tag_ids) - valid_ids
        if missing:
            raise BizError(4041, f"标签不存在: {sorted(missing)}")
    db.query(CustomerTagRelation).filter(
        CustomerTagRelation.customer_id == customer_id
    ).delete(synchronize_session=False)
    for tid in dict.fromkeys(tag_ids):  # 去重且保序
        db.add(CustomerTagRelation(customer_id=customer_id, tag_id=tid))


# ===== 列表 =====

def list_customers(
    db: Session,
    ctx: AuthContext,
    page: int,
    page_size: int,
    genre: int | None = None,
    group_id: int | None = None,
    credit_region_id: int | None = None,
    region_id: int | None = None,
    industry_id: int | None = None,
    managementor_id: int | None = None,
    controler_id: int | None = None,
    classification: int | None = None,
    q: str | None = None,
) -> tuple[list[dict], int]:
    from app.user.models import User

    stmt = select(Customer).order_by(Customer.credit_amount.desc())

    # 数据级权限：按管护人过滤（§4.1）——部门范围经统一入口翻译为部门内用户集合
    stmt = apply_data_scope_filter(db, stmt, ctx, owner_field="managementor_id")

    if genre is not None:
        stmt = stmt.where(Customer.genre == genre)
    if group_id is not None:
        stmt = stmt.where(Customer.group_id == group_id)
    if credit_region_id is not None:
        stmt = stmt.where(Customer.credit_region_id == credit_region_id)
    if region_id is not None:
        stmt = stmt.where(Customer.region_id == region_id)
    if industry_id is not None:
        stmt = stmt.where(Customer.industry_id == industry_id)
    if managementor_id is not None:
        stmt = stmt.where(Customer.managementor_id == managementor_id)
    if controler_id is not None:
        stmt = stmt.where(Customer.controler_id == controler_id)
    if classification is not None:
        stmt = stmt.where(Customer.classification == classification)
    if q:
        like = f"%{q}%"
        contact_exists = exists(
            select(CustomerContact.id)
            .where(
                CustomerContact.customer_id == Customer.id,
                or_(
                    CustomerContact.name.like(like),
                    CustomerContact.phone.like(like),
                ),
            )
        )
        stmt = stmt.where(
            or_(
                Customer.name.like(like),
                Customer.short_name.like(like),
                contact_exists,
            )
        )

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    customers = db.scalars(
        stmt.offset((page - 1) * page_size).limit(page_size)
    ).all()

    # 批量取关联名称（避免 N+1）；created_by 一并取，列表尾列展示创建人
    user_ids = (
        {c.managementor_id for c in customers}
        | {c.controler_id for c in customers}
        | {c.created_by for c in customers if c.created_by}
    )
    users = dict(
        db.execute(select(User.id, User.name).where(User.id.in_(user_ids))).all()
    ) if user_ids else {}
    region_ids = {c.region_id for c in customers if c.region_id}
    region_names = {}
    if region_ids:
        from app.user.models import Region

        region_names = dict(
            db.execute(select(Region.id, Region.name).where(Region.id.in_(region_ids))).all()
        )
    industry_names = {}
    industry_ids = {c.industry_id for c in customers if c.industry_id}
    if industry_ids:
        from app.customer.models import Industry

        industry_names = dict(
            db.execute(select(Industry.id, Industry.name).where(Industry.id.in_(industry_ids))).all()
        )
    group_names = {}
    group_ids = {c.group_id for c in customers if c.group_id}
    if group_ids:
        from app.customer.models import Group

        group_names = dict(
            db.execute(select(Group.id, Group.name).where(Group.id.in_(group_ids))).all()
        )
    credit_region_names = {}
    cr_ids = {c.credit_region_id for c in customers if c.credit_region_id}
    if cr_ids:
        from app.customer.models import CreditRegion

        credit_region_names = dict(
            db.execute(
                select(CreditRegion.id, CreditRegion.name).where(CreditRegion.id.in_(cr_ids))
            ).all()
        )

    items = []
    for c in customers:
        items.append(
            {
                "id": c.id,
                "name": c.name,
                "short_name": c.short_name,
                "genre": c.genre,
                "managementor_name": users.get(c.managementor_id, ""),
                "credit_amount": float(c.credit_amount),
                "amount": float(c.amount),
                "classification": c.classification,
                "region_name": region_names.get(c.region_id or 0),
                "credit_region_id": c.credit_region_id,
                "credit_region_name": credit_region_names.get(c.credit_region_id or 0),
                "industry_name": industry_names.get(c.industry_id or 0),
                "group_id": c.group_id,
                "group_name": group_names.get(c.group_id or 0),
                "controler_name": users.get(c.controler_id, ""),
                "last_provide_date": c.last_provide_date,
                "last_review_date": c.last_review_date,
                "day_space": c.day_space,
                "created_by_name": users.get(c.created_by) or "",
            }
        )
    return items, total


# ===== 详情 =====

def get_detail(db: Session, customer_id: int) -> dict:
    from app.user.models import User

    c = _get_or_404(db, customer_id)
    users = dict(
        db.execute(
            select(User.id, User.name).where(User.id.in_([c.managementor_id, c.controler_id, c.created_by]))
        ).all()
    )

    detail = {
        "id": c.id,
        "name": c.name,
        "short_name": c.short_name,
        "genre": c.genre,
        "license_num": c.license_num,
        "license_addr": c.license_addr,
        "managementor_name": users.get(c.managementor_id, ""),
        "credit_amount": float(c.credit_amount),
        "amount": float(c.amount),
        "classification": c.classification,
        "classification_display": _disp("classification", c.classification),
        "region_name": None,
        "credit_region_id": c.credit_region_id,
        "credit_region_name": None,
        "industry_name": None,
        "group_id": c.group_id,
        "group_name": None,
        "controler_name": users.get(c.controler_id, ""),
        "last_provide_date": c.last_provide_date,
        "last_review_date": c.last_review_date,
        "day_space": c.day_space,
        # 余额（M2 阶段实时 SUM 暂以缓存值返回，M3 放款落地后切换）
        "custom_flow": float(c.custom_flow),
        "custom_accept": float(c.custom_accept),
        "custom_back": float(c.custom_back),
        "entrusted_loan": float(c.entrusted_loan),
        "last_synced_at": c.last_synced_at,
        "g_radio": float(c.g_radio),
        "v_radio": float(c.v_radio),
        "company": None,
        "personal": None,
        "group": None,
        "core_info": None,
        "shareholder_count": 0,
        "director_count": 0,
        "extend_count": 0,
        "latest_extend": None,
        "tags": db.scalars(
            select(CustomerTagRelation.tag_id)
            .where(CustomerTagRelation.customer_id == customer_id)
            .order_by(CustomerTagRelation.tag_id)
        ).all(),
        "contacts": [],
        "created_by_name": users.get(c.created_by) or "",
        "created_at": c.created_at,
    }

    # 关联名称
    if c.region_id:
        from app.user.models import Region

        detail["region_name"] = db.scalar(
            select(Region.name).where(Region.id == c.region_id)
        )
    if c.industry_id:
        from app.customer.models import Industry

        detail["industry_name"] = db.scalar(
            select(Industry.name).where(Industry.id == c.industry_id)
        )
    if c.group_id:
        from app.customer.models import Group

        g = db.get(Group, c.group_id)
        if g:
            detail["group_name"] = g.name
    if c.credit_region_id:
        from app.customer.models import CreditRegion

        detail["credit_region_name"] = db.scalar(
            select(CreditRegion.name).where(CreditRegion.id == c.credit_region_id)
        )

    # 扩展信息
    if c.genre == Genre.COMPANY:
        cp = db.scalar(
            select(CompanyProfile).where(CompanyProfile.customer_id == customer_id)
        )
        if cp:
            detail["company"] = {
                "id": cp.id,
                "decisionor": cp.decisionor,
                "decisionor_display": _disp("decisionor", cp.decisionor),
                "custom_nature": cp.custom_nature,
                "custom_nature_display": _disp("custom_nature", cp.custom_nature),
                "industry_c": cp.industry_c,
                "typing": cp.typing,
                "typing_display": _disp("typing", cp.typing),
                "capital": float(cp.capital or 0),
                "paid_capital": float(cp.paid_capital or 0),
                "representative": cp.representative,
            }
            detail["shareholder_count"] = db.scalar(
                select(func.count(Shareholder.id)).where(Shareholder.company_id == cp.id)
            ) or 0
            detail["director_count"] = db.scalar(
                select(func.count(Director.id)).where(Director.company_id == cp.id)
            ) or 0
    else:
        pp = db.scalar(
            select(PersonalProfile).where(PersonalProfile.customer_id == customer_id)
        )
        if pp:
            spouse = None
            if pp.spouse_id:
                sc = db.get(Customer, pp.spouse_id)
                if sc:
                    spouse = {"id": sc.id, "name": sc.name, "short_name": sc.short_name}
            detail["personal"] = {
                "id": pp.id,
                "marital_status": pp.marital_status,
                "marital_status_display": _disp("marital_status", pp.marital_status),
                "household_nature": pp.household_nature,
                "household_nature_display": _disp("household_nature", pp.household_nature),
                "spouse": spouse,
            }

    # 经营快照
    detail["extend_count"] = db.scalar(
        select(func.count(CustomerExtend.id)).where(CustomerExtend.customer_id == customer_id)
    ) or 0
    latest = db.scalar(
        select(CustomerExtend)
        .where(CustomerExtend.customer_id == customer_id)
        .order_by(CustomerExtend.data_date.desc())
        .limit(1)
    )
    if latest:
        detail["latest_extend"] = {
            "id": latest.id,
            "sales_revenue": float(latest.sales_revenue),
            "total_assets": float(latest.total_assets),
            "people_engaged": float(latest.people_engaged),
            "data_date": latest.data_date,
            "typing": latest.typing,
        }

    # 核心企业概要（不再依赖 is_core 标记，有额度记录即返回）
    if db.scalar(select(CoreLimit.id).where(CoreLimit.customer_id == customer_id).limit(1)) is not None:
        current = db.scalar(
            select(CoreLimit).where(
                CoreLimit.customer_id == customer_id,
                CoreLimit.status == 10,
            )
        )
        total_used = db.scalar(
            select(func.coalesce(func.sum(CoreLimit.used_amount), 0)).where(
                CoreLimit.customer_id == customer_id
            )
        )
        detail["core_info"] = {
            "current_limit": (
                {
                    "id": current.id,
                    "credit_amount": float(current.credit_amount),
                    "valid_begin_date": current.valid_begin_date,
                    "valid_end_date": current.valid_end_date,
                    "used_amount": float(current.used_amount),
                    "remaining_amount": float(current.remaining_amount),
                    "status": current.status,
                }
                if current
                else None
            ),
            "total_used_amount": float(total_used or 0),
        }

    # 联系人列表
    contact_rows = db.execute(
        select(
            CustomerContact.id,
            CustomerContact.name,
            CustomerContact.phone,
            CustomerContact.email,
            CustomerContact.addr,
            CustomerContact.is_primary,
            CustomerContact.remark,
            User.name,
        )
        .join(User, User.id == CustomerContact.created_by)
        .where(CustomerContact.customer_id == customer_id)
        .order_by(CustomerContact.is_primary.desc(), CustomerContact.id)
    ).all()
    detail["contacts"] = [
        {
            "id": row[0],
            "name": row[1],
            "phone": row[2],
            "email": row[3],
            "addr": row[4],
            "is_primary": row[5],
            "remark": row[6],
            "created_by_name": row[7],
        }
        for row in contact_rows
    ]

    return detail


# ===== 创建 / 批量移交（直写，无审批）=====

def _validate_create_payload(db: Session, data: dict) -> None:
    """创建校验：三个业务唯一字段 + 外键存在性。"""
    from app.user.models import User

    # short_name 唯一
    if data.get("short_name"):
        dup = db.scalar(select(Customer.id).where(Customer.short_name == data["short_name"]))
        if dup is not None:
            raise BizError(4091, "客户简称已存在")

    # license_num 唯一（企业=信用代码 / 个人=身份证号，统一落主表）
    if data.get("license_num"):
        dup = db.scalar(select(Customer.id).where(Customer.license_num == data["license_num"]))
        if dup is not None:
            genre = data.get("genre")
            label = "统一社会信用代码" if genre == Genre.COMPANY else "身份证号"
            raise BizError(4091, f"{label}已存在")

    # 外键存在性（区域必填；行业/集团可空，空值跳过校验）

    if db.get(User, data.get("managementor_id")) is None:
        raise BizError(4041, "管护经理不存在")
    controler_id = data.get("controler_id")
    if controler_id is not None and db.get(User, controler_id) is None:
        raise BizError(4041, "风控专员不存在")


def create_customer(db: Session, body: CustomerCreate, user_id: int) -> int:
    """添加客户 → 直接落库（不走审批）。"""
    from app.user.models import Region

    from app.customer.models import Group, Industry as IndustryModel

    data = body.model_dump()
    _validate_create_payload(db, data)

    # 外键存在性（全部可空，空值跳过校验）
    region_id = data.get("region_id")
    if region_id is not None and db.get(Region, region_id) is None:
        raise BizError(4041, "行政区域不存在")
    industry_id = data.get("industry_id")
    if industry_id is not None and db.get(IndustryModel, industry_id) is None:
        raise BizError(4041, "行业不存在")
    if data.get("group_id") and db.get(Group, data["group_id"]) is None:
        raise BizError(4041, "集团不存在")

    company = data.pop("company", None)
    personal = data.pop("personal", None)
    tags = data.pop("tags", [])
    contacts = data.pop("contacts", None) or []

    customer = Customer(
        **data,
        created_by=user_id,
        classification=Classification.NORMAL,
    )
    db.add(customer)
    db.flush()
    if tags:
        _replace_tags(db, customer.id, tags)

    if customer.genre == Genre.COMPANY and company:
        db.add(CompanyProfile(customer_id=customer.id, **company))
    elif customer.genre == Genre.PERSONAL and personal:
        db.add(PersonalProfile(customer_id=customer.id, **personal))

    for c in contacts:
        db.add(CustomerContact(customer_id=customer.id, created_by=user_id, **c))

    return customer.id


def batch_transfer(db: Session, body: CustomerTransferReq, user_id: int) -> int:
    """批量管护经理移交 → 直接一条 UPDATE（不走审批，≤200 个客户）。"""
    from app.user.models import User

    if db.get(User, body.to_managementor_id) is None:
        raise BizError(4041, "目标管护经理不存在")

    # 校验客户存在
    for cid in body.customer_ids:
        _get_or_404(db, cid)

    db.query(Customer).filter(
        Customer.id.in_(body.customer_ids)
    ).update(
        {"managementor_id": body.to_managementor_id},
        synchronize_session=False,
    )
    return len(body.customer_ids)


# ===== 自由字段 PATCH / 删除 =====

def update_free_fields(db: Session, customer_id: int, body: CustomerUpdate) -> None:
    c = _get_or_404(db, customer_id)
    data = body.model_dump(exclude_unset=True)
    if not data:
        return
    # license_num 唯一性预检（避免直撞 unique 索引报 IntegrityError）
    new_license = data.get("license_num")
    if new_license:
        dup = db.scalar(select(Customer.id).where(Customer.license_num == new_license, Customer.id != customer_id))
        if dup is not None:
            label = "统一社会信用代码" if c.genre == Genre.COMPANY else "身份证号"
            raise BizError(4091, f"{label}已存在")
    tags = data.pop("tags", None)
    for k, v in data.items():
        setattr(c, k, v)
    if tags is not None:
        _replace_tags(db, customer_id, tags)


def change_controler(db: Session, customer_id: int, controler_id: int) -> None:
    from app.user.models import User

    c = _get_or_404(db, customer_id)
    if db.get(User, controler_id) is None:
        raise BizError(4041, "风控专员不存在")
    c.controler_id = controler_id


# ===== 经营快照 / 划型 / 分类 =====

def add_extend(
    db: Session, customer_id: int, sales_revenue: float, total_assets: float,
    people_engaged: float, data_date, user_id: int,
) -> int:
    c = _get_or_404(db, customer_id)
    if c.genre != Genre.COMPANY:
        raise BizError(4001, "仅企业客户可添加经营信息")

    # upsert（同 (customer_id, data_date) 覆盖）
    existing = db.scalar(
        select(CustomerExtend).where(
            CustomerExtend.customer_id == customer_id,
            CustomerExtend.data_date == data_date,
        )
    )
    typing = _classify_typing(db, customer_id, sales_revenue, total_assets, people_engaged)
    if existing:
        existing.sales_revenue = sales_revenue
        existing.total_assets = total_assets
        existing.people_engaged = people_engaged
        existing.typing = typing
        extend_id = existing.id
    else:
        e = CustomerExtend(
            customer_id=customer_id, sales_revenue=sales_revenue,
            total_assets=total_assets, people_engaged=people_engaged,
            data_date=data_date, typing=typing, created_by=user_id,
        )
        db.add(e)
        db.flush()
        extend_id = e.id

    # 同步主表快照 + 扩展表划型
    c.sales_revenue = sales_revenue
    c.total_assets = total_assets
    c.people_engaged = people_engaged
    c.data_date = data_date
    cp = db.scalar(
        select(CompanyProfile).where(CompanyProfile.customer_id == customer_id)
    )
    if cp:
        cp.typing = typing
    return extend_id


def delete_extend(db: Session, customer_id: int, extend_id: int) -> None:
    e = db.get(CustomerExtend, extend_id)
    if e is None or e.customer_id != customer_id:
        raise BizError(4041, "经营信息不存在")
    db.delete(e)


def list_extends(db: Session, customer_id: int) -> list[dict]:
    """经营快照历史列表（按基准日倒序）。"""
    from app.user.models import User

    _get_or_404(db, customer_id)
    rows = db.execute(
        select(CustomerExtend, User.name)
        .join(User, User.id == CustomerExtend.created_by)
        .where(CustomerExtend.customer_id == customer_id)
        .order_by(CustomerExtend.data_date.desc())
    ).all()
    return [
        {
            "id": e.id,
            "sales_revenue": float(e.sales_revenue),
            "total_assets": float(e.total_assets),
            "people_engaged": float(e.people_engaged),
            "data_date": e.data_date,
            "typing": e.typing,
            "created_by_name": uname,
        }
        for e, uname in rows
    ]


def _classify_typing(
    db: Session, customer_id: int, sales_revenue: float,
    total_assets: float, people_engaged: float,
) -> int:
    """划型（同步版，简化规则）：三指标就高不就低。

    M2 简化：按人数规则划型（<20 微型, 20-100 小型, 100-300 中型, >300 大型）。
    工信部分行业划型标准表 M2 后续按需补充（预留 industry_c 维度）。
    """
    if people_engaged < 20:
        return 10
    if people_engaged < 100:
        return 20
    if people_engaged < 300:
        return 30
    return 40


def change_classification(
    db: Session, customer_id: int, classification: int, reason: str, user_id: int
) -> None:
    c = _get_or_404(db, customer_id)
    c.classification = classification


# ===== 子资源：股东/董事/配偶 =====

def _get_company_profile(db: Session, customer_id: int) -> CompanyProfile:
    c = _get_or_404(db, customer_id)
    if c.genre != Genre.COMPANY:
        raise BizError(4001, "仅企业客户有股东/董事")
    cp = db.scalar(
        select(CompanyProfile).where(CompanyProfile.customer_id == customer_id)
    )
    if cp is None:
        raise BizError(4041, "企业扩展信息不存在")
    return cp


def list_shareholders(db: Session, customer_id: int) -> list[dict]:
    cp = _get_company_profile(db, customer_id)
    rows = db.scalars(
        select(Shareholder).where(Shareholder.company_id == cp.id)
        .order_by(Shareholder.shareholding_ratio.desc())
    ).all()
    return [
        {
            "id": s.id, "shareholder_name": s.shareholder_name,
            "invested_amount": float(s.invested_amount or 0),
            "shareholding_ratio": float(s.shareholding_ratio),
        }
        for s in rows
    ]


def add_shareholder(
    db: Session, customer_id: int, shareholder_name: str,
    invested_amount: float, shareholding_ratio: float, user_id: int,
) -> int:
    cp = _get_company_profile(db, customer_id)
    total = db.scalar(
        select(func.coalesce(func.sum(Shareholder.shareholding_ratio), 0)).where(
            Shareholder.company_id == cp.id
        )
    )
    if float(total or 0) + shareholding_ratio > 100:
        raise BizError(4091, f"持股比例合计将超过 100%（当前 {float(total or 0)}%）")
    dup = db.scalar(
        select(Shareholder.id).where(
            Shareholder.company_id == cp.id,
            Shareholder.shareholder_name == shareholder_name,
        )
    )
    if dup is not None:
        raise BizError(4091, "同名股东已存在")
    s = Shareholder(
        company_id=cp.id, shareholder_name=shareholder_name,
        invested_amount=invested_amount, shareholding_ratio=shareholding_ratio,
    )
    db.add(s)
    db.flush()
    return s.id


def delete_shareholder(db: Session, customer_id: int, shareholder_id: int) -> None:
    cp = _get_company_profile(db, customer_id)
    s = db.get(Shareholder, shareholder_id)
    if s is None or s.company_id != cp.id:
        raise BizError(4041, "股东不存在")
    db.delete(s)


def list_directors(db: Session, customer_id: int) -> list[dict]:
    cp = _get_company_profile(db, customer_id)
    rows = db.scalars(
        select(Director).where(Director.company_id == cp.id).order_by(Director.ordery)
    ).all()
    return [
        {"id": d.id, "director_name": d.director_name, "ordery": d.ordery}
        for d in rows
    ]


def add_director(
    db: Session, customer_id: int, director_name: str, user_id: int
) -> int:
    cp = _get_company_profile(db, customer_id)
    dup = db.scalar(
        select(Director.id).where(
            Director.company_id == cp.id, Director.director_name == director_name
        )
    )
    if dup is not None:
        raise BizError(4091, "同名董事已存在")
    max_order = db.scalar(
        select(func.max(Director.ordery)).where(Director.company_id == cp.id)
    ) or 0
    d = Director(
        company_id=cp.id, director_name=director_name, ordery=max_order + 1
    )
    db.add(d)
    db.flush()
    return d.id


def delete_director(db: Session, customer_id: int, director_id: int) -> None:
    cp = _get_company_profile(db, customer_id)
    d = db.get(Director, director_id)
    if d is None or d.company_id != cp.id:
        raise BizError(4041, "董事不存在")
    db.delete(d)


def order_directors(db: Session, customer_id: int, ordered_ids: list[int]) -> None:
    cp = _get_company_profile(db, customer_id)
    for idx, did in enumerate(ordered_ids, start=1):
        d = db.get(Director, did)
        if d is None or d.company_id != cp.id:
            raise BizError(4041, f"董事 {did} 不存在")
        d.ordery = idx


def bind_spouse(db: Session, customer_id: int, spouse_customer_id: int, user_id: int) -> None:
    c = _get_or_404(db, customer_id)
    s = _get_or_404(db, spouse_customer_id)
    if c.genre != Genre.PERSONAL or s.genre != Genre.PERSONAL:
        raise BizError(4001, "配偶双方必须都是个人客户")
    if customer_id == spouse_customer_id:
        raise BizError(4001, "不能与自己绑定配偶")

    cp1 = db.scalar(
        select(PersonalProfile).where(PersonalProfile.customer_id == customer_id)
    )
    cp2 = db.scalar(
        select(PersonalProfile).where(PersonalProfile.customer_id == spouse_customer_id)
    )
    if cp1 is None or cp2 is None:
        raise BizError(4041, "个人扩展信息不存在")
    if cp1.spouse_id or cp2.spouse_id:
        raise BizError(4091, "任一方已绑定配偶，请先解绑")

    # 双向关联 + 双方已婚
    cp1.spouse_id = spouse_customer_id
    cp2.spouse_id = customer_id
    cp1.marital_status = 20
    cp2.marital_status = 20


def unbind_spouse(db: Session, customer_id: int, user_id: int) -> None:
    c = _get_or_404(db, customer_id)
    cp1 = db.scalar(
        select(PersonalProfile).where(PersonalProfile.customer_id == customer_id)
    )
    if cp1 is None or cp1.spouse_id is None:
        raise BizError(4041, "该客户未绑定配偶")
    cp2 = db.scalar(
        select(PersonalProfile).where(PersonalProfile.customer_id == cp1.spouse_id)
    )
    cp1.spouse_id = None
    cp1.marital_status = 10
    if cp2 is not None:
        cp2.spouse_id = None
        cp2.marital_status = 10


# ===== 核心企业额度 =====

def list_core_limits(db: Session, customer_id: int) -> list[dict]:
    _get_or_404(db, customer_id)
    rows = db.scalars(
        select(CoreLimit)
        .where(CoreLimit.customer_id == customer_id)
        .order_by(CoreLimit.status, CoreLimit.valid_begin_date.desc())
    ).all()
    return [
        {
            "id": r.id,
            "credit_amount": float(r.credit_amount),
            "valid_begin_date": r.valid_begin_date,
            "valid_end_date": r.valid_end_date,
            "used_amount": float(r.used_amount),
            "remaining_amount": float(r.remaining_amount),
            "status": r.status,
            "status_display": _disp("core_limit_status", r.status),
            "remark": r.remark,
        }
        for r in rows
    ]


def add_core_limit(
    db: Session, customer_id: int, credit_amount: float,
    valid_begin_date, valid_end_date, remark: str | None, user_id: int,
) -> int:
    _get_or_404(db, customer_id)
    if valid_end_date <= valid_begin_date:
        raise BizError(4001, "额度到期日必须晚于起始日")

    # 旧额度失效 + 写历史
    olds = db.scalars(
        select(CoreLimit).where(
            CoreLimit.customer_id == customer_id, CoreLimit.status == 10
        )
    ).all()
    lim = CoreLimit(
        customer_id=customer_id, credit_amount=credit_amount,
        valid_begin_date=valid_begin_date, valid_end_date=valid_end_date,
        used_amount=0, remaining_amount=credit_amount,
        status=10, remark=remark,
    )
    db.add(lim)
    db.flush()
    for old in olds:
        old.status = 20
    db.add(
        CoreHistory(
            customer_id=customer_id,
            change_content={
                "action": "新增额度",
                "credit_amount": credit_amount,
                "valid_begin_date": str(valid_begin_date),
                "valid_end_date": str(valid_end_date),
                "expired_old_ids": [o.id for o in olds],
            },
            changed_by=user_id,
        )
    )
    # 异步刷新授信区域已用额度（容错）
    try:
        from app.customer.services import credit_region_service

        if c.credit_region_id:
            credit_region_service.recalc_used_amount(db, c.credit_region_id)
    except Exception:  # noqa: BLE001 刷新失败不影响主流程
        pass
    return lim.id


def update_core_limit(
    db: Session, customer_id: int, limit_id: int, data: dict, user_id: int
) -> None:
    c = _get_or_404(db, customer_id)
    lim = db.get(CoreLimit, limit_id)
    if lim is None or lim.customer_id != customer_id:
        raise BizError(4041, "额度记录不存在")

    changes: dict = {}
    for k, v in data.items():
        if v is None:
            continue
        old_v = getattr(lim, k)
        if old_v != v:
            changes[k] = {"before": str(old_v), "after": str(v)}
        setattr(lim, k, v)
    # 重算剩余额
    lim.remaining_amount = float(lim.credit_amount) - float(lim.used_amount)
    if changes:
        db.add(
            CoreHistory(
                customer_id=customer_id,
                change_content=changes,
                changed_by=user_id,
            )
        )


def list_core_histories(db: Session, customer_id: int) -> list[dict]:
    from app.user.models import User

    _get_or_404(db, customer_id)
    rows = db.execute(
        select(CoreHistory, User.name)
        .join(User, User.id == CoreHistory.changed_by)
        .where(CoreHistory.customer_id == customer_id)
        .order_by(CoreHistory.id.desc())
    ).all()
    return [
        {
            "id": h.id,
            "change_content": h.change_content,
            "changed_by_name": hname,
            "updated_at": h.updated_at,
        }
        for h, hname in rows
    ]


# ===== 字典 / 统计 =====

def customer_dict(
    db: Session, genre: int | None = None,
    managementor_id: int | None = None,
    q: str | None = None, page: int = 1, page_size: int = 50,
) -> tuple[list[dict], int]:
    """客户下拉字典（表单选择用）。无 data_scope——业务模块选所有权人/保证人等
    时需要看到全量客户，不应被 managementor 归属过滤。

    返回 (items, total)，前端分页/远程搜索用。
    """
    from app.user.models import User

    stmt = select(Customer, User.name).join(
        User, User.id == Customer.managementor_id
    )
    if genre is not None:
        stmt = stmt.where(Customer.genre == genre)
    if managementor_id is not None:
        stmt = stmt.where(Customer.managementor_id == managementor_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Customer.name.like(like), Customer.short_name.like(like))
        )

    # 先 count 再分页
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.scalar(count_stmt) or 0

    rows = db.execute(
        stmt.order_by(Customer.short_name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        {
            "id": c.id, "name": c.name, "short_name": c.short_name,
            "genre": c.genre, "managementor_name": mname,
        }
        for c, mname in rows
    ]
    return items, total


def stats_overview(db: Session) -> dict:
    total = db.scalar(select(func.count(Customer.id))) or 0
    credit_sum, amount_sum = db.execute(
        select(
            func.coalesce(func.sum(Customer.credit_amount), 0),
            func.coalesce(func.sum(Customer.amount), 0),
        )
    ).one()
    cls_rows = db.execute(
        select(Customer.classification, func.count()).group_by(Customer.classification)
    ).all()
    return {
        "total_count": total,
        "total_credit_amount": float(credit_sum),
        "total_amount": float(amount_sum),
        "classification_distribution": {
            _disp("classification", c): n for c, n in cls_rows
        },
    }


def stats_industry_chart(db: Session) -> list[dict]:
    from app.customer.models import Industry

    rows = db.execute(
        select(
            Industry.name,
            func.count(Customer.id),
            func.coalesce(func.sum(Customer.amount), 0),
        )
        .join(Customer, Customer.industry_id == Industry.id)
        .group_by(Industry.name)
        .order_by(func.count(Customer.id).desc())
    ).all()
    return [
        {"industry_name": name, "count": n, "total_amount": float(amt)}
        for name, n, amt in rows
    ]


def region_summary(db: Session, region_id: int) -> dict:
    """授信区域内成员授信/在保汇总（实时统计）。"""
    agg = db.execute(
        select(
            func.count(Customer.id),
            func.coalesce(func.sum(Customer.credit_amount), 0),
            func.coalesce(func.sum(Customer.amount), 0),
        ).where(Customer.credit_region_id == region_id)
    ).one()
    return {
        "member_count": agg[0],
        "total_credit_amount": float(agg[1]),
        "total_amount": float(agg[2]),
    }


# ===== 联系人 CRUD =====

def list_contacts(db: Session, customer_id: int) -> list[dict]:
    from app.user.models import User

    _get_or_404(db, customer_id)
    rows = db.execute(
        select(CustomerContact, User.name)
        .join(User, User.id == CustomerContact.created_by)
        .where(CustomerContact.customer_id == customer_id)
        .order_by(CustomerContact.is_primary.desc(), CustomerContact.id)
    ).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "phone": c.phone,
            "email": c.email,
            "addr": c.addr,
            "is_primary": c.is_primary,
            "remark": c.remark,
            "created_by_name": cname,
        }
        for c, cname in rows
    ]


def add_contact(
    db: Session, customer_id: int, body: CustomerContactCreate, user_id: int
) -> int:
    _get_or_404(db, customer_id)
    dup = db.scalar(
        select(CustomerContact.id).where(
            CustomerContact.customer_id == customer_id,
            CustomerContact.name == body.name,
        )
    )
    if dup is not None:
        raise BizError(4091, "同名联系人已存在")
    c = CustomerContact(
        customer_id=customer_id, created_by=user_id, **body.model_dump()
    )
    db.add(c)
    if body.is_primary:
        _clear_other_primaries(db, customer_id, exclude_contact_id=None)
    db.flush()
    return c.id


def update_contact(
    db: Session, customer_id: int, contact_id: int, body: CustomerContactUpdate
) -> None:
    c = _get_contact(db, customer_id, contact_id)
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    for k, v in data.items():
        setattr(c, k, v)
    # 如果本次把 is_primary 设为 True，清掉同客户其他联系人的首选
    if data.get("is_primary") is True:
        _clear_other_primaries(db, customer_id, exclude_contact_id=contact_id)


def delete_contact(db: Session, customer_id: int, contact_id: int) -> None:
    c = _get_contact(db, customer_id, contact_id)
    db.delete(c)


def _clear_other_primaries(
    db: Session, customer_id: int, exclude_contact_id: int | None
) -> None:
    """同客户项下设了首选后，将其他联系人的 is_primary 清零。

    exclude_contact_id：本次刚设为首选的联系人 ID（update 场景需跳过自身，
    add 场景传 None 让 SQL 忽略该条件——新加行还没 flush 也无冲突）。
    """
    stmt = (
        update(CustomerContact)
        .where(CustomerContact.customer_id == customer_id)
        .where(CustomerContact.is_primary.is_(True))
        .values(is_primary=False)
    )
    if exclude_contact_id is not None:
        stmt = stmt.where(CustomerContact.id != exclude_contact_id)
    db.execute(stmt)


def _get_contact(db: Session, customer_id: int, contact_id: int) -> CustomerContact:
    c = db.get(CustomerContact, contact_id)
    if c is None or c.customer_id != customer_id:
        raise BizError(4041, "联系人不存在")
    return c
