from pyramid.security import Authenticated
from pyramid.interfaces import IAuthenticationPolicy

from c2corg_api.models import DBSession
from c2corg_api.models.user import User
from c2corg_api.models.token import Token

import datetime
import logging

log = logging.getLogger(__name__)

# Schedule expired tokens cleanup on application start
next_expire_cleanup = datetime.datetime.utcnow()

# The number of days after which a token is expired
CONST_EXPIRE_AFTER_DAYS = 14

# The number of days after which expired tokens are deleted
CONST_CRON_DAYS = 1


def groupfinder(userid, request):
    is_moderator = DBSession.query(User). \
        filter(User.id == userid and User.moderator is True). \
        count() > 0
    return ['group:moderators'] if is_moderator else [Authenticated]


def validate_token(token):
    now = datetime.datetime.utcnow()
    return DBSession.query(Token). \
        filter(Token.value == token and Token.expire > now).count() == 1


def add_token(value, expire, userid):
    token = Token(value=value, expire=expire, userid=userid)
    DBSession.add(token)
    DBSession.flush()


def clean_expired_tokens():
    global next_expire_cleanup
    now = datetime.datetime.utcnow()
    if now >= next_expire_cleanup:
        next_expire_cleanup = now + datetime.timedelta(days=CONST_CRON_DAYS)
        condition = Token.expire > now
        result = DBSession.execute(Token.__table__.delete().where(condition))
        log.info('Removed %d expired tokens' % result.rowcount)
        DBSession.flush()


def remove_token(token):
    now = datetime.datetime.utcnow()
    condition = Token.value == token and Token.expire > now
    result = DBSession.execute(Token.__table__.delete().where(condition))
    if result.rowcount == 0:
        log.debug('Failed to remove token %s' % token)
    DBSession.flush()
    clean_expired_tokens()


def create_claims(user, exp):
    return {
        'sub': user.id,
        'username': user.username,
        'exp': round((exp - datetime.datetime(1970, 1, 1)).total_seconds())
    }


def try_login(username, password, request):
    user = DBSession.query(User). \
        filter(User.username == username).first()

    clean_expired_tokens()
    if username and password and user.validate_password(password, DBSession):
        policy = request.registry.queryUtility(IAuthenticationPolicy)
        now = datetime.datetime.utcnow()
        exp = now + datetime.timedelta(weeks=CONST_EXPIRE_AFTER_DAYS)
        claims = create_claims(user, exp)
        token = policy.encode_jwt(request, claims=claims)
        add_token(token, exp, user.id)
        return token
