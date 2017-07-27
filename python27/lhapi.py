#!/usr/bin/env python

import os, sys, time, requests
from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
import json, urllib, re, textwrap
from slackclient import SlackClient
from functools import wraps

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

class MinimalService:

    def __init__(self, client, service_name):
        """
        :client is a LighthouseApiClient
        :service_name is a prefix path for the used methods
        """
        self.client = client
        self.service_name = service_name

    def get(self):
        return self.client.get(self.service_name)

    def update(self, id, service):
        """
        :id the id of the object which is going to be updated
        :service stands for the object which is going to be updated
        """
        return self.client.put(self.service_name, id, service)

class DefaultService:

    def __init__(self, client, service_name):
        """
        :client is a LighthouseApiClient
        :service_name is a prefix path for the used methods
        """
        self.client = client
        self.service_name = service_name

    def find(self, id):
        return self.client.get('%s/%s' % (self.service_name, id))

    def create(self, service):
        return self.client.post(self.service_name, smartgroup)

    def delete(self, id):
        return self.client.delete(self.service_name, id)

    def update(self, id, service):
        return self.client.put(self.service_name, id, service)

    def list(self, **kwargs):
        return self.client.get(self.service_name, kwargs)

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

    def nodes(self):
        """
        Returns a node service with methods for dealing with node's properties

        API call: [no api call]

        Usage:

        >>> client.nodes()

        """
        return NodesService(self)

    def ports(self, id):
        """
        Retrieve a single port by ID

        API call: GET /ports/{id}

        Usage:

        >>> client.ports(port_id)

        """
        return self.get('ports/%s' % id)

    def services(self):
        """
        It returns the 'services' service

        Usage:

        >>> client.services()

        """
        return ServicesService(self)

    def global_tags(self):
        """
        It returns the global tags service

        Usage:

        >>> client.global_tags()

        """
        return GlobalTagsService(self)

    def interfaces(self):
        """
        It returns the interfaces service

        Usage:

        >>> client.interfaces()

        """
        return InterfacesService(self)

    def stats(self):
        """
        A summary of connected, pending and disconnected nodes

        API call: GET /stats/nodes/connection_summary

        Usage:

        >>> client.stats()

        """
        return self.get('stats/nodes/connection_summary')

    def support_report(self):
        """
        Retrieve the support report data

        API call: GET /support_report

        Usage:

        >>> client.support_report()
        """
        return self.get('support_report')

    def auth(self):
        """
        Return an auth service

        Usage:

        >>> client.auth()
        """
        return MinimalService(self, 'auth')

    def bundles(self):
        """
        Returns a bundles service

        Usage:

        >>> client.bundles()

        """
        return BundlesService(self)

    def users(self):
        """
        Returns a users service

        Usage:

        >>> client.users()

        """
        return DefaultService(self, 'users')

    def groups(self):
        """
        Returns a groups service

        Usage:

        >>> client.groups()

        """
        return DefaultService(self, 'groups')

class NodesService(DefaultService):
    def __init__(self, client):
        DefaultService.__init__(self, client, 'nodes')

    def smartgroups(self):
        """
        Retrieve the node smart groups' service

        API call: [no api call]

        Usage:

        >>> client.nodes().smartgroups()

        """
        return DefaultService(self.client, 'nodes/smartgroups')

    def manifest(self):
        """
        Download the system manifest file

        API call: GET /nodes/manifest

        Usage:

        >>> client.nodes().manifest()

        """
        return self.client.get('nodes/manifest')

    def registration_package(self, id):
        """
        Retrieve the enrollment package for a node.

        API call: GET /nodes/{id}/registration_package

        Usage:

        >>> client.nodes().registration_package(node_id)

        """
        return self.client.get('nodes/%s/registration_package' % id)

    def tags(self, id):
        """
        Retrieve the node tags' service

        API call: [no api call]

        Usage:

        >>> client.nodes().tags(node_id)

        """
        return DefaultService(self, 'nodes/%s/tags' % id)

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
        return self.client.get('ports/%s' % id)

    def delete(self, id):
        raise RuntimeError('It is not possible to delete Nodes')

class ServicesService:
    def __init__(self, client):
        self.client = client

    def https(self):
        return MinimalService(self.client, 'services/https')

    def ntp(self):
        return MinimalService(self.client, 'services/ntp')

    def console_gateway(self):
        return MinimalService(self.client, 'services/console_gateway')

class GlobalTagsService(DefaultService):
    def __init__(self, client):
        DefaultService.__init__(self, client, 'tags/node_tags')

    def find(self, id):
        raise RuntimeError('It is not possible to retrieve a single tag')

class InterfacesService:
    def __init__(self, client):
        self.client = client

    def list(self):
        """
        Get a list of the network interfaces on the Lighthouse server.

        API call: GET /interfaces

        Usage:

        >>> client.interfaces().list()

        """
        return self.client.get('interfaces')

    def find(self, id):
        """
        Get interface information by id.

        API call: GET /interfaces/{id}

        Usage:

        >>> client.interfaces().find(interface_id)

        """
        return self.client.get('interfaces/%s' % id)

    def update(self, id, interface):
        """
        Update settings for interface {id}

        API call: PUT /interfaces/{id}

        Usage:

        >>> client.interfaces().update(interface_id, interface)

        """
        return self.client.put('interfaces', id, interface)

class BundlesService(DefaultService):
    def __init__(self, client):
        DefaultService.__init__(self, client, 'bundles')

    def delete(self, id):
        raise RuntimeError('It is not possible to delete Bundles')

    def automatic_tags(self, id):
        """
        Returns an automatic tags service

        Usage:

        >>> client.bundles().automatic_tags(bundle_id)

        """
        return DefaultService(self.client, 'bundles/%s/automatic_tags' % id)

class SystemService:
    def __init__(self, client):
        self.client = client

    def hostname(self):
        return MinimalService(self.client, 'system/hostname')

    def webui_session_timeout(self):
        return MinimalService(self.client, 'system/webui_session_timeout')

    def global_enrollment_token(self):
        return MinimalService(self.client, 'system/global_enrollment_token')

    def manifest_link(self):
        return self.client.get('system/manifest_link')

    def timezone(self):
        return MinimalService(self.client, 'system/timezone')

    def external_address(self):
        return MinimalService(self.client, 'system/external_address')

    def time(self):
        return MinimalService(self.client, 'system/time')

    def config(self):
        return self.client.delete('system/config', '')
