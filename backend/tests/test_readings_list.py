"""回归测试：上报成功后，列表查询载荷必须包含刚写入的编号。

背景：曾存在“新行藏匿旁路”，GET /api/readings 会过滤掉最大编号、
改挂“待同步”提示，导致上报（含 WebSocket 推送）看似成功、总表却缺行。
因此这里的断言一律针对**列表接口返回的 items 载荷**，
不接受用推送文案“刚推送/已上报”闪过作为成功证据。
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.main import Reading


@pytest.fixture(scope="session")
def engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest.fixture(autouse=True)
def _patched_db(engine):
    """把应用绑定到内存 SQLite：每个用例一张干净的 readings 表。"""
    testing_session = sessionmaker(bind=engine)
    main_module.engine = engine
    main_module.SessionLocal = testing_session
    main_module.Base.metadata.drop_all(bind=engine)
    main_module.Base.metadata.create_all(bind=engine)
    yield
    main_module.Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client():
    # startup 事件只在首次建表/塞种子数据，这里已手工建表，直接用客户端即可
    from fastapi.testclient import TestClient

    with TestClient(app=main_module.app) as c:
        yield c


@pytest.fixture()
def token(client):
    res = client.post(
        "/api/auth/login",
        json={"username": "gasman", "password": "gas123456"},
    )
    assert res.status_code == 200
    return res.json()["access_token"]


@pytest.fixture()
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _list_ids(client, auth_headers):
    res = client.get("/api/readings", headers=auth_headers)
    assert res.status_code == 200
    return res.json()


def _post_reading(client, auth_headers, site, ch4_pct):
    res = client.post(
        "/api/readings",
        headers=auth_headers,
        json={"site": site, "ch4_pct": ch4_pct},
    )
    assert res.status_code == 201, res.text
    return res.json()


@pytest.mark.parametrize(
    "site,ch4_pct,expected_level",
    [
        ("东翼-12", 0.40, "正常"),
        ("回风巷", 1.40, "报警"),
    ],
)
def test_list_payload_contains_new_id_for_each_level(
    client, auth_headers, site, ch4_pct, expected_level
):
    """正常、报警各写一笔：列表载荷里都必须看得到这笔新编号。"""
    created = _post_reading(client, auth_headers, site, ch4_pct)
    new_id = created["id"]
    assert created["level"] == expected_level

    body = _list_ids(client, auth_headers)
    items = body["items"]
    ids = [r["id"] for r in items]

    # 核心断言：刚写入的编号必须出现在列表载荷，而不是被过滤掉
    assert new_id in ids
    new_row = next(r for r in items if r["id"] == new_id)
    assert new_row["site"] == site
    assert new_row["level"] == expected_level


def test_both_alarm_and_normal_visible_together(client, auth_headers):
    """报警与正常各写一笔后，两笔编号必须同时在总表中可见。"""
    normal = _post_reading(client, auth_headers, "东翼-21", 0.32)
    alarm = _post_reading(client, auth_headers, "回风巷", 1.80)

    body = _list_ids(client, auth_headers)
    items = body["items"]
    by_id = {r["id"]: r for r in items}

    assert normal["id"] in by_id
    assert alarm["id"] in by_id
    assert by_id[normal["id"]]["level"] == "正常"
    assert by_id[alarm["id"]]["level"] == "报警"
    # 最新一笔排在最前
    assert items[0]["id"] == alarm["id"]


def test_list_payload_has_no_bypass_or_pending_meta(client, auth_headers):
    """旁路废除后，列表载荷不得再带 bypass / pending_sync / 待同步 提示。"""
    _post_reading(client, auth_headers, "东翼-33", 0.50)

    body = _list_ids(client, auth_headers)
    assert "bypass" not in body
    assert "pending_sync" not in body
    assert "pending_msg" not in body
    for row in body["items"]:
        assert "bypass" not in row
        assert "待同步" not in str(row)


def test_ws_push_id_must_also_be_in_list_payload(client, auth_headers):
    """WebSocket 推送到的编号，必须同样能在随后的列表查询载荷中找到。

    防止“套接字闪过、总表缺行”：推送文案不能作为成功的唯一证据。
    """
    with client.websocket_connect("/ws/alerts") as ws:
        created = _post_reading(client, auth_headers, "回风巷", 1.20)
        pushed = ws.receive_json()

    assert pushed["id"] == created["id"]
    assert pushed["level"] == "报警"

    body = _list_ids(client, auth_headers)
    list_ids = [r["id"] for r in body["items"]]
    assert created["id"] in list_ids
    assert pushed["id"] in list_ids


def test_viewer_can_see_newly_created_row(client, auth_headers):
    """写入后换只读账号查询，新编号同样必须在其列表载荷中。"""
    created = _post_reading(client, auth_headers, "东翼-55", 0.10)

    login = client.post(
        "/api/auth/login",
        json={"username": "viewer", "password": "view123456"},
    )
    viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    body = _list_ids(client, viewer_headers)
    assert created["id"] in [r["id"] for r in body["items"]]


def test_rows_actually_persisted_in_database(client, auth_headers, engine):
    """旁路若在序列化层过滤，数据库仍有行；这里额外确认存储与列表一致。"""
    created = _post_reading(client, auth_headers, "回风巷", 2.10)

    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        assert db.get(Reading, created["id"]) is not None
    finally:
        db.close()

    body = _list_ids(client, auth_headers)
    assert created["id"] in [r["id"] for r in body["items"]]
