import itertools
import operator

from socket import inet_aton, inet_ntoa, htonl
from struct import pack, unpack


def make_cidr_prefix(ip, mask):
  x = unpack('l', inet_aton(ip))[0] & ~htonl((1 << (32 - mask)) - 1)
  return pack('l', x)


class CIDR(object):
  def __init__(self, cidr_string):
    try:
      self.ip, self.mask = cidr_string.split('/')
      self.mask = int(self.mask)
    except ValueError:
      self.ip, self.mask = cidr_string, 32
    
    self.cidr_prefix = make_cidr_prefix(self.ip, self.mask)
    # normalize the CIDR IP address
    self.ip = inet_ntoa(self.cidr_prefix)
    
  def __contains__(self, ip):
    return make_cidr_prefix(ip, self.mask) == self.cidr_prefix

  def __str__(self):
    return "%s/%s" % (self.ip, self.mask)

  __repr__ = __str__


class CIDRList(object):
  def __init__(self, cidr_list):
    self.cidr_list = [CIDR(cidr) for cidr in cidr_list]
  
  def __contains__(self, ip):
    for cidr in self.cidr_list:
      if ip in cidr:
        return True
    return False
