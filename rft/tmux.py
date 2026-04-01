#!/usr/bin/env python
# -*- coding: utf-8 -*-

# from .window_manager import WindowManager
import logging
import json
# import re
from subprocess import call
import asyncio
from collections import deque
from .exceptions import TerminateTaskGroup

# TODO: instead of json.loads, consider how libtmux does it: https://github.com/tmux-python/libtmux/blob/v0.8.2/libtmux/server.py#L160

# note vars can be prefixed w/ q: prefix to provide shell escaping; e.g. for [some "name"] #{q:window_name} would become [some\ \"name\"]
LIST_CLIENTS_CMD = """list-clients -F '!list-clients {"name":"#{client_name}","is_ctrl":#{client_control_mode},"active_session_id":"#{session_id}"}'"""
LIST_SESSIONS_CMD = """list-sessions -F '!list-sessions {"id": "#{session_id}", "name":"#{session_name}","active_window_id":"#{window_id}"}'"""
LIST_ALL_WINDOWS_CMD = """list-windows -a -F '!list-all-windows {"id":"#{window_id}","name":"#{window_name}","is_active":#{window_active},"index":#{window_index},"session_id":"#{session_id}"}'"""
LIST_SESSION_WINDOWS_CMD = """list-windows -t {0} -F '!list-session-windows {"id":"#{window_id}","name":"#{window_name}","is_active":#{window_active},"index":#{window_index},"session_id":"#{session_id}"}'"""

SWITCH_TO_CLIENT_CMD = """switch-client -c {0} -t {1}"""
KILL_WINDOW_CMD = """kill-window -t {0}"""
# notes:
# - session killing seems to produce: (note at least for me this causes client detach as well)
#     %sessions-changed
#     %unlinked-window-close @28
#     %client-detached /dev/pts/1
# - new session (:new) causes following events:
#     %unlinked-window-add @24
#     %sessions-changed
#     %client-session-changed /dev/pts/1 $10 10
# - attaching a new client (tmux attach) causes only this msg:
#     %client-session-changed /dev/pts/14 $1 lean
#
# possible others we may want to handle:
#   %client-detached /dev/pts/1


class Tmux(object):
    """tmux client"""

    def __init__(self, conf) -> None:
        """Constructor

        """
        self._conf = conf
        self._clients = {}
        self._sessions = []
        self._windows = []
        self._current_session = None
        self.client = None   # client we assume corresponds to our main one
        self._tmux_proc = None
        self._last_window = deque(maxlen=2)  # holds win id of previous tmux window
        self._last_session = deque(maxlen=2)  # holds session id of previous tmux session
        self.logger = logging.getLogger(__name__)
        self._block_cmd_to_processor = {
            '!list-clients': self.process_list_clients,
            '!list-sessions': self.process_list_sessions,
            '!list-all-windows': self.process_list_all_windows,
            '!list-session-windows': self.process_list_session_windows,
        }
        # note following are all async:
        self._single_cmd_to_processor = {
            '%client-session-changed': self.process_client_session_changed,
            '%session-window-changed': self.process_session_window_changed,
            '%unlinked-window-renamed': self.process_window_renamed,
            '%unlinked-window-add': self.process_add_window,
            '%unlinked-window-close': self.process_close_window,
            '%session-renamed': self.process_rename_session,
            '%sessions-changed': self.process_sessions_changed,
        }

    # note lines are defined by LIST_CLIENTS_CMD above, sans !command prefix
    def process_list_clients(self, lines):
        """
        events like:
        !list-clients {"name":"/dev/pts/1","is_ctrl":0,"active_session_id":"$0"}
        !list-clients {"name":"/dev/pts/26","is_ctrl":1,"active_session_id":"$1"}

        """
        clients = {}
        for line in lines:
            # line = re.sub(r'("[\s\w]*)"([\s\w]*")',r"\1\'\2", line)  # escape illegal double-quotes
            client = json.loads(line)

            # assign first non-ctr client as the active one. TODO what to do in case of multiple clients?
            if client['is_ctrl'] == 0:
                self.client = client
            clients[client['name']] = client
        self._clients = clients
        # print('SETTING clients: {0}'.format(self._clients))


    def process_list_sessions(self, lines):
        """
        events like:
        !list-sessions {"id": "$1", "name":"lean","active_window_id":"@4"}
        !list-sessions {"id": "$0", "name":"main","active_window_id":"@0"}
        """
        # do not filter out ignored sessions here; it's easier to keep tracking
        # its state and filter it out when rft actually queries state
        self._sessions = [json.loads(line) for line in lines]


    def process_list_all_windows(self, lines):
        """
        events like:
        !list-all-windows {id:"@1","name":"web","is_active":0,"index":1,"session_id":"$1"}
        !list-all-windows {id:"@2","name":"api","is_active":0,"index":1,"session_id":"$2"}
        """
        self._windows = [json.loads(line) for line in lines]
        # print(f'ALL private windows: {self._windows}')


    def process_list_session_windows(self, lines):
        """
        events like:
        !list-session-windows {id:"@1","name":"web","is_active":0,"index":1,"session_id":"$1"}
        !list-session-windows {id:"@2","name":"api","is_active":0,"index":2,"session_id":"$1"}
        """
        windows = [json.loads(line) for line in lines]
        session_id = windows[0]['session_id']
        self._windows = [w for w in self._windows if w['session_id'] != session_id].extend(windows)


    async def process_client_session_changed(self, line):
        """
        fired for:
        - changing session in client
        - note this is also the only event we get when launching a new client!

        events like:
        %client-session-changed /dev/pts/1 $2 work
        %client-session-changed /dev/pts/1 $0 main
        """
        line_split = line.split()
        client_id = line_split[0]

        if client_id in self._clients:
            client = self._clients[client_id]
            session_id = line_split[1]
            client['active_session_id'] = session_id

            if self.client and self.client['name'] == client_id:
                if (session := self.get_session(session_id)):  # TODO: likely null e.g. when launching new session, meaning state lags when new session is created
                    self._handle_last_win(session['active_window_id'])
                    self._handle_last_sess(session['id'])
        else:
            # likely new client, gotta add:
            await self._register_clients()


    async def process_session_window_changed(self, line):
        """
        fired for:
        - changing window within session
        - moving window order, e.g. when firing [swap-window -d -t +1] - note we lose the ordering in our state!
                                                                         this is why we re-regsiter windows
          - note without the -d flag _no_ events are fired
          - see https://github.com/orgs/tmux/discussions/4230 on the subject

        events like:
        %session-window-changed $0 @8
        """
        line_split = line.split()
        session_id = line_split[0]
        window_id = line_split[1]
        if (session := self.get_session(session_id)):
            session['active_window_id'] = window_id

        self._handle_last_win(window_id)
        # note this window query is to make sure we have latest index info:
        # await self.send_tmux_command(LIST_SESSIONS_CMD.format(session_id))
        await self._register_windows()  # just get all windows, should be nonexistent overhead


    # TODO: what about %window-renamed? never saw it, but it's in manual
    async def process_window_renamed(self, line):
        """
        events like:
        %unlinked-window-renamed @6 i3-new
        """
        line_split = line.split(' ', 1)
        if (window := self.get_window(line_split[0])):
            window['name'] = line_split[1]

    async def process_add_window(self, line):
        """
        events like:
        %unlinked-window-add @11
        """
        await self._register_windows()


    async def process_close_window(self, window_id):
        """
        events like:
        %unlinked-window-close @12
        """
        await self._register_windows()

        #  note we don't do the following anymore, as we need updated window_ids!:
        # window = next((w for w in self._windows if w['id'] == window_id), None)
        # self._windows.remove(window)

        # or alternatively:
        # self._windows = [w for w in self._windows if w['id'] != window_id]


    async def process_rename_session(self, line):
        """
        events like:
        %session-renamed $0 main-new
        """
        line_split = line.split(' ', 1)
        if (session := self.get_session(line_split[0])):
            session['name'] = line_split[1]


    # this seems to be invoked both with session creation & killing
    async def process_sessions_changed(self):
        """
        %sessions-changed
        """
        await self._register_sessions()


    # TODO: what if window part of ignored_sessions?
    def _handle_last_win(self, window_id):
        # print(f'pre-add Q: {self._last_window}')
        if not self._last_window or self._last_window[-1] != window_id:
            self._last_window.extend([window_id])
        # print(f'post-add Q: {self._last_window}')


    # TODO: what if ignored_session?
    def _handle_last_sess(self, session_id):
        # print(f'pre-add Q: {self._last_session}')
        if not self._last_session or self._last_session[-1] != session_id:
            self._last_session.extend([session_id])
        # print(f'post-add Q: {self._last_session}')


    async def init(self):
        if self._tmux_proc is None:
            self.logger.error('tmux control client has not been started, cannot init(); terminating...')
            raise TerminateTaskGroup(4)
        await self._register_clients()
        await self._register_sessions()
        await self._register_windows()


        await asyncio.sleep(0.15)  # allow state to be hydrated
        self._hydrate_state(self._conf.get('state', {}).get('tmux'))
        self._init_last_window_session()


    def _hydrate_state(self, state):
        if state and type(state) == dict:
            self._last_window.extend(state.get('last_window', []))
            self._last_session.extend(state.get('last_session', []))


    def get_state(self):
        return {
                'last_window': list(self._last_window),
                'last_session': list(self._last_session)
                }


    def _init_last_window_session(self):
        if (session := self.get_current_session()):
            self._handle_last_sess(session['id'])
            self._handle_last_win(session['active_window_id'])


    async def run_tmux_cc(self):
        self._tmux_proc = await asyncio.create_subprocess_exec(
            *self._conf['tmux_cc_cmd'],
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )
        await self.process_tmux_cc()


    async def process_tmux_cc(self):
        in_block = False
        current_cmd = None
        previous_cmd = None
        cmd_lines = []
        line = await self._tmux_proc.stdout.readline()

        # TODO: perhapse while True?
        while line:
            line = line.decode().rstrip('\n')
            # print(f'TMUX_OUT: [{line}]')
            line_split = line.split(' ', 1)
            current_cmd = line_split[0]

            # print(f'current cmd [{current_cmd}]')
            if current_cmd in self._single_cmd_to_processor:
                await self._single_cmd_to_processor[current_cmd](*line_split[1:])
            elif in_block:
                if current_cmd in self._block_cmd_to_processor:
                    # cmd_lines.append(line_split[1])
                    cmd_lines.append(*line_split[1:])
                    # alternatively: line.removeprefix('prfx')
                    #                re.sub(r'^{0}\s*'.format(re.escape('%list-clients')), '', line)
                elif current_cmd == '%end':
                    if cmd_lines:
                        # print(f'about to call proc {previous_cmd}')
                        self._block_cmd_to_processor[previous_cmd](cmd_lines)
                        cmd_lines = []
                    in_block = False
                elif current_cmd == '%error':
                    # e.g. previous line would be 'no sessions' if server is not running
                    self.logger.error('%error received')
                    cmd_lines = []  # just in case
                    in_block = False
            elif current_cmd == '%begin':
                in_block = True
            elif current_cmd == '%exit':
                self.logger.warning('%exit received, terminating...')
                raise TerminateTaskGroup(3)

            previous_cmd = current_cmd
            line = await self._tmux_proc.stdout.readline()


    async def send_tmux_command(self, cmd):
        if self._tmux_proc is None:
            self.logger.error('tmux control client has not been started, cannot send command; terminating...')
            raise TerminateTaskGroup(4)

        # print(f'about to send_tmux_command [{cmd}]')
        command = f'{ cmd }\n'.encode()
        self._tmux_proc.stdin.write(command)
        await self._tmux_proc.stdin.drain()


    async def _register_clients(self) -> None:
        await self.send_tmux_command(LIST_CLIENTS_CMD)

    async def _register_sessions(self) -> None:
        await self.send_tmux_command(LIST_SESSIONS_CMD)

    async def _register_windows(self) -> None:
        await self.send_tmux_command(LIST_ALL_WINDOWS_CMD)


    def get_sessions(self) -> list:
        return [s for s in self._sessions if s['name'] not in self._conf['ignored_sessions']]

    def get_windows_for_session_name(self, session_name) -> list:
        session_id = next((s['id'] for s in self._sessions if s['name'] == session_name), None)
        return self.get_windows_for_session_id(session_id)

    def get_windows_for_session_id(self, session_id) -> list:
        return [w for w in self._windows if w['session_id'] == session_id]

    def get_windows(self) -> list:
        whitelisted_sess_ids = [s['id'] for s in self._sessions if s['name'] not in self._conf['ignored_sessions']]
        return [w for w in self._windows if w['session_id'] in whitelisted_sess_ids]

    def get_session(self, session_id):
        return next((s for s in self._sessions if s['id'] == session_id), None)

    def get_last_window(self):
        if self._last_window:
            return self.get_window(self._last_window[0])
        return None

    def get_last_session(self):
        if self._last_session:
            return self.get_session(self._last_session[0])
        return None

    def get_window(self, window_id):
        return next((w for w in self._windows if w['id'] == window_id), None)

    async def switch_to_window(self, window) -> None:
        if self.client and window:
            await self.send_tmux_command(SWITCH_TO_CLIENT_CMD.format(self.client['name'], f'{window["session_id"]}:{window["id"]}'))

    async def switch_to_session(self, session) -> None:
        if self.client and session:
            await self.send_tmux_command(SWITCH_TO_CLIENT_CMD.format(self.client['name'], session['id']))

    # TODO: deprecated
    def select_window(self, win_name) -> None:
        cmd = ['tmux', 'select-window', '-t', win_name]
        call(cmd)

    async def kill_window(self, window) -> None:
        if window:
            await self.send_tmux_command(KILL_WINDOW_CMD.format(f'{window["session_id"]}:{window["id"]}'))

    def attach_session(self, session_name) -> None:
        cmd = ['tmux', 'attach-session', '-t', session_name]
        call(cmd)

    # current session as in attached to _a_ client.
    # # TODO: what if current session is blacklisted/ignored? does it even matter here?
    def get_current_session(self) -> dict|None:
        return None if self.client is None else self.get_session(self.client['active_session_id'])

        # for client in self._clients.values():
            # if client['is_ctrl'] == 1: continue
            # session = (None if client is None else
                    # next((s for s in self._sessions if s['id'] == client['active_session_id']), None))
            # if session is not None: return session

        # note we get first random client:
        # client = next(iter(self._clients.values()), None)
        # return (None if client is None else
                # next((s for s in self._sessions if s['id'] == client['active_session_id']), None))

