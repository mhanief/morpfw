from ...jslcrud import Collection, Model, StateMachine
from ...jslcrud import errors as cruderrors
from jsonschema import validate
from ..dbmodel.user import User
from ..app import App
import jsl
from .. import exc
import sqlalchemy as sa
import sqlalchemy_jsonfield as sajson
from .base import BaseSchema, NAME_PATTERN
from ...jslcrud import signals as crudsignal
from ...jslcrud import errors as cruderrors
from .group import GroupCollection, GroupSchema
from uuid import uuid4


class LoginSchema(jsl.Document):
    class Options(object):
        title = 'credential'

    username = jsl.StringField(required=True, pattern=NAME_PATTERN)
    password = jsl.StringField(required=True)
    password_validate = jsl.StringField(required=True)


class UserSchema(BaseSchema):
    class Options(object):
        title = 'user'
        additional_properties = True
    username = jsl.StringField(required=True, pattern=NAME_PATTERN)
    password = jsl.StringField(required=False)
    groups = jsl.ArrayField(items=jsl.StringField(
        pattern=NAME_PATTERN), required=False)
    attrs = jsl.DictField(required=False)
    state = jsl.StringField(required=False)
    created = jsl.StringField(required=False)
    modified = jsl.StringField(required=False)
    nonce = jsl.StringField(required=False)


@App.jslcrud_identifierfields(schema=UserSchema)
def user_identifierfields(schema):
    return ['username']


class UserCollection(Collection):
    schema = UserSchema

    def authenticate(self, username, password):
        try:
            user = self.storage.get(username)
        except cruderrors.NotFoundError:
            return False
        return user.validate(password)

    def search(self, *args, **kwargs):
        result = super(UserCollection, self).search(*args, **kwargs)
        return list([o for o in result if o.data['state'] != 'deleted'])

    def get(self, identifier):
        obj = super(UserCollection, self).get(identifier)
        if obj.data['state'] == 'deleted':
            raise cruderrors.NotFoundError(
                self.storage.model, identifier)
        return obj

    def get_by_uuid(self, uuid):
        obj = super(UserCollection, self).get_by_uuid(uuid)
        if obj.data['state'] == 'deleted':
            raise cruderrors.NotFoundError(
                self.storage.model, uuid)
        return obj

    def _create(self, data):
        exists = None
        data['nonce'] = uuid4().hex
        try:
            exists = self.storage.get(data['username'])
        except cruderrors.NotFoundError:
            pass
        if exists:
            raise exc.UserExistsError(data['username'])
        return super(UserCollection, self)._create(data)


class UserModel(Model):

    schema = UserSchema

    def change_password(self, password, new_password):
        if not self.app.authmanager_has_role(self.request, 'administrator'):
            if not self.validate(password, check_state=False):
                raise exc.InvalidPasswordError(self.data['username'])
        self.storage.change_password(self.data['username'], new_password)

    def validate(self, password, check_state=True):
        if check_state and self.data['state'] != 'active':
            return False
        return self.storage.validate(self.data['username'], password)

    def groups(self):
        return self.storage.get_user_groups(self.data['username'])

    def group_roles(self):
        group_roles = {}
        for g in self.groups():
            group_roles[g.data['groupname']] = g.get_member_roles(
                self.data['username'])
        return group_roles


class UserStateMachine(StateMachine):

    states = ['active', 'inactive', 'deleted']
    transitions = [
        {'trigger': 'activate', 'source': 'inactive', 'dest': 'active'},
        {'trigger': 'deactivate', 'source': 'active', 'dest': 'inactive'},
        {'trigger': 'delete', 'source': [
            'active', 'inactive'], 'dest': 'deleted'}
    ]


@App.jslcrud_statemachine(model=UserModel)
def userstatemachine(context):
    return UserStateMachine(context)


@App.jslcrud_jsontransfrom(schema=UserSchema)
def jsontransform(request, context, data):
    data = data.copy()
    for f in ['password', 'password_validate']:
        if f in data.keys():
            del data[f]
    data['groups'] = [g.identifier for g in context.groups()]
    return data


@App.jslcrud_subscribe(signal=crudsignal.OBJECT_CREATED, model=UserModel)
def add_user_to_default_group(app, request, obj, signal):
    request = obj.request
    storage = app.get_authmanager_storage(request, GroupSchema)
    try:
        g = storage.get('__default__')
    except cruderrors.NotFoundError:
        gcol = GroupCollection(request, storage)
        g = gcol.create({'groupname': '__default__'})
    g.add_members([obj.data['username']])
