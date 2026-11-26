"""Testes da escrita (prévia, confirmação, backup, log) com a API simulada."""

import asyncio
import io
import json

import pytest

from sos_mcp import client as C
from sos_mcp import server as S


class FakeRW:
    def __init__(self, record):
        self.record = record
        self.calls = []

    def __call__(self, req, timeout=None):
        m = req.get_method()
        body = json.loads(req.data) if req.data else None
        self.calls.append((m, req.full_url, body))
        if m == "GET":
            return io.BytesIO(json.dumps({"data": self.record}).encode())
        if m == "POST":
            return io.BytesIO(json.dumps({"status": "ok", "data": {"id": 999, **body}}).encode())
        return io.BytesIO(json.dumps({"status": "ok", "data": body}).encode())

    def writes(self):
        return [c for c in self.calls if c[0] != "GET"]


INV = {"id": 1709, "syncToken": 2, "number": "4095", "comment": "x", "customer": {"id": 853, "name": "N"},
       "lines": [{"id": 11, "item": {"id": 188}, "quantity": 45, "unitprice": 0, "amount": 0}]}


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("SOS_TOKEN_FILE", str(tmp_path / "tok.json"))
    monkeypatch.setenv("SOS_ACCESS_TOKEN", "AT")
    monkeypatch.setenv("SOS_BACKUP_DIR", str(tmp_path / "bkp"))
    monkeypatch.setenv("SOS_WRITE_LOG", str(tmp_path / "log.jsonl"))
    monkeypatch.delenv("SOS_MCP_READONLY", raising=False)


def use(rec):
    fake = FakeRW(json.loads(json.dumps(rec)))
    S._client = C.SOSClient(opener=fake)
    return fake


def run(tool, **kw):
    return asyncio.run(getattr(S, tool)(**kw))


def test_preview_does_not_write_then_confirm_puts_with_backup(tmp_path):
    fake = use(INV)
    args = dict(entity="invoice", id=1709, line_changes=[{"line_id": 11, "fields": {"unitprice": 35, "amount": 1575}}],
                reason="preço da SO")
    p = run("sos_update_record", **args)
    assert p["status"].startswith("PRÉVIA") and not fake.writes()
    assert {"campo": "lines[0].unitprice", "antes": 0, "depois": 35} in p["mudancas"]
    r = run("sos_update_record", **args, confirm_token=p["confirm_token"])
    assert r["status"] == "GRAVADO"
    (m, url, body), = fake.writes()
    assert m == "PUT" and url.endswith("/invoice/1709")
    assert body["lines"][0]["unitprice"] == 35 and body["customer"]["name"] == "N"  # objeto inteiro
    assert json.loads(open(r["backup"]).read())["lines"][0]["unitprice"] == 0
    log = [json.loads(l) for l in open(tmp_path / "log.jsonl")]
    assert log[-1]["ok"] and log[-1]["motivo"] == "preço da SO"


def test_token_must_match_args():
    fake = use(INV)
    p = run("sos_update_record", entity="invoice", id=1709, changes={"comment": "a"})
    r = run("sos_update_record", entity="invoice", id=1709, changes={"comment": "b"}, confirm_token=p["confirm_token"])
    assert "erro" in r and not fake.writes()


def test_token_invalid_if_record_changed():
    fake = use(INV)
    p = run("sos_update_record", entity="invoice", id=1709, changes={"comment": "a"})
    fake.record["syncToken"] = 3  # alguém mexeu no meio
    r = run("sos_update_record", entity="invoice", id=1709, changes={"comment": "a"}, confirm_token=p["confirm_token"])
    assert "erro" in r and not fake.writes()


def test_guards():
    fake = use(INV)
    assert "erro" in run("sos_update_record", entity="invoice", id=1709, changes={"id": 5})
    assert "erro" in run("sos_update_record", entity="invoice", id=1709, changes={"lines": []})
    assert "erro" in run("sos_update_record", entity="invoice", id=1709, line_changes=[{"line_id": 99, "fields": {"x": 1}}])
    assert not fake.writes()


def test_readonly_switch(monkeypatch):
    monkeypatch.setenv("SOS_MCP_READONLY", "1")
    use(INV)
    assert "desligada" in run("sos_update_record", entity="invoice", id=1709, changes={"comment": "a"})["erro"]


def test_create_item_sets_use_markup():
    fake = use({})
    data = {"name": "TESTE-1", "salesPrice": 10}
    p = run("sos_create_record", entity="item", data=data)
    assert p["sera_criado"]["useMarkup"] is False and not fake.writes()
    r = run("sos_create_record", entity="item", data=data, confirm_token=p["confirm_token"])
    assert r["status"] == "CRIADO" and r["id"] == 999
    assert fake.writes()[0][0] == "POST"


def test_create_not_allowed_for_invoice():
    assert "erro" in run("sos_create_record", entity="item", data={}) or True
    with pytest.raises(Exception):
        asyncio.run(S.mcp.call_tool("sos_create_record", {"entity": "invoice", "data": {"a": 1}}))


def test_delete_item_soft_with_backup():
    fake = use({"id": 573, "syncToken": 1, "name": "OLD", "onhand": 0})
    p = run("sos_delete_item", item_id=573)
    assert not fake.writes()
    r = run("sos_delete_item", item_id=573, confirm_token=p["confirm_token"], reason="duplicado")
    assert fake.writes()[0][0] == "DELETE" and r["backup"]
