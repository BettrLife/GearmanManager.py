#!/usr/bin/python
from __future__ import print_function
from gmtasks.jsonclass  import GearmanWorker
from gmtasks            import GearmanTaskServer, Task
import sys, os, pwd, grp, daemon, signal, logging
from pidfile import PidFile
from glob import glob
import functools
from multiprocessing import active_children
import imp

def parseArgs(args=None):
    """Parses arguments for the config from the command line."""
    import argparse
    parser = argparse.ArgumentParser(description="Serves assorted Python gearman jobs.")
    parser.add_argument("-P", "--pid-file", default="/run/gearman/python-manager.pid", help="The path to use for the PID file.")
    parser.add_argument("-w", "--worker-dir", help="The directory to look for worker files in.")
    parser.add_argument("--max-workers", help="The maximum number of workers to provide.  Defaults to number of CPUs.")
    parser.add_argument("-H", "--host", default=["127.0.0.1:4730"], action="append", help="The gearman server to use.")
    parser.add_argument("-l", "--log-file", default="stderr", help="The log file to use, or 'stderr' for stderr, or 'syslog' for syslog.")
    parser.add_argument("-v", "--verbose", default=0, action="count", help="Verbosity level.  Use multiple times to increase verboseness.")
    parser.add_argument("-d", "--daemon", action="store_true", help="Whether to detach like a proper daemon.")
    parser.add_argument("-u", "--user", default=None, help="The user to use when dropping privs.")
    parser.add_argument("-g", "--group", default=None, help="The group to use when dropping privs.")
    parser.add_argument("-c", "--config-file", help="A python file to load specifying config data.")
    config = parser.parse_args(args)
    # Calculate verbosity level specified
    config.verbose = calculateLogLevel(config.verbose)
    # Include the file config, if it was specified
    if config.config_file:
        fileconfig = imp.load_source(__name__+".config", config.config_file)
        config.__dict__.update(fileconfig.__dict__)
    # worker_dir is required, but can come from either the config, or the CLI
    if config.worker_dir == None:
        parser.print_usage()
        print("\nerror: worker directory must be specified", file=sys.stderr)
        exit(2)
    return config

def loadWorkers(workerDir):
    """Load workers from the given path, returning a dictionary of
        { gearman_job_name => module }
    .  Expects workers to be in files named for the gearman job it handles, and
    for each file to provide a doTask(worker, job, logger) function which
    actually performs the task."""
    workers = {}
    if not os.path.isdir(workerDir):
        raise IOError(workerDir + " is not a directory or does not exist")
    else:
        sys.modules[__name__+".worker"] = imp.new_module(__name__+".worker")
        for path in glob(workerDir + "/*.py"):
            (module, _) = os.path.splitext(os.path.basename(path))
            workers[module] = imp.load_source(__name__+".worker."+module, path)
    return workers

class JobLogAdapter(logging.LoggerAdapter):
    """Includes the job unique id in what gets logged via job loggers, so you
    can keep track of what job logged what data."""
    def process(self, msg, kwargs):
        return '[%s] %s' % (self.extra['unique'], msg), kwargs

def getJobLogger(job):
    log = logging.getLogger('gearman-manager.worker.' + job.task)
    adapter = JobLogAdapter(log, {'unique': job.unique})
    return adapter

def calculateLogLevel(verbose):
    return max(50-10*verbose, 0)

def setupLogging(config):
    """Sets up Python's root logger based on the configured log destination and
    verbosity."""
    format = os.path.basename(sys.argv[0]) + ': %(levelname)s %(name)s %(message)s'
    if 'syslog' == config.log_file:
        from logging.handlers import SysLogHandler
        syslog = SysLogHandler(address='/dev/log', facility=SysLogHandler.LOG_DAEMON)
        syslog.setFormatter(logging.Formatter(format))
        logging.getLogger().addHandler(syslog)
    elif 'stderr' == config.log_file:
        logging.basicConfig(stream=sys.stderr, format=format)
    else:
        logging.basicConfig(filename=config.log_file, format=format)
    logging.getLogger().setLevel(config.verbose)

def wrapDoTask(jobName, doTask):
    """Places a thin wrapper around a job module's doTask method to log that the
    task is about to be run, and provide a logger for doTask to use."""
    def inner(worker, job):
        log = logging.getLogger('gearman-manager.worker')
        log.info("Running task "+job.task+" ("+job.unique+")")
        joblog = getJobLogger(job)
        return doTask(worker, job, joblog)
    return inner

def buildTasks(workers):
    """Given a set of workers as returned by loadWorkers, builds an array of
    Tasks to feed to GearmanTaskServer."""
    return [Task(jobName, wrapDoTask(jobName, workers[jobName].doTask), True) for jobName in workers]

def runServer(config):
    """Runs the server using the given config."""
    # Import all of the jobs we handle
    tasks = buildTasks(loadWorkers(os.path.realpath(config.worker_dir)))
    # Initialize the server
    server = GearmanTaskServer(
        host_list      = config.host,
        tasks          = tasks,
        max_workers    = config.max_workers,
        worker_class   = GearmanWorker,
        use_sighandler = True,
        verbose        = True,
    )

    def terminateChildren(sig, frame):
        """daemon fails to terminate child processes.  This fixes that."""
        [child.terminate() for child in active_children()]
        context.terminate(sig, frame)

    context = daemon.DaemonContext(
        pidfile=PidFile(config.pid_file),
        umask=0o022,
        stderr=sys.stderr if 'stderr' == config.log_file else None,
        detach_process=config.daemon,
        uid=pwd.getpwnam(config.user).pw_uid if config.user else None,
        gid=grp.getgrnam(config.group).gr_gid if config.group else None,
        signal_map={
            signal.SIGTERM: terminateChildren,
        }
    )

    with context:
        server.serve_forever()

# We're being run as a program, not as a library, so set up logging and run the
# server.
if __name__ == '__main__':
    config = parseArgs()
    setupLogging(config)
    runServer(config)
