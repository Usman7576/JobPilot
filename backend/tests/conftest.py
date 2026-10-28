from __future__ import annotations

import asyncio
import base64
import os
import sys
from collections.abc import AsyncIterator, Iterator

# --- Environment for the app under test (must run before any app import) ---------------
os.environ["ENV"] = "test"
os.environ.setdefault("SECRET_KEY", "test-secret-key-" + "x" * 32)
os.environ.setdefault("ENCRYPTION_KEYS", base64.urlsafe_b64encode(b"k" * 32).decode())
os.environ.setdefault("FILE_MASTER_KEY", base64.b64encode(b"m" * 32).decode())
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["MAIL_BACKEND"] = "console"
os.environ["APP_BASE_URL"] = "http://localhost:3000"
os.environ["GOOGLE_CLIENT_ID"] = "test-client-id"
os.environ["GOOGLE_CLIENT_SECRET"] = "test-client-secret"
_test_db = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://jobpilot:jobpilot@localhost:5432/jobpilot_test"
)
os.environ["DATABASE_URL"] = _test_db
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ["LLM_PROVIDER"] = "fake"
os.environ["WRITING_LLM_PROVIDER"] = ""
os.environ["HUNTER_API_KEY"] = ""
os.environ["EMBEDDING_PROVIDER"] = "fake"
os.environ["LLM_RPM"] = "0"
os.environ["LLM_RPD"] = "0"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"
os.environ["PASSWORD_HASH_MEMORY_KIB"] = "8192"

if sys.platform == "win32":  # psycopg's async mode needs the selector loop on Windows
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import async_session_factory  # noqa: E402
from app.main import app  # noqa: E402
from app.providers.llm import set_llm_override  # noqa: E402
from app.providers.llm.fake import FakeLLM  # noqa: E402
from app.providers.mailer import OutgoingMail, get_mailer, set_mailer_override  # noqa: E402
from app.providers.storage import LocalStorage, set_storage_override  # noqa: E402

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[OutgoingMail] = []

    async def send(self, mail: OutgoingMail) -> None:
        self.sent.append(mail)

    def send_sync(self, mail: OutgoingMail) -> None:
        self.sent.append(mail)

    def last_link(self) -> str:
        for line in reversed(self.sent[-1].text.splitlines()):
            if line.startswith("http"):
                return line
        raise AssertionError("no link in last mail")

    def last_token(self) -> str:
        return self.last_link().split("token=", 1)[1]


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> Iterator[None]:
    """Fresh schema per test session, built by the real migrations."""
    engine = create_engine(_test_db)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    engine.dispose()
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "migrations"))
    command.upgrade(cfg, "head")  # env.py reads DATABASE_URL, which points at the test DB
    yield


_cleanup_engine = create_engine(_test_db)


@pytest.fixture
def clean_tables(migrated_database: None) -> Iterator[None]:
    """Empty every table after a DB-touching test. DELETE beats TRUNCATE on tiny tables."""
    yield
    with _cleanup_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def mailer() -> Iterator[FakeMailer]:
    fake = FakeMailer()
    app.dependency_overrides[get_mailer] = lambda: fake
    set_mailer_override(fake)
    yield fake
    set_mailer_override(None)
    app.dependency_overrides.pop(get_mailer, None)


@pytest.fixture(autouse=True)
def storage(tmp_path_factory: pytest.TempPathFactory) -> Iterator[LocalStorage]:
    store = LocalStorage(str(tmp_path_factory.mktemp("uploads")))
    set_storage_override(store)
    yield store
    set_storage_override(None)


@pytest.fixture
def fake_llm() -> Iterator[FakeLLM]:
    fake = FakeLLM()
    set_llm_override(fake)
    yield fake
    set_llm_override(None)


@pytest.fixture
async def client(mailer: FakeMailer, clean_tables: None) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost:3000") as c:
        yield c


@pytest.fixture
async def db(clean_tables: None) -> AsyncIterator[AsyncSession]:
    async with async_session_factory()() as session:
        yield session


def csrf_headers(client: AsyncClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("csrf_token") or ""}


async def signup_and_verify(
    client: AsyncClient,
    mailer: FakeMailer,
    email: str = "ada@example.com",
    password: str = "correct horse battery",
) -> None:
    r = await client.post("/api/v1/auth/signup", json={"email": email, "password": password})
    assert r.status_code == 202
    r = await client.post("/api/v1/auth/verify-email", json={"token": mailer.last_token()})
    assert r.status_code == 200, r.text


async def login(
    client: AsyncClient, email: str = "ada@example.com", password: str = "correct horse battery"
) -> None:
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers=csrf_headers(client),
    )
    assert r.status_code == 200, r.text


async def signed_in(
    client: AsyncClient, mailer: FakeMailer, email: str = "ada@example.com"
) -> None:
    await signup_and_verify(client, mailer, email=email)
    await login(client, email=email)
