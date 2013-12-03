#include <sys/types.h>
#include <sys/socket.h>
#include <sys/uio.h>
#include <sys/un.h>

#include <errno.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static char global_error_string[256];
static char global_data_buffer[] = {'\0'};

#define UNIX_SOCKET_PATH "/tmp/pyzy.sock"

static int remote_pid = 0;

int seterr(const char *fmt, ...)
{
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(global_error_string, sizeof(global_error_string), fmt, ap);
  va_end(ap);
  return -1;
}

int open_unix_socket(const char *path)
{
  int fd = -1;
  struct sockaddr_un addr;
  socklen_t addrlen = sizeof(struct sockaddr_un);
  size_t pathlen = strlen(path);
  size_t max_pathlen = sizeof(addr.sun_path) - 1;

  memset(&addr, 0, addrlen);
  addr.sun_family = AF_UNIX;

  if (path == NULL)
    return seterr("path cannot be NULL");
  if (pathlen > max_pathlen)
    return seterr("path cannot be longer than %u characters", max_pathlen);
  strncpy(addr.sun_path, path, pathlen);

  if ((fd = socket(PF_UNIX, SOCK_STREAM, 0)) < 0)
    return seterr("socket() failed: %s", strerror(errno));
  if (connect(fd, (struct sockaddr *)&addr, addrlen) < 0)
    return seterr("connect() failed: %s", strerror(errno));
  return fd;
}

int send_fd(int unix_fd, int fd)
{
  int n;
  struct msghdr msg;
  struct iovec iov;
  struct cmsghdr *cmsg;
  int myfds[1];
  
  char buf[CMSG_SPACE(sizeof(myfds))];
  int *fdptr;

  myfds[0] = fd;
  memset(&msg, 0, sizeof(struct msghdr));
  memset(&iov, 0, sizeof(struct iovec));
  iov.iov_base = global_data_buffer;
  iov.iov_len = 1;

  msg.msg_iov = &iov;
  msg.msg_iovlen = 1;
  msg.msg_control = buf;
  msg.msg_controllen = sizeof(buf);

  cmsg = CMSG_FIRSTHDR(&msg);
  cmsg->cmsg_level = SOL_SOCKET;
  cmsg->cmsg_type = SCM_RIGHTS;
  cmsg->cmsg_len = CMSG_LEN(sizeof(myfds));
  fdptr = (int *)CMSG_DATA(cmsg);
  memcpy(fdptr, myfds, sizeof(myfds));
  msg.msg_controllen = cmsg->cmsg_len;

  n = sendmsg(unix_fd, &msg, 0);
  if (n < 0)
    return seterr("sendmsg() failed: %s", strerror(errno));

  return 0;
}

int send_int(int unix_fd, unsigned int _int)
{
  unsigned int nbo_int = htonl(_int);
  ssize_t send_len = sizeof(unsigned int);
  ssize_t sent_bytes = send(unix_fd, &nbo_int, send_len, 0);
  if (sent_bytes != send_len) {
    return -1;
  }
  return 0;
}

int send_string(int unix_fd, char* _string)
{
  unsigned int len = strlen(_string);
  int rc = send_int(unix_fd, len);
  if (rc) {
    return rc;
  }
  ssize_t sent_bytes = send(unix_fd, _string, len, 0);
  if (sent_bytes != len) {
    return -1;
  }
  return 0;
}

int send_launch_ctl(int unix_fd, int argc, char** argv)
{
  int rc;
  
  char env[16*1024];
  char* environment_var_list[] = {
    "PYTHONPATH",
    "PWD",
    NULL,
  };
  
  env[0] = '\0';
  char* env_var_name = NULL;
  char* env_val = NULL;
  int i = 0;
  strcat(env, "PYZY_ENV=1\n");
  while (1) {
    env_var_name = environment_var_list[i++];
    if (!env_var_name) {
      break;
    }
    env_val = getenv(env_var_name);
    if (env_val != NULL) {
      strcat(env, env_var_name);
      strcat(env, "=");
      strcat(env, env_val);
      strcat(env, "\n");
    }
  }

  // printf("env: %s\n", env);
  if (rc = send_string(unix_fd, env)) {
    return rc;
  }
  if (rc = send_int(unix_fd, argc)) {
    return rc;
  }
  for (i = 0; i < argc; i++) {
    // printf("arg %d %s\n", i, argv[i]);
    if (rc = send_string(unix_fd, argv[i])) {
      return rc;
    }
  }
    
  if (rc = send_fd(unix_fd, STDIN_FILENO)) {
    return rc;
  }
  if (rc = send_fd(unix_fd, STDOUT_FILENO)) {
    return rc;
  }
  if (rc = send_fd(unix_fd, STDERR_FILENO)) {
    return rc;
  }
  return 0;
}

int recv_int(int unix_fd, int* rint)
{
  ssize_t bytes_read = recv(unix_fd, rint, sizeof(int), 0);
  if (bytes_read != sizeof(int)) {
    return -1;
  }
  *rint = ntohl(*rint);
  return 0;
}


int recv_return_code(int unix_fd)
{
  int return_codes[2];
  
  ssize_t bytes_read = recv(unix_fd, return_codes, sizeof(return_codes), 0);

  printf("return code %d, pid %d\n", ntohl(return_codes[0]),
         ntohl(return_codes[1]));

  return return_codes[0];
}

// FIXME: Catch a few more signals? TERM, HUP?
int signal_handler(int signal_num)
{
  printf("signal_handler: %d, send\n", signal_num);
  kill(remote_pid, signal_num);
  exit(1);
}

int main(int argc, char **argv)
{
  int unix_fd;

  if ((unix_fd = open_unix_socket(UNIX_SOCKET_PATH)) < 0)
  {
    fprintf(stderr, "open_unix_socket() failed (%s)\n", global_error_string);
    return 1;
  }

  if (send_launch_ctl(unix_fd, argc, argv) < 0)
  {
    fprintf(stderr, "send_launch_ctl() failed (%s)\n", global_error_string);
    return 1;
  }
  int rc;
  if (rc = recv_int(unix_fd, &remote_pid)) {
    return 1;
  }
  signal(SIGINT, (void*)signal_handler);
  
  fprintf(stderr, "remote pid: %d\n", remote_pid);

  fprintf(stderr, "recv_return_code\n");
  return recv_return_code(unix_fd);
}
