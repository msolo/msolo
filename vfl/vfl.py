
# want a versioned file layout that exposes multiple versions of files with the
# same logical filename in the code. each url then has 'infinite' expiration.
#
# so this url referenced in code:
#   /css/base.css
# resolves to this file:
#   /htdocs/css/base-vfl2048.css
# mapped to this url:
#   http://www.blah.com/css/base-vfl2048.css
#
# you can then prune based on the number of revisions you want to keep

# release process:
#  * checkout release version
#  * create versioned file tree
#  * create versioned index (python pickle? cdb?)
#  * prune versions to max revisions
#  * push versioned file tree (rsync w/ --delete)
#  * move versioned index to web code
#  * restart web processes to pick up new resource version index

# this was working all fine until i realized that things like css and
# javascript - classically static things - can themselves include resources
# that i want to version.
#
# i have a 2 problems. i want this to be simple for designers to use
# in the average case. i also want to have close to 100% coverage. this means
# that i need to generate a dependency tree from web resources and then dump
# out a copy with the correct versions substituted. this also means i don't
# get a fancy syntax (since i want backward compatibility) - so i need to rely
# on the kindness of strangers and their ability to follow simple conventions.
#
# the convention is that site-relative urls in css and javascript will be
# automatically versioned - so things starting with a / and ending with what
# looks like a file extension - we'll see how it goes.
#
# this results in a 2-stage 'compile' process.
#  * generate version index (see above)
#  * for each css and javascript file, parse it and look for subresources
#    * if it has subresources
#      * substitute all urls with versioned urls
#      * re-version the parent to the max revision of any resource/subresource

__author__ = 'Mike Solomon'
__author_email__ = '<mas63 @t cornell d0t edu>'
__version__ = '0.7.14'
__license__ = 'BSD License'

import errno
import logging
import os
import os.path
import pprint
import re
import stat
import subprocess
import shutil
import urlparse
import md5
import base64

import cPickle as pickle


log = logging.getLogger('vfl')

class VFLKeyError(KeyError):
    """Exception raised when there is no vfl url for the specific url
    """

class VersionedFileLayoutException(Exception):
    pass

# maps url -> (versioned_url, version)
class VersionUrlMap(dict):
    def __setitem__(self, key, value):
        # the prefix (/css/filename) of the key name (/css/filename.css)
        # *should* be in the versioned url (/css/filename-vfl1234.css)
        # if it isn't, there is some sort of corruption, so blow an exception
        # and don't corrupt the index
        if key.split('.')[0] not in value[0]:
            raise VersionedFileLayoutException(
                'bad versioned_url, %r -> %r' % (key, value))
        super(VersionUrlMap, self).__setitem__(key, value)

HASH_LENGTH = 6
default_filename_format = '%(name)s-vfl%(rev)s%(ext)s'
# this pattern now correctly matches mtime names as well as hash-appended names
# static_ad_728_90_g-vfl1283193554.html
# static_ad_728_90_g-vfl81cf06.html

default_filename_pattern = '(?P<name>.+)-vfl(?P<rev>\d{7,15}|\S{%d})(?P<ext>\..+)?' % HASH_LENGTH

class VersionedFileLayout(object):
    def __init__(self, versioned_filename_format=default_filename_format,
                 versioned_filename_pattern=default_filename_pattern,
                 http_root=None, new_index_format=True):
        self.versioned_filename_format = versioned_filename_format
        self.versioned_filename_pattern = versioned_filename_pattern
        self.http_root = http_root
        if self.http_root and self.http_root.endswith('/'):
            self.http_root = self.http_root[:-1]
        self.new_index_format = new_index_format
        self.index_loaded = False
        self.version_url_map = VersionUrlMap()
        self.last_mtime_indexed = None

    def load_index(self, index_path):
        self.index_path = index_path
        f = open(index_path, 'r')
        index = pickle.load(f)
        if 'vfl_map' in index:
            self.version_url_map = index['vfl_map']
            self.last_mtime_indexed = index['last_mtime_indexed']
        else:
            self.version_url_map = index
            self.last_mtime_indexed = index.get('last_mtime_indexed')
        f.close()
        self.index_loaded = True

    # try to return an absolute path to the versioned resource
    # if the lookup fails, fall through to the local resource so any cache
    # pulling through doesn't get confused
    def get_url(self, site_relative_path):
        try:
            url_path = self.version_url_map[site_relative_path]
            return '%s%s' % (self.http_root, url_path)
        except KeyError, e:
            raise VFLKeyError(site_relative_path + " is missing from " + 
                              self.index_path)

    def get_bundle_url(self, site_relative_bundle_path, bundle_file):
        return (self.get_url(site_relative_bundle_path) + '/' +
                bundle_file.lstrip('/'))
        
    
    def build_versioned_tree(self, release_base_path, versioned_base_path,
                             index_path, max_revisions, exclude_list=None,
                             exclude_suffixes=None, url_prefix=''):
        version_url_map, max_mtime, codependents = copy_versioned_tree(
            release_base_path, versioned_base_path,
            self.versioned_filename_format, exclude_list, exclude_suffixes,
            self.last_mtime_indexed,
            extract_revision_map(self.version_url_map,
                                 self.versioned_filename_pattern))

        # log.debug('codependents: %s', codependents)
        version_url_map = self.compile_versioned_resources(
            release_base_path, versioned_base_path,
            codependents, version_url_map, url_prefix)

        if index_path:
            self.write_vfl_map(version_url_map, max_mtime, index_path)

        if max_revisions:
            prune_versioned_tree(versioned_base_path, max_revisions,
                                 self.versioned_filename_pattern)


    def compile_versioned_resources(self, release_base_path,
                                    versioned_base_path, codependents,
                                    version_url_map, url_prefix):
        # release_base_path: ~/vfl-src
        # relative_path: /js/file.js
        # versioned_base_path: ~/vfl-dst
        version_url_map = version_url_map.copy()
        for relative_path, revision, ext in codependents:
            if ext in bundle_extension_map:
                bundle_processor_class = bundle_extension_map[ext]
                bundle_src = get_absolute_path(release_base_path,
                                               relative_path)
                relative_versioned_path = os.path.splitext(
                    get_relative_versioned_path(
                    relative_path, revision,
                    self.versioned_filename_format))[0]
                bundle_dst = get_absolute_path(versioned_base_path,
                                               relative_versioned_path)
                processor = bundle_processor_class(bundle_src, bundle_dst)
                processor.run()
                # we want to reference a bundle without its extension, so
                # alias the versioned directory name as well
                # we need the actual bundle path to handle versioning during
                # a vfl rebuild
                relative_path_alias = os.path.splitext(relative_path)[0]
                version_url_map[relative_path_alias] = (relative_versioned_path,
                                                  revision)
            else:
                preprocessor_class = codependent_extension_map.get(
                    ext, NullPreprocessor)
                preprocessor = preprocessor_class(
                    relative_path,
                    release_base_path,
                    version_url_map,
                    url_prefix)

                (data, new_revision) = preprocessor.run()
                if not data:
                    continue

                relative_versioned_path = get_relative_versioned_path(
                    relative_path, new_revision,
                    self.versioned_filename_format)
                version_url_map[relative_path] = (relative_versioned_path,
                                                  new_revision)
                versioned_path = get_absolute_path(versioned_base_path,
                                                   relative_versioned_path)
                f = open(versioned_path, 'w')
                f.write(data)
                f.close()

        return version_url_map


    def write_vfl_map(self, version_url_map, max_mtime, map_path):
        vfl_map = {}
        for key, value in version_url_map.iteritems():
            try:
                (path, revision) = value
            except TypeError:
                continue
            vfl_map[key] = path
        f = open(map_path, 'w')
        if self.new_index_format:
            index = {
                'vfl_map': vfl_map,
                'last_mtime_indexed': max_mtime,
                }
        else:
            index = vfl_map
            index['last_mtime_indexed'] = max_mtime
        pickle.dump(index, f, pickle.HIGHEST_PROTOCOL)
        f.close()


class Preprocessor(object):
    explicit_dependency_pattern = re.compile('/\*\s*#include\s+(\S+)\s*\*/')

    def __init__(self, relative_path, release_base_path, version_url_map,
                 url_prefix='',):
        self.relative_path = relative_path
        if url_prefix and url_prefix.endswith('/'):
            url_prefix = url_prefix[:-1]

        self.url_prefix = url_prefix
        self.release_path = get_absolute_path(release_base_path, relative_path)
        f = open(self.release_path)
        self.file_contents = f.read()
        f.close()
        self.version_url_map = version_url_map

    def replace_urls(self):
        return self.dependency_pattern.sub(self.url_match_replacement,
                                           self.file_contents)

    def run(self):
        dependencies = self.get_dependencies()
        dependencies.extend(self.get_explicit_dependencies())
        # prune out duplicate dependencies
        dependencies = list(set(dependencies))
        log.debug('dependencies: %s %s', self.relative_path, dependencies)
        if dependencies:
            preprocessed_content = self.replace_urls()
            dependent_revision = get_md5_hash(preprocessed_content)
            log.debug('dependent_revision: %s %s',
                      self.release_path, dependent_revision)
            return preprocessed_content, dependent_revision
        return (None, None)

    def get_explicit_dependencies(self):
        deps_path = get_dependency_path(self.release_path)
        try:
            f = open(deps_path)
        except IOError, e:
            if e[0] == errno.ENOENT:
                return []
            else:
                raise

        data = f.read()
        f.close()
        # i used to limit the dependencies to things that we already
        # seen by VFL - however, there are new files that have dependecies
        # outside of the vfl root.  for now, return those and if they aren't
        # in the tree, re-resolved via svn
        return [path
                for path in
                self.explicit_dependency_pattern.findall(data)]
                #if path in self.version_url_map]


class CSSPreprocessor(Preprocessor):
    dependency_pattern = re.compile('url\(([^\)]+)\)')

    # compute a dependency 'tree' for a css file
    def get_dependencies(self):
        # TODO: handle css import statement
        return [path
                for path in
                self.dependency_pattern.findall(self.file_contents)
                if path in self.version_url_map]

    def url_match_replacement(self, match_obj):
        url = match_obj.group(1)
        try:
            versioned_url = 'url(%s%s)' % (self.url_prefix,
                                           self.version_url_map[url][0])
        except KeyError:
            versioned_url = match_obj.group(0)
        return versioned_url


class JSPreprocessor(Preprocessor):
    # a little more ambiguous than the css version as the syntax isn't
    # as well specified
    dependency_pattern = re.compile("([\'\"])(/\S+?\.\w{2,4})([\'\"])")

    # compute a dependency 'tree' for a css file
    def get_dependencies(self):
        return [path
                for start, path, end in
                self.dependency_pattern.findall(self.file_contents)
                if start == end and path in self.version_url_map]

    def url_match_replacement(self, match_obj):
        start_token, url, end_token = match_obj.groups()
        if start_token != end_token:
            return match_obj.group(0)
        try:
            versioned_url = '%s%s%s%s' % (start_token,
                                          self.url_prefix,
                                          self.version_url_map[url][0],
                                          end_token)
        except KeyError:
            versioned_url = match_obj.group(0)
        return versioned_url


class NullPreprocessor(Preprocessor):
    def get_dependencies(self):
        return []

    def replace_urls(self):
        return self.file_contents


class BundleProcessor(object):
    # expand out a bundle into the correct versioned directory name
    # src_path: a path to a bundle file, /js/rsrc.tgz
    # dst_path: a path to a versioned directory name /js/rsrc-vfl1
    def __init__(self, src_path, dst_path):
        self.src_path = src_path
        self.dst_path = dst_path

    def run(self):
        if not os.path.exists(self.dst_path):
            try:
                os.mkdir(self.dst_path)
            except OSError, e:
                raise VersionedFileLayoutException(
                    'unabled to create director %s' % self.dst_path)
        exit_code = subprocess.call(self.cmd)
        if exit_code:
            raise VersionedFileLayoutException(
                'exitted with %d during %s' % (exit_code, ' '.join(self.cmd)))


class TgzBundleProcessor(BundleProcessor):
    @property
    def cmd(self):
       return ('tar', '-xzf', self.src_path, '-C', self.dst_path)


class TbzBundleProcessor(BundleProcessor):
    @property
    def cmd(self):
       return ('tar', '-xjf', self.src_path, '-C', self.dst_path)


bundle_extension_map = {
    '.tgz': TgzBundleProcessor,
    '.tbz': TgzBundleProcessor,
    }

# this maps codependent extensions to a possible preprocessor
# all bundles must be listed here, since this determines that a file needs
# additional processing
codependent_extension_map = {
    '.css': CSSPreprocessor,
    '.js': JSPreprocessor,
    }
codependent_extension_map.update(dict.fromkeys(bundle_extension_map))

def get_absolute_path(base_path, site_relative_path):
    # strip off the leading /
    # FIXME: not portable
    if site_relative_path.startswith('/'):
        site_relative_path = site_relative_path[1:]
    return os.path.join(base_path, site_relative_path)

def get_dependency_path(path):
    directory, filename = os.path.split(path)
    deps_file = '.%s.vfl' % filename
    return os.path.join(directory, deps_file)

def get_site_relative_path(site_root, path):
    return path.replace(os.path.abspath(site_root), '')

def format_dependency_comment(path):
    return '/* #include %s */' % path

def get_relative_versioned_path(relative_path, revision,
                            versioned_filename_format):
    dirname, filename = os.path.split(relative_path)
    name, ext = os.path.splitext(filename)
    sub_vars = {
        'name': name,
        'rev': revision,
        'ext': ext,
        }
    return os.path.join(dirname, versioned_filename_format % sub_vars)

def extract_revision_map(version_url_map, versioned_filename_pattern):
    version_url_map = version_url_map.copy()
    version_pattern = re.compile(versioned_filename_pattern)
    for path, versioned_path in version_url_map.items():
        try:
            versioned_filename = os.path.basename(versioned_path)
        except AttributeError, e:
            continue

        match = version_pattern.match(versioned_filename)
        if not match:
            continue
        version_url_map[path] = (versioned_path,
                                 match.group('rev'))

    return version_url_map

def _remove_file_callback(function, path, exc_info):
    log.error('error during remove: %s', exc_info[1])

def prune_versioned_tree(versioned_base_path, max_revisions,
                         versioned_filename_pattern):
    log.debug('prune_versioned_tree')
    if max_revisions < 1:
        raise VersionedFileLayoutException('max_revisions < 1')

    version_pattern = re.compile(versioned_filename_pattern)
    for (path, dir_list, file_list) in os.walk(versioned_base_path):
        versioned_file_map = {}
        for filename in file_list + dir_list:
            match = version_pattern.match(filename)
            if not match:
                continue
            name = match.group('name')
            rev = match.group('rev')
            ext = match.group('ext')

            # since rev is now an md5 hash, we can not use it for pruning
            # we instead set rev to mtime and use mtime for pruning
            rev = int(os.path.getmtime(os.path.join(path, filename)))

            normal_filename = '%s%s' % (name, ext)
            try:
                versioned_file_map[normal_filename].append((rev, filename))
            except KeyError:
                versioned_file_map[normal_filename] = [(rev, filename),]

        for filename, version_list in versioned_file_map.iteritems():
            version_list.sort(reverse=True)
            for version, version_file in version_list[max_revisions:]:
                remove_path = os.path.join(path, version_file)
                log.debug('rm %s %s', remove_path, version_list)
                if os.path.isdir(remove_path):
                    shutil.rmtree(remove_path, onerror=_remove_file_callback)
                else:
                    try:
                        os.unlink(remove_path)
                    except OSError, e:
                        log.error('unable to unlink %s %s', remove_path, e)

def get_md5_hash_path(path):
  f = open(path, 'r')
  mh = get_md5_hash(f.read())
  f.close()
  return mh

def get_md5_hash(input):
 h = md5.new(input).digest()
 b = base64.urlsafe_b64encode(h)
 return b[0:HASH_LENGTH]

def get_computed_revision(path):
  return get_md5_hash_path(path)

# create versioned mirror of release_base_path in versioned_base_path
# return dict mapping of path -> versions
def copy_versioned_tree(release_base_path, versioned_base_path,
                        versioned_filename_format, exclude_list=None, exclude_suffixes=None,
                        last_mtime_indexed=None, last_vfl_map=None):
    # note: i rationalize putting this here because this is a 'compile-time'
    # operation - the rest of the site should not need this package just to
    # read a url out of a dictionary
    if exclude_list is None:
        exclude_list = []
    exclude_list = tuple(exclude_list + ['.svn']) # skip subversion directories
    if exclude_suffixes is None:
        exclude_suffixes = []
    exclude_suffixes = tuple(exclude_suffixes + ['.vfl']) # skip dependency files

    # a list of (relative_path, version) tuples for files that might depend
    # on other versioned resources - this is just determined by file extension
    # right now. slightly ghetto.
    codependents = []
    version_url_map = VersionUrlMap()
    release_base_path = os.path.abspath(release_base_path)
    versioned_base_path = os.path.abspath(versioned_base_path)
    max_mtime = 0
    for (path, dir_list, file_list) in os.walk(release_base_path, followlinks=True):
        for dirname in exclude_list:
            if dirname in dir_list:
                dir_list.remove(dirname)
        relative_dir = path[len(release_base_path):]
        if not relative_dir:
            relative_dir = '/'
        versioned_dir = os.path.join(versioned_base_path, relative_dir[1:])
        if not os.path.isdir(versioned_dir):
            os.makedirs(versioned_dir)

        for filename in file_list:
            if filename.endswith(exclude_suffixes):
                continue
            release_path = os.path.join(path, filename)
            relative_path = os.path.join(relative_dir, filename)
            name, ext = os.path.splitext(filename)
            dependency_path = get_dependency_path(release_path)
            has_dependencies = os.path.exists(dependency_path)

            mtime = os.path.getmtime(release_path)
            max_mtime = max(max_mtime, mtime)
            if mtime <= last_mtime_indexed:
                needs_copying = False
                try:
                    if not isinstance(last_vfl_map[relative_path], tuple):
                        msg = "can't check %s: wrong entry type in last_vfl_map, not tuple" % relative_path
                        log.error(msg)
                        log.debug("vfl revision map: %s",
                                  pprint.pformat(last_vfl_map))
                        raise VersionedFileLayoutException(msg)
                    
                    revision = last_vfl_map[relative_path][-1]
                    try:
                        if revision is not None:
                            revision = revision
                    except ValueError:
                        msg = ("can't get last vfl revision: %r" %
                               last_vfl_map[relative_path])
                        log.error(msg)
                        raise VersionedFileLayoutException(msg)
                except (KeyError, IndexError), e:
                    log.warning("skipping %s: no cached entry", relative_path)
                    continue
            else:
                needs_copying = True
                revision = get_computed_revision(release_path)
            if revision is None:
                if not has_dependencies and ext not in codependent_extension_map:
                  log.warning("skipping %s: no svn entry", release_path)
                  continue

                # if the file is dependent on something else, maybe we can
                # create an implied version number
                if not has_dependencies:
                  log.warning("skipping %s: no dependency file %s",
                              release_path, dependency_path)
                  continue

            sub_vars = {
                'name': name,
                'rev': revision,
                'ext': ext,
                }
            try:
                versioned_name = versioned_filename_format % sub_vars
            except TypeError, e:
                if revision is None:
                    # make this a nonsense int we can look for on output if we
                    # are trying to track down a problem
                    sub_vars['rev'] = 0
                    versioned_name = versioned_filename_format % sub_vars
                else:
                    msg = "can't format %r %r" % (versioned_filename_format,
                                                  sub_vars)
                    log.error(msg)
                    raise VersionedFileLayoutException(msg)

            # copy through the unversioned resource in case something doesn't
            # use the VFL naming scheme
            unversioned_path = os.path.join(versioned_dir, filename)
            versioned_path = os.path.join(versioned_dir, versioned_name)

            if needs_copying or not os.path.isfile(unversioned_path):
                log.debug('unversioned: cp %s -> %s', release_path, unversioned_path)
                shutil.copy2(release_path, unversioned_path)
                # ensure the copy is writable to allow updating
                mode = os.stat(unversioned_path).st_mode | stat.S_IWUSR
                os.chmod(unversioned_path, mode)
            # if we have explicit dependencies, we have to copy this on
            # the second pass - most of the other data that's incorrect
            # will be overwritten later
            if (revision and
                (needs_copying or not os.path.isfile(versioned_path))):
                log.debug('versioned: cp %s -> %s', release_path, versioned_path)
                shutil.copy2(release_path, versioned_path)
                # ensure the copy is writable to allow updating
                mode = os.stat(versioned_path).st_mode | stat.S_IWUSR
                os.chmod(versioned_path, mode)

            relative_versioned_path = os.path.join(relative_dir,
                                                   versioned_name)
            version_url_map[relative_path] = (relative_versioned_path,
                                              revision)
            
            if has_dependencies or ext in codependent_extension_map:
                codependents.append((relative_path, revision, ext))
    return version_url_map, max_mtime, codependents
