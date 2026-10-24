"""Mode app Home Assistant : lecture des options et filtrage Ingress."""

import importlib
import json

from fastapi.testclient import TestClient

from app import config


def _recharger_config(monkeypatch, tmp_path, options=None, env=None):
    """Recharge le module config avec un options.json et un environnement
    contrôlés ; restauré en fin de test par un rechargement propre."""
    chemin = tmp_path / "options.json"
    if options is not None:
        chemin.write_text(json.dumps(options), encoding="utf-8")
    monkeypatch.setenv("LG_OPTIONS_HA", str(chemin))
    for variable, valeur in (env or {}).items():
        monkeypatch.setenv(variable, valeur)
    return importlib.reload(config)


def _restaurer_config():
    importlib.reload(config)


def test_options_ha_fournissent_hote_tv_et_acces_lan(monkeypatch, tmp_path):
    try:
        conf = _recharger_config(
            monkeypatch, tmp_path,
            options={"lg_tv_host": "10.0.0.9", "acces_lan": True})
        assert conf.MODE_APP_HA is True
        assert conf.TV_HOST == "10.0.0.9"
        assert conf.ACCES_LAN is True
    finally:
        _restaurer_config()


def test_variable_environnement_prime_sur_options_ha(monkeypatch, tmp_path):
    try:
        conf = _recharger_config(
            monkeypatch, tmp_path,
            options={"lg_tv_host": "10.0.0.9"},
            env={"LG_TV_HOST": "10.0.0.42"})
        assert conf.TV_HOST == "10.0.0.42"
    finally:
        _restaurer_config()


def test_sans_options_ha_mode_dev_et_defaut(monkeypatch, tmp_path):
    try:
        monkeypatch.delenv("LG_TV_HOST", raising=False)
        conf = _recharger_config(monkeypatch, tmp_path, options=None)
        assert conf.MODE_APP_HA is False
        assert conf.TV_HOST == ""
        assert conf.ACCES_LAN is False
    finally:
        _restaurer_config()


def test_hors_mode_app_aucun_filtrage(application):
    # MODE_APP_HA est faux par défaut dans les tests : tout client passe.
    with TestClient(application) as client:
        assert client.get("/api/health").status_code == 200


def test_mode_app_refuse_les_clients_hors_ingress(application, monkeypatch):
    monkeypatch.setattr(config, "MODE_APP_HA", True)
    monkeypatch.setattr(config, "ACCES_LAN", False)
    with TestClient(application) as client:
        reponse = client.get("/api/health")
    assert reponse.status_code == 403
    assert "Ingress" in reponse.json()["detail"]


def test_mode_app_accepte_le_proxy_ingress(application, monkeypatch):
    monkeypatch.setattr(config, "MODE_APP_HA", True)
    monkeypatch.setattr(config, "ACCES_LAN", False)
    # Le TestClient se présente avec l'hôte « testclient » : on fait de cette
    # adresse l'IP du proxy pour vérifier la branche « autorisé ».
    monkeypatch.setattr(config, "INGRESS_PROXY_IP", "testclient")
    with TestClient(application) as client:
        assert client.get("/api/health").status_code == 200


def test_mode_app_avec_acces_lan_accepte_tout_le_monde(application, monkeypatch):
    monkeypatch.setattr(config, "MODE_APP_HA", True)
    monkeypatch.setattr(config, "ACCES_LAN", True)
    with TestClient(application) as client:
        assert client.get("/api/health").status_code == 200


def test_mode_app_refuse_aussi_le_websocket(application, monkeypatch):
    monkeypatch.setattr(config, "MODE_APP_HA", True)
    monkeypatch.setattr(config, "ACCES_LAN", False)
    with TestClient(application) as client:
        try:
            with client.websocket_connect("/api/ws"):
                connecte = True
        except Exception:
            connecte = False
    assert connecte is False
