#!/usr/bin/env python

import os, signal, textwrap, re, time, multiprocessing, threading
import logging, logging.handlers, yaml

from oglhclient import LighthouseApiClient
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

class OgLhClient:

    def __init__(self):
        self.lh_api = LighthouseApiClient()
        self.url = self.lh_api.url
        self.lh_client = self.lh_api.get_client()
        self.pending_name_ids = {}
        _, _ = self.get_pending()

    def get_ports(self, label):
        """
        Return all ports along all nodes such that the port's label matches
        the :label paramater. Usage:

        >>> ports = slack_bot.get_ports('mySoughtLabel')
        """
        body = self.lh_client.nodes.list({ 'port:label': label })
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

        body = self.lh_client.nodes.list({ 'config:status' : 'Registered' })

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
        body = self.lh_client.nodes.list({ 'config:status' : 'Enrolled' })
        return sorted([node.name for node in body.nodes], key=unicode.lower)

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
        body = self.lh_client.stats.nodes.connection_summary.get()
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
        body = self.lh_client.nodes.list()
        deleted_names = []
        errors = []
        for node in body.nodes:
            if node.name in node_names:
                try:
                    result = self.lh_client.nodes.delete(id=node.id)
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
        body = self.lh_client.nodes.list({ 'config:status' : 'Registered' })
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
                    result = self.lh_client.nodes.update(data=approved_node, id=node.id)
                    if 'error' in result.__dict__.keys() \
                        and len(result.error) > 0:
                        raise RuntimeError(result.error[0].text)
                    approved_names.append(node.name)
                except Exception as e:
                    errors.append('Error approving [%s]: %s' % (node.name, str(e)))
        return approved_names, errors

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

        # create logger with 'spam_application'
        self.logger = logging.getLogger('SlackBotLogger')
        self.logger.setLevel(logging.INFO)
        fh = logging.FileHandler('oglh_slack_bot.log')
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
        self.default_log_channel = os.environ.get('SLACK_BOT_DEFAULT_LOG_CHANNEL')
        self.slack_token = os.environ.get('SLACK_BOT_TOKEN')
        self.slack_client = SlackClient(self.slack_token)

        self.poll_max_workers = multiprocessing.cpu_count()
        self.semaphores = threading.BoundedSemaphore(value=self.poll_max_workers)

        self.lh_client = OgLhClient()

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
            ssh_url = re.sub(r'ssh://lhbot', 'ssh://' + username, port.proxied_ssh_url)
            ssh_urls.append('<' + ssh_url + '>')
        return ssh_urls

    def _ports_list_web(self, ports, label):
        web_urls = []
        for port in ports:
            if not 'web_terminal_url' in port:
                continue
            web_url = self.lh_client.url + '/'
            web_url += port.web_terminal_url
            web_urls.append('<' + web_url + '>')
        return web_urls

    def _get_port_ssh(self, label, username):
        ports = self.lh_client.get_ports(label)
        urls = self._ports_list_ssh(ports, label, username)
        if not urls:
            return ':x: Problem to create ssh link'
        return '\n'.join(urls)

    def _get_port_web(self, label, *_):
        ports = self.lh_client.get_ports(label)
        urls = self._ports_list_web(ports, label)

        if not urls:
            return ':x: Problem to create web link.'
        return '\n'.join(urls)

    def _get_port(self, label, username):
        ports = self.lh_client.get_ports(label)
        ssh_urls = self._ports_list_ssh(ports, label, username)
        web_urls = self._ports_list_web(ports, label)

        urls = [ x for t in zip(ssh_urls, web_urls) for x in t ]
        if not urls:
            return ':x: Device not found. Unable to create ssh link and web link.'
        return '\n'.join(urls)

    def _approve_nodes(self, str_names, *_):
        names = str_names.split(' ')
        approved_names, errors = self.lh_client.approve_nodes(names)
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
        deleted_names, errors = self.lh_client.delete_nodes(names)
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
        labels = self.lh_client.get_port_labels(node_name)
        if labels:
            response = self._format_list(labels)
        else:
            response = 'Nothing to see here'
        return response

    def _get_enrolled(self, *_):
        try:
            enrolled_nodes = self.lh_client.get_enrolled()
        except Exception as e:
            self._logging('erro buscando nos: '+str(e))

        if enrolled_nodes:
            response = self._format_list(enrolled_nodes)
        else:
            response = 'No created node.'
        return response

    def _check_pending(self, new_only, *_):
        pending_nodes, new_pending = self.lh_client.get_pending()

        if not new_pending and new_only:
            return None

        if pending_nodes:
            response = ':warning: There are some nodes waiting for approval.\n'
            response += self._format_list(pending_nodes)
        else:
            response = ':white_check_mark: No pending node to approve.'
        return response

    def _get_node_summary(self, *_):
        connected, pending, disconnected = self.lh_client.get_summary()

        if connected == None:
            return None

        response = 'Nodes\' status information:\n' \
            '> Connected: %d\n' \
            '> Disconnected: %d\n' \
            '> Pending: %d' % (connected, disconnected, pending)

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

    def _format_list(self, raw_list):
        return '\n' + '\n'.join(['> %d. %s' % (i + 1, e) for i, e in enumerate(raw_list)])

    def _show_help(self):
        return textwrap.dedent("""
            ```
            Commands                                 Description                                                            Alias
            @""" + self.bot_name + """ devices       Shows all the manageable devices available                                 ports, labels
            @""" + self.bot_name + """ ssh <device>  Gets a SSH link for manageable Device                                      sshlink <device>
            @""" + self.bot_name + """ web <device>  Gets a web terminal link for manageable device                             webterm <device>, weblink <device>
            @""" + self.bot_name + """ con <device>  Gets both a SSH link and a web terminal link for manageable device         console <device>, gimme <device>
            @""" + self.bot_name + """ sup           Shows nodes enrollment summary                                             summary, stats, status, howzit
            @""" + self.bot_name + """ gui           Gets a link to the Lighthouse web UI                                       lighthouse, lhweb, webui
            @""" + self.bot_name + """ nodes         Shows enrolled nodes                                                       enrolled
            @""" + self.bot_name + """ pending       Shows nodes awaiting approval
            @""" + self.bot_name + """ ok <node>     Approves a node or a whitespace separated list of nodes                    okay <node>, approve <node>
            @""" + self.bot_name + """ nuke <node>   Unenrolls a node or a whitespace separated list of nodes                   kill <node>, delete <node>
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

    def _simple_plural(self, word):
        if word[-1] == 'y':
            return word[:-1] + 'ies'
        elif word[-1] == 's':
            return word
        return word + 's'

    def _format_response(self, action, resp):

        return yaml.dump(resp, default_flow_style=False)

    def _command(self, command, channel, user_id):
        try:
            self.semaphores.acquire()

            response = ''
            username = self._get_slack_username(user_id)
            self._logging('Got command: `' + command + '`, from: ' + username + '')
            if user_id:
                response = '<@' + user_id + '|' + username + '> '

            output = None

            intent, _, scope = command.partition(' ')

            for func, intents in self.func_intents.iteritems():
                if intent in intents:
                    output = func(self._sanitise(scope), username)
                    break

            if not output:
                action, _, scope = re.sub('\s+', ' ', command).partition(' ')
                action = action.lower()
                scope = scope.strip()

                if not action in ['get', 'find', 'list'] and channel != 'oglhadmin':
                    output = "Actions other than `get`, `find` and `list` must take place in `oglhadmin` channel."
                else:
                    params=[]
                    chain = []
                    main_parts = []

                    if 'from' in scope:
                        objects = scope.split('from')
                        main_parts = objects[0].strip().split(' ')
                        parent_parts = objects[1].strip().split(' ')
                        chain.append(self._simple_plural(parent_parts[0]))
                        if len(parent_parts) == 2:
                            params.append('parent_id=' + parent_parts[1])
                    else:
                        main_parts = scope.strip().split(' ')

                    chain.append(self._simple_plural(main_parts[0]))
                    if len(main_parts) == 2:
                        params.append(main_parts[1])

                    call_str = 'self.lh_client.lh_client.{chain}.{action}({params})'
                    r = eval(str.format(call_str, chain='.'.join(chain), \
                        action=action, params=','.join(params)))

                    output = self._format_response(action, r)
            #else:
            #    output = self._show_help()

            if not output:
                output = self._show_help()
                #return

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

    def _dying_message(self, message):
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

                    > """ + message + """

                    """)
            self.slack_client.api_call('chat.postMessage', \
                channel=self.default_log_channel, text=slack_message, as_user=True)

        if level == logging.CRITICAL:
            self.logger.critical(message)
        elif level == logging.ERROR:
            self.logger.error(message)
        elif level == logging.WARNING:
            self.logger.warning(message)
        else:
            self.logger.info(message)

    def listen(self):
        try:
            self._logging('Hi there! I am here to help!', force_slack=True)
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
            self._dying_message(str(error))

if __name__ == '__main__':
    slack_bot = OgLhSlackBot()
    slack_bot.listen()
