#!/usr/bin/env python

import os, signal, textwrap, re, time, multiprocessing, threading
import logging, logging.handlers, yaml

from oglhclient import LighthouseApiClient
from slackclient import SlackClient

class OgLhClientHelper:

    def __init__(self):
        self.lh_api = LighthouseApiClient()
        self.url = self.lh_api.url
        self.client = self.lh_api.get_client()
        self.pending_name_ids = {}
        _, _ = self.get_pending()

    def get_ports(self, label):
        """
        Return all ports along all nodes such that the port's label matches
        the :label paramater. Usage:

        >>> ports = slack_bot.get_ports('mySoughtLabel')
        """
        body = self.client.nodes.list({ 'port:label': label })
        return [port for node in body.nodes for port in node.ports \
            if port.label.lower() == label]

    def get_pending(self):
        """
        Usage:

        >>> pending_node_names, new_pending = slack_bot.get_pending()

        @pending_node_names is a list of names of the pending nodes
        @new_pending is True if there is some new pending node since the bot
            was instantiated, and False otherwise
        """
        body = self.client.nodes.list({ 'config:status' : 'Registered' })
        name_ids = { node.name: node.id for node in body.nodes \
            if node.approved == 0 }
        new_pending = (set(name_ids) > set(self.pending_name_ids))
        self.pending_name_ids = name_ids
        return sorted(name_ids, key=lambda k: k.lower()), new_pending

    def get_enrolled(self):
        """
        Usage:

        >>> enrolled_node_names = slack_bot.get_enrolled()

        @enrolled_node_names is a list of the currently enrolled nodes
        """
        body = self.client.nodes.list({ 'config:status' : 'Enrolled' })
        return sorted([node.name for node in body.nodes], key=unicode.lower)

    def get_node_id(self, node_name):
        """
        :node_name is the friendly name of the node

        Usage:

        >>> node_id = slack_bot.get_node_id('myNodeName')
        """
        body = self.client.nodes.list({ 'config:status' : 'Enrolled' })
        for node in body.nodes:
            if node.name == node_name:
                return node.id
        return None

    def get_port_labels(self, node_name):
        """
        Usage:

        >>> port_labels = slack_bot.get_port_labels('myNodeOfInterest')

        @port_labels is a list of port labels for a given node, specified by
            its name
        """
        if node_name:
            body = self.client.nodes.list({ 'config:name' : node_name })
        else:
            body = self.client.nodes.list()
            labels = [port.label for node in body.nodes for port \
                in node.ports if port.mode == 'consoleServer']
        return sorted(labels, key=unicode.lower)

    def get_summary(self):
        """
        Usage:

        >>> connected, pending, disconnected = slack_bot.get_summary()

        @connected is the number of connected nodes
        @pending is the number of pending nodes
        @disconnected is the number of disconnected nodes
        """
        body = self.client.stats.nodes.connection_summary.get()
        for conn in body.connectionSummary:
            if conn.status == 'connected':
                connected = int(conn.count)
            elif conn.status == 'pending':
                pending = int(conn.count)
                continue
            elif conn.status == 'disconnected':
                disconnected = int(conn.count)
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
        body = self.client.nodes.list()
        deleted_names = []
        errors = []
        for node in body.nodes:
            if node.name in node_names:
                try:
                    result = self.client.nodes.delete(id=node.id)
                    if 'error' in result.__dict__.keys() \
                        and len(result.error) > 0:
                        raise RuntimeError(result.error[0].text)
                    deleted_names.append(node.name)
                except Exception as e:
                    errors.append('Error deleting [%s]: %s' % (node.name, str(e)))
        return deleted_names, errors

    def approve_nodes(self, node_names):
        """
        :node_names is a list of names of nodes to be approved

        Usage:

        >>> nodes = ['myNodeName1', 'myNodeName2', 'myNodeName3']
        >>> approved_list = slack_bot.approve_nodes(nodes)
        >>> print approved_list

        @approved_list is a subset of :node_names with those which were approved
        """
        body = self.client.nodes.list({ 'config:status' : 'Registered' })
        approved_names = []
        errors = []
        for node in body.nodes:
            if node.name in node_names:
                try:
                    approved_node = {
                        'node': {
                            'name': node.name,
                            'mac_address': '',
                            'description': '',
                            'approved': 1,
                            'tags': node.tag_list.tags
                        }
                    }
                    result = self.client.nodes.update(data=approved_node, id=node.id)
                    if 'error' in result.__dict__.keys() \
                        and len(result.error) > 0:
                        raise RuntimeError(result.error[0].text)
                    approved_names.append(node.name)
                except Exception as e:
                    errors.append('Error approving [%s]: %s' % (node.name, str(e)))
        return approved_names, errors

class OgLhSlackBot:
    """
    A Bot for dealing with the Opengear Lighthouse API straight from Slack
    terminal.

    Usage:

    >>> from oglh_bot import OgLhSlackBot
    >>> slack_bot = OgLhSlackBot()
    >>> slack_bot.listen()
    """

    def __init__(self):
        self.logger = logging.getLogger('SlackBotLogger')
        self.logger.setLevel(logging.INFO)
        fh = logging.FileHandler('oglhslack_bot.log')
        fh.setLevel(logging.INFO)
        ch = logging.StreamHandler()
        ch.setLevel(logging.ERROR)
        formatter = logging.Formatter('%(asctime)s - [%(levelname)s] (%(threadName)-10s) %(message)s')
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        self.logger.addHandler(fh)
        self.logger.addHandler(ch)

        self.bot_name = os.environ.get('SLACK_BOT_NAME')
        self.default_channel = os.environ.get('SLACK_BOT_DEFAULT_CHANNEL')
        self.slack_token = os.environ.get('SLACK_BOT_TOKEN')

        if not (self.bot_name and self.default_channel and self.slack_token):
            raise RuntimeError("""
            Some of the required environment variables are not set, please refer
            to the documentation: https://github.com/thiagolcmelo/oglhslack
            """)

        self.default_log_channel = os.environ.get('SLACK_BOT_DEFAULT_LOG_CHANNEL')
        self.admin_channel = os.environ.get('SLACK_BOT_ADMIN_CHANNEL') or 'oglhadmin'

        self.slack_client = SlackClient(self.slack_token)
        self.client_helper = OgLhClientHelper()

        # the max number of threads is equals to the number of cpus
        self.poll_max_workers = multiprocessing.cpu_count()
        self.semaphores = threading.BoundedSemaphore(value=self.poll_max_workers)
        self.poll_interval = 1

        self.func_intents = { \
            self._get_port_ssh : { 'ssh', 'sshlink' }, \
            self._get_port_web : { 'web', 'webterm', 'weblink' }, \
            self._get_port : { 'con', 'console', 'gimme' }, \
            self._get_port_labels : { 'devices', 'ports', 'labels' }, \
            self._get_node_summary : { 'status', 'summary', 'stats', 'status', 'howzit' }, \
            self._get_web : { 'lighthouse', 'lhweb', 'webui', 'gui' }, \
            self._get_enrolled : { 'nodes', 'enrolled' }, \
            self._check_pending : { 'pending' }, \
            self._approve_nodes: { 'approve', 'okay', 'approve', 'admin' }, \
            self._delete_nodes: { 'delete', 'kill', 'delete', 'admin' }, \
        }

        if not self.slack_client.rtm_connect():
            raise RuntimeError('Slack connection failed')
        self.bod_id = self._get_bot_id()
        self.bot_at = '<@' + self.bod_id + '>'

    def listen(self):
        """
        Listen Slack channels for messages addressed to oglh slack bot
        """
        try:
            self._logging('Hi there! I am here to help!', force_slack=True)
            while True:
                try:
                    command, channel, user_id = self._read(self.slack_client.rtm_read())
                except NewConnectionError as nce:
                    self.slack_client = SlackClient(self.slack_token)
                    self.client_helper = OgLhClientHelper()
                except:
                    raise RuntimeError('Slack read failed, please check your token')

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
            self._dying_message(str(error))

    def _read(self, output_list):
        """
        reads slack messages in channels where the bot has access
        (PM, groups enrolled, etc)
        """
        if output_list and len(output_list) > 0:
            for output in output_list:
                if output and 'text' in output and self.bot_at in output['text']:
                    command = output['text'].split(self.bot_at)[1].strip().lower()
                    return command, output['channel'], output['user']
                elif output and 'text' in output and 'channel' in output \
                    and output['channel'][0] == 'D' and output['user'] != self.bod_id \
                    and (not 'subtype' in output or output['subtype'] != 'bot_message'):
                    return output['text'].strip().lower(), output['channel'], output['user']
        return None, None, None

    def _command(self, command, channel, user_id):
        """
        tries to execute a command received in some of the available channels
        or private messages

        it has a semaphore for assuring that no more commands are executed
        simultaneously than the number of cpus
        """
        try:
            self.semaphores.acquire()
            response = ''
            is_help = False

            username = self._get_slack_username(user_id)
            channel_name = self._get_channel_name(channel)

            self._logging(str.format('Got command: `{command}`, from: {username}', \
                command=command, username=username))
            if user_id:
                response = '<@' + user_id + '|' + username + '> '

            # check whether some of the built in funtions were called
            output = self._built_in_functions(command, channel_name, username)

            # try the more complex query tool in case of no built in function
            if not output:
                output, is_help = self._query_tool(command, channel_name)

            response += output
            self._logging('Responding: ' + (response if not is_help else 'help message'))

            try:
                self.slack_client.api_call('chat.postMessage', channel=channel, \
                    text=response, as_user=True)
            except:
                raise RuntimeError('Slack post failed')

        except Exception as e:
            self._logging(str(e), level=logging.ERROR)

        finally:
            self.semaphores.release()

    def _get_bot_id(self):
        """
        return the slack id for the bot specified at SLACK_BOT_NAME env var
        """
        try:
            users_list = self.slack_client.api_call('users.list')
        except:
            raise RuntimeError('Slack users list failed, please check your token')
        for member in users_list['members']:
            if member['name'] == self.bot_name:
                return member['id']
        raise RuntimeError('User ' + self.bot_name + ' not found')

    def _get_channel_name(self, channel_id):
        """
        returns the friendly name of a channel given its id
        """
        try:
            channel_list = self.slack_client.api_call('channels.list')
        except:
            raise RuntimeError('Slack channels list failed')
        for c in channel_list['channels']:
            if c['id'] == channel_id:
                return c['name']
        return None

    def _get_slack_username(self, user_id):
        """
        returns the friendly username of a user given its id

        if the username is not found 'friend' is returned
        """
        if user_id:
            try:
                info = self.slack_client.api_call('users.info', user=user_id)
            except:
                raise RuntimeError('Slack user info failed')
            username = info['user']['name']
            if username:
                return username
        return 'friend'

    def _built_in_functions(self, command, channel, username):
        """
        try to parse the :command as one of the built in ones, :channel is used
        for checking where the command was performed, whether in a
        public/private channel or in a private message, :username is required
        for some of the built in functions

        it also prevents from executing admin commands in not authorized channels
        """
        intent, _, scope = command.partition(' ')
        for func, intents in self.func_intents.iteritems():
            if intent in intents and (channel == self.admin_channel or not 'admin' in intents):
                return func(self._sanitise(scope), username)
            elif intent in intents and channel != self.admin_channel and 'admin' in intents:
                return "This operation must take place at `%s` channel." % self.admin_channel
        return None

    def _query_tool(self, command, channel):
        """
        tries to parse the :command as query, with a proper syntax specified
        at the documentation

        it also prevents from executing commands that make changes from
        not authorized channels
        """
        try:
            action, _, scope = re.sub('\s+', ' ', command).partition(' ')
            action = action.lower()
            scope = scope.strip()
            if action in ['update', 'set', 'delete', 'create'] and channel != self.admin_channel:
                return "Actions other than `get`, `find` and `list` " + \
                    "must take place at `%s` channel." % self.admin_channel, False
            else:
                params=[]
                chain = []
                main_parts = []

                if 'from' in scope:
                    objects = scope.split('from')
                    main_parts = objects[0].strip().split(' ')
                    parent_parts = objects[1].strip().split(' ')
                    chain.append(self._dummy_plural(parent_parts[0]))
                    if len(parent_parts) == 2:
                        params.append('parent_id="%s"' % parent_parts[1])
                else:
                    main_parts = scope.strip().split(' ')

                chain.append(self._dummy_plural(main_parts[0]) if action != 'get' else main_parts[0])
                if len(main_parts) == 2:
                    params.append('id="%s"' % main_parts[1])

                call_str = 'self.client_helper.client.{chain}.{action}({params})'
                r = eval(str.format(call_str, chain='.'.join(chain), \
                    action=action, params=','.join(params)))
                return self._format_response(action, r), False
        except:
            return self._show_help(), True

    # built in functions

    def _ports_list_ssh(self, ports, label, username):
        ssh_urls = []
        for port in ports:
            if not 'proxied_ssh_url' in port:
                continue
            ssh_url = re.sub(r'ssh://lhbot', 'ssh://' + username, port.proxied_ssh_url)
            ssh_urls.append('<' + ssh_url + '>')
        return ssh_urls

    def _ports_list_web(self, ports, label):
        web_urls = []
        for port in ports:
            if not 'web_terminal_url' in port:
                continue
            web_url = self.client_helper.url + '/'
            web_url += port.web_terminal_url
            web_urls.append('<' + web_url + '>')
        return web_urls

    def _get_port_ssh(self, label, username):
        ports = self.client_helper.get_ports(label)
        urls = self._ports_list_ssh(ports, label, username)
        if not urls:
            return ':x: Problem to create ssh link'
        return '\n'.join(urls)

    def _get_port_web(self, label, *_):
        ports = self.client_helper.get_ports(label)
        urls = self._ports_list_web(ports, label)

        if not urls:
            return ':x: Problem to create web link.'
        return '\n'.join(urls)

    def _get_port(self, label, username):
        ports = self.client_helper.get_ports(label)
        ssh_urls = self._ports_list_ssh(ports, label, username)
        web_urls = self._ports_list_web(ports, label)

        urls = [ x for t in zip(ssh_urls, web_urls) for x in t ]
        if not urls:
            return ':x: Device not found. Unable to create ssh link and web link.'
        return '\n'.join(urls)

    def _approve_nodes(self, str_names, *_):
        names = str_names.split(' ')
        approved_names, errors = self.client_helper.approve_nodes(names)
        for e in errors:
            self._logging(e, level=logging.ERROR)
        response = []
        for name in names:
            if name in approved_names:
                emoji = ':white_check_mark: Success: Node approved.'
            else:
                emoji = ':x: Error: Node could not be approved. Please check it and try again.'
            response.append(name + ' ' + emoji)
        return self._format_list(response)

    def _delete_nodes(self, str_names, *_):
        names = str_names.split(' ')
        deleted_names, errors = self.client_helper.delete_nodes(names)
        for e in errors:
            self._logging(e, level=logging.ERROR)
        response = []
        for name in names:
            if name in deleted_names:
                status_info = ':white_check_mark: Success: '
            else:
                status_info = ':x: Error: It was not possible to unenroll '
            response.append(status_info + name + '.')
        return self._format_list(response)

    def _get_port_labels(self, node_name, *_):
        labels = self.client_helper.get_port_labels(node_name)
        if labels:
            response = self._format_list(labels)
        else:
            response = 'Nothing to see here'
        return response

    def _get_enrolled(self, *_):
        try:
            enrolled_nodes = self.client_helper.get_enrolled()
        except Exception as e:
            self._logging('erro buscando nos: '+str(e))

        if enrolled_nodes:
            response = self._format_list(enrolled_nodes)
        else:
            response = 'No created node.'
        return response

    def _check_pending(self, new_only, *_):
        pending_nodes, new_pending = self.client_helper.get_pending()

        if not new_pending and new_only:
            return None

        if pending_nodes:
            response = ':warning: There are some nodes waiting for approval.\n'
            response += self._format_list(pending_nodes)
        else:
            response = ':white_check_mark: No pending nodes to approve.'
        return response

    def _get_node_summary(self, *_):
        connected, pending, disconnected = self.client_helper.get_summary()

        if connected == None:
            return None

        response = 'Nodes\' status information:\n' \
            '> Connected: %d\n' \
            '> Disconnected: %d\n' \
            '> Pending: %d' % (connected, disconnected, pending)

        return response

    def _get_web(self, *args):
        if args[0]:
            node_id = self.client_helper.get_node_id(args[0]) or args[0]
            return '<' + self.client_helper.url + '/' + node_id + '>'
        return '<' + self.client_helper.url + '>'

    # formatting functions

    def _sanitise(self, line):
        sanitised = []
        pattern = re.compile('^\<.*\|(.*)\>$')
        for s in line.strip().split():
            if pattern.search(s):
                sanitised.append(pattern.search(s).group(1))
            else:
                sanitised.append(s)
        return ' '.join(sanitised)

    def _dummy_plural(self, word):
        """
        it is a very simple tool for get plural names according to those used
        by the api, it is just a matter of making it easier for the user when
        guessing about query syntax
        """
        if word == 'system':
            return word
        if word[-1] == 'y':
            return word[:-1] + 'ies'
        elif word[-1] == 's':
            return word
        return word + 's'

    def _format_response(self, action, resp):
        """
        formats the message according to the action

        for 'list', minimal information is shown, mosly a list of names and/or
        ids

        for 'find' or 'get' returns a structured view of the objects properties
        """
        try:
            if 'error' in resp.__dict__.keys() and resp.error[0].text == 'Permission denied':
                return 'Object does not exist (please check the id) or @%s is not allowed to fetch it.' % self.bot_name

            if action == 'list':
                object_name = [k for k in resp.__dict__.keys() if k != 'meta'][0]
                object_label = ''

                if 'name' in resp.__dict__[object_name][0].__dict__:
                    object_label = 'name'
                if 'label' in resp.__dict__[object_name][0].__dict__:
                    object_label = 'label'

                if object_label == '':
                    return textwrap.dedent("""
                        ```
                        """ + self._dump_obj(resp) + """
                        ```""")

                try:
                    names = [o.__dict__[object_label] + ' (id: ' + o.__dict__['id'] + ')' for o in resp.__dict__[object_name]]
                except:
                    names = [o.__dict__[object_label] for o in resp.__dict__[object_name]]

                return self._format_list(sorted(names), object_name)
            elif action == 'find' or 'get':
                return textwrap.dedent("""
                    ```
                    """ + self._dump_obj(resp) + """
                    ```""")
        except:
            return str(resp)

    def _format_list(self, raw_list, list_title=''):
        """
        format an array of strings according to its length.
        until 10 items, a simple list is returned
        more than 10 items are printed in columns
        """
        if len(raw_list) <= 10:
            #return '\n' + '\n'.join(['> %d. %s' % (i + 1, e) for i, e in enumerate(raw_list)])
            return '\n' + '\n'.join(raw_list)
        max_len = max([len(l) for l in raw_list])
        cols = int (120 / max_len)
        formated_list = ''
        for i, word in enumerate(raw_list):
            if i % cols == 0:
                formated_list += '\n'
            #formated_list += ('{:3d}. {:' + str(max_len) + 's} ').format((i+1), word)
            formated_list += ('{:' + str(max_len) + 's} ').format(word)
        return textwrap.dedent((list_title + ':' if list_title else '') + """
            ```
            """ + formated_list + """
            ```
            """)

    def _dump_obj(self, obj, level=0):
        """
        tries to dump an object in a easy to read description of its properties
        """
        response = ''
        for key, value in obj.__dict__.items():
            try:
                if isinstance(value, list):
                    response += ('\n%s:' % (" " * level + key)) + self._dump_obj(value[0], level + 2)
                else:
                    response += ('\n%s:' % (" " * level + key)) + self._dump_obj(value, level + 2)
            except Exception as e:
                response += '\n' + " " * level + "%s -> %s" % (key, value)
        return response

    def _dying_message(self, message):
        """
        it is final message for the default slack channel and for the log
        file, in case of issues posting to slack, only the log file part
        will work
        """
        self._logging(message, level=logging.ERROR)
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
        try:
            if level == logging.CRITICAL:
                self.logger.critical(message)
            elif level == logging.ERROR:
                self.logger.error(message)
            elif level == logging.WARNING:
                self.logger.warning(message)
            else:
                self.logger.info(message[0:100] + ('...' if len(message) > 100 else ''))

            if self.default_log_channel and self.slack_client \
                and (self.default_log_channel != self.default_channel \
                or level > logging.INFO or force_slack):
                slack_message = message
                if level > logging.INFO:
                    slack_message = textwrap.dedent("""
                        @""" + self.bot_name + """  would like you to know:

                        > """ + message + """

                        """)
                self.slack_client.api_call('chat.postMessage', \
                    channel=self.default_log_channel, text=slack_message, as_user=True)
        except:
            self.logger.error('Error logging: \n' + message)

    def _show_help(self, *_):
        """
        returns a text with instructions about the commands syntax
        """
        build_in_commands = [
            {
                'command': 'devices',
                'description': 'Shows all the managed devices available',
                'alias': 'ports, labels'
            },
            {
                'command': 'ssh <device>',
                'description': 'Gets a SSH link for managed Device',
                'alias': 'sshlink <device>'
            },
            {
                'command': 'web <device>',
                'description': 'Gets a web terminal link for managed device',
                'alias': 'webterm <device>, weblink <device>'
            },
            {
                'command': 'con <device>',
                'description': 'Gets both a SSH link and a web terminal link for managed device',
                'alias': ''
            },
            {
                'command': 'status',
                'description': 'Shows nodes enrollment summary',
                'alias': 'console <device>, gimme <device>'
            },
            {
                'command': 'gui',
                'description': 'Gets a link to the Lighthouse web UI',
                'alias': 'lighthouse, lhweb, webui'
            },
            {
                'command': 'gui <node>',
                'description': 'Gets a link to the node\'s proxied web UI',
                'alias': ''
            },
            {
                'command': 'nodes',
                'description': 'Shows enrolled nodes',
                'alias': 'summary, stats, status, howzit'
            },
            {
                'command': 'pending',
                'description': 'Shows nodes awaiting approval',
                'alias': 'enrolled'
            },
            {
                'command': 'approve <node>',
                'description': 'Approves a node or a whitespace separated list of nodes (admin only)',
                'alias': 'okay <node>, approve <node>'
            },
            {
                'command': 'delete <node>',
                'description': 'Unenrolls a node or a whitespace separated list of nodes (admin only)',
                'alias': 'kill <node>, delete <node>'
            }
        ]

        max_command = max([len(c['command']) for c in build_in_commands])
        max_desc = max([len(c['description']) for c in build_in_commands])
        max_alias = max([len(c['alias']) for c in build_in_commands])
        #head_str = '\n%s {:%ds} | {:%ds} | {:%ds}' % (' ' * (len(self.bot_name) + 1), max_command, max_desc, max_alias)
        #line_str = '\n@%s {:%ds} | {:%ds} | {:%ds}' % (self.bot_name, max_command, max_desc, max_alias)
        head_str = '\n%s {:%ds} | {:%ds}' % (' ' * (len(self.bot_name) + 1), max_command, max_desc)
        line_str = '\n@%s {:%ds} | {:%ds}' % (self.bot_name, max_command, max_desc)
        help_text = head_str.format('Commands', 'Description')

        for c in build_in_commands:
            help_text += line_str.format(c['command'], c['description'])

        return textwrap.dedent("""
```""" + help_text + """
```

It is also possible to query objects like:
```
@""" + self.bot_name + """ list nodes
@""" + self.bot_name + """ find node my-node-id
@""" + self.bot_name + """ list tags from node my-node-id
```

Generically:
```
@""" + self.bot_name + """ get <static-object>
@""" + self.bot_name + """ list <objects>
@""" + self.bot_name + """ find <object> <object-id>

@""" + self.bot_name + """ get <static-object> from <parent-object> <parent-object-id>
@""" + self.bot_name + """ list <objects> from <parent-object> <parent-object-id>
@""" + self.bot_name + """ find <object> <object-id> from <parent-object> <parent-object-id>
```

For a complete reference, please refer to https://github.com/thiagolcmelo/oglhslack
            """)

if __name__ == '__main__':
    while True:
        try:
            slack_bot = OgLhSlackBot()
            slack_bot.listen()
        except NewConnectionError as nce:
            pass
