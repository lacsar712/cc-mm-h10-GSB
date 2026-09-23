"""上报后总表必须含新行：核对 GET 列表载荷里的编号，而不是只看推送文案。

覆盖回归点：
- 新行藏匿旁路曾过滤掉最大编号，导致上报成功 / 套接字闪过但总表缺行。
- 列表响应不再带 pending_sync / pending_msg / bypass 等待同步提示字段。
- 报警一笔、正常一笔写入后，两笔都要在列表载荷中可见。
"""


def submit(client, headers, site, ch4):
    res = client.post(
        "/api/readings",
        headers=headers,
        json={"site": site, "ch4_pct": ch4},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert isinstance(body["id"], int)
    return body


def list_payload(client, headers):
    res = client.get("/api/readings", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert "items" in data
    # 待同步之类提示已随旁路废除
    assert "pending_sync" not in data
    assert "pending_msg" not in data
    assert "bypass" not in data
    return data["items"]


def test_normal_reading_id_in_list_payload(client, auth_headers):
    created = submit(client, auth_headers, site="东翼-13", ch4=0.32)
    assert created["level"] == "正常"

    items = list_payload(client, auth_headers)
    ids = [r["id"] for r in items]
    # 核心断言：刚写入的编号必须出现在列表载荷中
    assert created["id"] in ids
    row = next(r for r in items if r["id"] == created["id"])
    assert row["site"] == "东翼-13"
    assert row["ch4_pct"] == 0.32
    assert row["level"] == "正常"
    assert "bypass" not in row


def test_alarm_reading_id_in_list_payload(client, auth_headers):
    created = submit(client, auth_headers, site="回风巷-2", ch4=1.40)
    assert created["level"] == "报警"

    items = list_payload(client, auth_headers)
    ids = [r["id"] for r in items]
    assert created["id"] in ids
    row = next(r for r in items if r["id"] == created["id"])
    assert row["level"] == "报警"


def test_newest_max_id_is_listed_first(client, auth_headers):
    # 连续上报：最新（最大编号）一行绝不能被过滤掉，且排在最前
    submit(client, auth_headers, site="测点甲", ch4=0.10)
    newest = submit(client, auth_headers, site="测点乙", ch4=0.20)

    items = list_payload(client, auth_headers)
    assert items, "列表不应为空"
    assert items[0]["id"] == newest["id"]
    assert max(r["id"] for r in items) == newest["id"]


def test_alarm_and_normal_both_visible_in_one_list(client, auth_headers):
    # 报警与正常各写一笔，总表载荷两笔都要看到
    normal = submit(client, auth_headers, site="北巷", ch4=0.40)
    alarm = submit(client, auth_headers, site="南巷", ch4=1.80)
    assert normal["level"] == "正常"
    assert alarm["level"] == "报警"

    items = list_payload(client, auth_headers)
    by_id = {r["id"]: r for r in items}
    assert normal["id"] in by_id
    assert alarm["id"] in by_id
    assert by_id[normal["id"]]["level"] == "正常"
    assert by_id[alarm["id"]]["level"] == "报警"


def test_push_flash_is_not_enough_list_must_contain_pushed_id(client, auth_headers):
    # 套接字推送文案闪过不算数：必须再核对列表载荷含推送的编号
    with client.websocket_connect("/ws/alerts") as ws:
        created = submit(client, auth_headers, site="综采面", ch4=2.10)
        pushed = ws.receive_json()

    # 推送确实到了
    assert pushed["id"] == created["id"]
    assert pushed["level"] == "报警"

    # 关键：推送里的编号必须同样出现在列表载荷中
    items = list_payload(client, auth_headers)
    assert pushed["id"] in [r["id"] for r in items]
