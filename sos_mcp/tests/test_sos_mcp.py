"""Testes sem rede: a API do SOS é simulada."""

import asyncio
import io
import json
import urllib.error

import pytest

from sos_mcp import client as C
from sos_mcp import server as S


class FakeAPI:
    def __init__(self, pages=None, fail_401_once=False):
        self.calls = []
        self.pages = pages or {}
        self.fail_401_once = fail_401_once

    def __call__(self, req, timeout=None):
        self.calls.append((req.get_method(), req.full_url, req.headers.get("Authorization")))
        assert req.get_method() == "GET", "o servidor não pode escrever no SOS"
        if self.fail_401_once:
            self.fail_401_once = False
            raise urllib.error.HTTPError(req.full_url, 401, "x", {}, io.BytesIO(b"expired"))
        from urllib.parse import urlparse, parse_qs
        u = urlparse(req.full_url)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        ent = u.path.split("/api/v2/")[1]
        rows = self.pages.get(ent, [])
        if "/" in ent:
            return io.BytesIO(json.dumps({"data": {"id": int(ent.split("/")[1]), "x": None, "name": "A"}}).encode())
        s, m = int(q.get("start", 0)), int(q.get("maxresults", 200))
        # simula a sobreposição de 1 linha entre páginas que a API às vezes faz
        chunk = rows[max(0, s - 1) if s else 0: s + m - (1 if s else 0)] if s else rows[s:s + m]
        return io.BytesIO(json.dumps({"data": chunk, "totalCount": len(rows)}).encode())


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("SOS_TOKEN_FILE", str(tmp_path / "tok.json"))
    monkeypatch.setenv("SOS_ACCESS_TOKEN", "AT")
    monkeypatch.delenv("SOS_REFRESH_TOKEN", raising=False)
    monkeypatch.setattr(C.time, "sleep", lambda s: None)


def use(fake):
    S._client = C.SOSClient(opener=fake)
    return fake


def call(tool, **kw):
    return asyncio.run(getattr(S, tool)(**kw))


def test_pagination_dedup_all_pages():
    rows = [{"id": i, "number": str(i), "blank": ""} for i in range(450)]
    fake = use(FakeAPI({"invoice": rows}))
    r = call("sos_list", entity="invoice", all_pages=True)
    assert r["count"] == 450 and r["totalCount"] == 450
    assert len({x["id"] for x in r["records"]}) == 450
    assert "blank" not in r["records"][0]  # compactado
    assert all(m == "GET" for m, *_ in fake.calls)


def test_filters_and_dates_passed():
    fake = use(FakeAPI({"salesorder": [{"id": 1}]}))
    call("sos_list", entity="salesorder", status="open", date_from="2026-11-01", date_to="2026-11-30",
         extra_filters={"orderStage": "Ready"}, fields=["number"])
    url = fake.calls[0][1]
    assert "status=open" in url and "from=2026-11-01T00%3A00%3A00" in url
    assert "to=2026-11-30T23%3A59%3A59" in url and "orderStage=Ready" in url
    assert "maxresults=25" in url


def test_refresh_on_401_saves_token(monkeypatch, tmp_path):
    monkeypatch.setenv("SOS_REFRESH_TOKEN", "RT")
    monkeypatch.setattr(C, "refresh", lambda rt: {"access_token": "AT2", "refresh_token": "RT2", "expires_in": 100})
    fake = use(FakeAPI({"location": [{"id": 1, "name": "VitaForte"}]}, fail_401_once=True))
    r = call("sos_list", entity="location")
    assert r["records"][0]["name"] == "VitaForte"
    assert fake.calls[-1][2] == "Bearer AT2"
    saved = json.loads((tmp_path / "tok.json").read_text())
    assert saved["refresh_token"] == "RT2"
    assert oct((tmp_path / "tok.json").stat().st_mode)[-3:] == "600"


def test_not_authorized_message(monkeypatch):
    monkeypatch.delenv("SOS_ACCESS_TOKEN")
    S._client = C.SOSClient(opener=FakeAPI())
    r = call("sos_get", entity="item", id=5)
    assert "erro" in r and "sos_mcp auth" in r["erro"]


def test_get_compacts():
    use(FakeAPI())
    assert call("sos_get", entity="item", id=7) == {"id": 7, "name": "A"}


def test_production_runs_summary():
    proc = [{
        "id": 1, "number": "PRT1166", "date": "2026-11-05T00:00:00", "location": {"name": "VitaForte"},
        "customFields": [{"name": "Tank", "value": "#03"}, {"name": "Labor", "value": "2"}],
        "inputs": [{"item": {"name": "R9601-080-VFI"}, "quantity": 400, "lot": {"name": "OFAIVF258"}}],
        "outputs": [{"item": {"name": "9601-0B0-VFI"}, "quantity": 100, "waste": False},
                    {"item": {"name": "Evap"}, "quantity": 300, "waste": True}],
    }, {"id": 2, "number": "PRT9", "date": "2026-11-06", "inputs": [{"item": {"name": "X"}, "quantity": 1}], "outputs": []}]
    use(FakeAPI({"process": proc}))
    r = call("sos_production_runs", date_from="2026-11-01", item_contains="9601")
    assert len(r["runs"]) == 1
    run = r["runs"][0]
    assert run["tank"] == "#03" and run["rendimento_kg"] == 0.25 and run["entradas"][0]["lote"] == "OFAIVF258"


def test_key_middleware():
    from sos_mcp.http_app import KeyMiddleware

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})

    async def go(headers, qs=b""):
        sent = []
        async def send(m): sent.append(m)
        await KeyMiddleware(app, "k1")({"type": "http", "headers": headers, "query_string": qs}, None, send)
        return sent[0]["status"]

    assert asyncio.run(go([])) == 401
    assert asyncio.run(go([(b"authorization", b"Bearer k1")])) == 200
    assert asyncio.run(go([], b"key=k1")) == 200
    assert asyncio.run(go([(b"authorization", b"Bearer no")])) == 401


def test_read_tools_marked_read_only():
    tools = {t.name: t for t in asyncio.run(S.mcp.list_tools())}
    writes = {"sos_update_record", "sos_create_record", "sos_delete_item"}
    assert writes <= set(tools)
    assert all(t.annotations.read_only_hint for n, t in tools.items() if n not in writes)
    assert not any(tools[n].annotations.read_only_hint for n in writes)
