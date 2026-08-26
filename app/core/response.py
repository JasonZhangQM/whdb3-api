"""统一响应体：R / RPage。所有接口出参经此包装。"""

from typing import Any

from pydantic import BaseModel


class PageData(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int


class R(BaseModel):
    code: int = 0  # 0 成功；非 0 见错误码表
    message: str = "ok"
    data: Any = None


def ok(data: Any = None, message: str = "ok") -> dict:
    return R(code=0, message=message, data=data).model_dump()


def fail(code: int, message: str, data: Any = None) -> dict:
    return R(code=code, message=message, data=data).model_dump()


def page(items: list[Any], total: int, page_num: int, page_size: int) -> dict:
    return R(
        code=0,
        data=PageData(items=items, total=total, page=page_num, page_size=page_size),
    ).model_dump()
