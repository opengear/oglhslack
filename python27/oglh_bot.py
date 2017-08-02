#!/usr/bin/env python

import os, signal, textwrap, re, time, multiprocessing, threading, logging
from oglh_client import LighthouseApi
from slackclient import SlackClient
from functools import wraps

def retry(ExceptionToCheck, tries=4, delay=3, backoff=2, logger=None):
    def deco_retry(f):
        @wraps(f)
        def f_retry(*args, **kwargs):
            mtries, mdelay = tries, delay
            while mtries > 1:
                try:
                    return f(*args, **kwargs)
                except ExceptionToCheck, e:
                    msg = "%s, Retrying in %d seconds..." % (str(e), mdelay)
                    if logger:
                        logger.warning(msg)
                    else:
                        print msg
                    time.sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
            return f(*args, **kwargs)
        return f_retry
    return deco_retry

class OgLhSlackBot:
    """
    Provides a minimum use of the LighthouseApi with methods that return
    parsed responses rather than the actual JSON responses so that

    Although the list() method keeps listening for request from the Slack and
    makes possible to access all other features throught there, most of them
    can be called directly from:

    >>> from oglh_bot import OgLhSlackBot
    >>> slack_bot = OgLhSlackBot()
    """

    def __init__(self):
        self.bot_name = os.environ.get('SLACK_BOT_NAME')
        self.default_channel = os.environ.get('SLACK_BOT_DEFAULT_CHANNEL')
        self.default_log_channel = os.environ.get('SLACK_BOT_DEFAULT_LOG_CHANNEL')
        self.slack_token = os.environ.get('SLACK_BOT_TOKEN')
        self.slack_client = SlackClient(self.slack_token)

        self.lh_api = LighthouseApi()
        self.lh_client = self.lh_api.get_client()

        self.poll_max_workers = multiprocessing.cpu_count()
        self.semaphores = threading.BoundedSemaphore(value=self.poll_max_workers)

        self.poll_interval = 1

        self.func_intents = { \
            self._get_port_ssh : { 'ssh', 'sshlink' }, \
            self._get_port_web : { 'web', 'webterm', 'weblink' }, \
            self._get_port : { 'con', 'console', 'gimme' }, \
            self._get_port_labels : { 'devices', 'ports', 'labels' }, \
            self._get_node_summary : { 'sup', 'summary', 'stats', 'status', 'howzit' }, \
            self._get_web : { 'lighthouse', 'lhweb', 'webui', 'gui' }, \
            self._get_enrolled : { 'nodes', 'enrolled' }, \
            self._check_pending : { 'pending' }, \
            self._approve_nodes: { 'ok', 'okay', 'approve' }, \
            self._delete_nodes: { 'nuke', 'kill', 'delete' }, \
        }

        if not self.slack_client.rtm_connect():
            raise RuntimeError('Slack connection failed')
        self.bot_at = '<@' + self._get_bot_id() + '>'
        self.pending_name_ids = {}
        _, _ = self.get_pending()

    # Slack Bot methods
    ## Methods for dealing with Slack Bot

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
            web_url = self.lh_api.url + '/'
            web_url += port['web_terminal_url']
            web_urls.append('<' + web_url + '>')
        return web_urls

    def _get_port_ssh(self, label, username):
        ports = self.get_ports(label)
        urls = self._ports_list_ssh(ports, label, username)
        if not urls:
            return ':thumbsdown:'
        return '\n'.join(urls)

    def _get_port_web(self, label, *_):
        ports = self.get_ports(label)
        urls = self._ports_list_web(ports, label)

        if not urls:
            return ':thumbsdown:'
        return '\n'.join(urls)

    def _get_port(self, label, username):
        ports = self.get_ports(label)
        ssh_urls = self._ports_list_ssh(ports, label, username)
        web_urls = self._ports_list_web(ports, label)

        urls = [ x for t in zip(ssh_urls, web_urls) for x in t ]
        if not urls:
            return 'I can\'t seem to find that one :thumbsdown:'
        return '\n'.join(urls)

    def _approve_nodes(self, str_names, *_):
        names = str_names.split(' ')
        approved_names = self.approve_nodes(names)
        response = []
        for name in names:
            if name in approved_names:
                emoji = 'approved :thumbsup:'
            else:
                emoji = 'failed :thumbsdown:'
            response.append(name + ' ' + emoji)
        return self._format_list(response)

    def _delete_nodes(self, str_names, *_):
        names = str_names.split(' ')
        deleted_names = self.delete_nodes(names)
        response = []
        for name in names:
            if name in deleted_names:
                emoji = 'unenrolled :boom:'
            else:
                emoji = 'failed :thumbsdown:'
            response.append(name + ' ' + emoji)
        return self._format_list(response)

    def _get_port_labels(self, node_name, *_):
        labels = self.get_port_labels(node_name)
        if labels:
            response = self._format_list(labels)
        else:
            response = 'Nothing to see here'
        return response

    def _get_enrolled(self, *_):
        enrolled_nodes = self.get_enrolled()

        if enrolled_nodes:
            response = self._format_list(enrolled_nodes)
        else:
            response = 'Nothing to see here'
        return response

    def _check_pending(self, new_only, *_):
        pending_nodes, new_pending = self.get_pending()

        if not new_pending and new_only:
            return None

        if pending_nodes:
            response = 'Nodes await your approval!\n'
            response += self._format_list(pending_nodes)
        else:
            response = 'Nothing pending, as you were'
        return response

    def _get_node_summary(self, *_):
        connected, pending, disconnected = self.get_summary()

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
        return '<' + self.lh_api.url + '>'

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

    def _format_list(self, raw_list):
        return '\n' + '\n'.join(['> %d. %s' % (i + 1, e) for i, e in enumerate(raw_list)])

    def _show_help(self):
        return textwrap.dedent("""
            ```
            @""" + self.bot_name + """ devices       Show you all the managed devices I've got
            @""" + self.bot_name + """ ssh <device>  Get you an SSH link to managed device
            @""" + self.bot_name + """ web <device>  Get you an web terminal link to managed device
            @""" + self.bot_name + """ con <device>  Both of the above
            @""" + self.bot_name + """ sup           Show you node enrollment summary
            @""" + self.bot_name + """ gui           Get you a link to the Lighthouse web UI
            @""" + self.bot_name + """ nodes         Show you nodes I've got enrolled
            @""" + self.bot_name + """ pending       Show you nodes awaiting your approval
            @""" + self.bot_name + """ ok <node>     Approve a node, or whitespace separated list of nodes
            @""" + self.bot_name + """ nuke <node>   Unenroll a node, or whitespace separated list of nodes
            ```
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
        try:
            self.semaphores.acquire()

            response = ''
            username = self._get_slack_username(user_id)

            self._logging('Got command: `' + command + '`, from: ' + username + '')

            if user_id:
                response = '<@' + user_id + '|' + username + '> '

            output = self._show_help()
            intent, _, scope = command.partition(' ')

            for func, intents in self.func_intents.iteritems():
                if intent in intents:
                    output = func(self._sanitise(scope), username)
                    break

            if not output:
                return

            response = response + output
            self._logging('Responding: ' + response)

            try:
                self.slack_client.api_call('chat.postMessage', channel=channel, \
                    text=response, as_user=True)
            except:
                raise RuntimeError('Slack post failed')
        except Exception as e:
            self._logging(str(e), level=logging.ERROR)
        finally:
            self.semaphores.release()


    def _read(self, output_list):
        if output_list and len(output_list) > 0:
            for output in output_list:
                if output and 'text' in output and self.bot_at in output['text']:
                    return output['text'].split(self.bot_at)[1].strip().lower(), output['channel'], output['user']
        return None, None, None

    def _warning_message(self, message):
        warning_message = textwrap.dedent("""
            @""" + self.bot_name + """  went offline with error message:
            ```
            """ + message + """
            ```
            """)
        self.slack_client = SlackClient(self.slack_token)
        self.slack_client.api_call('chat.postMessage', \
            channel=self.default_channel, text=warning_message, as_user=True)

    def _logging(self, message, level=logging.INFO, force_slack=False):
        """
        it will log to slack only if there is a specified slack channel for logs
        or if the level is not a simple logging.INFO
        """

        if self.default_log_channel and self.slack_client \
            and (self.default_log_channel != self.default_channel \
            or level > logging.INFO or force_slack):
            slack_message = message
            if level > logging.INFO:
                slack_message = textwrap.dedent("""
                    @""" + self.bot_name + """  would like you to know:
                    ```
                    """ + message + """
                    ```
                    """)
            self.slack_client.api_call('chat.postMessage', \
                channel=self.default_log_channel, text=slack_message, as_user=True)

        if level == logging.CRITICAL:
            logging.critical(message)
        elif level == logging.ERROR:
            logging.error(message)
        elif level == logging.WARNING:
            logging.warning(message)
        else:
            logging.info(message)

    def listen(self):
        try:
            while True:
                try:
                    command, channel, user_id = self._read(self.slack_client.rtm_read())
                except:
                    raise RuntimeError('Slack read failed')

                if command and channel and user_id:
                    t = threading.Thread(target=self._command, \
                        args=(command, channel, user_id))
                    t.setDaemon(True)
                    t.start()

                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            self._logging('Slack bot was interrupt manually', level=logging.WARNING)
            os.kill(os.getpid(), signal.SIGUSR1)
        except Exception as error:
            self._warning_message(str(error))

    # Lighthouse API methods
    ## the following methods are those used to interact with the Lighthouse API

    def get_ports(self, label):
        """
        Return all ports along all nodes such that the port's label matches
        the :label paramater. Usage:

        >>> ports = slack_bot.get_ports('mySoughtLabel')
        """
        body = self.lh_client.nodes.list({ 'port:label': label })
        return [port for node in body['nodes'] for port in node['ports'] \
            if port['label'].lower() == label]

    def get_pending(self):
        """
        Usage:

        >>> pending_node_names, new_pending = slack_bot.get_pending()

        @pending_node_names is a list of names of the pending nodes
        @new_pending is True if there is some new pending node since the bot
            was instantiated, and False otherwise
        """
        body = self.lh_client.nodes.list({ 'config:status' : 'Registered' })
        name_ids = { node['name']: node['id'] for node in body['nodes'] \
            if node['approved'] == 0 }
        new_pending = (set(name_ids) > set(self.pending_name_ids))
        self.pending_name_ids = name_ids
        return sorted(name_ids, key=lambda k: k.lower()), new_pending

    def get_enrolled(self):
        """
        Usage:

        >>> enrolled_node_names = slack_bot.get_enrolled()

        @enrolled_node_names is a list of the currently enrolled nodes
        """
        body = self.lh_client.nodes.list({ 'config:status' : 'Enrolled' })
        return sorted([node['name'] for node in body['nodes']], key=unicode.lower)

    def get_port_labels(self, node_name):
        """
        Usage:

        >>> port_labels = slack_bot.get_port_labels('myNodeOfInterest')

        @port_labels is a list of port labels for a given node, specified by
            its name
        """
        if node_name:
            body = self.lh_client.nodes.list({ 'config:name' : node_name })
        else:
            body = self.lh_client.nodes.list()
            labels = [port['label'] for node in body['nodes'] for port \
                in node['ports'] if port['mode'] == 'consoleServer']
        return sorted(labels, key=unicode.lower)

    def get_summary(self):
        """
        Usage:

        >>> connected, pending, disconnected = slack_bot.get_summary()

        @connected is the number of connected nodes
        @pending is the number of pending nodes
        @disconnected is the number of disconnected nodes
        """
        body = self.lh_client.stats.nodes.connection_summary.get()
        for conn in body['connectionSummary']:
            if conn['status'] == 'connected':
                connected = int(conn['count'])
            elif conn['status'] == 'pending':
                pending = int(conn['count'])
                continue
            elif conn['status'] == 'disconnected':
                disconnected = int(conn['count'])
        return connected, pending, disconnected

    def delete_nodes(self, node_names):
        """
        :node_names is a list of names of nodes to be deleted

        Usage:

        >>> nodes = ['myNodeName1', 'myNodeName2', 'myNodeName3']
        >>> deleted_list = slack_bot.delete_nodes(nodes)
        >>> print deleted_list

        @deleted_list is a subset of :node_names with those which were deleted
        """
        body = self.lh_client.nodes.list()
        deleted_names = []
        for node in body['nodes']:
            if node['name'] in node_names:
                try:
                    result = self.lh_client.nodes.delete(id=node['id'])
                    if type(result) is dict and 'error' in result \
                        and len(result['error']) > 0:
                        raise RuntimeError(result['error'][0]['text'])
                    deleted_names.append(node['name'])
                except Exception as e:
                    self._logging(str(e), level=logging.ERROR)
        return deleted_names

    def approve_nodes(self, node_names):
        """
        :node_names is a list of names of nodes to be approved

        Usage:

        >>> nodes = ['myNodeName1', 'myNodeName2', 'myNodeName3']
        >>> approved_list = slack_bot.approve_nodes(nodes)
        >>> print approved_list

        @approved_list is a subset of :node_names with those which were approved
        """
        body = self.lh_client.nodes.list({ 'config:status' : 'Registered' })
        approved_names = []
        for node in body['nodes']:
            if node['name'] in node_names:
                try:
                    approved_node = {
                        'node': {
                            'name': node['name'],
                            'mac_address': '',
                            'description': '',
                            'approved': 1,
                            'tags': node['tag_list']['tags']
                        }
                    }
                    result = self.lh_client.nodes.update(data=approved_node, id=node['id'])
                    if type(result) is dict and 'error' in result \
                        and len(result['error']) > 0:
                        raise RuntimeError(result['error'][0]['text'])
                    approved_names.append(node['name'])
                except Exception as e:
                    self._logging(str(e), level=logging.ERROR)
        return approved_names

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, filename='oglh_slack_bot.log',
        format='%(asctime)s - [%(levelname)s] (%(threadName)-10s) %(message)s')
    slack_bot = OgLhSlackBot()
    slack_bot.listen()
