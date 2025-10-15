"""Optional integration helpers for the external scopinator project."""

from __future__ import annotations

import importlib
import inspect
import json
from types import ModuleType
from typing import Any, Callable, Iterable, Optional, Sequence


class ScopinatorNotAvailableError(RuntimeError):
    """Raised when scopinator cannot be imported or instantiated."""


class ScopinatorCallError(RuntimeError):
    """Raised when a scopinator call fails."""


class ScopinatorBridge:
    """Dynamically integrate with the optional scopinator package.

    The scopinator project changed names a few times (``scopinator`` vs
    ``pyscopinator``) and the public surface is still in flux.  This bridge uses
    a collection of heuristics so that we can take advantage of any compatible
    installation without taking a hard dependency on a specific release.
    """

    _MODULE_NAMES: Sequence[str] = ("scopinator", "pyscopinator")
    _SUBMODULE_NAMES: Sequence[str] = ("client", "api", "core", "device")
    _CONSTRUCTOR_NAMES: Sequence[str] = (
        "SeestarClient",
        "Seestar",
        "ScopinatorClient",
        "ScopeClient",
        "Scope",
        "Client",
        "Controller",
        "Connection",
    )
    _FUNCTION_CONSTRUCTORS: Sequence[str] = (
        "create_client",
        "make_client",
        "get_client",
        "connect",
        "open_connection",
    )
    _SYNC_NAMES: Sequence[str] = (
        "call_sync",
        "method_sync",
        "call",
        "request",
        "send_sync",
        "execute",
        "invoke",
        "send_request",
    )
    _ASYNC_NAMES: Sequence[str] = (
        "call_async",
        "method_async",
        "send_async",
        "queue",
        "enqueue",
        "execute_async",
        "request_async",
    )
    _RAW_NAMES: Sequence[str] = (
        "send",
        "send_raw",
        "send_message",
        "send_json",
        "write",
        "emit",
    )

    def __init__(
        self,
        logger,
        host: str,
        port: int,
        device_name: str,
        *,
        prefer: bool = False,
        timeout: Optional[float] = None,
    ) -> None:
        self.logger = logger
        self.host = host
        self.port = port
        self.device_name = device_name
        self.prefer = prefer
        self.timeout = timeout

        self._module = self._import_module()
        self._client = self._create_client(self._module)
        self._sync_callables = self._collect_callables(self._SYNC_NAMES)
        self._async_callables = self._collect_callables(self._ASYNC_NAMES)
        self._raw_callables = self._collect_callables(self._RAW_NAMES)

        if not self._sync_callables and self._async_callables:
            # Allow using async callables as a synchronous fallback.
            self._sync_callables = list(self._async_callables)

        if not (self._sync_callables or self._async_callables or self._raw_callables):
            raise ScopinatorNotAvailableError(
                "scopinator module was located but no compatible call interfaces were found"
            )

        self.logger.info(
            "Scopinator integration enabled for %s using %s",
            self.device_name,
            type(self._client).__name__,
        )

    # ------------------------------------------------------------------
    # public helpers
    # ------------------------------------------------------------------
    @classmethod
    def create(
        cls,
        logger,
        host: str,
        port: int,
        device_name: str,
        *,
        prefer: bool = False,
        timeout: Optional[float] = None,
    ) -> Optional["ScopinatorBridge"]:
        try:
            return cls(logger, host, port, device_name, prefer=prefer, timeout=timeout)
        except ScopinatorNotAvailableError as exc:
            logger.info("Scopinator integration unavailable: %s", exc)
            return None

    def is_ready(self) -> bool:
        return self._client is not None

    # synchronous ------------------------------------------------------
    def call_sync(self, payload: dict[str, Any]) -> Any:
        return self._invoke_candidates(self._sync_callables, payload, wait=True)

    # asynchronous -----------------------------------------------------
    def call_async(self, payload: dict[str, Any]) -> Any:
        try:
            return self._invoke_candidates(self._async_callables, payload, wait=False)
        except ScopinatorCallError:
            # Fallback to synchronous if no dedicated async call exists.
            return self._invoke_candidates(self._sync_callables, payload, wait=False)

    # raw --------------------------------------------------------------
    def send_raw(self, data: str) -> Any:
        payload = {"method": None, "raw": data}
        return self._invoke_candidates(self._raw_callables, payload, wait=False)

    # ------------------------------------------------------------------
    # dynamic discovery helpers
    # ------------------------------------------------------------------
    def _import_module(self) -> ModuleType:
        last_exc: Optional[Exception] = None
        for name in self._MODULE_NAMES:
            try:
                return importlib.import_module(name)
            except ImportError as exc:  # pragma: no cover - best effort
                last_exc = exc
        raise ScopinatorNotAvailableError("scopinator package is not installed") from last_exc

    def _related_modules(self) -> Iterable[ModuleType]:
        visited: set[str] = set()
        modules: list[ModuleType] = []
        base_modules: list[ModuleType] = []

        if self._module:
            modules.append(self._module)
            base_modules.append(self._module)
            visited.add(self._module.__name__)

        base_name = self._module.__name__.split(".")[0]
        for suffix in self._SUBMODULE_NAMES:
            try:
                mod = importlib.import_module(f"{base_name}.{suffix}")
            except ImportError:  # pragma: no cover - optional modules
                continue
            if mod.__name__ not in visited:
                modules.append(mod)
                visited.add(mod.__name__)

        return modules

    def _iter_candidate_ctors(self, module: ModuleType) -> Iterable[type]:
        seen: set[type] = set()
        for name in self._CONSTRUCTOR_NAMES:
            attr = getattr(module, name, None)
            if inspect.isclass(attr) and attr not in seen:
                seen.add(attr)
                yield attr

    def _create_client(self, module: ModuleType):
        errors: list[str] = []
        for mod in self._related_modules():
            for ctor in self._iter_candidate_ctors(mod):
                client = self._try_instantiate(ctor, errors)
                if client:
                    self._connect_client(client)
                    return client

            for func_name in self._FUNCTION_CONSTRUCTORS:
                func = getattr(mod, func_name, None)
                if callable(func):
                    client = self._try_constructor_function(func, errors)
                    if client:
                        self._connect_client(client)
                        return client

        raise ScopinatorNotAvailableError(
            "unable to locate a compatible scopinator client constructor: "
            + "; ".join(errors) if errors else "unknown reason"
        )

    def _try_constructor_function(self, func: Callable[..., Any], errors: list[str]):
        attempts = [
            {"host": self.host, "port": self.port, "timeout": self.timeout},
            {"ip": self.host, "port": self.port, "timeout": self.timeout},
            {"address": self.host, "port": self.port},
            {"base_url": f"http://{self.host}:{self.port}"},
            {},
        ]
        for kwargs in attempts:
            clean_kwargs = {k: v for k, v in kwargs.items() if v is not None}
            try:
                return func(**clean_kwargs)
            except TypeError:
                continue
            except Exception as exc:  # pragma: no cover - best effort
                errors.append(f"{func.__name__}: {exc}")
                break
        return None

    def _try_instantiate(self, ctor: type, errors: list[str]):
        kwargs_attempts = [
            {"host": self.host, "port": self.port, "timeout": self.timeout, "logger": self.logger},
            {"host": self.host, "port": self.port, "timeout": self.timeout},
            {"host": self.host, "port": self.port},
            {"address": self.host, "port": self.port},
            {"ip": self.host, "port": self.port},
            {"hostname": self.host, "port": self.port},
            {"base_url": f"http://{self.host}:{self.port}"},
            {},
        ]
        for kwargs in kwargs_attempts:
            clean_kwargs = {k: v for k, v in kwargs.items() if v is not None}
            try:
                return ctor(**clean_kwargs)
            except TypeError:
                continue
            except Exception as exc:  # pragma: no cover - best effort
                errors.append(f"{ctor.__name__}: {exc}")
                break

        args_attempts = [
            (self.host, self.port, self.logger),
            (self.host, self.port),
            (self.host,),
            (),
        ]
        for args in args_attempts:
            try:
                return ctor(*args)
            except TypeError:
                continue
            except Exception as exc:  # pragma: no cover - best effort
                errors.append(f"{ctor.__name__}: {exc}")
                break
        return None

    def _connect_client(self, client: Any) -> None:
        for name in ("connect", "open", "start", "ensure_connection", "ensure_connected"):
            method = getattr(client, name, None)
            if callable(method):
                try:
                    method()
                    return
                except TypeError:
                    try:
                        method(self.host, self.port)
                        return
                    except Exception:  # pragma: no cover - best effort
                        continue
                except Exception:  # pragma: no cover - best effort
                    continue

    def _collect_callables(self, names: Sequence[str]) -> list[Callable[..., Any]]:
        callables: list[Callable[..., Any]] = []
        sources: list[Any] = [self._client]
        sources.extend(self._related_modules())
        for source in sources:
            if source is None:
                continue
            for name in names:
                attr = getattr(source, name, None)
                if callable(attr) and attr not in callables:
                    callables.append(attr)
        return callables

    # ------------------------------------------------------------------
    # invocation helpers
    # ------------------------------------------------------------------
    def _invoke_candidates(
        self,
        candidates: Sequence[Callable[..., Any]],
        payload: dict[str, Any],
        *,
        wait: bool,
    ) -> Any:
        if not candidates:
            raise ScopinatorCallError("no callable candidates available")

        errors: list[str] = []
        for func in candidates:
            try:
                result = self._invoke_callable(func, payload, wait=wait)
            except TypeError as exc:
                errors.append(f"{func.__name__}: {exc}")
                continue
            except Exception as exc:  # pragma: no cover - best effort
                errors.append(f"{func.__name__}: {exc}")
                continue
            return self._normalise_result(result)

        raise ScopinatorCallError("; ".join(errors))

    def _invoke_callable(self, func: Callable[..., Any], payload: dict[str, Any], *, wait: bool) -> Any:
        method = payload.get("method")
        params = payload.get("params")
        message_id = payload.get("id")
        raw = payload.get("raw")

        base_kwargs = {}
        if self.timeout is not None:
            base_kwargs["timeout"] = self.timeout
        if wait is not None:
            base_kwargs["wait"] = wait

        attempts: list[Callable[[], Any]] = []
        if method is not None:
            attempts.extend(
                [
                    lambda: func(method, params=params, message_id=message_id, **base_kwargs),
                    lambda: func(method, params=params, id=message_id, **base_kwargs),
                    lambda: func(method, params=params, **base_kwargs),
                    lambda: func(method, message_id=message_id, **base_kwargs),
                    lambda: func(method, **base_kwargs),
                ]
            )

            if isinstance(params, dict):
                attempts.append(lambda: func(method, **params))
                attempts.append(lambda: func(method, **params, **base_kwargs))
            elif isinstance(params, (list, tuple)):
                attempts.append(lambda: func(method, *params))

            attempts.append(lambda: func({k: v for k, v in payload.items() if k != "raw"}))
            attempts.append(lambda: func(json.dumps({k: v for k, v in payload.items() if k != "raw"})))
        elif raw is not None:
            attempts.append(lambda: func(raw))

        attempts.append(lambda: func(payload))

        for attempt in attempts:
            try:
                return attempt()
            except TypeError:
                continue

        raise TypeError("no compatible signature found for scopinator callable")

    def _normalise_result(self, result: Any) -> Any:
        if result is None:
            return None
        if isinstance(result, (bytes, bytearray)):
            try:
                return json.loads(result.decode("utf-8"))
            except Exception:  # pragma: no cover - best effort
                return result
        if isinstance(result, str):
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                return {"result": result}
        return result


__all__ = [
    "ScopinatorBridge",
    "ScopinatorCallError",
    "ScopinatorNotAvailableError",
]
