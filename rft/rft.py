#!/usr/bin/env python
# -*- coding: utf-8 -*-

from tmux import tmux
import logging
import json
import os
import rofi
import subprocess
logging.basicConfig(level=logging.INFO)


class RFT(object):
    """Abstraction to interface with rofi, tmux, tmuxinator."""

    def __init__(self, debug=False):
        """Initialize ."""
        self._rofi = rofi.Rofi()
        self._sessions = None
        self._cur_tmux_s = None
        self.logger = logging.getLogger(__name__)
        if debug:
            self.logger.setLevel(logging.DEBUG)

        homedir = os.environ.get('HOME')
        self._cache_f = os.path.join(homedir, '.rft.cache')
        self._cache = self._load_cache()
        self._config = self._load_config(os.path.join(homedir, '.rft'))
        self._tmux = tmux(self._config, logger_lvl = self.logger.getEffectiveLevel())
        if self._config.get('wm') == 'i3':
            from i3wm import i3WM
            self._wm = i3WM(self._config, logger_lvl = self.logger.getEffectiveLevel())
        else:
            self._wm = None

    def _load_config(self, conf_file_loc) -> None:
        """Load json config file ~/.rft.

        Currently supported window managers: 'i3'

        """
        conf = {
                'wm': 'i3',
                'tmux_title_rgx': '{session}',
                'ignored_sessions': []
        }
        conf.update(_read_dict_from_file(conf_file_loc))
        self.logger.debug('effective config: {}'.format(conf))
        return conf


    def _load_cache(self) -> None:
        """Load last tmux sessions and window cache."""

        cache = {
                'last_tmux_s': None,
                'last_tmux_w': None
        }
        cache.update(_read_dict_from_file(self._cache_f))
        self.logger.debug('loaded cache: {}'.format(cache))
        return cache

    def _write_cache(self) -> None:
        """Write cache."""
        try:
            with open(self._cache_f, 'w') as f:
                f.write(
                    json.dumps(
                        self._cache,
                        indent=4,
                        sort_keys=True,
                        separators=(',', ': '),
                        ensure_ascii=False))
            self.logger.debug('wrote cache: {}'.format(self._cache))
        except IOError as e:
            raise e

    def _get_sessions_filtered(self) -> list:
        """Return list of tmux sessions, sans ones explicitly blacklisted
        by self._config.ignored_sessions"""
        return [s for s in self._libts.list_sessions() if s.name not in self._config['ignored_sessions']]


    # def _get_cur_session(self) -> libtmux.session.Session:
        # """Return reference to our current tmux session."""
        # for s in self._sessions:
            # if str(s.attached) != '0':
                # return s
        # return None

    def _get_cur_tmux_win(self) -> str:
        """Get current tmux window."""
        session = self._tmux.get_current_session()
        if not session:
            return None
        else:
            return '{}:{}:{}'.format(
                session['name'],
                session['win']['index'],
                session['win']['name'])

    def _get_tmuxinator_projects(self) -> list:
        """Get tmuxinator projects name."""
        out, err = subprocess.Popen(
            "tmuxinator list",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE).communicate()
        projects = []
        for line in out.splitlines():
            line_str = line.decode('utf-8')
            if "tmuxinator projects" in line_str:
                continue
            projects += line_str.split()
        return projects

    def _get_session_by_name(self, session_name) -> None:  #libtmux.session.Session:
        """Get libtmux.session.Session.

        :session_name: session name

        """
        if self._sessions:
            for s in self._sessions:
                if s.name == session_name:
                    return s
        return None

    def _rofi_tmuxinator(self, rofi_msg, rofi_err) -> None:
        """Launch rofi for loading a tmuxinator project.

        :rofi_msg: rofi displayed message
        :err_msg: rofi error message

        """
        projects = self._get_tmuxinator_projects()
        if projects:
            res, key = self._rofi.select(rofi_msg, projects, rofi_args=['-i'])
            if key == 0:
                out, err = subprocess.Popen(
                    "tmuxinator {}".format(projects[res]),
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE).communicate()
                # update sessions.
                self._sessions = self._get_sessions_filtered()
                session = self._get_session_by_name(projects[res])
                if not session:
                    return
                if self._wm:
                    self._wm.focus_tmux_window(self._cur_tmux_s)
                try:
                    session.attach_session()
                except libtmux.exc.LibTmuxException as e:
                    # there are no attached clients just switch instead.
                    session.switch_client()
                if self._cur_tmux_s:
                    self._cache['last_tmux_s'] = self._cur_tmux_s.name
                    self._write_cache()
        else:
            self._rofi.error(rofi_err)

    def load_tmuxinator(self) -> None:
        """Load tmuxinator project."""
        self._rofi_tmuxinator(
            rofi_msg='Tmuxinator project',
            rofi_err='There are no projects available')

    def _rofi_tmux_session(self, action, rofi_msg) -> None:
        """Launch rofi for a specific tmux session action.

        :action: 'switch', 'kill'
        :rofi_msg: rofi displayed message

        """
        if self._sessions:
            sessions_list = [s.name for s in self._sessions]
            is_tmux_win_visible = False
            if self._wm:
                self.logger.debug('resolving is_tmux_win_visible...')
                is_tmux_win_visible = self._wm.is_tmux_win_visible(self._cur_tmux_s)
                self.logger.debug('is_tmux_win_visible: {}'.format(is_tmux_win_visible))
            try:
                if is_tmux_win_visible:
                    sel = sessions_list.index(self._cache.get('last_tmux_s'))
                elif self._cur_tmux_s:
                    sel = sessions_list.index(self._cur_tmux_s.name)
                else:
                    sel = 0
            except ValueError as e:
                sel = 0
            res, key = self._rofi.select(rofi_msg, sessions_list, select=sel, rofi_args=['-i'])
            if key == 0:
                session = self._sessions[res]
                if action == 'switch':
                    if self._wm:
                        self._wm.focus_tmux_window(self._cur_tmux_s)
                    try:
                        session.switch_client()
                    except libtmux.exc.LibTmuxException as e:
                        session.attach_session()
                    if self._cur_tmux_s:
                        self._cache['last_tmux_s'] = self._cur_tmux_s.name
                        self._write_cache()
                elif action == 'kill':
                    session.kill_session()
                else:
                    self._rofi.error('This action is not implemented')
        else:
            self._rofi.error("There are no sessions yet")

    def switch_session(self) -> None:
        """Switch tmux session."""
        self._rofi_tmux_session(action='switch', rofi_msg='Switch session')

    def kill_session(self) -> None:
        """Kill tmux session."""
        self._rofi_tmux_session(action='kill', rofi_msg='Kill session')

    def _rofi_tmux_window(self, action, session_name, global_scope,
                          rofi_msg) -> None:
        """Launch rofi for a specific tmux window action.

        :action: 'switch', 'kill'
        :session_name: if it's not None, the scope is limited to this session
        :global_scope: if True, it will take into account all existent windows
        :rofi_msg: rofi displayed message

        """
        windows = None
        if session_name:
            session = self._tmux.get_session(session_name)
            windows = session['wins']
        else:
            session = self._tmux.get_current_session()
            if session:
                if global_scope:
                    windows = []
                    for s in self._tmux.get_sessions():
                        windows += s['wins']
                else:
                    windows = session['wins']

        if windows:
            windows_str = [
                "{}:{}:{}".format(w['session'], w['index'], w['name'])
                for w in windows
            ]
            is_tmux_win_visible = False
            cur_win = self._get_cur_tmux_win()
            if self._wm:
                self.logger.debug('resolving is_tmux_win_visible...')
                is_tmux_win_visible = self._wm.is_tmux_win_visible(self._tmux.get_current_session())
                self.logger.debug('is_tmux_win_visible: {}'.format(is_tmux_win_visible))
            try:
                if is_tmux_win_visible:
                    sel = windows_str.index(self._cache.get('last_tmux_w'))
                else:
                    sel = windows_str.index(cur_win)
            except ValueError as e:
                sel = 0

            res, key = self._rofi.select(rofi_msg, windows_str, select=sel, rofi_args=['-i'])
            if key == 0:
                win = windows[res]
                if action == 'switch':
                    self.logger.debug('selected: {}'.format(windows_str[res]))

                    if self._wm:
                        self._wm.focus_tmux_window(self._tmux.get_current_session())
                    try:
                        self.logger.debug('tmux switching: {}'.format(win['session']))
                        self._tmux.switch_client(win['session'])
                        self._tmux.select_window(win['name'])
                    except libtmux.exc.LibTmuxException as e:
                        # there are no attached clients yet
                        # attach if running in the shell
                        self.logger.debug('tmux attaching: {}'.format(win['session']))
                        self._tmux.attach_session(win['session'])
                    self._cache['last_tmux_w'] = cur_win
                    # also update last session accordingly:
                    if self._tmux.get_current_session():
                        self._cache['last_tmux_s'] = self._tmux.get_current_session()['name']
                        self._write_cache()
                elif action == 'kill':
                    self._tmux.kill_window(win['name'])
                else:
                    self._rofi.error('This action is not implemented')

    def switch_window(self, session_name=None, global_scope=True) -> None:
        """Switch to a window of a particular session or any session.

        :session_name: if it's not None, the scope is limited to this session
        :global_scope: if True, it will take into account all existent windows

        """
        self._rofi_tmux_window(
            action='switch',
            rofi_msg='Switch window',
            session_name=session_name,
            global_scope=global_scope)

    def kill_window(self, session_name=None, global_scope=True) -> None:
        """Kill window of a particular session or any session.

        :session_name: if it's not None, the scope is limited to this session
        :global_scope: if True, it will take into account all existent windows

        """
        self._rofi_tmux_window(
            action='kill',
            rofi_msg='Kill window',
            session_name=session_name,
            global_scope=global_scope)

def _read_dict_from_file(file_loc):
    try:
        with open(file_loc, 'r') as f:
            return json.load(f)
    except Exception as e:
        return {}

