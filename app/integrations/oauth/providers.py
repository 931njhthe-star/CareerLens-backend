"""OAuth adapters using only this project's configured provider credentials."""

from authlib.integrations.flask_client import OAuth

from app.modules.auth.service import AuthError


PROVIDERS = {"google": "Google", "github": "GitHub", "linkedin": "LinkedIn"}


class OAuthProviders:
    def __init__(self, app):
        self.oauth = OAuth(app)
        self.enabled = {}
        for provider in PROVIDERS:
            prefix = provider.upper()
            client_id = app.config.get(f"{prefix}_CLIENT_ID")
            client_secret = app.config.get(f"{prefix}_CLIENT_SECRET")
            self.enabled[provider] = bool(client_id and client_secret)
            if not self.enabled[provider]:
                continue
            settings = {"client_id": client_id, "client_secret": client_secret}
            if provider == "github":
                settings.update(
                    api_base_url="https://api.github.com/",
                    authorize_url="https://github.com/login/oauth/authorize",
                    access_token_url="https://github.com/login/oauth/access_token",
                    client_kwargs={
                        "scope": "read:user user:email",
                        "code_challenge_method": "S256",
                        "timeout": 15,
                    },
                )
            else:
                settings.update(
                    server_metadata_url=(
                        "https://accounts.google.com/.well-known/openid-configuration"
                        if provider == "google"
                        else "https://www.linkedin.com/oauth/.well-known/openid-configuration"
                    ),
                    client_kwargs={"scope": "openid profile email", "timeout": 15},
                )
            self.oauth.register(provider, **settings)

    def list(self):
        return [
            {"id": key, "name": name, "enabled": self.enabled[key]}
            for key, name in PROVIDERS.items()
        ]

    def client(self, provider):
        if provider not in PROVIDERS:
            raise AuthError("지원하지 않는 로그인 방법입니다.", "provider_unknown", 404)
        if not self.enabled[provider]:
            raise AuthError(
                f"{PROVIDERS[provider]} 로그인은 이 프로젝트의 OAuth 앱 키를 설정한 뒤 사용할 수 있습니다.",
                "provider_unavailable",
                503,
            )
        return self.oauth.create_client(provider)

    def identity(self, provider):
        client = self.client(provider)
        token = client.authorize_access_token()
        if provider != "github":
            # Authlib verifies signature, issuer, audience, expiration and nonce.
            # Never trust userinfo supplied without a validated ID token.
            if not token.get("id_token") or not token.get("userinfo"):
                raise AuthError(
                    "소셜 계정의 ID 토큰을 확인하지 못했습니다.", "oauth_identity_invalid"
                )
            identity = dict(token["userinfo"])
            # LinkedIn may omit email claims from its ID token. Fetch only the
            # authenticated subject's userinfo, and bind it to the signed token.
            if not identity.get("email") or "email_verified" not in identity:
                profile = client.userinfo(token=token, timeout=15)
                if not identity.get("sub") or profile.get("sub") != identity["sub"]:
                    raise AuthError("소셜 계정 정보가 일치하지 않습니다.", "oauth_identity_invalid")
                identity.update(
                    {
                        key: profile[key]
                        for key in ("email", "email_verified", "name")
                        if key in profile
                    }
                )
            return identity
        profile_response = client.get("user", token=token, timeout=15)
        profile_response.raise_for_status()
        email_response = client.get("user/emails", token=token, timeout=15)
        email_response.raise_for_status()
        profile, emails = profile_response.json(), email_response.json()
        email = next(
            (item["email"] for item in emails if item.get("primary") and item.get("verified")), None
        )
        if not email:
            raise AuthError(
                "GitHub에서 확인된 기본 이메일을 제공하지 않았습니다.", "oauth_email_unverified"
            )
        if not profile.get("id"):
            raise AuthError("GitHub 계정을 확인할 수 없습니다.", "oauth_identity_invalid")
        return {
            "sub": str(profile["id"]),
            "email": email,
            "email_verified": True,
            "name": profile.get("name") or profile.get("login"),
        }
