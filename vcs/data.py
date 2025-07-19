from functools import lru_cache
import os
import hashlib
from collections import namedtuple

global VCS_DIR


def get_vcs_dir():
    current_path = os.getcwd()
    home_dir = os.path.expanduser("~")
    while True:
        if ".vcs" in os.listdir(current_path):
            return os.path.join(current_path, ".vcs")

        current_path = os.path.dirname(current_path)
        if current_path == home_dir:
            break


def init():
    global VCS_DIR
    if os.path.exists(".vcs"):
        print("VCS already initialized")
        return
    os.makedirs(".vcs")
    os.makedirs(os.path.join(".vcs", "objects"))
    VCS_DIR = ".vcs"


VCS_DIR = get_vcs_dir()

RefValue = namedtuple("RefValue", ["symbolic", "value"])


def update_ref(ref, value, deref=True):
    ref = _get_ref_internal(ref, deref)[0]
    if not value.value:
        raise ValueError
    if value.symbolic:
        value = f"ref: {value.value}"
    else:
        value = value.value
    ref_path = f"{VCS_DIR}/{ref}"
    os.makedirs(os.path.dirname(ref_path), exist_ok=True)
    with open(ref_path, "w") as f:
        f.write(value)


def get_ref(ref, deref=True):
    return _get_ref_internal(ref, deref)[1]


def _get_ref_internal(ref, deref):
    ref_path = f"{VCS_DIR}/{ref}"
    value = None
    if os.path.isfile(ref_path):
        with open(ref_path) as f:
            value = f.read().strip()
    symbolic = bool(value) and value.startswith("ref:")
    if symbolic and value:
        value = value.split(":", 1)[1].strip()
        if deref:
            return _get_ref_internal(value, deref=True)
    return ref, RefValue(symbolic=symbolic, value=value)


def iter_refs(prefix="", deref=True):
    refs = ["HEAD"]
    for root, _, filenames in os.walk(f"{VCS_DIR}/refs/"):
        root = os.path.relpath(root, VCS_DIR)
        refs.extend(f"{root}/{name}" for name in filenames)
    for refname in refs:
        if not refname.startswith(prefix):
            continue
        yield refname, get_ref(refname, deref=deref)


def hash_object(data: bytes, type_="blob") -> str:
    obj = type_.encode() + b"\x00" + data
    oid = hashlib.sha1(obj).hexdigest()
    with open(f"{VCS_DIR}/objects/{oid}", "wb") as out:
        out.write(obj)
    return oid


def get_object(oid: str, expected="blob") -> bytes:
    """getting a object from repo"""
    with open(f"{VCS_DIR}/objects/{oid}", "rb") as f:
        obj = f.read()
    type_, _, content = obj.partition(b"\x00")
    type_ = type_.decode()

    if expected is not None:
        if type_ != expected:
            raise ValueError(f"Expected {expected}, got {type_}")
    return content
