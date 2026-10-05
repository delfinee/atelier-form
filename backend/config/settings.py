"""Django settings for the Atelier Form platform.

Everything environment-specific is read through `django-environ` from the
process environment or a local `.env` file. No secret has a usable default:
`DJANGO_SECRET_KEY` falls back to an ephemeral per-process key, which is fine
for development and fails safely in production because sessions will not
survive a restart.
"""

import os
from datetime import timedelta
from pathlib import Path
from typing import cast

import environ
from django.core.management.utils import get_random_secret_key

BASE_DIR = Path(__file__).resolve().parents[2]

env = environ.Env(
    DJANGO_DEBUG=(bool, True),
    DJANGO_ALLOWED_HOSTS=(list, ["*"]),
    CORS_ALLOWED_ORIGINS=(list, []),
    DJANGO_LANGUAGE_CODE=(str, "en-us"),
    ACCESS_TOKEN_LIFETIME_MINUTES=(int, 30),
    REFRESH_TOKEN_LIFETIME_DAYS=(int, 7),
    FREE_SHIPPING_THRESHOLD=(str, "80"),
    SHIPPING_STANDARD=(str, "8"),
    SHIPPING_EXPRESS=(str, "18"),
    LOW_STOCK_THRESHOLD=(int, 5),
    PAYMENT_RESERVATION_MINUTES=(int, 30),
    PAYMENT_BACKEND=(str, "payments.services.MockPaymentProvider"),
    EMAIL_BACKEND_CLASS=(str, "content.services.ConsoleEmailSender"),
    JWT_ALGORITHM=(str, "HS256"),
    CURRENCY=(str, "CNY"),
    ORDER_NUMBER_PREFIX=(str, "AF"),
    LOG_LEVEL=(str, "INFO"),
    DATABASE_URL=(str, "postgres://atelier:atelier@127.0.0.1:5432/atelier_form"),
    DJANGO_CONN_MAX_AGE=(int, 60),
    SECURE_SSL_REDIRECT=(bool, True),
    SECURE_HSTS_SECONDS=(int, 60 * 60 * 24 * 30),
    GEMINI_API_KEY=(str, ""),
    GEMINI_MODEL=(str, "gemini-3.8-flash"),
)

# Read .env if present. Never committed -- see .env.example.
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or get_random_secret_key()
DEBUG = env.bool("DJANGO_DEBUG")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

GEMINI_API_KEY = env.str("GEMINI_API_KEY", default="")
GEMINI_MODEL = env.str("GEMINI_MODEL", default="gemini-3.8-flash")

if not DEBUG and not os.environ.get("DJANGO_SECRET_KEY"):
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured("DJANGO_SECRET_KEY is required when DJANGO_DEBUG=0.")


# -- Applications ---------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",

    # Third party
    "rest_framework",
    "rest_framework_simplejwt",
    "django_filters",
    "drf_spectacular",
    "corsheaders",

    # Charter's modular apps
    "accounts",
    "products",
    "orders",
    "payments",
    "reviews",
    "content",
    "recommendations",
    "messaging",

    # Photography held in PostgreSQL, shared by every surface
    "imagery",

    # Presentation layer (server-rendered buyer frontend)
    "frontend",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "frontend.context_processors.frontend",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# -- Database -------------------------------------------------------------
# PostgreSQL is required because the schema uses PostgreSQL-native types.

DATABASES = {
    "default": env.db("DATABASE_URL")
}
# Disable persistent connections on serverless deployments.
DATABASES["default"].setdefault("CONN_MAX_AGE", env.int("DJANGO_CONN_MAX_AGE"))

# -- Authentication -------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"

# Prefer Argon2 while keeping older hashers available for migration.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "account_overview"
LOGOUT_REDIRECT_URL = "home"


# -- REST framework -------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        # Use sessions for the frontend and JWT for API clients.
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.AllowAny",),
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_PAGINATION_CLASS": "config.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "config.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "auth": "20/min",
        "contact": "10/hour",
        "newsletter": "10/hour",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=cast(int, env.int("ACCESS_TOKEN_LIFETIME_MINUTES"))
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=cast(int, env.int("REFRESH_TOKEN_LIFETIME_DAYS"))
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "UPDATE_LAST_LOGIN": True,
    "SIGNING_KEY": os.environ.get("JWT_SECRET") or SECRET_KEY,
    "ALGORITHM": env.str("JWT_ALGORITHM"),
    "USER_ID_FIELD": "uuid",
    "USER_ID_CLAIM": "user_uuid",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Atelier Form API",
    "DESCRIPTION": "Backend for the Atelier Form handmade-goods marketplace (NTU DIP E006).",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api",
}


# -- CORS -----------------------------------------------------------------
# Allow credentials only for explicitly configured client origins.

CORS_ALLOWED_ORIGINS = cast(list[str], env.list("CORS_ALLOWED_ORIGINS"))
CORS_ALLOW_CREDENTIALS = True


# -- Internationalisation -------------------------------------------------
# Enable incremental Simplified Chinese translation support.

LANGUAGE_CODE = env.str("DJANGO_LANGUAGE_CODE")
LANGUAGES = [("en", "English"), ("zh-hans", "简体中文")]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# -- Static files ---------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# -- Storefront / commerce configuration ---------------------------------
# Convert money strings to Decimal without using floats.

CURRENCY = env.str("CURRENCY")

# Read the currency symbol directly to avoid django-environ's dollar expansion.
CURRENCY_SYMBOLS = {"SGD": "$", "USD": "$", "CNY": "¥", "RMB": "¥", "EUR": "€"}
CURRENCY_SYMBOL = os.environ.get("CURRENCY_SYMBOL") or CURRENCY_SYMBOLS.get(str(CURRENCY), "$")

COMMERCE = {
    "CURRENCY": CURRENCY,
    "CURRENCY_SYMBOL": CURRENCY_SYMBOL,
    "FREE_SHIPPING_THRESHOLD": env("FREE_SHIPPING_THRESHOLD"),
    "SHIPPING_STANDARD": env("SHIPPING_STANDARD"),
    "SHIPPING_EXPRESS": env("SHIPPING_EXPRESS"),
    "LOW_STOCK_THRESHOLD": env("LOW_STOCK_THRESHOLD"),
    "ORDER_NUMBER_PREFIX": env.str("ORDER_NUMBER_PREFIX"),
}

PAYMENT_BACKEND = env("PAYMENT_BACKEND")
PAYMENT_RESERVATION_MINUTES = env("PAYMENT_RESERVATION_MINUTES")
EMAIL_SENDER_CLASS = env("EMAIL_BACKEND_CLASS")


# -- Django password-reset email -----------------------------------------
# Separate from the existing notification sender above. Console delivery is
# for local development only; deployed environments must configure SMTP.
EMAIL_BACKEND = env.str("EMAIL_BACKEND", default=(
    "django.core.mail.backends.console.EmailBackend" if DEBUG
    else "django.core.mail.backends.smtp.EmailBackend"
))
DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL", default="Atelier Form <noreply@atelierform.test>")
EMAIL_HOST = env.str("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=25)
EMAIL_HOST_USER = env.str("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env.str("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=10)
PASSWORD_RESET_TIMEOUT = env.int("PASSWORD_RESET_TIMEOUT", default=259200)


# -- Security -------------------------------------------------------------
# Apply secure cookie and transport settings when DEBUG is disabled.

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"

# Trust the deployment origin for form POSTs behind a TLS proxy.
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS") if os.environ.get(
    "CSRF_TRUSTED_ORIGINS"
) else [origin for origin in CORS_ALLOWED_ORIGINS if origin.startswith("http")]

if not DEBUG:
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS")
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


# -- Logging --------------------------------------------------------------
# Keep credentials out of logs and expose only server-error references.

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "{levelname} {name}: {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": env.str("LOG_LEVEL")},
}
