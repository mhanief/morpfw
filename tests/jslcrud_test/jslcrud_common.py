import os
import morepath
import yaml
from webtest import TestApp as Client
from morpfw.jslcrud.model import Collection, Model, Schema
from morpfw.jslcrud.model import StateMachine
from morpfw.jslcrud.app import App as BaseApp
import morpfw.jslcrud.signals as signals
import jsl
import json
from uuid import uuid4
from datetime import datetime
import jsonobject


class App(BaseApp):
    pass


def validate_body(request, json):
    if not isinstance(json['body'], str):
        return

    if json['body'].lower() == "invalid":
        return "Body must not be 'invalid'"


class PageSchema(jsonobject.JsonObject):

    uuid = jsonobject.StringProperty(required=False)
    title = jsonobject.StringProperty(required=True, default='')
    body = jsonobject.StringProperty(required=True, default='')
    value = jsonobject.IntegerProperty(required=False)
    footer = jsonobject.StringProperty(required=False, default='')
    created = jsonobject.DateTimeProperty(required=False)
    modified = jsonobject.DateTimeProperty(required=False)
    state = jsonobject.StringProperty(required=False)


@App.formvalidators(schema=PageSchema)
def page_formvalidators(schema):
    return [validate_body]


@App.identifierfields(schema=PageSchema)
def page_identifierfields(schema):
    return ['uuid']


@App.default_identifier(schema=PageSchema)
def page_default_identifier(schema, obj, request):
    return str(uuid4())


class PageCollection(Collection):
    schema = PageSchema


class PageModel(Model):
    schema = PageSchema


class ObjectSchema(Schema):

    id = jsonobject.IntegerProperty(required=False)
    uuid = jsonobject.StringProperty(required=False)
    body = jsonobject.StringProperty(required=True, default='')
    created_flag = jsonobject.BooleanProperty(required=False, default=False)
    updated_flag = jsonobject.BooleanProperty(required=False, default=False)


@App.jslcrud_identifierfields(schema=ObjectSchema)
def object_identifierfields(schema):
    return ['id']


@App.jslcrud_default_identifier(schema=ObjectSchema)
def object_default_identifier(schema, obj, request):
    return None


class ObjectCollection(Collection):
    schema = ObjectSchema


class ObjectModel(Model):
    schema = ObjectSchema


@App.json(model=ObjectCollection, name='get_uuid')
def get_object_by_uuid(context, request):
    uuid = request.GET.get('uuid')
    return context.get_by_uuid(uuid).json()


@App.jslcrud_subscribe(signal=signals.OBJECT_CREATED, model=ObjectModel)
def object_created(app, request, obj, signal):
    obj.data['created_flag'] = True


@App.jslcrud_subscribe(signal=signals.OBJECT_UPDATED, model=ObjectModel)
def object_updated(app, request, obj, signal):
    obj.data['updated_flag'] = True


class PageStateMachine(StateMachine):

    states = ['new', 'pending', 'approved']
    transitions = [
        {'trigger': 'approve', 'source': [
            'new', 'pending'], 'dest': 'approved'},
        {'trigger': 'submit', 'source': 'new', 'dest': 'pending'}
    ]


@App.jslcrud_statemachine(model=PageModel)
def get_pagemodel_statemachine(context):
    return PageStateMachine(context)


class NamedObjectSchema(jsonobject.JsonObject):

    name = jsonobject.StringProperty(required=False)
    body = jsonobject.StringProperty(required=True, default='')
    created_flag = jsonobject.BooleanProperty(required=False, default=False)
    updated_flag = jsonobject.BooleanProperty(required=False, default=False)


@App.jslcrud_identifierfields(schema=NamedObjectSchema)
def namedobject_identifierfields(schema):
    return ['name']


@App.jslcrud_default_identifier(schema=NamedObjectSchema)
def namedobject_default_identifier(schema, obj, request):
    return obj['name']


class NamedObjectCollection(Collection):
    schema = NamedObjectSchema


class NamedObjectModel(Model):
    schema = NamedObjectSchema


def get_client(app, config='settings.yml'):
    if isinstance(config, str):
        with open(os.path.join(os.path.dirname(__file__), config)) as f:
            settings = yaml.load(f) or {}
    else:
        settings = config

    morepath.autoscan()
    app.init_settings(settings)
    morepath.commit(app)
    c = Client(app())
    return c


def run_jslcrud_test(app, skip_aggregate=False):
    c = get_client(app)

    c.authorization = ('Basic', ('admin', 'admin'))

    # test loading the model details and schema
    r = c.get('/pages')

    assert r.json['schema']['type'] == 'object'

    # lets try creating an entry
    r = c.post_json('/pages/', {'title': 'Hello', 'body': 'World'})

    assert r.json['data']['title'] == 'Hello'

    uuid = r.json['data']['uuid']
    assert uuid

    r = c.get('/pages/%s' % uuid)

    assert r.json['data']['title'] == 'Hello'
    assert r.json['data']['state'] == 'new'

    # lets see if the entry appears in listing

    for i in range(10):
        r = c.post_json(
            '/pages/', {'title': 'page%s' % i, 'body': 'page%sbody' % i, 'value': i})

    if not skip_aggregate:
        r = c.get('/pages/+aggregate', {'group': json.dumps({
            'count': {
                'function': 'count',
                'field': 'uuid'
            },
            'year': {
                'function': 'year',
                'field': 'created'
            },
            'month': {
                'function': 'month',
                'field': 'created'
            },
            'day': {
                'function': 'day',
                'field': 'created'
            },
            'sum': {
                'function': 'sum',
                'field': 'value'
            },
            'avg': {
                'function': 'avg',
                'field': 'value'
            }
        })})

        now = datetime.utcnow()
        assert r.json[0]['year'] == now.year
        assert r.json[0]['month'] == now.month
        assert r.json[0]['day'] == now.day
        assert r.json[0]['sum'] == 45
        assert r.json[0]['count'] == 11
        assert r.json[0]['avg'] == 4.5

    r = c.get('/pages/+search',
              {'q': json.dumps({'operator': 'in',
                                'value': ['Hello', 'something'],
                                'field': 'title'})})

    assert r.json['results'][0]['data']['title'] == 'Hello'

    r = c.get('/pages/+search')

    assert 'Hello' in [i['data']['title'] for i in r.json['results']]

    r = c.get('/pages/+search', {
        'select': '$.title',
        'q': json.dumps({'operator': 'in',
                         'value': ['Hello'],
                         'field': 'title'})
    })

    assert r.json['results'] == [['Hello']]

    r = c.get('/pages/+search', {
        'select': '$.[title, body]',
        'q': json.dumps({'operator': 'in',
                         'value': ['Hello'],
                         'field': 'title'})
    })

    assert r.json['results'] == [['Hello', 'World']]

    r = c.get('/pages/+search', {
        'order_by': 'title'
    })

    assert list([i['data']['title'] for i in r.json['results']]) == (
        ['Hello'] + ['page%s' % i for i in range(10)])

    r = c.get('/pages/+search', {
        'order_by': 'title:desc'
    })

    assert list([i['data']['title'] for i in r.json['results']]) == (
        ['page%s' % i for i in range(9, -1, -1)] + ['Hello'])

    r = c.get('/pages/+search', {
        'order_by': 'title',
        'limit': 5
    })

    assert list([i['data']['title'] for i in r.json['results']]) == (
        ['Hello'] + ['page%s' % i for i in range(4)])

    r = c.get('/pages/+search', {
        'order_by': 'title',
        'offset': 1
    })

    assert list([i['data']['title'] for i in r.json['results']]) == (
        ['page%s' % i for i in range(10)])

    r = c.get('/pages/+search', {
        'order_by': 'title',
        'offset': 1,
        'limit': 5
    })

    assert list([i['data']['title'] for i in r.json['results']]) == (
        ['page%s' % i for i in range(5)])

    # lets create another with wrong invalid values
    r = c.post_json('/pages/',
                    {'title': 'page2', 'body': 123, 'footer': 123},
                    expect_errors=True)

    assert r.json['status'] == 'error'
    assert len(r.json['field_errors']) == 2
    assert len(r.json['form_errors']) == 0

    r = c.post_json('/pages/',
                    {'title': 'page2', 'body': 'invalid', 'footer': 123},
                    expect_errors=True)

    assert r.json['status'] == 'error'
    assert len(r.json['field_errors']) == 1
    assert len(r.json['form_errors']) == 1

    # lets update the entry
    r = c.patch_json('/pages/%s' % uuid, {'body': 'newbody'})

    assert r.json['status'] == 'success'

    r = c.get('/pages/%s' % uuid)

    assert r.json['data']['body'] == 'newbody'

    # lets approve the page

    r = c.post_json('/pages/%s/+statemachine' %
                    uuid, {'transition': 'approve'})

    assert r.json['data']['state'] == 'approved'

    # it cant be approved twice

    r = c.post_json('/pages/%s/+statemachine' % uuid, {
        'transition': 'approve'
    }, expect_errors=True)

    assert r.status_code == 422

    r = c.patch_json('/pages/%s' %
                     uuid, {'body': 'invalid'}, expect_errors=True)

    assert r.json['status'] == 'error'

    # lets delete the entry

    r = c.get('/pages/+search')

    assert len(r.json['results']) == 11

    r = c.delete('/pages/%s' % uuid)

    assert r.json['status'] == 'success'

    r = c.get('/pages/%s' % uuid, expect_errors=True)

    r = c.get('/pages/+search')

    assert len(r.json['results']) == 10

    r = c.get('/objects')

    assert r.json

    r = c.post_json('/objects/', {'body': 'hello'})

    assert r.json['data']['body'] == 'hello'
    assert r.json['data']['id']
    assert r.json['data']['created_flag'] is True
    assert r.json['data']['created']
    assert r.json['data']['creator'] == 'admin'
    uuid = r.json['data']['uuid']
    original_object = r.json['data']
    assert len(uuid) == 32
    r = c.get('/objects/+get_uuid?uuid=%s' % uuid)

    object_by_uuid = r.json['data']

    assert original_object == object_by_uuid

    # test creation of named object
    r = c.post_json('/named_objects/',
                    {'name': 'obj1', 'body': 'hello'})

    r = c.get('/named_objects/obj1')

    assert r.json['data']['name'] == 'obj1'

    # duplicate should fail
    r = c.post_json('/named_objects/',
                    {'name': 'obj1', 'body': 'hello'},
                    expect_errors=True)

    assert r.status_code == 422

    # catch issue with ':' in name

    r = c.post_json('/named_objects/',
                    {'name': 'object:obj2', 'body': 'hello'})

    r = c.get('/named_objects/object:obj2')

    assert r.json['data']['name'] == 'object:obj2'

    r = c.get('/named_objects/object:obj2?select=$.[body]')

    assert r.json == ['hello']

    # catch issue with ' ' in name

    r = c.post_json('/named_objects/',
                    {'name': 'object obj2', 'body': 'hello'})

    r = c.get('/named_objects/object%20obj2')

    assert r.json['data']['name'] == 'object obj2'

    r = c.patch_json('/named_objects/object%20obj2', {'body': 'hello1'})

    assert r.status_code == 200
