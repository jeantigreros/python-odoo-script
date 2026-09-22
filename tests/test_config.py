"""Config + health endpoint tests (no Windows required)."""

import config
import main


def test_validate_host_accepts_any_and_0000():
    assert config.validate_host("0.0.0.0") == "0.0.0.0"
    assert config.validate_host("192.168.18.92") == "192.168.18.92"


def test_validate_host_rejects_bad():
    for bad in ["", "999.1.1.1", "hola", "192.168.1"]:
        try:
            config.validate_host(bad)
        except ValueError:
            continue
        raise AssertionError(f"should reject {bad!r}")


def test_save_load_roundtrip(tmp_path):
    ini = tmp_path / "config.ini"
    cfg = config.BridgeConfig(host="192.168.18.92", printer_name="POS-80")
    config.save_config(cfg, str(ini))
    loaded = config.load_config(str(ini))
    assert loaded.host == "192.168.18.92"
    assert loaded.printer_name == "POS-80"


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"
    assert "version" in resp.get_json()


def testUpdater_never_raises_without_velopack(monkeypatch):
    monkeypatch.setattr(main, "velopack", None)
    assert main.check_for_updates_once() is False
