from studio_helper import selftest


def test_selftest_passes():
    assert selftest.run() == 0
