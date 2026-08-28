"""机构服务聚合出口：按 model 拆分（主表/联系人/分支/协议），此处仅 re-export。

路由层统一 `from app.institution import services as svc` 后调 `svc.xxx`。
"""

from app.institution.services.agreement_service import (  # noqa: F401
    add_agreement,
    delete_agreement,
    list_agreements,
    list_credit_histories,
    update_agreement,
)
from app.institution.services.branch_service import (  # noqa: F401
    add_branch,
    delete_branch,
    list_branches,
    update_branch,
)
from app.institution.services.contact_service import (  # noqa: F401
    add_contact,
    delete_contact,
    list_contacts,
    update_contact,
)
from app.institution.services.institution_service import (  # noqa: F401
    change_status,
    create,
    delete,
    expire_agreements_job,
    get_detail,
    list_institutions,
    recalc_institution_balance,
    stats_balance_summary,
    stats_overview,
    update,
)
