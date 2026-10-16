import sys


def test_python_version_matches_lambda_runtime():
    # Lambda 使用 python3.12 runtime，本機版本太舊會出現兩邊行為不一致
    assert sys.version_info >= (3, 12)
