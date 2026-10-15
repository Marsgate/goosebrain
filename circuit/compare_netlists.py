"""Compare two KiCad netlists net-by-net.

Usage:
    python compare_netlists.py REFERENCE.net CANDIDATE.net
    python compare_netlists.py --dump NETLIST.net

Nets are matched by their set of (ref, pin) connections, so net names don't
have to agree. Parts are compared on value, footprint and LCSC part number, ignoring
surrounding whitespace.
Exits non-zero when anything differs.
"""

import re
import sys

TOKEN = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')


def parse_sexp(text):
    stack = [[]]
    for tok in TOKEN.findall(text):
        if tok == "(":
            stack.append([])
        elif tok == ")":
            done = stack.pop()
            stack[-1].append(done)
        elif tok.startswith('"'):
            stack[-1].append(tok[1:-1].replace('\\"', '"').replace("\\\\", "\\"))
        else:
            stack[-1].append(tok)
    return stack[0][0]


def children(node, name):
    return [c for c in node[1:] if isinstance(c, list) and c and c[0] == name]


def child(node, name):
    found = children(node, name)
    return found[0] if found else None


def value_of(node, name, default=""):
    c = child(node, name)
    return c[1] if c is not None and len(c) > 1 else default


def load(path):
    with open(path, encoding="utf-8") as f:
        root = parse_sexp(f.read())

    parts = {}
    for comp in children(child(root, "components"), "comp"):
        ref = value_of(comp, "ref")
        fields = {}
        fields_node = child(comp, "fields")
        if fields_node is not None:
            for field in children(fields_node, "field"):
                name = value_of(field, "name")
                fields[name] = field[2] if len(field) > 2 else ""
        lib = child(comp, "libsource")
        parts[ref] = {
            "value": value_of(comp, "value"),
            "footprint": value_of(comp, "footprint"),
            "lcsc": fields.get("LCSC Part #", ""),
            "lib": f"{value_of(lib, 'lib')}:{value_of(lib, 'part')}" if lib else "",
        }

    nets = {}
    for net in children(child(root, "nets"), "net"):
        name = value_of(net, "name")
        nodes = frozenset(
            (value_of(n, "ref"), value_of(n, "pin")) for n in children(net, "node")
        )
        nets[name] = nodes
    return parts, nets


def dump(path):
    parts, nets = load(path)
    print("# Parts")
    for ref in sorted(parts, key=natural_key):
        p = parts[ref]
        print(f"{ref}\t{p['lib']}\t{p['value']}\t{p['footprint']}\t{p['lcsc']}")
    print("\n# Nets")
    for name in sorted(nets):
        pins = " ".join(f"{r}.{p}" for r, p in sorted(nets[name], key=lambda rp: (natural_key(rp[0]), natural_key(rp[1]))))
        print(f"{name}: {pins}")


def natural_key(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def compare(ref_path, cand_path):
    ref_parts, ref_nets = load(ref_path)
    cand_parts, cand_nets = load(cand_path)
    problems = []

    for ref in sorted(set(ref_parts) | set(cand_parts), key=natural_key):
        if ref not in cand_parts:
            problems.append(f"part {ref} missing from candidate")
        elif ref not in ref_parts:
            problems.append(f"part {ref} only in candidate")
        else:
            for key in ("value", "footprint", "lcsc"):
                a, b = ref_parts[ref][key], cand_parts[ref][key]
                if a.strip() != b.strip():
                    problems.append(f"part {ref} {key}: {a!r} != {b!r}")

    # Single-pin nets are unconnected pins; compare only real connections.
    ref_conns = {nodes: name for name, nodes in ref_nets.items() if len(nodes) > 1}
    cand_conns = {nodes: name for name, nodes in cand_nets.items() if len(nodes) > 1}
    for nodes in ref_conns.keys() - cand_conns.keys():
        problems.append(f"net {ref_conns[nodes]} not matched: {fmt(nodes)}")
    for nodes in cand_conns.keys() - ref_conns.keys():
        problems.append(f"candidate net {cand_conns[nodes]} not in reference: {fmt(nodes)}")

    matched = len(ref_conns.keys() & cand_conns.keys())
    print(f"parts: {len(ref_parts)} reference, {len(cand_parts)} candidate")
    print(f"connected nets: {len(ref_conns)} reference, {len(cand_conns)} candidate, {matched} identical")
    for p in problems:
        print("DIFF", p)
    print("MATCH" if not problems else f"{len(problems)} difference(s)")
    return not problems


def fmt(nodes):
    return " ".join(f"{r}.{p}" for r, p in sorted(nodes, key=lambda rp: (natural_key(rp[0]), natural_key(rp[1]))))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--dump":
        dump(sys.argv[2])
    elif len(sys.argv) == 3:
        sys.exit(0 if compare(sys.argv[1], sys.argv[2]) else 1)
    else:
        sys.exit(__doc__)
