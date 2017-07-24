#!/usr/bin/env python

import os
import sys
import time
import requests
from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
import json
import urllib
import re
import textwrap
from slackclient import SlackClient

#from functools import reduce
from functools import wraps

def ensure_auth(f):
    """ makes sure the client has a valid token
    when a function is called
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
        #retries = Retry(total=5, backoff_factor=0.2, status_forcelist=[ 401, 500 ])
        #self.s.mount('https://', HTTPAdapter(max_retries=retries))
        #self._do_auth()

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
            r = self.s.post(url, headers=self._headers(), data=json.dumps(data), verify=False)
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
            #response.raise_for_status()
            return json.loads(response.text)
        except ValueError:
            raise Exception('Invalid response')

    @ensure_auth
    def get(self, path, data={}):
        params = urllib.urlencode(data)
        url = self._get_api_url(path)
        r = self.s.get(url, headers=self._headers(), params=params, verify=False)
        return self._parse_response(r)

    @ensure_auth
    def post(self, path, data={}):
        url = self._get_api_url(path)
        r = self.s.post(url, headers=self._headers(), data=json.dumps(data), verify=False)
        return self._parse_response(r)

    @ensure_auth
    def put(self, path, obj_id, data={}):
        url = self._get_api_url('%s/%s' % (path, obj_id))
        r = self.s.put(url, headers=self._headers(), data=json.dumps(data), verify=False)
        return self._parse_response(r)

    @ensure_auth
    def delete(self, path, obj_id):
        url = self._get_api_url('%s/%s' % (path, obj_id))
        r = self.s.delete(url, headers=self._headers(), verify=False)
        return self._parse_response(r)


    def nodes(self):
        return NodesService(self)


class NodesService:
    def __init__(self, client):
        self.client = client

    def find(self, id):
        return self.client.get('nodes/%d' % int(id))

    def create(self, enrollment):
        return self.client.post('nodes', enrollment)

    def update(self, id, node):
        return self.client.put('nodes', id, node)

    def list(self, **kwargs):
        return self.client.get('nodes', kwargs)

    def smartgroups(self):
        return SmartGroupsService(self.client)

    def manifest(self):
        return self.client.get('nodes/manifest')

    def ids(self, **kwargs):
        return self.client.get('nodes/ids', kwargs)

    def fields(self):
        return self.client.get('nodes/fields')

    def registration_package(self, id):
        return self.client.get('nodes/%d/registration_package' % int(id))

    def tags(self):
        return []

    def ports(self):
        return None

class SmartGroupsService:

    def __init__(self, client):
        self.client = client

    def find(self, id):
        return self.client.get('nodes/smartgroups/%d' % int(id))

    def create(self, smartgroup):
        return self.client.post('nodes/smartgroups', smartgroup)

    def delete(self, id):
        return self.client.delete('nodes/smartgroups/%d' % int(id))

    def update(self, id, smartgroup):
        return self.client.put('nodes/smartgroups', id, smartgroup)

    def list(self, **kwargs):
        return self.client.get('nodes/smartgroups', kwargs)



#class SmartGroup:
#    def __init__(self, id=0):
#        if
