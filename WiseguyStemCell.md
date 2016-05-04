This is the launch procedure when running under stemcell. It is more complex, but affords much better restart characteristics.

  * script start
  * open logging
  * preload modules
  * bind mgmt port (tcp http)
  * bind main port (80/4000/unix socket, fcgi or http)
    * drop privileges
  * bind fd\_server
  * bind µmgmt server (derived from the fd\_server address)
  * superfork and daemonize
    * close stdin/stdout/stderr
  * start mgmt thread
  * start fd\_server thread
  * start µmgmt server thread
  * connect to previous µmgmt server
  * spawn some workers
    * send prune\_worker to µmgmt server
    * fork worker
    * run child init functions
      * open request log
  * send graceful\_shutdown to µmgmt server
    * queue a SIGKILL to children after 30 seconds
    * attempt to gracefully prune children with SIGTERM