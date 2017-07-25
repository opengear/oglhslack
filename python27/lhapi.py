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
    """
    the basic API client, with methods for GET, POST, PUT, and DELETE
    it also has methods for accessing the other services:
    - NodesService
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
            #response.raise_for_status()
            return json.loads(response.text)
        except ValueError:
            raise Exception('Invalid response')

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
        url = self._get_api_url('%s/%s' % (path, obj_id))
        r = self.s.put(url, headers=self._headers(), data=json.dumps(data), \
            verify=False)
        return self._parse_response(r)

    @ensure_auth
    def delete(self, path, obj_id):
        url = self._get_api_url('%s/%s' % (path, obj_id))
        r = self.s.delete(url, headers=self._headers(), verify=False)
        return self._parse_response(r)


    def nodes(self):
        return NodesService(self)


class NodesService:
    """
    A service which provides access for the nodes

    All the following methods are expected to be executed after a call like:

    >>> import lhapi
    >>> client = lhapi.LighthouseApiClient()

    it also has methods for accessing the other services:
    - SmartGroupsService
    - TagsService
    """

    def __init__(self, client):
        """
        :client is an instance of the @LighthouseApiClient class
        it will be changed soon, NodesService will be a extend a base class
        """
        self.client = client

    def list(self, **kwargs):
        """
        Gets nodes attached to this lighthouse instance

        API call: GET /nodes

        Usage:

        >>> client.nodes().list()

        """
        return self.client.get('nodes', kwargs)

    def create(self, enrollment):
        """
        Enqueue a new node for enrollment

        API call: POST /nodes

        Usage:

        >>> client.nodes().create(enrollment)

        """
        return self.client.post('nodes', enrollment)

    def smartgroups(self):
        """
        Retrieve the node smart groups' service

        API call: [no api call]

        Usage:

        >>> client.nodes().smartgroups()

        """
        return SmartGroupsService(self.client)

    def update(self, id, node):
        """
        Update a node

        API call: PUT /nodes/{id}

        Usage:

        >>> client.nodes().update(node_id, node)

        """
        return self.client.put('nodes', id, node)

    def manifest(self):
        """
        Download the system manifest file

        API call: GET /nodes/manifest

        Usage:

        >>> client.nodes().manifest()

        """
        return self.client.get('nodes/manifest')

    def find(self, id):
        """
        Find a node by its `id`.

        API call: GET /nodes

        Usage:

        >>> client.nodes().find(node_id)

        """
        return self.client.get('nodes/%d' % int(id))

    def registration_package(self, id):
        """
        Retrieve the enrollment package for a node.

        API call: GET /nodes/{id}/registration_package

        Usage:

        >>> client.nodes().registration_package(node_id)

        """
        return self.client.get('nodes/%d/registration_package' % int(id))

    def tags(self, id):
        """
        Retrieve the node tags' service

        API call: [no api call]

        Usage:

        >>> client.nodes().tags(node_id)

        """
        return TagsService(self, id)

    def ids(self, **kwargs):
        """
        Obtain a list of node ids

        API call: GET /nodes/ids

        Usage:

        >>> client.nodes().ids()

        """
        return self.client.get('nodes/ids', kwargs)

    def fields(self):
        """
        Obtain a list of fields which can be used to perform queries
        against nodes

        API call: GET /nodes/fields

        Usage:

        >>> client.nodes().fields()

        """
        return self.client.get('nodes/fields')

    def ports(self, id):
        """
        Retrieve a list of all ports belonging to a node

        API call: GET /nodes/{id}/ports

        Usage:

        >>> client.nodes().ports(node_id)

        """
        return self.client.get('/ports/%d' % int(id))

class SmartGroupsService:
    """
    A service which provides access for the smargroups

    All the following methods are expected to be executed after a call like:

    >>> import lhapi
    >>> client = lhapi.LighthouseApiClient()

    """

    def __init__(self, client):
        """

        """
        self.client = client

    def find(self, id):
        """
        Retrieve the details for a smart group.

        API call: GET /nodes/smartgroups/{groupId}

        Usage:

        >>> client.nodes().smartgroups().find(smartgroup_id)

        """
        return self.client.get('nodes/smartgroups/%d' % int(id))

    def create(self, smartgroup):
        """
        Create a new node smart group

        API call: POST /nodes/smartgroups

        Usage:

        >>> client.nodes().smartgroups().create(smartgroup)

        """
        return self.client.post('nodes/smartgroups', smartgroup)

    def delete(self, id):
        """
        Delete a smart group

        API call: DELETE /nodes/smartgroups/{groupId}

        Usage:

        >>> client.nodes().smartgroups().delete(smartgroup_id)

        """
        return self.client.delete('nodes/smartgroups/%d' % int(id))

    def update(self, id, smartgroup):
        """
        Updates the details for a smart group

        API call: PUT /nodes/smartgroups/{groupId}

        Usage:

        >>> client.nodes().smartgroups().update(smartgroup_id, smartgroup)

        """
        return self.client.put('nodes/smartgroups', id, smartgroup)

    def list(self, **kwargs):
        """
        Retrieve a list of node smart groups

        API call: GET /nodes/smartgroups

        Usage:

        >>> client.nodes().smartgroups().list()

        """
        return self.client.get('nodes/smartgroups', kwargs)

class TagsService:
    """
    A service which provides access for the tags

    All the following methods are expected to be executed after a call like:

    >>> import lhapi
    >>> client = lhapi.LighthouseApiClient()

    """
    def __init__(self, client, node_id):
        self.client = client
        self.node_id = node_id

    def list(self):
        """
        Get the list of all tags associated with this node

        API call: GET /nodes/{id}/tags

        Usage:

        >>> client.nodes().tags(node_id).list()

        """
        return self.client.get('nodes/%d/tags' % int(self.node_id))

    def create(self, tag):
        """
        Create and associate a new tag with the node

        API call: POST /nodes/{id}/tags

        Usage:

        >>> client.nodes().tags(node_id).create(tag)

        """
        return self.client.post('nodes/%d/tags' % int(self.node_id), tag)

    def find(self, id):
        """
        Get a tag's information by ID

        API call: GET /nodes/{id}/tags/{tag_value_id}

        Usage:

        >>> client.nodes().tags(node_id).find(tag_id)

        """
        return self.client.get('nodes/%d/tags/%d' % int(self.node_id), \
            int(self.node_id))

    def delete(self, id):
        """
        Delete a tag value from the node

        API call: DELETE /nodes/{id}/tags/{tag_value_id}

        Usage:

        >>> client.nodes().tags(node_id).delete(tag_id)

        """
        return self.client.delete('nodes/%d/tags/%d' % int(self.node_id), \
            int(self.node_id))

    def update(self, id, tag):
        """
        Update tag information for {node_tag_id} in node {id}

        API call: PUT /nodes/{id}/tags/{tag_value_id}

        Usage:

        >>> client.nodes().tags(node_id).update(tag_id, tag)

        """
        return self.client.put('nodes/%d/tags/%d' % int(self.node_id), \
            int(self.node_id), tag)
