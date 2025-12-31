import pytest
from pydantic import ValidationError
from app.settings import Settings

def test_db_url_validation():
    # Valid DB URL
    s = Settings(source_database_url="postgresql://user:pass@localhost/db")
    assert s.source_database_url.startswith("postgresql")

    # Invalid DB URL
    with pytest.raises(ValidationError) as excinfo:
        Settings(source_database_url="mysql://user:pass@localhost/db")
    assert "DB URL은 'postgresql'로 시작해야 합니다." in str(excinfo.value)

def test_url_validation():
    # Valid URL
    s = Settings(ownerclan_api_base_url="https://api.example.com")
    assert s.ownerclan_api_base_url.startswith("http")

    # Invalid URL
    with pytest.raises(ValidationError) as excinfo:
        Settings(ownerclan_api_base_url="ftp://api.example.com")
    assert "URL은 'http://' 또는 'https://'로 시작해야 합니다." in str(excinfo.value)

def test_sleep_validation():
    # Valid sleep
    s = Settings(ownerclan_api_sleep=0.1)
    assert s.ownerclan_api_sleep == 0.1

    # Invalid sleep (negative)
    with pytest.raises(ValidationError) as excinfo:
        Settings(ownerclan_api_sleep=-0.5)
    assert "대기 시간은 0 이상이어야 합니다." in str(excinfo.value)

def test_batch_commit_size_validation():
    # Valid size
    s = Settings(ownerclan_batch_commit_size=100)
    assert s.ownerclan_batch_commit_size == 100

    # Invalid size (too small)
    with pytest.raises(ValidationError) as excinfo:
        Settings(ownerclan_batch_commit_size=10)
    assert "batch_commit_size는 50에서 2000 사이여야 합니다." in str(excinfo.value)

    # Invalid size (too large)
    with pytest.raises(ValidationError) as excinfo:
        Settings(ownerclan_batch_commit_size=2500)
    assert "batch_commit_size는 50에서 2000 사이여야 합니다." in str(excinfo.value)
