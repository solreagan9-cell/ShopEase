"""
Django settings for config project.
"""
from pathlib import Path
import dj_database_url
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------
# Security
# ---------------------------------------------------------------
SECRET_KEY = config("SECRET_KEY", default="dev-only-insecure-key-change-me")
DEBUG = config("DEBUG", default=False, cast=bool)

ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="shopease-pb01.onrender.com,localhost,127.0.0.1",
    cast=Csv(),
)

CSRF_TRUSTED_ORIGINS = [
    "https://shopease-pb01.onrender.com",
    "https://shopease-1-wtdp.onrender.com",
]

# Render serves your app behind a proxy that terminates HTTPS
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ---------------------------------------------------------------
# Applications
# ---------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "pharmacy",
]

MIDDLEWARE = [
    "pharmacy.cors.SimpleCorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Addresses the separate frontend is allowed to run from (CORS).
# Both names are defined in case pharmacy/cors.py reads either one.
CORS_ALLOWED_ORIGINS = [
    "https://shopease-1-wtdp.onrender.com",
    "http://127.0.0.1:5500",
    "http://localhost:5500",
]
FRONTEND_ORIGINS = CORS_ALLOWED_ORIGINS

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
                "pharmacy.context_processors.sidebar_analytics",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------
# Database
# On Render: reads DATABASE_URL (set it in the Environment tab).
# On your computer: falls back to your local PostgreSQL.
# ---------------------------------------------------------------
DATABASES = {
    "default": dj_database_url.config(
        default="postgres://postgres:12345678@localhost:5432/pharmacy_db",
        conn_max_age=600,
    )
}

# ---------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------
# Static and media files
# ---------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
_static_dir = BASE_DIR / "static"
STATICFILES_DIRS = [_static_dir] if _static_dir.exists() else []

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---------------------------------------------------------------
# Auth redirects
# ---------------------------------------------------------------
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "pharmacy:dashboard"
LOGOUT_REDIRECT_URL = "login"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------
# Email
# ---------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"