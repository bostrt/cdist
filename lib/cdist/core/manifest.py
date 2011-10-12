# -*- coding: utf-8 -*-
#
# 2011 Steven Armstrong (steven-cdist at armstrong.cc)
# 2011 Nico Schottelius (nico-cdist at schottelius.org)
#
# This file is part of cdist.
#
# cdist is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# cdist is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with cdist. If not, see <http://www.gnu.org/licenses/>.
#
#

import logging
import os

import cdist

log = logging.getLogger(__name__)


'''
common:
    runs only locally, does not need remote

    env:
        PATH: prepend directory with type emulator symlinks == local.bin_path
        __target_host: the target host we are working on
        __global: full qualified path to the global output dir == local.out_path
        __cdist_manifest: full qualified path of the manifest == script
        __cdist_type_base_path: full qualified path to the directory where types are defined for use in type emulator
            == local.type_base_path

initial manifest is:
    script: full qualified path to the initial manifest

    env:
        __manifest: path to .../conf/manifest/ == local.manifest_path

    creates: new objects through type emulator

type manifeste is:
    script: full qualified path to the type manifest

    env:
        __object: full qualified path to the object's dir
        __object_id: the objects id
        __object_fq: full qualified object id, iow: $type.name + / + object_id
        __type: full qualified path to the type's dir

    creates: new objects through type emulator
'''


class Manifest(object):
    """Represents a cdist manifest.

    """
    def __init__(self, target_host, local):
        self.target_host = target_host
        self.local = local
        self.env = {
            'PATH': "%s:%s" % (self.local.bin_path, os.environ['PATH']),
            '__target_host': self.target_host,
            '__global': self.local.out_path,
            '__cdist_type_base_path': self.local.type_base_path, # for use in type emulator
        }

    def run_initial_manifest(self, script):
        env = os.environ.copy()
        env.update(self.env)
        env['__manifest'] = self.local.manifest_path
        return self.local.run_script(script, env=env)

    def run_type_manifest(self, cdist_object):
        env = os.environ.copy()
        env.update(self.env)
        env.update({
            '__object': cdist_object.absolute_path,
            '__object_id': cdist_object.object_id,
            '__object_fq': cdist_object.path,
            '__type': cdist_object.type.absolute_path,
        })
        script = os.path.join(self.local.type_base_path, cdist_object.type.manifest_path)
        return self.local.run_script(script, env=env)