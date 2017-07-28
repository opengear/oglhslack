#!/usr/bin/env python

import os, sys, time, requests, json, urllib, re, textwrap, yaml
from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from collections import namedtuple
from functools import wraps, partial
from slackclient import SlackClient

def ensure_auth(f):
    """
    makes sure the client has a valid token when a function is called
    the call is going to be made once, in case of not authenticated,
    it will try to authenticate and call the function again
    """
    def wrapper(*args):
        result = f(*args)
        if type(result) is dict and 'error' in result and \
                len(result['error']) > 0 and \
                result['error'][0]['level'] == 1 and \
                result['error'][0]['type'] == 7 and \
		        result['error'][0]['text'] == 'Invalid session ID':
            args[0]._do_auth()
            return f(*args)
        return result
    return wrapper

class LighthouseApiClient:
    """
    the basic API client, with methods for GET, POST, PUT, and DELETE
    """

    def __init__(self):
        self.url = 'https://oglh-octo.opengear.com'
        requests.packages.urllib3.disable_warnings()

        self.api_url = self.url + '/api/v1'
        self.username = os.environ.get('OGLH_API_USER')
        self.password = os.environ.get('OGLH_API_PASS')
        self.token = None
        self.token_timeout = 5 * 60
        self.pending_name_ids = {}
        self.s = requests.Session()

        with open("../og-rest-api-specification-v1.raml", 'r') as stream:
            self.raml = yaml.load(stream)

    def _headers(self):
        headers = { 'Content-type' : 'application/json' }
        if self.token:
            headers.update({ 'Authorization' : 'Token ' + self.token })
        return headers

    def _do_auth(self):
        url = self._get_api_url('sessions')
        data = { 'username' : self.username, 'password' : self.password }
        self.token = None

        try:
            r = self.s.post(url, headers=self._headers(), \
                data=json.dumps(data), verify=False)
            r.raise_for_status()
        except Exception as e:
            print e
            return

        body = json.loads(r.text)

        self.token = body['session']
        if not self.token:
            raise RuntimeError('Auth failed')

    def _get_api_url(self, path):
        return '%s/%s' % (self.api_url, path)

    def _parse_response(self, response):
        try:
            return json.loads(response.text)
        except ValueError:
            return response.text

    @ensure_auth
    def get(self, path, data={}):
        params = urllib.urlencode(data)
        url = self._get_api_url(path)
        r = self.s.get(url, headers=self._headers(), params=params, \
            verify=False)
        return self._parse_response(r)

    @ensure_auth
    def post(self, path, data={}):
        url = self._get_api_url(path)
        r = self.s.post(url, headers=self._headers(), data=json.dumps(data), \
            verify=False)
        return self._parse_response(r)

    @ensure_auth
    def put(self, path, obj_id, data={}):
        url = self._get_api_url('%s/%s' % (path, obj_id) if obj_id else path)
        r = self.s.put(url, headers=self._headers(), data=json.dumps(data), \
            verify=False)
        return self._parse_response(r)

    @ensure_auth
    def delete(self, path, obj_id):
        url = self._get_api_url('%s/%s' % (path, obj_id) if obj_id else path)
        r = self.s.delete(url, headers=self._headers(), verify=False)
        return self._parse_response(r)

    def get_client(self):
        return self._get_client(self.raml, 0, '')

    def _get_client(self, node, level, path):

        top_children = set([key.split('/')[1] for key in node.keys() \
            if re.match('^\/', key) and len(key.split('/')) == 2])

        sub_children = set(['__'.join(key.split('/')[1:]) for key in node.keys() \
            if re.match('^\/', key) and len(key.split('/')) > 2])

        middle_children = set([s.split('__')[0] for s in sub_children])

        actions = set([key for key in node.keys() if re.match('^[^\/]', key)])

        kwargs = { 'path': path }

        for k in actions:
            if k == 'get' and len([l for l in top_children \
                if re.match('\{.+\}', l)]) > 0:
                #kwargs['list'] = node[k]
                kwargs['list'] = partial(self.get, path)
            elif k == 'get':
                kwargs['get'] = partial(self.get, path)
            elif k == 'put':
                kwargs['update'] = partial(self.get, path)
            else:
                kwargs[k] = node[k]

        for k in top_children:
            if re.match('\{.+\}', k):
                inner_props = self._get_client(node['/' + k], level + 4, path + '/' + k)
                for l in inner_props._asdict():
                    kwargs[l] = inner_props._asdict()[l]
            else:
                kwargs[k] = self._get_client(node['/' + k], level + 4, path + '/' + k)

        SynClient = namedtuple('SynClient', ' '.join(kwargs.keys()))
        return SynClient(**kwargs)
