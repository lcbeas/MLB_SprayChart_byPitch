"""
Application configuration settings
"""

import os


class Config:
    """Base configuration."""

    # Flask settings
    DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'
    PORT = int(os.environ.get('PORT', 5000))
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

    # Ottoneu settings
    OTTONEU_LEAGUE_ID = os.environ.get('OTTONEU_LEAGUE_ID', '1395')

    # Data caching
    CACHE_DIR = os.path.join(os.path.dirname(__file__), 'data')
    DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
    CACHE_EXPIRY_HOURS = 24

    # API settings
    FANGRAPHS_BASE_URL = 'https://www.fangraphs.com'
    OTTONEU_BASE_URL = 'https://ottoneu.fangraphs.com'
    SAVANT_BASE_URL = 'https://baseballsavant.mlb.com'


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
