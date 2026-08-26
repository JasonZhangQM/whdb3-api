"""安全机制：JWT 双 token + bcrypt 密码 + Redis 客户端（无状态服务类，不含业务知识）。

token 语义（详设 §4）：
- access：HS256 JWT，30min，payload 含 sub/username/type/jti；登出黑名单按 jti
- refresh：secrets.token_urlsafe(48) 不透明串，有效性完全由 Redis 存在性决定
- 单设备语义：whdb_api:refresh:{user_id} 只存最新值，新登录覆盖旧 token
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import redis as redis_lib
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()

# decode_responses=True：bytes -> str，统一按字符串处理
redis_client: redis_lib.Redis = redis_lib.Redis.from_url(
    settings.redis_url, decode_responses=True
)

ACCESS_TTL = settings.jwt_access_expire_minutes * 60
REFRESH_TTL = settings.jwt_refresh_expire_days * 24 * 3600

KEY_REFRESH = "whdb_api:refresh:{user_id}"          # 正向：user -> 当前 token
KEY_REFRESH_PAYLOAD = "whdb_api:refresh:payload:{token}"  # 反向：token -> user（旋转校验用）
KEY_BLACKLIST = "whdb_api:blacklist:{jti}"
# 用户级吊销水位：iat 早于该时间戳的全部 access 失效（改密/重置/停用踢出）
KEY_REVOKE_BEFORE = "whdb_api:revoke_before:{user_id}"

# refresh 旋转原子化：比对+删旧+写新一步完成（防并发双刷产生两个活跃 token）
_ROTATE_LUA = """
local cur = redis.call('GET', KEYS[1])
if cur ~= ARGV[1] then return 0 end
redis.call('DEL', KEYS[1])
redis.call('DEL', KEYS[2])
redis.call('SETEX', KEYS[1], ARGV[4], ARGV[2])
redis.call('SETEX', KEYS[3], ARGV[4], ARGV[3])
return 1
"""


class PasswordService:
    _ctx = CryptContext(schemes=["bcrypt"], bcrypt__rounds=12)

    @classmethod
    def hash(cls, plain: str) -> str:
        return cls._ctx.hash(plain)

    @classmethod
    def verify(cls, plain: str, hashed: str) -> bool:
        return cls._ctx.verify(plain, hashed)

    @staticmethod
    def validate_policy(plain: str) -> str | None:
        """策略：≥10 位、含大小写字母与数字。返回错误信息，None 即通过。"""
        if len(plain) < 10:
            return "密码长度不得少于 10 位"
        if not any(c.isupper() for c in plain):
            return "密码须包含大写字母"
        if not any(c.islower() for c in plain):
            return "密码须包含小写字母"
        if not any(c.isdigit() for c in plain):
            return "密码须包含数字"
        return None


class TokenService:
    @staticmethod
    def issue_access_token(user_id: int, username: str) -> tuple[str, str, int]:
        """返回 (token, jti, expires_in)。"""
        now = datetime.now(timezone.utc)
        jti = uuid.uuid4().hex
        payload = {
            "sub": str(user_id),
            "username": username,
            "type": "access",
            "jti": jti,
            "iat": now,
            "exp": now + timedelta(seconds=ACCESS_TTL),
        }
        token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
        return token, jti, ACCESS_TTL

    @staticmethod
    def issue_refresh_token(user_id: int) -> str:
        """签发并写入双 key（新登录自然覆盖旧值 = 单设备语义）。"""
        token = secrets.token_urlsafe(48)
        pkey = KEY_REFRESH_PAYLOAD.format(token=token)
        redis_client.setex(KEY_REFRESH.format(user_id=user_id), REFRESH_TTL, token)
        redis_client.setex(pkey, REFRESH_TTL, str(user_id))
        return token

    @staticmethod
    def verify_access_token(token: str) -> dict:
        """验签 + 黑名单检查。失败抛 jwt 异常或 BizError(4010)。"""
        from app.core.exceptions import ERR_UNAUTHORIZED, BizError

        try:
            payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            raise  # 4011 过期，前端据此触发 refresh
        except jwt.InvalidTokenError:
            raise BizError(ERR_UNAUTHORIZED, "无效 token") from None
        if payload.get("type") != "access":
            raise BizError(ERR_UNAUTHORIZED, "无效 token")
        if redis_client.exists(KEY_BLACKLIST.format(jti=payload["jti"])):
            raise BizError(ERR_UNAUTHORIZED, "token 已吊销")
        # 用户级吊销水位：改密/重置/停用后，此前签发的全部 access 一并失效
        before = redis_client.get(KEY_REVOKE_BEFORE.format(user_id=payload["sub"]))
        if before and int(payload["iat"]) < int(float(before)):
            raise BizError(ERR_UNAUTHORIZED, "token 已吊销")
        return payload

    @staticmethod
    def rotate_refresh(old_token: str) -> tuple[str, int]:
        """旋转 refresh：返回 (new_token, user_id)。旧值作废（单活跃）。"""
        from app.core.exceptions import BizError, ERR_TOKEN_INVALID

        user_id = redis_client.get(KEY_REFRESH_PAYLOAD.format(token=old_token))
        if not user_id:
            raise BizError(ERR_TOKEN_INVALID, "refresh token 无效")
        user_id = int(user_id)
        new_token = secrets.token_urlsafe(48)
        ok = redis_client.eval(
            _ROTATE_LUA,
            3,
            KEY_REFRESH.format(user_id=user_id),
            KEY_REFRESH_PAYLOAD.format(token=old_token),
            KEY_REFRESH_PAYLOAD.format(token=new_token),
            old_token,
            new_token,
            str(user_id),
            REFRESH_TTL,
        )
        if not ok:
            raise BizError(ERR_TOKEN_INVALID, "refresh token 无效")
        return new_token, user_id

    @staticmethod
    def revoke(user_id: int, jti: str, access_exp: int) -> None:
        """登出：access 入黑名单（TTL=剩余寿命）+ 删 refresh 双 key。"""
        now = int(datetime.now(timezone.utc).timestamp())
        ttl = access_exp - now
        if ttl > 0:
            redis_client.setex(KEY_BLACKLIST.format(jti=jti), ttl, "1")
        token = redis_client.get(KEY_REFRESH.format(user_id=user_id))
        if token:
            redis_client.delete(KEY_REFRESH_PAYLOAD.format(token=token))
        redis_client.delete(KEY_REFRESH.format(user_id=user_id))

    @staticmethod
    def revoke_all(user_id: int) -> None:
        """密码重置/改密/停用后踢出全部会话：删 refresh 双 key + 设吊销水位。"""
        token = redis_client.get(KEY_REFRESH.format(user_id=user_id))
        if token:
            redis_client.delete(KEY_REFRESH_PAYLOAD.format(token=token))
        redis_client.delete(KEY_REFRESH.format(user_id=user_id))
        # 水位只需覆盖最长 access 寿命，过期自动清理
        now = int(datetime.now(timezone.utc).timestamp())
        redis_client.setex(KEY_REVOKE_BEFORE.format(user_id=user_id), ACCESS_TTL, str(now))
