import os
import tempfile
import time
import mimetypes
import logging

from pyramid.response import FileResponse
from pyramid_simpleform.renderers import FormRenderer
from pyramid_simpleform import Form
from pyramid.httpexceptions import HTTPFound
from pyramid.httpexceptions import HTTPNotFound
from pyramid.view import view_config
from pyramid.view import view_defaults

import utils
from whereikeepinfo import forms
from whereikeepinfo.models import File
from whereikeepinfo.models import User
from whereikeepinfo.views.base import BaseView
from whereikeepinfo.views import utils


logger = logging.getLogger(__name__)


@view_defaults(route_name='view_files', renderer='whereikeepinfo:templates/files.pt')
class FilesView(BaseView):

    @view_config(request_method='POST')
    def upload_file(self):
        if self.username is None:
            self.request.session.flash(u'You must be logged in to keep files.')
            return HTTPFound(location=self.request.route_url('login', came_from='view_files'))

        form = Form(self.request, schema=forms.UploadFileSchema)

        with utils.db_session(self.dbmaker) as session:
            user = session.query(User).filter(User.username==self.username).first()
            if user.verified_at is None:
                self.request.session.flash(u'Account must be verified to keep files.')
                return HTTPFound(location=self.request.route_url('user', userid=self.username))

            if 'uploaded_file' in self.request.POST and form.validate():
                f = form.data['uploaded_file']
                name = f['filename']
                size = f['size']
                self.request.session.flash(u'successfully uploaded file %s.' % (name, ))
                encrypted = utils.encrypt(f['file'], user.public_key)
                name = utils.store_file(encrypted, name, user.username, self.storage_dir)
                fileobj = File(name, size, user.id)
                user.files.append(fileobj)
                session.add(user)

        return HTTPFound(location=self.request.route_url('view_files'))

    @view_config(request_method='GET')
    def view_files(self):
        if self.username is None:
            self.request.session.flash(u'You must be logged in to keep files.')
            return HTTPFound(location=self.request.route_url('login', 'view_files'))

        form = Form(self.request, schema=forms.UploadFileSchema)

        with utils.db_session(self.dbmaker) as session:
            user = session.query(User).filter(User.username==self.username).first()
            if user.verified_at is None:
                self.request.session.flash(u'Account must be verified to keep files.')
                return HTTPFound(location=self.request.route_url('user', userid=self.username))
            current_upload_size = sum([f.size for f in user.files])
            username = user.username
            owned_files = dict()
            for f in user.files:
                owned_files[f.name] = [u.username for u in f.shared_users]
            sharable_users = session.query(User).filter(User.sharable==True)
            sharable_users = sharable_users.filter(User.username!=self.username).all()
            sharable_users = [u.username for u in sharable_users]
            shared_files = [f.name for f in user.shared_files]

        return dict(
            current_upload_size=current_upload_size,
            form=FormRenderer(form),
            username=username,
            uploaded_files=owned_files,
            sharable_users=sharable_users,
            shared_files=shared_files
        )


    @view_config(route_name='view_file', renderer='whereikeepinfo:templates/view_file.pt')
    def view_file(self):
        form = Form(self.request, schema=forms.PassphraseSchema)
        if 'form.submitted' in self.request.POST and form.validate():
            with utils.db_session(self.dbmaker) as session:
                user = session.query(User).filter(User.username==self.username).first()
                priv = user.private_key
                pub = user.public_key
                f = session.query(File).filter(File.name==self.filename).first()
                owner = session.query(User).filter(User.id==f.user_id).first().username
                if f not in user.shared_files and owner != user.username:
                    self.request.session.flash(u'File not shared with you. are you a bad actor?')
                    return HTTPFound(location=self.request.route_url('home'))
            query_file = os.path.join(self.storage_dir, owner, self.filename)
            if not os.path.isfile(query_file):
                return HTTPNotFound("file %s is not a thinger" % (self.filename, ))
            content_type, encoding = mimetypes.guess_type(query_file)
            with open(query_file, 'rb') as o:
                encrypted = o.read()
                decrypted = utils.decrypt(encrypted, priv, pub, form.data['password']) 
            with utils.tmpdir() as tmpd:
                tmp = os.path.join(tmpd, self.filename)
                with open(tmp, 'wb') as tmpf:
                    tmpf.write(decrypted)
                    tmpf.flush()
                    response = FileResponse(
                        tmp,
                        request=self.request,
                        content_type=content_type,
                        content_encoding=encoding
                    )
                    return response
        return dict(
            form=FormRenderer(form),
            username=self.username,
            filename=self.filename
        )

    @view_config(route_name='delete_file')
    def delete_file(self):
        if self.username is None:
            self.request.session.flash(u'You must be logged in to delete files.')
            return HTTPFound(location=self.request.route_url('login', came_from='view_files'))
        query_file = os.path.join(self.storage_dir, self.username, self.filename)
        with utils.db_session(self.dbmaker) as session:
            f = session.query(File).filter(File.name==self.filename).first()
            session.delete(f)
        os.remove(query_file)
        self.request.session.flash(u'successfully deleted file: %s.' % (self.filename, ))
        return HTTPFound(location=self.request.route_url('view_files'))

    @view_config(route_name='share_file', renderer='whereikeepinfo:templates/share_file.pt')
    def share_file(self):
        form = Form(self.request, schema=forms.PassphraseSchema)
        if 'form.submitted' in self.request.POST and form.validate():
            passwd = form.data['password']
            query_file = os.path.join(self.storage_dir, self.username, self.filename)
            share_user = self.request.params['share_user']
            with utils.db_session(self.dbmaker) as session:
                owner = session.query(User).filter(User.username==self.username).one()
                f = session.query(File).filter(File.name==self.filename).one()
                u = session.query(User).filter(User.username==share_user).one()
                f.shared_users.append(u)
                session.add(f)
                recipients = [user.public_key for user in f.shared_users]
                with open(query_file, 'rb') as o:
                    data = o.read()
                decrypted = utils.decrypt(data, u.private_key, u.public_key, passwd)
                with tempfile.NamedTemporaryFile() as tmp:
                    tmp.write(decrypted)
                    tmp.flush()
                    encrypted = utils.encrypt(tmp, recipients)
                name = utils.store_file(encrypted, self.filename, u.username, self.storage_dir)
            self.request.session.flash(
                u'successfully shared file: %s with user %s' % (self.filename, share_user)
            )
            return HTTPFound(location=self.request.route_url('view_files'))
        with utils.db_session(self.dbmaker) as session:
            sharable_users = session.query(User).filter(User.sharable==True)
            sharable_users = sharable_users.filter(User.username!=self.username).all()
            sharable_users = [u.username for u in sharable_users]
        return dict(
            form=FormRenderer(form),
            username=self.username,
            filename=self.filename,
            sharable_users=sharable_users
        )

    @view_config(route_name='unshare_file')
    def unshare_file(self):
        if self.username is None:
            self.request.session.flash(u'You must be logged in to share files.')
            return HTTPFound(location=self.request.route_url('login', came_from='view_files'))
        query_file = os.path.join(self.storage_dir, self.username, self.filename)
        with utils.db_session(self.dbmaker) as session:
            f = session.query(File).filter(File.name==self.filename).first()
            u = session.query(User).filter(User.username==self.unshare_user).first()
            f.shared_users.remove(u)
            session.add(f)
        self.request.session.flash(
            u'no longer sharing file: %s with user: %s' % (self.filename, self.unshare_user)
        )
        return HTTPFound(location=self.request.route_url('view_files'))
