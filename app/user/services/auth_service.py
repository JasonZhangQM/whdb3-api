"""认证服务：登录（三层保护）/ 登出 / 刷新 / 验证码 / 改密。

登录保护（详设 §4.3）：
锁检查(最前) → 验证码(失败计数≥3 强制) → 密码校验 → 成功清计数。
失败计数：ZSET 滑动窗口 member=ip:nonce；5 次锁 15 分钟、10 次锁 2 小时。
"""

import base64
import logging
import random
import secrets
import string
import time
import uuid
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import BizError
from app.core.security import (
    PasswordService,
    TokenService,
    redis_client,
)
from app.user.enums import UserStatus
from app.user.models import LoginLog, User
from app.user.schemas.auth import LoginReq, LoginResult, TokenPair
from app.user.services import context_service

logger = logging.getLogger(__name__)

KEY_LOGINFAIL = "whdb_api:loginfail:{username}"
KEY_LOGINLOCK = "whdb_api:loginlock:{username}"
KEY_CAPTCHA = "whdb_api:captcha:{id}"
FAIL_WINDOW = 900  # 15 分钟滑窗
CAPTCHA_TTL = 120

STATUS_SUCCESS = 10
STATUS_WRONG_PWD = 20
STATUS_LOCKED = 30
STATUS_DISABLED = 31
STATUS_CAPTCHA_ERROR = 32


def _log(db: Session, username: str | None, status: int, message: str,
         ip: str | None, ua: str | None, login_type: str = "login",
         user_id: int | None = None) -> None:
    db.add(LoginLog(
        user_id=user_id, username=username, login_type=login_type,
        ip=ip, user_agent=ua, status=status, message=message,
    ))


def _record_fail(username: str, ip: str | None, status: int, db: Session) -> int:
    """滑窗计数 + 条件锁定（5→15min，10→2h）。返回当前计数。"""
    key = KEY_LOGINFAIL.format(username=username)
    now = time.time()
    redis_client.zremrangebyscore(key, 0, now - FAIL_WINDOW)
    redis_client.zadd(key, {f"{ip or '-'}:{uuid.uuid4().hex[:8]}": now})
    redis_client.expire(key, FAIL_WINDOW)
    count = redis_client.zcard(key)
    if count == 5:
        redis_client.setex(KEY_LOGINLOCK.format(username=username), 900, "1")
    elif count == 10:
        redis_client.setex(KEY_LOGINLOCK.format(username=username), 7200, "1")
    _log(db, username, status, f"fail_count={count}", ip, None)
    db.commit()
    return count


def generate_captcha() -> dict:
    """生成 SVG 图形验证码（一次性，TTL 120s）。"""
    captcha_id = uuid.uuid4().hex
    code = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    redis_client.setex(KEY_CAPTCHA.format(id=captcha_id), CAPTCHA_TTL, code.lower())
    # 简易干扰：随机旋转 + 偏移的 SVG 文本
    chars = "".join(
        f'<text x="{30 + i * 28}" y="34" font-size="26" font-family="monospace" '
        f'font-weight="bold" fill="hsl({random.randint(0, 360)},70%,40%)" '
        f'transform="rotate({random.randint(-15, 15)}, {30 + i * 28}, 30)">{c}</text>'
        for i, c in enumerate(code)
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="130" height="44">'
        f'<rect width="100%" height="100%" fill="#f0f2f5"/>{chars}'
        f'<line x1="5" y1="{random.randint(8, 36)}" x2="125" y2="{random.randint(8, 36)}" '
        f'stroke="#ccc" stroke-width="1"/></svg>'
    )
    b64 = base64.b64encode(svg.encode()).decode()
    return {"captcha_id": captcha_id, "image": f"data:image/svg+xml;base64,{b64}"}


def _verify_captcha(captcha_id: str | None, captcha_code: str | None) -> bool:
    if not captcha_id or not captcha_code:
        return False
    key = KEY_CAPTCHA.format(id=captcha_id)
    stored = redis_client.get(key)
    if stored is None or stored != captcha_code.lower():
        return False
    redis_client.delete(key)  # 一次性
    return True


def login(db: Session, req: LoginReq, ip: str | None, ua: str | None) -> LoginResult:
    username = req.account

    # 1. 锁定检查（最前——锁定期连验证码口子也关死，防爆破）
    if redis_client.exists(KEY_LOGINLOCK.format(username=username)):
        _log(db, username, STATUS_LOCKED, "账号锁定期间尝试登录", ip, ua)
        db.commit()
        raise BizError(4013, "账号已锁定，请稍后再试")

    # 2. 验证码（失败计数 >= 3 时强制）
    fail_count = redis_client.zcard(KEY_LOGINFAIL.format(username=username))
    if fail_count >= 3 and not _verify_captcha(req.captcha_id, req.captcha_code):
        _record_fail(username, ip, STATUS_CAPTCHA_ERROR, db)
        raise BizError(4014, "验证码错误或已过期")

    # 3. 密码校验（统一模糊文案，不暴露账号是否存在）
    user = db.scalar(
        select(User).where(or_(User.username == username, User.email == username))
    )
    if user is None or not PasswordService.verify(req.password, user.password_hash):
        _record_fail(username, ip, STATUS_WRONG_PWD, db)
        raise BizError(4010, "账号或密码错误")

    if user.status != UserStatus.ACTIVE.value:
        _log(db, user.username, STATUS_DISABLED, f"status={user.status}", ip, ua, user_id=user.id)
        db.commit()
        raise BizError(4013, "账号已停用或离职")

    # 4. 成功：清计数、发双 token、记录登录信息
    redis_client.delete(KEY_LOGINFAIL.format(username=username))
    user.login_fail_count = 0
    user.last_login_at = datetime.now()
    user.last_login_ip = ip
    _log(db, user.username, STATUS_SUCCESS, "登录成功", ip, ua, user_id=user.id)
    db.commit()

    access, _, expires_in = TokenService.issue_access_token(user.id, user.username)
    refresh = TokenService.issue_refresh_token(user.id)
    return LoginResult(
        tokens=TokenPair(
            access_token=access, refresh_token=refresh, expires_in=expires_in
        ),
        must_change_password=user.must_change_password,
    )


def refresh(db: Session, refresh_token: str, ip: str | None, ua: str | None) -> TokenPair:
    """旋转式刷新：旧 refresh 作废，签发新对。"""
    new_refresh, user_id = TokenService.rotate_refresh(refresh_token)
    user = db.get(User, user_id)
    if user is None or user.status != UserStatus.ACTIVE.value:
        raise BizError(4012, "refresh token 无效")
    access, _, expires_in = TokenService.issue_access_token(user.id, user.username)
    _log(db, user.username, STATUS_SUCCESS, "token 刷新", ip, ua, "refresh", user_id)
    db.commit()
    return TokenPair(
        access_token=access, refresh_token=new_refresh, expires_in=expires_in
    )


def logout(db: Session, token: str, ip: str | None, ua: str | None) -> None:
    payload = TokenService.verify_access_token(token)
    user_id = int(payload["sub"])
    TokenService.revoke(user_id, payload["jti"], payload["exp"])
    _log(db, payload.get("username"), STATUS_SUCCESS, "登出", ip, ua, "logout", user_id)
    db.commit()


def change_my_password(db: Session, user: User, old_password: str, new_password: str) -> None:
    """改本人密码：校验旧密 + 策略 + 踢出全部会话。"""
    if not PasswordService.verify(old_password, user.password_hash):
        raise BizError(4010, "原密码错误")
    if err := PasswordService.validate_policy(new_password):
        raise BizError(4001, err)
    user.password_hash = PasswordService.hash(new_password)
    user.must_change_password = False
    db.commit()
    # 踢出全部会话（旧 access 由前端 4011 后重新登录；refresh 已删）
    TokenService.revoke_all(user.id)
    context_service.invalidate(user.id)


def generate_random_password() -> str:
    """强随机密码（满足策略：≥10 位、大小写+数字）。"""
    alphabet = string.ascii_letters + string.digits
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(12))
        if PasswordService.validate_policy(pwd) is None:
            return pwd
