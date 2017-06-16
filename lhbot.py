#!/usr/bin/env python

import os
import sys
import time
import requests
import json
import urllib
import re
import textwrap
from slackclient import SlackClient

class LighthouseApiClient:

	def __init__(self):
		self.url = 'https://oglh-octo.opengear.com'
		self.api_url = self.url + '/api/v1'
		self.username = os.environ.get('OGLH_API_USER')
		self.password = os.environ.get('OGLH_API_PASS')
		self.token = None
		self.token_timeout = 5 * 60
		self.pending_name_ids = {}
		self._do_auth()

	def _headers(self):
		headers = { 'Content-type' : 'application/json' }
		if self.token:
			headers.update({ 'Authorization' : 'Token ' + self.token })
		return headers

	def _do_auth(self):
		url = self.api_url + '/sessions'
		data = { 'username' : self.username, 'password' : self.password }

		try:
			r = requests.post(url, headers=self._headers(), data=json.dumps(data), verify=False)
			r.raise_for_status()
		except:
			return None
		body = json.loads(r.text)

		self.token = body['session']
		if not self.token:
			raise RuntimeError('Auth failed')

	def get_ports(self, label):
		url = self.api_url + '/nodes'
		data = { 'port:label' : label }
		params = urllib.urlencode(data)

		try:
			r = requests.get(url, headers=self._headers(), params=params, verify=False)
			r.raise_for_status()
		except:
			return None
		body = json.loads(r.text)

		ports = []
		for node in body['nodes']:
			for port in node['ports']:
				if port['label'].lower() == label:
					ports.append(port)
		return ports

	def get_pending(self):
		url = self.api_url + '/nodes'
		data =  { 'config:status' : 'Registered' }
		params = urllib.urlencode(data)

		try:
			r = requests.get(url, headers=self._headers(), params=params, verify=False)
			r.raise_for_status()
		except:
			return None, None
		body = json.loads(r.text)

		name_ids = {}
		for node in body['nodes']:
			if node['approved'] == 0:
				name_ids[node['name']] = node['id']

		new_pending = (set(name_ids) > set(self.pending_name_ids))
		self.pending_name_ids= name_ids

		return name_ids, new_pending

	def get_summary(self):
		url = self.api_url + '/stats/nodes/connection_summary'

		try:
			r = requests.get(url, headers=self._headers(), verify=False)
			r.raise_for_status()
		except:
			return None, None, None
		body = json.loads(r.text)

		for conn in body['connectionSummary']:
			if conn['status'] == 'connected':
				connected = int(conn['count'])
			elif conn['status'] == 'pending':
				pending = int(conn['count'])
				continue
			elif conn['status'] == 'disconnected':
				disconnected = int(conn['count'])

		return connected, pending, disconnected

	def _delete_node(self, node):
		url = self.api_url + '/nodes' + '/' + node['id']

		try:
			r = requests.delete(url, headers=self._headers(), verify=False)
			r.raise_for_status()
		except:
			return None

		return True

	def delete_nodes(self, node_names):
		url = self.api_url + '/nodes'

		try:
			r = requests.get(url, headers=self._headers(), verify=False)
			r.raise_for_status()
		except:
			return None
		body = json.loads(r.text)

		deleted_names = []
		for node in body['nodes']:
			if node['name'] in node_names:
				if self._delete_node(node):
					deleted_names.append(node['name'])
		return deleted_names


	def _approve_node(self, node):
		url = self.api_url + '/nodes' + '/' + node['id']

		approved_node = { 'node' : {} }
		approved_node['node']['name'] = node['name']
		approved_node['node']['mac_address'] = ''
		approved_node['node']['description'] = ''
		approved_node['node']['approved'] = 1
		approved_node['node']['tags'] = node['tag_list']['tags']

		try:
			r = requests.put(url, headers=self._headers(), data=json.dumps(approved_node), verify=False)
			r.raise_for_status()
		except:
			return None

		return True

	def approve_nodes(self, node_names):
		url = self.api_url + '/nodes'
		data = { 'config:status' : 'Registered' }
		params = urllib.urlencode(data)

		try:
			r = requests.get(url, headers=self._headers(), params=params, verify=False)
			r.raise_for_status()
		except:
			return None
		body = json.loads(r.text)

		approved_names = []
		for node in body['nodes']:
			if node['name'] in node_names:
				if self._approve_node(node):
					approved_names.append(node['name'])
		return approved_names

	def tick(self, elapsed_seconds):
		if not self.token_timeout > 0:
			self._do_auth()
		self.token_timeout -= elapsed_seconds


class LighthouseBot:

	def __init__(self):
		self.poll_count = 0
		self.poll_interval = 1
		self.bot_name = 'lhbot'

		self.func_intents = { \
			self._get_port_ssh : { 'ssh', 'sshlink' }, \
			self._get_port_web : { 'web', 'webterm', 'weblink' }, \
			self._get_port : { 'con', 'console', 'gimme' }, \
			self._get_node_summary : { 'sup', 'summary', 'stats', 'status', 'howzit' }, \
			self._get_web : { 'lighthouse', 'lhweb', 'webui', 'gui' }, \
			self._check_pending : { 'pending' }, \
			self._approve_nodes: { 'ok', 'okay', 'approve' }, \
			self._delete_nodes: { 'nuke', 'kill', 'delete' } \
		}

 		self.slack_client = SlackClient(os.environ.get('SLACK_BOT_TOKEN'))
		if not self.slack_client.rtm_connect():
			raise RuntimeError('Slack connection failed')
 		self.bot_at = '<@' + self._get_bot_id() + '>'

		self.lh_client = LighthouseApiClient()

	def _get_bot_id(self):
		try:
			users_list = self.slack_client.api_call('users.list')
		except:
			raise RuntimeError('Slack users list failed')
		for member in users_list['members']:
			if member['name'] == self.bot_name:
				return member['id']
		raise RuntimeError('User ' + self.bot_name + ' not found')

	def _ports_list_ssh(self, ports, label, username):
		ssh_urls = []

		for port in ports:
			if not 'proxied_ssh_url' in port:
				continue
			ssh_url = re.sub(r'ssh://lhbot', 'ssh://' + username, port['proxied_ssh_url'])
			ssh_urls.append('<' + ssh_url + '>')
		return ssh_urls

	def _ports_list_web(self, ports, label):
		web_urls = []

		for port in ports:
			if not 'web_terminal_url' in port:
				continue
			web_url = self.lh_client.url + '/'
			web_url += port['web_terminal_url']
			web_urls.append('<' + web_url + '>')
		return web_urls

	def _get_port_ssh(self, label, username):
		ports = self.lh_client.get_ports(label)
		urls = self._ports_list_ssh(ports, label, username)

		if not urls:
			return ':thumbsdown:'
		return '\n'.join(urls)


	def _get_port_web(self, label, *_):
		ports = self.lh_client.get_ports(label)
		urls = self._ports_list_web(ports, label)

		if not urls:
			return ':thumbsdown:'
		return '\n'.join(urls)

	def _get_port(self, label, username):
		ports = self.lh_client.get_ports(label)
		ssh_urls = self._ports_list_ssh(ports, label, username)
		web_urls = self._ports_list_web(ports, label)

		urls = [ x for t in zip(ssh_urls, web_urls) for x in t ]
		if not urls:
			return 'I can\'t seem to find that one :thumbsdown:'
		return '\n'.join(urls)

	def _approve_nodes(self, str_names, *_):
		names = str_names.split(' ')
		approved_names = self.lh_client.approve_nodes(names)
		response = ''
		for name in names:
			if name in approved_names:
				emoji = 'approved :thumbsup:'
			else:
				emoji = 'failed :thumbsdown:'
			response +=  name + ' ' + emoji + '\n'
		return response

	def _delete_nodes(self, str_names, *_):
		names = str_names.split(' ')
		deleted_names = self.lh_client.delete_nodes(names)
		response = ''
		for name in names:
			if name in deleted_names:
				emoji = 'nuked :boom:'
			else:
				emoji = 'failed :thumbsdown:'
			response +=  name + ' ' + emoji + '\n'
		return response

	def _check_pending(self, new_only, *_):
		pending_nodes, new_pending = self.lh_client.get_pending()

		if not new_pending and new_only:
			return None

		if pending_nodes:
			response = 'Nodes await your approval!\n'
			response += '\n'.join(pending_nodes)
		else:
			response = 'Nothing pending, as you were'
		return response

	def _get_node_summary(self, *_):
		connected, pending, disconnected = self.lh_client.get_summary()

		if connected == None:
			return None
		if disconnected == 0:
			if connected == 0:
				response = 'Bored :sleeping:'
			else:
				response = 'I\'m super, thanks for asking! :smile:'
		else:
			if connected == 0:
				response = 'Time to panic :fire:'
			else:
				response = 'I\'m not so great :frowning:'

		response += '\n```' \
			'Connected:    %d\n' \
			'Disconnected: %d\n' \
			'Pending:      %d```' % (connected, disconnected, pending)

		return response

	def _get_web(self, *_):
		return '<' + self.lh_client.url + '>'

	def _get_slack_username(self, user_id):
		if user_id:
			try:
				info = self.slack_client.api_call('users.info', user=user_id)
			except:
				raise RuntimeError('Slack user info failed')
			username = info['user']['name']
			if username:
				return username
		return 'nobody'

	def _show_help(self):
		return textwrap.dedent("""
			I know how to: ```
			ssh <device>  Get you an SSH link to managed device
			web <device>  Get you an web terminal link to managed device
			con <device>  Both of the above
			sup           Show you node enrollment status
			lhweb         Get you a link to the Lighthouse web UI
			pending       Show you nodes awaiting approval
			ok <node>     Approve a node, or whitespace separated list of nodes
			nuke <node>   Delete a node, or whitespace separated list of nodes```
			""")

	def _sanitise(self, line):
		sanitised = []
		pattern = re.compile('^\<.*\|(.*)\>$')
		for s in line.strip().split():
			if pattern.search(s):
				sanitised.append(pattern.search(s).group(1))
			else:
				sanitised.append(s)
		return ' '.join(sanitised)

	def _command(self, command, channel, user_id):
		print 'Got command: ' + command

		response = self._show_help()
		intent, _, scope = command.partition(' ')
		for func, intents in self.func_intents.iteritems():
			if intent in intents:
				response = func(self._sanitise(scope), self._get_slack_username(user_id))
				break
		if not response:
			return

		print 'Responding: ' + response

		try:
			self.slack_client.api_call('chat.postMessage', channel=channel, text=response, as_user=True)
		except:
			raise RuntimeError('Slack post failed')

	def _read(self, output_list):
		if output_list and len(output_list) > 0:
			for output in output_list:
				if output and 'text' in output and self.bot_at in output['text']:
					return output['text'].split(self.bot_at)[1].strip().lower(), output['channel'], output['user']
		return None, None, None

	def poll(self):
		self.lh_client.tick(self.poll_interval)

		try:
			command, channel, user_id = self._read(self.slack_client.rtm_read())
		except:
			raise RuntimeError('Slack read failed')
		if command and channel and user_id:
			self._command(command, channel, user_id)

		if self.poll_count % 5 == 0:
			self._command('pending new_only', '#general', None)
		self.poll_count += self.poll_interval
		time.sleep(self.poll_interval)


lhbot = LighthouseBot()
while True:
	lhbot.poll()
