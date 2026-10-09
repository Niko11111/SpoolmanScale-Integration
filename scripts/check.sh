#!/usr/bin/env bash
# House rules of this repository, checked by machine. Exit 1 on any finding.
set -u
cd "$(dirname "$0")/.."

fail=0
ok()  { printf 'ok    %s\n' "$*"; }
bad() { printf 'FAIL  %s\n' "$*"; fail=1; }

# Tracked and not-yet-tracked files alike, so the rules hold before the first
# commit too. Ignored files stay out.
files() { git ls-files -z --cached --others --exclude-standard; }

# 1. No em-dash (U+2014). The one file allowed to carry any is the CC BY
#    legal text, which is not ours to edit.
hits=$(files | grep -zv '^LICENSE-CC-BY-4.0.txt$' | xargs -0 env LC_ALL=C grep -n $'\xe2\x80\x94' 2>/dev/null || true)
if [ -n "$hits" ]; then bad "em-dash found:"; echo "$hits" | sed 's/^/        /'; else ok "no em-dash"; fi

# 2. Python: compiles, and keeps to the limits (50 lines per function,
#    5 parameters, 3 levels of nesting, 1000 lines per file).
hits=$(files | grep -z '\.py$' | xargs -0 python3 - <<'PY'
import ast, sys
MAX_FUNC_LINES, MAX_PARAMS, MAX_NESTING, MAX_FILE_LINES = 50, 5, 3, 1000
NESTING = (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.AsyncFor, ast.AsyncWith)

def depth(node, level=0):
    worst = level
    for child in ast.iter_child_nodes(node):
        step = level + 1 if isinstance(child, NESTING) else level
        worst = max(worst, depth(child, step))
    return worst

for path in sys.argv[1:]:
    src = open(path, encoding="utf-8").read()
    try:
        tree = ast.parse(src, path)
    except SyntaxError as err:
        print(f"{path}:{err.lineno}: syntax error: {err.msg}"); continue
    lines = src.count("\n")
    if lines > MAX_FILE_LINES:
        print(f"{path}: {lines} lines, limit {MAX_FILE_LINES}")
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        length = node.end_lineno - node.lineno + 1
        params = len(node.args.args) + len(node.args.kwonlyargs)
        if length > MAX_FUNC_LINES:
            print(f"{path}:{node.lineno}: {node.name}() is {length} lines, limit {MAX_FUNC_LINES}")
        if params > MAX_PARAMS:
            print(f"{path}:{node.lineno}: {node.name}() has {params} parameters, limit {MAX_PARAMS}")
        if depth(node) > MAX_NESTING:
            print(f"{path}:{node.lineno}: {node.name}() nests {depth(node)} deep, limit {MAX_NESTING}")
PY
)
if [ -n "$hits" ]; then bad "python limits:"; echo "$hits" | sed 's/^/        /'; else ok "python compiles and keeps to the limits"; fi

# 3. Every relative link in a Markdown file points at a file that exists.
hits=$(files | grep -z '\.md$' | xargs -0 python3 - <<'PY'
import os, re, sys
LINK = re.compile(r'\]\(([^)#\s]+)(#[^)]*)?\)')
for path in sys.argv[1:]:
    text = open(path, encoding="utf-8").read()
    for target, _anchor in LINK.findall(text):
        if "://" in target or target.startswith("mailto:"):
            continue
        if not os.path.exists(os.path.join(os.path.dirname(path), target)):
            print(f"{path}: link to missing file {target}")
PY
)
if [ -n "$hits" ]; then bad "markdown links:"; echo "$hits" | sed 's/^/        /'; else ok "markdown links resolve"; fi

# 4. The checker runs, and the rules behind it pass their tests.
if python3 check/check_inventory.py --help >/dev/null 2>&1; then ok "check_inventory.py --help"; else bad "check_inventory.py --help fails"; fi
out=$(python3 -m unittest discover -s tests 2>&1)
if echo "$out" | tail -1 | grep -q '^OK'; then ok "unit tests: $(echo "$out" | grep -o 'Ran [0-9]* tests')"; else bad "unit tests:"; echo "$out" | tail -15 | sed 's/^/        /'; fi

# 5. Part versions in CHANGELOG.md and common.md agree.
v_log=$(sed -nE 's/^### Version ([0-9]+) .*/\1/p' CHANGELOG.md | head -1)
v_common=$(grep -E '^\| 1, \[Inventory\]' common.md | awk -F'|' '{gsub(/ /,"",$4); print $4}')
if [ -n "$v_log" ] && [ "$v_log" = "$v_common" ]; then ok "inventory version $v_log in CHANGELOG.md and common.md"; else bad "inventory version differs: CHANGELOG.md '$v_log', common.md '$v_common'"; fi

[ $fail -eq 0 ] && echo "all checks passed" || echo "CHECK FAILED"
exit $fail
