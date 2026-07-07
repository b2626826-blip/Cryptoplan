from config_secrets import load_keys


def test_env_takes_priority(tmp_path, monkeypatch):
    monkeypatch.setenv("BITUNIX_API_KEY", "envkey")
    monkeypatch.setenv("BITUNIX_API_SECRET", "envsecret")
    k, s = load_keys("bitunix", secrets_dir=str(tmp_path))
    assert (k, s) == ("envkey", "envsecret")


def test_file_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("BINGX_API_KEY", raising=False)
    monkeypatch.delenv("BINGX_API_SECRET", raising=False)
    f = tmp_path / "bingx.txt"
    f.write_text("API_KEY : filekey\nSecret Key : filesecret\n", encoding="utf-8")
    k, s = load_keys("bingx", secrets_dir=str(tmp_path))
    assert (k, s) == ("filekey", "filesecret")


def test_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.delenv("OKX_API_KEY", raising=False)
    monkeypatch.delenv("OKX_API_SECRET", raising=False)
    k, s = load_keys("okx", secrets_dir=str(tmp_path))
    assert (k, s) == ("", "")
