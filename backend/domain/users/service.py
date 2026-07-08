import hashlib
import hmac
import os
import uuid
from datetime import datetime, timedelta, timezone

try:
    import bcrypt
except ImportError:  # pragma: no cover - exercised in environments with broken bcrypt installs
    bcrypt = None

from jose import jwt

from backend.core.config import settings
from backend.domain.users.model import User
from backend.domain.users.repository import UserRepository
from backend.common.base_service import BaseService
from backend.common.schema import UserCreate, UserOut, UserUpdate
from backend.core.security.token_store import TokenStore

_session_revocation_store = TokenStore()
_DUMMY_HASH = None


class UserService(BaseService[User, UserCreate, UserUpdate]):
    def __init__(self, repository: UserRepository) -> None:
        super().__init__(repository)

    @staticmethod
    def hash_password(password: str) -> str:
        if bcrypt is not None:
            return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        salt = hashlib.sha256(os.urandom(16)).hexdigest().encode("utf-8")
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, 100_000)
        return "pbkdf2_sha256$100000$" + salt.decode("utf-8") + "$" + digest.hex()

    @staticmethod
    def verify_password(password: str, hashed_password: str) -> bool:
        if bcrypt is not None:
            return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))

        if not hashed_password.startswith("pbkdf2_sha256$"):
            return False

        _, iterations, salt, expected = hashed_password.split("$", 3)
        iterations = int(iterations)
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations,
        )
        return hmac.compare_digest(derived.hex(), expected)

    async def create(self, obj_in: UserCreate) -> User:
        user = User(
            email=obj_in.email,
            username=obj_in.username,
            hashed_password=self.hash_password(obj_in.password),
            is_active=True,
            is_verified=False,
            is_superuser=False,
            role="user",
            permissions=[],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        return await self.repository.create(user)

    async def delete(self, db_obj: User) -> None:
        db_obj.deleted_at = datetime.now(timezone.utc)
        db_obj.updated_at = datetime.now(timezone.utc)
        self.repository.db.add(db_obj)
        await self.repository.db.flush()
        await self.repository.db.refresh(db_obj)

    async def update(self, db_obj: User, obj_in: UserUpdate) -> User:
        update_data = obj_in.model_dump(exclude_unset=True)

        new_password = update_data.pop("password", None)
        if new_password:
            db_obj.hashed_password = self.hash_password(new_password)
            await _session_revocation_store.revoke_all_for_user(db_obj.id)

        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db_obj.updated_at = datetime.now(timezone.utc)
        self.repository.db.add(db_obj)
        await self.repository.db.flush()
        await self.repository.db.refresh(db_obj)
        return db_obj

    @staticmethod
    def _normalize_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    async def authenticate(self, email: str, password: str) -> User | None:
        user = await self.repository.get_by_email(email)

        if not user:
            global _DUMMY_HASH
            if _DUMMY_HASH is None:
                _DUMMY_HASH = self.hash_password(
                    "not-a-real-password-used-only-for-timing")
            self.verify_password(password, _DUMMY_HASH)
            return None

        now = datetime.now(timezone.utc)
        locked_until = self._normalize_datetime(user.locked_until)
        if locked_until and locked_until > now:
            return None

        if not self.verify_password(password, user.hashed_password):
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                user.locked_until = now + timedelta(minutes=15)
            self.repository.db.add(user)
            await self.repository.db.flush()
            await self.repository.db.commit()
            await self.repository.db.refresh(user)
            return None

        user.failed_login_attempts = 0
        user.locked_until = None
        self.repository.db.add(user)
        await self.repository.db.flush()
        await self.repository.db.commit()
        await self.repository.db.refresh(user)
        return user

    async def mark_verified(self, user: User) -> User:
        user.is_verified = True
        user.updated_at = datetime.now(timezone.utc)
        self.repository.db.add(user)
        await self.repository.db.flush()
        await self.repository.db.refresh(user)
        return user

    def create_access_token(self, user: User) -> str:
        payload = {
            "sub": str(user.id),
            "jti": str(uuid.uuid4()),
            "email": user.email,
            "username": user.username,
            "is_superuser": user.is_superuser,
            "exp": datetime.now(timezone.utc).timestamp() + settings.access_token_expire_minutes * 60,
        }
        return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)

    def to_public(self, user: User) -> UserOut:
        return UserOut.model_validate(user)
