import os
import itertools
import operator
from collections import namedtuple, deque
import string

from . import data
from . import diff


def close():
    if not data.IS_INIT:
        print("")
        exit(0)


def init():
    data.init()
    data.update_ref("HEAD", data.RefValue(symbolic=True, value="refs/heads/master"))


def write_tree(directory="."):
    entries = []
    with os.scandir(directory) as it:
        for entry in it:
            full = f"{directory}/{entry.name}"
            if is_ignored(full):
                continue
            if entry.is_file(follow_symlinks=False):
                type_ = "blob"
                with open(full, "rb") as f:
                    oid = data.hash_object(f.read())
            elif entry.is_dir(follow_symlinks=False):
                type_ = "tree"
                oid = write_tree(full)
            entries.append((entry.name, oid, type_))  # pyright: ignore
    tree = "".join(f"{type_} {oid} {name}\n" for name, oid, type_ in sorted(entries))
    return data.hash_object(tree.encode(), "tree")


def _iter_tree_entries(oid):
    if not oid:
        return
    tree = data.get_object(oid, "tree")
    for entry in tree.decode().splitlines():
        type_, oid, name = entry.split(" ", 2)
        yield type_, oid, name


def get_tree(oid, base_path=""):
    result = {}
    for type_, oid, name in _iter_tree_entries(oid):
        if "/" in name or name in ("..", "."):
            raise ValueError(f"invalid {name=}")
        path = base_path + name
        if type_ == "blob":
            result[path] = oid
        elif type_ == "tree":
            result.update(get_tree(oid, f"{path}/"))
        else:
            raise ValueError(f"Unknown tree entry {type_}")
    return result


def get_working_tree():
    result = {}
    for root, _, filenames in os.walk(os.path.dirname(data.VCS_DIR)):
        for filename in filenames:
            path = os.path.relpath(f"{root}/{filename}")
            if is_ignored(path) or not os.path.isfile(path):
                continue
            with open(path, "rb") as f:
                result[path] = data.hash_object(f.read())
    return result


def _empty_current_directory():
    for root, dirnames, filenames in os.walk(".", topdown=False):
        for filename in filenames:
            path = os.path.relpath(f"{root}/{filename}")
            if is_ignored(path) or not os.path.isfile(path):
                continue
            os.remove(path)
        for dirname in dirnames:
            path = os.path.relpath(f"{root}/{dirname}")
            if is_ignored(path):
                continue
            try:
                os.rmdir(path)
            except (FileNotFoundError, OSError):
                pass


def read_tree(tree_oid):
    _empty_current_directory()
    for path, oid in get_tree(tree_oid, base_path="./").items():
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data.get_object(oid))


def read_tree_merged(t_head, t_other):
    _empty_current_directory()
    for path, blob in diff.merge_trees(get_tree(t_head), get_tree(t_other)).items():
        os.makedirs(f"./{os.path.dirname(path)}", exist_ok=True)
        with open(path, "wb") as f:
            f.write(blob)


def commit(message):
    commit = f"tree {write_tree()}\n"
    head = data.get_ref("HEAD").value
    if head:
        commit += f"parent {head}\n"
    merge_head = data.get_ref("MERGE_HEAD").value
    if merge_head:
        commit += f"parent {merge_head}\n"
        data.delete_ref("MERGE_HEAD", deref=False)

    commit += "\n"
    commit += f"{message}\n"

    oid = data.hash_object(commit.encode(), "commit")
    data.update_ref("HEAD", data.RefValue(symbolic=False, value=oid))
    return oid


def checkout(name):
    oid = get_oid(name)
    commit = get_commit(oid)
    read_tree(commit.tree)
    if is_branch(name):
        head = data.RefValue(symbolic=True, value=f"refs/heads/{name}")
    else:
        head = data.RefValue(symbolic=False, value=oid)
    data.update_ref("HEAD", head, deref=False)


def reset(oid):
    data.update_ref("HEAD", data.RefValue(symbolic=False, value=oid))


def merge(other):
    head = data.get_ref("HEAD").value
    if not head:
        raise ValueError
    c_head = get_commit(head)
    c_other = get_commit(other)

    read_tree_merged(c_head.tree, c_other.tree)
    print("Merged in working tree\nPlease commit")


def is_branch(branch):
    return data.get_ref(f"refs/heads/{branch}").value is not None


def get_branch_name():
    head = data.get_ref("HEAD", deref=False)
    if not head.symbolic:
        return None
    head = head.value
    if not head.startswith("refs/heads/"):
        raise ValueError
    return os.path.relpath(head, "refs/heads")


def get_merge_base(oid1, oid2):
    parents1 = set(iter_commits_and_parents({oid1}))
    for oid in iter_commits_and_parents({oid2}):
        if oid in parents1:
            return oid


def create_tag(name, oid):
    data.update_ref(f"refs/tags/{name}", data.RefValue(symbolic=False, value=oid))


def create_branch(name, oid):
    data.update_ref(f"refs/heads/{name}", data.RefValue(symbolic=False, value=oid))


def iter_branch_names():
    for refname, _ in data.iter_refs("refs/heads/"):
        yield os.path.relpath(refname, "refs/heads/")


Commit = namedtuple("Commit", ["tree", "parents", "message"])


def get_commit(oid):
    parents = []
    tree = None
    commit = data.get_object(oid, "commit").decode()
    lines = iter(commit.splitlines())
    for line in itertools.takewhile(operator.truth, lines):
        key, value = line.split(" ", 1)
        if key == "tree":
            tree = value
        elif key == "parent":
            parents.append(value)
        else:
            raise ValueError(f"Unknown field {key}")
    message = "\n".join(lines)
    return Commit(tree=tree, parents=parents, message=message)


def iter_commits_and_parents(oids):
    oids = deque(oids)
    visited = set()
    while oids:
        oid = oids.popleft()
        if not oid or oid in visited:
            continue
        visited.add(oid)
        yield oid
        commit = get_commit(oid)
        oids.extendleft(commit.parents[:1])
        oids.extend(commit.parents[1:])


def get_oid(name):
    close()
    if name == "@":
        name = "HEAD"
    refs_to_try = [
        f"{name}",
        f"refs/{name}",
        f"refs/tags/{name}",
        f"refs/heads/{name}",
    ]
    for ref in refs_to_try:
        if data.get_ref(ref, deref=False).value:
            return data.get_ref(ref).value
    is_hex = all(c in string.hexdigits for c in name)
    if len(name) == 40 and is_hex:
        return name
    raise ValueError(f"Unknown name {name}")


def is_ignored(path):
    return ".vcs" in path.split("/")
