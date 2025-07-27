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

# def repo_file(repo, *path, mkdir=False):
#     """Same as repo_path, but create dirname(*path) if absent.  For
# example, repo_file(r, \"refs\", \"remotes\", \"origin\", \"HEAD\") will create
# .git/refs/remotes/origin."""

#     if repo_dir(repo, *path[:-1], mkdir=mkdir):
#         return repo_path(repo, *path)
    
# def repo_dir(repo, *path, mkdir=False):
#     """Same as repo_path, but mkdir *path if absent if mkdir."""

#     path = repo_path(repo, *path)

#     if os.path.exists(path):
#         if (os.path.isdir(path)):
#             return path
#         else:
#             raise Exception(f"Not a directory {path}")

#     if mkdir:
#         os.makedirs(path)
#         return path
#     else:
#         return None
    
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


