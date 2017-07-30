#!/usr/bin/env python

from lhapi import LighthouseApiClient
from slackclient import SlackClient
from functools import wraps

def ensure_auth(f):
    def wrapper(*args):
        try:
            result = f(*args)
        except Exception as error:
            args[0]._warning_message(str(error))
        return None
    return wrapper

class OgLhSlackBot:
    """

    """

    def __init__(self):
        self.bot_name = os.environ.get('SLACK_BOT_NAME')
        self.default_channel = os.environ.get('SLACK_BOT_DEFAULT_CHANNEL')
        self.slack_client = SlackClient(os.environ.get('SLACK_BOT_TOKEN'))
        self.lh_client = LighthouseApiClient()

        self.poll_count = 0
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
            self._dad_joke: { 'joke', 'dad', 'lame', 'lol' } \
        }

        if not self.slack_client.rtm_connect():
            raise RuntimeError('Slack connection failed')
        self.bot_at = '<@' + self._get_bot_id() + '>'

    @report_failure
    def listen(self):
        print 'Hello'

    def _warning_message(self, message):
        warning_message = textwrap.dedent("""
            @""" + self.bot_name + """  went offline with error message:
            ```
            """ + message + """
            ```
            """)
        self.slack_client = SlackClient(os.environ.get('SLACK_BOT_TOKEN'))
        self.slack_client.api_call('chat.postMessage', \
            channel=self.default_channel, text=warning_message, as_user=True)

if __name__ == '__main__':
    slack_bot = OgLhSlackBot()
    slack_bot.listen()
