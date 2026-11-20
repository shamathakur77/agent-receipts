"""Thin wrappers: a decorator for Python tools and a proxy for MCP client sessions."""
from __future__ import annotations

import functools
import inspect
from typing import Any, Dict, Optional

from .ledger import Ledger


def _bound_args(fn, args, kwargs) -> Dict[str, Any]:
    try:
        return dict(inspect.signature(fn).bind_partial(*args, **kwargs).arguments)
    except TypeError:
        return dict(kwargs)


def receipted(ledger: Ledger, name: Optional[str] = None, *, kind: str = "tool_call",
              purpose: Optional[str] = None, data_categories=(), subject_arg: Optional[str] = None,
              agent_id: Optional[str] = None, run_id: Optional[str] = None):
    """Write one receipt per call, on success and on failure. Works for sync and async functions."""

    def decorator(fn):
        tool = name or fn.__name__
        if inspect.isgeneratorfunction(fn) or inspect.isasyncgenfunction(fn):
            raise TypeError("receipted() does not support generators: the call would be recorded before "
                            "any work happens. Wrap a function that returns the final result instead.")

        def write(args, result, error):
            subject = args.get(subject_arg) if subject_arg else None
            ledger.record(
                kind, tool, outcome="error" if error else "ok", agent_id=agent_id, run_id=run_id,
                purpose=purpose, data_categories=data_categories, subject_id=subject, args=args,
                result=None if error else result,
                error_type=type(error).__name__ if error else None,
            )

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def awrapper(*a, **kw):
                args, result, error = _bound_args(fn, a, kw), None, None
                try:
                    result = await fn(*a, **kw)
                    return result
                except BaseException as exc:
                    error = exc
                    raise
                finally:
                    write(args, result, error)
            return awrapper

        @functools.wraps(fn)
        def wrapper(*a, **kw):
            args, result, error = _bound_args(fn, a, kw), None, None
            try:
                result = fn(*a, **kw)
                return result
            except BaseException as exc:
                error = exc
                raise
            finally:
                write(args, result, error)
        return wrapper

    return decorator


class ReceiptedSession:
    """Wrap any object with an async ``call_tool(name, arguments)``, such as an MCP ClientSession.

    ``tool_meta`` marks which tools touch personal data, for example::

        {"lookup_customer": {"purpose": "support", "data_categories": ["contact"],
                             "subject_arg": "customer_id"}}
    """

    def __init__(self, session, ledger: Ledger, *, agent_id: Optional[str] = None,
                 run_id: Optional[str] = None, tool_meta: Optional[Dict[str, Dict[str, Any]]] = None):
        self._session, self._ledger = session, ledger
        self._agent_id, self._run_id = agent_id, run_id
        self._meta = tool_meta or {}

    def __getattr__(self, item):  # every other method passes straight through
        return getattr(self._session, item)

    async def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None, *a, **kw):
        meta = self._meta.get(name, {})
        outcome, error_type, result = "ok", None, None
        try:
            result = await self._session.call_tool(name, arguments, *a, **kw)
            # mcp 1.x names it isError, mcp 2.x names it is_error
            if getattr(result, "isError", False) or getattr(result, "is_error", False):
                outcome, error_type = "error", "ToolResultError"
            return result
        except BaseException as exc:
            outcome, error_type = "error", type(exc).__name__
            raise
        finally:
            subject_arg = meta.get("subject_arg")
            self._ledger.record(
                "tool_call", name, outcome=outcome, agent_id=self._agent_id, run_id=self._run_id,
                purpose=meta.get("purpose"), data_categories=meta.get("data_categories", ()),
                subject_id=(arguments or {}).get(subject_arg) if subject_arg else None,
                args=arguments, result=result if outcome == "ok" else None, error_type=error_type,
            )
