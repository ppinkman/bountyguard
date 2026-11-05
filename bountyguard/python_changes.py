"""Bounded AST comparison. Submitted Python is parsed, never executed."""
import ast

from .domain import GuardError


class WithoutDocstrings(ast.NodeTransformer):
    def body(self, node):
        self.generic_visit(node)
        if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str):
            node.body = node.body[1:]
        return node

    visit_Module = body
    visit_ClassDef = body
    visit_FunctionDef = body
    visit_AsyncFunctionDef = body


def implementation_changed(before: str, after: str) -> bool:
    trees = []
    for text in (before, after):
        if len(text.encode("utf-8")) > 100_000:
            raise GuardError("Python source exceeds the bounded implementation check; manual review is required.")
        try:
            tree = ast.parse(text)
            if sum(1 for _ in ast.walk(tree)) > 20_000:
                raise GuardError("Python AST exceeds the bounded implementation check.")
            trees.append(ast.dump(WithoutDocstrings().visit(tree), include_attributes=False))
        except (SyntaxError, ValueError, RecursionError):
            raise GuardError("Python source cannot be structurally compared; automatic acceptance is blocked.") from None
    return trees[0] != trees[1]

# Controlled revision-mutation probe; this commit is archived, not merged.
TOCTOU_DEMO_MARKER = "unreviewed revision"
