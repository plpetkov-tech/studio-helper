from studio_helper.validators import mp4


def test_mp4_is_a_warn_stub(tmp_path):
    fake = tmp_path / "clip.mp4"
    fake.write_bytes(b"not a real mp4")
    checks = mp4.validate(fake, {}, {})
    assert len(checks) == 1
    assert checks[0].status == "warn"
    assert "not available yet" in checks[0].message


def test_mp4_validate_signature_matches_other_validators():
    # every validator module exposes validate(path, fmt, deliverable)
    import inspect

    sig = inspect.signature(mp4.validate)
    assert list(sig.parameters) == ["path", "fmt", "deliverable"]
