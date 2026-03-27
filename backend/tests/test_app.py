def test_healthcheck(client) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_hello_requires_authentication(client) -> None:
    response = client.get("/api/hello")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_root_serves_html(client) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert '<div id="root"></div>' in response.text


def test_login_logout_flow(client) -> None:
    login_response = client.post(
        "/api/auth/login",
        json={"username": "user", "password": "password"},
    )
    assert login_response.status_code == 200
    assert login_response.json()["user"]["username"] == "user"

    session_response = client.get("/api/auth/session")
    assert session_response.status_code == 200
    assert session_response.json()["authenticated"] is True

    hello_response = client.get("/api/hello")
    assert hello_response.status_code == 200
    assert hello_response.json()["username"] == "user"

    logout_response = client.post("/api/auth/logout")
    assert logout_response.status_code == 200
    assert logout_response.json() == {"ok": True}

    session_after_logout = client.get("/api/auth/session")
    assert session_after_logout.status_code == 401


def test_login_rejects_invalid_credentials(client) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "user", "password": "wrong"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"
