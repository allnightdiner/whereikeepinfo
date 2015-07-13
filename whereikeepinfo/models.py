from passlib.hash import bcrypt

import sqlalchemy as sa
import sqlalchemy.orm as sa_orm
from sqlalchemy.ext.declarative import declarative_base

from pyramid.security import Allow
from pyramid.security import Authenticated
from pyramid.security import Everyone

Base = declarative_base()


class User(Base):

    __tablename__ = 'users'
    id = sa.Column(sa.INTEGER, primary_key=True)
    created_at = sa.Column(sa.INTEGER, nullable=False)
    username = sa.Column(sa.TEXT, unique=True, nullable=False)
    name = sa.Column(sa.TEXT, nullable=False)
    email = sa.Column(sa.TEXT, unique=True, nullable=False)
    verified = sa.Column(sa.BOOLEAN, nullable=False, default=False)
    verified_at = sa.Column(sa.INTEGER, nullable=True)
    last_probe = sa.Column(sa.INTEGER)

    _password = sa.Column('password', sa.TEXT, nullable=False)

    def _get_password(self):
        return self._password
    def _set_password(self, password):
        self._password = bcrypt.encrypt(password)

    password = property(_get_password, _set_password)
    password = sa_orm.synonym('_password', descriptor=password)

    def __init__(self, username, name, email, password, created_at):
        self.username = username
        self.name = name
        self.email = email
        self.password = password
        self.created_at = created_at


class RootFactory(object):
    __acl__ = [
        (Allow, Everyone, 'view'),
        (Allow, Authenticated, 'post')
    ]

    def __init__(self, request):
        pass  # pragma: no cover
