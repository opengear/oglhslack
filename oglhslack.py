#!/usr/bin/env python

import os, signal, textwrap, re, time, multiprocessing, threading
import logging, logging.handlers, yaml

from datetime import datetime, timedelta
from functools import wraps, partial
from future.standard_library import install_aliases

from oglhclient import LighthouseApiClient
from slackclient import SlackClient

install_aliases()

class LighhouseError(Exception):
    pass

class OgLhClientHelper:

    def __init__(self):
        self.lh_api = LighthouseApiClient()
        self.url = self.lh_api.url
        self.client = self.lh_api.get_client()
        self.pending_name_ids = {}
        _, _ = self.get_pending()

    def get_smart_groups(self):
        """returns a list of smartgroups"""
        try:
            body = self.client.nodes.smartgroups.list()
            if 'error' in body._asdict():
                raise LighhouseError('Lighthouse says: %s' % error[0].text)
            return sorted([s.name for s in body.smartgroups])
        except LighhouseError as error:
            raise error
        except:
            return None
        
    def get_smart_group_nodes(self, smartgroup):
        """returns a list of nodes belonging to a smartgroup
        
        :smartgroup is the smartgroup name
        """
        try:
            query = self.get_smart_group_query(smartgroup)
            body = self.client.nodes.list(json=query)
            if 'error' in body._asdict():
                raise LighhouseError('Lighthouse says: %s' % error[0].text)
            nodes = body.nodes
            node_names = [n.name for n in nodes]
            return sorted(node_names, key=lambda k: k.lower())
        except LighhouseError as error:
            raise error
        except:
            return None
            
    def get_smart_group_query(self, smartgroup):
        """returns the query a smartgroup specified by its name
        
        :smartgroup is the name of the smart group
        """
        if not smartgroup:
            return ''
        try:
            body = self.client.nodes.smartgroups.list()
            if 'error' in body._asdict():
                raise LighhouseError('Lighthouse says: %s' % error[0].text)
                
            for s in body.smartgroups:
                if s.name.lower() == smartgroup.lower():
                    return s.query
        except LighhouseError as error:
            raise error
        except:
            return ''

    def get_ports(self, label, smartgroup=None):
        """Return all ports along all nodes such that the port's label matches
        the :label paramater. 
        
        :label a port label
        :smartgroup if specified, objects will be filtered by smargroup query
        
        Usage:

        >>> ports = slack_bot.get_ports('mySoughtLabel')
        """
        query = self.get_smart_group_query(smartgroup)
        body = self.client.nodes.list({ 'port:label': label }, json=query)
        if 'error' in body._asdict():
            raise LighhouseError('Lighthouse says: %s' % error[0].text)
                
        return [port for node in body.nodes for port in node.ports \
            if port.label.lower() == label.lower()]

    def get_pending(self, smartgroup=None):
        """a list of names of the pending nodes (waiting for approval)
        
        :smartgroup if specified, objects will be filtered by smargroup query
        
        Usage:

        >>> pending_node_names, new_pending = slack_bot.get_pending()

        @pending_node_names is a list of names of the pending nodes
        @new_pending is True if there is some new pending node since the bot
            was instantiated, and False otherwise
        """
        query = self.get_smart_group_query(smartgroup)
        
        body = self.client.nodes.list(json=query)
        if 'error' in body._asdict():
            raise LighhouseError('Lighthouse says: %s' % error[0].text)
        
        name_ids = { node.name: node.id for node in body.nodes \
            if node.approved == 0 }
        new_pending = (set(name_ids) > set(self.pending_name_ids))
        self.pending_name_ids = name_ids
        return sorted(name_ids, key=lambda k: k.lower()), new_pending

    def get_enrolled(self, smartgroup=None):
        """A list of current enrolled nodes
        
        :smartgroup if specified, objects will be filtered by smargroup query
        
        Usage:

        >>> enrolled_node_names = slack_bot.get_enrolled()

        @enrolled_node_names is a list of the currently enrolled nodes
        """
        query = self.get_smart_group_query(smartgroup)
        body = self.client.nodes.list({ 'config:status' : 'Enrolled' }, \
            json=query)
        if 'error' in body._asdict():
            raise LighhouseError('Lighthouse says: %s' % error[0].text)
        return sorted([node.name for node in body.nodes])

    def get_node_id(self, node_name):
        """Returns the node id given its name
        
        :node_name is the friendly name of the node

        Usage:

        >>> node_id = slack_bot.get_node_id('myNodeName')
        """
        try:
            body = self.client.nodes.list({ 'config:status' : 'Enrolled' })
            if 'error' in body._asdict():
                raise LighhouseError('Lighthouse says: %s' % error[0].text)
            for node in body.nodes:
                if node.name == node_name:
                    return node.id
        except LighhouseError as error:
            raise error
        except:
            pass
        return None

    def get_port_labels(self, node_name, smartgroup=None):
        """Returns all port labels for a given node
        
        :node_name is the friendly name of the node
        :smartgroup might be used together or instead of :node_name, so that
        only ports belonging to nodes belonging to the :smartgroup will be
        listed
        
        Usage:

        >>> port_labels = slack_bot.get_port_labels('myNodeOfInterest')

        @port_labels is a list of port labels for a given node, specified by
            its name
        """
        try:
            query = self.get_smart_group_query(smartgroup)
            nodes = []
            if node_name:
                body = self.client.nodes.list({ 'config:name' : node_name }, \
                    json=query)
            else:
                body = self.client.nodes.list(json=query)
            
            if 'error' in body._asdict():
                raise LighhouseError('Lighthouse says: %s' % error[0].text)
                
            nodes = body.nodes
            labels = [port.label for node in nodes for port \
                    in node.ports if port.mode == 'consoleServer']
            return sorted(labels)
        except LighhouseError as error:
            raise error
        except:
            return None

    def get_summary(self):
        """Returns a summary about how many nodes are currently connected,
        pending, and disconnected
        
        Usage:

        >>> connected, pending, disconnected = slack_bot.get_summary()

        @connected is the number of connected nodes
        @pending is the number of pending nodes
        @disconnected is the number of disconnected nodes
        """
        body = self.client.stats.nodes.connection_summary.get()
        if 'error' in body._asdict():
            raise LighhouseError('Lighthouse says: %s' % error[0].text)
        
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
        """Delete or disconnect a list of nodes specified by their names
        
        :node_names is a list of names of nodes to be deleted

        Usage:

        >>> nodes = ['myNodeName1', 'myNodeName2', 'myNodeName3']
        >>> deleted_list = slack_bot.delete_nodes(nodes)
        >>> print(deleted_list)

        @deleted_list is a subset of :node_names with those which were deleted
        """
        body = self.client.nodes.list()
        if 'error' in body._asdict():
            raise LighhouseError('Lighthouse says: %s' % error[0].text)
        
        deleted_names = []
        errors = []
        for node in body.nodes:
            if node.name in node_names:
                try:
                    result = self.client.nodes.delete(id=node.id)
                    if 'error' in result._asdict() \
                        and len(result.error) > 0:
                        raise RuntimeError(result.error[0].text)
                    deleted_names.append(node.name)
                except Exception as e:
                    errors.append('Error deleting [%s]: %s' % \
                        (node.name, str(e)))
        return deleted_names, errors

    def approve_nodes(self, node_names):
        """Approv or enroll a list of nodes specified by their names
        
        :node_names is a list of names of nodes to be approved

        Usage:

        >>> nodes = ['myNodeName1', 'myNodeName2', 'myNodeName3']
        >>> approved_list = slack_bot.approve_nodes(nodes)
        >>> print(approved_list)

        @approved_list is a subset of :node_names with those which were approved
        """
        body = self.client.nodes.list({ 'config:status' : 'Registered' })
        if 'error' in body._asdict():
            raise LighhouseError('Lighthouse says: %s' % error[0].text)
            
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
                    result = self.client.nodes.update(data=approved_node, \
                        id=node.id)
                    if 'error' in result._asdict() \
                        and len(result.error) > 0:
                        raise RuntimeError(result.error[0].text)
                    approved_names.append(node.name)
                except Exception as e:
                    errors.append('Error approving [%s]: %s' % (node.name, \
                        str(e)))
        return approved_names, errors
    
    def get_licenses(self):
        """returns the license keys related to the regarding lighthouse"""
        try:
            body = self.client.system.licenses.list()
            if 'error' in body._asdict():
                raise LighhouseError('Lighthouse says: %s' % error[0].text)
            return body.licenses
        except LighhouseError as error:
            raise error
        except:
            return None
    
    def get_entitlements(self):
        """returns the entitlements related to the regarding lighthouse"""
        try:
            body = self.client.system.entitlements.list()
            if 'error' in body._asdict():
                raise LighhouseError('Lighthouse says: %s' % error[0].text)
            return body.entitlements
        except LighhouseError as error:
            raise error
        except:
            return None
    
    def is_evaluation(self):
        """check whether the user is in evaluation mode"""
        try:
            licenses = self.get_licenses()
            for l in licenses:
                if len(l.raw) > 0:
                    return False
            raise
        except LighhouseError as error:
            raise error
        except:
            return True
    
    def is_license_valid(self):
        """check whether the user license is still valid, which means it is 
        not expired neither exceeding maximum nodes number"""
        try:
            entitlements = self.get_entitlements()
            body = self.client.nodes.list()
            if 'error' in body._asdict():
                raise LighhouseError('Lighthouse says: %s' % error[0].text)
            
            nodes_count = len(body.nodes)
            is_valid = False
            
            for e in entitlements:
                if 'features' in e._asdict() and \
                    'maintenance' in e.features._asdict() and \
                    'nodes' in e.features._asdict():
                    is_valid |= (time.time() <= int(e.features.maintenance) \
                        and int(e.features.nodes) >= nodes_count)
            return is_valid
        except LighhouseError as error:
            raise error
        except:
            return False
            
    def get_object_id(self, object_type, object_name, \
        parent_type=None, parent_name=None, parent_id=None):
        """Returns the id for a generic object based on its name, if it is a
        child object, the parent information is required
        
        :object_type is the type like: 'nodes', 'tags', 'smartgroups', etc.
        :object_name the known name of the object
        :parent_type depends on the object, for 'tags' it might be 'nodes'
        :parent_name the known name of the parent object
        :parent_id if the parent id is known, it might reduce the cost of
        finding it
        """
        try:
            if parent_type and parent_name and not parent_id:
                parent_id = self.get_object_id(parent_type, parent_name)
            
            chain = []
            params = []
            if parent_type:
                chain.append(parent_type)
                params.append('parent_id=' + parent_id)
            chain.append(object_type)
            
            call_str = 'self.client.{chain}.list({params})'
            r = eval(str.format(call_str, chain='.'.join(chain), \
                params=','.join(params)))
            if 'error' in r._asdict():
                raise LighhouseError('Lighthouse says: %s' % error[0].text)
            
            for o in r._asdict()[object_type]:
                obj_label = ''
                for label in ['name', 'label', 'username', 'groupname']:
                    if label in o._asdict():
                        obj_label = label
                        break
            
                if o._asdict()[obj_label] == object_name:
                    return o.id
        except LighhouseError as error:
            raise error
        except:
            return object_name

    def get_monitor(self, max_nodes=None, smartgroup=None):
        """builds a report similar to the web ui
        
        :max_nodes is for limiting the number of nodes displayed
        :smartgroup is for filtering nodes beloging to this smartgroup
        """
        query = self.get_smart_group_query(smartgroup)
        body = None
        
        if max_nodes:
            body = self.client.nodes.list(page=1, per_page=max_nodes, \
                json=query)
        else:
            body = self.client.nodes.list(json=query)
        if 'error' in body._asdict():
            raise LighhouseError('Lighthouse says: %s' % error[0].text)
            
        nodes = body.nodes
        
        body = self.client.system.licenses.list()
        if 'error' in body._asdict():
            raise LighhouseError('Lighthouse says: %s' % error[0].text)
        licenses = body.licenses
        
        body = self.client.system.entitlements.list()
        if 'error' in body._asdict():
            raise LighhouseError('Lighthouse says: %s' % error[0].text)
        entitlements = body.entitlements
        
        connected, pending, disconnected = self.get_summary()
        
        dashboard = """
Enrolled nodes:
{nodes_info}


Current Node Status:
{nodes_status}


Licensing Information:
{licensing}"""

        node_template = """
>  {node_name}:
>    {node_status}: last status change {time_change} ago
>    Web UI: <{url}/{node_id}>"""
        
        nodes_info = []
        
        for node in sorted(nodes, key=lambda n: n.name):
            if node.status == 'Enrolled':
                nodes_info.append(str.format(node_template, \
                    node_name=node.name, \
                    node_status=node.runtime_status.connection_status, \
                    time_change=self._format_time(\
                        node.runtime_status.change_delta), \
                    url=self.url, \
                    node_id=node.id))
        
        nodes_status = str.format("""
>  Connected: {connected}
>  Pending: {pending}
>  Disconnected: {disconnected}""",connected=connected, pending=pending, \
  disconnected=disconnected)
        
        max_devices = sum([e.features.nodes for e in entitlements \
            if e.features.maintenance >= time.time()])
        devices = len([n for n in nodes if n.status == 'Enrolled'])
        expiry_epoch = max([e.features.maintenance for e in entitlements])
        expiry = time.strftime('%m/%d/%Y', time.localtime(expiry_epoch))
        status = 'In Compliance' if devices <= max_devices \
            and expiry_epoch >= time.time() else 'Not in Compliance'
        
        licensing = str.format("""
>  Number of Installed Licenses: {installed}
>  Number of Supported Devices: {devices} / {max_devices}
>  Expiry Date: {expiry}
>  Status: {status}""", installed=len(licenses), devices=devices, \
  max_devices=max_devices, expiry=expiry,  status=status)
        
        return str.format(dashboard, nodes_info='\n'.join(nodes_info), \
            nodes_status=nodes_status, licensing=licensing)

    def get_node_info(self, node_name, smartgroup=None):
        """builds a full description of a node
        :node_name is the node's name
        """
        query = self.get_smart_group_query(smartgroup)
        body = self.client.nodes.list(json=query)
        if 'error' in body._asdict():
            raise LighhouseError('Lighthouse says: %s' % error[0].text)
        nodes = body.nodes
        
        for node in nodes:
            if node.name.lower() == node_name.lower():
                network = ''
                lan = ''
                modem = ''
                for i in node.interfaces:
                    if i.name == 'Network' and 'ipv4_addr' in i._asdict():
                        network = i.ipv4_addr
                    elif i.name == 'Management LAN' \
                        and 'ipv4_addr' in i._asdict():
                        lan = i.ipv4_addr
                    elif i.name == 'Internal Cellular Modem' \
                        and 'ipv4_addr' in i._asdict():
                        modem = i.ipv4_addr
                node_status=node.runtime_status.connection_status
                time_change=self._format_time(node.runtime_status.change_delta)
                return str.format("""
*{node_name}*
> Connection Status: *{status}*, last status change {change} ago
> Model: {model}
> Firmware Version: {firmware}
> Enrollment Bundle: {bundle}
> Management VPN Address: {vpn}
> NET1 MAC address: {mac}
> Network: {network}
> Management LAN: {lan}
> Internal Cellular Modem: {modem}
> Serial Number: {serial}
> Access Web UI: <{url}>
""", model=node.model, firmware=node.firmware_version, \
    bundle=node.enrollment_bundle, vpn=node.lhvpn_address, \
    mac=node.mac_address, network=network, lan=lan, modem=modem, \
    serial=node.serial_number, url='<%s/%s>' % (self.url, node.id), \
    status=node_status, change=time_change, node_name=node_name)
        
        return 'Information not found for node: [%s]' % node
            
    def get_device_monitor(self, smartgroup=None):
        """returns a formatted list of devices grouped by node
        :max_nodes is for limiting the number of nodes displayed
        :smartgroup is for filtering nodes beloging to this smartgroup
        """
        try:
            query = self.get_smart_group_query(smartgroup)
            body = self.client.ports.list(json=query)
            if 'error' in body._asdict():
                raise LighhouseError('Lighthouse says: %s' % error[0].text)
                
            ports = body.ports
            clean_ports = []
            for p in ports:
                clean_ports.append({
                    'name': p.label,
                    'node_name': p.node_name,
                    'change': self._format_time(p.runtime_status.change_delta),
                    'status': p.runtime_status.connection_status,
                    'web': '<%s/%s>' % (self.url, p.web_terminal_url) \
                        if 'web_terminal_url' in p._asdict() else '',
                    'ssh': '<%s>' % p.proxied_ssh_url \
                        if 'proxied_ssh_url' in p._asdict() else ''
                })
            ports = sorted(clean_ports, \
                key=lambda x: x['node_name'] + x['name'])
            
            monitor_template = """
Devices matching search:
{devices_list}
"""
            device_template = """
> Node: {node_name}
> Device: {name}
> Status: {status}, last status change {change} ago
> Web Terminal: {web}
> SSH: {ssh}"""
            return str.format(monitor_template, devices_list='\n'.join(\
                [str.format(device_template, **p) for p in ports]))
                
        except LighhouseError as error:
            raise error
        except:
            return 'Problem listing devices'
        
    
    def get_device_info(self, device, smartgroup):
        """returns a formatted list of devices that match :device name
        
        :device is the device name
        :smartgroup is for filtering nodes beloging to this smartgroup
        """
        try:
            query = self.get_smart_group_query(smartgroup)
            body = self.client.ports.list(json=query)
            if 'error' in body._asdict():
                raise LighhouseError('Lighthouse says: %s' % error[0].text)
            ports = body.ports
            
            clean_ports = []
            for p in ports:
                if p.label.lower() == device.lower():
                    clean_ports.append({
                        'name': p.label,
                        'node_name': p.node_name,
                        'change': self._format_time(p.runtime_status.change_delta),
                        'status': p.runtime_status.connection_status,
                        'web': '<%s/%s>' % (self.url, p.web_terminal_url) \
                            if 'web_terminal_url' in p._asdict() else '',
                        'ssh': '<%s>' % p.proxied_ssh_url \
                            if 'proxied_ssh_url' in p._asdict() else ''
                    })
            ports = sorted(clean_ports, \
                key=lambda x: x['node_name'] + x['name'])
            
            monitor_template = """
Devices Monitor:
{devices_list}
"""
            device_template = """
> Node: {node_name}
> Device: {name}
> Status: {status}, last status change {change} ago
> Web Terminal: {web}
> SSH: {ssh}"""
            return str.format(monitor_template, devices_list='\n'.join(\
                [str.format(device_template, **p) for p in ports]))
        except LighhouseError as error:
            raise error
        except:
            return 'Problem finding device'
    
    def _format_time(self, time_sec):
        """formats properly a time in seconds for the highest time unit as
        possible
        
        :time_sec a time interval in seconds
        """
        sec = timedelta(seconds=time_sec)
        d = datetime(1,1,1) + sec
        if d.day-1 > 0:
            return '%d days' % (d.day-1)
        elif d.hour > 0:
            return '%d hours' % d.hour
        elif d.minute > 0:
            return '%d minutes' % d.minute
        return '%d seconds' % d.second
        
class OgLhSlackBot:
    """A Bot for dealing with the Opengear Lighthouse API straight from Slack
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
        formatter = logging.Formatter('%(asctime)s - [%(levelname)s] ' + \
            '(%(threadName)-10s) %(message)s')
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        self.logger.addHandler(fh)
        self.logger.addHandler(ch)

        self.bot_name = os.environ.get('SLACK_BOT_NAME')
        self.default_channel = os.environ.get('SLACK_BOT_DEFAULT_CHANNEL')
        self.slack_token = os.environ.get('SLACK_BOT_TOKEN')

        if not (self.bot_name and self.default_channel and self.slack_token):
            raise RuntimeError("""
Some of the required environment variables are not set, please refer to the 
documentation: https://github.com/thiagolcmelo/oglhslack
            """)

        self.default_log_channel = \
            os.environ.get('SLACK_BOT_DEFAULT_LOG_CHANNEL')
        self.admin_channel = \
            os.environ.get('SLACK_BOT_ADMIN_CHANNEL') or 'oglhadmin'

        # the max number of threads is equals to the number of cpus
        self.poll_max = multiprocessing.cpu_count()
        self.semaphores = threading.BoundedSemaphore(value=self.poll_max)
        self.poll_interval = 1
        self.restart_interval = 15

        self.func_intents = { \
            self._get_monitor : { 'monitor', 'dashboard' }, \
            self._get_device_monitor : { 'devices-monitor', \
                'device-monitor' }, \
            self._device_info : { 'device-info' }, \
            self._get_port_ssh : { 'ssh', 'sshlink' }, \
            self._get_port_web : { 'web', 'webterm', 'weblink' }, \
            self._get_port : { 'con', 'console', 'gimme' }, \
            self._get_port_labels : { 'devices', 'ports', 'labels' }, \
            self._get_node_summary : { 'status', 'summary', 'stats', 'status', \
                'howzit' }, \
            self._info : { 'info', 'desc' }, \
            self._get_web : { 'lighthouse', 'lhweb', 'webui', 'gui' }, \
            self._get_enrolled : { 'nodes', 'enrolled' }, \
            self._check_pending : { 'pending' }, \
            self._approve_nodes: { 'approve', 'okay', 'approve', 'admin' }, \
            self._delete_nodes: { 'delete', 'kill', 'delete', 'admin' }, \
            self._smart_groups: { 'smart', 'smartgroups', 'smart-groups' }, \
            self._smart_group_nodes: { 'smart-nodes', 'smartgroup-nodes', \
                'smartgroupnodes', 'smart-group-nodes' }, \
            self._get_monitor_full : { 'monitor-full', 'dashboard-full' },
        }

        self._start_clients()

        if not self.slack_client.rtm_connect():
            raise RuntimeError('Slack connection failed')
            
        self.bod_id = self._get_bot_id()
        self.bot_at = '<@' + self.bod_id + '>'
    
    def _start_clients(self):
        """it starts or restarts slack and lighthouse clients when necessary
        """
        try:
            self.slack_client = SlackClient(self.slack_token)
        except:
            raise RuntimeError('Slack read failed, ' + \
                'please check your token')
        try:
            self.client_helper = OgLhClientHelper()
        except:
            raise RuntimeError('Problems accessing Lighthouse API')

    def listen(self):
        """Listen Slack channels for messages addressed to oglh slack bot"""
        while True:
            try:
                try:
                    self._logging('Hi there! I am here to help!', force_slack=True)
                    
                    while True:
                        command, channel, user_id = \
                                self._read(self.slack_client.rtm_read())
                        
                        if command and channel and user_id:
                            t = threading.Thread(target=self._command, \
                                args=(command, channel, user_id))
                            t.setDaemon(True)
                            t.start()
                        time.sleep(self.poll_interval)

                except KeyboardInterrupt:
                    self._logging('Slack bot was interrupt manually', \
                        level=logging.WARNING)
                    os.kill(os.getpid(), signal.SIGUSR1)

                except Exception as error:
                    self.logger.exception(error)
                    self._dying_message(str(error))
            
                self._logging('Restarting Bot in %d seconds...' \
                    % self.restart_interval, force_slack=True)
                time.sleep(self.restart_interval)
                self._start_clients()
            except Exception as error:
                self._logging('Error starting clients: %s' % error)
                
                

    def _read(self, output_list):
        """reads slack messages in channels where the bot has access
        (PM, channels enrolled, etc)
        
        :output_list is the slack return for the api.rtm_read() function
        
        WARNING: it ignores messages from whathever other slack bot
        """
        if output_list and len(output_list) > 0:
            for output in output_list:
                if output and 'text' in output and \
                    self.bot_at in output['text']:
                    command = \
                        output['text'].split(self.bot_at)[1].strip().lower()
                    return command, output['channel'], output['user']
                elif output and 'text' in output and 'channel' in output \
                    and output['channel'][0] == 'D' \
                    and output['user'] != self.bod_id \
                    and (not 'subtype' in output \
                    or output['subtype'] != 'bot_message'):
                    return \
                        output['text'].strip().lower(), \
                        output['channel'], \
                        output['user']
        return None, None, None

    def _command(self, command, channel, user_id):
        """tries to execute a command received in some of the available channels
        or private messages. It has a semaphore for assuring that no more 
        commands are executed simultaneously than the number of cpus
        
        :command is a string carriying the command, it might be empty, a single
        word or many words
        :channel is the slack id of the channel where the message was sent
        :user_id is the id of the user who sent the message
        """
        try:
            self.semaphores.acquire()
            response = ''
            is_help = False

            username = self._get_slack_username(user_id)
            channel_name = self._get_channel_name(channel)

            self._logging(str.format('Got command: `{command}`, from: ' + \
                '{username}', command=command, username=username))
            if user_id:
                response = '<@' + user_id + '|' + username + '> '
            
            try:
                #if not self.client_helper.is_license_valid():
                #    response += '\n\n*We were not able of validating your ' + \
                #        'license key, please check the status of your ' + \
                #        'signature* :rage:\n\n'
                if self.client_helper.is_evaluation():
                    response += '*WARNING:* Lighthouse is currently ' + \
                        'running in evaluation mode. :slightly_frowning_face:\n'
                        
                # check whether some of the built in funtions were called    
                output = self._built_in_functions(command, channel_name, \
                    username)
                # try the more complex query tool in case of no built in function
                if not output:
                    output, is_help = self._query_tool(command, channel_name)
            except LighthouseError as error:
                output = str(error)
            except Exception as ie:
                raise ie

            response += output
                
            self._logging('Responding: ' + \
                (response if not is_help else 'help message'))

            try:
                self.slack_client.api_call('chat.postMessage', \
                    channel=channel, text=response, as_user=True)
            except:
                raise RuntimeError('Slack post failed')

        except Exception as e:
            self._logging(str(e), level=logging.ERROR, error_stack=e)

        finally:
            self.semaphores.release()

    def _get_bot_id(self):
        """return the slack id for the bot specified at SLACK_BOT_NAME env var
        """
        try:
            users_list = self.slack_client.api_call('users.list')
        except:
            raise RuntimeError('Slack users list failed, ' + \
                'please check your token')
        for member in users_list['members']:
            if member['name'] == self.bot_name:
                return member['id']
        raise RuntimeError('User ' + self.bot_name + ' not found')

    def _get_channel_name(self, channel_id):
        """returns the friendly name of a channel given its id
        
        :channel_id is the slack id of the sought channel
        """
        try:
            channel_list = self.slack_client.api_call('channels.list')
        except:
            raise RuntimeError('Slack channels list failed')
        for c in channel_list['channels']:
            if c['id'] == channel_id:
                return c['name']
        
        try:
            channel_list = self.slack_client.api_call('groups.list')
        except:
            raise RuntimeError('Slack private channels list failed')
        
        for c in channel_list['groups']:
            if c['id'] == channel_id:
                return c['name']
        return None

    def _get_slack_username(self, user_id):
        """returns the friendly username of a user given its id if the username
        is not found 'friend' is returned
        
        :user_id is the slack id of the sought user
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
        """try to parse the :command as one of the built in ones, :channel is 
        used for checking where the command was performed, whether in a
        public/private channel or in a private message, :username is required
        for some of the built in functions
        
        :command is the trimmed string with the comand only
        :channel is the friendly name of the channel where the message was sent
        :username is the friendly name of the user who sent the message
        
        WARNING: it also prevents from executing admin commands in not 
        authorized channels
        """
        intent, _, scope = command.partition(' ')
        scope = self._sanitise(scope)
        
        for func, intents in self.func_intents.items():
            if intent in intents and (channel == self.admin_channel or \
                not 'admin' in intents):
                scope, smartgroup = self._split_scope_smartgroup(scope)
                return func(scope, smartgroup, username)
            elif intent in intents and channel != self.admin_channel \
                and 'admin' in intents:
                return "This operation must take place at `%s` channel." % \
                    self.admin_channel
        return None

    def _query_tool(self, command, channel):
        """tries to parse the :command as query, with a proper syntax specified
        at the documentation
        
        :command is the trimmed string with the comand only
        :channel is the friendly name of the channel where the message was sent
        
        WARNING: it also prevents from executing commands that make changes from
        not authorized channels
        """
        try:
            action, _, scope = re.sub('\s+', ' ', command).partition(' ')
            action = action.lower()
            scope = self._sanitise(scope.strip())
            
            action_type = 'simple' if action in ['get','find','list'] \
                else 'complex'
                
            if action in ['update', 'set', 'delete', 'create'] \
                and channel != self.admin_channel:
                return "Actions other than `get`, `find` and `list` " + \
                    "must take place at `%s` channel." % \
                    self.admin_channel, False
            else:
                params=[]
                chain = []
                main_parts = []
                
                object_type = None
                object_name = None
                parent_type = None
                parent_name = None
                parent_id = None
                
                if re.match('.*\s+in\s+\w+$', scope):
                    scope = scope.split(' in ')
                    query = self.client_helper.get_smart_group_query(scope[1])
                    params.append('json=\'%s\'' % query)
                    scope = scope[0]

                if 'from' in scope:
                    objects = scope.split('from')
                    main_parts = objects[0].strip().split(' ')
                    parent_parts = objects[1].strip().split(' ')
                    parent_type = self._dummy_plural(parent_parts[0])
                    chain.append(parent_type)
                    if len(parent_parts) == 2:
                        parent_name = parent_parts[1]
                        parent_id = self.client_helper.get_object_id(\
                            parent_type, parent_name)
                        params.append('parent_id="%s"' % parent_id)
                else:
                    main_parts = scope.strip().split(' ')

                object_type = self._dummy_plural(main_parts[0])
                if object_type == 'devices':
                    object_type = 'ports'
                chain.append(object_type)
                    
                if len(main_parts) == 2:
                    if action_type == 'simple':
                        action = 'find'
                    object_name = main_parts[1]
                    object_id = self.client_helper.get_object_id(\
                            object_type, object_name, \
                            parent_type=parent_type, \
                            parent_name=parent_name)
                    params.append('id="%s"' % object_id)
                    
                call_str = 'self.client_helper.client.' + \
                    '{chain}.{action}({params})'
                r = eval(str.format(call_str, chain='.'.join(chain), \
                    action=action, params=','.join(params)))
                    
                if 'error' in r._asdict() and \
                    'Could not find element' in r.error[0].text:
                    # lets try to be smart
                    try:
                        r2 = eval(str.format(call_str, chain='.'.join(chain), \
                            action='list', params=','.join(params)))
                        for o in r2._asdict()[object_type]:
                            if o.id == object_id:
                                return self._format_response(action, r2), False
                    except:
                        pass
                    
                    
                return self._format_response(action, r), False
        except:
            return self._show_help(), True

    # built in functions

    def _ports_list_ssh(self, ports, label, username):
        """ssh connection strings for devices
        
        :ports a list of port objects
        :label the label of the port to build the url
        :username it is the user's slack username
        """
        ssh_urls = []
        for port in ports:
            if not 'proxied_ssh_url' in port._asdict():
                continue
            ssh_url = re.sub(r'ssh://lhbot', 'ssh://' + username, \
                port.proxied_ssh_url)
            ssh_urls.append('<' + ssh_url + '>')
        return ssh_urls

    def _ports_list_web(self, ports, label):
        """web urls for devices
        
        :ports a list of ports objects
        :label the label of the port to build the url
        """
        web_urls = []
        for port in ports:
            if not 'web_terminal_url' in port._asdict():
                continue
            web_url = self.client_helper.url + '/'
            web_url += port.web_terminal_url
            web_urls.append('<' + web_url + '>')
        return web_urls

    def _get_port_ssh(self, label, smartgroup, username):
        """returns a list of ssh links for a device
        
        :label the device label
        :username the slack username
        """
        ports = self.client_helper.get_ports(label, smartgroup)
        urls = self._ports_list_ssh(ports, label, username)
        if not urls:
            return ':x: Problem to create ssh link'
        return '\n'.join(urls)
        
    def _get_port_web(self, label, smartgroup, *_):
        """ returns a list of web urls for a device
        
        :label the device label
        """
        ports = self.client_helper.get_ports(label, smartgroup)
        urls = self._ports_list_web(ports, label)

        if not urls:
            return ':x: Problem to create web link.'
        return '\n'.join(urls)

    def _get_port(self, label, smartgroup, username):
        """return all urls ans ssh links for a given device
        
        :label the device label
        :username the slack username
        """
        ports = self.client_helper.get_ports(label, smartgroup)
        ssh_urls = self._ports_list_ssh(ports, label, username)
        web_urls = self._ports_list_web(ports, label)

        urls = [ x for t in zip(ssh_urls, web_urls) for x in t ]
        if not urls:
            return ':x: Device not found. ' + \
                'Unable to create ssh link and web link.'
        return '\n'.join(urls)

    def _approve_nodes(self, str_names, *_):
        """approve or enroll a list of nodes specified by their names
        :str_names a list of nodes names
        """
        names = str_names.split(' ')
        approved_names, errors = self.client_helper.approve_nodes(names)
        for e in errors:
            self._logging(e, level=logging.ERROR)
        response = []
        for name in names:
            if name in approved_names:
                emoji = ':white_check_mark: Success: Node approved.'
            else:
                emoji = ':x: Error: Node could not be approved. ' + \
                    'Please check it and try again.'
            response.append(name + ' ' + emoji)
        return self._format_list(response)
        
    def _delete_nodes(self, str_names, *_):
        """delete or unenroll a list of nodes specified by their names
        :str_names a list of nodes names
        """
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

    def _get_port_labels(self, node_name, smartgroup, *_):
        """returns a list of ports labels r a given node specified by its name
        :node_name the friendly name of the node for listing ports
        """
        labels = self.client_helper.get_port_labels(node_name, smartgroup)
        if labels:
            response = self._format_list(labels)
        else:
            response = 'No devices found'
        return response

    def _get_enrolled(self, nodes, smartgroup, *args):
        """return a list of the current nodes connectes or enrolled"""
        enrolled_nodes = self.client_helper.get_enrolled(smartgroup)
        if enrolled_nodes:
            response = self._format_list(enrolled_nodes)
        else:
            response = 'No created node.'
        return response
        
    def _check_pending(self, new_only, smartgroup, *_):
        """check whether there are pending nodes waiting for approval, in such
        a case it returns a list with their names
        
        :new_only is a boolean for indicating that only nodes waiting for
        approval that appeared after the last check should be returned
        """
        pending_nodes, new_pending = self.client_helper.get_pending(smartgroup)

        if not new_pending and new_only:
            return None

        if pending_nodes:
            response = ':warning: There are some nodes waiting for approval.\n'
            response += self._format_list(pending_nodes)
        else:
            response = ':white_check_mark: No pending nodes to approve.'
        return response

    def _get_node_summary(self, *_):
        """returns a status of the current nodes enrolled, pending or deleted
        """
        connected, pending, disconnected = self.client_helper.get_summary()
        if connected == None:
            return None
        response = 'Nodes\' status information:\n' \
            '> Connected: %d\n' \
            '> Disconnected: %d\n' \
            '> Pending: %d' % (connected, disconnected, pending)
        return response

    def _get_web(self, *args):
        """returns the general url for the GUI or for a specific node
        
        :args can be a tuple like ('','username'), in such a case only the
        general url will be returned, or it can be ('node-name','username')
        in sucha a case the url for the given node will be returned        
        """
        if args[0]:
            node_id = self.client_helper.get_node_id(args[0]) or args[0]
            return '<' + self.client_helper.url + '/' + node_id + '>'
        return '<' + self.client_helper.url + '>'

    def _get_monitor(self, scope, smartgroup, *_):
        """returns a summary similar to the one at the monitor dashboard
        in the web ui, max 10 nodes
        
        :scope is never used
        :smartgroup is used for filtering nodes belonging to this smartgroup
        
        """
        return self.client_helper.get_monitor(max_nodes=10, \
            smartgroup=smartgroup)
        
    def _get_monitor_full(self, scope, smartgroup, *_):
        """returns a summary similar to the one at the monitor dashboard
        in the web ui
        
        :scope is never used
        :smartgroup is used for filtering nodes belonging to this smartgroup
        """
        return self.client_helper.get_monitor(smartgroup=smartgroup)
        
    def _smart_groups(self, *_):
        """return a list of smartgroups"""
        smartgroups = self.client_helper.get_smart_groups()
        if smartgroups:
            response = self._format_list(smartgroups)
        else:
            response = 'No smart groups found'
        return response
    
    def _smart_group_nodes(self, smartgroup, *_):
        """return a list of nodes belonging to a smartgroup
        
        :smartgroup the smart group name
        """
        nodes = self.client_helper.get_smart_group_nodes(smartgroup)
        if nodes:
            response = self._format_list(nodes)
        else:
            response = 'No nodes were found for smart group %s' % smartgroup
        return response
        
    def _info(self, node, *_):
        """displays a detailed description of a node
        
        :node is the node's name
        """
        return self.client_helper.get_node_info(node)
    
    def _get_device_monitor(self, scope, smartgroup, *_):
        """shows a list of devides, grouped by node
        
        :scope is never used
        :smartgroup is used for filtering nodes belonging to this smartgroup
        """
        return self.client_helper.get_device_monitor(smartgroup)
    
    def _device_info(self, device, smartgroup, *_):
        """shows the description of a device, if more than one device is found
        with this name, they will be listed according to their nodes
        
        :device the devices name
        :smartgroup is used for filtering nodes belonging to this smartgroup
        """
        return self.client_helper.get_device_info(device, smartgroup)

    # formatting functions

    def _sanitise(self, line):
        """slack messages come with some sort of formatting like:
        <user-id|username>
        <channel-id|channel-name>
        <url|link-label>
        
        for such cases, it returns the content part:
        <user-id|username> becomes: username
        <channel-id|channel-name> becomes: channel-name
        <url|link-label> becomes: link-label
        
        it is most useful for links, which slack always put in the shape above
        
        :line is a string with a shape like above
        """
        sanitised = []
        pattern = re.compile('^\<.*\|(.*)\>$')
        for s in line.strip().split():
            if pattern.search(s):
                sanitised.append(pattern.search(s).group(1))
            else:
                sanitised.append(s)
        return ' '.join(sanitised)

    def _dummy_plural(self, word):
        """it is a very simple tool for get plural names according to those used
        by the api, it is just a matter of making it easier for the user when
        guessing about query syntax
        
        :word is a string to be transformed to its plural shape according to
        the api conventions
        """
        if word == 'system':
            return word
        if word[-1] == 'y':
            return word[:-1] + 'ies'
        elif word[-1] == 's':
            return word
        return word + 's'

    def _format_response(self, action, resp):
        """formats the message according to the action

        for 'list', minimal information is shown, basically a list of names 
        and/or ids

        for 'find' or 'get' returns a structured view of the objects properties
        
        :action the action, which might be: 'list', 'get', 'find', 'update', and
        'create'
        :resp might be a simple string, an array, or a named tuple
        """
        try:
            if 'error' in resp._asdict() \
                and resp.error[0].text == 'Permission denied':
                return 'Object does not exist (please check the id) ' + \
                    'or @%s is not allowed to fetch it.' % self.bot_name

            if action == 'list':
                object_name = [k for k in resp._asdict() \
                    if k != 'meta'][0]
                object_label = ''

                if 'name' in resp._asdict()[object_name][0]._asdict():
                    object_label = 'name'
                if 'label' in resp._asdict()[object_name][0]._asdict():
                    object_label = 'label'

                if object_label == '':
                    return textwrap.dedent("""
                        ```
                        """ + self._dump_obj(resp) + """
                        ```""")

                try:
                    #names = [o._asdict()[object_label] + \
                    #    ' (id: ' + o._asdict()['id'] + ')' \
                    names = [o._asdict()[object_label] \
                        for o in resp._asdict()[object_name]]
                except:
                    names = [o._asdict()[object_label] \
                        for o in resp._asdict()[object_name]]

                return self._format_list(sorted(names), object_name)
            elif action == 'find' or 'get':
                return textwrap.dedent("""
                    ```
                    """ + self._dump_obj(resp) + """
                    ```""")
        except:
            return str(resp)

    def _format_list(self, raw_list, list_title=''):
        """format an array of strings according to its length.
        - until 10 items, a simple list is returned
        - more than 10 items are printed in columns
        
        :raw_list is an array of strings
        :list_title is a title to be placed above the list, it is not required
        """
        if len(raw_list) <= 20:
            #return '\n' + '\n'.join(['> %d. %s' % (i + 1, e) \
            #    for i, e in enumerate(raw_list)])
            return '\n' + '\n'.join(raw_list)
        max_len = max([len(l) for l in raw_list])
        cols = int (100 / max_len)
        formated_list = ''
        for i, word in enumerate(raw_list):
            if i % cols == 0:
                formated_list += '\n'
            #formated_list += ('{:3d}. {:' + str(max_len) + 's} '\
            #    ).format((i+1), word)
            formated_list += ('{:' + str(max_len) + 's} ').format(word)
        return textwrap.dedent((list_title + ':' if list_title else '') + """
            ```
            """ + formated_list + """
            ```
            """)

    def _dump_obj(self, obj, level=0):
        """tries to dump an object in a easy to read description of its
        properties
        
        :obj the object to be dumped, it might be since a simple string until
        a named tuple
        :level it is basically an indicator of how many tabs will be in the
        beginning of the line, for creating an easy of reading text, which means
        for identation
        """
        response = ''
        for key, value in obj._asdict().items():
            try:
                if isinstance(value, list):
                    response += ('\n%s:' % (" " * level + key)) + \
                        self._dump_obj(value[0], level + 2)
                else:
                    response += ('\n%s:' % (" " * level + key)) + \
                        self._dump_obj(value, level + 2)
            except Exception as e:
                response += '\n' + " " * level + "%s -> %s" % (key, value)
        return response
    
    def _split_scope_smartgroup(self, scope):
        """removes the smartgroup from a command's scope
        
        :scope is the scope of a command, its parameter
        """
        smartgroup = None
        if re.match('.*in\s+\w+$', scope):
            scope, smartgroup = scope.split('in ')
        return scope.strip(), smartgroup and smartgroup.strip()

    def _dying_message(self, message):
        """it is final message for the default slack channel and for the log
        file, in case of issues posting to slack, only the log file part
        will work
        
        :message is a raw final message given by slack bot before it dies
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

    def _logging(self, message, level=logging.INFO, force_slack=False,
        error_stack=None):
        """it will log to slack only if there is a specified slack channel 
        for logs or if the level is not a simple logging.INFO
        
        :message the message to be logged
        :level the level, which should be those logging standard ones
        force_slack
        """
        try:
            if error_stack:
                self.logger.exception(error_stack)
            elif level == logging.CRITICAL:
                self.logger.critical(message)
            elif level == logging.ERROR:
                self.logger.error(message)
            elif level == logging.WARNING:
                self.logger.warning(message)
            else:
                self.logger.info(message[0:100] + ('...' \
                    if len(message) > 100 else ''))

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
                    channel=self.default_log_channel, \
                        text=slack_message, as_user=True)
        except:
            self.logger.error('Error logging: \n' + message)

    def _show_help(self, *_):
        """returns a text with instructions about the commands syntax"""
        build_in_commands = [
            {
                'command': 'monitor',
                'description': 'Shows a summary information about nodes ' + \
                    'and licenses (displays only first 10 nodes) (SG).',
                'alias': 'dashboard'
            },
#            {
#                'command': 'monitor-full',
#                'description': 'Shows a summary information about nodes ' + \
#                    'and licenses (displays all nodes) (SG).',
#                'alias': 'dashboard'
#            },
#            {
#                'command': 'devices-monitor',
#                'description': 'Shows a list of devices grouped by node (SG).',
#                'alias': 'device-monitor'
#            },
            {
                'command': 'devices',
                'description': 'Shows all the managed devices available (SG)',
                'alias': 'ports, labels'
            },
            {
                'command': 'device-info <device>',
                'description': 'Shows the description of a device (SG)',
                'alias': ''
            },
            {
                'command': 'ssh <device>',
                'description': 'Gets a SSH link for managed Device (SG)',
                'alias': 'sshlink <device>'
            },
            {
                'command': 'web <device>',
                'description': 'Gets a web terminal link for managed ' + \
                    'device (SG)',
                'alias': 'webterm <device>, weblink <device>'
            },
            {
                'command': 'con <device>',
                'description': 'Gets both a SSH link and a web terminal ' + \
                    'link for managed device (SG)',
                'alias': ''
            },
            {
                'command': 'status',
                'description': 'Shows nodes enrollment summary',
                'alias': 'console <device>, gimme <device>'
            },
            {
                'command': 'info <node>',
                'description': 'Shows the node\'s description',
                'alias': 'desc <node>'
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
                'description': 'Shows enrolled nodes (SG)',
                'alias': 'summary, stats, status, howzit'
            },
            {
                'command': 'pending',
                'description': 'Shows nodes awaiting approval (SG)',
                'alias': 'enrolled'
            },
            {
                'command': 'approve <node>',
                'description': 'Approves a node or a whitespace separated ' + \
                    'list of nodes (admin only)',
                'alias': 'okay <node>, approve <node>'
            },
            {
                'command': 'delete <node>',
                'description': 'Unenrolls a node or a whitespace separated ' + \
                    'list of nodes (admin only)',
                'alias': 'kill <node>, delete <node>'
            },
            {
                'command': 'smart-groups',
                'description': 'Shows the list of smartgroups',
                'alias': 'smart'
            },
            {
                'command': 'smart-group-nodes <smartgroup>',
                'description': 'Shows the nodes belonging to a smartgroup',
                'alias': 'smart-nodes, smartgroupnodes'
            },
        ]

        max_command = max([len(c['command']) for c in build_in_commands])
        max_desc = max([len(c['description']) for c in build_in_commands])
        max_alias = max([len(c['alias']) for c in build_in_commands])
        #head_str = '\n%s {:%ds} | {:%ds} | {:%ds}' % \
        #    (' ' * (len(self.bot_name) + 1), max_command, max_desc, max_alias)
        #line_str = '\n@%s {:%ds} | {:%ds} | {:%ds}' % \
        #    (self.bot_name, max_command, max_desc, max_alias)
        head_str = '\n%s {:%ds} | {:%ds}' % \
            (' ' * (len(self.bot_name) + 1), max_command, max_desc)
        line_str = '\n@%s {:%ds} | {:%ds}' % \
            (self.bot_name, max_command, max_desc)
        help_text = head_str.format('Commands', 'Description')

        for c in build_in_commands:
            help_text += line_str.format(c['command'], c['description'])

        return textwrap.dedent("""
```""" + help_text + """
```

In the list of commands above (same holding for those bellow), those """ + \
"""with *(SG)* can be followed by `in MySmartGroup`, for instance:

```
@""" + self.bot_name + """ nodes in MySmartGroup """ + \
"""(same as @mybot smart-group-nodes MySmartGroup)
```

It is also possible to query objects like:
```
@""" + self.bot_name + """ list nodes
@""" + self.bot_name + """ find node my-node-name
@""" + self.bot_name + """ list tags from node my-node-name
```

Generically:
```
@""" + self.bot_name + """ get <static-object>
@""" + self.bot_name + """ list <objects>
@""" + self.bot_name + """ find <object> <object-name>

@""" + self.bot_name + """ get <static-object> from <parent-object> """ + \
"""<parent-object-name>
@""" + self.bot_name + """ list <objects> from <parent-object> """ + \
"""<parent-object-name>
@""" + self.bot_name + """ find <object> <object-name> from """ + \
"""<parent-object> <parent-object-name>
```

For a complete reference, please refer to:

https://github.com/thiagolcmelo/oglhslack
            """)

if __name__ == '__main__':
    slack_bot = OgLhSlackBot()
    slack_bot.listen()
