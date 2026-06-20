import unittest
import typing
from uuid import uuid4

from flask import Flask
from flask.testing import FlaskClient


class TestBase(unittest.TestCase):
    app: typing.ClassVar[Flask]
    client: FlaskClient

    @classmethod
    def setUpClass(cls) -> None:
        from WebHostLib import app as raw_app
        from WebHost import get_app

        raw_app.config["PONY"] = {
            "provider": "sqlite",
            "filename": ":memory:",
            "create_db": True,
        }
        raw_app.config.update({
            "TESTING": True,
            "DEBUG": True,
        })
        try:
            cls.app = get_app()
        except (AssertionError, ValueError) as e:
            # We only have 1 global app object, so the 2nd+ test class to build it fails when
            # register() re-runs one-time app setup. All tests use the same config, so fall back to
            # the already-built app. Two shapes depending on whether the app has served a request:
            #   - AssertionError "...setup method 'register_blueprint' can no longer be called..."
            #   - ValueError     "The name 'api' is already registered for this blueprint..."
            msg = str(e.args[0])
            if "register_blueprint" not in msg and "already registered" not in msg:
                raise
            cls.app = raw_app

    def setUp(self) -> None:
        from WebHostLib.models import db
        from pony.orm import db_session
        with db_session:
            for entity in db.entities.values():
                entity.select().delete(bulk=True)
        self.client = self.app.test_client()
