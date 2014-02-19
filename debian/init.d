#!/bin/sh

### BEGIN INIT INFO
# Provides:          python-gearman-manager
# Required-Start:    $network $remote_fs $syslog
# Required-Stop:     $network $remote_fs $syslog
# Should-Start:      gearman-job-server
# Should-Stop:       gearman-job-server
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: Start daemon at boot time
# Description:       Enable gearman manager daemon
### END INIT INFO

PATH=/sbin:/usr/sbin:/bin:/usr/bin
DESC="Gearman Manager (Python)"
NAME=python-gearman-manager
DAEMON=/usr/bin/python-gearman-manager
PIDDIR=/run/gearman
PIDFILE=${PIDDIR}/python-manager.pid
LOGFILE=syslog
CONFIGDIR=/etc/python-gearman-manager
RUNAS_USER="gearman"
RUNAS_GROUP="gearman"
DAEMON_ARGS=""

test -x ${DAEMON} || exit 0

# Read configuration variable file if it is present
[ -r /etc/default/$NAME ] && . /etc/default/$NAME

if [ "$START" != "yes" ]; then
  echo "To enable $DESC, edit /etc/default/$NAME and set START=yes"
  exit 0
fi

if test -e "${CONFIGDIR}/config.py"; then 
  DAEMON_ARGS="$DAEMON_ARGS --config ${CONFIGDIR}/config.py"
fi

. /lib/lsb/init-functions

ensure_logfile() {
  case "${LOGFILE}" in
    stderr|syslog) ;;
    *)
      if ! test -f ${LOGFILE}
      then
        touch ${LOGFILE}
        chown "${RUNAS_USER}:${RUNAS_GROUP}" ${LOGFILE}
      fi
      ;;
  esac
}

ensure_piddir() {
  if ! test -d ${PIDDIR}
  then
    mkdir ${PIDDIR}
    chown ${RUNAS_USER} ${PIDDIR}
  fi
}

start()
{
  log_daemon_msg "Starting $DESC"
  ensure_piddir
  ensure_logfile
  if start-stop-daemon \
    --start \
    --startas $DAEMON \
    --pidfile $PIDFILE \
    --chuid $RUNAS_USER:$RUNAS_GROUP \
    -- -P $PIDFILE \
       -l $LOGFILE \
       -u $RUNAS_USER \
       -g $RUNAS_GROUP \
       -d \
       $DAEMON_ARGS
  then
    log_end_msg 0
  else
    log_end_msg 1
    log_warning_msg "Please take a look at the syslog"
    exit 1
  fi
}

stop()
{
  log_daemon_msg "Stopping $DESC"
  if start-stop-daemon \
    --stop \
    --oknodo \
    --retry 20 \
    --pidfile $PIDFILE
  then
    log_end_msg 0
  else
    log_end_msg 1
    exit 1
  fi
}

case "$1" in

  start)
    start
  ;;

  stop)
    stop
  ;;

  restart|force-reload)
    stop
    start
  ;;

  status)
    status_of_proc -p $PIDFILE $DAEMON "$DESC"
  ;;

  *)
    echo "Usage: $0 {start|stop|restart|force-reload|status|help}"
  ;;

esac
