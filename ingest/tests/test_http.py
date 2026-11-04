import logging

import httpx
import pytest

from sintesis_ingest.http import FetchError, HttpClient

BASE = "https://api.example.test/Service.ashx"
SECRET = "s3cr3t-pass"  # noqa: S105  # pragma: allowlist secret (valor falso de prueba)
USER = "persona@example.com"


class FakeServer:
    """Simula al servidor: responde en orden la lista de respuestas y anota cada solicitud."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture
def sleeps():
    return []


def make_client(server, sleeps, **kw):
    return HttpClient(
        "contacto@example.com",
        pause_seconds=2.0,
        transport=httpx.MockTransport(server),
        sleep=sleeps.append,
        **kw,
    )


def get_with_secrets(client):
    return client.get(BASE, params={"function": "GetSeries"}, secret_params={"user": USER, "pass": SECRET})


def test_user_agent_is_honest_with_contact(sleeps):
    server = FakeServer(httpx.Response(200, json={}))
    make_client(server, sleeps).get(BASE)
    ua = server.requests[0].headers["user-agent"]
    assert ua.startswith("sintesis-economica-v2/")
    assert "contacto@example.com" in ua


def test_at_sign_reaches_server_unencoded(sleeps):
    server = FakeServer(httpx.Response(200))
    get_with_secrets(make_client(server, sleeps))
    query = server.requests[0].url.raw_path.decode()
    assert f"user={USER}" in query  # '@' literal, no '%40'


def test_credentials_travel_but_never_appear_in_returned_url(sleeps):
    server = FakeServer(httpx.Response(200, content=b"{}", headers={"content-type": "application/json"}))
    resp = get_with_secrets(make_client(server, sleeps))
    assert SECRET in server.requests[0].url.raw_path.decode()  # el servidor sí la recibe
    assert SECRET not in resp.url and USER not in resp.url
    assert resp.url == f"{BASE}?function=GetSeries"
    assert (resp.content, resp.content_type) == (b"{}", "application/json")


def test_credentials_never_appear_in_logs(sleeps, caplog):
    server = FakeServer(httpx.Response(503), httpx.Response(200))
    with caplog.at_level(logging.DEBUG):
        get_with_secrets(make_client(server, sleeps))
    everything = " ".join(str(vars(r)) for r in caplog.records)
    assert "reintento" in everything
    assert SECRET not in everything and USER not in everything


def test_error_after_retries_hides_credentials_and_original_exception(sleeps):
    server = FakeServer(httpx.Response(503), httpx.Response(503), httpx.Response(503))
    with pytest.raises(FetchError) as exc:
        get_with_secrets(make_client(server, sleeps))
    assert SECRET not in str(exc.value) and USER not in str(exc.value)
    assert "3 intentos" in str(exc.value)
    # `from None`: el traceback no arrastra la excepción original (que traería la URL completa)
    assert exc.value.__cause__ is None and exc.value.__suppress_context__


def test_server_error_is_retried_then_succeeds(sleeps):
    server = FakeServer(httpx.Response(503), httpx.Response(200, content=b"ok"))
    resp = make_client(server, sleeps).get(BASE)
    assert resp.content == b"ok"
    assert len(server.requests) == 2


def test_network_error_is_retried(sleeps):
    server = FakeServer(httpx.ConnectError("sin red"), httpx.Response(200))
    make_client(server, sleeps).get(BASE)
    assert len(server.requests) == 2


def test_rate_limit_429_is_retried(sleeps):
    server = FakeServer(httpx.Response(429), httpx.Response(200))
    make_client(server, sleeps).get(BASE)
    assert len(server.requests) == 2


def test_not_found_is_not_retried(sleeps):
    server = FakeServer(httpx.Response(404))
    with pytest.raises(FetchError, match="HTTP 404"):
        make_client(server, sleeps).get(BASE)
    assert len(server.requests) == 1


def test_retry_waits_grow(sleeps):
    server = FakeServer(httpx.Response(503), httpx.Response(503), httpx.Response(200))
    make_client(server, sleeps, backoff_seconds=2.0).get(BASE)
    # pausa de cortesía (2 s) antes de cada reintento + espera creciente (2 s, 4 s)
    assert sleeps == [2.0, 2.0, 4.0, 2.0]


def test_pause_between_requests_but_not_before_first(sleeps):
    server = FakeServer(httpx.Response(200), httpx.Response(200))
    client = make_client(server, sleeps)
    client.get(BASE)
    assert sleeps == []
    client.get(BASE)
    assert sleeps == [2.0]
