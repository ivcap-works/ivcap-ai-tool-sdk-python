from ivcap_ai_tool import SecretMgrClient
import pytest

def test_secret_mgr():
    client = SecretMgrClient()
    try:
        client.get_secret("LITELLM_OPENAI_KEY")
    except Exception as e:
        assert "AUTH0_CLIENT_SECRET" in str(e)
