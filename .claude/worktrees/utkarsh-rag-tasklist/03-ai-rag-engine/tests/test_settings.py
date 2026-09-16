from __future__ import annotations

import unittest

from config.settings import Settings


class SettingsTests(unittest.TestCase):
    def test_reads_duckdns_and_vercel_public_origins(self):
        settings = Settings.from_env({
            "APP_ENV": "production",
            "PUBLIC_API_ORIGIN": "https://echoquery-api.duckdns.org",
            "PUBLIC_WS_ORIGIN": "wss://echoquery-api.duckdns.org/ws",
            "SARVAM_API_KEY": "real-key",
            "SARVAM_LLM_MODEL": "real-model",
            "CORS_ALLOWED_ORIGINS": "https://echoquery.vercel.app",
            "WS_ALLOWED_ORIGINS": "https://echoquery.vercel.app",
        })
        settings.validate()
        self.assertEqual(settings.cors_allowed_origins, ("https://echoquery.vercel.app",))
        self.assertEqual(settings.public_ws_origin, "wss://echoquery-api.duckdns.org/ws")

    def test_production_rejects_unresolved_placeholders(self):
        settings = Settings.from_env({
            "APP_ENV": "production",
            "PUBLIC_API_ORIGIN": "https://api.example",
            "PUBLIC_WS_ORIGIN": "wss://api.example/ws",
            "SARVAM_API_KEY": "REPLACE_ME",
            "SARVAM_LLM_MODEL": "VERIFY_MODEL",
        })
        with self.assertRaises(ValueError):
            settings.validate()


if __name__ == "__main__":
    unittest.main()
