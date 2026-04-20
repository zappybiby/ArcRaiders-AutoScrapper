---

name: language-optimization
description: Optimize code for readability, performance, maintainability, and security across Python. Use when asked to improve code quality, optimize performance, add type safety, or refactor for idioms

# Language Optimization

Optimize code across languages following universal principles and language-specific idioms.
<instructions>

## Workflow

Think through optimization systematically:

1. **Analyze**: Identify issues - lint errors, type errors, performance bottlenecks, security gaps
2. **Profile first**: Measure before optimizing performance (never optimize without data)
3. **Apply fixes**: Follow language-specific standards from `instructions/`
4. **Verify**: All tests pass, metrics improved, no regressions

## Universal Principles

<principles>

- KISS: Simple over clever; readability first
- YAGNI: Don't build before needed; no premature optimization
- DRY: Extract repeated logic; single source of truth
- Fail Fast: Validate early; specific error messages
- Security: No secrets in code; validate at boundaries
</principles>

## Optimization Targets (Priority Order)

1. **Correctness**: Fix bugs, handle edge cases
2. **Type safety**: Add/improve type annotations
3. **Readability**: Clear names, reduce nesting, simplify logic
4. **Performance**: Only after profiling identifies bottlenecks
5. **Security**: Input validation, secret management, dependency audit
</instructions>
<language_specific>

## Python

- Standards: `.github/instructions/python.instructions.md`
- Always: type hints on public functions, `T | None` not `Optional[T]`
- Tools: `ruff` (lint+format), `mypy` (types), `pytest` (tests)
- Prefer: generators over lists, `pathlib` over `os.path`, f-strings over `.format()`
</language_specific>
<performance_patterns>

## Common Optimizations

Algorithm, Before=O(n^2) nested loops, After=O(n) hash map lookup
Caching, Before=Recompute every call, After=Memoize/cache result
Lazy eval, Before=Build full list, After=Generator/iterator
Batching, Before=N individual calls, After=Single batch operation
Built-ins, Before=Custom implementation, After=Standard library function

## Performance Workflow

1. Set baseline benchmark
2. Profile to find bottleneck (not guess)
3. Apply targeted optimization
4. Measure improvement against baseline
5. Document trade-off if complexity increased
</performance_patterns>
<examples>

### Python: Add type safety

```python

# Before
def get_user(id, include_posts=False):
 user = db.find(id)
 if include_posts:
 user['posts'] = db.posts(id)
 return user

# After
def get_user(user_id: int, *, include_posts: bool = False) -> User | None:
 user = db.find(user_id)
 if user is None:
 return None
 user.posts = db.posts(user_id)
```

</examples>

## Success Criteria

Optimization is complete when:

- All linter/type checks pass with zero warnings
- Test suite passes with no regressions
- Performance improved (if that was the goal, with measurements)
- Code follows language-specific idioms from `.github/instructions/`
