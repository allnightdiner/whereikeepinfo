from pyramid.httpexceptions import HTTPFound
from pyramid.security import authenticated_userid

from whereikeepinfo.models import User
import utils


class BaseView(object):
    def __init__(self, request):
        self.request = request
        self.username = authenticated_userid(request)
        self.__dict__.update(request.matchdict)
        self.__dict__.update(request.registry.settings)

    def require_login(self, errmsg=u'you must be logged in to do that', came_from='home'):
        if self.username is None:
            self.request.session.flash(errmsg)
            raise HTTPFound(location=self.request.route_url('login', came_from=came_from))

    def require_verification(self, errmsg=u'Account must be verified to do that'):
        self.require_login()
        with utils.db_session(self.dbmaker) as session:
            user = session.query(User).filter(User.username==self.username).first()
            if user.verified_at is None:
                self.request.session.flash(errmsg)
                raise HTTPFound(location=self.request.route_url('user', userid=self.username))

    def require_key(self, errmsg=u'you must first create a key to do that'):
        self.require_verification()
        with utils.db_session(self.dbmaker) as session:
            user = session.query(User).filter(User.username==self.username).first()
            if not user.keys:
                self.request.session.flash(errmsg)
                raise HTTPFound(location=self.request.route_url('keys'))


class LoggedInView(BaseView):
    def __init__(self, request):
        super(LoggedInView, self).__init__(request)
        self.require_login()
