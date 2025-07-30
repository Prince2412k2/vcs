from argparse import ArgumentParser
import os
import sys
import textwrap
import subprocess

from . import base
from . import data
from . import diff


def main():
    args = parse_args()
    args.func(args)


def parse_args():
    parser = ArgumentParser()
    # parser.set_defaults(func=help)
    commands = parser.add_subparsers(dest="command")
    commands.required = True

    oid = base.get_oid
    # init parser
    init_parser = commands.add_parser("init", help="initialize a repo")
    init_parser.set_defaults(func=init)

    # hash parser
    hash_object_parser = commands.add_parser("hash-object")
    hash_object_parser.set_defaults(func=hash_object)
    hash_object_parser.add_argument("file")

    # cat-file parser
    cat_file_object_parser = commands.add_parser("cat-file")
    cat_file_object_parser.set_defaults(func=cat_file)
    cat_file_object_parser.add_argument("object", type=oid)

    # write-tree parser
    write_tree_parser = commands.add_parser("write-tree")
    write_tree_parser.set_defaults(func=write_tree)

    # read-tree parser
    read_tree_parser = commands.add_parser("read-tree")
    read_tree_parser.set_defaults(func=read_tree)
    read_tree_parser.add_argument("tree", type=oid)

    # commit-tree parser
    commit_tree_parser = commands.add_parser("commit")
    commit_tree_parser.set_defaults(func=commit)
    commit_tree_parser.add_argument("-m", "--message", required=True)

    # log parser
    log_parser = commands.add_parser("log")
    log_parser.set_defaults(func=log)
    log_parser.add_argument("oid", default="@", type=oid, nargs="?")
    log_parser.add_argument(
        "--oneline", action="store_true", help="Show log in one-line format"
    )

    # show parser
    show_parser = commands.add_parser("show")
    show_parser.set_defaults(func=show)
    show_parser.add_argument("oid", default="@", type=oid, nargs="?")

    # diff parser
    diff_parser = commands.add_parser("diff")
    diff_parser.set_defaults(func=_diff)
    diff_parser.add_argument("commit", default="@", type=oid, nargs="?")

    # checkout parser
    checkout_parser = commands.add_parser("checkout")
    checkout_parser.set_defaults(func=checkout)
    checkout_parser.add_argument("commit")

    # tag parser
    tag_parser = commands.add_parser("tag")
    tag_parser.set_defaults(func=tag)
    tag_parser.add_argument("name")
    tag_parser.add_argument("oid", default="@", type=oid, nargs="?")

    # branch parser
    branch_parser = commands.add_parser("branch")
    branch_parser.set_defaults(func=branch)
    branch_parser.add_argument("name", nargs="?")
    branch_parser.add_argument("start_point", default="@", type=oid, nargs="?")

    # k_vcs parser
    k_parser = commands.add_parser("k")
    k_parser.set_defaults(func=k)

    # status_vcs parser
    status_parser = commands.add_parser("status")
    status_parser.set_defaults(func=status)

    # reset parser
    reset_parser = commands.add_parser("reset")
    reset_parser.set_defaults(func=reset)
    reset_parser.add_argument("commit", type=oid)

    # merge parser
    merge_parser = commands.add_parser("merge")
    merge_parser.set_defaults(func=merge)
    merge_parser.add_argument("commit", type=oid)

    # merge_base parser
    merge_base_parser = commands.add_parser("merge-base")
    merge_base_parser.set_defaults(func=merge_base)
    merge_base_parser.add_argument("commit1", type=oid)
    merge_base_parser.add_argument("commit2", type=oid)

    return parser.parse_args()


def init(args):
    base.init()
    sys.stdout.write("\033[2K\r")
    sys.stdout.flush()
    print(f"initialized vcs repo at {os.getcwd()}/{data.VCS_DIR}")


def hash_object(args):
    with open(args.file, "rb") as f:
        print(data.hash_object(f.read()))


def cat_file(args):
    sys.stdout.flush()
    sys.stdout.buffer.write(
        data.get_object(args.object, expected=None)  # pyright: ignore
    )


def write_tree(args):
    print(base.write_tree())


def read_tree(args):
    base.read_tree(args.tree)


def commit(args):
    print(base.commit(args.message))


def print_line(color="\033[94m", len=50):
    print(color, end="")
    print("-" * len)
    print("\033[0m", end="")


def _print_commit(oid, commit, refs=None):
    refs_str = f"(\033[96m{', '.join(refs)}\033[93m)\033[0m" if refs else ""
    print(f"\033[93mcommit {oid}{refs_str}\033[0m\n")
    print(textwrap.indent(commit.message, "    "))
    print("")


def _print_commit_oneline(oid, commit, refs=None):
    refs_str = f"(\033[96m{', '.join(refs)}\033[93m)\033[0m" if refs else ""
    print(f"\033[93m{oid}{refs_str}\033[0m - ", end="")
    print(textwrap.indent(commit.message, " "), end="")
    print("")


def log(args):
    print_commit_func = _print_commit_oneline if args.oneline else _print_commit

    refs = {}
    for refname, ref in data.iter_refs():
        refs.setdefault(ref.value, []).append(refname)
    for oid in base.iter_commits_and_parents({args.oid}):
        commit = base.get_commit(oid)
        print_commit_func(oid, commit, refs.get(oid))


def show(args):
    if not args.oid:
        return
    commit = base.get_commit(args.oid)
    parent_tree = None
    if commit.parents:
        parent_tree = base.get_commit(commit.parents[0]).tree
    _print_commit(args.oid, commit)
    result = diff.diff_trees(base.get_tree(parent_tree), base.get_tree(commit.tree))
    sys.stdout.flush()
    sys.stdout.buffer.write(result)


def _diff(args):
    tree = args.commit and base.get_commit(args.commit).tree
    result = diff.diff_trees(base.get_tree(tree), base.get_working_tree())
    sys.stdout.flush()
    sys.stdout.buffer.write(result)


def checkout(args):
    base.checkout(args.commit)


def tag(args):
    base.create_tag(args.name, args.oid)


def branch(args):
    if not args.name:
        current = base.get_branch_name()
        for branch in base.iter_branch_names():
            prefix = "*" if branch == current else " "
            print(f"{prefix} {branch}")
    else:
        base.create_branch(args.name, args.start_point)
        print(f"Branch {args.name} created at {args.start_point[:10]}")


def k(args):
    dot = "digraph commits {\n"
    oids = set()
    for refname, ref in data.iter_refs(deref=False):
        dot += f'"{refname}"[shape=note]\n'
        dot += f'"{refname}" -> "{ref.value}"\n'
        if not ref.symbolic:
            oids.add(ref.value)
    for oid in base.iter_commits_and_parents(oids):
        commit = base.get_commit(oid)
        dot += (
            f'"{oid}" [shape=box style=filled label="{oid[:10]}\n{commit.message}"]\n'
        )
        for parent in commit.parents:
            dot += f'"{oid}" -> "{parent}"\n'
    dot += "}"

    with subprocess.Popen(
        ["dot", "-Tx11", "/dev/stdin"], stdin=subprocess.PIPE
    ) as proc:
        proc.communicate(dot.encode())


def status(args):
    head = base.get_oid("@")
    branch = base.get_branch_name()
    if branch:
        print(f"On branch {branch}")
    else:
        assert head
        print(f"HEAD detached at {head[:10]}")

    merge_head = data.get_ref("merge_head").value
    if merge_head:
        print(f"Merging with {merge_head[:10]}")

    print("\nChanges to be commited:\n")
    head_tree = head and base.get_commit(head).tree

    print("\033[91m", end="")  # for red color
    for path, action in diff.iter_changed_files(
        base.get_tree(head_tree), base.get_working_tree()
    ):
        print(f"    {action:.12}:  {path}")

    print("\033[0m", end="")  # for red color


def reset(args):
    base.reset(args.commit)


def merge(args):
    base.merge(args.commit)


def merge_base(args):
    print(base.get_merge_base(args.commit1, args.commit2))
