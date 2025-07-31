import argparse
import configparser
from datetime  import datetime
import grp, pwd # to read the users/group database on Unix
from fnmatch import fnmatch
import hashlib
from math import ceil
import os
import re
import sys
import zlib


#fisrt we need to set the format of CLI commands!

argparser = argparse.ArgumentParser(description="The stupidest content tracker")
argsubparsers = argparser.add_subparsers(title="Commands", dest="command")
argsubparsers.required = True


def main(argv=sys.argv[1:]):
    args = argparser.parse_args(argv)
    match args.command:

        case "add": cmd_add(args)
        case "cat-file": cmd_cat_file(args)
        case "check-ignore": cmd_check_ignore(args)
        case "checkout": cmd_checkout(args)
        case "commit": cmd_commit(args)
        case "hash-object": cmd_hash_object(args)
        case "init": cmd_init(args)
        case "log": cmd_log(args)
        case "ls-files": cmd_ls_files(args)
        case "ls-tree": cmd_ls_tree(args)
        case "rev-parse": cmd_rev_parse(args)
        case "rm": cmd_rm(args)
        case "show-ref": cmd_show_ref(args)
        case "status": cmd_status(args)
        case "tag": cmd_tag(args)
        case _ : print("Bad command.")


class GitRepo(object):
    worktree = None
    gitdir = None
    conf = None

    # initilizing the repo object : first we should check if there is any git repository in the given path!
    def __init__(self, path, force=False):
        self.worktree = path
        self.gitdir = os.path.join(path, ".git")
        if (not force) and (not os.path.isdir(self.gitdir)):
            raise Exception(f"Not a Git repository {path}")

        # if there is a repo, read the conf:
        self.conf = configparser.ConfigParser()
        cf = repo_path_safe(self, "config",is_file=True)
        if cf and os.path.exists(cf):
            self.conf.read([cf])
        elif not force:
            vers = int(self.conf.get("core", "repositoryformatversion"))
            if vers != 0:
                raise Exception(f"Unsupported repositoryformatversion: {vers}")
            

def repo_path(repo, *path):
    """Compute path under repo's gitdir."""
    return os.path.join(repo.gitdir, *path) 

def repo_file(repo, *path, mkdir=False):
    """Same as repo_path, but create dirname(*path) if absent.  For
example, repo_file(r, \"refs\", \"remotes\", \"origin\", \"HEAD\") will create
.git/refs/remotes/origin."""

    if repo_dir(repo, *path[:-1], mkdir=mkdir):
        return repo_path(repo, *path)
    
def repo_dir(repo, *path, mkdir=False):
    """Same as repo_path, but mkdir *path if absent if mkdir."""

    path = repo_path(repo, *path)

    if os.path.exists(path):
        if (os.path.isdir(path)):
            return path
        else:
            raise Exception(f"Not a directory {path}")

    if mkdir:
        os.makedirs(path)
        return path
    else:
        return None
    
def repo_path_safe(repo, *path, mkdir=False, is_file=False):
    """
    Return the full path under repo.gitdir.
    If mkdir=True:
        - If is_file=True: create only parent directories (like repo_file)
        - If is_file=False: create the entire directory (like repo_dir)
    """
    full_path = repo_path(repo, *path)

    # Decide what to create based on is_file
    target_dir = os.path.dirname(full_path) if is_file else full_path

    if os.path.exists(target_dir):
        if not os.path.isdir(target_dir):
            raise Exception(f"Not a directory: {target_dir}")
    elif mkdir:
        os.makedirs(target_dir)

    return full_path

def repo_default_config():
    pass
    ret = configparser.ConfigParser()
    ret.add_section("core")
    ret.set("core", "repositoryformatversion", "0")
    ret.set("core", "filemode", "false")
    ret.set("core", "bare", "false")
    return ret

def repo_create(path):
    repo = GitRepo(path, True)
    # First, we make sure the path either doesn't exist or is an
    # empty dir.
    if os.path.exists(repo.worktree):
        if not os.path.isdir(repo.worktree):
            raise Exception(f"{path} is not a directory!")
        if os.path.exists(repo.gitdir) and os.listdir(repo.gitdir):
            raise Exception (f"{path} is not empty!")
    else:
        os.makedirs(repo.worktree)

    
    assert repo_path_safe(repo, "branches", mkdir=True,is_file=False)
    assert repo_path_safe(repo, "objects", mkdir=True,is_file=False)
    assert repo_path_safe(repo, "refs", "tags", mkdir=True,is_file=False)
    assert repo_path_safe(repo, "refs", "heads", mkdir=True,is_file=False)

    # .git/description
    with open(repo_path_safe(repo, "description",is_file=True), "w") as f:
        f.write("Unnamed repository; edit this file 'description' to name the repository.\n")
    
    # .git/HEAD
    with open(repo_path_safe(repo, "HEAD", is_file=True), "w") as f:
        f.write("ref: refs/heads/master\n")
    
    with open(repo_path_safe(repo, "config", is_file=True), "w") as f:
        config = repo_default_config()
        config.write(f)

    return repo


argsp = argsubparsers.add_parser("init",help="Initialize a new, empty repository.")
argsp.add_argument("path", metavar="directory", nargs="?", default=".", help="Where to create the repository.")

def cmd_init(args):
    repo_create(args.path)

def repo_find(path='.', required=True):
    path = os.path.realpath(path)
    if os.path.isdir(os.path.join(path,".git")):
        return GitRepo(path)
    
    # If we haven't returned, recurse in parent
    parent = os.path.realpath(os.path.join(path, ".."))
    if parent == path:
        if required:
            raise Exception("No git directory.")
        else:
            return None
        
    return repo_find(parent, required)


# now we creat an object!

class GitObject(object):

    def __init__(self, data=None):
        if data != None:
            self.deserialize(data)

        else:
            pass

    def serialize(self, repo):
        """This function MUST be implemented by subclasses.

It must read the object's contents from self.data, a byte string, and
do whatever it takes to convert it into a meaningful representation.
What exactly that means depend on each subclass."""

        raise Exception("Unimplemented!")

    def deserialize(self, data):
        raise Exception("Unimplemented!")


def object_read(repo, sha):
    """Read object sha from Git repository repo.  Return a
    GitObject whose exact type depends on the object."""

    path = repo_file(repo,"objects",sha[0:2], sha[2:])
    if not os.path.isfile(path):
        return None
    
    with open (path, "rb") as f:
        raw = zlib.decompress(f.read())

        # Read object file:
        x = raw.find(b' ')
        fmt = raw[0:x]
        # Read and validate object size
        y = raw.find(b'\x00', x)
        size  = int(raw[x:y].decode("ascii"))
        if size != len(raw)-y-1:
            raise Exception(f"Malformed object {sha}: bad length")

        # pick the suitable constructor:
        match fmt:
            case b'commit' : c=GitCommit
            case b'tree'   : c=GitTree
            case b'tag'    : c=GitTag
            case b'blob'   : c=GitBlob
            case _:
                raise Exception(f"Unknown type {fmt.decode("ascii")} for object {sha}")

        # Call constructor and return object
        return c(raw[y+1:])
    
def object_write(obj: GitObject, repo=None):
    data = obj.serialize()
    result = obj.ftm + b' ' + str(len(data)).encode() + b'\x00' + data
    sha = hashlib.sha1(result).hexdigest()

    if repo:
        path=repo_file(repo,"objects", sha[0:2], sha[2:], mkdir=True)
        if not os.path.exists(path):
            with open(path,'wb') as f:
                #Compress it and Write:
                f.write(zlib.compress(result))
    
    return sha

class GitBlob(GitObject):
    ftm=b'blob'
    def serialize(self):
        return self.blobdata
    def deserialize(self, data):
        self.blobdata = data

argsp = argsubparsers.add_parser("cat-file",
                                 help="Provide content of repository objects")

argsp.add_argument("type",
                   metavar="type",
                   choices=["blob", "commit", "tag", "tree"],
                   help="Specify the type")

argsp.add_argument("object",
                   metavar="object",
                   help="The object to display")

def cmd_cat_file(args):
    repo = repo_find()
    cat_file(repo, args.object, fmt=args.type.encode())

def cat_file(repo, obj, fmt=None):
    obj = object_read(repo,object_find(repo,obj,fmt=fmt))

    sys.stdout.buffer.write(obj.serialize)



"""$ wyag checkout v3.11 # A tag
$ wyag checkout feature/explosions # A branch
$ wyag ls-tree -r HEAD # The active branch or commit.  There's also a
                       # follow here: HEAD is actually a commit.
$ wyag cat-file blob e0695f # A short hash
$ wyag cat-file tree master # A branch, as a tree (another "follow")

we can do all these!
"""
def object_find(repo, name, fmt=None, follow=True):
    sha = object_resolve(repo,name)
    if not sha:
        raise Exception(f"No such reference {name}.")
    if len(sha)>1:
        raise Exception("Ambiguous reference {name}: Candidates are:\n - {'\n - '.join(sha)}.")

    sha = sha[0]

    if not fmt:
        return sha
    
    while True:
        obj = object_read(repo=repo,sha=sha)

        if obj.fmt == fmt:
            return sha
        if not follow:
            return None
        
        if obj.fmt == b'tag':
            sha = obj.kvlm[b'object'].decode("ascii")
        elif obj.fmt == b'commit' and fmt == b'tree':
            sha = obj.kvlm[b'tree'].decode("ascii")
        else:
            return None

argsp = argsubparsers.add_parser(
    "hash-object",
    help="Compute object ID and optionally creates a blob from a file")

argsp.add_argument("-t",
                   metavar="type",
                   dest="type",
                   choices=["blob", "commit", "tag", "tree"],
                   default="blob",
                   help="Specify the type")

argsp.add_argument("-w",
                   dest="write",
                   action="store_true",
                   help="Actually write the object into the database")

argsp.add_argument("path",
                   help="Read object from <file>")

def cmd_hash_object(args):
    if args.write:
        repo = repo_find()
    else:
        repo = None

    with open(args.path, 'rb') as fd:
        sha = object_hash(fd, args.type.encode(), repo)
        print(sha)

def object_hash(fd, fmt, repo=None):
    """ Hash object, writing it to repo if provided."""
    data = fd.read()

    # choose constructor according to fmt argument
    match fmt:
        case b'commit' : obj=GitCommit(data)
        case b'tree'   : obj=GitTree(data)
        case b'tag'    : obj=GitTag(data)
        case b'blob'   : obj=GitBlob(data)
        case _: raise Exception(f"Unknown type {fmt}!")

    return object_write(obj, repo)

def kvlm_parse(raw, start=0, dct=None):
    if not dct:
        dct=dict()
    
    # we want to recursivly read a key/value pair and call it self back with new positions!
    # at first we need to know where we are, at a keyword? or at a messageQ?
    # the format I am using is RFC 2822 you can find it here: https://www.ietf.org/rfc/rfc2822.txt
    # lines of information for a given part are seperated with a space charachter!

    spc = raw.find(b' ', start)
    nl = raw.find(b'\n', start)

    # if there is a space before newline, we have a keyword. Otherwise it's the final message, which we just read to the end of the file
    
    # Base case
    # =========
    # If newline appears first (or there's no space at all, in which
    # case find returns -1), we assume a blank line.  A blank line
    # means the remainder of the data is the message.  We store it in
    # the dictionary, with None as the key, and return.
    
    
    if (spc<0) or (nl<spc):
        assert nl == start
        dct[None] = raw[start+1:]
        return dct
    
    # Recursive case
    # ==============
    # we read a key-value pair and recurse for the next.
    key = raw[start:spc]

    # Find the end of the value.  Continuation lines begin with a space, so we loop until we find a "\n" not followed by a space.
    end = start
    while True:
        end = raw.find(b'\n', end+1)
        if raw[end+1] != ord(' '): break

    # now we should grab the value and delete the spcae (in the start of the line) to have access to the full data
    value = raw[spc+1:end].replace(b'\n ', b'\n')
    if key in dct:
        if type(dct[key]) == list:
            dct[key].append(value)
        else:
            dct[key] = [ dct[key], value ]
    else:
        dct[key] = value

    return kvlm_parse(raw, start=end+1, dct=dct)

# Key-Value List with Message
def kvlm_serialize(kvlm):
    """write all fields first, then a newline, the message, and a final newline"""
    ret = b''

    for k in kvlm.keys():
        #skip the message
        if k == None: continue
        val = kvlm[k]
        # Normalize it to a list
        if type(val) != list:
            val = [ val ]

        for v in val:
            ret += k + b' ' + (v.replace(b'\n', b'\n ')) + b'\n'

        ret += b'\n' + kvlm[None]

    return ret


class GitCommit(GitObject):
    fmt=b'commit'

    def deserialize(self, data):
        self.kvlm = kvlm_parse(data)

    def serialize(self):
        return kvlm_serialize(self.kvlm)
    
    def init(self):
        self.kvlm = dict()


argsp = argsubparsers.add_parser("log", help="Display history of a given commit.")
argsp.add_argument(
    "commit",
    default="HEAD",
    nargs="?",
    help="Commit to start at."
)


# usage of log is aas below:
# wyag log e03158242ecab460f31b0d6ae1642880577ccbe8 > log.dot dot -O -Tpdf log.dot

def cmd_log(args):
    repo = repo_find()

    print("digraph wyaglog{")
    print("  node[shape=rect]")
    log_graphviz(repo, object_find(repo, args.commit), set())
    print("}")

def log_graphviz(repo, sha, seen):
    if sha in seen:
        return
    seen.add(sha)

    commit = object_read(repo,sha)
    message = commit.kvlm[None].decode("utf8").strip()
    message = message.replace("\\","\\\\")
    message = message.replace("\"", "\\\"")

    # Keep only the first line
    if "\n" in message:
        message = message[:message.index("\n")]
    print(f"  c_{sha} [label=\"{sha[0:7]}: {message}\"]")
    assert commit.fmt==b'commit'

    if not b'parent' in commit.kvlm.keys():
        # Base case: the init   ial commit.
        return

    parents = commit.kvlm[b'parent']

    if type(parents) != list:
        parents = [ parents ]

    for p in parents:
        p = p.decode("ascii")
        print (f"  c_{sha} -> c_{p};")
        log_graphviz(repo, p, seen)


class GitTreeLeaf(object):
    def __init__(self, mode, path, sha):
        self.mode = mode
        self.path = path
        self.sha = sha

def tree_parse_one(raw, start=0):
    # finding the space terminatorof mode
    x = raw.find(b' ', start)
    assert x-start == 5 or x-start == 6 
    # now we should read the mode:
    mode = raw[start:x]
    if len(mode) ==  5:
        # Normalize to six bytes.
        mode = b"0" + mode

    # Find the NULL terminator of the path
    y = raw.find(b'\x00', x)
    # and read the path
    path = raw[x+1:y]
    # Read the SHA…
    raw_sha = int.from_bytes(raw[y+1:y+21], "big")
    # and convert it into an hex string, padded to 40 chars
    # with zeros if needed.
    sha = format(raw_sha, "040x")
    return y+21, GitTreeLeaf(mode, path.decode("utf8"), sha)

def tree_parse(raw):
    pos = 0
    max = len(raw)
    ret = list()
    while pos < max:
        pos, data = tree_parse_one(raw, pos)
        ret.append(data)

    return ret



def tree_leaf_sort_key(leaf):
    if leaf.mode.startswith(b"10"):
        return leaf.path
    else:
        return leaf.path + "/"
    
def tree_serialize(obj):
    obj.items.sort(key=tree_leaf_sort_key)
    ret = b''
    for i in obj.items:
        ret += i.mode
        ret += b' '
        ret += i.path.encode("utf8")
        ret += b'\x00'
        sha = int(i.sha, 16)
        ret += sha.to_bytes(20, byteorder="big")
    return ret

class GitTree(GitObject):
    fmt=b'tree'

    def deserialize(self, data):
        self.items = tree_parse(data)

    def serialize(self):
        return tree_serialize(self)

    def init(self):
        self.items = list()

argsp = argsubparsers.add_parser("ls-tree", help="Pretty-print a tree object.")
argsp.add_argument("-r",
                   dest="recursive",
                   action="store_true",
                   help="Recurse into sub-trees")

argsp.add_argument("tree",
                   help="A tree-ish object.")

def cmd_ls_tree(args):
    repo = repo_find()
    ls_tree(repo, args.tree, args.recursive)

def ls_tree(repo, ref, recursive=None, prefix=""):
    sha = object_find(repo, ref, fmt=b"tree")
    obj = object_read(repo, sha)
    for item in obj.items:
        if len(item.mode) == 5:
            type = item.mode[0:1]
        else:
            type = item.mode[0:2]

        match type: # Determine the type.
            case b'04': type = "tree"
            case b'10': type = "blob" # A regular file.
            case b'12': type = "blob" # A symlink. Blob contents is link target.
            case b'16': type = "commit" # A submodule
            case _: raise Exception(f"Weird tree leaf mode {item.mode}")

        if not (recursive and type=='tree'): # This is a leaf
            print(f"{'0' * (6 - len(item.mode)) + item.mode.decode("ascii")} {type} {item.sha}\t{os.path.join(prefix, item.path)}")
        else: # This is a branch, recurse
            ls_tree(repo, item.sha, recursive, os.path.join(prefix, item.path))

argsp = argsubparsers.add_parser("checkout", help="Checkout a commit inside of a directory.")

argsp.add_argument("commit",
                   help="The commit or tree to checkout.")

argsp.add_argument("path",
                   help="The EMPTY directory to checkout on.")


def cmd_checkout(args):
    repo = repo_find()

    obj = object_read(repo, object_find(repo, args.commit))

    # If the object is a commit, we grab its tree
    if obj.fmt == b'commit':
        obj = object_read(repo, obj.kvlm[b'tree'].decode("ascii"))

    # Verify that path is an empty directory
    if os.path.exists(args.path):
        if not os.path.isdir(args.path):
            raise Exception(f"Not a directory {args.path}!")
        if os.listdir(args.path):
            raise Exception(f"Not empty {args.path}!")
    else:
        os.makedirs(args.path)

    tree_checkout(repo, obj, os.path.realpath(args.path))

def tree_checkout(repo, tree, path):
    for item in tree.items:
        obj = object_read(repo, item.sha)
        dest = os.path.join(path, item.path)

        if obj.fmt == b'tree':
            os.mkdir(dest)
            tree_checkout(repo, obj, dest)
        elif obj.fmt == b'blob':
            # @TODO Support symlinks (identified by mode 12****)
            with open(dest, 'wb') as f:
                f.write(obj.blobdata)

def ref_resolve(repo, ref):
    path = repo_file(repo, ref)

    # Sometimes, an indirect reference may be broken.  This is normal
    # in one specific case: we're looking for HEAD on a new repository
    # with no commits.  In that case, .git/HEAD points to "ref:
    # refs/heads/main", but .git/refs/heads/main doesn't exist yet
    # (since there's no commit for it to refer to).
    if not os.path.isfile(path):
        return None

    with open(path, 'r') as fp:
        data = fp.read()[:-1]
        # Drop final \n ^^^^^
    if data.startswith("ref: "):
        return ref_resolve(repo, data[5:])
    else:
        return data
    

def ref_list(repo, path=None):
    if not path:
        path = repo_dir(repo, "refs")
    ret = dict()
    # Git shows refs sorted.  To do the same, we sort the output of
    # listdir
    for f in sorted(os.listdir(path)):
        box = os.path.join(path, f)
        if os.path.isdir(box):
            ret[f] = ref_list(repo, box)
        else:
            ret[f] = ref_resolve(repo, box)

    return ret


argsp = argsubparsers.add_parser("show-ref", help="List references.")
def cmd_show_ref(args):
    repo = repo_find()
    refs = ref_list(repo)
    show_ref(repo, refs,prefix='refs')

def show_ref(repo, refs, with_hash=True, prefix=""):
    if prefix:
        prefix += '/'
    for key,value in refs.itme():
        if type(value) == str and with_hash:
            print(f"{value} {prefix}{key}")
        elif type(value) == str:
            print (f"{prefix}{key}")
        else:
            show_ref(repo, value, with_hash=with_hash, prefix=f"{prefix}{key}")


# class GitTag(GitObject):
#     fmt=b'tag'

#     def deserialize(self, data):
#         self.kvlm = kvlm_parse(data)

#     def serialize(self):
#         return kvlm_serialize(self.kvlm)
    
#     def init(self):
#         self.kvlm = dict()

#re use GitCommit!
class GitTag(GitCommit):
    fmt = b'tag'


# now I'm gonna add the tag command!
argsp = argsubparsers.add_parser(
    "tag",
    help="List and create tags")

argsp.add_argument("-a",
                   action="store_true",
                   dest="create_tag_object",
                   help="Whether to create a tag object")

argsp.add_argument("name",
                   nargs="?",
                   help="The new tag's name")

argsp.add_argument("object",
                   default="HEAD",
                   nargs="?",
                   help="The object the new tag will point to")


# git tag                  # List all tags
# git tag NAME [OBJECT]    # create a new *lightweight* tag NAME, pointing
#                          # at HEAD (default) or OBJECT
# git tag -a NAME [OBJECT] # create a new tag *object* NAME, pointing at
#                          # HEAD (default) or OBJECT

def cmd_tag(args):
    repo = repo_find()
    if args.name:
        tag_creat(repo, args.name, args.object, create_tag_object = args.create_tag_object)
    else:
        refs = ref_list(repo)
        show_ref(repo,refs["tag"], with_hash=False)

def tag_creat(repo, name, ref, create_tag_object=False):
    
    #getting the GitObject from object reference
    sha = object_find(repo, ref)
    if create_tag_object:
        tag = GitTag()
        tag.kvlm = dict()
        tag.kvlm[b'object'] = sha.encode()
        tag.kvlm[b'type'] = b'commit'
        tag.kvlm[b'tag'] = name.encode()
        tag.kvlm[None] = b"A tag generated by wyag, which won't let you customize the message!\n"
        tag_sha = object_write(tag, repo)
        ref_create(repo, "tags/"+ name, tag_sha)
    else:
        ref_create(repo,"tags/"+ name, sha)

def ref_create(repo, ref_name, sha):
    with open(repo_file(repo, "refs/" + ref_name), 'w') as fp:
        fp.write(sha + "\n")


def object_resolve(repo, name):
    """Resolve name to an object hash in repo.

This function is aware of:

 - the HEAD literal
    - short and long hashes
    - tags
    - branches
    - remote branches"""

    candidates = list()
    hashRE= re.compile(r"^[0-9A-Fa-f]{4,40}$")
    # If it is an empty string, abort!
    if name.strip() == None:
        return None
    
    if name == 'HEAD':
        return [ref_resolve(repo, "HEAD")]
    
    if hashRE.match(name):
        # This may be a hash, either small or full.  4 seems to be the
        # minimal length for git to consider something a short hash.
        # This limit is documented in man git-rev-parse

        name = name.lower()
        prefix = name[0:2]
        path = repo_dir(repo, "object",mkdir=False)
        if path:
            rem = name[2:]
            for f in os.listdir(path):
                if f.startswith(rem):
                    # Notice a string startswith() itself, so this
                    # works for full hashes.
                    candidates.append(prefix + f) 
    
     # Try for references.
    as_tag = ref_resolve(repo, "refs/tags/" + name)
    if as_tag: # Did we find a tag?
        candidates.append(as_tag)

    as_branch = ref_resolve(repo, "refs/heads/" + name)
    if as_branch: # Did we find a branch?
        candidates.append(as_branch)

    as_remote_branch = ref_resolve(repo, "refs/remotes/" + name)
    if as_remote_branch: # Did we find a remote branch?
        candidates.append(as_remote_branch)

    return candidates        


argsp = argsubparsers.add_parser(
    "rev-parse",
    help="Parse revision (or other objects) identifiers")

argsp.add_argument("--wyag-type",
                   metavar="type",
                   dest="type",
                   choices=["blob", "commit", "tag", "tree"],
                   default=None,
                   help="Specify the expected type")

argsp.add_argument("name",
                   help="The name to parse")


def cmd_rev_parse(args):
    if args.type:
        fmt = args.type.encode()
    else:
        fmt = None

    repo = repo_find()

    print (object_find(repo, args.name, fmt, follow=True))

# $ wyag rev-parse --wyag-type commit HEAD
# 6c22393f5e3830d15395fd8d2f8b0cf8eb40dd58
# $ wyag rev-parse --wyag-type tree HEAD
# 11d33fad71dbac72840aff1447e0d080c7484361
# $ wyag rev-parse --wyag-type tag HEAD
# None 


