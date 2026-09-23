"""测试前置：用临时 SQLite 跑应用，不依赖 PostgreSQL。

必须在导入 app.main 之前设好 DATABASE_URL，模块导入时即建立引擎。
"""

import os
import tempfile

_db_fd, _db_path = tempfile.mkstemp(prefix="methane-test-", suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import Reading, SessionLocal, app  # noqa: E402


@pytest.fixture()
def client():
    # TestClient 启动时会建表并写入种子数据，每个用例前清空，保证只看本用例写入的行
    with TestClient(app) as c:
        db = SessionLocal()
        try:
            db.query(Reading).delete()
            db.commit()
        finally:
            db.close()
        yield c


@pytest.fixture()
def writer_token(client):
    res = client.post(
        "/api/auth/login",
        json={"username": "gasman", "password": "gas123456"},
    )
    assert res.status_code == 200
    return res.json()["access_token"]


@pytest.fixture()
def auth_headers(writer_token):
    return {"Authorization": f"Bearer {writer_token}"}
