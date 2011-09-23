# Given paths from installation
REMOTE_BASE_DIR                 = "/var/lib/cdist"
REMOTE_CONF_DIR                 = os.path.join(REMOTE_BASE_DIR, "conf")
REMOTE_OBJECT_DIR               = os.path.join(REMOTE_BASE_DIR, "object")
REMOTE_TYPE_DIR                 = os.path.join(REMOTE_CONF_DIR, "type")
REMOTE_GLOBAL_EXPLORER_DIR      = os.path.join(REMOTE_CONF_DIR, "explorer")

CODE_HEADER                     = "#!/bin/sh -e\n"
DOT_CDIST                       = ".cdist"
TYPE_PREFIX                     = "__"

def file_to_list(filename):
    """Return list from \n seperated file"""
    if os.path.isfile(filename):
        file_fd = open(filename, "r")
        lines = file_fd.readlines()
        file_fd.close()

        # Remove \n from all lines
        lines = map(lambda s: s.strip(), lines)
    else:
        lines = []

    return lines

class Path:
    """Class that handles path related configurations"""

    def __init__(self, target_host, base_dir=None):
        # Base and Temp Base 
        if home:
            self.base_dir = base_dir
        else:
            self.base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))

        self.temp_dir = tempfile.mkdtemp()

        self.conf_dir               = os.path.join(self.base_dir, "conf")
        self.cache_base_dir         = os.path.join(self.base_dir, "cache")
        self.cache_dir              = os.path.join(self.cache_base_dir, target_host)
        self.global_explorer_dir    = os.path.join(self.conf_dir, "explorer")
        self.lib_dir                = os.path.join(self.base_dir, "lib")
        self.manifest_dir           = os.path.join(self.conf_dir, "manifest")
        self.type_base_dir          = os.path.join(self.conf_dir, "type")

        self.out_dir = os.path.join(self.temp_dir, "out")
        os.mkdir(self.out_dir)

        self.global_explorer_out_dir = os.path.join(self.out_dir, "explorer")
        os.mkdir(self.global_explorer_out_dir)

        self.object_base_dir = os.path.join(self.out_dir, "object")

        # Setup binary directory + contents
        self.bin_dir = os.path.join(self.out_dir, "bin")
        os.mkdir(self.bin_dir)
        self.link_type_to_emulator()

        # List of type explorers transferred
        self.type_explorers_transferred = {}

        # objects
        self.objects_prepared = []

        self.remote_user = remote_user

        # Mostly static, but can be overwritten on user demand
        if initial_manifest:
            self.initial_manifest = initial_manifest
        else:
            self.initial_manifest = os.path.join(self.manifest_dir, "init")

    def cleanup(self):
        # Do not use in __del__:
        # http://docs.python.org/reference/datamodel.html#customization
        # "other globals referenced by the __del__() method may already have been deleted 
        # or in the process of being torn down (e.g. the import machinery shutting down)"
        #
        log.debug("Saving" + self.temp_dir + "to " + self.cache_dir)
        # Remove previous cache
        if os.path.exists(self.cache_dir):
            shutil.rmtree(self.cache_dir)
        shutil.move(self.temp_dir, self.cache_dir)


    def remote_mkdir(self, directory):
        """Create directory on remote side"""
        self.run_or_fail(["mkdir", "-p", directory], remote=True)

    def remote_cat(filename):
        """Use cat on the remote side for output"""
        self.run_or_fail(["cat", filename], remote=True)

    def shell_run_or_debug_fail(self, script, *args, **kargs):
        # Manually execute /bin/sh, because sh -e does what we want
        # and sh -c -e does not exit if /bin/false called
        args[0][:0] = [ "/bin/sh", "-e" ]

        remote = False
        if "remote" in kargs:
            if kargs["remote"]:
                args[0][:0] = self.remote_prefix
                remote = true

            del kargs["remote"]

        log.debug("Shell exec cmd: %s", args)
        log.debug("Shell exec env: %s", kargs['env'])
        try:
            subprocess.check_call(*args, **kargs)
        except subprocess.CalledProcessError:
            log.error("Code that raised the error:\n")
            if remote:
                remote_cat(script)
            else:
                script_fd = open(script)
                print(script_fd.read())
                script_fd.close()

            exit_error("Command failed (shell): " + " ".join(*args))
        except OSError as error:
            exit_error(" ".join(*args) + ": " + error.args[1])

    def run_or_fail(self, *args, **kargs):
        if "remote" in kargs:
            if kargs["remote"]:
                args[0][:0] = self.remote_prefix

            del kargs["remote"]

        log.debug("Exec: " + " ".join(*args))
        try:
            subprocess.check_call(*args, **kargs)
        except subprocess.CalledProcessError:
            exit_error("Command failed: " + " ".join(*args))
        except OSError as error:
            exit_error(" ".join(*args) + ": " + error.args[1])


    def remove_remote_dir(self, destination):
        self.run_or_fail(["rm", "-rf",  destination], remote=True)

    def transfer_dir(self, source, destination):
        """Transfer directory and previously delete the remote destination"""
        self.remove_remote_dir(destination)
        self.run_or_fail(["scp", "-qr", source, 
                                self.remote_user + "@" + 
                                self.target_host + ":" + 
                                destination])

    def transfer_file(self, source, destination):
        """Transfer file"""
        self.run_or_fail(["scp", "-q", source, 
                                self.remote_user + "@" +
                                self.target_host + ":" +
                                destination])

    def global_explorer_output_path(self, explorer):
        """Returns path of the output for a global explorer"""
        return os.path.join(self.global_explorer_out_dir, explorer)

    def type_explorer_output_dir(self, cdist_object):
        """Returns and creates dir of the output for a type explorer"""
        dir = os.path.join(self.object_dir(cdist_object), "explorer")
        if not os.path.isdir(dir):
            os.mkdir(dir)

        return dir

    def remote_global_explorer_path(self, explorer):
        """Returns path to the remote explorer"""
        return os.path.join(REMOTE_GLOBAL_EXPLORER_DIR, explorer)

    def list_global_explorers(self):
        """Return list of available explorers"""
        return os.listdir(self.global_explorer_dir)

    def list_type_explorers(self, type):
        """Return list of available explorers for a specific type"""
        dir = self.type_dir(type, "explorer")
        if os.path.isdir(dir):
            list = os.listdir(dir)
        else:
            list = []

        log.debug("Explorers for %s in %s: %s", type, dir, list)

        return list

    def list_types(self):
        return os.listdir(self.type_base_dir)

    def list_object_paths(self, starting_point):
        """Return list of paths of existing objects"""
        object_paths = []

        for content in os.listdir(starting_point):
            full_path = os.path.join(starting_point, content)
            if os.path.isdir(full_path):
                object_paths.extend(self.list_object_paths(starting_point = full_path))

            # Directory contains .cdist -> is an object
            if content == DOT_CDIST:
                object_paths.append(starting_point)

        return object_paths

    def get_type_from_object(self, cdist_object):
        """Returns the first part (i.e. type) of an object"""
        return cdist_object.split(os.sep)[0]

    def get_object_id_from_object(self, cdist_object):
        """Returns everything but the first part (i.e. object_id) of an object"""
        return os.sep.join(cdist_object.split(os.sep)[1:])

    def object_dir(self, cdist_object):
        """Returns the full path to the object (including .cdist)"""
        return os.path.join(self.object_base_dir, cdist_object, DOT_CDIST)

    def remote_object_dir(self, cdist_object):
        """Returns the remote full path to the object (including .cdist)"""
        return os.path.join(REMOTE_OBJECT_DIR, cdist_object, DOT_CDIST)

    def object_parameter_dir(self, cdist_object):
        """Returns the dir to the object parameter"""
        return os.path.join(self.object_dir(cdist_object), "parameter")

    def remote_object_parameter_dir(self, cdist_object):
        """Returns the remote dir to the object parameter"""
        return os.path.join(self.remote_object_dir(cdist_object), "parameter")

    def object_code_paths(self, cdist_object):
        """Return paths to code scripts of object"""
        return [os.path.join(self.object_dir(cdist_object), "code-local"),
                  os.path.join(self.object_dir(cdist_object), "code-remote")]

    def list_objects(self):
        """Return list of existing objects"""

        objects = []
        if os.path.isdir(self.object_base_dir):
            object_paths = self.list_object_paths(self.object_base_dir)

            for path in object_paths:
                objects.append(os.path.relpath(path, self.object_base_dir))

        return objects

    def type_dir(self, type, *args):
        """Return directory the type"""
        return os.path.join(self.type_base_dir, type, *args)

    def remote_type_explorer_dir(self, type):
        """Return remote directory that holds the explorers of a type"""
        return os.path.join(REMOTE_TYPE_DIR, type, "explorer")

    def transfer_object_parameter(self, cdist_object):
        """Transfer the object parameter to the remote destination"""
        # Create base path before using mkdir -p
        self.remote_mkdir(self.remote_object_parameter_dir(cdist_object))

        # Synchronise parameter dir afterwards
        self.transfer_dir(self.object_parameter_dir(cdist_object), 
                                self.remote_object_parameter_dir(cdist_object))

    def transfer_global_explorers(self):
        """Transfer the global explorers"""
        self.remote_mkdir(REMOTE_GLOBAL_EXPLORER_DIR)
        self.transfer_dir(self.global_explorer_dir, REMOTE_GLOBAL_EXPLORER_DIR)

    def transfer_type_explorers(self, type):
        """Transfer explorers of a type, but only once"""
        if type in self.type_explorers_transferred:
            log.debug("Skipping retransfer for explorers of %s", type)
            return
        else:
            # Do not retransfer
            self.type_explorers_transferred[type] = 1

        src = self.type_dir(type, "explorer")
        remote_base = os.path.join(REMOTE_TYPE_DIR, type)
        dst = self.remote_type_explorer_dir(type)

        # Only continue, if there is at least the directory
        if os.path.isdir(src):
            # Ensure that the path exists
            self.remote_mkdir(remote_base)
            self.transfer_dir(src, dst)


    def link_type_to_emulator(self):
        """Link type names to cdist-type-emulator"""
        source = os.path.abspath(sys.argv[0])
        for type in self.list_types():
            destination = os.path.join(self.bin_dir, type)
            log.debug("Linking %s to %s", source, destination)
            os.symlink(source, destination)

    def run_global_explores(self):
        """Run global explorers"""
        explorers = self.list_global_explorers()
        if(len(explorers) == 0):
            exit_error("No explorers found in", self.global_explorer_dir)

        self.transfer_global_explorers()
        for explorer in explorers:
            output = self.global_explorer_output_path(explorer)
            output_fd = open(output, mode='w')
            cmd = []
            cmd.append("__explorer=" + REMOTE_GLOBAL_EXPLORER_DIR)
            cmd.append(self.remote_global_explorer_path(explorer))

            self.run_or_fail(cmd, stdout=output_fd, remote=True)
            output_fd.close()

    def run_type_explorer(self, cdist_object):
        """Run type specific explorers for objects"""
        # Based on bin/cdist-object-explorer-run

        # Transfering explorers for this type
        type = self.get_type_from_object(cdist_object)
        self.transfer_type_explorers(type)

        cmd = []
        cmd.append("__explorer="        + REMOTE_GLOBAL_EXPLORER_DIR)
        cmd.append("__type_explorer=" + self.remote_type_explorer_dir(type))
        cmd.append("__object="          + self.remote_object_dir(cdist_object))
        cmd.append("__object_id="      + self.get_object_id_from_object(cdist_object))
        cmd.append("__object_fq="      + cdist_object)

        # Need to transfer at least the parameters for objects to be useful
        self.transfer_object_parameter(cdist_object)

        explorers = self.list_type_explorers(type)
        for explorer in explorers:
            remote_cmd = cmd + [os.path.join(self.remote_type_explorer_dir(type), explorer)]
            output = os.path.join(self.type_explorer_output_dir(cdist_object), explorer)
            output_fd = open(output, mode='w')
            log.debug("%s exploring %s using %s storing to %s", 
                        cdist_object, explorer, remote_cmd, output)
                        
            self.run_or_fail(remote_cmd, stdout=output_fd, remote=True)
            output_fd.close()

    def init_deploy(self):
        """Ensure the base directories are cleaned up"""
        log.debug("Creating clean directory structure")

        self.remove_remote_dir(REMOTE_BASE_DIR)
        self.remote_mkdir(REMOTE_BASE_DIR)

    def run_initial_manifest(self):
        """Run the initial manifest"""
        env = {  "__manifest" : self.manifest_dir }
        self.run_manifest(self.initial_manifest, extra_env=env)

    def run_type_manifest(self, cdist_object):
        """Run manifest for a specific object"""
        type = self.get_type_from_object(cdist_object)
        manifest = self.type_dir(type, "manifest")
        
        log.debug("%s: Running %s", cdist_object, manifest)
        if os.path.exists(manifest):
            env = {  "__object" :    self.object_dir(cdist_object), 
                        "__object_id": self.get_object_id_from_object(cdist_object),
                        "__object_fq": cdist_object,
                        "__type":        self.type_dir(type)
                    }
            self.run_manifest(manifest, extra_env=env)

    def run_manifest(self, manifest, extra_env=None):
        """Run a manifest"""
        log.debug("Running manifest %s, env=%s", manifest, extra_env)
        env = os.environ.copy()
        env['PATH'] = self.bin_dir + ":" + env['PATH']

        # Information required in every manifest
        env['__target_host']     = self.target_host
        env['__global']            = self.out_dir
        
        # Legacy stuff to make cdist-type-emulator work
        env['__cdist_core_dir']         = os.path.join(self.base_dir, "core")
        env['__cdist_local_base_dir'] = self.temp_dir

        # Submit information to new type emulator
        env['__cdist_manifest']         = manifest
        env['__cdist_type_base_dir']  = self.type_base_dir

        # Other environment stuff
        if extra_env:
            env.update(extra_env)

        self.shell_run_or_debug_fail(manifest, [manifest], env=env)

    def object_run(self, cdist_object, mode):
        """Run gencode or code for an object"""
        log.debug("Running %s from %s", mode, cdist_object)
        file=os.path.join(self.object_dir(cdist_object), "require")
        requirements = file_to_list(file)
        type = self.get_type_from_object(cdist_object)
            
        for requirement in requirements:
            log.debug("Object %s requires %s", cdist_object, requirement)
            self.object_run(requirement, mode=mode)

        #
        # Setup env Variable:
        # 
        env = os.environ.copy()
        env['__target_host'] = self.target_host
        env['__global']        = self.out_dir
        env["__object"]        = self.object_dir(cdist_object)
        env["__object_id"]    = self.get_object_id_from_object(cdist_object)
        env["__object_fq"]    = cdist_object
        env["__type"]          = self.type_dir(type)

        if mode == "gencode":
            paths = [
                self.type_dir(type, "gencode-local"),
                self.type_dir(type, "gencode-remote")
            ]
            for bin in paths:
                if os.path.isfile(bin):
                    # omit "gen" from gencode and use it for output base
                    outfile=os.path.join(self.object_dir(cdist_object), 
                        os.path.basename(bin)[3:])

                    outfile_fd = open(outfile, "w")

                    # Need to flush to ensure our write is done before stdout write
                    outfile_fd.write(CODE_HEADER)
                    outfile_fd.flush()

                    self.shell_run_or_debug_fail(bin, [bin], env=env, stdout=outfile_fd)
                    outfile_fd.close()

                    status = os.stat(outfile)

                    # Remove output if empty, else make it executable
                    if status.st_size == len(CODE_HEADER):
                        os.unlink(outfile)
                    else:
                        # Add header and make executable - identically to 0o700
                        os.chmod(outfile, stat.S_IXUSR | stat.S_IRUSR | stat.S_IWUSR)

                        # Mark object as changed
                        open(os.path.join(self.object_dir(cdist_object), "changed"), "w").close()


        if mode == "code":
            local_dir    = self.object_dir(cdist_object)
            remote_dir  = self.remote_object_dir(cdist_object)

            bin = os.path.join(local_dir, "code-local")
            if os.path.isfile(bin):
                self.run_or_fail([bin], remote=False)
                

            local_remote_code = os.path.join(local_dir, "code-remote")
            remote_remote_code = os.path.join(remote_dir, "code-remote")
            if os.path.isfile(local_remote_code):
                self.transfer_file(local_remote_code, remote_remote_code)
                self.run_or_fail([remote_remote_code], remote=True)
                
    def stage_prepare(self):
        """Do everything for a deploy, minus the actual code stage"""
        self.init_deploy()
        self.run_global_explores()
        self.run_initial_manifest()
        
        old_objects = []
        objects = self.list_objects()

        # Continue process until no new objects are created anymore
        while old_objects != objects:
            log.debug("Prepare stage")
            old_objects = list(objects)
            for cdist_object in objects:
                if cdist_object in self.objects_prepared:
                    log.debug("Skipping rerun of object %s", cdist_object)
                    continue
                else:
                    self.run_type_explorer(cdist_object)
                    self.run_type_manifest(cdist_object)
                    self.objects_prepared.append(cdist_object)

            objects = self.list_objects()

    def stage_run(self):
        """The final (and real) step of deployment"""
        log.debug("Actual run objects")
        # Now do the final steps over the existing objects
        for cdist_object in self.list_objects():
            log.debug("Run object: %s", cdist_object)
            self.object_run(cdist_object, mode="gencode")
            self.object_run(cdist_object, mode="code")

    def deploy_to(self):
        """Mimic the old deploy to: Deploy to one host"""
        log.info("Deploying to " + self.target_host)
        time_start = datetime.datetime.now()

        self.stage_prepare()
        self.stage_run()

        time_end = datetime.datetime.now()
        duration = time_end - time_start
        log.info("Finished run of %s in %s seconds", 
            self.target_host,
            duration.total_seconds())

    def deploy_and_cleanup(self):
        """Do what is most often done: deploy & cleanup"""
        self.deploy_to()
        self.cleanup()

def banner(args):
    """Guess what :-)"""
    print(BANNER)
    sys.exit(0)

def config(args):
    """Configure remote system"""
    process = {}

    time_start = datetime.datetime.now()

    for host in args.host:
        c = Cdist(host, initial_manifest=args.manifest, home=args.cdist_home, debug=args.debug)
        if args.parallel:
            log.debug("Creating child process for %s", host)
            process[host] = multiprocessing.Process(target=c.deploy_and_cleanup)
            process[host].start()
        else:
            c.deploy_and_cleanup()

    if args.parallel:
        for p in process.keys():
            log.debug("Joining %s", p)
            process[p].join()

    time_end = datetime.datetime.now()
    log.info("Total processing time for %s host(s): %s", len(args.host),
                (time_end - time_start).total_seconds())

def install(args):
    """Install remote system"""
    process = {}

def emulator():
    """Emulate type commands (i.e. __file and co)"""
    type = os.path.basename(sys.argv[0])
    type_dir = os.path.join(os.environ['__cdist_type_base_dir'], type)
    param_dir = os.path.join(type_dir, "parameter")
    global_dir = os.environ['__global']
    object_source = os.environ['__cdist_manifest']

    parser = argparse.ArgumentParser(add_help=False)

    # Setup optional parameters
    for parameter in file_to_list(os.path.join(param_dir, "optional")):
        argument = "--" + parameter
        parser.add_argument(argument, action='store', required=False)

    # Setup required parameters
    for parameter in file_to_list(os.path.join(param_dir, "required")):
        argument = "--" + parameter
        parser.add_argument(argument, action='store', required=True)

    # Setup positional parameter, if not singleton

    if not os.path.isfile(os.path.join(type_dir, "singleton")):
        parser.add_argument("object_id", nargs=1)

    # And finally verify parameter
    args = parser.parse_args(sys.argv[1:])

    # Setup object_id
    if os.path.isfile(os.path.join(type_dir, "singleton")):
        object_id = "singleton"
    else:
        object_id = args.object_id[0]
        del args.object_id

        # FIXME: / hardcoded - better portable solution available?
        if object_id[0] == '/':
            object_id = object_id[1:]

    # FIXME: verify object id
    log.debug(args)

    object_dir = os.path.join(global_dir, "object", type,
                            object_id, DOT_CDIST)
    param_out_dir = os.path.join(object_dir, "parameter")

    object_source_file = os.path.join(object_dir, "source")

    if os.path.exists(param_out_dir):
        object_exists = True
        old_object_source_fd = open(object_source_file, "r")
        old_object_source = old_object_source_fd.readlines()
        old_object_source_fd.close()

    else:
        object_exists = False
        try:
            os.makedirs(param_out_dir, exist_ok=True)
        except OSError as error:
            exit_error(param_out_dir + ": " + error.args[1])

    # Record parameter
    params = vars(args)
    for param in params:
        value = getattr(args, param)
        if value:
            file = os.path.join(param_out_dir, param)
            log.debug(file + "<-" + param + " = " + value)

            # Already exists, verify all parameter are the same
            if object_exists:
                if not os.path.isfile(file):
                    print("New parameter + " + param + "specified, aborting")
                    print("Source = " + old_object_source + "new =" + object_source)
                    sys.exit(1)
                else:
                    param_fd = open(file, "r")
                    param_old = param_fd.readlines()
                    param_fd.close()
                    
                    if(param_old != param):
                        print("Parameter " + param + " differs: " + " ".join(param_old) + " vs. " + param)
                        print("Sources: " + " ".join(old_object_source) + " and " + object_source)
                        sys.exit(1)
            else:
                param_fd = open(file, "w")
                param_fd.writelines(value)
                param_fd.close()

    # Record requirements
    if "__require" in os.environ:
        requirements = os.environ['__require']
        print(object_id + ":Writing requirements: " + requirements)
        require_fd = open(os.path.join(object_dir, "require"), "a")
        require_fd.writelines(requirements.split(" "))
        require_fd.close()

    # Record / Append source
    source_fd = open(os.path.join(object_dir, "source"), "a")
    source_fd.writelines(object_source)
    source_fd.close()

    # sys.exit(1)
    print("Finished " + type + "/" + object_id + repr(params))


def commandline():
    """Parse command line"""
    # Construct parser others can reuse
    parser = {}
    # Options _all_ parsers have in common
    parser['most'] = argparse.ArgumentParser(add_help=False)
    parser['most'].add_argument('-d', '--debug',
        help='Set log level to debug', action='store_true')

    # Main subcommand parser
    parser['main'] = argparse.ArgumentParser(description='cdist ' + VERSION)
    parser['main'].add_argument('-V', '--version',
        help='Show version', action='version',
        version='%(prog)s ' + VERSION)
    parser['sub'] = parser['main'].add_subparsers(title="Commands")

    # Banner
    parser['banner'] = parser['sub'].add_parser('banner', 
        add_help=False)
    parser['banner'].set_defaults(func=banner)

    # Config and install (common stuff)
    parser['configinstall'] = argparse.ArgumentParser(add_help=False)
    parser['configinstall'].add_argument('host', nargs='+',
        help='one or more hosts to operate on')
    parser['configinstall'].add_argument('-c', '--cdist-home',
         help='Change cdist home (default: .. from bin directory)',
         action='store')
    parser['configinstall'].add_argument('-i', '--initial-manifest', 
         help='Path to a cdist manifest',
         dest='manifest', required=False)
    parser['configinstall'].add_argument('-p', '--parallel',
         help='Operate on multiple hosts in parallel',
         action='store_true', dest='parallel')
    parser['configinstall'].add_argument('-s', '--sequential',
         help='Operate on multiple hosts sequentially (default)',
         action='store_false', dest='parallel')

    # Config
    parser['config'] = parser['sub'].add_parser('config',
        parents=[parser['most'], parser['configinstall']])
    parser['config'].set_defaults(func=config)

    # Install
    parser['install'] = parser['sub'].add_parser('install',
        parents=[parser['most'], parser['configinstall']])
    parser['install'].set_defaults(func=install)

    for p in parser:
        parser[p].epilog = "Get cdist at http://www.nico.schottelius.org/software/cdist/"

    args = parser['main'].parse_args(sys.argv[1:])

    # Most subcommands have --debug, so handle it here
    if 'debug' in args:
        if args.debug:
            logging.root.setLevel(logging.DEBUG)
    log.debug(args)

    args.func(args)

if __name__ == "__main__":
    try:
        if re.match(TYPE_PREFIX, os.path.basename(sys.argv[0])):
            emulator()
        else:
            commandline()
    except KeyboardInterrupt:
         sys.exit(0)
