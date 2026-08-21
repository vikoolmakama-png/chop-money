import os

class Config:
    SECRET_KEY = os.environ.get(
        "SECRET_KEY",
        "chop-money-change-this-secret"
    )

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "sqlite:///chop_money.db"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False
